"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from "react";
import { useAuth } from "../auth/SessionProvider";

/* ══════════════════════════════════════════════
   Shared types (also re-exported for consumers)
   ══════════════════════════════════════════════ */

export interface ExtractedContext {
  industry: string | null;
  companyProfile: string | null;
  technologyFocus: string | null;
  qualifyingCriteria: string | null;
  disqualifiers: string | null;
  geographicRegion: string | null;
  countryCode: string | null;
}

export interface SearchCompany {
  url: string;
  domain: string;
  title: string;
  snippet: string;
  score: number | null;
  source_query?: string;
}

export interface QualifiedCompany {
  title: string;
  domain: string;
  url: string;
  score: number;
  tier: "hot" | "review" | "rejected";
  hardware_type?: string | null;
  industry_category?: string | null;
  reasoning: string;
  key_signals: string[];
  red_flags: string[];
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface PipelineProgress {
  index: number;
  total: number;
  phase: "crawling" | "qualifying";
  company: string;
}

export interface PipelineSummary {
  hot: number;
  review: number;
  rejected: number;
  failed: number;
}

export interface EnrichedContact {
  domain: string;
  title: string;
  url: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  source: string | null;
  found: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface Readiness {
  industry: boolean;
  companyProfile: boolean;
  technologyFocus: boolean;
  qualifyingCriteria: boolean;
  isReady: boolean;
}

export const INITIAL_READINESS: Readiness = {
  industry: false,
  companyProfile: false,
  technologyFocus: false,
  qualifyingCriteria: false,
  isReady: false,
};

export type Phase =
  | "chat"
  | "searching"
  | "search-complete"
  | "qualifying"
  | "complete";

/* ══════════════════════════════════════════════
   Context value shape
   ══════════════════════════════════════════════ */

interface HuntContextValue {
  /* ── Chat state (persists across navigation) ── */
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  readiness: Readiness;
  setReadiness: React.Dispatch<React.SetStateAction<Readiness>>;

  /* ── Pipeline state ── */
  phase: Phase;
  searchCompanies: SearchCompany[];
  allSearchCompanies: SearchCompany[];
  qualifiedCompanies: QualifiedCompany[];
  pipelineProgress: PipelineProgress | null;
  pipelineSummary: PipelineSummary | null;
  pipelineStartTime: number;
  extractedContext: ExtractedContext | null;
  enrichedContacts: Map<string, EnrichedContact>;
  enrichDone: boolean;

  /* ── Setters (exposed so ChatInterface can still drive them) ── */
  setPhase: (p: Phase) => void;
  setSearchCompanies: React.Dispatch<React.SetStateAction<SearchCompany[]>>;
  setAllSearchCompanies: React.Dispatch<React.SetStateAction<SearchCompany[]>>;
  setQualifiedCompanies: React.Dispatch<React.SetStateAction<QualifiedCompany[]>>;
  setPipelineProgress: React.Dispatch<React.SetStateAction<PipelineProgress | null>>;
  setPipelineSummary: React.Dispatch<React.SetStateAction<PipelineSummary | null>>;
  setPipelineStartTime: React.Dispatch<React.SetStateAction<number>>;
  setExtractedContext: React.Dispatch<React.SetStateAction<ExtractedContext | null>>;
  setEnrichedContacts: React.Dispatch<React.SetStateAction<Map<string, EnrichedContact>>>;
  setEnrichDone: React.Dispatch<React.SetStateAction<boolean>>;

  /* ── Actions ── */
  launchSearch: (ctx: ExtractedContext) => Promise<void>;
  launchPipeline: (batch: SearchCompany[], previousResults: QualifiedCompany[], ctx: ExtractedContext | null) => Promise<void>;
  resetHunt: () => void;
  /** Load a saved search (with messages + leads) back into context */
  resumeHunt: (searchId: string) => Promise<void>;

  /** The DB search ID (set after pipeline saves to DB) */
  searchId: string | null;

  /** True while an SSE pipeline stream is active */
  isPipelineRunning: boolean;
}

const HuntContext = createContext<HuntContextValue | null>(null);

export function useHunt() {
  const ctx = useContext(HuntContext);
  if (!ctx) throw new Error("useHunt must be used inside <HuntProvider>");
  return ctx;
}

/* ══════════════════════════════════════════════
   Provider — lives in root layout, survives navigation
   ══════════════════════════════════════════════ */

export function HuntProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();

