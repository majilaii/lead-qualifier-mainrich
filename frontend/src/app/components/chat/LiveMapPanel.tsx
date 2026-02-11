"use client";

import { useEffect, useRef, useMemo, useState } from "react";
import { useHunt } from "../hunt/HuntContext";
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
        score: c.score,
        tier: c.tier,
        country: c.country ?? null,
        latitude: c.latitude!,
        longitude: c.longitude!,
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

  const dotSize = (score: number) => Math.max(6, Math.min(16, score / 6));

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
          <p className="font-mono text-[10px] text-text-dim/60">
            Set NEXT_PUBLIC_MAPBOX_TOKEN
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <Map
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

      {/* Live stats overlay — top left */}
      <div className="absolute top-3 left-3 bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 flex items-center gap-3 z-10">
        <span
          className={`w-2 h-2 rounded-full ${isPipelineRunning ? "bg-green-400 animate-pulse" : "bg-text-dim"}`}
        />
        <span className="font-mono text-[9px] text-text-primary">
          {leads.length} leads
        </span>
        {tierCounts.hot > 0 && (
          <span className="font-mono text-[9px] text-hot">
            {tierCounts.hot} hot
          </span>
        )}
        {tierCounts.review > 0 && (
          <span className="font-mono text-[9px] text-review">
            {tierCounts.review} review
          </span>
        )}
      </div>

      {/* Pipeline banner — top center */}
      {isPipelineRunning && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-surface-1/90 backdrop-blur-md border border-green-500/30 rounded-full px-4 py-1.5 flex items-center gap-2 z-10">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="font-mono text-[10px] text-green-400">
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
