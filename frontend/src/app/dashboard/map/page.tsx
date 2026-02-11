"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { useAuth } from "../../components/auth/SessionProvider";
import { useHunt } from "../../components/hunt/HuntContext";
import Map, { Marker, Popup, NavigationControl } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

interface GeoLead {
  id: string;
  company_name: string;
  domain: string;
  score: number;
  tier: string;
  country: string | null;
  latitude: number;
  longitude: number;
  status: string | null;
  isLive?: boolean;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export default function MapPage() {
  const { session } = useAuth();
  const { qualifiedCompanies, phase } = useHunt();

  const [dbLeads, setDbLeads] = useState<GeoLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLead, setSelectedLead] = useState<GeoLead | null>(null);
  const [tierFilter, setTierFilter] = useState<Set<string>>(
    new Set(["hot", "review", "rejected"])
  );
  const [searchQuery, setSearchQuery] = useState("");
  const mapRef = useRef<{ flyTo: (opts: { center: [number, number]; zoom: number; duration: number }) => void } | null>(null);
  const flownToRef = useRef<Set<string>>(new Set());

  /* ── Fetch historical leads from DB ──────── */

  const fetchLeads = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch(`${API}/api/leads/geo`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setDbLeads(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  /* ── Merge live pipeline leads + DB leads ── */

  const liveLeads: GeoLead[] = useMemo(() => {
    return qualifiedCompanies
      .filter((c) => c.latitude != null && c.longitude != null)
      .map((c, i) => ({
        id: `live-${i}-${c.domain}`,
        company_name: c.title,
        domain: c.domain,
        score: c.score,
        tier: c.tier,
        country: c.country ?? null,
        latitude: c.latitude!,
        longitude: c.longitude!,
        status: null,
        isLive: true,
      }));
  }, [qualifiedCompanies]);

  const allLeads = useMemo(() => {
    const liveDomains = new Set(liveLeads.map((l) => l.domain));
    const historical = dbLeads.filter((l) => !liveDomains.has(l.domain));
    return [...liveLeads, ...historical];
  }, [liveLeads, dbLeads]);

  /* ── Fly to new lead when it arrives during pipeline ── */

  useEffect(() => {
    if (phase !== "qualifying" && phase !== "complete") return;
    const newLive = liveLeads.filter((l) => !flownToRef.current.has(l.id));
    if (newLive.length > 0) {
      const latest = newLive[newLive.length - 1];
      newLive.forEach((l) => flownToRef.current.add(l.id));
      if (phase === "qualifying") {
        mapRef.current?.flyTo({
          center: [latest.longitude, latest.latitude],
          zoom: 4,
          duration: 1200,
        });
      }
    }
  }, [liveLeads, phase]);

  const toggleTier = (tier: string) => {
    setTierFilter((prev) => {
      const next = new Set(prev);
      if (next.has(tier)) next.delete(tier);
      else next.add(tier);
      return next;
    });
  };

  const filtered = allLeads.filter((l) => {
    if (!tierFilter.has(l.tier)) return false;
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      l.company_name.toLowerCase().includes(q) ||
      l.domain.toLowerCase().includes(q) ||
      (l.country || "").toLowerCase().includes(q)
    );
  });

  const flyToLead = (lead: GeoLead) => {
    setSelectedLead(lead);
    mapRef.current?.flyTo({
      center: [lead.longitude, lead.latitude],
      zoom: 8,
      duration: 1500,
    });
  };

  const tierCounts = {
    hot: allLeads.filter((l) => l.tier === "hot").length,
    review: allLeads.filter((l) => l.tier === "review").length,
    rejected: allLeads.filter((l) => l.tier === "rejected").length,
  };

  // Compute dot size based on score (6-16px)
  const dotSize = (score: number) => Math.max(6, Math.min(16, score / 6));

  // Mapbox dark style (requires token)
  const mapStyle = "mapbox://styles/mapbox/dark-v11";

  const isPipelineRunning = phase === "qualifying";

  return (
    <div className="flex h-full">
      {/* Left panel — lead list */}
      <div className="hidden md:flex flex-col w-80 border-r border-border-dim bg-surface-1/50">
        {/* Stats bar */}
        <div className="px-4 py-3 border-b border-border-dim bg-surface-2/50">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`} />
            <span className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em]">
              {isPipelineRunning ? "Live Pipeline" : "Lead Map"}
            </span>
            <span className="font-mono text-[10px] text-text-primary ml-auto">
              {allLeads.length} leads
            </span>
          </div>
          <div className="flex items-center gap-3 font-mono text-[10px]">
            <span className="text-hot">{tierCounts.hot} hot</span>
            <span className="text-review">{tierCounts.review} review</span>
            <span className="text-text-dim">{tierCounts.rejected} rejected</span>
          </div>
        </div>

        {/* Filters */}
        <div className="px-4 py-3 border-b border-border-dim space-y-2">
          {/* Tier toggles */}
          <div className="flex gap-1.5">
            {(["hot", "review", "rejected"] as const).map((tier) => (
              <button
                key={tier}
                onClick={() => toggleTier(tier)}
                className={`font-mono text-[9px] px-2.5 py-1 rounded-md border uppercase tracking-[0.1em] transition-all cursor-pointer ${
                  tierFilter.has(tier)
                    ? tier === "hot"
                      ? "bg-hot/10 border-hot/20 text-hot"
                      : tier === "review"
                        ? "bg-review/10 border-review/20 text-review"
                        : "bg-text-dim/10 border-text-dim/20 text-text-dim"
                    : "border-border text-text-dim/50"
                }`}
              >
                {tier}
              </button>
            ))}
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-1.5 font-mono text-[10px] text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/30 transition-colors"
          />
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto divide-y divide-border-dim">
          {filtered.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <p className="font-mono text-[10px] text-text-dim">
                {isPipelineRunning
                  ? "Waiting for qualified leads…"
                  : "No leads with coordinates yet"}
              </p>
              {!isPipelineRunning && (
                <p className="font-mono text-[9px] text-text-dim/60 mt-1">
                  Run a hunt to see leads on the map
                </p>
              )}
            </div>
          ) : (
            filtered.map((lead) => (
              <button
                key={lead.id}
                onClick={() => flyToLead(lead)}
                className={`w-full text-left px-4 py-3 hover:bg-surface-3/50 transition-colors cursor-pointer ${
                  selectedLead?.id === lead.id ? "bg-surface-3/80" : ""
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="font-mono text-xs text-text-primary truncate flex-1 flex items-center gap-1.5">
                    {lead.isLive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse flex-shrink-0" />
                    )}
                    {lead.company_name}
                  </span>
                  <span
                    className="font-mono text-xs font-bold ml-2"
                    style={{ color: DOT_COLORS[lead.tier] }}
                  >
                    {lead.score}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[9px] text-text-dim truncate">
                    {lead.domain}
                  </span>
                  {lead.country && (
                    <span className="font-mono text-[9px] text-text-dim">
                      · {lead.country}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        {loading && dbLeads.length === 0 && liveLeads.length === 0 ? (
          <div className="flex items-center justify-center h-full bg-surface-1">
            <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
          </div>
        ) : (
          <Map
            ref={mapRef as React.Ref<never>}
            mapboxAccessToken={MAPBOX_TOKEN}
            initialViewState={{
              longitude: 0,
              latitude: 20,
              zoom: 1.5,
            }}
            style={{ width: "100%", height: "100%" }}
            mapStyle={mapStyle}
            attributionControl={false}
          >
            <NavigationControl position="top-right" />

            {filtered.map((lead) => {
              const size = dotSize(lead.score);
              const color = DOT_COLORS[lead.tier] || DOT_COLORS.rejected;
              const glow = DOT_GLOW[lead.tier] || DOT_GLOW.rejected;

              return (
                <Marker
                  key={lead.id}
                  longitude={lead.longitude}
                  latitude={lead.latitude}
                  anchor="center"
                  onClick={(e: { originalEvent: MouseEvent }) => {
                    e.originalEvent.stopPropagation();
                    setSelectedLead(lead);
                  }}
                >
                  <div
                    className={`rounded-full cursor-pointer transition-transform hover:scale-150 ${lead.isLive ? "animate-ping-once" : ""}`}
                    style={{
                      width: size,
                      height: size,
                      backgroundColor: color,
                      boxShadow: `0 0 ${size}px ${size / 2}px ${glow}`,
                    }}
                  />
                </Marker>
              );
            })}

            {selectedLead && (
              <Popup
                longitude={selectedLead.longitude}
                latitude={selectedLead.latitude}
                anchor="bottom"
                onClose={() => setSelectedLead(null)}
                closeButton={true}
                closeOnClick={false}
                className="lead-popup"
              >
                <div className="bg-surface-2 rounded-lg p-3 min-w-[180px] border border-border">
                  <h3 className="font-mono text-xs font-bold text-text-primary mb-1">
                    {selectedLead.company_name}
                  </h3>
                  <p className="font-mono text-[10px] text-text-muted mb-2">
                    {selectedLead.domain}
                  </p>
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    <span
                      style={{ color: DOT_COLORS[selectedLead.tier] }}
                      className="font-bold"
                    >
                      Score: {selectedLead.score}
                    </span>
                    {selectedLead.country && (
                      <span className="text-text-dim">
                        · {selectedLead.country}
                      </span>
                    )}
                  </div>
                </div>
              </Popup>
            )}
          </Map>
        )}

        {/* Pipeline live banner */}
        {isPipelineRunning && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-surface-1/90 backdrop-blur-md border border-green-500/30 rounded-full px-4 py-1.5 flex items-center gap-2 z-10">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="font-mono text-[10px] text-green-400">
              Pipeline running — leads appearing live
            </span>
          </div>
        )}

        {/* Mobile stats overlay */}
        <div className="md:hidden absolute top-3 left-3 right-3 bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 flex items-center gap-3 z-10">
          <span className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`} />
          <span className="font-mono text-[9px] text-text-primary">
            {allLeads.length} leads
          </span>
          <span className="font-mono text-[9px] text-hot">
            {tierCounts.hot} hot
          </span>
          <span className="font-mono text-[9px] text-review">
            {tierCounts.review} review
          </span>
        </div>
      </div>

      <style jsx global>{`
        .lead-popup .mapboxgl-popup-content {
          background: transparent !important;
          padding: 0 !important;
          box-shadow: none !important;
          border-radius: 0.75rem;
        }
        .lead-popup .mapboxgl-popup-tip {
          border-top-color: #18181b !important;
        }
        .lead-popup .mapboxgl-popup-close-button {
          color: #71717a;
          font-size: 16px;
          right: 4px;
          top: 4px;
        }
        @keyframes ping-once {
          0% {
            transform: scale(1);
            opacity: 1;
          }
          50% {
            transform: scale(2.5);
            opacity: 0.5;
          }
          100% {
            transform: scale(1);
            opacity: 1;
          }
        }
        .animate-ping-once {
          animation: ping-once 0.6s ease-out;
        }
        .mapboxgl-ctrl-logo,
        .mapboxgl-ctrl-attrib,
        .mapboxgl-ctrl-bottom-left,
        .mapboxgl-ctrl-bottom-right {
          display: none !important;
        }
      `}</style>
    </div>
  );
}
