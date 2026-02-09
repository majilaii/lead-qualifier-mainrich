"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  type KeyboardEvent,
} from "react";
import Link from "next/link";

/* ══════════════════════════════════════════════
   Types
   ══════════════════════════════════════════════ */

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

interface Readiness {
  industry: boolean;
  companyProfile: boolean;
  technologyFocus: boolean;
  qualifyingCriteria: boolean;
  isReady: boolean;
}

interface ExtractedContext {
  industry: string | null;
  companyProfile: string | null;
  technologyFocus: string | null;
  qualifyingCriteria: string | null;
  disqualifiers: string | null;
}

interface SearchCompany {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  score: number | null;
  source_query?: string;
}

interface QualifiedCompany {
  title: string;
  domain: string;
  url: string;
  score: number;
  tier: "hot" | "review" | "rejected";
  hardware_type?: string | null;
  industry_category?: string | null;
  reasoning: string;
  key_signals: string[];
  red_flags: string[];
}

interface PipelineProgress {
  index: number;
  total: number;
  phase: "crawling" | "qualifying";
  company: string;
}

interface PipelineSummary {
  hot: number;
  review: number;
  rejected: number;
  failed: number;
}

type Phase =
  | "chat"
  | "searching"
  | "search-complete"
  | "qualifying"
  | "complete";

const INITIAL_READINESS: Readiness = {
  industry: false,
  companyProfile: false,
  technologyFocus: false,
  qualifyingCriteria: false,
  isReady: false,
};

const BACKEND_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000")
    : "http://localhost:8000";

/* ══════════════════════════════════════════════
   CSV Export Utility
   ══════════════════════════════════════════════ */

function escapeCsvField(value: string): string {
  if (!value) return "";
  // If field contains comma, quote, or newline — wrap in quotes and escape inner quotes
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function exportToCsv(companies: QualifiedCompany[], filename?: string, enrichedContacts?: Map<string, EnrichedContact>) {
  const hasEnrichment = enrichedContacts && enrichedContacts.size > 0;

  const headers = [
    "Tier",
    "Score",
    "Company",
    "Domain",
    "URL",
    "Company Type",
    "Industry",
    "Reasoning",
    "Key Signals",
    "Red Flags",
    ...(hasEnrichment ? ["Contact Email", "Contact Job Title", "Contact Source"] : []),
  ];

  const rows = companies
    .sort((a, b) => b.score - a.score)
    .map((c) => {
      const contact = enrichedContacts?.get(c.domain);
      return [
        c.tier.toUpperCase(),
        String(c.score),
        escapeCsvField(c.title),
        c.domain,
        c.url,
        escapeCsvField(c.hardware_type || ""),
        escapeCsvField(c.industry_category || ""),
        escapeCsvField(c.reasoning),
        escapeCsvField(c.key_signals.join("; ")),
        escapeCsvField(c.red_flags.join("; ")),
        ...(hasEnrichment
          ? [
              escapeCsvField(contact?.email || ""),
              escapeCsvField(contact?.job_title || ""),
              escapeCsvField(contact?.source || ""),
            ]
          : []),
      ];
    });

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `hunt-leads-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function DownloadButton({
  companies,
  label,
  variant = "secondary",
  enrichedContacts,
}: {
  companies: QualifiedCompany[];
  label?: string;
  variant?: "primary" | "secondary";
  enrichedContacts?: Map<string, EnrichedContact>;
}) {
  return (
    <button
      onClick={() => exportToCsv(companies, undefined, enrichedContacts)}
      disabled={companies.length === 0}
      className={`inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.15em] px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${
        variant === "primary"
          ? "bg-text-primary text-void hover:bg-white/85"
          : "border border-border-dim text-text-muted hover:text-text-secondary hover:border-border"
      }`}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      {label || `CSV (${companies.length})`}
    </button>
  );
}

const SUGGESTIONS = [
  { text: "Find robotics startups building humanoid robots in the US", icon: "🤖" },
  { text: "Companies manufacturing BLDC motors for drones", icon: "⚡" },
  { text: "Medical device makers that use precision motors or magnets", icon: "🏥" },
  { text: "EV powertrain companies developing in-house motor technology", icon: "🔋" },
];

/* ══════════════════════════════════════════════
   Shared Sub-Components
   ══════════════════════════════════════════════ */

function ReadinessTracker({ readiness }: { readiness: Readiness }) {
  const steps: { key: keyof Readiness; label: string }[] = [
    { key: "industry", label: "Industry" },
    { key: "companyProfile", label: "Profile" },
    { key: "technologyFocus", label: "Technology" },
    { key: "qualifyingCriteria", label: "Criteria" },
    { key: "isReady", label: "Search" },
  ];

  return (
    <div className="hidden md:flex items-center gap-1.5">
      {steps.map((step, i) => {
        const done = readiness[step.key];
        return (
          <div key={step.key} className="flex items-center gap-1.5">
            {i > 0 && (
              <div className={`w-3 h-px transition-colors duration-500 ${done ? "bg-secondary/40" : "bg-border-dim"}`} />
            )}
            <div className="flex items-center gap-1">
              <div className={`w-1.5 h-1.5 rounded-full transition-all duration-500 ${done ? "bg-secondary shadow-[0_0_6px_rgba(129,140,248,0.4)]" : "bg-border"}`} />
              <span className={`font-mono text-[9px] uppercase tracking-[0.15em] transition-colors duration-500 ${done ? "text-secondary/70" : "text-text-dim"}`}>
                {step.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-slide-up">
      <div className="w-6 h-6 rounded-md flex items-center justify-center bg-secondary/10 text-secondary text-xs flex-shrink-0 mt-0.5">◈</div>
      <div className="flex items-center gap-1.5 py-3">
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "200ms" }} />
        <span className="w-1.5 h-1.5 bg-text-muted rounded-full animate-typing-dot" style={{ animationDelay: "400ms" }} />
      </div>
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1.5">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1.5" />;
        const rendered = line.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-medium">$1</strong>');

        const numberedMatch = line.match(/^(\d+)\.\s+(.*)/);
        if (numberedMatch) {
          return (
            <div key={i} className="flex gap-2.5 pl-0.5">
              <span className="text-secondary/50 font-mono text-xs mt-px min-w-[1rem] text-right">{numberedMatch[1]}.</span>
              <span dangerouslySetInnerHTML={{ __html: numberedMatch[2].replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-medium">$1</strong>') }} />
            </div>
          );
        }

        if (line.trim().startsWith("- ") || line.trim().startsWith("• ")) {
          return (
            <div key={i} className="flex gap-2.5 pl-0.5">
              <span className="text-secondary/50 mt-1.5">
                <svg width="4" height="4" viewBox="0 0 4 4"><circle cx="2" cy="2" r="2" fill="currentColor" /></svg>
              </span>
              <span dangerouslySetInnerHTML={{ __html: rendered.replace(/^[-•]\s*/, "") }} />
            </div>
          );
        }

        return <p key={i} dangerouslySetInnerHTML={{ __html: rendered }} />;
      })}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} animate-slide-up`}>
      <div className={`flex items-start gap-3 max-w-[88%] md:max-w-[75%] ${isUser ? "flex-row-reverse" : ""}`}>
        {!isUser && (
          <div className="w-6 h-6 rounded-md flex items-center justify-center bg-secondary/10 text-secondary text-xs flex-shrink-0 mt-0.5">◈</div>
        )}
        <div className={`rounded-2xl px-4 py-3 ${isUser ? "bg-surface-3 border border-border text-text-primary font-sans text-sm" : "text-text-secondary font-sans text-sm leading-relaxed"}`}>
          {isUser ? <p className="whitespace-pre-wrap">{message.content}</p> : <MessageContent content={message.content} />}
        </div>
      </div>
    </div>
  );
}

