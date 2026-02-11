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

interface SearchSummary {
  id: string;
  industry: string | null;
  technology_focus: string | null;
  hot: number;
  review: number;
  rejected: number;
  created_at: string | null;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const { session } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentSearches, setRecentSearches] = useState<SearchSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session?.access_token) return;
    const headers = { Authorization: `Bearer ${session.access_token}` };

    Promise.all([
      fetch(`${API}/api/dashboard/stats`, { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch(`${API}/api/searches`, { headers }).then((r) =>
        r.ok ? r.json() : []
      ),
    ])
      .then(([statsData, searchesData]) => {
        setStats(statsData);
        setRecentSearches((searchesData || []).slice(0, 5));
      })
      .finally(() => setLoading(false));
  }, [session]);

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
        <Link
          href="/chat"
          className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-white/85 transition-colors"
        >
          + New Hunt
        </Link>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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

      {/* Recent Hunts */}
      <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border-dim flex items-center justify-between">
          <h2 className="font-mono text-sm font-semibold text-text-primary uppercase tracking-[0.1em]">
            Recent Hunts
          </h2>
          <Link
            href="/dashboard/hunts"
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
              <Link
                key={s.id}
                href={`/dashboard/hunts`}
                className="flex items-center justify-between px-5 py-4 hover:bg-surface-3/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-text-primary truncate">
                    {s.industry || "Untitled Search"}
                  </p>
                  {s.technology_focus && (
                    <p className="font-mono text-[10px] text-text-dim truncate mt-0.5">
                      {s.technology_focus}
                    </p>
                  )}
                </div>
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
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
