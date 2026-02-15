"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../../components/auth/SessionProvider";
import LeadDrawer from "./LeadDrawer";
import { useEnrichmentJobs, EnrichmentJobBanner } from "./EnrichmentJobTracker";

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
  notes: string | null;
  deal_value: number | null;
  contact_count: number;
  status_changed_at: string | null;
  created_at: string | null;
}

interface SearchItem {
  id: string;
  name: string | null;
  industry: string | null;
  company_profile: string | null;
  technology_focus: string | null;
  qualifying_criteria: string | null;
  total_found: number;
  hot: number;
  review: number;
  rejected: number;
  created_at: string | null;
}

type TierFilter = "all" | "hot" | "review" | "rejected";
type SortField = "score" | "company_name" | "created_at";

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

/* ── Colour palette for pipeline cards ── */
const PIPELINE_COLORS = [
  "border-secondary/40 bg-secondary/5",
  "border-blue-400/40 bg-blue-400/5",
  "border-purple-400/40 bg-purple-400/5",
  "border-amber-400/40 bg-amber-400/5",
  "border-teal-400/40 bg-teal-400/5",
  "border-pink-400/40 bg-pink-400/5",
  "border-cyan-400/40 bg-cyan-400/5",
  "border-orange-400/40 bg-orange-400/5",
];

