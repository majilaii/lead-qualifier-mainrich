"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../components/auth/SessionProvider";

interface DashboardStats {
  total_leads: number;
  hot_leads: number;
  review_leads: number;
  rejected_leads: number;
  total_searches: number;
  contacts_enriched: number;
  leads_this_month: number;
}

interface FunnelData {
  stages: Record<string, number>;
  total_pipeline_value: number;
  won_value: number;
  lost_value: number;
  conversion_rate: number;
  avg_days_to_close: number;
  total_leads: number;
}

interface SearchSummary {
  id: string;
  industry: string | null;
  technology_focus: string | null;
  hot: number;
  review: number;
  rejected: number;
  created_at: string | null;
}

export default function DashboardPage() {
  const { session } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentSearches, setRecentSearches] = useState<SearchSummary[]>([]);
  const [funnel, setFunnel] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;
    const headers = { Authorization: `Bearer ${session.access_token}` };

    Promise.all([
      fetch("/api/proxy/dashboard/stats", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch("/api/proxy/searches", { headers }).then((r) =>
        r.ok ? r.json() : []
      ),
      fetch("/api/proxy/dashboard/funnel", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
    ])
      .then(([statsData, searchesData, funnelData]) => {
        setStats(statsData);
        setRecentSearches((searchesData || []).slice(0, 5));
        setFunnel(funnelData);
      })
      .finally(() => setLoading(false));
  }, [session]);

  const handleDeleteSearch = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!session?.access_token) return;
    setDeleting(id);
    try {
      const res = await fetch(`/api/proxy/searches/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        setRecentSearches((prev) => prev.filter((s) => s.id !== id));
        // Refresh stats
        const statsRes = await fetch("/api/proxy/dashboard/stats", {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (statsRes.ok) setStats(await statsRes.json());
      }
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
      </div>
    );
  }

  const statCards = [
    { label: "Total Leads", value: stats?.total_leads ?? 0 },
    { label: "Hot Leads", value: stats?.hot_leads ?? 0 },
    { label: "This Month", value: stats?.leads_this_month ?? 0 },
    { label: "Searches Run", value: stats?.total_searches ?? 0 },
    {
      label: "Contacts Enriched",
      value: stats?.contacts_enriched ?? 0,
    },
  ];

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
            Dashboard
          </h1>
          <p className="font-sans text-sm text-text-muted mt-1">
            Overview of your lead discovery pipeline
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/dashboard/bulk"
            className="inline-flex items-center gap-2 border border-border text-text-muted hover:text-secondary hover:border-secondary/30 font-mono text-xs uppercase tracking-[0.15em] px-4 py-3 rounded-lg transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
            Bulk Import
          </Link>
          <Link
            href="/chat"
            className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-white/85 transition-colors"
          >
            + New Hunt
          </Link>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="bg-surface-2 border border-border rounded-xl p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono text-2xl font-bold text-text-primary">
                {card.value}
              </span>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted">
              {card.label}
            </p>
          </div>
        ))}
      </div>

      {/* Conversion Funnel */}
      {funnel && funnel.total_leads > 0 && (
        <div className="space-y-4">
          <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
            Conversion Funnel
          </h2>

          {/* Funnel Bar */}
          <div className="bg-surface-2 border border-border rounded-xl p-5">
            <div className="flex h-8 rounded-lg overflow-hidden bg-surface-3">
              {(() => {
                const funnelStages = [
                  { key: "new", label: "New", bg: "bg-text-muted" },
                  { key: "contacted", label: "Contacted", bg: "bg-blue-400" },
                  { key: "in_progress", label: "In Progress", bg: "bg-amber-400" },
                  { key: "won", label: "Won", bg: "bg-green-400" },
                ];
                const active = funnel.total_leads - (funnel.stages.lost || 0) - (funnel.stages.archived || 0);
                if (active === 0) return null;
                return funnelStages
                  .filter((s) => (funnel.stages[s.key] || 0) > 0)
                  .map((s) => {
                    const count = funnel.stages[s.key] || 0;
                    const pct = (count / active) * 100;
                    return (
                      <div
                        key={s.key}
                        className={`${s.bg} flex items-center justify-center min-w-[40px] transition-all`}
                        style={{ width: `${pct}%` }}
                        title={`${s.label}: ${count}`}
                      >
                        {pct > 12 && (
                          <span className="font-mono text-[9px] text-void font-bold truncate px-1">
                            {s.label} ({count})
                          </span>
                        )}
                      </div>
                    );
                  });
              })()}
            </div>

            {/* Legend row */}
            <div className="flex flex-wrap gap-4 mt-3">
              {[
                { key: "new", label: "New", dot: "bg-text-muted" },
                { key: "contacted", label: "Contacted", dot: "bg-blue-400" },
                { key: "in_progress", label: "In Progress", dot: "bg-amber-400" },
                { key: "won", label: "Won", dot: "bg-green-400" },
                { key: "lost", label: "Lost", dot: "bg-red-400" },
                { key: "archived", label: "Archived", dot: "bg-text-dim" },
              ].map((s) => (
                <div key={s.key} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${s.dot}`} />
                  <span className="font-mono text-[9px] text-text-muted">
                    {s.label}: {funnel.stages[s.key] || 0}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Funnel Stats Row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-surface-2 border border-border rounded-xl p-5">
              <span className="font-mono text-2xl font-bold text-text-primary">
                ${funnel.total_pipeline_value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-3">
                Pipeline Value
              </p>
            </div>
            <div className="bg-surface-2 border border-border rounded-xl p-5">
              <span className="font-mono text-2xl font-bold text-green-400">
                ${funnel.won_value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-3">
                Won Revenue
              </p>
            </div>
            <div className="bg-surface-2 border border-border rounded-xl p-5">
              <span className="font-mono text-2xl font-bold text-text-primary">
                {funnel.conversion_rate}%
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-3">
                Conversion Rate
              </p>
            </div>
            <div className="bg-surface-2 border border-border rounded-xl p-5">
              <span className="font-mono text-2xl font-bold text-text-primary">
                {funnel.avg_days_to_close}
              </span>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-text-muted mt-3">
                Avg Days to Close
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Recent Hunts */}
      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border-dim flex items-center justify-between">
          <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
            Recent Pipeline Runs
          </h2>
          <Link
            href="/dashboard/pipeline"
            className="font-mono text-[10px] text-secondary/60 hover:text-secondary uppercase tracking-[0.15em] transition-colors"
          >
            View All →
          </Link>
        </div>

        {recentSearches.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <p className="font-mono text-xs text-text-dim mb-4">
              No hunts yet. Start your first search!
            </p>
            <Link
              href="/chat"
              className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors"
            >
              Start Hunting
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-border-dim">
            {recentSearches.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between px-5 py-4 hover:bg-surface-3/50 transition-colors group"
              >
                <Link
                  href={`/dashboard/leads?search_id=${s.id}`}
                  className="flex-1 min-w-0"
                >
                  <p className="font-mono text-xs text-text-primary truncate">
                    {s.industry || "Untitled Search"}
                  </p>
                  {s.technology_focus && (
                    <p className="font-mono text-[10px] text-text-dim truncate mt-0.5">
                      {s.technology_focus}
                    </p>
                  )}
                </Link>
                <div className="flex items-center gap-3 ml-4">
                  <span className="font-mono text-[10px] text-hot">
                    {s.hot} hot
                  </span>
                  <span className="font-mono text-[10px] text-review">
                    {s.review} review
                  </span>
                  <span className="font-mono text-[10px] text-text-dim">
                    {s.rejected} rejected
                  </span>
                  {s.created_at && (
                    <span className="font-mono text-[9px] text-text-dim">
                      {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  )}
                  <button
                    onClick={(e) => handleDeleteSearch(s.id, e)}
                    disabled={deleting === s.id}
                    className="opacity-0 group-hover:opacity-100 text-text-dim hover:text-red-400 transition-all cursor-pointer ml-1 disabled:opacity-50"
                    title="Delete hunt"
                  >
                    {deleting === s.id ? (
                      <span className="w-3.5 h-3.5 border border-text-dim border-t-transparent rounded-full animate-spin inline-block" />
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
