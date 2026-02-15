"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "../../components/auth/SessionProvider";

interface EnrichmentJob {
  id: string;
  action: string;
  status: string; // pending | running | complete | error
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

interface SSEProgress {
  type: string;
  index?: number;
  total?: number;
  lead_id?: string;
  company?: string;
  domain?: string;
  status?: string;
  message?: string;
  succeeded?: number;
  failed?: number;
}

const ACTION_LABELS: Record<string, string> = {
  recrawl_contacts: "Re-crawl Contacts",
  requalify: "Re-qualify",
  full_recrawl: "Full Re-crawl",
  linkedin: "LinkedIn Lookup",
};

const ACTION_COLORS: Record<string, string> = {
  recrawl_contacts: "secondary",
  requalify: "amber-400",
  full_recrawl: "purple-400",
  linkedin: "blue-400",
};

export function useEnrichmentJobs() {
  const { session } = useAuth();
  const [jobs, setJobs] = useState<EnrichmentJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [liveProgress, setLiveProgress] = useState<SSEProgress | null>(null);
  const [liveProcessed, setLiveProcessed] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch recent jobs
  const fetchJobs = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/leads/enrich-jobs", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
        // Auto-detect running job
        const running = data.find((j: EnrichmentJob) => j.status === "running" || j.status === "pending");
        if (running && running.id !== activeJobId) {
          setActiveJobId(running.id);
        }
      }
    } catch { /* ignore */ }
  }, [session, activeJobId]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // SSE stream for active job
  useEffect(() => {
    if (!activeJobId || !session?.access_token) return;
    // Close previous
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setLiveProcessed(0);
    setLiveProgress(null);

    // Use fetch-based SSE since we need auth headers
    const controller = new AbortController();
    let eventIdx = 0;

    const connectSSE = async () => {
      try {
        const res = await fetch(`/api/proxy/leads/enrich-jobs/${activeJobId}/stream?after=${eventIdx}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event: SSEProgress = JSON.parse(line.slice(6));
              eventIdx++;

              if (event.type === "progress" || event.type === "result") {
                setLiveProgress(event);
                if (event.type === "result") {
                  setLiveProcessed((prev) => prev + 1);
                }
              }

              if (event.type === "complete") {
                // Refresh jobs list
                fetchJobs();
                setActiveJobId(null);
                setLiveProgress(null);
              }
            } catch { /* ignore parse errors */ }
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          // Retry after delay
          setTimeout(connectSSE, 3000);
        }
      }
    };

    connectSSE();

    return () => {
      controller.abort();
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [activeJobId, session, fetchJobs]);

  // Start a batch job
  const startBatchJob = useCallback(async (leadIds: string[], action: string): Promise<string | null> => {
    if (!session?.access_token) return null;
    try {
      const res = await fetch("/api/proxy/leads/batch-enrich", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ lead_ids: leadIds, action }),
      });
      if (res.ok) {
        const data = await res.json();
        setActiveJobId(data.job_id);
        fetchJobs();
        return data.job_id;
      }
    } catch { /* ignore */ }
    return null;
  }, [session, fetchJobs]);

  const activeJob = jobs.find((j) => j.id === activeJobId) || null;

  return {
    jobs,
    activeJob,
    activeJobId,
    liveProgress,
    liveProcessed,
    startBatchJob,
    fetchJobs,
  };
}

export function EnrichmentJobBanner({
  activeJob,
  liveProgress,
  liveProcessed,
}: {
  activeJob: EnrichmentJob | null;
  liveProgress: SSEProgress | null;
  liveProcessed: number;
}) {
  // Also show recently completed jobs (within last 30s)
  if (!activeJob && !liveProgress) return null;

  const total = activeJob?.total || liveProgress?.total || 0;
  const processed = liveProcessed || activeJob?.processed || 0;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  const isRunning = activeJob?.status === "running" || activeJob?.status === "pending";
  const isComplete = activeJob?.status === "complete";
  const actionLabel = ACTION_LABELS[activeJob?.action || ""] || activeJob?.action || "Enrichment";
  const color = ACTION_COLORS[activeJob?.action || ""] || "secondary";

  return (
    <div className={`bg-surface-2 border rounded-xl p-4 transition-all ${
      isRunning ? `border-${color}/30 bg-${color}/5` : isComplete ? "border-green-400/30 bg-green-400/5" : "border-border"
    }`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isRunning && (
            <span className={`w-3 h-3 border-2 border-${color}/40 border-t-${color} rounded-full animate-spin`} />
          )}
          {isComplete && (
            <span className="text-green-400 text-sm">✓</span>
          )}
          <span className="font-mono text-[12px] font-semibold text-text-primary">
            {actionLabel}
          </span>
          <span className="font-mono text-[12px] text-text-dim">
            {processed}/{total} leads
          </span>
        </div>
        <span className="font-mono text-[12px] text-text-muted">
          {pct}%
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            isComplete ? "bg-green-400" : `bg-secondary`
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Current lead */}
      {isRunning && liveProgress && liveProgress.company && (
        <p className="font-mono text-[12px] text-text-dim mt-1.5 truncate">
          → {liveProgress.company} {liveProgress.domain ? `(${liveProgress.domain})` : ""}
        </p>
      )}

      {/* Completed summary */}
      {isComplete && activeJob && (
        <p className="font-mono text-[12px] text-text-muted mt-1.5">
          {activeJob.succeeded} succeeded · {activeJob.failed} failed
        </p>
      )}
    </div>
  );
}

export default EnrichmentJobBanner;
