"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { useHunt } from "../hunt/HuntContext";
import MapGL, { Marker, Popup, NavigationControl } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

interface GeoLead {
  id: string;
  company_name: string;
  domain: string;
  website_url: string;
  score: number;
  tier: string;
  country: string | null;
  latitude: number;
  longitude: number;
  hardware_type: string | null;
  industry_category: string | null;
  reasoning: string | null;
  key_signals: string[];
  red_flags: string[];
  isLive?: boolean;
}

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

export default function LiveMapPanel() {
  const { qualifiedCompanies, phase } = useHunt();
  const [selectedLead, setSelectedLead] = useState<GeoLead | null>(null);
  const mapRef = useRef<{
    flyTo: (opts: {
      center: [number, number];
      zoom: number;
      duration: number;
    }) => void;
  } | null>(null);
  const flownToRef = useRef<Set<string>>(new Set());

  /* ── Convert pipeline leads to map data ── */
  const leads: GeoLead[] = useMemo(() => {
    return qualifiedCompanies
      .filter((c) => c.latitude != null && c.longitude != null)
      .map((c, i) => ({
        id: `live-${i}-${c.domain}`,
        company_name: c.title,
        domain: c.domain,
        website_url: c.url || `https://${c.domain}`,
        score: c.score,
        tier: c.tier,
        country: c.country ?? null,
        latitude: c.latitude!,
        longitude: c.longitude!,
        hardware_type: c.hardware_type || null,
        industry_category: c.industry_category || null,
        reasoning: c.reasoning || null,
        key_signals: c.key_signals || [],
        red_flags: c.red_flags || [],
        isLive: true,
      }));
  }, [qualifiedCompanies]);

  /* ── Auto-fly to new leads ── */
  useEffect(() => {
    if (phase !== "qualifying") return;
    const newLeads = leads.filter((l) => !flownToRef.current.has(l.id));
    if (newLeads.length > 0) {
      const latest = newLeads[newLeads.length - 1];
      newLeads.forEach((l) => flownToRef.current.add(l.id));
      mapRef.current?.flyTo({
        center: [latest.longitude, latest.latitude],
        zoom: 4,
        duration: 1200,
      });
    }
  }, [leads, phase]);

  const dotSize = (score: number) => Math.max(10, Math.min(18, score / 6));

  const tierCounts = {
    hot: leads.filter((l) => l.tier === "hot").length,
    review: leads.filter((l) => l.tier === "review").length,
    rejected: leads.filter((l) => l.tier === "rejected").length,
  };

  const isPipelineRunning = phase === "qualifying";

  if (!MAPBOX_TOKEN) {
    return (
      <div className="flex items-center justify-center h-full bg-surface-1 text-text-dim">
        <div className="text-center px-6">
          <p className="font-mono text-xs mb-1">Map unavailable</p>
          <p className="font-mono text-[12px] text-text-dim/60">
            Set NEXT_PUBLIC_MAPBOX_TOKEN
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <MapGL
        ref={mapRef as React.Ref<never>}
        mapboxAccessToken={MAPBOX_TOKEN}
        initialViewState={{
          longitude: 10,
          latitude: 45,
          zoom: 2.5,
        }}
        style={{ width: "100%", height: "100%" }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        attributionControl={false}
      >
        <NavigationControl position="top-right" showCompass={false} />

        {leads.map((lead) => {
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
              {/* 44px hover zone — dot enlarges when cursor is anywhere nearby */}
              <div
                className="group cursor-pointer flex items-center justify-center"
                style={{
                  width: 44,
                  height: 44,
                }}
              >
                <div
                  className={`rounded-full transition-all duration-150 ease-out group-hover:scale-[2.5] ${lead.isLive ? "animate-ping-once" : ""}`}
                  style={{
                    width: size,
                    height: size,
                    backgroundColor: color,
                    boxShadow: `0 0 ${size}px ${size / 2}px ${glow}`,
                  }}
                />
              </div>
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
            maxWidth="340px"
          >
            <div className="bg-surface-2 rounded-lg p-4 min-w-[280px] max-w-[320px] border border-border">
              {/* Header */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-mono text-xs font-bold text-text-primary truncate flex-1">{selectedLead.company_name}</h3>
                <span className={`font-mono text-[12px] uppercase tracking-[0.1em] px-2 py-0.5 rounded flex-shrink-0 ${TIER_STYLES[selectedLead.tier]?.bg || ""} ${TIER_STYLES[selectedLead.tier]?.color || ""} ${TIER_STYLES[selectedLead.tier]?.border || ""} border`}>
                  {TIER_STYLES[selectedLead.tier]?.label || selectedLead.tier}
                </span>
              </div>

              {/* Domain + Score */}
              <div className="flex items-center gap-2 mb-2">
                <a href={selectedLead.website_url || `https://${selectedLead.domain}`} target="_blank" rel="noopener noreferrer" className="font-mono text-[12px] text-secondary/60 hover:text-secondary transition-colors truncate">{selectedLead.domain} ↗</a>
                <span className="font-mono text-xs font-bold ml-auto" style={{ color: DOT_COLORS[selectedLead.tier] }}>{selectedLead.score}/100</span>
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
            </div>
          </Popup>
        )}
      </MapGL>

      {/* Live stats overlay — top left */}
      <div className="absolute top-3 left-3 bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 flex items-center gap-3 z-10">
        <span
          className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`}
        />
        <span className="font-mono text-[12px] text-text-primary">
          {leads.length} leads
        </span>
        {tierCounts.hot > 0 && (
          <span className="font-mono text-[12px] text-hot">
            {tierCounts.hot} hot
          </span>
        )}
        {tierCounts.review > 0 && (
          <span className="font-mono text-[12px] text-review">
            {tierCounts.review} review
          </span>
        )}
      </div>

      {/* Pipeline banner — top center */}
      {isPipelineRunning && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-surface-1/90 backdrop-blur-md border border-green-500/30 rounded-full px-4 py-1.5 flex items-center gap-2 z-10">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="font-mono text-[12px] text-green-400">
            Leads appearing live
          </span>
        </div>
      )}

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
          0% { transform: scale(1); opacity: 1; }
          50% { transform: scale(2.5); opacity: 0.5; }
          100% { transform: scale(1); opacity: 1; }
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