  /* ══════════════════════════════════════════════
     Session-storage hydration helpers
     ══════════════════════════════════════════════ */
  const STORAGE_KEY = "hunt_state";

  // Ref to hold deserialized sessionStorage snapshot (populated by hydration effect)
  const saved = useRef<Record<string, unknown> | null>(null);
  // Track whether we've already attempted a recovery this session
  const recoveryAttempted = useRef(false);
  // Track whether client-side hydration from sessionStorage is done
  const [isHydrated, setIsHydrated] = useState(false);

  /* ── State (defaults only — hydrated from sessionStorage via useEffect to avoid SSR mismatch) ── */
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [readiness, setReadiness] = useState<Readiness>(INITIAL_READINESS);
  const [phase, setPhase] = useState<Phase>("chat");
  const [searchCompanies, setSearchCompanies] = useState<SearchCompany[]>([]);
  const [allSearchCompanies, setAllSearchCompanies] = useState<SearchCompany[]>([]);
  const [qualifiedCompanies, setQualifiedCompanies] = useState<QualifiedCompany[]>([]);
  const [pipelineProgress, setPipelineProgress] = useState<PipelineProgress | null>(null);
  const [pipelineSummary, setPipelineSummary] = useState<PipelineSummary | null>(null);
  const [pipelineStartTime, setPipelineStartTime] = useState<number>(0);
  const [extractedContext, setExtractedContext] = useState<ExtractedContext | null>(null);
  const [enrichedContacts, setEnrichedContacts] = useState<Map<string, EnrichedContact>>(new Map());
  const [enrichDone, setEnrichDone] = useState(false);
  const [isPipelineRunning, setIsPipelineRunning] = useState(false);
  const [searchId, setSearchId] = useState<string | null>(null);

  // Abort controller for in-flight SSE so we can cancel on reset
  const abortRef = useRef<AbortController | null>(null);

