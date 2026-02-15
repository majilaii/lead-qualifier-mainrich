# UX Polish & Cleanup

> **Goal:** Reusable empty states, loading skeletons, error handling, toast notifications, and the HuntContext → PipelineContext rename. Pure polish — no new features.

_Last updated: February 2026_

---

## Build Sequence

```
Day 1:  Shared UI components (EmptyState, Skeleton, ErrorBoundary, Toast)
Day 1:  Wire shared components into all existing pages
Day 2:  HuntContext → PipelineContext rename across the entire codebase
```

---

## 1. Shared UI Components

Currently, every page has ad-hoc loading/error/empty states with inconsistent styling. Create reusable components.

### 1.1 EmptyState Component

**New file: `frontend/src/app/components/ui/EmptyState.tsx`**

A consistent empty state for any page with zero data.

```tsx
interface EmptyStateProps {
  icon?: React.ReactNode;        // Optional icon/emoji at top
  title: string;                  // "No pipelines yet"
  description?: string;           // "Launch your first pipeline..."
  action?: {
    label: string;                // "New Pipeline"
    href?: string;                // Link destination
    onClick?: () => void;         // Or callback
  };
}
```

Visual:
```
┌─────────────────────────────────────┐
│                                     │
│              ◈                      │
│                                     │
│       No pipelines yet              │
│                                     │
│   Launch your first pipeline to     │
│   start discovering leads.          │
│                                     │
│       [+ New Pipeline]              │
│                                     │
└─────────────────────────────────────┘
```

Styling:
- `bg-surface-2 border border-border-dim rounded-xl p-12 text-center`
- Icon: `text-4xl mb-4`
- Title: `font-mono text-sm text-text-primary mb-2`
- Description: `font-mono text-xs text-text-dim mb-6 max-w-sm mx-auto`
- Action button: same style as existing "+ New Pipeline" button

### 1.2 Skeleton Loaders

**New file: `frontend/src/app/components/ui/Skeleton.tsx`**

Reusable skeleton primitives:

```tsx
// Base shimmer block
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-surface-3 rounded-lg ${className}`} />
  );
}

// Pre-composed skeletons for common patterns
export function StatCardSkeleton() { /* 4 stat cards with shimmer */ }
export function TableRowSkeleton({ rows = 5 }: { rows?: number }) { /* n rows */ }
export function LeadDrawerSkeleton() { /* Full drawer layout shimmer */ }
export function FunnelBarSkeleton() { /* Funnel bar + stats shimmer */ }
export function MapSkeleton() { /* Full-width map placeholder */ }
```

Skeleton styling:
- Use `animate-pulse` (built into Tailwind)
- Match exact dimensions of the real components so there's no layout shift
- `bg-surface-3` as the shimmer color (fits the dark theme)

### 1.3 ErrorBoundary

**New file: `frontend/src/app/components/ui/ErrorBoundary.tsx`**

React error boundary with a friendly fallback:

```tsx
interface ErrorFallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
}

function ErrorFallback({ error, resetErrorBoundary }: ErrorFallbackProps) {
  return (
    <div className="bg-surface-2 border border-red-500/20 rounded-xl p-8 text-center">
      <p className="font-mono text-sm text-red-400 mb-2">Something went wrong</p>
      <p className="font-mono text-xs text-text-dim mb-4 max-w-md mx-auto">
        {error.message}
      </p>
      <button onClick={resetErrorBoundary}
        className="font-mono text-[10px] uppercase tracking-[0.15em] text-secondary 
                   border border-secondary/30 px-4 py-2 rounded-lg hover:bg-secondary/10">
        Try Again
      </button>
    </div>
  );
}
```

Use `react-error-boundary` package (lightweight, well-maintained):
```
npm install react-error-boundary
```

### 1.4 Toast Notifications

**New file: `frontend/src/app/components/ui/Toast.tsx`**

A toast system for success/error/info feedback. Options:

**Option A: Build minimal custom toast** (recommended — no dependencies):

```tsx
// ToastProvider wraps the app
// useToast() hook returns { toast } function
// toast({ title, description, variant: "success" | "error" | "info" })

interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: "success" | "error" | "info";
}
```

Visual (bottom-right corner, stacked):
```
                              ┌──────────────────────────┐
                              │ ✓ Pipeline launched       │
                              │   CNC Manufacturers DACH  │
                              └──────────────────────────┘
                              ┌──────────────────────────┐
                              │ ✗ Export failed            │
                              │   Try again in a moment   │
                              └──────────────────────────┘
