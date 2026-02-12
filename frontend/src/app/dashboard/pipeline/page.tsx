"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../components/auth/SessionProvider";
import { useHunt } from "../../components/hunt/HuntContext";

interface PipelineRun {
  id: string;
  industry: string | null;
  company_profile: string | null;
  technology_focus: string | null;
  qualifying_criteria: string | null;
  disqualifiers: string | null;
  total_found: number;
  hot: number;
  review: number;
  rejected: number;
  created_at: string | null;
}

export default function PipelinePage() {
  const { session } = useAuth();
  const router = useRouter();
  const { phase, searchCompanies, qualifiedCompanies, pipelineProgress, resetHunt } = useHunt();

  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // Active pipeline state
  const isLiveRunning = phase === "searching" || phase === "qualifying";
  const isLiveComplete = phase === "complete" || phase === "search-complete";

  const fetchRuns = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/searches", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setRuns(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Refresh list when a live run completes
  useEffect(() => {
    if (phase === "complete") {
      fetchRuns();
    }
  }, [phase, fetchRuns]);

  const handleDelete = async (id: string) => {
    if (!session?.access_token) return;
    setDeletingId(id);
    try {
      const res = await fetch(`/api/proxy/searches/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) {
        setRuns((prev) => prev.filter((r) => r.id !== id));
      }
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const handleResume = (run: PipelineRun) => {
    router.push(`/chat?resume=${run.id}`);
  };

  const totalLeads = runs.reduce((s, r) => s + r.hot + r.review + r.rejected, 0);
  const totalHot = runs.reduce((s, r) => s + r.hot, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
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
            {runs.length} run{runs.length !== 1 && "s"} · {totalLeads} leads ({totalHot} hot)
          </p>
        </div>
        <button
          onClick={() => { resetHunt(); router.push("/chat"); }}
          className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-[10px] font-bold uppercase tracking-[0.15em] px-4 py-2.5 rounded-lg hover:bg-white/85 transition-colors cursor-pointer"
        >
          + New Run
        </button>
      </div>

      {/* Live Run Card */}
      {(isLiveRunning || isLiveComplete) && (
        <div className="bg-surface-2 border border-secondary/30 rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-3">
            {isLiveRunning ? (
              <div className="w-3 h-3 border-2 border-secondary/40 border-t-secondary rounded-full animate-spin flex-shrink-0" />
            ) : (
              <div className="w-3 h-3 rounded-full bg-green-400 flex-shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <p className="font-mono text-xs text-text-primary font-medium">
                {phase === "searching" && "Searching the web…"}
                {phase === "search-complete" && `${searchCompanies.length} companies found — ready to qualify`}
                {phase === "qualifying" && "Qualifying leads…"}
                {phase === "complete" && "Run complete"}
              </p>
              {pipelineProgress && (
                <p className="font-mono text-[10px] text-text-dim mt-0.5">
                  {pipelineProgress.phase === "crawling" ? "Crawling" : "Analyzing"}{" "}
                  {pipelineProgress.company}
                </p>
              )}
            </div>
            <Link
              href="/chat"
              className="font-mono text-[10px] uppercase tracking-[0.15em] text-secondary hover:text-secondary/80 transition-colors"
            >
              View →
            </Link>
          </div>

          {/* Progress bar for qualifying */}
          {phase === "qualifying" && searchCompanies.length > 0 && (
            <div className="space-y-1.5">
              <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                <div
                  className="h-full bg-secondary rounded-full transition-all duration-300"
                  style={{ width: `${(qualifiedCompanies.length / searchCompanies.length) * 100}%` }}
                />
              </div>
              <div className="flex justify-between">
                <span className="font-mono text-[9px] text-text-dim">
                  {qualifiedCompanies.length} / {searchCompanies.length} companies
                </span>
                <span className="font-mono text-[9px] text-text-dim">
                  {Math.round((qualifiedCompanies.length / searchCompanies.length) * 100)}%
                </span>
              </div>
            </div>
          )}

          {/* Result preview when complete */}
          {phase === "complete" && qualifiedCompanies.length > 0 && (
            <div className="flex gap-3 pt-1">
              <span className="font-mono text-[10px] text-hot">
                {qualifiedCompanies.filter((c) => c.tier === "hot").length} hot
              </span>
              <span className="font-mono text-[10px] text-review">
                {qualifiedCompanies.filter((c) => c.tier === "review").length} review
              </span>
              <span className="font-mono text-[10px] text-text-dim">
                {qualifiedCompanies.filter((c) => c.tier === "rejected").length} rejected
              </span>
            </div>
          )}
        </div>
      )}

      {/* Runs List */}
      {runs.length === 0 && !isLiveRunning && !isLiveComplete ? (
        <div className="bg-surface-2 border border-border rounded-xl px-6 py-16 text-center space-y-4">
          <div className="w-12 h-12 mx-auto bg-surface-3 rounded-full flex items-center justify-center">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-text-dim">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
            </svg>
          </div>
          <p className="font-mono text-xs text-text-dim">
            No pipeline runs yet
          </p>
          <button
            onClick={() => { resetHunt(); router.push("/chat"); }}
            className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
          >
            Start Your First Hunt
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const total = run.hot + run.review + run.rejected;
            const hotPct = total > 0 ? (run.hot / total) * 100 : 0;
            const reviewPct = total > 0 ? (run.review / total) * 100 : 0;
            const rejectedPct = total > 0 ? (run.rejected / total) * 100 : 0;
            const isConfirming = confirmDeleteId === run.id;
            const isDeleting = deletingId === run.id;

            return (
              <div
                key={run.id}
                className="bg-surface-2 border border-border rounded-xl hover:border-border-bright transition-colors group"
              >
                {/* Main row */}
                <div className="p-5 flex items-start gap-4">
                  {/* Status dot */}
                  <div className="mt-1 flex-shrink-0">
                    <div className="w-2.5 h-2.5 rounded-full bg-green-400/80" title="Complete" />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0 space-y-2">
                    <div>
                      <p className="font-mono text-sm text-text-primary font-medium truncate">
                        {run.industry || run.company_profile || "Untitled Search"}
                      </p>
                      {run.technology_focus && (
                        <p className="font-mono text-[10px] text-text-dim truncate mt-0.5">
                          {run.technology_focus}
                        </p>
                      )}
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
                          <span className="font-mono text-[10px] text-hot">
                            {run.hot} hot
                          </span>
                          <span className="font-mono text-[10px] text-review">
                            {run.review} review
                          </span>
                          <span className="font-mono text-[10px] text-text-dim">
                            {run.rejected} rejected
                          </span>
                          <span className="font-mono text-[10px] text-text-dim ml-auto">
                            {run.total_found} found
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right side: date + actions */}
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    {run.created_at && (
                      <span className="font-mono text-[10px] text-text-dim">
                        {new Date(run.created_at).toLocaleDateString()}
                      </span>
                    )}
                    <div className="flex items-center gap-1.5">
                      {/* View leads */}
                      <Link
                        href={`/dashboard/leads?search_id=${run.id}`}
                        className="font-mono text-[10px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md bg-secondary/10 border border-secondary/20 text-secondary hover:bg-secondary/20 transition-colors"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Leads →
                      </Link>

                      {/* Resume */}
                      <button
                        onClick={() => handleResume(run)}
                        className="font-mono text-[10px] uppercase tracking-[0.12em] px-2.5 py-1.5 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-border-bright transition-colors cursor-pointer"
                        title="Resume in chat"
                      >
                        Resume
                      </button>

                      {/* Delete */}
                      {isConfirming ? (
                        <span className="flex items-center gap-1">
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={() => handleDelete(run.id)}
                            onKeyDown={(e) => { if (e.key === "Enter") handleDelete(run.id); }}
                            className="font-mono text-[10px] text-red-400 hover:text-red-300 cursor-pointer px-1.5 py-1"
                          >
                            {isDeleting ? "…" : "Confirm"}
                          </span>
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={() => setConfirmDeleteId(null)}
                            onKeyDown={(e) => { if (e.key === "Enter") setConfirmDeleteId(null); }}
                            className="font-mono text-[10px] text-text-dim hover:text-text-muted cursor-pointer px-1.5 py-1"
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
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
          })}
        </div>
      )}
    </div>
  );
}