function WelcomeScreen({ onSuggestionClick }: { onSuggestionClick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 py-12">
      <div className="animate-slide-up flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-secondary/10 border border-secondary/20 flex items-center justify-center text-secondary text-2xl mb-6">◈</div>
        <h1 className="font-mono text-xl md:text-2xl font-bold text-text-primary tracking-tight mb-2 text-center">What are you hunting?</h1>
        <p className="font-sans text-sm text-text-muted mb-10 text-center max-w-md leading-relaxed">
          Describe your ideal customer. I&apos;ll ask a few follow-up questions to sharpen the search, then find matching companies across the web.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
          {SUGGESTIONS.map((s) => (
            <button key={s.text} onClick={() => onSuggestionClick(s.text)} className="text-left bg-surface-2 border border-border hover:border-secondary/30 hover:bg-surface-3 rounded-xl px-4 py-3.5 transition-all duration-200 group cursor-pointer">
              <span className="text-base mb-1.5 block">{s.icon}</span>
              <p className="font-sans text-xs text-text-muted group-hover:text-text-secondary transition-colors leading-relaxed">{s.text}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ChatInput({ onSend, isLoading }: { onSend: (text: string) => void; isLoading: boolean }) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 200) + "px"; }
  }, []);

  useEffect(() => { adjustHeight(); }, [input, adjustHeight]);
  useEffect(() => { textareaRef.current?.focus(); }, []);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [input, isLoading, onSend]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }, [handleSend]);

  return (
    <div className="border-t border-border-dim bg-surface-1/80 backdrop-blur-md px-4 py-4 flex-shrink-0">
      <div className="max-w-3xl mx-auto">
        <div className="relative flex items-end bg-surface-2 border border-border rounded-2xl focus-within:border-secondary/30 transition-colors duration-200">
          <textarea ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder="Describe your ideal customer..." rows={1} disabled={isLoading} className="flex-1 bg-transparent text-text-primary font-sans text-sm px-4 py-3.5 resize-none outline-none placeholder:text-text-dim disabled:opacity-50 max-h-[200px]" />
          <button onClick={handleSend} disabled={!input.trim() || isLoading} className="flex-shrink-0 m-2 p-2 rounded-xl bg-text-primary text-void disabled:opacity-15 disabled:cursor-not-allowed hover:bg-white/85 transition-all duration-200 cursor-pointer" aria-label="Send message">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
          </button>
        </div>
        <p className="font-mono text-[10px] text-text-dim mt-2 text-center select-none">Enter to send · Shift+Enter for newline</p>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════
   Pipeline Phase Components
   ══════════════════════════════════════════════ */

function SearchActionCard({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-secondary/20 rounded-2xl p-5 mt-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-secondary text-sm">◈</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-secondary/60">Ready to search</span>
        </div>
        <p className="font-sans text-sm text-text-secondary mb-4">
          I have enough context to find matching companies. Click below to generate search queries and scan the web.
        </p>
        <button onClick={onLaunch} className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-6 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer">
          Launch Search
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  );
}

function SearchingCard() {
  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl p-5 mt-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-5 h-5 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
          <span className="font-mono text-xs text-secondary">Generating queries &amp; searching...</span>
        </div>
        <div className="space-y-2">
          <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-secondary/30 rounded-full animate-pulse" style={{ width: "60%" }} />
          </div>
          <p className="font-sans text-xs text-text-dim">Generating semantic queries via AI, then searching across the web with Exa...</p>
        </div>
      </div>
    </div>
  );
}