```

Behavior:
- Auto-dismiss after 4 seconds (success/info) or 8 seconds (error)
- Slide in from right, fade out
- Max 3 visible at once
- Click to dismiss

**Option B: Use `sonner`** (popular, tiny, Next.js-friendly):
```
npm install sonner
```

Either option works. `sonner` is faster to implement, custom is more on-brand.

### 1.5 Quota / Rate Limit Error Pages

**New file: `frontend/src/app/components/ui/QuotaExceeded.tsx`**

Dedicated component for when the user hits their plan limit:

```
┌─────────────────────────────────────┐
│                                     │
│         Monthly limit reached       │
│                                     │
│   You've used 50/50 pipeline runs   │
│   this month on the Free plan.      │
│                                     │
│   Upgrade to Pro for 20 pipelines   │
│   per month + scheduling.           │
│                                     │
│       [Upgrade to Pro — $49/mo]     │
│                                     │
└─────────────────────────────────────┘
```

Reusable for different quota types: pipeline runs, email drafts, enrichments, schedules.

---

## 2. Wire Shared Components Into All Pages

Replace every ad-hoc loading/empty/error state with the shared components.

### Dashboard — `frontend/src/app/dashboard/page.tsx`

| Current | Replace With |
|---------|-------------|
| Inline `loading` check → simple "Loading..." text | `<StatCardSkeleton />` + `<FunnelBarSkeleton />` + `<TableRowSkeleton />` |
| Inline empty state for "No pipelines yet" | `<EmptyState icon="◈" title="No pipelines yet" description="..." action={{ label: "+ New Pipeline", href: "/dashboard/new" }} />` |
| No error handling | Wrap stat/funnel/pipeline fetches with try/catch → show toast on error |

### Pipeline Table — `frontend/src/app/dashboard/pipeline/page.tsx`

| Current | Replace With |
|---------|-------------|
| Loading state (if any) | `<TableRowSkeleton rows={8} />` |
| No leads found | `<EmptyState title="No leads in this pipeline" description="Run a pipeline to start qualifying companies." />` |
| Status change success | `toast({ title: "Status updated", variant: "success" })` |

### Lead Drawer — `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx`

| Current | Replace With |
|---------|-------------|
| Loading enrichment data | `<LeadDrawerSkeleton />` |
| Enrichment error | Inline error banner + retry button |
| Notes/deal value saved | Brief "Saved ✓" → use `toast({ title: "Saved", variant: "success" })` |

### Hunts (Past Runs) — `frontend/src/app/dashboard/hunts/page.tsx`

| Current | Replace With |
|---------|-------------|
| Loading | `<TableRowSkeleton rows={6} />` |
| No hunts | `<EmptyState title="No past hunts" description="Your completed pipeline runs will appear here." action={{ label: "+ New Pipeline", href: "/dashboard/new" }} />` |

### Map — `frontend/src/app/dashboard/map/page.tsx`

| Current | Replace With |
|---------|-------------|
| Map loading | `<MapSkeleton />` (full-width gray box with pulsing dots) |
| No leads with locations | `<EmptyState title="No locations to show" description="Run a pipeline to discover companies and see them on the map." />` |

### Settings — `frontend/src/app/dashboard/settings/page.tsx`

| Current | Replace With |
|---------|-------------|
| Any save action | `toast({ title: "Settings saved", variant: "success" })` |
| Stripe errors | `toast({ title: "Billing error", description: error.message, variant: "error" })` |

### New Pipeline — `frontend/src/app/dashboard/new/page.tsx`

| Current | Replace With |
|---------|-------------|
| Pipeline launch success | `toast({ title: "Pipeline launched", description: name, variant: "success" })` |
| Quota exceeded | `<QuotaExceeded type="pipelines" current={50} limit={50} plan="free" />` |
| Template load error | `toast({ title: "Failed to load template", variant: "error" })` |

### Reddit — `frontend/src/app/dashboard/reddit/page.tsx`

| Current | Replace With |
|---------|-------------|
| Has `{/* Empty state */}` comment | `<EmptyState title="No Reddit signals yet" description="Configure keywords to monitor Reddit for buying signals." />` |

---

## 3. HuntContext → PipelineContext Rename

This is a cosmetic rename that aligns the codebase with the "pipeline-first" mental model from the SAAS_PLAN.

### Files to Change

Based on the current codebase, `HuntContext` (via `useHunt`) is imported in **7 files**:

| File | Changes |
|------|---------|
| `frontend/src/app/components/pipeline/PipelineTracker.tsx` | Primary file — rename context, provider, hook, all exports |
| `frontend/src/app/providers/HuntProvider.tsx` | Rename file → `PipelineProvider.tsx`, rename all internals |
| `frontend/src/app/dashboard/layout.tsx` | Update import path + component name |
| `frontend/src/app/dashboard/new/page.tsx` | `useHunt()` → `usePipeline()` |
| `frontend/src/app/dashboard/page.tsx` | `useHunt()` → `usePipeline()` |
| `frontend/src/app/dashboard/pipeline/page.tsx` | `useHunt()` → `usePipeline()` |
| `frontend/src/app/dashboard/map/page.tsx` | `useHunt()` → `usePipeline()` |

### Rename Map

| Old | New |
|-----|-----|
| `HuntContext` | `PipelineContext` |
| `HuntProvider` | `PipelineProvider` |
| `useHunt()` | `usePipeline()` |
| `HuntProvider.tsx` (file) | `PipelineProvider.tsx` |
| `resetHunt()` | `resetPipeline()` |
| `startHunt()` | `startPipeline()` |

### State/Export Renames

In `PipelineTracker.tsx` (the context definition), rename exports:

| Old Export | New Export |
|------------|-----------|
| `phase` | `phase` (keep — generic enough) |
| `searchCompanies` | `discoveredCompanies` |
| `qualifiedCompanies` | `qualifiedCompanies` (keep) |
| `pipelineProgress` | `pipelineProgress` (keep) |
| `resetHunt` | `resetPipeline` |
| `searchId` | `pipelineId` |

### Process

1. Rename `HuntProvider.tsx` → `PipelineProvider.tsx`
2. Update all internal names in `PipelineTracker.tsx`
3. Update `PipelineProvider.tsx` to use new names
4. Update all 5 consumer files (find & replace `useHunt` → `usePipeline`, `resetHunt` → `resetPipeline`)
5. Update `layout.tsx` import
6. Run `npm run build` to verify no broken imports

### Backend Note

The backend doesn't use "hunt" terminology in its API routes — it already uses `/api/pipeline/*`. No backend changes needed.

---

## 4. Other Minor Cleanup

### 4a. Friendly 404 Page

**New file: `frontend/src/app/not-found.tsx`** (Next.js convention)

```
┌─────────────────────────────────────┐
│                                     │
│              404                    │
│                                     │
│       Page not found                │
│                                     │
│   The page you're looking for       │
│   doesn't exist or was moved.       │
│                                     │
│       [Back to Dashboard]           │
│                                     │
└─────────────────────────────────────┘
```

### 4b. Rate Limit Error Page

For API rate limits (429 responses), show a friendly message instead of a generic error:

```
┌─────────────────────────────────────┐
│                                     │
│         Slow down there 🏎️          │
│                                     │
│   Too many requests. Please wait    │
│   a moment and try again.           │
│                                     │
│       [Try Again]                   │
│                                     │
└─────────────────────────────────────┘
```

### 4c. Consistent Loading Indicator

Replace the various `border-t-secondary rounded-full animate-spin` spinners across login, signup, hunts, dashboard, LeadDrawer, etc. with a shared `<Spinner />` component:

**New file: `frontend/src/app/components/ui/Spinner.tsx`**

```tsx
export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "w-4 h-4", md: "w-6 h-6", lg: "w-8 h-8" };
  return (
    <div className={`${sizes[size]} border-2 border-surface-3 border-t-secondary rounded-full animate-spin`} />
  );
}
```

---

## File Summary

| # | File | Change | Est. Time |
|---|------|--------|-----------|
| 1 | `components/ui/EmptyState.tsx` | **New** — reusable empty state | 20 min |
| 2 | `components/ui/Skeleton.tsx` | **New** — skeleton primitives + composed skeletons | 30 min |
| 3 | `components/ui/ErrorBoundary.tsx` | **New** — React error boundary | 15 min |
| 4 | `components/ui/Toast.tsx` | **New** — toast provider + hook + component | 45 min |
| 5 | `components/ui/QuotaExceeded.tsx` | **New** — plan limit exceeded state | 15 min |
| 6 | `components/ui/Spinner.tsx` | **New** — shared spinner | 5 min |
| 7 | `app/not-found.tsx` | **New** — 404 page | 10 min |
| 8 | `dashboard/page.tsx` | Wire skeletons + empty states + toasts | 30 min |
| 9 | `dashboard/pipeline/page.tsx` | Wire skeletons + empty state + toasts | 20 min |
| 10 | `dashboard/pipeline/LeadDrawer.tsx` | Wire skeleton + toasts | 15 min |
| 11 | `dashboard/hunts/page.tsx` | Wire skeleton + empty state | 15 min |
| 12 | `dashboard/map/page.tsx` | Wire skeleton + empty state | 15 min |
| 13 | `dashboard/new/page.tsx` | Wire quota exceeded + toasts | 15 min |
| 14 | `dashboard/settings/page.tsx` | Wire toasts | 10 min |
| 15 | `dashboard/reddit/page.tsx` | Wire empty state | 5 min |
| 16 | `components/pipeline/PipelineTracker.tsx` | Rename Hunt → Pipeline exports | 30 min |
| 17 | `providers/HuntProvider.tsx` → `PipelineProvider.tsx` | Rename file + internals | 15 min |
| 18 | `dashboard/layout.tsx` | Update import | 2 min |
| 19 | `dashboard/new/page.tsx` | useHunt → usePipeline | 2 min |
| 20 | `dashboard/page.tsx` | useHunt → usePipeline | 2 min |
| 21 | `dashboard/pipeline/page.tsx` | useHunt → usePipeline | 2 min |
| 22 | `dashboard/map/page.tsx` | useHunt → usePipeline | 2 min |

**Total: ~2 days**
