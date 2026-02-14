"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "../../components/auth/SessionProvider";

interface LeadDetail {
  id: string;
  search_id: string;
  company_name: string;
  domain: string;
  website_url: string | null;
  score: number;
  tier: string;
  hardware_type: string | null;
  industry_category: string | null;
  reasoning: string | null;
  key_signals: string | null;
  red_flags: string | null;
  deep_research: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string | null;
  notes: string | null;
  deal_value: number | null;
  status_changed_at: string | null;
  created_at: string | null;
  last_seen_at: string | null;
  enrichment?: {
    email: string | null;
    phone: string | null;
    job_title: string | null;
    source: string | null;
  };
  contacts?: LeadContactPerson[];
}

interface LeadContactPerson {
  id: string;
  full_name: string | null;
  job_title: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  source: string | null;
}

type RecrawlAction = "recrawl_contacts" | "requalify" | "full_recrawl";

// All backend calls go through /api/proxy/* (Next.js server proxy)

const STATUS_OPTIONS = [
  { value: "new", label: "New", color: "text-text-muted" },
  { value: "contacted", label: "Contacted", color: "text-blue-400" },
  { value: "in_progress", label: "In Progress", color: "text-amber-400" },
  { value: "won", label: "Won", color: "text-green-400" },
  { value: "lost", label: "Lost", color: "text-red-400" },
  { value: "archived", label: "Archived", color: "text-text-dim" },
];

const TIER_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  hot: { bg: "bg-hot/10 border-hot/20", text: "text-hot", label: "HOT" },
  review: { bg: "bg-review/10 border-review/20", text: "text-review", label: "REVIEW" },
  rejected: { bg: "bg-text-dim/10 border-text-dim/20", text: "text-text-dim", label: "REJECTED" },
};

