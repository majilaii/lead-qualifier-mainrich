"use client";

import { useEffect, useState } from "react";
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
  created_at: string | null;
  enrichment?: {
    email: string | null;
    phone: string | null;
    job_title: string | null;
    source: string | null;
  };
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}: {
  leadId: string;
  onClose: () => void;
  onStatusChange?: (leadId: string, status: string) => void;
}) {
  const { session } = useAuth();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusUpdating, setStatusUpdating] = useState(false);

  useEffect(() => {
    if (!session?.access_token || !leadId) return;
    setLoading(true);
    fetch(`${API}/api/leads/${leadId}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then(setLead)
      .finally(() => setLoading(false));
  }, [leadId, session]);

  const updateStatus = async (status: string) => {
    if (!session?.access_token || !lead) return;
    setStatusUpdating(true);
    try {
      const res = await fetch(`${API}/api/leads/${lead.id}/status`, {
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

  // Try to parse JSON fields safely
  const parseJsonField = (val: string | null): string[] => {
    if (!val) return [];
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
                    lead.score >= 70
                      ? "bg-hot"
                      : lead.score >= 40
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
              <Section title="Contact Info">
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
