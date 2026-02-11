"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../../components/auth/SessionProvider";
import LeadDrawer from "./LeadDrawer";

interface Lead {
  id: string;
  search_id: string;
  company_name: string;
  domain: string;
  website_url: string | null;
  score: number;
  tier: string;
  industry_category: string | null;
  country: string | null;
  status: string | null;
  created_at: string | null;
}

type TierFilter = "all" | "hot" | "review" | "rejected";
type SortField = "score" | "company_name" | "created_at";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TIER_BADGE: Record<string, { bg: string; label: string }> = {
  hot: { bg: "bg-hot/10 text-hot border-hot/20", label: "Hot" },
  review: {
    bg: "bg-review/10 text-review border-review/20",
    label: "Review",
  },
  rejected: {
    bg: "bg-text-dim/10 text-text-dim border-text-dim/20",
    label: "Rejected",
  },
};

const STATUS_DOT: Record<string, string> = {
  new: "bg-text-muted",
  contacted: "bg-blue-400",
  in_progress: "bg-amber-400",
  won: "bg-green-400",
  lost: "bg-red-400",
  archived: "bg-text-dim",
};

export default function PipelinePage() {
  const { session } = useAuth();
  const searchParams = useSearchParams();
  const searchIdFilter = searchParams.get("search_id");

  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);

  const fetchLeads = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const params = new URLSearchParams({
        sort: sortField,
        order: sortOrder,
      });
      if (tierFilter !== "all") params.set("tier", tierFilter);
      if (searchIdFilter) params.set("search_id", searchIdFilter);

      const res = await fetch(`${API}/api/leads?${params}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setLeads(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session, sortField, sortOrder, tierFilter, searchIdFilter]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((o) => (o === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const handleStatusChange = (leadId: string, newStatus: string) => {
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, status: newStatus } : l))
    );
  };

  // Client-side text filter
  const filtered = leads.filter((l) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      l.company_name.toLowerCase().includes(q) ||
      l.domain.toLowerCase().includes(q) ||
      (l.country || "").toLowerCase().includes(q) ||
      (l.industry_category || "").toLowerCase().includes(q)
    );
  });

  const tierCounts = {
    all: leads.length,
    hot: leads.filter((l) => l.tier === "hot").length,
    review: leads.filter((l) => l.tier === "review").length,
    rejected: leads.filter((l) => l.tier === "rejected").length,
  };

  const SortArrow = ({ field }: { field: SortField }) =>
    sortField === field ? (
      <span className="ml-1 text-secondary">
        {sortOrder === "desc" ? "↓" : "↑"}
      </span>
    ) : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
          Pipeline
        </h1>
        <p className="font-sans text-sm text-text-muted mt-1">
          {leads.length} lead{leads.length !== 1 && "s"} across all hunts
          {searchIdFilter && (
            <span className="text-secondary ml-2">(filtered by hunt)</span>
          )}
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        {/* Tier tabs */}
        <div className="flex gap-1 bg-surface-2 border border-border rounded-lg p-1">
          {(["all", "hot", "review", "rejected"] as TierFilter[]).map((t) => (
            <button
              key={t}
              onClick={() => setTierFilter(t)}
              className={`font-mono text-[10px] uppercase tracking-[0.1em] px-3 py-1.5 rounded-md transition-all cursor-pointer ${
                tierFilter === t
                  ? "bg-secondary/10 text-secondary"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              {t === "all" ? "All" : t === "hot" ? "Hot" : t === "review" ? "Review" : "Rejected"}{" "}
              {tierCounts[t]}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <input
            type="text"
            placeholder="Search companies..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/30 transition-colors"
          />
        </div>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="bg-surface-2 border border-border rounded-xl px-6 py-16 text-center">
          <p className="font-mono text-xs text-text-dim">
            No leads found matching your filters
          </p>
        </div>
      ) : (
        <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-dim">
                  <th
                    onClick={() => handleSort("company_name")}
                    className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors"
                  >
                    Company
                    <SortArrow field="company_name" />
                  </th>
                  <th className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3">
                    Tier
                  </th>
                  <th
                    onClick={() => handleSort("score")}
                    className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors"
                  >
                    Score
                    <SortArrow field="score" />
                  </th>
                  <th className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden md:table-cell">
                    Industry
                  </th>
                  <th className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden lg:table-cell">
                    Country
                  </th>
                  <th className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden lg:table-cell">
                    Status
                  </th>
                  <th
                    onClick={() => handleSort("created_at")}
                    className="text-left font-mono text-[10px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors hidden sm:table-cell"
                  >
                    Date
                    <SortArrow field="created_at" />
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dim">
                {filtered.map((lead) => {
                  const badge = TIER_BADGE[lead.tier] || TIER_BADGE.rejected;
                  const statusDot =
                    STATUS_DOT[lead.status || "new"] || STATUS_DOT.new;
                  return (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLeadId(lead.id)}
                      className="hover:bg-surface-3/50 transition-colors cursor-pointer"
                    >
                      <td className="px-5 py-3.5">
                        <div>
                          <p className="font-mono text-xs text-text-primary font-medium truncate max-w-[200px]">
                            {lead.company_name}
                          </p>
                          <p className="font-mono text-[10px] text-text-dim truncate max-w-[200px]">
                            {lead.domain}
                          </p>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono border ${badge.bg}`}
                        >
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-sm font-bold text-text-primary">
                          {lead.score}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden md:table-cell">
                        <span className="font-mono text-[10px] text-text-muted truncate max-w-[140px] block">
                          {lead.industry_category || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden lg:table-cell">
                        <span className="font-mono text-[10px] text-text-muted">
                          {lead.country || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden lg:table-cell">
                        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-text-muted capitalize">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${statusDot}`}
                          />
                          {(lead.status || "new").replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden sm:table-cell">
                        <span className="font-mono text-[10px] text-text-dim">
                          {lead.created_at
                            ? new Date(lead.created_at).toLocaleDateString()
                            : "—"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lead Drawer */}
      {selectedLeadId && (
        <LeadDrawer
          leadId={selectedLeadId}
          onClose={() => setSelectedLeadId(null)}
          onStatusChange={handleStatusChange}
        />
      )}
    </div>
  );
}
