"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../components/auth/SessionProvider";
import { useHunt } from "../../components/hunt/HuntContext";

interface SearchItem {
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

export default function HuntsPage() {
  const { session } = useAuth();
  const router = useRouter();
  const { resumeHunt, resetHunt } = useHunt();
  const [searches, setSearches] = useState<SearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [resuming, setResuming] = useState<string | null>(null);

  const fetchSearches = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const res = await fetch("/api/proxy/searches", {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (res.ok) setSearches(await res.json());
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    fetchSearches();
  }, [fetchSearches]);

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await fetch(`/api/proxy/searches/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session!.access_token}` },
      });
      setSearches((prev) => prev.filter((s) => s.id !== id));
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  };

  const handleResume = async (id: string) => {
    setResuming(id);
    try {
      await resumeHunt(id);
      router.push("/chat");
    } catch (err) {
      console.error("Failed to resume hunt:", err);
      setResuming(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-6 h-6 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-xl font-bold text-text-primary tracking-tight">
            Hunts
          </h1>
          <p className="font-sans text-sm text-text-muted mt-1">
            All your saved searches
          </p>
        </div>
        <button
          onClick={() => { resetHunt(); router.push("/chat"); }}
          className="inline-flex items-center gap-2 bg-text-primary text-void font-mono text-xs font-bold uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-white/85 transition-colors cursor-pointer"
        >
          + New Hunt
        </button>
      </div>

      {searches.length === 0 ? (
        <div className="bg-surface-2 border border-border rounded-xl px-6 py-16 text-center">
          <p className="font-mono text-xs text-text-dim mb-4">
            No hunts yet. Start your first search!
          </p>
          <button
            onClick={() => { resetHunt(); router.push("/chat"); }}
            className="inline-flex items-center gap-2 bg-secondary/10 border border-secondary/20 text-secondary font-mono text-xs uppercase tracking-[0.15em] px-5 py-3 rounded-lg hover:bg-secondary/20 transition-colors cursor-pointer"
          >
            Start Hunting
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {searches.map((s) => (
            <button
              key={s.id}
              onClick={() => handleResume(s.id)}
              disabled={resuming === s.id}
              className="bg-surface-2 border border-border rounded-xl p-5 hover:border-secondary/20 transition-all group text-left cursor-pointer disabled:opacity-60"
            >
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-mono text-xs font-semibold text-text-primary uppercase tracking-[0.1em] truncate flex-1">
                  {s.industry || "Untitled Search"}
                </h3>
                {confirmDelete === s.id ? (
                  <span className="flex items-center gap-1.5 ml-2" onClick={(e) => e.stopPropagation()}>
                    <span role="button" onClick={() => handleDelete(s.id)} className={`font-mono text-[12px] text-red-400 hover:text-red-300 transition-colors cursor-pointer ${deleting === s.id ? "opacity-50 pointer-events-none" : ""}`}>
                      {deleting === s.id ? "…" : "Confirm"}
                    </span>
                    <span role="button" onClick={() => setConfirmDelete(null)} className="font-mono text-[12px] text-text-dim hover:text-text-muted transition-colors cursor-pointer">Cancel</span>
                  </span>
                ) : (
                  <span
                    onClick={(e) => { e.stopPropagation(); setConfirmDelete(s.id); }}
                    role="button"
                    className="text-text-dim hover:text-red-400 transition-colors ml-2 opacity-0 group-hover:opacity-100 cursor-pointer"
                    title="Delete hunt"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                  </span>
                )}
              </div>

              {s.technology_focus && (
                <p className="font-sans text-[12px] text-text-muted leading-relaxed mb-3 line-clamp-2">
                  {s.technology_focus}
                </p>
              )}

              {s.qualifying_criteria && (
                <p className="font-sans text-[12px] text-text-dim leading-relaxed mb-3 line-clamp-1">
                  {s.qualifying_criteria}
                </p>
              )}

              <div className="flex items-center gap-3 mb-3 font-mono text-[12px]">
                <span className="text-hot">{s.hot} hot</span>
                <span className="text-text-dim">·</span>
                <span className="text-review">{s.review} review</span>
                <span className="text-text-dim">·</span>
                <span className="text-text-dim">{s.rejected} rejected</span>
              </div>

              <div className="flex items-center justify-between">
                {s.created_at && (
                  <span className="font-mono text-[12px] text-text-dim">
                    {new Date(s.created_at).toLocaleDateString()}
                  </span>
                )}
                {resuming === s.id ? (
                  <span className="font-mono text-[12px] text-secondary/60 uppercase tracking-[0.15em] flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 border border-secondary/40 border-t-secondary rounded-full animate-spin inline-block" />
                    Loading…
                  </span>
                ) : (
                  <span className="font-mono text-[12px] text-secondary/60 group-hover:text-secondary uppercase tracking-[0.15em] transition-colors">
                    Resume →
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
