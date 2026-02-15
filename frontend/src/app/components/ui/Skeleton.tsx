"use client";

/* ── Base shimmer block ── */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-surface-3 rounded-lg ${className ?? ""}`} />
  );
}

/* ── Stat Card skeleton (matches dashboard stat cards) ── */

export function StatCardSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-surface-2 border border-border rounded-xl p-5">
          <Skeleton className="h-8 w-16 mb-3" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/* ── Table rows skeleton ── */

export function TableRowSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-border-dim">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-4">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-48" />
            <Skeleton className="h-2.5 w-32" />
          </div>
          <div className="flex items-center gap-3">
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-10" />
            <Skeleton className="h-3 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Lead Drawer skeleton ── */

export function LeadDrawerSkeleton() {
  return (
    <div className="px-6 py-6 space-y-6">
      {/* Company header */}
      <div className="flex items-start gap-3">
        <Skeleton className="w-6 h-6 rounded" />
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-28" />
        </div>
      </div>
      {/* Score bar */}
      <div className="bg-surface-2 border border-border rounded-xl p-4 space-y-3">
        <div className="flex justify-between">
          <Skeleton className="h-3 w-12" />
          <Skeleton className="h-5 w-14" />
        </div>
        <Skeleton className="h-2 w-full rounded-full" />
      </div>
      {/* Status buttons */}
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        <div className="flex gap-1.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-7 w-20 rounded-md" />
          ))}
        </div>
      </div>
      {/* Sections */}
      {[1, 2, 3].map((n) => (
        <div key={n} className="bg-surface-2 border border-border rounded-xl p-4 space-y-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
      ))}
    </div>
  );
}

/* ── Funnel bar skeleton ── */

export function FunnelBarSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-4 w-36" />
      <div className="bg-surface-2 border border-border rounded-xl p-5 space-y-3">
        <Skeleton className="h-8 w-full rounded-lg" />
        <div className="flex gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-3 w-16" />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-surface-2 border border-border rounded-xl p-5">
            <Skeleton className="h-8 w-24 mb-3" />
            <Skeleton className="h-3 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Map skeleton ── */

export function MapSkeleton() {
  return (
    <div className="flex h-full">
      {/* Sidebar placeholder */}
      <div className="hidden md:flex flex-col w-80 bg-surface-2 border-r border-border p-4 space-y-4">
        <Skeleton className="h-8 w-full rounded-lg" />
        <div className="grid grid-cols-3 gap-2">
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
          <Skeleton className="h-14 rounded-lg" />
        </div>
        <Skeleton className="h-8 w-full rounded-lg" />
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
      {/* Map area */}
      <div className="flex-1 bg-surface-3 animate-pulse relative">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-text-dim font-mono text-xs uppercase tracking-[0.2em]">
            Loading map…
          </div>
        </div>
      </div>
    </div>
  );
}
