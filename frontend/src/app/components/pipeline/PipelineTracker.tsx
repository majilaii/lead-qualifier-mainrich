"use client";

/**
 * PipelineTracker — Tracks multiple concurrent pipeline runs in real-time.
 *
 * Unlike HuntContext (which manages a single "active" pipeline flow),
 * this context provides a list of ALL pipeline runs (active + completed)
 * and keeps live progress for any that are currently running.
 *
 * Used by the Pipeline dashboard page to show each run as its own card.
 */

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
   Types
   ══════════════════════════════════════════════ */

export interface PipelineRunInfo {
  id: string;
  name: string;
  mode: string; // "discover" | "qualify_only"
  industry: string | null;
  company_profile: string | null;
  technology_focus: string | null;
  qualifying_criteria: string | null;
  disqualifiers: string | null;
  geographic_region: string | null;
  search_context: Record<string, string>;
  total_found: number;
  hot: number;
  review: number;
  rejected: number;
  created_at: string | null;
  // Live state
  run_status: "running" | "complete" | "error" | "not_found";
  run_progress: { processed: number; total: number } | null;
}

export interface LiveProgress {
  processed: number;
  total: number;
  phase: string;
  company: string;
}

export interface LaunchPipelineConfig {
  name?: string;
  mode: "discover" | "qualify_only";
  search_context?: Record<string, string | undefined>;
  domains?: string[];
  template_id?: string;
  country_code?: string;
  options?: { use_vision?: boolean; max_leads?: number };
}

interface PipelineTrackerContextValue {
  /** All pipeline runs (active + completed), most recent first */
  runs: PipelineRunInfo[];
  /** Loading state */
  loading: boolean;
  /** Refresh the runs list from the server */
  refresh: () => Promise<void>;
  /** Launch a brand-new pipeline (POST + SSE) — sole owner of the stream */
  launchPipeline: (config: LaunchPipelineConfig) => Promise<string>;
  /** Re-run an existing pipeline (returns the new pipeline ID) */
  rerunPipeline: (searchId: string) => Promise<string>;
  /** Stop a running pipeline (keeps leads already found) */
  stopPipeline: (searchId: string) => Promise<void>;
  /** Delete a pipeline run */
  deletePipeline: (searchId: string) => Promise<void>;
  /** Map of searchId → live SSE progress for running pipelines */
  liveProgress: Map<string, LiveProgress>;
}

const PipelineTrackerContext = createContext<PipelineTrackerContextValue | null>(null);

export function usePipelineTracker() {
  const ctx = useContext(PipelineTrackerContext);
  if (!ctx) throw new Error("usePipelineTracker must be used inside <PipelineTrackerProvider>");
  return ctx;
}

/* ══════════════════════════════════════════════
   Provider
   ══════════════════════════════════════════════ */

