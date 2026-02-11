"use client";

import { useEffect, useState } from "react";
import { useAuth } from "./auth/SessionProvider";

interface UsageData {
  year_month: string;
  leads_qualified: number;
  leads_limit: number | null;
  searches_run: number;
  searches_limit: number | null;
}

export default function UsageMeter() {
  const { session } = useAuth();
  const [usage, setUsage] = useState<UsageData | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;

    fetch("/api/usage", {
      headers: {
        Authorization: `Bearer ${session.access_token}`,
      },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then(setUsage)
      .catch(() => setUsage(null));
  }, [session]);

  if (!usage) return null;

  const leadsPercent =
    usage.leads_limit != null
      ? Math.min(100, Math.round((usage.leads_qualified / usage.leads_limit) * 100))
      : 0;
  const searchesPercent =
    usage.searches_limit != null
      ? Math.min(100, Math.round((usage.searches_run / usage.searches_limit) * 100))
      : 0;

  return (
    <div className="flex flex-col gap-2 px-4 py-3 border border-border-dim rounded-lg bg-surface/30">
      <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-text-dim">
        Monthly Usage
      </span>

      {/* Leads meter */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-text-muted w-16">Leads</span>
        <div className="flex-1 h-1.5 bg-border-dim rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              leadsPercent >= 90 ? "bg-red-400" : leadsPercent >= 70 ? "bg-amber-400" : "bg-secondary"
            }`}
            style={{ width: `${leadsPercent}%` }}
          />
        </div>
        <span className="font-mono text-[10px] text-text-muted w-20 text-right">
          {usage.leads_qualified}
          {usage.leads_limit != null ? ` / ${usage.leads_limit}` : ""}
        </span>
      </div>

      {/* Searches meter */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-text-muted w-16">Searches</span>
        <div className="flex-1 h-1.5 bg-border-dim rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              searchesPercent >= 90 ? "bg-red-400" : searchesPercent >= 70 ? "bg-amber-400" : "bg-secondary"
            }`}
            style={{ width: `${searchesPercent}%` }}
          />
        </div>
        <span className="font-mono text-[10px] text-text-muted w-20 text-right">
          {usage.searches_run}
          {usage.searches_limit != null ? ` / ${usage.searches_limit}` : ""}
        </span>
      </div>
    </div>
  );
}
