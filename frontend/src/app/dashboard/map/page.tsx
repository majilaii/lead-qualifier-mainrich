"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useAuth } from "../../components/auth/SessionProvider";
import { usePipeline } from "../../components/hunt/PipelineContext";
import { MapSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import MapGL, { Marker, Popup, NavigationControl } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

/* ── Types ──────────────────────────────────────────── */

interface GeoLead {
  id: string;
  search_id: string;
  company_name: string;
  domain: string;
  website_url: string;
  score: number;
  tier: string;
  country: string | null;
  latitude: number;
  longitude: number;
  status: string | null;
  hardware_type: string | null;
  industry_category: string | null;
  reasoning: string | null;
  key_signals: string[];
  red_flags: string[];
  search_label: string;
  search_date: string | null;
  isLive?: boolean;
}

interface HuntGroup {
  searchId: string;
  label: string;
  date: string | null;
  leads: GeoLead[];
  hot: number;
  review: number;
  rejected: number;
  visible: boolean;
}

// All backend calls go through /api/proxy/* (Next.js server proxy)
const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

const DOT_COLORS: Record<string, string> = {
  hot: "#ef4444",
  review: "#f59e0b",
  rejected: "#71717a",
};

const DOT_GLOW: Record<string, string> = {
  hot: "rgba(239, 68, 68, 0.4)",
  review: "rgba(245, 158, 11, 0.3)",
  rejected: "rgba(113, 113, 122, 0.2)",
};

const TIER_STYLES: Record<string, { label: string; color: string; bg: string; border: string }> = {
  hot: { label: "HOT", color: "text-hot", bg: "bg-hot/10", border: "border-hot/20" },
  review: { label: "REVIEW", color: "text-review", bg: "bg-review/10", border: "border-review/20" },
  rejected: { label: "REJECTED", color: "text-text-dim", bg: "bg-text-dim/10", border: "border-text-dim/20" },
};

const GROUP_COLORS = [
  "#818cf8", "#34d399", "#f472b6", "#fbbf24", "#22d3ee",
  "#a78bfa", "#fb923c", "#2dd4bf", "#e879f9", "#a3e635",
];

export default function MapPage() {
  const { session } = useAuth();
  const { qualifiedCompanies, phase, pipelineId: liveSearchId } = usePipeline();

  const [dbLeads, setDbLeads] = useState<GeoLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLead, setSelectedLead] = useState<GeoLead | null>(null);
  const [tierFilter, setTierFilter] = useState<Set<string>>(new Set(["hot", "review", "rejected"]));
  const [searchQuery, setSearchQuery] = useState("");
  const [hiddenGroups, setHiddenGroups] = useState<Set<string>>(new Set());
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"groups" | "all">("groups");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deletingLead, setDeletingLead] = useState<string | null>(null);

  const mapRef = useRef<{ flyTo: (opts: { center: [number, number]; zoom: number; duration: number }) => void } | null>(null);
  const flownToRef = useRef<Set<string>>(new Set());

  /* ── Fetch historical leads from DB ── */
  const fetchLeads = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/leads/geo", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setDbLeads(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => { fetchLeads(); }, [fetchLeads]);

  /* ── Merge live pipeline leads + DB leads ── */
  const liveLeads: GeoLead[] = useMemo(() => {
    return qualifiedCompanies
      .filter((c) => c.latitude != null && c.longitude != null)
      .map((c, i) => ({
        id: `live-${i}-${c.domain}`,
        search_id: liveSearchId || "live",
        company_name: c.title,
        domain: c.domain,
        website_url: c.url || `https://${c.domain}`,
        score: c.score,
        tier: c.tier,
        country: c.country ?? null,
        latitude: c.latitude!,
        longitude: c.longitude!,
        status: null,
        hardware_type: c.hardware_type || null,
        industry_category: c.industry_category || null,
        reasoning: c.reasoning || null,
        key_signals: c.key_signals || [],
        red_flags: c.red_flags || [],
        search_label: "Current Hunt",
        search_date: new Date().toISOString(),
        isLive: true,
      }));
  }, [qualifiedCompanies, liveSearchId]);

  const allLeads = useMemo(() => {
    const liveDomains = new Set(liveLeads.map((l) => l.domain));
    const historical = dbLeads.filter((l) => !liveDomains.has(l.domain));
    return [...liveLeads, ...historical];
  }, [liveLeads, dbLeads]);

  /* ── Build hunt groups ── */
  const huntGroups: HuntGroup[] = useMemo(() => {
    const groupMap = new Map<string, GeoLead[]>();
    allLeads.forEach((l) => {
      const arr = groupMap.get(l.search_id) || [];
      arr.push(l);
      groupMap.set(l.search_id, arr);
    });
    const groups: HuntGroup[] = [];
    groupMap.forEach((leads, searchId) => {
      const first = leads[0];
      groups.push({
        searchId, label: first.search_label || "Untitled Hunt", date: first.search_date, leads,
        hot: leads.filter((l) => l.tier === "hot").length,
        review: leads.filter((l) => l.tier === "review").length,
        rejected: leads.filter((l) => l.tier === "rejected").length,
        visible: !hiddenGroups.has(searchId),
      });
    });
    groups.sort((a, b) => {
      if (a.leads.some((l) => l.isLive) && !b.leads.some((l) => l.isLive)) return -1;
      if (!a.leads.some((l) => l.isLive) && b.leads.some((l) => l.isLive)) return 1;
      const da = a.date ? new Date(a.date).getTime() : 0;
      const db_ = b.date ? new Date(b.date).getTime() : 0;
      return db_ - da;
    });
    return groups;
  }, [allLeads, hiddenGroups]);

  const groupColorMap = useMemo(() => {
    const colorMap = new Map<string, string>();
    huntGroups.forEach((g, i) => colorMap.set(g.searchId, GROUP_COLORS[i % GROUP_COLORS.length]));
    return colorMap;
  }, [huntGroups]);

  /* ── Fly to new lead ── */
  useEffect(() => {
    if (phase !== "qualifying" && phase !== "complete") return;
    const newLive = liveLeads.filter((l) => !flownToRef.current.has(l.id));
    if (newLive.length > 0) {
      const latest = newLive[newLive.length - 1];
      newLive.forEach((l) => flownToRef.current.add(l.id));
      if (phase === "qualifying") {
        mapRef.current?.flyTo({ center: [latest.longitude, latest.latitude], zoom: 4, duration: 1200 });
      }
    }
  }, [liveLeads, phase]);

  /* ── Helpers ── */
  const toggleTier = (tier: string) => {
    setTierFilter((prev) => { const next = new Set(prev); if (next.has(tier)) next.delete(tier); else next.add(tier); return next; });
  };
  const toggleGroup = (searchId: string) => {
    setHiddenGroups((prev) => { const next = new Set(prev); if (next.has(searchId)) next.delete(searchId); else next.add(searchId); return next; });
  };
  const showOnlyGroup = (searchId: string) => {
    const allIds = new Set(huntGroups.map((g) => g.searchId)); allIds.delete(searchId); setHiddenGroups(allIds);
  };
  const showAllGroups = () => setHiddenGroups(new Set());
  const hideAllGroups = () => setHiddenGroups(new Set(huntGroups.map((g) => g.searchId)));

  const deleteHunt = async (searchId: string) => {
    if (!session?.access_token || searchId === "live") return;
    try {
      const res = await fetch(`/api/proxy/searches/${searchId}`, { method: "DELETE", headers: { Authorization: `Bearer ${session.access_token}` } });
      if (res.ok) { setDbLeads((prev) => prev.filter((l) => l.search_id !== searchId)); setConfirmDelete(null); }
    } catch (e) { console.error("Failed to delete hunt:", e); }
  };

  const deleteLead = async (leadId: string, e?: React.MouseEvent) => {
    if (e) { e.stopPropagation(); e.preventDefault(); }
    if (!session?.access_token || leadId.startsWith("live-")) return;
    setDeletingLead(leadId);
    try {
      const res = await fetch(`/api/proxy/leads/${leadId}`, { method: "DELETE", headers: { Authorization: `Bearer ${session.access_token}` } });
      if (res.ok) {
        setDbLeads((prev) => prev.filter((l) => l.id !== leadId));
        if (selectedLead?.id === leadId) setSelectedLead(null);
      }
    } catch (e) { console.error("Failed to delete lead:", e); }
    finally { setDeletingLead(null); }
  };

  const filtered = allLeads.filter((l) => {
    if (!tierFilter.has(l.tier)) return false;
    if (hiddenGroups.has(l.search_id)) return false;
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return l.company_name.toLowerCase().includes(q) || l.domain.toLowerCase().includes(q) || (l.country || "").toLowerCase().includes(q) || l.search_label.toLowerCase().includes(q);
  });

  const flyToLead = (lead: GeoLead) => { setSelectedLead(lead); mapRef.current?.flyTo({ center: [lead.longitude, lead.latitude], zoom: 8, duration: 1500 }); };
  const flyToGroup = (group: HuntGroup) => {
    if (group.leads.length === 0) return;
    const lats = group.leads.map((l) => l.latitude); const lngs = group.leads.map((l) => l.longitude);
    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2;
    mapRef.current?.flyTo({ center: [centerLng, centerLat], zoom: 3, duration: 1500 });
  };

  const tierCounts = { hot: filtered.filter((l) => l.tier === "hot").length, review: filtered.filter((l) => l.tier === "review").length, rejected: filtered.filter((l) => l.tier === "rejected").length };
  const dotSize = (score: number) => Math.max(6, Math.min(16, score / 6));
  const mapStyle = "mapbox://styles/mapbox/dark-v11";
  const isPipelineRunning = phase === "qualifying";
  const formatDate = (dateStr: string | null) => { if (!dateStr) return ""; return new Date(dateStr).toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };

  return (
    <div className="flex h-full">
      {/* ═══ Left panel ═══ */}
      <div className="hidden md:flex flex-col w-80 border-r border-border-dim bg-surface-1/50">
        {/* Stats */}
        <div className="px-4 py-3 border-b border-border-dim bg-surface-2/50">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`} />
            <span className="font-mono text-[12px] text-text-muted uppercase tracking-[0.15em]">{isPipelineRunning ? "Live Pipeline" : "Lead Map"}</span>
            <span className="font-mono text-[12px] text-text-primary ml-auto">{filtered.length} / {allLeads.length} leads</span>
          </div>
          <div className="flex items-center gap-3 font-mono text-[12px]">
            <span className="text-hot">{tierCounts.hot} hot</span>
            <span className="text-review">{tierCounts.review} review</span>
            <span className="text-text-dim">{tierCounts.rejected} rejected</span>
            <span className="text-text-dim ml-auto">{huntGroups.length} hunts</span>
          </div>
        </div>
        {/* Filters */}
        <div className="px-4 py-3 border-b border-border-dim space-y-2">
          <div className="flex gap-1.5">
            {(["hot", "review", "rejected"] as const).map((tier) => (
              <button key={tier} onClick={() => toggleTier(tier)} className={`font-mono text-[12px] px-2.5 py-1 rounded-md border uppercase tracking-[0.1em] transition-all cursor-pointer ${tierFilter.has(tier) ? tier === "hot" ? "bg-hot/10 border-hot/20 text-hot" : tier === "review" ? "bg-review/10 border-review/20 text-review" : "bg-text-dim/10 border-text-dim/20 text-text-dim" : "border-border text-text-dim/50"}`}>{tier}</button>
            ))}
          </div>
          <input type="text" placeholder="Search leads or hunts..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full bg-surface-2 border border-border rounded-lg px-3 py-1.5 font-mono text-[12px] text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/30 transition-colors" />
          <div className="flex items-center gap-2">
            <button onClick={showAllGroups} className="font-mono text-[12px] text-text-dim hover:text-secondary transition-colors cursor-pointer">Show All</button>
            <span className="text-text-dim/30">·</span>
            <button onClick={hideAllGroups} className="font-mono text-[12px] text-text-dim hover:text-secondary transition-colors cursor-pointer">Hide All</button>
          </div>
        </div>
        {/* Tabs */}
        <div className="flex border-b border-border-dim">
          <button onClick={() => setSidebarTab("groups")} className={`flex-1 font-mono text-[12px] uppercase tracking-[0.15em] py-2 transition-colors cursor-pointer ${sidebarTab === "groups" ? "text-secondary border-b-2 border-secondary" : "text-text-dim hover:text-text-muted"}`}>By Hunt ({huntGroups.length})</button>
          <button onClick={() => setSidebarTab("all")} className={`flex-1 font-mono text-[12px] uppercase tracking-[0.15em] py-2 transition-colors cursor-pointer ${sidebarTab === "all" ? "text-secondary border-b-2 border-secondary" : "text-text-dim hover:text-text-muted"}`}>All Leads ({filtered.length})</button>
        </div>
        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {sidebarTab === "groups" ? (
            huntGroups.length === 0 ? (
              <div className="px-4 py-12 text-center"><p className="font-mono text-[12px] text-text-dim">{isPipelineRunning ? "Waiting for qualified leads…" : "No leads yet"}</p></div>
            ) : (
              <div className="divide-y divide-border-dim">
                {huntGroups.map((group) => {
                  const color = groupColorMap.get(group.searchId) || GROUP_COLORS[0];
                  const isExpanded = expandedGroup === group.searchId;
                  const isHidden = hiddenGroups.has(group.searchId);
                  const isLive = group.leads.some((l) => l.isLive);
                  return (
                    <div key={group.searchId}>
                      <div className={`px-3 py-2.5 transition-colors ${isHidden ? "opacity-40" : ""}`}>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setExpandedGroup(isExpanded ? null : group.searchId)} className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${isLive ? "animate-pulse" : ""}`} style={{ backgroundColor: color }} />
                            <span className="font-mono text-[12px] text-text-primary truncate">{group.label}</span>
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`text-text-dim transition-transform flex-shrink-0 ${isExpanded ? "rotate-90" : ""}`}><path d="M9 18l6-6-6-6" /></svg>
                          </button>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            {group.hot > 0 && <span className="font-mono text-[12px] text-hot bg-hot/10 px-1.5 py-0.5 rounded">{group.hot}</span>}
                            {group.review > 0 && <span className="font-mono text-[12px] text-review bg-review/10 px-1.5 py-0.5 rounded">{group.review}</span>}
                            <span className="font-mono text-[12px] text-text-dim">{group.leads.length}</span>
                          </div>
                          <button onClick={() => toggleGroup(group.searchId)} className="cursor-pointer flex-shrink-0" title={isHidden ? "Show on map" : "Hide from map"}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transition-colors ${isHidden ? "text-text-dim/40" : "text-text-muted hover:text-secondary"}`}>
                              {isHidden ? (<><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" /><line x1="1" y1="1" x2="23" y2="23" /></>) : (<><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>)}
                            </svg>
                          </button>
                        </div>
                        <div className="flex items-center gap-2 mt-1 ml-[18px]">
                          {group.date && <span className="font-mono text-[12px] text-text-dim">{formatDate(group.date)}</span>}
                          <div className="flex items-center gap-1 ml-auto">
                            <button onClick={() => showOnlyGroup(group.searchId)} className="font-mono text-[12px] text-text-dim hover:text-secondary transition-colors cursor-pointer">Solo</button>
                            <span className="text-text-dim/20">·</span>
                            <button onClick={() => flyToGroup(group)} className="font-mono text-[12px] text-text-dim hover:text-secondary transition-colors cursor-pointer">Focus</button>
                            {!isLive && (<>
                              <span className="text-text-dim/20">·</span>
                              {confirmDelete === group.searchId ? (
                                <span className="flex items-center gap-1">
                                  <button onClick={() => deleteHunt(group.searchId)} className="font-mono text-[12px] text-red-400 hover:text-red-300 transition-colors cursor-pointer">Confirm</button>
                                  <button onClick={() => setConfirmDelete(null)} className="font-mono text-[12px] text-text-dim hover:text-text-muted transition-colors cursor-pointer">Cancel</button>
                                </span>
                              ) : (
                                <button onClick={() => setConfirmDelete(group.searchId)} className="font-mono text-[12px] text-text-dim hover:text-red-400 transition-colors cursor-pointer">Delete</button>
                              )}
                            </>)}
                          </div>
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="bg-surface-2/30 border-t border-border-dim">
                          {group.leads.filter((l) => tierFilter.has(l.tier)).filter((l) => { if (!searchQuery) return true; const q = searchQuery.toLowerCase(); return l.company_name.toLowerCase().includes(q) || l.domain.toLowerCase().includes(q) || (l.country || "").toLowerCase().includes(q); }).sort((a, b) => b.score - a.score).map((lead) => (
                            <div key={lead.id} className={`flex items-center px-4 py-2 hover:bg-surface-3/50 transition-colors border-b border-border-dim/50 last:border-b-0 ${selectedLead?.id === lead.id ? "bg-surface-3/80" : ""}`}>
                              <button onClick={() => flyToLead(lead)} className="flex-1 min-w-0 text-left cursor-pointer">
                                <div className="flex items-center justify-between">
                                  <span className="font-mono text-[12px] text-text-primary truncate flex-1 flex items-center gap-1.5">
                                    {lead.isLive && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse flex-shrink-0" />}
                                    {lead.company_name}
                                  </span>
                                  <span className="font-mono text-[12px] font-bold ml-2" style={{ color: DOT_COLORS[lead.tier] }}>{lead.score}</span>
                                </div>
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="font-mono text-[12px] text-text-dim truncate">{lead.domain}</span>
                                  {lead.country && <span className="font-mono text-[12px] text-text-dim">· {lead.country}</span>}
                                </div>
                              </button>
                              {!lead.isLive && (lead.tier === "rejected" || lead.tier === "review") && (
                                <button onClick={(e) => deleteLead(lead.id, e)} disabled={deletingLead === lead.id} className="ml-2 text-text-dim/40 hover:text-red-400 transition-colors cursor-pointer flex-shrink-0 disabled:opacity-50" title="Delete lead">
                                  {deletingLead === lead.id ? <span className="w-3 h-3 border border-text-dim border-t-transparent rounded-full animate-spin inline-block" /> : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>}
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            filtered.length === 0 ? (
              <div className="px-4 py-12 text-center"><p className="font-mono text-[12px] text-text-dim">{isPipelineRunning ? "Waiting for qualified leads…" : "No leads with coordinates yet"}</p></div>
            ) : (
              <div className="divide-y divide-border-dim">
                {filtered.sort((a, b) => b.score - a.score).map((lead) => {
                  const groupColor = groupColorMap.get(lead.search_id);
                  return (
                    <div key={lead.id} className={`flex items-center px-4 py-3 hover:bg-surface-3/50 transition-colors ${selectedLead?.id === lead.id ? "bg-surface-3/80" : ""}`}>
                      <button onClick={() => flyToLead(lead)} className="flex-1 min-w-0 text-left cursor-pointer">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="font-mono text-xs text-text-primary truncate flex-1 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: groupColor }} />
                            {lead.isLive && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse flex-shrink-0" />}
                            {lead.company_name}
                          </span>
                          <span className="font-mono text-xs font-bold ml-2" style={{ color: DOT_COLORS[lead.tier] }}>{lead.score}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[12px] text-text-dim truncate">{lead.domain}</span>
                          {lead.country && <span className="font-mono text-[12px] text-text-dim">· {lead.country}</span>}
                          <span className="font-mono text-[12px] ml-auto truncate max-w-[80px]" style={{ color: groupColor }}>{lead.search_label}</span>
                        </div>
                      </button>
                      {!lead.isLive && (lead.tier === "rejected" || lead.tier === "review") && (
                        <button onClick={(e) => deleteLead(lead.id, e)} disabled={deletingLead === lead.id} className="ml-2 text-text-dim/40 hover:text-red-400 transition-colors cursor-pointer flex-shrink-0 disabled:opacity-50" title="Delete lead">
                          {deletingLead === lead.id ? <span className="w-3 h-3 border border-text-dim border-t-transparent rounded-full animate-spin inline-block" /> : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
      </div>

      {/* ═══ Map ═══ */}
      <div className="flex-1 relative">
        {loading && dbLeads.length === 0 && liveLeads.length === 0 ? (
          <MapSkeleton />
        ) : (
          <MapGL ref={mapRef as React.Ref<never>} mapboxAccessToken={MAPBOX_TOKEN} initialViewState={{ longitude: 0, latitude: 20, zoom: 1.5 }} style={{ width: "100%", height: "100%" }} mapStyle={mapStyle} attributionControl={false}>
            <NavigationControl position="top-right" />
            {filtered.map((lead) => {
              const size = dotSize(lead.score);
              const groupColor = groupColorMap.get(lead.search_id);
              const dotColor = DOT_COLORS[lead.tier] || DOT_COLORS.rejected;
              const glow = DOT_GLOW[lead.tier] || DOT_GLOW.rejected;
              return (
                <Marker key={lead.id} longitude={lead.longitude} latitude={lead.latitude} anchor="center" onClick={(e: { originalEvent: MouseEvent }) => { e.originalEvent.stopPropagation(); setSelectedLead(lead); }}>
                  <div className={`rounded-full cursor-pointer transition-transform hover:scale-150 ${lead.isLive ? "animate-ping-once" : ""}`} style={{ width: size, height: size, backgroundColor: dotColor, boxShadow: `0 0 ${size}px ${size / 2}px ${glow}`, border: huntGroups.length > 1 ? `1.5px solid ${groupColor}` : undefined }} />
                </Marker>
              );
            })}

            {selectedLead && (
              <Popup longitude={selectedLead.longitude} latitude={selectedLead.latitude} anchor="bottom" onClose={() => setSelectedLead(null)} closeButton={true} closeOnClick={false} className="lead-popup" maxWidth="340px">
                <div className="bg-surface-2 rounded-lg p-4 min-w-[280px] max-w-[320px] border border-border">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: groupColorMap.get(selectedLead.search_id) }} />
                      <h3 className="font-mono text-xs font-bold text-text-primary truncate">{selectedLead.company_name}</h3>
                    </div>
                    <span className={`font-mono text-[12px] uppercase tracking-[0.1em] px-2 py-0.5 rounded flex-shrink-0 ${TIER_STYLES[selectedLead.tier]?.bg || ""} ${TIER_STYLES[selectedLead.tier]?.color || ""} ${TIER_STYLES[selectedLead.tier]?.border || ""} border`}>
                      {TIER_STYLES[selectedLead.tier]?.label || selectedLead.tier}
                    </span>
                  </div>

                  {/* Domain + Score */}
                  <div className="flex items-center gap-2 mb-2">
                    <a href={selectedLead.website_url || `https://${selectedLead.domain}`} target="_blank" rel="noopener noreferrer" className="font-mono text-[12px] text-secondary/60 hover:text-secondary transition-colors truncate">{selectedLead.domain} ↗</a>
                    <span className="font-mono text-xs font-bold ml-auto" style={{ color: DOT_COLORS[selectedLead.tier] }}>{selectedLead.score}/10</span>
                  </div>

                  {/* Tags */}
                  <div className="flex flex-wrap gap-1 mb-2">
                    {selectedLead.hardware_type && <span className="font-mono text-[12px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.hardware_type}</span>}
                    {selectedLead.industry_category && <span className="font-mono text-[12px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.industry_category}</span>}
                    {selectedLead.country && <span className="font-mono text-[12px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.country}</span>}
                  </div>

                  {/* Reasoning */}
                  {selectedLead.reasoning && (
                    <p className="font-sans text-[12px] text-text-muted leading-relaxed mb-2 line-clamp-3">{selectedLead.reasoning}</p>
                  )}

                  {/* Key signals */}
                  {selectedLead.key_signals && selectedLead.key_signals.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {selectedLead.key_signals.slice(0, 4).map((s, i) => (
                        <span key={i} className="font-mono text-[12px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">{s}</span>
                      ))}
                      {selectedLead.key_signals.length > 4 && <span className="font-mono text-[12px] text-text-dim">+{selectedLead.key_signals.length - 4}</span>}
                    </div>
                  )}

                  {/* Red flags */}
                  {selectedLead.red_flags && selectedLead.red_flags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-2">
                      {selectedLead.red_flags.slice(0, 3).map((f, i) => (
                        <span key={i} className="font-mono text-[12px] text-red-400/60 bg-red-400/5 border border-red-400/10 rounded px-1.5 py-0.5">{f}</span>
                      ))}
                    </div>
                  )}

                  {/* Footer: hunt label + delete */}
                  <div className="flex items-center justify-between border-t border-border-dim pt-2 mt-1">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: groupColorMap.get(selectedLead.search_id) }} />
                      <span className="font-mono text-[12px] text-text-dim truncate max-w-[140px]">{selectedLead.search_label}</span>
                    </div>
                    {!selectedLead.isLive && (
                      <button onClick={(e) => deleteLead(selectedLead.id, e)} disabled={deletingLead === selectedLead.id} className="font-mono text-[12px] text-text-dim hover:text-red-400 transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1">
                        {deletingLead === selectedLead.id ? <span className="w-2.5 h-2.5 border border-text-dim border-t-transparent rounded-full animate-spin inline-block" /> : <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" /></svg>}
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              </Popup>
            )}
          </MapGL>
        )}

        {isPipelineRunning && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-surface-1/90 backdrop-blur-md border border-green-500/30 rounded-full px-4 py-1.5 flex items-center gap-2 z-10">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="font-mono text-[12px] text-green-400">Pipeline running — leads appearing live</span>
          </div>
        )}

        <div className="md:hidden absolute top-3 left-3 right-3 bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 flex items-center gap-3 z-10">
          <span className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`} />
          <span className="font-mono text-[12px] text-text-primary">{filtered.length} leads</span>
          <span className="font-mono text-[12px] text-hot">{tierCounts.hot} hot</span>
          <span className="font-mono text-[12px] text-review">{tierCounts.review} review</span>
          <span className="font-mono text-[12px] text-text-dim ml-auto">{huntGroups.length} hunts</span>
        </div>

        {huntGroups.length > 1 && (
          <div className="hidden md:block absolute bottom-4 left-4 bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 z-10 max-w-[200px]">
            <span className="font-mono text-[12px] text-text-dim uppercase tracking-[0.15em] mb-1.5 block">Hunts</span>
            {huntGroups.filter((g) => !hiddenGroups.has(g.searchId)).map((group) => (
              <div key={group.searchId} className="flex items-center gap-1.5 mb-1 last:mb-0 cursor-pointer hover:opacity-80" onClick={() => flyToGroup(group)}>
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: groupColorMap.get(group.searchId) }} />
                <span className="font-mono text-[12px] text-text-muted truncate">{group.label}</span>
                <span className="font-mono text-[12px] text-text-dim ml-auto">{group.leads.length}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <style jsx global>{`
        .lead-popup .mapboxgl-popup-content { background: transparent !important; padding: 0 !important; box-shadow: none !important; border-radius: 0.75rem; }
        .lead-popup .mapboxgl-popup-tip { border-top-color: #18181b !important; }
        .lead-popup .mapboxgl-popup-close-button { color: #71717a; font-size: 16px; right: 4px; top: 4px; }
        @keyframes ping-once { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(2.5); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
        .animate-ping-once { animation: ping-once 0.6s ease-out; }
        .mapboxgl-ctrl-logo, .mapboxgl-ctrl-attrib, .mapboxgl-ctrl-bottom-left, .mapboxgl-ctrl-bottom-right { display: none !important; }
      `}</style>
    </div>
  );
}