  // Keep a ref to current messages so the pipeline closure can read them
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  /* ══════════════════════════════════════════════
     Hydrate from sessionStorage (client-only, runs once after mount)
     Avoids SSR mismatch by keeping useState defaults on first render.
     ══════════════════════════════════════════════ */
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const s = JSON.parse(raw);
        saved.current = s;
        if (s.messages?.length) setMessages(s.messages);
        if (s.readiness) setReadiness(s.readiness);
        if (s.phase) setPhase(s.phase);
        if (s.searchCompanies?.length) setSearchCompanies(s.searchCompanies);
        if (s.allSearchCompanies?.length) setAllSearchCompanies(s.allSearchCompanies);
        if (s.qualifiedCompanies?.length) setQualifiedCompanies(s.qualifiedCompanies);
        if (s.pipelineSummary) setPipelineSummary(s.pipelineSummary);
        if (s.extractedContext) setExtractedContext(s.extractedContext);
        if (s.searchId) setSearchId(s.searchId);
        if (s.pipelineStartTime) setPipelineStartTime(s.pipelineStartTime);
      }
    } catch { /* ignore */ }
    setIsHydrated(true);
  }, []);

  /* ══════════════════════════════════════════════
     Persist state to sessionStorage on every change
     ══════════════════════════════════════════════ */
  useEffect(() => {
    // Don't persist until client-side hydration is done (avoids overwriting saved state with defaults)
    if (!isHydrated) return;
    // Don't persist the initial empty "chat" state (avoids overwriting real saved state before recovery runs)
    if (phase === "chat" && messages.length === 0 && !searchId) return;
    try {
      // If we're mid-Exa-search, persist as "chat" — the search is a single request
      // that can't be resumed, so on refresh we drop back to the ready-to-search state.
      let persistPhase: Phase = phase;
      if (isPipelineRunning) persistPhase = "qualifying";
      else if (phase === "searching") persistPhase = readiness.isReady ? "chat" : "chat";

      const snapshot = {
        messages,
        readiness,
        phase: persistPhase,
        searchCompanies,
        allSearchCompanies,
        qualifiedCompanies,
        pipelineSummary,
        extractedContext,
        searchId,
        pipelineStartTime: isPipelineRunning ? pipelineStartTime : 0,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      /* storage full — ignore */
    }
  }, [
    isHydrated, messages, readiness, phase, searchCompanies, allSearchCompanies,
    qualifiedCompanies, pipelineSummary, extractedContext, searchId,
    isPipelineRunning, pipelineStartTime,
  ]);

  /* ══════════════════════════════════════════════
     Shared SSE stream consumer — used by both launchPipeline and recovery.
     Connects to GET /api/proxy/pipeline/{searchId}/stream, reads events,
     and updates React state.  Supports reconnection via ?after=N.
     ══════════════════════════════════════════════ */
  const eventCountRef = useRef(0); // how many SSE events we've consumed (for reconnect offset)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Helper: map DB lead rows → QualifiedCompany[] */
  const mapLeadsToQualified = (leads: Record<string, unknown>[]): QualifiedCompany[] =>
    leads.map((l) => ({
      title: l.company_name as string,
      domain: l.domain as string,
      url: l.website_url as string,
      score: l.score as number,
      tier: l.tier as "hot" | "review" | "rejected",
      hardware_type: (l.hardware_type as string) ?? null,
      industry_category: (l.industry_category as string) ?? null,
      reasoning: (l.reasoning as string) || "",
      key_signals: (l.key_signals as string[]) || [],
      red_flags: (l.red_flags as string[]) || [],
      country: (l.country as string) ?? null,
      latitude: (l.latitude as number) ?? null,
      longitude: (l.longitude as number) ?? null,
    }));

  /** Helper: build PipelineSummary from qualified companies */
  const buildSummary = (qualified: QualifiedCompany[]): PipelineSummary => {
    const summary: PipelineSummary = { hot: 0, review: 0, rejected: 0, failed: 0 };
    for (const c of qualified) {
      if (c.tier in summary) summary[c.tier as keyof PipelineSummary] += 1;
    }
    return summary;
  };

  /**
   * Polling fallback — when SSE stream fails, poll /status every 4s.
   * When the pipeline completes, loads final results from DB.
   */
  const startPolling = useCallback(
    (pipelineSearchId: string, token: string) => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }

      console.log("[Poll] Starting status polling for %s", pipelineSearchId);
      let inflight = false;

      const poll = async () => {
        if (inflight) return;
        inflight = true;
        try {
          const res = await fetch(`/api/proxy/pipeline/${pipelineSearchId}/status`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return; // keep polling

          const data = await res.json();
          console.log("[Poll] %s — %d/%d", data.status, data.processed ?? 0, data.total ?? 0);

          if (data.status === "running") {
            if (data.total > 0) {
              setPipelineProgress({
                index: data.processed || 0,
                total: data.total,
                phase: "qualifying",
                company: "",
              });
            }
            return; // keep polling
          }

          // Pipeline done (complete / error / not_found) — stop polling, load from DB
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }

          try {
            const searchRes = await fetch(`/api/proxy/searches/${pipelineSearchId}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (searchRes.ok) {
              const searchData = await searchRes.json();
              const leads = searchData.leads || [];
              const qualified = mapLeadsToQualified(leads);
              setQualifiedCompanies(qualified);
              setPipelineSummary(buildSummary(qualified));
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: "assistant" as const,
                  content: `⚡ **Pipeline complete** — found **${qualified.length}** leads.`,
                  timestamp: Date.now(),
                },
              ]);
            } else {
              setPipelineSummary((prev) => prev || { hot: 0, review: 0, rejected: 0, failed: 0 });
            }
          } catch (dbErr) {
            console.error("[Poll] Failed to load from DB:", dbErr);
            setPipelineSummary((prev) => prev || { hot: 0, review: 0, rejected: 0, failed: 0 });
          }

          setPipelineProgress(null);
          setPhase("complete");
          setIsPipelineRunning(false);
        } catch (err) {
          console.error("[Poll] Error:", err);
        } finally {
          inflight = false;
        }
      };

      poll();
      pollIntervalRef.current = setInterval(poll, 4000);
    },
    [],
  );

  const connectToStream = useCallback(
    (pipelineSearchId: string, token: string) => {
      console.log("[SSE] connectToStream called for %s, after=%d", pipelineSearchId, eventCountRef.current);
      // Abort any prior stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      (async () => {
        let streamCompleted = false;
        try {
          const after = eventCountRef.current;
          const res = await fetch(
            `/api/proxy/pipeline/${pipelineSearchId}/stream?after=${after}`,
            {
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            },
          );
          console.log("[SSE] Stream response: status=%d, content-type=%s", res.status, res.headers.get("content-type"));

          if (!res.ok || !res.body) {
            // Stream endpoint failed — fall back to polling instead of giving up
            console.warn("[SSE] Stream unavailable (status=%d), falling back to polling", res.status);
            startPolling(pipelineSearchId, token);
            return;
          }

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n\n");
            buffer = parts.pop() || "";

            for (const part of parts) {
              const match = part.match(/^data:\s*(.*)/);
              if (!match) continue;

              try {
                const event = JSON.parse(match[1]);
                eventCountRef.current += 1;

                if (event.type === "progress") {
                  setPipelineProgress({
                    index: event.index,
                    total: event.total,
                    phase: event.phase,
                    company: event.company?.title || event.company?.domain || "",
                  });
                } else if (event.type === "result") {
                  setPipelineProgress(null);
                  setQualifiedCompanies((prev) => {
                    // Deduplicate by domain (replay can re-send already-seen results)
                    const domain = event.company?.domain;
                    if (domain && prev.some((c) => c.domain === domain)) return prev;
                    return [...prev, event.company];
                  });
                } else if (event.type === "error" && event.fatal) {
                  throw new Error(event.error);
                } else if (event.type === "complete") {
                  setPipelineProgress(null);
                  if (event.search_id) setSearchId(event.search_id);
                  setPipelineSummary((prev) => {
                    if (!prev) return event.summary;
                    return {
                      hot: prev.hot + (event.summary?.hot || 0),
                      review: prev.review + (event.summary?.review || 0),
                      rejected: prev.rejected + (event.summary?.rejected || 0),
                      failed: prev.failed + (event.summary?.failed || 0),
                    };
                  });
                  setPhase("complete");
                  streamCompleted = true;
                }
              } catch (parseErr) {
                if (parseErr instanceof Error && parseErr.message) throw parseErr;
              }
            }
          }

          if (!streamCompleted) {
            // Stream ended without "complete" event — connection dropped
            console.warn("[SSE] Stream ended without complete event, falling back to polling");
            startPolling(pipelineSearchId, token);
            return;
          }
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          console.error("[SSE] Stream error:", err);
          // Fall back to polling instead of giving up
          startPolling(pipelineSearchId, token);
          return;
        } finally {
          if (abortRef.current === controller) abortRef.current = null;
          // Only mark pipeline as done if stream delivered the "complete" event
          if (streamCompleted) {
            setIsPipelineRunning(false);
          }
        }
      })();
    },
    [startPolling],
  );

  /* ══════════════════════════════════════════════
     Recover interrupted pipeline on mount
     ══════════════════════════════════════════════ */
  useEffect(() => {
    // Wait for client-side sessionStorage hydration before attempting recovery
    if (!isHydrated) {
      console.log("[HuntRecovery] Waiting for hydration...");
      return;
    }
    if (recoveryAttempted.current) return;

    const s = saved.current;
    if (!s) {
      console.log("[HuntRecovery] No saved state found");
      recoveryAttempted.current = true;
      return;
    }

    const savedPhase = s.phase as Phase | undefined;
    const savedSearchId = s.searchId as string | undefined;
    console.log("[HuntRecovery] savedPhase=%s, savedSearchId=%s, hasAuth=%s", savedPhase, savedSearchId, !!session?.access_token);

    // If pipeline was mid-run but auth isn't ready yet, wait (don't mark as attempted)
    if (savedPhase === "qualifying" && savedSearchId && !session?.access_token) {
      console.log("[HuntRecovery] Waiting for auth...");
      return;
    }

    // All conditions checked — mark as attempted
    recoveryAttempted.current = true;

    // If pipeline was mid-run when the user refreshed, try to reconnect to the live stream
    if (savedPhase === "qualifying" && savedSearchId && session?.access_token) {
      console.log("[HuntRecovery] Attempting pipeline recovery for %s", savedSearchId);
      setIsPipelineRunning(true);

      const token = session.access_token;

      (async () => {
        try {
          // Step 1: Check if backend still has this pipeline
          const statusRes = await fetch(`/api/proxy/pipeline/${savedSearchId}/status`, {
            headers: { Authorization: `Bearer ${token}` },
          });

          if (!statusRes.ok) {
            // Backend unreachable or auth issue — start polling (it will keep retrying)
            console.warn("[HuntRecovery] Status check failed (HTTP %d), falling back to polling", statusRes.status);
            startPolling(savedSearchId, token);
            return;
          }

          const statusData = await statusRes.json();
          console.log("[HuntRecovery] Pipeline status:", statusData);

          if (statusData.status === "running") {
            // Pipeline still running — try SSE stream (connectToStream falls back to polling on failure)
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                role: "assistant" as const,
                content: `⚡ **Reconnected** — the pipeline is still running on the server. Catching up on progress...`,
                timestamp: Date.now(),
              },
            ]);
            connectToStream(savedSearchId, token);

          } else if (statusData.status === "complete" || statusData.status === "error") {
            // Pipeline finished — load final results from DB
            const res = await fetch(`/api/proxy/searches/${savedSearchId}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
              const data = await res.json();
              const qualified = mapLeadsToQualified(data.leads || []);
              setQualifiedCompanies(qualified);
              setPipelineSummary(buildSummary(qualified));
              setMessages((prev) => [
                ...prev,
                {
                  id: crypto.randomUUID(),
                  role: "assistant" as const,
                  content: `⚡ **Pipeline recovered** — loaded **${qualified.length}** leads from the completed run.`,
                  timestamp: Date.now(),
                },
              ]);
            } else {
              // DB load failed — show what we have from sessionStorage
              setPipelineSummary((prev) => prev || { hot: 0, review: 0, rejected: 0, failed: 0 });
            }
            setPhase("complete");
            setIsPipelineRunning(false);

          } else {
            // status === "not_found" — pipeline no longer in backend memory
            // Try DB first; if no leads yet, start polling as last resort
            console.log("[HuntRecovery] Pipeline not in backend memory, checking DB...");
            const res = await fetch(`/api/proxy/searches/${savedSearchId}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
              const data = await res.json();
              const qualified = mapLeadsToQualified(data.leads || []);
              if (qualified.length > 0) {
                setQualifiedCompanies(qualified);
                setPipelineSummary(buildSummary(qualified));
                setPhase("complete");
                setIsPipelineRunning(false);
                setMessages((prev) => [
                  ...prev,
                  {
                    id: crypto.randomUUID(),
                    role: "assistant" as const,
                    content: `⚡ **Pipeline recovered** — loaded **${qualified.length}** leads from the completed run.`,
                    timestamp: Date.now(),
                  },
                ]);
                return;
              }
            }
            // Nothing in DB — pipeline might still be running (backend restarted?)
            // Start polling; it will eventually load from DB when leads appear
            console.log("[HuntRecovery] No leads in DB yet, starting polling fallback");
            startPolling(savedSearchId, token);
          }
        } catch (err) {
          console.error("[HuntRecovery] Failed:", err);
          // Last resort — poll until we get something
          if (savedSearchId && session?.access_token) {
            startPolling(savedSearchId, session.access_token);
          } else {
            setIsPipelineRunning(false);
          }
        }
      })();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, connectToStream, startPolling, isHydrated]);

  /* ── Reset ── */
  const resetHunt = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setMessages([]);
    setReadiness(INITIAL_READINESS);
    setPhase("chat");
    setSearchCompanies([]);
    setAllSearchCompanies([]);
    setQualifiedCompanies([]);
    setPipelineProgress(null);
    setPipelineSummary(null);
    setPipelineStartTime(0);
    setExtractedContext(null);
    setEnrichedContacts(new Map());
    setEnrichDone(false);
    setIsPipelineRunning(false);
    setSearchId(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, []);

  /* ── Launch search ── */
  const launchSearch = useCallback(
    async (ctx: ExtractedContext) => {
      setExtractedContext(ctx);
      setPhase("searching");

      try {
        const response = await fetch("/api/chat/search", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(session?.access_token
              ? { Authorization: `Bearer ${session.access_token}` }
              : {}),
          },
          body: JSON.stringify({
            industry: ctx.industry || "",
            technology_focus: ctx.technologyFocus || "",
            qualifying_criteria: ctx.qualifyingCriteria || "",
            company_profile: ctx.companyProfile || undefined,
            disqualifiers: ctx.disqualifiers || undefined,
            geographic_region: ctx.geographicRegion || undefined,
            country_code: ctx.countryCode || undefined,
          }),
        });

        if (!response.ok) {
          if (response.status === 429) {
            const err = await response.json();
            // Dispatch custom event for quota exceeded
            window.dispatchEvent(new CustomEvent("hunt:quota_exceeded", { detail: err }));
            setPhase("chat");
            return;
          }
          throw new Error("Search failed");
        }
        const data = await response.json();

        setSearchCompanies(data.companies || []);
        setAllSearchCompanies(data.companies || []);
        setPhase("search-complete");
      } catch (err) {
        console.error("Search error:", err);
        setPhase("chat");
        throw err; // let caller handle messaging
      }
    },
    [session],
  );

  /* ── Launch pipeline (background task + SSE stream) ── */
  const launchPipeline = useCallback(
    async (
      batch: SearchCompany[],
      previousResults: QualifiedCompany[],
      ctx: ExtractedContext | null,
    ) => {
      // Abort any prior stream
      abortRef.current?.abort();

      setSearchCompanies(batch);
      setPhase("qualifying");
      setQualifiedCompanies(previousResults);
      setPipelineProgress(null);
      setPipelineSummary(null);
      setPipelineStartTime(Date.now());
      setIsPipelineRunning(true);
      eventCountRef.current = 0;

      // Step 1: POST to start the background pipeline — returns { search_id }
      const response = await fetch("/api/pipeline/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.access_token
            ? { Authorization: `Bearer ${session.access_token}` }
            : {}),
        },
        body: JSON.stringify({
          companies: batch.map((c) => ({
            url: c.url,
            domain: c.domain,
            title: c.title,
            score: c.score,
          })),
          use_vision: true,
          search_context: ctx
            ? {
                industry: ctx.industry || undefined,
                company_profile: ctx.companyProfile || undefined,
                technology_focus: ctx.technologyFocus || undefined,
                qualifying_criteria: ctx.qualifyingCriteria || undefined,
                disqualifiers: ctx.disqualifiers || undefined,
                geographic_region: ctx.geographicRegion || undefined,
              }
            : undefined,
          messages: messagesRef.current.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!response.ok) {
        if (response.status === 429) {
          const err = await response.json();
          window.dispatchEvent(new CustomEvent("hunt:quota_exceeded", { detail: err }));
          setPhase("search-complete");
          setIsPipelineRunning(false);
          return;
        }
        setIsPipelineRunning(false);
        throw new Error("Pipeline start failed");
      }

      const { search_id: newSearchId } = await response.json();
      setSearchId(newSearchId);

      // Write searchId directly to sessionStorage so it survives a refresh
      // even before the React persist effect gets a chance to run
      try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        if (raw) {
          const s = JSON.parse(raw);
          s.searchId = newSearchId;
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
        }
      } catch { /* ignore */ }

      // Step 2: Connect to the SSE stream for live results
      connectToStream(newSearchId, session?.access_token || "");
    },
    [session, connectToStream],
  );

  /* ── Resume a saved hunt from the DB ── */
  const resumeHunt = useCallback(
    async (savedSearchId: string) => {
      if (!session?.access_token) throw new Error("Not authenticated");

      const res = await fetch(`/api/proxy/searches/${savedSearchId}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!res.ok) throw new Error("Failed to load hunt");
      const data = await res.json();

      const search = data.search;
      const leads = data.leads || [];

      // Restore context
      setExtractedContext({
        industry: search.industry || null,
        companyProfile: search.company_profile || null,
        technologyFocus: search.technology_focus || null,
        qualifyingCriteria: search.qualifying_criteria || null,
        disqualifiers: null,
        geographicRegion: search.geographic_region || null,
        countryCode: search.country_code || null,
      });

      // Restore messages
      if (Array.isArray(search.messages) && search.messages.length > 0) {
        setMessages(
          search.messages.map((m: { role: string; content: string }) => ({
            id: crypto.randomUUID(),
            role: m.role as "user" | "assistant",
            content: m.content,
            timestamp: Date.now(),
          })),
        );
        // Mark all fields as ready since we already ran a search
        setReadiness({
          industry: true,
          companyProfile: true,
          technologyFocus: true,
          qualifyingCriteria: true,
          isReady: true,
        });
      }

      // Restore qualified leads
      const qualified = mapLeadsToQualified(leads);
      setQualifiedCompanies(qualified);
      setPipelineSummary(buildSummary(qualified));

      setSearchId(savedSearchId);
      setPhase("complete");
    },
    [session],
  );

  return (
    <HuntContext.Provider
      value={{
        messages,
        setMessages,
        readiness,
        setReadiness,
        phase,
        searchCompanies,
        allSearchCompanies,
        qualifiedCompanies,
        pipelineProgress,
        pipelineSummary,
        pipelineStartTime,
        extractedContext,
        enrichedContacts,
        enrichDone,
        setPhase,
        setSearchCompanies,
        setAllSearchCompanies,
        setQualifiedCompanies,
        setPipelineProgress,
        setPipelineSummary,
        setPipelineStartTime,
        setExtractedContext,
        setEnrichedContacts,
        setEnrichDone,
        launchSearch,
        launchPipeline,
        resetHunt,
        resumeHunt,
        searchId,
        isPipelineRunning,
      }}
    >
      {children}
    </HuntContext.Provider>
  );
}
