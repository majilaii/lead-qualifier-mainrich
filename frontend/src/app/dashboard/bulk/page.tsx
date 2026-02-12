"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../components/auth/SessionProvider";

interface Template {
  id: string;
  name: string;
  search_context: Record<string, string | null>;
}

interface PipelineResult {
  title: string;
  domain: string;
  url: string;
  score: number;
  tier: string;
  reasoning: string;
  contacts?: { full_name: string; job_title?: string; email?: string }[];
}

export default function BulkImportPage() {
  const { session } = useAuth();
  const router = useRouter();

  const [domains, setDomains] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [templatesLoaded, setTemplatesLoaded] = useState(false);

  // ICP context fields (optional, for qualification)
  const [industry, setIndustry] = useState("");
  const [techFocus, setTechFocus] = useState("");
  const [criteria, setCriteria] = useState("");

  // Pipeline state
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ index: 0, total: 0, phase: "", company: "" });
  const [results, setResults] = useState<PipelineResult[]>([]);
  const [summary, setSummary] = useState<{ hot: number; review: number; rejected: number; failed: number } | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load templates on first render
  if (!templatesLoaded && session?.access_token) {
    setTemplatesLoaded(true);
    fetch("/api/proxy/templates", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setTemplates)
      .catch(() => {});
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      if (!text) return;

      // Parse CSV — extract domains from first column or 'domain'/'website' column
      const lines = text.split("\n").filter((l) => l.trim());
      if (lines.length === 0) return;

      const header = lines[0].toLowerCase();
      const hasHeader = header.includes("domain") || header.includes("website") || header.includes("url");
      const dataLines = hasHeader ? lines.slice(1) : lines;

      const extracted = dataLines
        .map((line) => {
          const cols = line.split(",").map((c) => c.trim().replace(/"/g, ""));
          // Try to find a domain-like value
          for (const col of cols) {
            const cleaned = col
              .replace(/^https?:\/\//, "")
              .replace(/^www\./, "")
              .split("/")[0];
            if (cleaned.includes(".") && cleaned.length > 3) {
              return cleaned;
            }
          }
          return "";
        })
        .filter(Boolean);

      setDomains(extracted.join("\n"));
    };
    reader.readAsText(file);
    // Reset input so same file can be re-selected
    e.target.value = "";
  };

  const applyTemplate = (templateId: string) => {
    const t = templates.find((t) => t.id === templateId);
    if (!t) return;
    setSelectedTemplate(templateId);
    setIndustry(t.search_context.industry || "");
    setTechFocus(t.search_context.technology_focus || t.search_context.technologyFocus || "");
    setCriteria(t.search_context.qualifying_criteria || t.search_context.qualifyingCriteria || "");
  };

  const startPipeline = async () => {
    if (!session?.access_token || !domains.trim()) return;

    const domainList = domains
      .split(/[\n,;]+/)
      .map((d) => d.trim())
      .filter((d) => d && d.includes("."));

    if (domainList.length === 0) return;

    setRunning(true);
    setResults([]);
    setSummary(null);
    setSearchId(null);
    setProgress({ index: 0, total: domainList.length, phase: "starting", company: "" });

    const searchContext = industry || techFocus || criteria
      ? { industry: industry || null, technology_focus: techFocus || null, qualifying_criteria: criteria || null }
      : null;

    try {
      const res = await fetch("/api/proxy/pipeline/bulk", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          domains: domainList,
          search_context: searchContext,
          use_vision: true,
        }),
      });

      if (!res.ok || !res.body) {
        setRunning(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "init") {
              setProgress((p) => ({ ...p, total: event.total }));
            } else if (event.type === "progress") {
              setProgress({
                index: event.index,
                total: event.total,
                phase: event.phase,
                company: event.company?.title || event.company?.domain || "",
              });
            } else if (event.type === "result") {
              setResults((prev) => [...prev, event.company]);
            } else if (event.type === "complete") {
              setSummary(event.summary);
              if (event.search_id) setSearchId(event.search_id);
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } finally {
      setRunning(false);
    }
  };

  const pctDone = progress.total > 0 ? Math.round(((progress.index + 1) / progress.total) * 100) : 0;

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
          Bulk Domain Import
        </h1>
        <p className="font-sans text-sm text-text-muted mt-1">
          Paste domains or upload a CSV — qualify all at once without the chat flow.
        </p>
      </div>

      {/* Template selector */}
      {templates.length > 0 && (
        <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-3">
          <h2 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
            Apply ICP Template
          </h2>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                setSelectedTemplate(null);
                setIndustry("");
                setTechFocus("");
                setCriteria("");
              }}
              className={`font-mono text-[10px] px-3 py-1.5 rounded-md border transition-all cursor-pointer ${
                !selectedTemplate
                  ? "bg-secondary/10 border-secondary/30 text-secondary"
                  : "border-border text-text-muted hover:border-border-bright"
              }`}
            >
              None
            </button>
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => applyTemplate(t.id)}
                className={`font-mono text-[10px] px-3 py-1.5 rounded-md border transition-all cursor-pointer ${
                  selectedTemplate === t.id
                    ? "bg-secondary/10 border-secondary/30 text-secondary"
                    : "border-border text-text-muted hover:border-border-bright"
                }`}
              >
                {t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Domain input */}
      <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
            Domains
          </h2>
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="font-mono text-[10px] text-secondary/60 hover:text-secondary uppercase tracking-[0.15em] transition-colors cursor-pointer"
            >
              Upload CSV
            </button>
          </div>
        </div>
        <textarea
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
          placeholder={"acme.com\nexample.de\nmanufacturer.co.uk\n\nOne domain per line, or comma-separated"}
          className="w-full bg-surface-3 border border-border rounded-lg p-4 font-mono text-xs text-text-primary placeholder:text-text-dim resize-none focus:outline-none focus:border-secondary/40 min-h-[160px]"
          disabled={running}
        />
        <p className="font-mono text-[9px] text-text-dim">
          {domains.split(/[\n,;]+/).filter((d) => d.trim() && d.includes(".")).length} valid domains
        </p>
      </div>

      {/* Optional ICP context */}
      <details className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <summary className="px-5 py-4 font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] cursor-pointer hover:text-text-primary transition-colors">
          Optional: Set ICP Context (for smarter qualification)
        </summary>
        <div className="px-5 pb-5 space-y-3 border-t border-border-dim pt-4">
          <div>
            <label className="font-mono text-[9px] text-text-dim uppercase tracking-wider mb-1 block">Industry</label>
            <input
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              placeholder="e.g. CNC machining, industrial automation"
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40"
            />
          </div>
          <div>
            <label className="font-mono text-[9px] text-text-dim uppercase tracking-wider mb-1 block">Technology Focus</label>
            <input
              value={techFocus}
              onChange={(e) => setTechFocus(e.target.value)}
              placeholder="e.g. servo motors, precision gears, robotics"
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40"
            />
          </div>
          <div>
            <label className="font-mono text-[9px] text-text-dim uppercase tracking-wider mb-1 block">Qualifying Criteria</label>
            <input
              value={criteria}
              onChange={(e) => setCriteria(e.target.value)}
              placeholder="e.g. companies that manufacture hardware products"
              className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40"
            />
          </div>
        </div>
      </details>

      {/* Start button */}
      <button
        onClick={startPipeline}
        disabled={running || !domains.trim()}
        className="w-full inline-flex items-center justify-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-4 rounded-lg hover:bg-white/85 transition-colors disabled:opacity-40 cursor-pointer"
      >
        {running ? (
          <>
            <span className="w-4 h-4 border-2 border-void border-t-transparent rounded-full animate-spin" />
            Processing…
          </>
        ) : (
          `Qualify ${domains.split(/[\n,;]+/).filter((d) => d.trim() && d.includes(".")).length} Domains`
        )}
      </button>

      {/* Progress */}
      {running && progress.total > 0 && (
        <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-text-muted uppercase tracking-wider">
              {progress.phase === "crawling" ? "Crawling" : "Qualifying"}{" "}
              {progress.company}
            </span>
            <span className="font-mono text-xs text-text-primary font-bold">
              {progress.index + 1} / {progress.total}
            </span>
          </div>
          <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
            <div
              className="h-full bg-secondary rounded-full transition-all duration-300"
              style={{ width: `${pctDone}%` }}
            />
          </div>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && (
        <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-border-dim flex items-center justify-between">
            <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
              Results ({results.length})
            </h2>
            {summary && (
              <div className="flex gap-3">
                <span className="font-mono text-[10px] text-hot">{summary.hot} hot</span>
                <span className="font-mono text-[10px] text-review">{summary.review} review</span>
                <span className="font-mono text-[10px] text-text-dim">{summary.rejected} rejected</span>
              </div>
            )}
          </div>
          <div className="divide-y divide-border-dim max-h-[400px] overflow-y-auto">
            {results.sort((a, b) => b.score - a.score).map((r, i) => (
              <div key={i} className="px-5 py-3 flex items-center gap-3">
                <span
                  className={`font-mono text-xs font-bold w-8 text-center ${
                    r.tier === "hot" ? "text-hot" : r.tier === "review" ? "text-review" : "text-text-dim"
                  }`}
                >
                  {r.score}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-text-primary truncate">{r.title}</p>
                  <p className="font-mono text-[10px] text-text-dim truncate">{r.domain}</p>
                </div>
                <span
                  className={`font-mono text-[9px] uppercase tracking-wider ${
                    r.tier === "hot" ? "text-hot" : r.tier === "review" ? "text-review" : "text-text-dim"
                  }`}
                >
                  {r.tier}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Complete — link to leads & pipeline */}
      {summary && searchId && (
        <div className="flex gap-3">
          <button
            onClick={() => router.push("/dashboard/leads")}
            className="flex-1 inline-flex items-center justify-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
          >
            View Leads →
          </button>
          <button
            onClick={() => router.push("/dashboard/pipeline")}
            className="flex-1 inline-flex items-center justify-center gap-2 bg-surface-3 border border-border text-text-muted font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:text-text-primary transition-colors cursor-pointer"
          >
            All Pipeline Runs
          </button>
        </div>
      )}
    </div>
  );
}