function SearchResultsCard({
  companies,
  onQualify,
}: {
  companies: SearchCompany[];
  onQualify: (count: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? companies : companies.slice(0, 8);
  const remaining = companies.length - 8;
  const topN = Math.min(10, companies.length);
  const hasMany = companies.length > 12;

  // Estimate time: ~35s per company
  const estTop = Math.ceil((topN * 35) / 60);
  const estAll = Math.ceil((companies.length * 35) / 60);

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-dim">
          <div className="flex items-center gap-2">
            <span className="text-secondary text-sm">◈</span>
            <span className="font-mono text-xs text-text-primary">Found {companies.length} companies</span>
          </div>
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-text-dim">Exa AI · sorted by relevance</span>
        </div>

        {/* Company list */}
        <div className="divide-y divide-border-dim max-h-[320px] overflow-y-auto">
          {shown.map((c, i) => (
            <div key={c.domain} className="px-5 py-3 hover:bg-surface-3/50 transition-colors">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-mono text-[10px] text-text-dim min-w-[1.2rem] text-right">{i + 1}.</span>
                <span className="font-mono text-[11px] text-secondary/60">{c.domain}</span>
                {c.score != null && (
                  <span className="font-mono text-[9px] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{(c.score * 100).toFixed(0)}%</span>
                )}
              </div>
              <p className="font-sans text-xs text-text-secondary leading-relaxed line-clamp-2 pl-[1.7rem]">
                {c.title}{c.snippet ? ` — ${c.snippet}` : ""}
              </p>
            </div>
          ))}
        </div>

        {remaining > 0 && !expanded && (
          <button onClick={() => setExpanded(true)} className="w-full px-5 py-2 text-center font-mono text-[10px] text-text-muted hover:text-text-secondary border-t border-border-dim hover:bg-surface-3/50 transition-colors cursor-pointer">
            + {remaining} more companies
          </button>
        )}

        {/* Batch size buttons */}
        <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
          <div className="flex flex-wrap items-center gap-2.5">
            {hasMany && (
              <button
                onClick={() => onQualify(topN)}
                className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer"
              >
                Top {topN} · ~{estTop} min
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
              </button>
            )}
            <button
              onClick={() => onQualify(companies.length)}
              className={`inline-flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl transition-colors cursor-pointer ${
                hasMany
                  ? "bg-surface-3 border border-border text-text-secondary hover:bg-surface-3/80 hover:border-border-bright"
                  : "bg-text-primary text-void hover:bg-white/85"
              }`}
            >
              {hasMany ? `All ${companies.length}` : `Qualify ${companies.length}`} · ~{estAll} min
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
            </button>
          </div>
          <p className="font-mono text-[10px] text-text-dim mt-2">Crawls each website &amp; scores with AI · highest relevance processed first</p>
        </div>
      </div>
    </div>
  );
}

const TIER_STYLES = {
  hot: { label: "Hot Lead", color: "text-hot", bg: "bg-hot/10", border: "border-hot/20", icon: "🔥" },
  review: { label: "Review", color: "text-review", bg: "bg-review/10", border: "border-review/20", icon: "🔍" },
  rejected: { label: "Rejected", color: "text-rejected", bg: "bg-surface-3", border: "border-border", icon: "✕" },
};

function LiveResultsView({
  progress,
  qualifiedCompanies,
  searchCompanies,
  startTime,
}: {
  progress: PipelineProgress | null;
  qualifiedCompanies: QualifiedCompany[];
  searchCompanies: SearchCompany[];
  startTime: number;
}) {
  const [activeTab, setActiveTab] = useState<"results" | "queue">("results");
  const [expandedCompany, setExpandedCompany] = useState<string | null>(null);

  const total = searchCompanies.length;
  const done = qualifiedCompanies.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  // Live ETA calculation
  const elapsed = (Date.now() - startTime) / 1000;
  const avgPerCompany = done > 0 ? elapsed / done : 35;
  const remaining = total - done;
  const etaSeconds = Math.ceil(remaining * avgPerCompany);
  const etaMin = Math.floor(etaSeconds / 60);
  const etaSec = etaSeconds % 60;
  const etaStr = etaMin > 0 ? `~${etaMin}m ${etaSec}s` : `~${etaSec}s`;

  // Live tier counts
  const hotCount = qualifiedCompanies.filter((c) => c.tier === "hot").length;
  const reviewCount = qualifiedCompanies.filter((c) => c.tier === "review").length;

  // Sort results: hot first, then by score descending
  const sortedResults = [...qualifiedCompanies].sort((a, b) => {
    if (a.tier === "hot" && b.tier !== "hot") return -1;
    if (b.tier === "hot" && a.tier !== "hot") return 1;
    return b.score - a.score;
  });

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Progress header */}
        <div className="px-5 py-3 border-b border-border-dim">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
              <span className="font-mono text-xs text-text-primary">Qualifying leads</span>
            </div>
            <div className="flex items-center gap-3">
              {hotCount > 0 && <span className="font-mono text-[10px] text-hot">🔥 {hotCount}</span>}
              {reviewCount > 0 && <span className="font-mono text-[10px] text-review">🔍 {reviewCount}</span>}
              <span className="font-mono text-xs text-text-muted">{done}/{total}</span>
              <span className="font-mono text-[10px] text-text-dim">{etaStr}</span>
              {done >= 2 && <DownloadButton companies={qualifiedCompanies} label="CSV" />}
            </div>
          </div>
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-secondary rounded-full transition-all duration-500 ease-out" style={{ width: `${pct}%` }} />
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-border-dim">
          <button
            onClick={() => setActiveTab("results")}
            className={`flex-1 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors cursor-pointer ${
              activeTab === "results"
                ? "text-secondary border-b-2 border-secondary bg-secondary/5"
                : "text-text-dim hover:text-text-muted"
            }`}
          >
            Results ({done})
          </button>
          <button
            onClick={() => setActiveTab("queue")}
            className={`flex-1 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors cursor-pointer ${
              activeTab === "queue"
                ? "text-secondary border-b-2 border-secondary bg-secondary/5"
                : "text-text-dim hover:text-text-muted"
            }`}
          >
            Queue ({remaining})
          </button>
        </div>

        {/* Results tab — interactive, browsable */}
        {activeTab === "results" && (
          <div className="max-h-[450px] overflow-y-auto divide-y divide-border-dim">
            {sortedResults.length === 0 && (
              <div className="px-5 py-8 text-center">
                <p className="font-mono text-xs text-text-dim">Results will appear here as companies are qualified...</p>
                {progress && (
                  <p className="font-mono text-[10px] text-secondary/60 mt-2">
                    Currently {progress.phase === "crawling" ? "crawling" : "analyzing"} {progress.company}
                  </p>
                )}
              </div>
            )}
            {sortedResults.map((c) => {
              const style = TIER_STYLES[c.tier];
              const isExpanded = expandedCompany === c.domain;
              return (
                <div key={c.domain} className="animate-slide-up">
                  <button
                    onClick={() => setExpandedCompany(isExpanded ? null : c.domain)}
                    className="w-full px-5 py-3 flex items-center gap-3 hover:bg-surface-3/50 transition-colors cursor-pointer text-left"
                  >
                    <span className={`font-mono text-xs font-bold min-w-[2rem] text-right ${style.color}`}>{c.score}/10</span>
                    <span className="font-mono text-[11px] text-text-secondary flex-1 truncate">{c.domain}</span>
                    <span className={`font-mono text-[9px] uppercase tracking-[0.15em] px-2 py-0.5 rounded ${style.bg} ${style.color} ${style.border} border`}>
                      {style.icon} {style.label}
                    </span>
                    <svg
                      width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      className={`text-text-dim transition-transform duration-200 flex-shrink-0 ${isExpanded ? "rotate-90" : ""}`}
                    >
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </button>
                  {isExpanded && (
                    <div className="px-5 pb-3 bg-surface-3/30 border-t border-border-dim">
                      <div className="pl-[2.5rem] pt-2.5 space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[11px] text-secondary/60 hover:text-secondary transition-colors">
                            {c.url} ↗
                          </a>
                          {c.hardware_type && (
                            <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{c.hardware_type}</span>
                          )}
                          {c.industry_category && (
                            <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{c.industry_category}</span>
                          )}
                        </div>
                        <p className="font-sans text-xs text-text-muted leading-relaxed">{c.reasoning}</p>
                        {c.key_signals.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.key_signals.map((s, i) => (
                              <span key={i} className="font-mono text-[9px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">{s}</span>
                            ))}
                          </div>
                        )}
                        {c.red_flags.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.red_flags.map((f, i) => (
                              <span key={i} className="font-mono text-[9px] text-red-400/60 bg-red-400/5 border border-red-400/10 rounded px-1.5 py-0.5">{f}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Queue tab — shows what's processing / pending */}
        {activeTab === "queue" && (
          <div className="max-h-[450px] overflow-y-auto divide-y divide-border-dim">
            {/* Currently processing */}
            {progress && (
              <div className="px-5 py-2.5 flex items-center gap-3 bg-secondary/5">
                <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin min-w-[2rem] flex items-center justify-center" />
                <span className="font-mono text-[11px] text-secondary flex-1 truncate">{progress.company}</span>
                <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-secondary/50">
                  {progress.phase === "crawling" ? "Crawling..." : "Qualifying..."}
                </span>
              </div>
            )}
            {/* Pending */}
            {searchCompanies.slice(done + (progress ? 1 : 0)).map((c, i) => (
              <div key={c.domain} className="px-5 py-2.5 flex items-center gap-3 opacity-40">
                <span className="font-mono text-[10px] min-w-[2rem] text-right text-text-dim">{done + (progress ? 1 : 0) + i + 1}</span>
                <span className="font-mono text-[11px] text-text-dim flex-1 truncate">{c.domain}</span>
              </div>
            ))}
            {remaining === 0 && !progress && (
              <div className="px-5 py-6 text-center">
                <p className="font-mono text-xs text-text-dim">All companies processed</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface EnrichedContact {
  domain: string;
  title: string;
  url: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  source: string | null;
  found: boolean;
}

function ResultsSummaryCard({ qualifiedCompanies, summary, remainingCount, onContinue, enrichedContacts, setEnrichedContacts, enrichDone, setEnrichDone }: {
  qualifiedCompanies: QualifiedCompany[];
  summary: PipelineSummary;
  remainingCount: number;
  onContinue: (count: number) => void;
  enrichedContacts: Map<string, EnrichedContact>;
  setEnrichedContacts: React.Dispatch<React.SetStateAction<Map<string, EnrichedContact>>>;
  enrichDone: boolean;
  setEnrichDone: React.Dispatch<React.SetStateAction<boolean>>;
}) {
  const [expandedTier, setExpandedTier] = useState<string | null>("hot");

  // Enrichment progress (local — fine to reset)
  const [enriching, setEnriching] = useState(false);
  const [enrichProgress, setEnrichProgress] = useState<{ index: number; total: number } | null>(null);

  const hot = qualifiedCompanies.filter((c) => c.tier === "hot").sort((a, b) => b.score - a.score);
  const review = qualifiedCompanies.filter((c) => c.tier === "review").sort((a, b) => b.score - a.score);
  const rejected = qualifiedCompanies.filter((c) => c.tier === "rejected").sort((a, b) => b.score - a.score);
  const nonRejected = qualifiedCompanies.filter((c) => c.tier !== "rejected").sort((a, b) => b.score - a.score);

  // Enrich hot leads (and optionally review)
  const enrichLeads = useCallback(async (companies: QualifiedCompany[]) => {
    if (companies.length === 0) return;
    setEnriching(true);
    setEnrichDone(false);
    setEnrichProgress({ index: 0, total: companies.length });

    try {
      const response = await fetch(`${BACKEND_URL}/api/enrich`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companies: companies.map((c) => ({
            domain: c.domain,
            title: c.title,
            url: c.url,
          })),
        }),
      });

      if (!response.ok || !response.body) {
        console.error("Enrichment failed:", response.status);
        setEnriching(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const match = part.match(/^data:\s*(.*)/);
          if (!match) continue;

          try {
            const event = JSON.parse(match[1]);

            if (event.type === "progress") {
              setEnrichProgress({ index: event.index, total: event.total });
            } else if (event.type === "result" && event.contact) {
              setEnrichedContacts((prev) => {
                const next = new Map(prev);
                next.set(event.contact.domain, event.contact);
                return next;
              });
              setEnrichProgress({ index: event.index + 1, total: event.total });
            } else if (event.type === "complete") {
              setEnriching(false);
              setEnrichDone(true);
              setEnrichProgress(null);
            }
          } catch {
            // Skip unparseable
          }
        }
      }
    } catch (err) {
      console.error("Enrichment error:", err);
      setEnriching(false);
    }
  }, []);

  const tiers = [
    { key: "hot", label: "Hot Leads", icon: "🔥", companies: hot, count: summary.hot },
    { key: "review", label: "Needs Review", icon: "🔍", companies: review, count: summary.review },
    { key: "rejected", label: "Rejected", icon: "✕", companies: rejected, count: summary.rejected },
  ];

  return (
    <div className="animate-slide-up max-w-3xl mx-auto">
      <div className="bg-surface-2 border border-border rounded-2xl overflow-hidden mt-4">
        {/* Summary header */}
        <div className="px-5 py-4 border-b border-border-dim">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-secondary text-sm">◈</span>
              <span className="font-mono text-xs text-text-primary font-semibold">Qualification Complete</span>
            </div>
            <div className="flex items-center gap-2">
              {hot.length > 0 && (
                <DownloadButton companies={hot} label={`Hot leads (${hot.length})`} variant="primary" enrichedContacts={enrichedContacts} />
              )}
              {nonRejected.length > hot.length && (
                <DownloadButton companies={nonRejected} label={`Hot + Review (${nonRejected.length})`} enrichedContacts={enrichedContacts} />
              )}
              <DownloadButton companies={qualifiedCompanies} label={`All (${qualifiedCompanies.length})`} enrichedContacts={enrichedContacts} />
            </div>
          </div>
          <div className="flex items-center gap-4 font-mono text-xs">
            <span className="text-hot">🔥 {summary.hot} hot</span>
            <span className="text-border-bright">|</span>
            <span className="text-review">🔍 {summary.review} review</span>
            <span className="text-border-bright">|</span>
            <span className="text-text-muted">✕ {summary.rejected} rejected</span>
            {summary.failed > 0 && (
              <>
                <span className="text-border-bright">|</span>
                <span className="text-text-dim">⚠ {summary.failed} failed</span>
              </>
            )}
          </div>
        </div>

        {/* Tier sections */}
        <div className="divide-y divide-border-dim">
          {tiers.map((tier) => {
            if (tier.count === 0) return null;
            const isExpanded = expandedTier === tier.key;
            const style = TIER_STYLES[tier.key as keyof typeof TIER_STYLES];

            return (
              <div key={tier.key}>
                <button
                  onClick={() => setExpandedTier(isExpanded ? null : tier.key)}
                  className="w-full px-5 py-3 flex items-center justify-between hover:bg-surface-3/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    <span className={`font-mono text-xs ${style.color}`}>{tier.icon}</span>
                    <span className="font-mono text-xs text-text-primary">{tier.label} ({tier.count})</span>
                  </div>
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    className={`text-text-dim transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>

                {isExpanded && (
                  <div className="border-t border-border-dim divide-y divide-border-dim">
                    {tier.companies.map((c) => {
                      const contact = enrichedContacts.get(c.domain);
                      return (
                      <div key={c.domain} className="px-5 py-3">
                        <div className="flex items-center gap-3 mb-1">
                          <span className={`font-mono text-xs font-bold ${style.color}`}>{c.score}/10</span>
                          <a href={c.url} target="_blank" rel="noopener noreferrer" className="font-mono text-[11px] text-secondary/60 hover:text-secondary transition-colors">
                            {c.domain} ↗
                          </a>
                          {c.hardware_type && (
                            <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">
                              {c.hardware_type}
                            </span>
                          )}
                        </div>
                        <p className="font-sans text-xs text-text-muted leading-relaxed mb-1.5">{c.reasoning}</p>
                        {c.key_signals.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {c.key_signals.slice(0, 4).map((s, i) => (
                              <span key={i} className="font-mono text-[9px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Enriched contact info */}
                        {contact && contact.found && (
                          <div className="mt-2 flex flex-wrap items-center gap-2 bg-secondary/5 border border-secondary/10 rounded-lg px-3 py-2">
                            <span className="font-mono text-[9px] text-secondary/40 uppercase tracking-[0.15em]">Contact</span>
                            {contact.job_title && (
                              <span className="font-mono text-[10px] text-text-secondary">{contact.job_title}</span>
                            )}
                            {contact.email && (
                              <a href={`mailto:${contact.email}`} className="font-mono text-[10px] text-secondary hover:text-secondary/80 transition-colors">
                                ✉ {contact.email}
                              </a>
                            )}
                            {contact.phone && (
                              <span className="font-mono text-[10px] text-text-secondary">📞 {contact.phone}</span>
                            )}
                            {contact.source && (
                              <span className="font-mono text-[8px] text-text-dim bg-surface-3 px-1 py-0.5 rounded">via {contact.source}</span>
                            )}
                          </div>
                        )}
                        {contact && !contact.found && (
                          <div className="mt-2 font-mono text-[9px] text-text-dim">No contact info found</div>
                        )}
                      </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Find Contacts action */}
        {hot.length > 0 && !enrichDone && (
          <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
            {enriching && enrichProgress ? (
              <div className="flex items-center gap-3">
                <div className="w-5 h-5 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
                <span className="font-mono text-xs text-text-secondary">
                  Finding contacts... {enrichProgress.index}/{enrichProgress.total}
                </span>
                <div className="flex-1 h-1 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-secondary/50 rounded-full transition-all duration-300"
                    style={{ width: `${Math.round((enrichProgress.index / enrichProgress.total) * 100)}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => enrichLeads(hot)}
                  className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-secondary/20 hover:border-secondary/40 transition-colors cursor-pointer"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  Find contacts for {hot.length} hot lead{hot.length > 1 ? "s" : ""}
                </button>
                {nonRejected.length > hot.length && (
                  <button
                    onClick={() => enrichLeads(nonRejected)}
                    className="inline-flex items-center gap-2 font-mono text-[10px] text-text-muted hover:text-secondary uppercase tracking-[0.15em] transition-colors cursor-pointer border border-border-dim hover:border-secondary/30 rounded-lg px-3 py-1.5"
                  >
                    Or all {nonRejected.length} qualified
                  </button>
                )}
                <span className="font-mono text-[10px] text-text-dim">Waterfull · Apollo · Hunter waterfall</span>
              </div>
            )}
          </div>
        )}
        {enrichDone && (
          <div className="px-5 py-3 border-t border-border-dim bg-secondary/5">
            <div className="flex items-center gap-2">
              <span className="text-secondary text-xs">✓</span>
              <span className="font-mono text-[10px] text-secondary/70">
                Contacts enriched — {Array.from(enrichedContacts.values()).filter((c) => c.found).length} found, {Array.from(enrichedContacts.values()).filter((c) => !c.found).length} not found
              </span>
            </div>
          </div>
        )}

        {/* Continue with remaining batch */}
        {remainingCount > 0 && (
          <div className="px-5 py-4 border-t border-border-dim bg-surface-1/50">
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => onContinue(remainingCount)}
                className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-xl hover:bg-white/85 transition-colors cursor-pointer"
              >
                Continue with remaining {remainingCount}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="M12 5l7 7-7 7" /></svg>
              </button>
              <span className="font-mono text-[10px] text-text-dim">~{Math.ceil(remainingCount * 0.6)} min · results will be merged</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════
   Main ChatInterface
   ══════════════════════════════════════════════ */

export default function ChatInterface() {
  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [readiness, setReadiness] = useState<Readiness>(INITIAL_READINESS);
  const [isLoading, setIsLoading] = useState(false);
  const [extractedContext, setExtractedContext] = useState<ExtractedContext | null>(null);

  // Pipeline state
  const [phase, setPhase] = useState<Phase>("chat");
  const [searchCompanies, setSearchCompanies] = useState<SearchCompany[]>([]);
  const [allSearchCompanies, setAllSearchCompanies] = useState<SearchCompany[]>([]);
  const [qualifiedCompanies, setQualifiedCompanies] = useState<QualifiedCompany[]>([]);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);
  const [pipelineSummary, setPipelineSummary] = useState<PipelineSummary | null>(null);
  const [pipelineStartTime, setPipelineStartTime] = useState<number>(0);

  // Enrichment state (lifted so it persists across continue batches)
  const [enrichedContacts, setEnrichedContacts] = useState<Map<string, EnrichedContact>>(new Map());
  const [enrichDone, setEnrichDone] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, phase, qualifiedCompanies, scrollToBottom]);

  // Reset everything
  const resetChat = useCallback(() => {
    setMessages([]);
    setReadiness(INITIAL_READINESS);
    setExtractedContext(null);
    setPhase("chat");
    setSearchCompanies([]);
    setAllSearchCompanies([]);
    setQualifiedCompanies([]);
    setPipelineProgress(null);
    setPipelineSummary(null);
    setPipelineStartTime(0);
    setEnrichedContacts(new Map());
    setEnrichDone(false);
  }, []);

  // Send chat message
  const sendMessage = useCallback(
    async (content: string) => {
      const userMessage: Message = { id: crypto.randomUUID(), role: "user", content, timestamp: Date.now() };
      const updatedMessages = [...messages, userMessage];
      setMessages(updatedMessages);
      setIsLoading(true);

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: updatedMessages }),
        });

        if (!response.ok) throw new Error("Failed to get response");
        const data = await response.json();

        const assistantMessage: Message = { id: crypto.randomUUID(), role: "assistant", content: data.message, timestamp: Date.now() };
        setMessages((prev) => [...prev, assistantMessage]);

        if (data.readiness) setReadiness(data.readiness);
        if (data.extractedContext) setExtractedContext(data.extractedContext);
      } catch {
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), role: "assistant", content: "Something went wrong. Please try again.", timestamp: Date.now() },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  // Launch Exa search
  const launchSearch = useCallback(async () => {
    if (!extractedContext) return;
    setPhase("searching");

    try {
      const response = await fetch("/api/chat/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: extractedContext.industry || "",
          technology_focus: extractedContext.technologyFocus || "",
          qualifying_criteria: extractedContext.qualifyingCriteria || "",
          company_profile: extractedContext.companyProfile || undefined,
          disqualifiers: extractedContext.disqualifiers || undefined,
        }),
      });

      if (!response.ok) throw new Error("Search failed");
      const data = await response.json();

      setSearchCompanies(data.companies || []);
      setAllSearchCompanies(data.companies || []);
      setPhase("search-complete");
    } catch (err) {
      console.error("Search error:", err);
      setPhase("chat");
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Search failed. Please try again.", timestamp: Date.now() },
      ]);
    }
  }, [extractedContext]);

  // Launch pipeline (SSE stream directly to FastAPI)
  const launchPipeline = useCallback(async (batchCount: number, continueFromRemaining = false) => {
    // When continuing, use the remaining unprocessed companies from the full search results
    const source = continueFromRemaining
      ? allSearchCompanies.filter((c) => !qualifiedCompanies.some((qc) => qc.domain === c.domain))
      : searchCompanies;

    if (source.length === 0) return;

    // Sort by Exa score (descending) and take the requested batch
    const sorted = [...source].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    const batch = sorted.slice(0, batchCount);

    // Preserve previous results when continuing
    const previousResults = continueFromRemaining ? qualifiedCompanies : [];

    // Reorder searchCompanies so progress/queue reflects the actual processing order
    setSearchCompanies(batch);
    setPhase("qualifying");
    setQualifiedCompanies(previousResults);
    setPipelineProgress(null);
    setPipelineSummary(null);
    setPipelineStartTime(Date.now());

    try {
      const response = await fetch(`${BACKEND_URL}/api/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          companies: batch.map((c) => ({
            url: c.url,
            domain: c.domain,
            title: c.title,
            score: c.score,
          })),
          use_vision: true,
          search_context: extractedContext ? {
            industry: extractedContext.industry || undefined,
            company_profile: extractedContext.companyProfile || undefined,
            technology_focus: extractedContext.technologyFocus || undefined,
            qualifying_criteria: extractedContext.qualifyingCriteria || undefined,
            disqualifiers: extractedContext.disqualifiers || undefined,
          } : undefined,
        }),
      });

      if (!response.ok || !response.body) throw new Error("Pipeline connection failed");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          const match = part.match(/^data:\s*(.*)/);
          if (!match) continue;

          try {
            const event = JSON.parse(match[1]);

            if (event.type === "progress") {
              setPipelineProgress({
                index: event.index,
                total: event.total,
                phase: event.phase,
                company: event.company?.title || event.company?.domain || "",
              });
            } else if (event.type === "result") {
              setPipelineProgress(null);
              setQualifiedCompanies((prev) => [...prev, event.company]);
            } else if (event.type === "error" && event.fatal) {
              throw new Error(event.error);
            } else if (event.type === "complete") {
              setPipelineProgress(null);
              // Merge summary with any previous batch results
              setPipelineSummary((prev) => {
                if (!prev) return event.summary;
                return {
                  hot: prev.hot + (event.summary?.hot || 0),
                  review: prev.review + (event.summary?.review || 0),
                  rejected: prev.rejected + (event.summary?.rejected || 0),
                  failed: prev.failed + (event.summary?.failed || 0),
                };
              });
              setPhase("complete");
              completed = true;
            }
          } catch (parseErr) {
            // Re-throw intentional errors (fatal pipeline errors)
            if (parseErr instanceof Error && parseErr.message) throw parseErr;
            // Skip genuinely unparseable SSE events
          }
        }
      }

      // If we exited the loop without a "complete" event
      if (!completed) {
        setPhase("complete");
        setPipelineSummary((prev) => {
          if (prev) return prev;
          return { hot: 0, review: 0, rejected: 0, failed: 0 };
        });
      }
    } catch (err) {
      console.error("Pipeline error:", err);
      setPhase("search-complete");
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Pipeline encountered an error. You can try again.", timestamp: Date.now() },
      ]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCompanies, allSearchCompanies, qualifiedCompanies, extractedContext]);

  // Force-launch search with whatever context we have (skip follow-ups)
  const forceSearch = useCallback(async () => {
    // Build context from whatever we have — infer from messages if extractedContext is sparse
    const ctx = extractedContext || { industry: null, companyProfile: null, technologyFocus: null, qualifyingCriteria: null, disqualifiers: null };

    // If we have almost nothing extracted, try to derive from the last user message
    if (!ctx.industry && messages.length > 0) {
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      if (lastUserMsg) {
        ctx.industry = lastUserMsg.content;
      }
    }

    setExtractedContext(ctx);
    setReadiness({ industry: true, companyProfile: true, technologyFocus: true, qualifyingCriteria: true, isReady: true });
    setPhase("searching");

    try {
      const response = await fetch("/api/chat/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          industry: ctx.industry || "",
          technology_focus: ctx.technologyFocus || "",
          qualifying_criteria: ctx.qualifyingCriteria || "",
          company_profile: ctx.companyProfile || undefined,
          disqualifiers: ctx.disqualifiers || undefined,
        }),
      });

      if (!response.ok) throw new Error("Search failed");
      const data = await response.json();

      setSearchCompanies(data.companies || []);
      setAllSearchCompanies(data.companies || []);
      setPhase("search-complete");
    } catch (err) {
      console.error("Search error:", err);
      setPhase("chat");
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: "Search failed. Please try again.", timestamp: Date.now() },
      ]);
    }
  }, [extractedContext, messages]);

  // Determine if we should show the search action card
  const showSearchAction = readiness.isReady && phase === "chat" && !isLoading;
  // Show "skip & search" when we have at least 1 user message, AI has responded, but isReady is still false
  const showSkipSearch = !readiness.isReady && phase === "chat" && !isLoading && messages.length >= 2;
  const showChatInput = phase === "chat";

  return (
    <div className="flex flex-col h-dvh bg-void">
      {/* ─── Header ─── */}
      <header className="flex items-center justify-between px-4 md:px-6 h-14 border-b border-border-dim bg-surface-1/80 backdrop-blur-md flex-shrink-0 z-10">
        <Link href="/" className="flex items-center gap-2.5 group">
          <span className="text-secondary text-base font-bold">◈</span>
          <span className="text-text-primary text-xs font-semibold tracking-[0.12em] uppercase group-hover:text-secondary transition-colors duration-200">Hunt</span>
        </Link>
        {messages.length > 0 && phase === "chat" && <ReadinessTracker readiness={readiness} />}
        {phase !== "chat" && (
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-secondary/50">
            {phase === "searching" && "Searching..."}
            {phase === "search-complete" && `${searchCompanies.length} companies found`}
            {phase === "qualifying" && "Qualifying..."}
            {phase === "complete" && "Complete"}
          </span>
        )}
        {messages.length > 0 && (
          <button onClick={resetChat} className="font-mono text-[10px] text-text-muted hover:text-text-primary uppercase tracking-[0.15em] transition-colors duration-200 border border-border-dim hover:border-border rounded-lg px-3 py-1.5 cursor-pointer">
            + New Hunt
          </button>
        )}
        {messages.length === 0 && <div />}
      </header>

      {/* ─── Content ─── */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <WelcomeScreen onSuggestionClick={sendMessage} />
        ) : (
          <div className="max-w-3xl mx-auto py-6 px-4 space-y-5">
            {/* Chat messages */}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isLoading && <TypingIndicator />}

            {/* Skip & Search — lets users bypass follow-up questions */}
            {showSkipSearch && (
              <div className="animate-slide-up max-w-3xl mx-auto">
                <button
                  onClick={forceSearch}
                  className="inline-flex items-center gap-2 font-mono text-[10px] text-text-muted hover:text-secondary uppercase tracking-[0.15em] transition-colors duration-200 mt-2 cursor-pointer border border-border-dim hover:border-secondary/30 rounded-lg px-3 py-1.5"
                >
                  Skip questions &amp; search now →
                </button>
              </div>
            )}

            {/* Search action card */}
            {showSearchAction && <SearchActionCard onLaunch={launchSearch} />}

            {/* Searching indicator */}
            {phase === "searching" && <SearchingCard />}

            {/* Search results with batch size control */}
            {phase === "search-complete" && searchCompanies.length > 0 && (
              <SearchResultsCard companies={searchCompanies} onQualify={launchPipeline} />
            )}

            {/* Live interactive results — browse while processing */}
            {phase === "qualifying" && (
              <LiveResultsView
                progress={pipelineProgress}
                qualifiedCompanies={qualifiedCompanies}
                searchCompanies={searchCompanies}
                startTime={pipelineStartTime}
              />
            )}

            {/* Final results */}
            {phase === "complete" && pipelineSummary && (
              <ResultsSummaryCard
                qualifiedCompanies={qualifiedCompanies}
                summary={pipelineSummary}
                remainingCount={allSearchCompanies.filter((c) => !qualifiedCompanies.some((qc) => qc.domain === c.domain)).length}
                onContinue={(count) => launchPipeline(count, true)}
                enrichedContacts={enrichedContacts}
                setEnrichedContacts={setEnrichedContacts}
                enrichDone={enrichDone}
                setEnrichDone={setEnrichDone}
              />
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* ─── Input ─── */}
      {showChatInput && <ChatInput onSend={sendMessage} isLoading={isLoading} />}

      {/* Status bar for pipeline phases */}
      {!showChatInput && (
        <div className="border-t border-border-dim bg-surface-1/80 backdrop-blur-md px-4 py-3 flex-shrink-0">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <p className="font-mono text-[10px] text-text-dim">
              {phase === "searching" && "Generating queries and searching the web..."}
              {phase === "search-complete" && "Review the results above, then qualify them"}
              {phase === "qualifying" && `Qualifying ${searchCompanies.length} companies — browse results above while you wait`}
              {phase === "complete" && `Done — ${pipelineSummary?.hot || 0} hot leads found`}
            </p>
            {phase === "complete" && (
              <button onClick={resetChat} className="font-mono text-[10px] text-secondary hover:text-secondary/80 uppercase tracking-[0.15em] cursor-pointer">
                New Hunt →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