export function PipelineTrackerProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [runs, setRuns] = useState<PipelineRunInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [liveProgress, setLiveProgress] = useState<Map<string, LiveProgress>>(new Map());

  // Track active SSE connections so we don't double-subscribe
  const activeStreams = useRef<Set<string>>(new Set());
  // Track polling intervals
  const pollIntervals = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  // Abort controllers for SSE streams
  const abortControllers = useRef<Map<string, AbortController>>(new Map());

  /* ── Fetch all runs from API ── */
  const refresh = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/searches", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        const data: PipelineRunInfo[] = await res.json();
        setRuns(data);
        return;
      }
    } catch (err) {
      console.error("[PipelineTracker] Failed to fetch runs:", err);
    } finally {
      setLoading(false);
    }
  }, [session]);

  /* ── Initial load ── */
  useEffect(() => {
    refresh();
  }, [refresh]);

  /* ── Connect SSE streams for any running pipelines ── */
  const connectStream = useCallback(
    (searchId: string, token: string) => {
      if (activeStreams.current.has(searchId)) return;
      activeStreams.current.add(searchId);

      const controller = new AbortController();
      abortControllers.current.set(searchId, controller);

      (async () => {
        try {
          const res = await fetch(
            `/api/proxy/pipeline/${searchId}/stream?after=0`,
            {
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            }
          );

          if (!res.ok || !res.body) {
            // Fall back to polling
            startPolling(searchId, token);
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

                if (event.type === "progress") {
                  setLiveProgress((prev) => {
                    const next = new Map(prev);
                    next.set(searchId, {
                      processed: event.index,
                      total: event.total,
                      phase: event.phase,
                      company: event.company?.title || event.company?.domain || "",
                    });
                    return next;
                  });

                  // Also update the run's progress in the runs list
                  setRuns((prev) =>
                    prev.map((r) =>
                      r.id === searchId
                        ? {
                            ...r,
                            run_status: "running" as const,
                            run_progress: { processed: event.index, total: event.total },
                          }
                        : r
                    )
                  );
                } else if (event.type === "result") {
                  // Increment counts in the runs list
                  setRuns((prev) =>
                    prev.map((r) => {
                      if (r.id !== searchId) return r;
                      const tier = event.company?.tier;
                      return {
                        ...r,
                        total_found: r.total_found + 1,
                        hot: r.hot + (tier === "hot" ? 1 : 0),
                        review: r.review + (tier === "review" ? 1 : 0),
                        rejected: r.rejected + (tier === "rejected" ? 1 : 0),
                      };
                    })
                  );
                } else if (event.type === "complete") {
                  // Mark as complete
                  setRuns((prev) =>
                    prev.map((r) =>
                      r.id === searchId
                        ? {
                            ...r,
                            run_status: "complete" as const,
                            run_progress: null,
                            hot: event.summary?.hot ?? r.hot,
                            review: event.summary?.review ?? r.review,
                            rejected: event.summary?.rejected ?? r.rejected,
                            total_found:
                              (event.summary?.hot ?? 0) +
                              (event.summary?.review ?? 0) +
                              (event.summary?.rejected ?? 0) || r.total_found,
                          }
                        : r
                    )
                  );
                  setLiveProgress((prev) => {
                    const next = new Map(prev);
                    next.delete(searchId);
                    return next;
                  });
                  cleanup(searchId);
                  return;
                } else if (event.type === "error" && event.fatal) {
                  setRuns((prev) =>
                    prev.map((r) =>
                      r.id === searchId
                        ? { ...r, run_status: "error" as const, run_progress: null }
                        : r
                    )
                  );
                  cleanup(searchId);
                  return;
                }
              } catch {
                // parse error, skip
              }
            }
          }

          // Stream ended without complete — fall back to polling
          startPolling(searchId, token);
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          console.error("[PipelineTracker] SSE error for %s:", searchId, err);
          startPolling(searchId, token);
        }
      })();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const startPolling = useCallback(
    (searchId: string, token: string) => {
      if (pollIntervals.current.has(searchId)) return;

      const poll = async () => {
        try {
          const res = await fetch(`/api/proxy/pipeline/${searchId}/status`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return;
          const data = await res.json();

          if (data.status === "running") {
            setRuns((prev) =>
              prev.map((r) =>
                r.id === searchId
                  ? {
                      ...r,
                      run_status: "running" as const,
                      run_progress: { processed: data.processed || 0, total: data.total || 0 },
                    }
                  : r
              )
            );
            setLiveProgress((prev) => {
              const next = new Map(prev);
              next.set(searchId, {
                processed: data.processed || 0,
                total: data.total || 0,
                phase: "qualifying",
                company: "",
              });
              return next;
            });
          } else {
            // Complete or error — refresh from DB
            cleanup(searchId);
            refresh();
          }
        } catch {
          // keep polling
        }
      };

      poll();
      pollIntervals.current.set(searchId, setInterval(poll, 4000));
    },
    [refresh]
  );

  const cleanup = useCallback((searchId: string) => {
    activeStreams.current.delete(searchId);
    const controller = abortControllers.current.get(searchId);
    if (controller) {
      controller.abort();
      abortControllers.current.delete(searchId);
    }
    const interval = pollIntervals.current.get(searchId);
    if (interval) {
      clearInterval(interval);
      pollIntervals.current.delete(searchId);
    }
  }, []);

  /* ── Auto-connect to SSE for running pipelines ── */
  useEffect(() => {
    if (!session?.access_token) return;

    const runningPipelines = runs.filter((r) => r.run_status === "running");
    for (const run of runningPipelines) {
      if (!activeStreams.current.has(run.id)) {
        connectStream(run.id, session.access_token);
      }
    }
  }, [runs, session, connectStream]);

  /* ── Cleanup on unmount ── */
  useEffect(() => {
    return () => {
      for (const controller of abortControllers.current.values()) {
        controller.abort();
      }
      for (const interval of pollIntervals.current.values()) {
        clearInterval(interval);
      }
    };
  }, []);

  /* ── Launch a new pipeline (sole SSE owner — no HuntContext involved) ── */
  const launchPipeline = useCallback(
    async (config: LaunchPipelineConfig): Promise<string> => {
      if (!session?.access_token) throw new Error("Not authenticated");

      const res = await fetch("/api/proxy/pipeline/create", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: config.name,
          mode: config.mode,
          search_context: config.search_context || undefined,
          domains: config.domains || undefined,
          template_id: config.template_id || undefined,
          country_code: config.country_code || undefined,
          options: config.options || { use_vision: true },
        }),
      });

      if (!res.ok) {
        if (res.status === 429) {
          const err = await res.json();
          window.dispatchEvent(new CustomEvent("hunt:quota_exceeded", { detail: err }));
          throw new Error("Quota exceeded");
        }
        const errText = await res.text().catch(() => "Pipeline creation failed");
        throw new Error(errText);
      }

      const data = await res.json();
      const newId = data.pipeline_id;

      // Add optimistically to runs list
      const newRun: PipelineRunInfo = {
        id: newId,
        name: data.name || config.name || "Pipeline",
        mode: config.mode,
        industry: config.search_context?.industry || null,
        company_profile: config.search_context?.company_profile || null,
        technology_focus: config.search_context?.technology_focus || null,
        qualifying_criteria: config.search_context?.qualifying_criteria || null,
        disqualifiers: config.search_context?.disqualifiers || null,
        geographic_region: config.search_context?.geographic_region || null,
        search_context: (config.search_context || {}) as Record<string, string>,
        total_found: 0,
        hot: 0,
        review: 0,
        rejected: 0,
        created_at: new Date().toISOString(),
        run_status: "running",
        run_progress: { processed: 0, total: 0 },
      };
      setRuns((prev) => [newRun, ...prev]);

      // Connect SSE — PipelineTracker is the sole consumer
      connectStream(newId, session.access_token);

      return newId;
    },
    [session, connectStream]
  );

  /* ── Re-run a pipeline ── */
  const rerunPipeline = useCallback(
    async (searchId: string): Promise<string> => {
      if (!session?.access_token) throw new Error("Not authenticated");

      const res = await fetch(`/api/proxy/searches/${searchId}/rerun`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
      });

      if (!res.ok) {
        if (res.status === 429) {
          const err = await res.json();
          window.dispatchEvent(new CustomEvent("hunt:quota_exceeded", { detail: err }));
          throw new Error("Quota exceeded");
        }
        throw new Error("Re-run failed");
      }

      const data = await res.json();
      const newId = data.pipeline_id;

      // Add the new run to the top of the list optimistically
      const original = runs.find((r) => r.id === searchId);
      if (original) {
        const newRun: PipelineRunInfo = {
          ...original,
          id: newId,
          name: data.name || `${original.name} (re-run)`,
          total_found: 0,
          hot: 0,
          review: 0,
          rejected: 0,
          created_at: new Date().toISOString(),
          run_status: "running",
          run_progress: { processed: 0, total: 0 },
        };
        setRuns((prev) => [newRun, ...prev]);
      }

      // Connect to the SSE stream for the new pipeline
      if (session.access_token) {
        connectStream(newId, session.access_token);
      }

      return newId;
    },
    [session, runs, connectStream]
  );

  /* ── Stop a running pipeline ── */
  const stopPipeline = useCallback(
    async (searchId: string) => {
      if (!session?.access_token) return;

      const res = await fetch(`/api/proxy/pipeline/${searchId}/stop`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });

      if (res.ok) {
        // Clean up SSE/polling for this pipeline
        cleanup(searchId);

        // Update local state immediately
        setRuns((prev) =>
          prev.map((r) =>
            r.id === searchId
              ? { ...r, run_status: "complete" as const, run_progress: null }
              : r
          )
        );
        setLiveProgress((prev) => {
          const next = new Map(prev);
          next.delete(searchId);
          return next;
        });

        // Refresh from DB after a beat to get final counts
        setTimeout(() => refresh(), 1000);
      }
    },
    [session, cleanup, refresh]
  );

  /* ── Delete a pipeline ── */
  const deletePipeline = useCallback(
    async (searchId: string) => {
      if (!session?.access_token) return;

      // Clean up any active streams first
      cleanup(searchId);

      const res = await fetch(`/api/proxy/searches/${searchId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });

      if (res.ok) {
        setRuns((prev) => prev.filter((r) => r.id !== searchId));
      }
    },
    [session, cleanup]
  );

  /* ── Auto-refresh when a pipeline completes (to get final DB counts) ── */
  const prevRunning = useRef<Set<string>>(new Set());
  useEffect(() => {
    const currentRunning = new Set(
      runs.filter((r) => r.run_status === "running").map((r) => r.id)
    );

    // Check if any pipeline just transitioned from running → not running
    for (const id of prevRunning.current) {
      if (!currentRunning.has(id)) {
        // Pipeline just completed — refresh after a short delay to get final DB data
        setTimeout(() => refresh(), 1500);
        break;
      }
    }

    prevRunning.current = currentRunning;
  }, [runs, refresh]);

  return (
    <PipelineTrackerContext.Provider
      value={{
        runs,
        loading,
        refresh,
        launchPipeline,
        rerunPipeline,
        stopPipeline,
        deletePipeline,
        liveProgress,
      }}
    >
      {children}
    </PipelineTrackerContext.Provider>
  );
}