export default function LeadsPage() {
  const { session } = useAuth();
  const searchParams = useSearchParams();
  const searchIdParam = searchParams.get("search_id");

  const [leads, setLeads] = useState<Lead[]>([]);
  const [searches, setSearches] = useState<SearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [tierFilter, setTierFilter] = useState<TierFilter>("all");
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(
    searchIdParam
  );
  const [dbSearchQuery, setDbSearchQuery] = useState("");
  const [dbSearchResults, setDbSearchResults] = useState<Lead[] | null>(null);
  const [dbSearching, setDbSearching] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [hasContactsFilter, setHasContactsFilter] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState<Set<string>>(new Set());
  const [batchMenuOpen, setBatchMenuOpen] = useState(false);
  const [confirmDeletePipelineId, setConfirmDeletePipelineId] = useState<string | null>(null);
  const [deletingPipelineId, setDeletingPipelineId] = useState<string | null>(null);
  const { activeJob, liveProgress, liveProcessed, startBatchJob, fetchJobs: refreshJobs } = useEnrichmentJobs();

  /* ── Fetch all leads (no search_id filter – we filter client-side) ── */
  const fetchLeads = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const params = new URLSearchParams({
        sort: sortField,
        order: sortOrder,
      });
      if (tierFilter !== "all") params.set("tier", tierFilter);

      const res = await fetch(`/api/proxy/leads?${params}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setLeads(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session, sortField, sortOrder, tierFilter]);

  /* ── Fetch searches (pipelines) ── */
  const fetchSearches = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/searches", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setSearches(await res.json());
    } catch {
      /* ignore */
    }
  }, [session]);

  /* ── Delete a pipeline and its leads ── */
  const handleDeletePipeline = useCallback(async (searchId: string) => {
    if (!session?.access_token) return;
    setDeletingPipelineId(searchId);
    try {
      const res = await fetch(`/api/proxy/searches/${searchId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        setSearches((prev) => prev.filter((s) => s.id !== searchId));
        setLeads((prev) => prev.filter((l) => l.search_id !== searchId));
        if (selectedPipeline === searchId) setSelectedPipeline(null);
      }
    } finally {
      setDeletingPipelineId(null);
      setConfirmDeletePipelineId(null);
    }
  }, [session, selectedPipeline]);

  useEffect(() => {
    fetchLeads();
    fetchSearches();
  }, [fetchLeads, fetchSearches]);

  /* ── Pipeline-aware filtering ── */
  const pipelineLeads = useMemo(() => {
    if (!selectedPipeline) return leads;
    return leads.filter((l) => l.search_id === selectedPipeline);
  }, [leads, selectedPipeline]);

  const sourceLeads = dbSearchResults !== null ? dbSearchResults : pipelineLeads;
  const filtered = sourceLeads.filter((l) => {
    if (hasContactsFilter && (l.contact_count || 0) === 0) return false;
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      l.company_name.toLowerCase().includes(q) ||
      l.domain.toLowerCase().includes(q) ||
      (l.country || "").toLowerCase().includes(q) ||
      (l.industry_category || "").toLowerCase().includes(q)
    );
  });

  const contactsFoundCount = useMemo(
    () => sourceLeads.filter((l) => (l.contact_count || 0) > 0).length,
    [sourceLeads]
  );

  /* ── Tier counts scoped to selected pipeline ── */
  const tierCounts = useMemo(() => ({
    all: pipelineLeads.length,
    hot: pipelineLeads.filter((l) => l.tier === "hot").length,
    review: pipelineLeads.filter((l) => l.tier === "review").length,
    rejected: pipelineLeads.filter((l) => l.tier === "rejected").length,
  }), [pipelineLeads]);

  /* ── Per-pipeline lead counts (from actual leads data for accuracy) ── */
  const pipelineLeadCounts = useMemo(() => {
    const map: Record<string, { total: number; hot: number; review: number; rejected: number }> = {};
    for (const l of leads) {
      if (!map[l.search_id]) map[l.search_id] = { total: 0, hot: 0, review: 0, rejected: 0 };
      map[l.search_id].total++;
      if (l.tier === "hot") map[l.search_id].hot++;
      else if (l.tier === "review") map[l.search_id].review++;
      else if (l.tier === "rejected") map[l.search_id].rejected++;
    }
    return map;
  }, [leads]);

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

  const handleDbSearch = useCallback(async () => {
    if (!session?.access_token || !dbSearchQuery.trim()) {
      setDbSearchResults(null);
      return;
    }
    setDbSearching(true);
    try {
      const params = new URLSearchParams({ q: dbSearchQuery.trim() });
      if (tierFilter !== "all") params.set("tier", tierFilter);
      const res = await fetch(`/api/proxy/leads/search?${params}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        setDbSearchResults(await res.json());
      }
    } finally {
      setDbSearching(false);
    }
  }, [session, dbSearchQuery, tierFilter]);

  const handleExport = useCallback(async (options?: { tier?: string; search_id?: string; label?: string }) => {
    if (!session?.access_token) return;
    setExporting(true);
    setExportMenuOpen(false);
    try {
      const params = new URLSearchParams();
      if (options?.tier) params.set("tier", options.tier);
      if (options?.search_id) params.set("search_id", options.search_id);
      const qs = params.toString();
      const url = `/api/proxy/leads/export${qs ? `?${qs}` : ""}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        // Build a descriptive filename
        const parts = ["leads"];
        if (options?.tier) parts.push(options.tier);
        if (options?.search_id) parts.push("pipeline");
        parts.push(new Date().toISOString().slice(0, 10));
        a.download = `${parts.join("-")}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      }
    } finally {
      setExporting(false);
    }
  }, [session]);

  const toggleSelectLead = (id: string) => {
    setSelectedLeadIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedLeadIds.size === filtered.length) {
      setSelectedLeadIds(new Set());
    } else {
      setSelectedLeadIds(new Set(filtered.map((l) => l.id)));
    }
  };

  const handleBatchEnrich = async (action: string) => {
    const ids = Array.from(selectedLeadIds);
    if (ids.length === 0) return;
    setBatchMenuOpen(false);
    await startBatchJob(ids, action);
    setSelectedLeadIds(new Set());
  };

  const [batchDrafting, setBatchDrafting] = useState(false);
  const [batchDraftResults, setBatchDraftResults] = useState<{ success: number; failed: number } | null>(null);

  const handleBatchDraftEmail = async () => {
    if (!session?.access_token) return;
    const ids = Array.from(selectedLeadIds);
    if (ids.length === 0) return;
    setBatchMenuOpen(false);
    setBatchDrafting(true);
    setBatchDraftResults(null);
    try {
      const res = await fetch("/api/proxy/leads/batch-draft-email", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          lead_ids: ids,
          tone: "consultative",
          sender_context: localStorage.getItem("hunt_sender_context") || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const success = data.drafts?.filter((d: { status: string }) => d.status === "ok").length || 0;
        const failed = data.drafts?.filter((d: { status: string }) => d.status === "error").length || 0;
        setBatchDraftResults({ success, failed });
      }
    } catch { /* ignore */ }
    finally {
      setBatchDrafting(false);
      setSelectedLeadIds(new Set());
    }
  };

  // Refresh leads when a batch job completes
  useEffect(() => {
    if (activeJob?.status === "complete") {
      fetchLeads();
    }
  }, [activeJob?.status, fetchLeads]);

  const selectedSearchInfo = searches.find((s) => s.id === selectedPipeline);

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
      <div className="flex items-start sm:items-center justify-between gap-3 flex-col sm:flex-row">
        <div>
          <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
            Leads
          </h1>
          <p className="font-sans text-sm text-text-muted mt-1">
            {leads.length} lead{leads.length !== 1 && "s"} across{" "}
            {searches.length} pipeline{searches.length !== 1 && "s"}
            {selectedPipeline && selectedSearchInfo && (
              <span className="text-secondary ml-2">
                — viewing {selectedSearchInfo.name || selectedSearchInfo.industry || "Pipeline"}
              </span>
            )}
            {dbSearchResults !== null && (
              <span className="text-secondary ml-2">
                ({dbSearchResults.length} search results)
              </span>
            )}
          </p>
        </div>
        <div className="relative flex gap-2">
          <button
            onClick={() => setExportMenuOpen((v) => !v)}
            disabled={exporting || leads.length === 0}
            className="inline-flex items-center gap-1.5 font-mono text-[12px] uppercase tracking-[0.15em] px-3 py-2 rounded-lg border border-border text-text-muted hover:text-text-primary hover:border-border-bright transition-colors cursor-pointer disabled:opacity-30"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {exporting ? "Exporting…" : "Export CSV"}
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          {exportMenuOpen && (
            <>
              {/* Backdrop to close menu */}
              <div className="fixed inset-0 z-40" onClick={() => setExportMenuOpen(false)} />
              <div className="absolute right-0 top-full mt-1 z-50 w-56 bg-surface-2 border border-border rounded-xl shadow-xl py-1.5 animate-in fade-in slide-in-from-top-1 duration-150">
                <p className="px-3 py-1.5 font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim">
                  Export as CSV
                </p>

                <button
                  onClick={() => handleExport()}
                  className="w-full text-left px-3 py-2 font-mono text-[12px] text-text-primary hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                >
                  <span>All Leads</span>
                  <span className="text-text-dim text-[12px]">{leads.length}</span>
                </button>

                <button
                  onClick={() => handleExport({ tier: "hot" })}
                  className="w-full text-left px-3 py-2 font-mono text-[12px] text-hot hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                >
                  <span>🔥 Hot Leads Only</span>
                  <span className="text-text-dim text-[12px]">{tierCounts.hot}</span>
                </button>

                <button
                  onClick={() => handleExport({ tier: "review" })}
                  className="w-full text-left px-3 py-2 font-mono text-[12px] text-review hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                >
                  <span>🔍 Review Leads Only</span>
                  <span className="text-text-dim text-[12px]">{tierCounts.review}</span>
                </button>

                <button
                  onClick={() => handleExport({ tier: "rejected" })}
                  className="w-full text-left px-3 py-2 font-mono text-[12px] text-text-muted hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                >
                  <span>❌ Rejected Leads Only</span>
                  <span className="text-text-dim text-[12px]">{tierCounts.rejected}</span>
                </button>

                {selectedPipeline && selectedSearchInfo && (
                  <>
                    <div className="border-t border-border my-1" />
                    <p className="px-3 py-1.5 font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim">
                      Current Pipeline
                    </p>
                    <button
                      onClick={() => handleExport({ search_id: selectedPipeline })}
                      className="w-full text-left px-3 py-2 font-mono text-[12px] text-secondary hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                    >
                      <span className="truncate pr-2">{selectedSearchInfo.name || selectedSearchInfo.industry || "Pipeline"} — All</span>
                      <span className="text-text-dim text-[12px] flex-shrink-0">{pipelineLeads.length}</span>
                    </button>
                    <button
                      onClick={() => handleExport({ search_id: selectedPipeline, tier: "hot" })}
                      className="w-full text-left px-3 py-2 font-mono text-[12px] text-hot hover:bg-surface-3 transition-colors flex items-center justify-between cursor-pointer"
                    >
                      <span className="truncate pr-2">{selectedSearchInfo.name || selectedSearchInfo.industry || "Pipeline"} — Hot</span>
                      <span className="text-text-dim text-[12px] flex-shrink-0">{pipelineLeads.filter(l => l.tier === "hot").length}</span>
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ═══ Pipeline cards ═══ */}
      {searches.length > 0 && (
        <div>
          <h2 className="font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim mb-3">
            Filter by Pipeline
          </h2>
          <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
            {/* All pipelines card */}
            <button
              onClick={() => { setSelectedPipeline(null); setDbSearchResults(null); setDbSearchQuery(""); }}
              className={`flex-shrink-0 w-44 rounded-xl border p-4 transition-all cursor-pointer text-left ${
                !selectedPipeline
                  ? "border-secondary/50 bg-secondary/10 ring-1 ring-secondary/20"
                  : "border-border bg-surface-2 hover:border-border-bright"
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded-lg bg-secondary/10 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-secondary">
                    <rect x="3" y="3" width="7" height="7" rx="1" />
                    <rect x="14" y="3" width="7" height="7" rx="1" />
                    <rect x="3" y="14" width="7" height="7" rx="1" />
                    <rect x="14" y="14" width="7" height="7" rx="1" />
                  </svg>
                </div>
                <span className="font-mono text-[12px] font-semibold text-text-primary uppercase tracking-[0.1em]">
                  All
                </span>
              </div>
              <span className="font-mono text-lg font-bold text-text-primary">
                {leads.length}
              </span>
              <span className="font-mono text-[12px] text-text-dim ml-1.5">
                leads
              </span>
            </button>

            {/* Individual pipeline cards */}
            {searches.map((s, idx) => {
              const counts = pipelineLeadCounts[s.id] || { total: 0, hot: 0, review: 0, rejected: 0 };
              const isSelected = selectedPipeline === s.id;
              const colorClass = PIPELINE_COLORS[idx % PIPELINE_COLORS.length];
              const displayName = s.name || s.industry || s.technology_focus || "Untitled Pipeline";
              const isConfirming = confirmDeletePipelineId === s.id;
              const isDeleting = deletingPipelineId === s.id;

              return (
                <div
                  key={s.id}
                  className={`group relative flex-shrink-0 w-56 rounded-xl border p-4 transition-all text-left ${
                    isSelected
                      ? `${colorClass} ring-1 ring-secondary/20`
                      : "border-border bg-surface-2 hover:border-border-bright"
                  } ${isDeleting ? "opacity-50 pointer-events-none" : ""}`}
                >
                  {/* Delete button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isConfirming) {
                        handleDeletePipeline(s.id);
                      } else {
                        setConfirmDeletePipelineId(s.id);
                      }
                    }}
                    onBlur={() => {
                      // Auto-cancel confirm after losing focus
                      setTimeout(() => setConfirmDeletePipelineId((prev) => prev === s.id ? null : prev), 200);
                    }}
                    title={isConfirming ? "Click again to confirm" : "Delete pipeline"}
                    className={`absolute top-2 right-2 z-10 w-6 h-6 rounded-md flex items-center justify-center transition-all cursor-pointer ${
                      isConfirming
                        ? "bg-red-500/20 text-red-400 border border-red-500/30 scale-110"
                        : "text-text-dim hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100"
                    }`}
                  >
                    {isDeleting ? (
                      <div className="w-3 h-3 border border-red-400/50 border-t-red-400 rounded-full animate-spin" />
                    ) : isConfirming ? (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                      </svg>
                    )}
                  </button>
                  {isConfirming && (
                    <div className="absolute -top-8 right-0 z-20 px-2 py-1 rounded-md bg-red-500/10 border border-red-500/20 font-mono text-[9px] text-red-400 whitespace-nowrap">
                      Click again to delete
                    </div>
                  )}

                  {/* Clickable card body */}
                  <button
                    onClick={() => {
                      setSelectedPipeline(isSelected ? null : s.id);
                      setDbSearchResults(null);
                      setDbSearchQuery("");
                    }}
                    className="w-full text-left cursor-pointer"
                  >
                    <p className="font-mono text-[11px] font-semibold text-text-primary truncate mb-1.5 leading-tight pr-6">
                      {displayName}
                    </p>
                    {s.qualifying_criteria && (
                      <p className="font-sans text-[10px] text-text-dim truncate mb-2 leading-tight">
                        {s.qualifying_criteria}
                      </p>
                    )}
                    <div className="flex items-baseline gap-1.5 mb-2">
                      <span className="font-mono text-lg font-bold text-text-primary">
                        {counts.total}
                      </span>
                      <span className="font-mono text-[10px] text-text-dim">
                        leads
                      </span>
                    </div>
                    <div className="flex items-center gap-2 font-mono text-[9px]">
                      <span className="text-hot">{counts.hot} hot</span>
                      <span className="text-text-dim">·</span>
                      <span className="text-review">{counts.review} review</span>
                      <span className="text-text-dim">·</span>
                      <span className="text-text-dim">{counts.rejected} rej</span>
                    </div>
                    {s.created_at && (
                      <p className="font-mono text-[9px] text-text-dim mt-2">
                        {new Date(s.created_at).toLocaleDateString()}
                      </p>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ═══ Search bar + tier filter ═══ */}
      <div className="flex flex-col gap-3">
        {/* DB search */}
        <div className="flex gap-2">
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              placeholder="Search all leads (company, domain, industry, country)..."
              value={dbSearchQuery}
              onChange={(e) => {
                setDbSearchQuery(e.target.value);
                if (!e.target.value.trim()) setDbSearchResults(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleDbSearch();
              }}
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/30 transition-colors"
            />
          </div>
          <button
            onClick={handleDbSearch}
            disabled={dbSearching || !dbSearchQuery.trim()}
            className="font-mono text-[12px] uppercase tracking-[0.15em] px-4 py-2 rounded-lg bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors disabled:opacity-30 cursor-pointer"
          >
            {dbSearching ? "…" : "Search DB"}
          </button>
          {dbSearchResults !== null && (
            <button
              onClick={() => {
                setDbSearchResults(null);
                setDbSearchQuery("");
              }}
              className="font-mono text-[12px] uppercase tracking-[0.15em] px-3 py-2 rounded-lg border border-border text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>

        {/* Tier tabs + inline filter */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="flex gap-1 bg-surface-2 border border-border rounded-lg p-1">
            {(["all", "hot", "review", "rejected"] as TierFilter[]).map(
              (t) => (
                <button
                  key={t}
                  onClick={() => setTierFilter(t)}
                  className={`font-mono text-[12px] uppercase tracking-[0.1em] px-3 py-1.5 rounded-md transition-all cursor-pointer ${
                    tierFilter === t
                      ? "bg-secondary/10 text-secondary"
                      : "text-text-muted hover:text-text-primary"
                  }`}
                >
                  {t === "all"
                    ? "All"
                    : t === "hot"
                    ? "Hot"
                    : t === "review"
                    ? "Review"
                    : "Rejected"}{" "}
                  {tierCounts[t]}
                </button>
              )
            )}
          </div>

          <button
            onClick={() => setHasContactsFilter((v) => !v)}
            className={`font-mono text-[12px] uppercase tracking-[0.1em] px-3 py-1.5 rounded-md border transition-all cursor-pointer flex items-center gap-1.5 ${
              hasContactsFilter
                ? "bg-green-400/10 border-green-400/30 text-green-400"
                : "border-border text-text-muted hover:text-text-primary hover:border-border-bright"
            }`}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            Has Contacts {contactsFoundCount}
          </button>

          <div className="relative flex-1 max-w-xs">
            <input
              type="text"
              placeholder="Filter companies..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/30 transition-colors"
            />
          </div>

          {selectedPipeline && (
            <button
              onClick={() => setSelectedPipeline(null)}
              className="font-mono text-[12px] uppercase tracking-[0.15em] px-3 py-1.5 rounded-md border border-secondary/20 text-secondary hover:bg-secondary/10 transition-colors cursor-pointer flex items-center gap-1.5"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Clear pipeline filter
            </button>
          )}
        </div>
      </div>

      {/* ═══ Enrichment Job Progress Banner ═══ */}
      <EnrichmentJobBanner
        activeJob={activeJob}
        liveProgress={liveProgress}
        liveProcessed={liveProcessed}
      />

      {/* ═══ Batch Action Bar ═══ */}
      {selectedLeadIds.size > 0 && (
        <div className="bg-surface-2 border border-secondary/20 rounded-xl px-5 py-3 flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[12px] text-text-primary font-semibold">
              {selectedLeadIds.size} lead{selectedLeadIds.size > 1 ? "s" : ""} selected
            </span>
            <button
              onClick={() => setSelectedLeadIds(new Set())}
              className="font-mono text-[12px] text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            >
              Clear
            </button>
          </div>
          <div className="relative">
            <button
              onClick={() => setBatchMenuOpen((v) => !v)}
              disabled={!!activeJob && (activeJob.status === "running" || activeJob.status === "pending")}
              className="inline-flex items-center gap-1.5 font-mono text-[12px] uppercase tracking-[0.15em] px-4 py-2 rounded-lg bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors cursor-pointer disabled:opacity-40"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M3 3v5h5" />
                <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                <path d="M16 16h5v5" />
              </svg>
              Batch Enrich
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {batchMenuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setBatchMenuOpen(false)} />
                <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-surface-2 border border-border rounded-xl shadow-xl py-1.5">
                  <p className="px-3 py-1.5 font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim">
                    Batch Action ({selectedLeadIds.size} leads)
                  </p>
                  <button
                    onClick={() => handleBatchEnrich("recrawl_contacts")}
                    className="w-full text-left px-3 py-2.5 font-mono text-[12px] text-text-primary hover:bg-surface-3 transition-colors cursor-pointer"
                  >
                    <span className="text-secondary">↻</span> Re-crawl for Contacts
                    <p className="font-sans text-[12px] text-text-dim mt-0.5">Crawl websites for contact info</p>
                  </button>
                  <button
                    onClick={() => handleBatchEnrich("linkedin")}
                    className="w-full text-left px-3 py-2.5 font-mono text-[12px] text-text-primary hover:bg-surface-3 transition-colors cursor-pointer"
                  >
                    <span className="text-blue-400">in</span> Find Decision Makers (LinkedIn)
                    <p className="font-sans text-[12px] text-text-dim mt-0.5">LinkedIn lookup for key contacts</p>
                  </button>
                  <button
                    onClick={() => handleBatchEnrich("requalify")}
                    className="w-full text-left px-3 py-2.5 font-mono text-[12px] text-text-primary hover:bg-surface-3 transition-colors cursor-pointer"
                  >
                    <span className="text-amber-400">✎</span> Re-qualify All
                    <p className="font-sans text-[12px] text-text-dim mt-0.5">Re-crawl &amp; re-score with AI</p>
                  </button>
                  <button
                    onClick={() => handleBatchEnrich("full_recrawl")}
                    className="w-full text-left px-3 py-2.5 font-mono text-[12px] text-text-primary hover:bg-surface-3 transition-colors cursor-pointer"
                  >
                    <span className="text-purple-400">⚙</span> Full Re-crawl (Score + Contacts)
                    <p className="font-sans text-[12px] text-text-dim mt-0.5">Complete re-crawl of everything</p>
                  </button>
                  <div className="border-t border-border-dim my-1" />
                  <button
                    onClick={handleBatchDraftEmail}
                    disabled={batchDrafting}
                    className="w-full text-left px-3 py-2.5 font-mono text-[11px] text-text-primary hover:bg-surface-3 transition-colors cursor-pointer disabled:opacity-40"
                  >
                    <span className="text-hot">✉</span> Batch Draft Emails
                    <p className="font-sans text-[10px] text-text-dim mt-0.5">AI-generate personalized emails (max 10)</p>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Batch draft status */}
      {batchDrafting && (
        <div className="bg-hot/5 border border-hot/20 rounded-xl px-5 py-3 flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-hot/30 border-t-hot rounded-full animate-spin" />
          <span className="font-mono text-[11px] text-hot">Generating AI email drafts…</span>
        </div>
      )}
      {batchDraftResults && (
        <div className="bg-green-400/5 border border-green-400/20 rounded-xl px-5 py-3 flex items-center justify-between">
          <span className="font-mono text-[11px] text-green-400">
            ✉ {batchDraftResults.success} email draft{batchDraftResults.success !== 1 ? "s" : ""} generated
            {batchDraftResults.failed > 0 && (
              <span className="text-red-400 ml-2">· {batchDraftResults.failed} failed</span>
            )}
          </span>
          <button
            onClick={() => setBatchDraftResults(null)}
            className="font-mono text-[10px] text-text-dim hover:text-text-muted cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ═══ Leads table ═══ */}
      {filtered.length === 0 ? (
        <div className="bg-surface-2 border border-border rounded-xl px-6 py-16 text-center">
          <p className="font-mono text-xs text-text-dim">
            No leads found matching your filters
          </p>
          {selectedPipeline && (
            <button
              onClick={() => setSelectedPipeline(null)}
              className="mt-3 font-mono text-[12px] uppercase tracking-[0.15em] text-secondary hover:text-secondary/80 cursor-pointer"
            >
              Show all pipelines →
            </button>
          )}
        </div>
      ) : (
        <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-dim">
                  <th className="w-10 px-3 py-3">
                    <input
                      type="checkbox"
                      checked={filtered.length > 0 && selectedLeadIds.size === filtered.length}
                      onChange={toggleSelectAll}
                      className="w-3.5 h-3.5 accent-secondary cursor-pointer"
                    />
                  </th>
                  <th
                    onClick={() => handleSort("company_name")}
                    className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors"
                  >
                    Company
                    <SortArrow field="company_name" />
                  </th>
                  <th className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3">
                    Tier
                  </th>
                  <th
                    onClick={() => handleSort("score")}
                    className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors"
                  >
                    Score
                    <SortArrow field="score" />
                  </th>
                  <th className="text-center font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-3 py-3 hidden md:table-cell">
                    Contacts
                  </th>
                  <th className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden md:table-cell">
                    Industry
                  </th>
                  <th className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden lg:table-cell">
                    Country
                  </th>
                  <th className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden lg:table-cell">
                    Status
                  </th>
                  {!selectedPipeline && (
                    <th className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 hidden xl:table-cell">
                      Pipeline
                    </th>
                  )}
                  <th
                    onClick={() => handleSort("created_at")}
                    className="text-left font-mono text-[12px] uppercase tracking-[0.15em] text-text-muted px-5 py-3 cursor-pointer hover:text-text-primary transition-colors hidden sm:table-cell"
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
                  const pipelineName =
                    searches.find((s) => s.id === lead.search_id)?.industry ||
                    searches.find((s) => s.id === lead.search_id)?.name ||
                    null;
                  return (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLeadId(lead.id)}
                      className={`hover:bg-surface-3/50 transition-colors cursor-pointer ${
                        selectedLeadIds.has(lead.id) ? "bg-secondary/5" : ""
                      }`}
                    >
                      <td className="px-3 py-3.5">
                        <input
                          type="checkbox"
                          checked={selectedLeadIds.has(lead.id)}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleSelectLead(lead.id);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="w-3.5 h-3.5 accent-secondary cursor-pointer"
                        />
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2.5">
                          {lead.domain && (
                            <img
                              src={`https://www.google.com/s2/favicons?domain=${lead.domain}&sz=32`}
                              alt=""
                              width={16}
                              height={16}
                              className="rounded-sm flex-shrink-0"
                              loading="lazy"
                            />
                          )}
                          <div>
                            <p className="font-mono text-xs text-text-primary font-medium truncate max-w-[200px]">
                              {lead.company_name}
                            </p>
                            <div className="flex items-center gap-1.5">
                              <p className="font-mono text-[12px] text-text-dim truncate max-w-[180px]">
                                {lead.domain}
                              </p>
                              {(lead.contact_count || 0) > 0 && (
                                <span className="inline-flex items-center gap-0.5 font-mono text-[12px] text-green-400 bg-green-400/10 border border-green-400/20 rounded px-1 py-px flex-shrink-0">
                                  <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                                    <circle cx="9" cy="7" r="4" />
                                  </svg>
                                  {lead.contact_count}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[12px] font-mono border ${badge.bg}`}
                        >
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-sm font-bold text-text-primary">
                          {lead.score}
                        </span>
                      </td>
                      <td className="px-3 py-3.5 hidden md:table-cell text-center">
                        {(lead.contact_count || 0) > 0 ? (
                          <span className="inline-flex items-center gap-1 font-mono text-[12px] text-green-400 bg-green-400/10 border border-green-400/20 rounded-md px-2 py-0.5">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                              <circle cx="9" cy="7" r="4" />
                            </svg>
                            {lead.contact_count}
                          </span>
                        ) : (
                          <span className="font-mono text-[12px] text-text-dim">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 hidden md:table-cell">
                        <span className="font-mono text-[12px] text-text-muted truncate max-w-[140px] block">
                          {lead.industry_category || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden lg:table-cell">
                        <span className="font-mono text-[12px] text-text-muted">
                          {lead.country || "—"}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 hidden lg:table-cell">
                        <span className="inline-flex items-center gap-1.5 font-mono text-[12px] text-text-muted capitalize">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${statusDot}`}
                          />
                          {(lead.status || "new").replace("_", " ")}
                        </span>
                      </td>
                      {!selectedPipeline && (
                        <td className="px-5 py-3.5 hidden xl:table-cell">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedPipeline(lead.search_id);
                            }}
                            className="font-mono text-[12px] text-text-dim hover:text-secondary truncate max-w-[120px] block transition-colors"
                            title={pipelineName || "Unknown pipeline"}
                          >
                            {pipelineName || "—"}
                          </button>
                        </td>
                      )}
                      <td className="px-5 py-3.5 hidden sm:table-cell">
                        <span className="font-mono text-[12px] text-text-dim">
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
          onLeadUpdate={(leadId, updates) => {
            setLeads((prev) =>
              prev.map((l) =>
                l.id === leadId
                  ? {
                      ...l,
                      ...(updates.notes !== undefined && {
                        notes: updates.notes ?? null,
                      }),
                      ...(updates.deal_value !== undefined && {
                        deal_value: updates.deal_value ?? null,
                      }),
                    }
                  : l
              )
            );
          }}
        />
      )}
    </div>
  );
}