export default function LeadDrawer({
  leadId,
  onClose,
  onStatusChange,
  onLeadUpdate,
}: {
  leadId: string;
  onClose: () => void;
  onStatusChange?: (leadId: string, status: string) => void;
  onLeadUpdate?: (leadId: string, updates: { notes?: string | null; deal_value?: number | null }) => void;
}) {
  const { session } = useAuth();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [notes, setNotes] = useState<string>("");
  const [dealValue, setDealValue] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [linkedinLoading, setLinkedinLoading] = useState(false);
  const [contacts, setContacts] = useState<LeadContactPerson[]>([]);
  const [recrawlLoading, setRecrawlLoading] = useState<RecrawlAction | null>(null);
  const [recrawlResult, setRecrawlResult] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);
  // Enrichment job tracking for persistent state
  const [enrichJobId, setEnrichJobId] = useState<string | null>(null);
  const [enrichJobStatus, setEnrichJobStatus] = useState<string | null>(null);
  const [enrichJobProgress, setEnrichJobProgress] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token || !leadId) return;
    setLoading(true);
    fetch(`/api/proxy/leads/${leadId}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        setLead(data);
        if (data) {
          setNotes(data.notes || "");
          setDealValue(data.deal_value);
          setContacts(data.contacts || []);
        }
      })
      .finally(() => setLoading(false));
  }, [leadId, session]);

  const saveField = async (fields: { notes?: string; deal_value?: number | null }) => {
    if (!session?.access_token || !lead) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/proxy/leads/${lead.id}/status`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status: lead.status || "new", ...fields }),
      });
      if (res.ok) {
        const updated = await res.json();
        setLead({ ...lead, notes: updated.notes, deal_value: updated.deal_value, status_changed_at: updated.status_changed_at });
        onLeadUpdate?.(lead.id, fields);
        setSaved(true);
        setTimeout(() => setSaved(false), 1500);
      }
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (status: string) => {
    if (!session?.access_token || !lead) return;
    setStatusUpdating(true);
    try {
      const res = await fetch(`/api/proxy/leads/${lead.id}/status`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ status }),
      });
      if (res.ok) {
        setLead({ ...lead, status });
        onStatusChange?.(lead.id, status);
      }
    } finally {
      setStatusUpdating(false);
    }
  };

  const tier = TIER_CONFIG[lead?.tier || "rejected"] || TIER_CONFIG.rejected;

  const findDecisionMakers = async () => {
    if (!session?.access_token || !lead) return;
    setLinkedinLoading(true);
    setRecrawlResult(null);
    setEnrichJobProgress("Looking up on LinkedIn…");
    try {
      // Use batch job for tracking
      const jobRes = await fetch("/api/proxy/leads/batch-enrich", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ lead_ids: [lead.id], action: "linkedin" }),
      });

      if (!jobRes.ok) {
        const err = await jobRes.json().catch(() => null);
        setRecrawlResult({ type: "error", message: err?.detail || "LinkedIn lookup failed" });
        setLinkedinLoading(false);
        setEnrichJobProgress(null);
        return;
      }

      const { job_id } = await jobRes.json();
      setEnrichJobId(job_id);
      setEnrichJobStatus("running");

      // Poll for completion
      let attempts = 0;
      while (attempts < 30) {
        await new Promise((r) => setTimeout(r, 2000));
        attempts++;
        const pollRes = await fetch(`/api/proxy/leads/enrich-jobs/${job_id}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (pollRes.ok) {
          const pollData = await pollRes.json();
          if (pollData.status === "complete" || pollData.status === "error") {
            setEnrichJobStatus(pollData.status);
            // Refresh contacts
            const refreshRes = await fetch(`/api/proxy/leads/${lead.id}`, {
              headers: { Authorization: `Bearer ${session.access_token}` },
            });
            if (refreshRes.ok) {
              const refreshed = await refreshRes.json();
              setContacts(refreshed.contacts || []);
            }
            if (pollData.status === "complete" && pollData.results?.[0]) {
              const r = pollData.results[0];
              setRecrawlResult({
                type: "success",
                message: r.new_contacts
                  ? `Found ${r.new_contacts} new contact${r.new_contacts > 1 ? "s" : ""} via LinkedIn`
                  : "No new contacts found via LinkedIn",
              });
            } else {
              setRecrawlResult({ type: "error", message: pollData.error || "LinkedIn lookup failed" });
            }
            break;
          }
        }
      }
    } catch {
      setRecrawlResult({ type: "error", message: "Network error" });
    } finally {
      setLinkedinLoading(false);
      setEnrichJobProgress(null);
    }
  };

  const recrawlLead = useCallback(async (action: RecrawlAction) => {
    if (!session?.access_token || !lead) return;
    setRecrawlLoading(action);
    setRecrawlResult(null);
    setEnrichJobProgress("Starting…");
    try {
      // Create a tracked batch job (single lead)
      const jobRes = await fetch("/api/proxy/leads/batch-enrich", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ lead_ids: [lead.id], action }),
      });

      if (!jobRes.ok) {
        const err = await jobRes.json().catch(() => null);
        setRecrawlResult({ type: "error", message: err?.detail || "Failed to start enrichment" });
        setRecrawlLoading(null);
        setEnrichJobProgress(null);
        return;
      }

      const { job_id } = await jobRes.json();
      setEnrichJobId(job_id);
      setEnrichJobStatus("running");

      // Stream SSE for progress
      try {
        const sseRes = await fetch(`/api/proxy/leads/enrich-jobs/${job_id}/stream`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (sseRes.ok && sseRes.body) {
          const reader = sseRes.body.getReader();
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
                if (event.type === "progress") {
                  setEnrichJobProgress(`Processing ${event.company || ""}…`);
                }
                if (event.type === "result") {
                  // Refresh lead data
                  const refreshRes = await fetch(`/api/proxy/leads/${lead.id}`, {
                    headers: { Authorization: `Bearer ${session.access_token}` },
                  });
                  if (refreshRes.ok) {
                    const refreshed = await refreshRes.json();
                    setLead(refreshed);
                    setContacts(refreshed.contacts || []);
                  }
                  if (event.status === "success") {
                    const msgs: string[] = [];
                    if (event.new_score !== undefined) msgs.push(`Re-scored: ${event.new_score}/100 (${event.new_tier})`);
                    if (event.new_contacts !== undefined) {
                      msgs.push(event.new_contacts > 0 ? `Found ${event.new_contacts} new contact${event.new_contacts > 1 ? "s" : ""}` : "No new contacts found");
                    }
                    setRecrawlResult({ type: "success", message: msgs.join(" · ") || "Done" });
                  } else {
                    setRecrawlResult({ type: "error", message: event.message || "Failed" });
                  }
                }
                if (event.type === "complete") {
                  setEnrichJobStatus("complete");
                  setEnrichJobProgress(null);
                }
              } catch { /* ignore */ }
            }
          }
        }
      } catch {
        // SSE failed — poll for status instead
        let attempts = 0;
        while (attempts < 30) {
          await new Promise((r) => setTimeout(r, 2000));
          attempts++;
          const pollRes = await fetch(`/api/proxy/leads/enrich-jobs/${job_id}`, {
            headers: { Authorization: `Bearer ${session.access_token}` },
          });
          if (pollRes.ok) {
            const pollData = await pollRes.json();
            setEnrichJobProgress(`Processing… (${pollData.processed}/${pollData.total})`);
            if (pollData.status === "complete" || pollData.status === "error") {
              setEnrichJobStatus(pollData.status);
              setEnrichJobProgress(null);
              if (pollData.status === "complete") {
                // Refresh lead data
                const refreshRes = await fetch(`/api/proxy/leads/${lead.id}`, {
                  headers: { Authorization: `Bearer ${session.access_token}` },
                });
                if (refreshRes.ok) {
                  const refreshed = await refreshRes.json();
                  setLead(refreshed);
                  setContacts(refreshed.contacts || []);
                }
                setRecrawlResult({ type: "success", message: `Completed (${pollData.succeeded} succeeded, ${pollData.failed} failed)` });
              } else {
                setRecrawlResult({ type: "error", message: pollData.error || "Job failed" });
              }
              break;
            }
          }
        }
      }
    } catch {
      setRecrawlResult({ type: "error", message: "Network error — try again" });
    } finally {
      setRecrawlLoading(null);
      setEnrichJobProgress(null);
    }
  }, [session, lead]);

  // Try to parse JSON fields safely
  const parseJsonField = (val: unknown): string[] => {
    if (!val) return [];
    if (Array.isArray(val)) return val.map(String);
    if (typeof val !== "string") return [String(val)];
    try {
      const parsed = JSON.parse(val);
      return Array.isArray(parsed) ? parsed : [String(parsed)];
    } catch {
      return val
        .split(/[,;\n]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed top-0 right-0 h-full w-full max-w-lg bg-surface-1 border-l border-border z-50 overflow-y-auto animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 bg-surface-1/95 backdrop-blur-md border-b border-border-dim px-6 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <span
              className={`inline-flex items-center px-2.5 py-1 rounded-md text-[10px] font-mono uppercase tracking-[0.12em] border ${tier.bg} ${tier.text}`}
            >
              {tier.label}
            </span>
            {lead && (
              <span className="font-mono text-lg font-bold text-text-primary">
                {lead.score}
              </span>
            )}
            {/* Contacts found badge */}
            {contacts.length > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono bg-green-400/10 border border-green-400/20 text-green-400">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                {contacts.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors p-1 cursor-pointer"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
          </div>
        ) : !lead ? (
          <div className="py-20 text-center font-mono text-xs text-text-dim">
            Lead not found
          </div>
        ) : (
          <div className="px-6 py-6 space-y-6">
            {/* Company info */}
            <div className="flex items-start gap-3">
              {lead.domain && (
                <img
                  src={`https://www.google.com/s2/favicons?domain=${lead.domain}&sz=64`}
                  alt=""
                  width={24}
                  height={24}
                  className="rounded flex-shrink-0 mt-0.5"
                  loading="lazy"
                />
              )}
              <div>
                <h2 className="font-mono text-base font-bold text-text-primary mb-1">
                  {lead.company_name}
                </h2>
                <p className="font-mono text-xs text-text-muted">{lead.domain}</p>
                {lead.country && (
                  <p className="font-mono text-[10px] text-text-dim mt-1">
                    {lead.country}
                  </p>
                )}
              </div>
            </div>

            {/* Score gauge */}
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
                  Score
                </span>
                <span className="font-mono text-xl font-bold text-text-primary">
                  {lead.score}/100
                </span>
              </div>
              <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    lead.score >= 80
                      ? "bg-hot"
                      : lead.score >= 50
                        ? "bg-review"
                        : "bg-text-dim"
                  }`}
                  style={{ width: `${lead.score}%` }}
                />
              </div>
            </div>

            {/* Status selector */}
            <div>
              <label className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-2 block">
                Pipeline Status
              </label>
              <div className="flex flex-wrap gap-1.5">
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => updateStatus(opt.value)}
                    disabled={statusUpdating}
                    className={`font-mono text-[10px] px-3 py-1.5 rounded-md border uppercase tracking-[0.1em] transition-all cursor-pointer ${
                      lead.status === opt.value
                        ? "bg-secondary/10 border-secondary/30 text-secondary"
                        : "border-border text-text-muted hover:border-border-bright hover:text-text-primary"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              {saving && (
                <span className="font-mono text-[9px] text-text-dim mt-1 block">Saving…</span>
              )}
              {saved && (
                <span className="font-mono text-[9px] text-green-400 mt-1 block">Saved ✓</span>
              )}
            </div>

            {/* Notes */}
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-2">
                Notes
              </h3>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => saveField({ notes })}
                placeholder="Add notes about this lead..."
                className="w-full bg-surface-3 border border-border rounded-lg p-3 font-sans text-xs text-text-primary placeholder:text-text-dim resize-none focus:outline-none focus:border-secondary/40 min-h-[80px]"
              />
            </div>

            {/* Deal Value */}
            <div className="bg-surface-2 border border-border rounded-xl p-4">
              <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-2">
                Deal Value
              </h3>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-text-dim">$</span>
                <input
                  type="number"
                  value={dealValue ?? ""}
                  onChange={(e) => setDealValue(e.target.value ? parseFloat(e.target.value) : null)}
                  onBlur={() => saveField({ deal_value: dealValue })}
                  placeholder="0.00"
                  className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40"
                />
              </div>
            </div>

            {/* Industry & type */}
            {(lead.industry_category || lead.hardware_type) && (
              <div className="grid grid-cols-2 gap-3">
                {lead.industry_category && (
                  <div className="bg-surface-2 border border-border rounded-lg p-3">
                    <p className="font-mono text-[9px] text-text-dim uppercase tracking-[0.15em] mb-1">
                      Industry
                    </p>
                    <p className="font-mono text-xs text-text-primary">
                      {lead.industry_category}
                    </p>
                  </div>
                )}
                {lead.hardware_type && (
                  <div className="bg-surface-2 border border-border rounded-lg p-3">
                    <p className="font-mono text-[9px] text-text-dim uppercase tracking-[0.15em] mb-1">
                      Product Type
                    </p>
                    <p className="font-mono text-xs text-text-primary">
                      {lead.hardware_type}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Reasoning */}
            {lead.reasoning && (
              <Section title="AI Reasoning">
                <p className="font-sans text-xs text-text-secondary leading-relaxed">
                  {lead.reasoning}
                </p>
              </Section>
            )}

            {/* Key signals */}
            {lead.key_signals && (
              <Section title="Key Signals">
                <ul className="space-y-1.5">
                  {parseJsonField(lead.key_signals).map((s, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 font-sans text-xs text-text-secondary"
                    >
                      <span className="text-green-400 mt-0.5 shrink-0">✓</span>
                      {s}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Red flags */}
            {lead.red_flags && (
              <Section title="Red Flags">
                <ul className="space-y-1.5">
                  {parseJsonField(lead.red_flags).map((f, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 font-sans text-xs text-text-secondary"
                    >
                      <span className="text-red-400 mt-0.5 shrink-0">•</span>
                      {f}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {/* Deep research */}
            {lead.deep_research && (
              <Section title="Deep Research">
                <p className="font-sans text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">
                  {lead.deep_research}
                </p>
              </Section>
            )}

            {/* Enrichment */}
            {lead.enrichment && (
              <Section title="Contact Info (Hunter)">
                <div className="space-y-2">
                  {lead.enrichment.email && (
                    <InfoRow label="Email" value={lead.enrichment.email} />
                  )}
                  {lead.enrichment.phone && (
                    <InfoRow label="Phone" value={lead.enrichment.phone} />
                  )}
                  {lead.enrichment.job_title && (
                    <InfoRow label="Title" value={lead.enrichment.job_title} />
                  )}
                  {lead.enrichment.source && (
                    <InfoRow label="Source" value={lead.enrichment.source} />
                  )}
                </div>
              </Section>
            )}

            {/* People at this Company */}
            <Section title={`People at this Company${contacts.length ? ` (${contacts.length})` : ""}`}>
              {contacts.length > 0 ? (
                <div className="space-y-3">
                  {contacts.map((c, i) => (
                    <div key={c.id || i} className="bg-surface-3 border border-border-dim rounded-lg p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-semibold text-text-primary">
                          {c.full_name || "Unknown"}
                        </span>
                        <span className="font-mono text-[9px] text-text-dim uppercase tracking-wider">
                          {c.source}
                        </span>
                      </div>
                      {c.job_title && (
                        <p className="font-mono text-[10px] text-text-muted">{c.job_title}</p>
                      )}
                      <div className="flex flex-wrap gap-2 mt-1">
                        {c.email && (
                          <a
                            href={`mailto:${c.email}`}
                            className="font-mono text-[10px] text-secondary hover:text-secondary/80 transition-colors"
                          >
                            {c.email}
                          </a>
                        )}
                        {c.phone && (
                          <a
                            href={`tel:${c.phone}`}
                            className="font-mono text-[10px] text-text-muted hover:text-text-primary transition-colors"
                          >
                            {c.phone}
                          </a>
                        )}
                        {c.linkedin_url && (
                          <a
                            href={c.linkedin_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
                          >
                            LinkedIn ↗
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="font-mono text-[10px] text-text-dim">
                  No contacts extracted yet.
                </p>
              )}
            </Section>

            {/* ── Enrichment Actions ── */}
            <Section title="Enrichment Actions">
              {/* Active enrichment progress */}
              {enrichJobProgress && (
                <div className="mb-3 px-3 py-2.5 rounded-lg font-mono text-[10px] border border-secondary/20 bg-secondary/5 text-secondary flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin flex-shrink-0" />
                  {enrichJobProgress}
                </div>
              )}

              {recrawlResult && (
                <div className={`mb-3 px-3 py-2 rounded-lg font-mono text-[10px] border ${
                  recrawlResult.type === "success"
                    ? "bg-green-400/5 border-green-400/20 text-green-400"
                    : "bg-red-400/5 border-red-400/20 text-red-400"
                }`}>
                  {recrawlResult.message}
                </div>
              )}

              <div className="space-y-2">
                {/* Re-crawl for contacts */}
                <button
                  onClick={() => recrawlLead("recrawl_contacts")}
                  disabled={recrawlLoading !== null || linkedinLoading}
                  className="w-full flex items-center gap-3 bg-surface-3 border border-border-dim hover:border-secondary/30 rounded-lg px-3.5 py-3 transition-all group cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span className="w-7 h-7 rounded-md bg-secondary/10 border border-secondary/20 flex items-center justify-center flex-shrink-0">
                    {recrawlLoading === "recrawl_contacts" ? (
                      <span className="w-3.5 h-3.5 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-secondary">
                        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                        <path d="M3 3v5h5" />
                        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                        <path d="M16 16h5v5" />
                      </svg>
                    )}
                  </span>
                  <div className="text-left flex-1">
                    <p className="font-mono text-[11px] text-text-primary group-hover:text-secondary transition-colors">
                      Re-crawl Website for Contacts
                    </p>
                    <p className="font-sans text-[10px] text-text-dim mt-0.5">
                      Crawl homepage, /contact, /about &amp; /team pages again
                    </p>
                  </div>
                </button>

                {/* Find Decision Makers via LinkedIn */}
                <button
                  onClick={findDecisionMakers}
                  disabled={recrawlLoading !== null || linkedinLoading}
                  className="w-full flex items-center gap-3 bg-surface-3 border border-border-dim hover:border-blue-400/30 rounded-lg px-3.5 py-3 transition-all group cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span className="w-7 h-7 rounded-md bg-blue-400/10 border border-blue-400/20 flex items-center justify-center flex-shrink-0">
                    {linkedinLoading ? (
                      <span className="w-3.5 h-3.5 border-2 border-blue-400/40 border-t-blue-400 rounded-full animate-spin" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" className="text-blue-400">
                        <path d="M19 3a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h14m-.5 15.5v-5.3a3.26 3.26 0 00-3.26-3.26c-.85 0-1.84.52-2.32 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 011.4 1.4v4.93h2.79M6.88 8.56a1.68 1.68 0 001.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 00-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
                      </svg>
                    )}
                  </span>
                  <div className="text-left flex-1">
                    <p className="font-mono text-[11px] text-text-primary group-hover:text-blue-400 transition-colors">
                      Find Decision Makers (LinkedIn)
                    </p>
                    <p className="font-sans text-[10px] text-text-dim mt-0.5">
                      Search LinkedIn for C-suite, VPs &amp; key contacts
                    </p>
                  </div>
                </button>

                {/* Re-qualify */}
                <button
                  onClick={() => recrawlLead("requalify")}
                  disabled={recrawlLoading !== null || linkedinLoading}
                  className="w-full flex items-center gap-3 bg-surface-3 border border-border-dim hover:border-amber-400/30 rounded-lg px-3.5 py-3 transition-all group cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span className="w-7 h-7 rounded-md bg-amber-400/10 border border-amber-400/20 flex items-center justify-center flex-shrink-0">
                    {recrawlLoading === "requalify" ? (
                      <span className="w-3.5 h-3.5 border-2 border-amber-400/40 border-t-amber-400 rounded-full animate-spin" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-400">
                        <path d="M12 20h9" />
                        <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
                      </svg>
                    )}
                  </span>
                  <div className="text-left flex-1">
                    <p className="font-mono text-[11px] text-text-primary group-hover:text-amber-400 transition-colors">
                      Re-qualify Lead
                    </p>
                    <p className="font-sans text-[10px] text-text-dim mt-0.5">
                      Re-crawl &amp; re-score with AI against your ICP criteria
                    </p>
                  </div>
                </button>

                {/* Full re-crawl (both) */}
                <button
                  onClick={() => recrawlLead("full_recrawl")}
                  disabled={recrawlLoading !== null || linkedinLoading}
                  className="w-full flex items-center gap-3 bg-surface-3 border border-border-dim hover:border-purple-400/30 rounded-lg px-3.5 py-3 transition-all group cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <span className="w-7 h-7 rounded-md bg-purple-400/10 border border-purple-400/20 flex items-center justify-center flex-shrink-0">
                    {recrawlLoading === "full_recrawl" ? (
                      <span className="w-3.5 h-3.5 border-2 border-purple-400/40 border-t-purple-400 rounded-full animate-spin" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-purple-400">
                        <circle cx="12" cy="12" r="3" />
                        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
                      </svg>
                    )}
                  </span>
                  <div className="text-left flex-1">
                    <p className="font-mono text-[11px] text-text-primary group-hover:text-purple-400 transition-colors">
                      Full Re-crawl (Score + Contacts)
                    </p>
                    <p className="font-sans text-[10px] text-text-dim mt-0.5">
                      Complete re-crawl: re-qualify and extract contacts
                    </p>
                  </div>
                </button>
              </div>
            </Section>

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              {lead.website_url && (
                <a
                  href={lead.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 inline-flex items-center justify-center gap-2 bg-text-primary text-void font-mono text-[10px] font-bold uppercase tracking-[0.15em] px-4 py-3 rounded-lg hover:bg-white/85 transition-colors"
                >
                  Visit Website ↗
                </a>
              )}
              <button
                onClick={onClose}
                className="flex-1 inline-flex items-center justify-center gap-2 bg-surface-3 border border-border text-text-muted font-mono text-[10px] uppercase tracking-[0.15em] px-4 py-3 rounded-lg hover:text-text-primary hover:border-border-bright transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes slide-in-right {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.25s ease-out;
        }
      `}</style>
    </>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface-2 border border-border rounded-xl p-4">
      <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-3">
        {title}
      </h3>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[10px] text-text-dim uppercase tracking-[0.15em]">
        {label}
      </span>
      <span className="font-mono text-xs text-text-primary">{value}</span>
    </div>
  );
}
