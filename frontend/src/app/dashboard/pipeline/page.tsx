"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  usePipelineTracker,
  type PipelineRunInfo,
} from "../../components/pipeline/PipelineTracker";
import { usePipeline } from "../../components/hunt/PipelineContext";
import { TableRowSkeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { useToast } from "../../components/ui/Toast";

type Tab = "active" | "history";

export default function PipelinePage() {
  const router = useRouter();
  const {
    runs,
    loading,
    rerunPipeline,
    stopPipeline,
    deletePipeline,
    liveProgress,
  } = usePipelineTracker();
  const { resetPipeline } = usePipeline();
  const { toast } = useToast();

  const [tab, setTab] = useState<Tab>("active");
  const [rerunningId, setRerunningId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const activeRuns = runs.filter((r) => r.run_status === "running");
  // Chat sessions: mode === "chat" and no leads yet (still in conversation)
  const chatSessions = runs.filter(
    (r) => r.mode === "chat" && r.run_status !== "running" && r.hot + r.review + r.rejected === 0
  );
  const completedRuns = runs.filter(
    (r) => r.run_status !== "running" && !(r.mode === "chat" && r.hot + r.review + r.rejected === 0)
  );

  // Respect the user's explicit tab choice at all times
  const displayTab = tab;

  const activeCount = activeRuns.length + chatSessions.length;

  const totalLeads = runs.reduce(
    (s, r) => s + r.hot + r.review + r.rejected,
    0
  );
  const totalHot = runs.reduce((s, r) => s + r.hot, 0);

  const handleRerun = useCallback(
    async (run: PipelineRunInfo) => {
      setRerunningId(run.id);
      try {
        await rerunPipeline(run.id);
        toast({ title: "Pipeline re-launched", description: run.name || run.industry || "Re-run", variant: "success" });
        setTab("active");
      } catch (err) {
        console.error("Rerun failed:", err);
        toast({ title: "Re-run failed", description: err instanceof Error ? err.message : "Try again", variant: "error" });
      } finally {
        setRerunningId(null);
      }
    },
    [rerunPipeline, toast]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      setDeletingId(id);
      try {
        await deletePipeline(id);
        toast({ title: "Pipeline deleted", variant: "info" });
      } finally {
        setDeletingId(null);
        setConfirmDeleteId(null);
      }
    },
    [deletePipeline, toast]
  );

  if (loading) {
    return (
      <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">Pipeline</h1>
            <p className="font-sans text-sm text-text-muted mt-1">Loading runs…</p>
          </div>
        </div>
        <div className="bg-surface-2 border border-border rounded-xl overflow-hidden">
          <TableRowSkeleton rows={6} />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start sm:items-center justify-between gap-3 flex-col sm:flex-row">
        <div>
          <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
            Pipeline
          </h1>
          <p className="font-sans text-sm text-text-muted mt-1">
            {runs.length} run{runs.length !== 1 && "s"} · {totalLeads} leads (
            {totalHot} hot)
            {activeCount > 0 && (
              <span className="text-secondary ml-2">
                · {activeCount} active
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => {
            resetPipeline();
            router.push("/dashboard/new");
          }}
          className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-[12px] font-bold uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg hover:bg-white/85 transition-colors cursor-pointer"
        >
          + New Pipeline
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-2 border border-border rounded-xl p-1">
        <button
          onClick={() => setTab("active")}
          className={`flex-1 flex items-center justify-center gap-2 font-mono text-xs uppercase tracking-[0.1em] py-2.5 rounded-lg transition-all cursor-pointer ${
            displayTab === "active"
              ? "bg-secondary/10 text-secondary border border-secondary/20"
              : "text-text-muted hover:text-text-primary border border-transparent"
          }`}
        >
          <div className="relative flex items-center gap-2">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Active
            {activeCount > 0 && (
              <span className="bg-secondary text-void text-[12px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                {activeCount}
              </span>
            )}
          </div>
        </button>
        <button
          onClick={() => setTab("history")}
          className={`flex-1 flex items-center justify-center gap-2 font-mono text-xs uppercase tracking-[0.1em] py-2.5 rounded-lg transition-all cursor-pointer ${
            displayTab === "history"
              ? "bg-secondary/10 text-secondary border border-secondary/20"
              : "text-text-muted hover:text-text-primary border border-transparent"
          }`}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          History
          {completedRuns.length > 0 && (
            <span className="text-text-dim text-[12px]">
              ({completedRuns.length})
            </span>
          )}
        </button>
      </div>

      {/* Active Tab */}
      {displayTab === "active" && (
        <div className="space-y-3">
          {activeCount === 0 ? (
            <div className="bg-surface-2 border border-border rounded-xl px-6 py-12 text-center space-y-4">
              <div className="w-12 h-12 mx-auto bg-surface-3 rounded-full flex items-center justify-center">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-text-dim"
                >
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              </div>
              <p className="font-mono text-xs text-text-dim">
                No active pipelines or chats
              </p>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => {
                    resetPipeline();
                    router.push("/dashboard/new");
                  }}
                  className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
                >
                  + New Pipeline
                </button>
                <button
                  onClick={() => {
                    resetPipeline();
                    router.push("/chat");
                  }}
                  className="inline-flex items-center gap-2 border border-border text-text-muted font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:text-text-primary hover:border-border-bright transition-colors cursor-pointer"
                >
                  Start Chat
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Running pipelines */}
              {activeRuns.map((run) => (
                <ActivePipelineCard
                  key={run.id}
                  run={run}
                  liveProgress={liveProgress.get(run.id) || null}
                  onStop={() => stopPipeline(run.id)}
                />
              ))}
              {/* Chat sessions in progress */}
              {chatSessions.map((chat) => (
                <ChatSessionCard key={chat.id} chat={chat} onDelete={() => handleDelete(chat.id)} />
              ))}
            </>
          )}
        </div>
      )}

      {/* History Tab */}
      {displayTab === "history" && (
        <div className="space-y-3">
          {completedRuns.length === 0 ? (
            <div className="bg-surface-2 border border-border rounded-xl px-6 py-12 text-center space-y-4">
              <p className="font-mono text-xs text-text-dim">
                No completed runs yet
              </p>
              <button
                onClick={() => {
                  resetPipeline();
                  router.push("/dashboard/new");
                }}
                className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
              >
                + New Pipeline
              </button>
            </div>
          ) : (
            completedRuns.map((run) => {
              const isChatMode = run.mode === "chat" || run.mode === "chat_pipeline";
              const isRerunning = rerunningId === run.id;
              const isConfirming = confirmDeleteId === run.id;
              const isDeleting = deletingId === run.id;

              if (isChatMode) {
                return (
                  <ChatHistoryCard
                    key={run.id}
                    run={run}
                    isRerunning={isRerunning}
                    isConfirming={isConfirming}
                    isDeleting={isDeleting}
                    onRerun={() => handleRerun(run)}
                    onDelete={() => handleDelete(run.id)}
                    onConfirmDelete={() => setConfirmDeleteId(run.id)}
                    onCancelDelete={() => setConfirmDeleteId(null)}
                  />
                );
              }

              const total = run.hot + run.review + run.rejected;
              const hotPct = total > 0 ? (run.hot / total) * 100 : 0;
              const reviewPct = total > 0 ? (run.review / total) * 100 : 0;
              const rejectedPct = total > 0 ? (run.rejected / total) * 100 : 0;

              return (
                <div
                  key={run.id}
                  className="bg-surface-2 border border-border rounded-xl hover:border-border-bright transition-colors group"
                >
                  <div className="p-5 flex items-start gap-4">
                    {/* Status dot */}
                    <div className="mt-1 flex-shrink-0">
                      <div
                        className={`w-2.5 h-2.5 rounded-full ${
                          run.run_status === "error"
                            ? "bg-red-400/80"
                            : "bg-green-400/80"
                        }`}
                        title={
                          run.run_status === "error" ? "Error" : "Complete"
                        }
                      />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0 space-y-2">
                      <div>
                        <p className="font-mono text-sm text-text-primary font-medium truncate">
                          {run.name || run.industry || "Untitled Pipeline"}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          {run.technology_focus && (
                            <span className="font-mono text-[12px] text-text-dim truncate">
                              {run.technology_focus}
                            </span>
                          )}
                          {run.mode && (
                            <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-text-dim/60 bg-surface-3 px-1.5 py-0.5 rounded">
                              {run.mode === "qualify_only"
                                  ? "bulk"
                                  : "discover"}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Tier bar */}
                      {total > 0 && (
                        <div className="space-y-1">
                          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden flex">
                            {run.hot > 0 && (
                              <div
                                className="h-full bg-hot rounded-l-full"
                                style={{ width: `${hotPct}%` }}
                              />
                            )}
                            {run.review > 0 && (
                              <div
                                className="h-full bg-review"
                                style={{ width: `${reviewPct}%` }}
                              />
                            )}
                            {run.rejected > 0 && (
                              <div
                                className="h-full bg-text-dim/40 rounded-r-full"
                                style={{ width: `${rejectedPct}%` }}
                              />
                            )}
                          </div>
                          <div className="flex gap-3">
                            <span className="font-mono text-[12px] text-hot">
                              {run.hot} hot
                            </span>
                            <span className="font-mono text-[12px] text-review">
                              {run.review} review
                            </span>
                            <span className="font-mono text-[12px] text-text-dim">
                              {run.rejected} rejected
                            </span>
                            <span className="font-mono text-[12px] text-text-dim ml-auto">
                              {run.total_found} found
                            </span>
                          </div>
                        </div>
                      )}

                      {/* ICP context tags */}
                      {Object.keys(run.search_context || {}).length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {run.search_context.industry && (
                            <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
                              {run.search_context.industry.slice(0, 30)}
                            </span>
                          )}
                          {run.search_context.geographic_region && (
                            <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
                              📍{" "}
                              {run.search_context.geographic_region.slice(
                                0,
                                25
                              )}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Right side: date + actions */}
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      {run.created_at && (
                        <span className="font-mono text-[12px] text-text-dim">
                          {new Date(run.created_at).toLocaleDateString()}
                        </span>
                      )}
                      <div className="flex items-center gap-1.5">
                        {/* View leads */}
                        <Link
                          href={`/dashboard/leads?search_id=${run.id}`}
                          className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Leads →
                        </Link>

                        {/* Re-run */}
                        <button
                          onClick={() => handleRerun(run)}
                          disabled={isRerunning}
                          className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md border border-border text-text-muted hover:text-secondary hover:border-secondary/30 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                          title="Re-run this pipeline with the same configuration"
                        >
                          {isRerunning ? (
                            <>
                              <div className="w-2.5 h-2.5 border border-secondary/40 border-t-secondary rounded-full animate-spin" />
                              Running...
                            </>
                          ) : (
                            <>
                              <svg
                                width="10"
                                height="10"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2.5"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <polyline points="23 4 23 10 17 10" />
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                              </svg>
                              Re-run
                            </>
                          )}
                        </button>

                        {/* Delete */}
                        {isConfirming ? (
                          <span className="flex items-center gap-1">
                            <span
                              role="button"
                              tabIndex={0}
                              onClick={() => handleDelete(run.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleDelete(run.id);
                              }}
                              className="font-mono text-[12px] text-red-400 hover:text-red-300 cursor-pointer px-1.5 py-1"
                            >
                              {isDeleting ? "…" : "Confirm"}
                            </span>
                            <span
                              role="button"
                              tabIndex={0}
                              onClick={() => setConfirmDeleteId(null)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter")
                                  setConfirmDeleteId(null);
                              }}
                              className="font-mono text-[12px] text-text-dim hover:text-text-muted cursor-pointer px-1.5 py-1"
                            >
                              Cancel
                            </span>
                          </span>
                        ) : (
                          <button
                            onClick={() => setConfirmDeleteId(run.id)}
                            className="opacity-0 group-hover:opacity-100 text-text-dim hover:text-red-400 transition-all cursor-pointer p-1"
                            title="Delete run"
                          >
                            <svg
                              width="13"
                              height="13"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════
   Active Pipeline Card — Live real-time progress
   ══════════════════════════════════════════════ */

function ActivePipelineCard({
  run,
  liveProgress,
  onStop,
}: {
  run: PipelineRunInfo;
  liveProgress: {
    processed: number;
    total: number;
    phase: string;
    company: string;
  } | null;
  onStop: () => void;
}) {
  const [stopping, setStopping] = useState(false);
  const processed =
    liveProgress?.processed ?? run.run_progress?.processed ?? 0;
  const total = liveProgress?.total ?? run.run_progress?.total ?? 0;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  const phase = liveProgress?.phase ?? "qualifying";
  const company = liveProgress?.company ?? "";

  const hotCount = run.hot;
  const reviewCount = run.review;
  const rejectedCount = run.rejected;

  return (
    <div className="bg-surface-2 border border-secondary/30 rounded-xl p-5 space-y-3">
      {/* Header row */}
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-mono text-xs text-text-primary font-medium truncate">
            {run.name || run.industry || "Pipeline"}
          </p>
          <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-secondary/50">
            {run.mode === "chat_pipeline" ? "Chat" : run.mode === "qualify_only" ? "Bulk Import" : "Discovery"} · Running
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              setStopping(true);
              await onStop();
            }}
            disabled={stopping}
            className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md border border-red-500/30 text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
            title="Stop this pipeline"
          >
            {stopping ? (
              <div className="w-2.5 h-2.5 border border-red-400/40 border-t-red-400 rounded-full animate-spin" />
            ) : (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
            )}
            Stop
          </button>
          {run.mode === "chat_pipeline" && (
            <Link
              href={`/chat?session=${run.id}`}
              className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/20 transition-colors"
            >
              Chat →
            </Link>
          )}
          <Link
            href={`/dashboard/leads?search_id=${run.id}`}
            className="font-mono text-[12px] uppercase tracking-[0.15em] text-secondary hover:text-secondary/80 transition-colors"
          >
            View →
          </Link>
        </div>
      </div>

      {/* Currently processing */}
      {company && (
        <p className="font-mono text-[12px] text-text-dim truncate">
          {phase === "crawling" ? "🌐 Crawling" : "🔍 Analyzing"}{" "}
          <span className="text-text-muted">{company}</span>
        </p>
      )}

      {/* Progress bar */}
      {total > 0 && (
        <div className="space-y-1.5">
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div
              className="h-full bg-secondary rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex justify-between">
            <span className="font-mono text-[12px] text-text-dim">
              {processed} / {total} companies
            </span>
            <span className="font-mono text-[12px] text-text-dim">{pct}%</span>
          </div>
        </div>
      )}

      {/* Discovery phase — pulsing bar (total unknown yet) */}
      {total === 0 && (
        <div className="space-y-1.5">
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div className="h-full bg-secondary/60 rounded-full animate-pulse w-full" />
          </div>
          <p className="font-mono text-[12px] text-text-dim">
            Discovering companies…
          </p>
        </div>
      )}

      {/* Live result counts */}
      {(hotCount > 0 || reviewCount > 0 || rejectedCount > 0) && (
        <div className="flex gap-3 pt-1 border-t border-border/50">
          <span className="font-mono text-[12px] text-hot">
            {hotCount} hot
          </span>
          <span className="font-mono text-[12px] text-review">
            {reviewCount} review
          </span>
          <span className="font-mono text-[12px] text-text-dim">
            {rejectedCount} rejected
          </span>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════
   Chat History Card — Completed chat sessions
   ══════════════════════════════════════════════ */

function ChatHistoryCard({
  run,
  isRerunning,
  isConfirming,
  isDeleting,
  onRerun,
  onDelete,
  onConfirmDelete,
  onCancelDelete,
}: {
  run: PipelineRunInfo;
  isRerunning: boolean;
  isConfirming: boolean;
  isDeleting: boolean;
  onRerun: () => void;
  onDelete: () => void;
  onConfirmDelete: () => void;
  onCancelDelete: () => void;
}) {
  const total = run.hot + run.review + run.rejected;
  const hotPct = total > 0 ? (run.hot / total) * 100 : 0;
  const reviewPct = total > 0 ? (run.review / total) * 100 : 0;
  const rejectedPct = total > 0 ? (run.rejected / total) * 100 : 0;

  return (
    <div className="bg-surface-2 border border-blue-500/20 rounded-xl hover:border-blue-500/30 transition-colors group">
      <div className="p-5 space-y-3">
        {/* Header */}
        <div className="flex items-center gap-3">
          {/* Chat icon */}
          <div className="w-7 h-7 bg-blue-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-mono text-xs text-text-primary font-medium truncate">
              {run.name || run.industry || "Chat Session"}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-blue-400/60">
                Chat · {run.run_status === "error" ? "Error" : "Complete"}
              </span>
              {run.technology_focus && (
                <span className="font-mono text-[12px] text-text-dim truncate">
                  {run.technology_focus}
                </span>
              )}
            </div>
          </div>

          {/* Date + actions */}
          <div className="flex flex-col items-end gap-2 flex-shrink-0">
            {run.created_at && (
              <span className="font-mono text-[12px] text-text-dim">
                {new Date(run.created_at).toLocaleDateString()}
              </span>
            )}
            <div className="flex items-center gap-1.5">
              {/* View leads */}
              {total > 0 && (
                <Link
                  href={`/dashboard/leads?search_id=${run.id}`}
                  className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  Leads →
                </Link>
              )}

              {/* Resume chat */}
              <Link
                href={`/chat?session=${run.id}`}
                className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/20 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                Resume Chat
              </Link>

              {/* Re-run */}
              <button
                onClick={onRerun}
                disabled={isRerunning}
                className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md border border-border text-text-muted hover:text-secondary hover:border-secondary/30 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                title="Re-run this pipeline with the same configuration"
              >
                {isRerunning ? (
                  <>
                    <div className="w-2.5 h-2.5 border border-secondary/40 border-t-secondary rounded-full animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="23 4 23 10 17 10" />
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                    </svg>
                    Re-run
                  </>
                )}
              </button>

              {/* Delete */}
              {isConfirming ? (
                <span className="flex items-center gap-1">
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={onDelete}
                    onKeyDown={(e) => { if (e.key === "Enter") onDelete(); }}
                    className="font-mono text-[12px] text-red-400 hover:text-red-300 cursor-pointer px-1.5 py-1"
                  >
                    {isDeleting ? "…" : "Confirm"}
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    onClick={onCancelDelete}
                    onKeyDown={(e) => { if (e.key === "Enter") onCancelDelete(); }}
                    className="font-mono text-[12px] text-text-dim hover:text-text-muted cursor-pointer px-1.5 py-1"
                  >
                    Cancel
                  </span>
                </span>
              ) : (
                <button
                  onClick={onConfirmDelete}
                  className="opacity-0 group-hover:opacity-100 text-text-dim hover:text-red-400 transition-all cursor-pointer p-1"
                  title="Delete run"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Tier bar (only if there are leads) */}
        {total > 0 && (
          <div className="space-y-1">
            <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden flex">
              {run.hot > 0 && (
                <div className="h-full bg-hot rounded-l-full" style={{ width: `${hotPct}%` }} />
              )}
              {run.review > 0 && (
                <div className="h-full bg-review" style={{ width: `${reviewPct}%` }} />
              )}
              {run.rejected > 0 && (
                <div className="h-full bg-text-dim/40 rounded-r-full" style={{ width: `${rejectedPct}%` }} />
              )}
            </div>
            <div className="flex gap-3">
              <span className="font-mono text-[12px] text-hot">{run.hot} hot</span>
              <span className="font-mono text-[12px] text-review">{run.review} review</span>
              <span className="font-mono text-[12px] text-text-dim">{run.rejected} rejected</span>
              <span className="font-mono text-[12px] text-text-dim ml-auto">{run.total_found} found</span>
            </div>
          </div>
        )}

        {/* Context tags */}
        <div className="flex flex-wrap gap-1.5">
          {run.industry && (
            <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
              {run.industry.slice(0, 40)}
            </span>
          )}
          {(run.search_context?.geographic_region) && (
            <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
              📍 {run.search_context.geographic_region.slice(0, 25)}
            </span>
          )}
          {!run.industry && !run.technology_focus && total === 0 && (
            <span className="font-mono text-[12px] text-text-dim/50 italic">
              Chat session — no leads generated
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════
   Chat Session Card — In-progress conversation
   ══════════════════════════════════════════════ */

function ChatSessionCard({
  chat,
  onDelete,
}: {
  chat: PipelineRunInfo;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="bg-surface-2 border border-blue-500/20 rounded-xl p-5 space-y-2">
      {/* Header */}
      <div className="flex items-center gap-3">
        {/* Chat icon */}
        <div className="w-7 h-7 bg-blue-500/10 rounded-lg flex items-center justify-center flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-400">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-mono text-xs text-text-primary font-medium truncate">
            {chat.name || chat.industry || "Chat Session"}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-mono text-[12px] uppercase tracking-[0.15em] text-blue-400/60">
              Chat · In progress
            </span>
            {chat.created_at && (
              <span className="font-mono text-[12px] text-text-dim">
                {new Date(chat.created_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            href={`/chat?session=${chat.id}`}
            className="font-mono text-[12px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-blue-500/10 border border-blue-500/20 text-blue-400 hover:bg-blue-500/20 transition-colors"
          >
            Resume →
          </Link>
          {confirming ? (
            <span className="flex items-center gap-1">
              <span
                role="button"
                tabIndex={0}
                onClick={onDelete}
                onKeyDown={(e) => { if (e.key === "Enter") onDelete(); }}
                className="font-mono text-[12px] text-red-400 hover:text-red-300 cursor-pointer px-1.5 py-1"
              >
                Confirm
              </span>
              <span
                role="button"
                tabIndex={0}
                onClick={() => setConfirming(false)}
                onKeyDown={(e) => { if (e.key === "Enter") setConfirming(false); }}
                className="font-mono text-[12px] text-text-dim hover:text-text-muted cursor-pointer px-1.5 py-1"
              >
                Cancel
              </span>
            </span>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="text-text-dim hover:text-red-400 transition-all cursor-pointer p-1"
              title="Delete chat session"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Context tags */}
      <div className="flex flex-wrap gap-1.5">
        {chat.industry && (
          <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
            {chat.industry.slice(0, 40)}
          </span>
        )}
        {chat.technology_focus && (
          <span className="font-mono text-[12px] text-text-dim/80 bg-surface-3 px-2 py-0.5 rounded-full">
            {chat.technology_focus.slice(0, 40)}
          </span>
        )}
        {!chat.industry && !chat.technology_focus && (
          <span className="font-mono text-[12px] text-text-dim/50 italic">
            Conversation started — no ICP defined yet
          </span>
        )}
      </div>
    </div>
  );
}
