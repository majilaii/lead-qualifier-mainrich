"use client";

import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import { usePipeline } from "../hunt/PipelineContext";
import MapGL, { Marker, Popup, NavigationControl, Source, Layer } from "react-map-gl/mapbox";
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

type MapRef = {
  flyTo: (opts: { center: [number, number]; zoom: number; duration: number }) => void;
  getMap: () => {
    getBounds: () => {
      getSouthWest: () => { lat: number; lng: number };
      getNorthEast: () => { lat: number; lng: number };
    };
    getCanvas: () => HTMLCanvasElement;
  };
};

export default function LiveMapPanel() {
  const {
    qualifiedCompanies,
    phase,
    mapBounds,
    setMapBounds,
    useMapBounds,
    setUseMapBounds,
    mapViewState,
    setMapViewState,
  } = usePipeline();

  const [selectedLead, setSelectedLead] = useState<GeoLead | null>(null);
  const [viewState, setViewState] = useState(mapViewState ?? {
    longitude: 10,
    latitude: 45,
    zoom: 2.5,
  });
  const mapRef = useRef<MapRef | null>(null);
  const flownToRef = useRef<Set<string>>(new Set());
  const viewSyncTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── Draw-rectangle state ── */
  const [isDrawMode, setIsDrawMode] = useState(false);
  const [drawStart, setDrawStart] = useState<[number, number] | null>(null); // [lng, lat]
  const [drawCurrent, setDrawCurrent] = useState<[number, number] | null>(null); // [lng, lat]
  const isDrawingRef = useRef(false);

  /* ── Follow-leads toggle ── */
  const [followLeads, setFollowLeads] = useState(true);

  /* ── User interaction tracking (suppresses auto-fly) ── */
  const userInteractingRef = useRef(false);
  const interactionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const markUserInteracting = useCallback(() => {
    userInteractingRef.current = true;
    if (interactionTimerRef.current) clearTimeout(interactionTimerRef.current);
    interactionTimerRef.current = setTimeout(() => {
      userInteractingRef.current = false;
    }, 5000);
  }, []);

  /* ── Apply crosshair cursor to the Mapbox canvas element in draw mode ── */
  useEffect(() => {
    const canvas = mapRef.current?.getMap?.()?.getCanvas?.();
    if (!canvas) return;
    if (isDrawMode) {
      canvas.style.cursor = "crosshair";
    } else {
      canvas.style.cursor = "";
    }
    return () => { canvas.style.cursor = ""; };
  }, [isDrawMode]);

  /* ── Quick-fence: lock current viewport as bounds ── */
  const lockViewportBounds = useCallback(() => {
    try {
      const map = mapRef.current?.getMap?.();
      if (!map) return;
      const bounds = map.getBounds();
      const sw = bounds.getSouthWest();
      const ne = bounds.getNorthEast();
      setMapBounds([sw.lat, sw.lng, ne.lat, ne.lng]);
      setUseMapBounds(true);
    } catch {
      // Map not ready yet
    }
  }, [setMapBounds, setUseMapBounds]);

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

  /* ── Auto-fly to new leads (suppressed when fence active or user interacting) ── */
  useEffect(() => {
    if (phase !== "qualifying") return;
    if (!followLeads) return;
    if (useMapBounds) return; // Don't fight the geo-fence
    if (userInteractingRef.current) return;

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
  }, [leads, phase, followLeads, useMapBounds]);

  /* ── Auto-disable follow when fence is activated ── */
  useEffect(() => {
    if (useMapBounds) setFollowLeads(false);
  }, [useMapBounds]);

  const dotSize = (score: number) => Math.max(10, Math.min(18, score / 6));

  const tierCounts = {
    hot: leads.filter((l) => l.tier === "hot").length,
    review: leads.filter((l) => l.tier === "review").length,
    rejected: leads.filter((l) => l.tier === "rejected").length,
  };

  const isPipelineRunning = phase === "qualifying";

  /* ── Draw rectangle helpers ── */
  const drawBoundsRect = useMemo(() => {
    if (!drawStart || !drawCurrent) return null;
    const [lng1, lat1] = drawStart;
    const [lng2, lat2] = drawCurrent;
    const swLat = Math.min(lat1, lat2);
    const swLng = Math.min(lng1, lng2);
    const neLat = Math.max(lat1, lat2);
    const neLng = Math.max(lng1, lng2);
    return {
      type: "Feature" as const,
      properties: {},
      geometry: {
        type: "Polygon" as const,
        coordinates: [[
          [swLng, swLat],
          [neLng, swLat],
          [neLng, neLat],
          [swLng, neLat],
          [swLng, swLat],
        ]],
      },
    };
  }, [drawStart, drawCurrent]);

  const handleMapMouseDown = useCallback(
    (e: { lngLat: { lng: number; lat: number }; originalEvent: MouseEvent }) => {
      if (!isDrawMode) return;
      e.originalEvent.preventDefault();
      const { lng, lat } = e.lngLat;
      setDrawStart([lng, lat]);
      setDrawCurrent([lng, lat]);
      isDrawingRef.current = true;
    },
    [isDrawMode],
  );

  const handleMapMouseMove = useCallback(
    (e: { lngLat: { lng: number; lat: number } }) => {
      if (!isDrawingRef.current) return;
      setDrawCurrent([e.lngLat.lng, e.lngLat.lat]);
    },
    [],
  );

  const handleMapMouseUp = useCallback(() => {
    if (!isDrawingRef.current || !drawStart || !drawCurrent) {
      isDrawingRef.current = false;
      return;
    }
    isDrawingRef.current = false;

    const [lng1, lat1] = drawStart;
    const [lng2, lat2] = drawCurrent;

    // Ignore tiny rectangles (accidental clicks)
    if (Math.abs(lng1 - lng2) < 0.01 && Math.abs(lat1 - lat2) < 0.01) {
      setDrawStart(null);
      setDrawCurrent(null);
      setIsDrawMode(false);
      return;
    }

    const swLat = Math.min(lat1, lat2);
    const swLng = Math.min(lng1, lng2);
    const neLat = Math.max(lat1, lat2);
    const neLng = Math.max(lng1, lng2);

    setMapBounds([swLat, swLng, neLat, neLng]);
    setUseMapBounds(true);
    setDrawStart(null);
    setDrawCurrent(null);
    setIsDrawMode(false);
  }, [drawStart, drawCurrent, setMapBounds, setUseMapBounds]);

  /* ── Draggable corner markers for resizing the fence ── */
  const cornerPositions = useMemo(() => {
    if (!mapBounds) return null;
    const [swLat, swLng, neLat, neLng] = mapBounds;
    return {
      sw: { lat: swLat, lng: swLng },
      se: { lat: swLat, lng: neLng },
      ne: { lat: neLat, lng: neLng },
      nw: { lat: neLat, lng: swLng },
    };
  }, [mapBounds]);

  const handleCornerDrag = useCallback(
    (corner: "sw" | "se" | "ne" | "nw", e: { lngLat: { lng: number; lat: number } }) => {
      if (!mapBounds) return;
      const [swLat, swLng, neLat, neLng] = mapBounds;
      const { lng, lat } = e.lngLat;

      let newBounds: [number, number, number, number];
      switch (corner) {
        case "sw":
          newBounds = [lat, lng, neLat, neLng];
          break;
        case "se":
          newBounds = [lat, swLng, neLat, lng];
          break;
        case "ne":
          newBounds = [swLat, swLng, lat, lng];
          break;
        case "nw":
          newBounds = [swLat, lng, lat, neLng];
          break;
      }
      setMapBounds(newBounds);
    },
    [mapBounds, setMapBounds],
  );

  /* ── Clear fence ── */
  const clearFence = useCallback(() => {
    setUseMapBounds(false);
    setMapBounds(null);
    setFollowLeads(true);
  }, [setUseMapBounds, setMapBounds]);

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
    <div
      className="relative w-full h-full"
      style={{ minHeight: 0, cursor: isDrawMode ? "crosshair" : undefined }}
    >
      <MapGL
        ref={mapRef as React.Ref<never>}
        mapboxAccessToken={MAPBOX_TOKEN}
        {...viewState}
        onMove={(evt: { viewState: typeof viewState }) => {
          setViewState(evt.viewState);
          // Debounce persisting to context so we don't thrash on every frame
          if (viewSyncTimer.current) clearTimeout(viewSyncTimer.current);
          viewSyncTimer.current = setTimeout(() => {
            setMapViewState({
              longitude: evt.viewState.longitude,
              latitude: evt.viewState.latitude,
              zoom: evt.viewState.zoom,
            });
          }, 300);
        }}
        onDragStart={markUserInteracting}
        onZoomStart={markUserInteracting}
        onMouseDown={handleMapMouseDown}
        onMouseMove={handleMapMouseMove}
        onMouseUp={handleMapMouseUp}
        style={{ width: "100%", height: "100%" }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        attributionControl={false}
        dragPan={!isDrawMode}
        dragRotate={!isDrawMode}
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
                className="group cursor-pointer flex items-center justify-center"
                style={{ width: 44, height: 44 }}
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

        {/* ── Live draw preview ── */}
        {drawStart && drawCurrent && drawBoundsRect && (
          <Source id="draw-preview" type="geojson" data={drawBoundsRect}>
            <Layer
              id="draw-preview-fill"
              type="fill"
              paint={{ "fill-color": "#10b981", "fill-opacity": 0.1 }}
            />
            <Layer
              id="draw-preview-line"
              type="line"
              paint={{
                "line-color": "#10b981",
                "line-width": 2,
                "line-dasharray": [4, 2],
                "line-opacity": 0.8,
              }}
            />
          </Source>
        )}

        {/* ── Locked bounding box overlay ── */}
        {useMapBounds && mapBounds && (
          <Source
            id="search-bounds"
            type="geojson"
            data={{
              type: "Feature",
              properties: {},
              geometry: {
                type: "Polygon",
                coordinates: [[
                  [mapBounds[1], mapBounds[0]], // SW
                  [mapBounds[3], mapBounds[0]], // SE
                  [mapBounds[3], mapBounds[2]], // NE
                  [mapBounds[1], mapBounds[2]], // NW
                  [mapBounds[1], mapBounds[0]], // close
                ]],
              },
            }}
          >
            <Layer
              id="search-bounds-fill"
              type="fill"
              paint={{ "fill-color": "#10b981", "fill-opacity": 0.06 }}
            />
            <Layer
              id="search-bounds-line"
              type="line"
              paint={{
                "line-color": "#10b981",
                "line-width": 2,
                "line-dasharray": [3, 2],
                "line-opacity": 0.6,
              }}
            />
          </Source>
        )}

        {/* ── Draggable corner handles ── */}
        {useMapBounds && cornerPositions && (
          <>
            {(["sw", "se", "ne", "nw"] as const).map((corner) => (
              <Marker
                key={corner}
                longitude={cornerPositions[corner].lng}
                latitude={cornerPositions[corner].lat}
                anchor="center"
                draggable
                onDrag={(e: { lngLat: { lng: number; lat: number } }) =>
                  handleCornerDrag(corner, e)
                }
              >
                <div className="w-3 h-3 rounded-full bg-emerald-400 border-2 border-white shadow-lg cursor-move hover:scale-150 transition-transform" />
              </Marker>
            ))}
          </>
        )}

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
                <span className={`font-mono text-[9px] uppercase tracking-[0.1em] px-2 py-0.5 rounded flex-shrink-0 ${TIER_STYLES[selectedLead.tier]?.bg || ""} ${TIER_STYLES[selectedLead.tier]?.color || ""} ${TIER_STYLES[selectedLead.tier]?.border || ""} border`}>
                  {TIER_STYLES[selectedLead.tier]?.label || selectedLead.tier}
                </span>
              </div>

              {/* Domain + Score */}
              <div className="flex items-center gap-2 mb-2">
                <a href={selectedLead.website_url || `https://${selectedLead.domain}`} target="_blank" rel="noopener noreferrer" className="font-mono text-[10px] text-secondary/60 hover:text-secondary transition-colors truncate">{selectedLead.domain} ↗</a>
                <span className="font-mono text-xs font-bold ml-auto" style={{ color: DOT_COLORS[selectedLead.tier] }}>{selectedLead.score}/100</span>
              </div>

              {/* Tags */}
              <div className="flex flex-wrap gap-1 mb-2">
                {selectedLead.hardware_type && <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.hardware_type}</span>}
                {selectedLead.industry_category && <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.industry_category}</span>}
                {selectedLead.country && <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-text-dim bg-surface-3 px-1.5 py-0.5 rounded">{selectedLead.country}</span>}
              </div>

              {/* Reasoning */}
              {selectedLead.reasoning && (
                <p className="font-sans text-[10px] text-text-muted leading-relaxed mb-2 line-clamp-3">{selectedLead.reasoning}</p>
              )}

              {/* Key signals */}
              {selectedLead.key_signals && selectedLead.key_signals.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {selectedLead.key_signals.slice(0, 4).map((s, i) => (
                    <span key={i} className="font-mono text-[8px] text-secondary/50 bg-secondary/5 border border-secondary/10 rounded px-1.5 py-0.5">{s}</span>
                  ))}
                  {selectedLead.key_signals.length > 4 && <span className="font-mono text-[8px] text-text-dim">+{selectedLead.key_signals.length - 4}</span>}
                </div>
              )}

              {/* Red flags */}
              {selectedLead.red_flags && selectedLead.red_flags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {selectedLead.red_flags.slice(0, 3).map((f, i) => (
                    <span key={i} className="font-mono text-[8px] text-red-400/60 bg-red-400/5 border border-red-400/10 rounded px-1.5 py-0.5">{f}</span>
                  ))}
                </div>
              )}
            </div>
          </Popup>
        )}
      </MapGL>

      {/* ══════ Toolbar: top-left ══════ */}
      <div className="absolute top-3 left-3 z-10 flex flex-col gap-2">
        {/* Live stats */}
        <div className="bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-3 py-2 flex items-center gap-3">
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

        {/* Draw + Follow + Quick-fence buttons */}
        <div className="flex items-center gap-1.5">
          {/* Draw rectangle button */}
          <button
            onClick={() => setIsDrawMode((v) => !v)}
            className={`bg-surface-1/90 backdrop-blur-md border rounded-lg px-2.5 py-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors cursor-pointer ${
              isDrawMode
                ? "border-emerald-500/60 text-emerald-400 bg-emerald-500/10"
                : "border-border-dim text-text-muted hover:text-emerald-400 hover:border-emerald-500/40"
            }`}
            title={isDrawMode ? "Cancel draw mode" : "Draw a geo-fence rectangle"}
          >
            {/* Bounding box icon */}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18M3 15h18M9 3v18M15 3v18" opacity="0.3" />
            </svg>
            {isDrawMode ? "Drawing…" : "Draw fence"}
          </button>

          {/* Quick-fence (viewport) */}
          {!useMapBounds && !isDrawMode && (
            <button
              onClick={lockViewportBounds}
              className="bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-lg px-2.5 py-2 flex items-center gap-1.5 font-mono text-[9px] text-text-muted hover:text-emerald-400 hover:border-emerald-500/40 transition-colors cursor-pointer uppercase tracking-[0.1em]"
              title="Lock current viewport as search area"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3">
                <path fillRule="evenodd" d="m7.539 14.841.003.003.002.002a.755.755 0 0 0 .912 0l.002-.002.003-.003.012-.009a5.57 5.57 0 0 0 .19-.153 15.588 15.588 0 0 0 2.046-2.082c1.101-1.362 2.291-3.342 2.291-5.597A5 5 0 0 0 3 7c0 2.255 1.19 4.235 2.291 5.597a15.591 15.591 0 0 0 2.236 2.235l.012.01ZM8 8.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" clipRule="evenodd" />
              </svg>
              This area
            </button>
          )}

          {/* Follow leads toggle */}
          <button
            onClick={() => setFollowLeads((v) => !v)}
            className={`bg-surface-1/90 backdrop-blur-md border rounded-lg px-2.5 py-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors cursor-pointer ${
              followLeads
                ? "border-blue-500/40 text-blue-400"
                : "border-border-dim text-text-dim hover:text-blue-400 hover:border-blue-500/40"
            }`}
            title={followLeads ? "Stop following new leads" : "Auto-follow new leads on map"}
          >
            {/* Crosshair icon */}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="22" y1="12" x2="18" y2="12" />
              <line x1="6" y1="12" x2="2" y2="12" />
              <line x1="12" y1="6" x2="12" y2="2" />
              <line x1="12" y1="22" x2="12" y2="18" />
            </svg>
            {followLeads ? "Following" : "Follow"}
          </button>
        </div>
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

      {/* Draw mode instruction banner — top center */}
      {isDrawMode && !isPipelineRunning && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-surface-1/90 backdrop-blur-md border border-emerald-500/40 rounded-full px-4 py-1.5 flex items-center gap-2 z-10">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-mono text-[10px] text-emerald-400">
            Click &amp; drag to draw a rectangle
          </span>
          <button
            onClick={() => setIsDrawMode(false)}
            className="text-emerald-400/60 hover:text-emerald-300 transition-colors cursor-pointer text-xs ml-1"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Area locked / Clear — bottom center ── */}
      {useMapBounds && mapBounds && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2">
          <div className="bg-surface-1/90 backdrop-blur-md border border-emerald-500/40 rounded-full px-4 py-1.5 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3 h-3 text-emerald-400">
              <path fillRule="evenodd" d="m7.539 14.841.003.003.002.002a.755.755 0 0 0 .912 0l.002-.002.003-.003.012-.009a5.57 5.57 0 0 0 .19-.153 15.588 15.588 0 0 0 2.046-2.082c1.101-1.362 2.291-3.342 2.291-5.597A5 5 0 0 0 3 7c0 2.255 1.19 4.235 2.291 5.597a15.591 15.591 0 0 0 2.236 2.235l.012.01ZM8 8.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" clipRule="evenodd" />
            </svg>
            <span className="font-mono text-[10px] text-emerald-400">
              Area locked
            </span>
          </div>
          <button
            onClick={() => setIsDrawMode(true)}
            className="bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-full px-3 py-1.5 font-mono text-[10px] text-text-dim hover:text-emerald-400 hover:border-emerald-500/40 transition-colors cursor-pointer"
            title="Redraw the fence"
          >
            ✎ Redraw
          </button>
          <button
            onClick={clearFence}
            className="bg-surface-1/90 backdrop-blur-md border border-border-dim rounded-full px-3 py-1.5 font-mono text-[10px] text-text-dim hover:text-text-primary hover:border-text-dim transition-colors cursor-pointer"
          >
            ✕ Clear
          </button>
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
