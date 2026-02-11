# Conversion Funnel — Implementation Plan

> **Goal:** Add notes, deal value, and a visual conversion funnel to the pipeline so Mainrich can track leads from discovery → close.

---

## The Funnel

```
New  →  Contacted  →  In Progress  →  Won / Lost
```

The 6 statuses already exist in the DB (`new`, `contacted`, `in_progress`, `won`, `lost`, `archived`). What's missing: **notes**, **deal value**, **status timestamps**, and a **visual funnel dashboard**.

---

## Layer 1: Database — 3 New Columns + Migration

### File: `backend/db/models.py`

Add three columns to the `QualifiedLead` model, after the existing `status` field (around line 117):

| Column             | Type                  | Default    | Purpose                                           |
| ------------------ | --------------------- | ---------- | ------------------------------------------------- |
| `notes`            | `Text, nullable=True` | `None`     | Free-text notes (e.g. "emailed Jenny, waiting")   |
| `deal_value`       | `Float, nullable=True`| `None`     | Estimated deal value in USD                        |
| `status_changed_at`| `DateTime(tz=True)`   | `_utcnow`  | Auto-set when status changes — powers timing metrics |

### File: `backend/supabase_migration.sql` (append)

```sql
-- Funnel: add notes, deal_value, status_changed_at to qualified_leads
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS deal_value DOUBLE PRECISION;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ DEFAULT NOW();
```

**Run migration** via the same asyncpg pattern used before, or directly in Supabase SQL editor.

---

## Layer 2: Backend API — Extend PATCH + New Funnel Endpoint

### File: `backend/chat_server.py`

### 2a. Extend `PATCH /api/leads/{lead_id}/status` (around line 1134)

Current `UpdateLeadStatusRequest` only has `status: str`. Extend it:

```python
class UpdateLeadStatusRequest(BaseModel):
    status: str  # existing
    notes: Optional[str] = None        # NEW
    deal_value: Optional[float] = None  # NEW
```

In the handler:
- If `notes` is provided, update `lead.notes = req.notes`
- If `deal_value` is provided, update `lead.deal_value = req.deal_value`
- Always set `lead.status_changed_at = datetime.utcnow()` when status changes
- Return the updated lead fields in the response (include `notes`, `deal_value`, `status_changed_at`)

### 2b. New endpoint: `GET /api/dashboard/funnel`

Add a new authenticated endpoint that queries `qualified_leads` for the logged-in user and returns:

```json
{
  "stages": {
    "new": 42,
    "contacted": 18,
    "in_progress": 7,
    "won": 3,
    "lost": 5,
    "archived": 2
  },
  "total_pipeline_value": 127500.00,
  "won_value": 45000.00,
  "lost_value": 12000.00,
  "conversion_rate": 7.1,
  "avg_days_to_close": 12.3,
  "total_leads": 77
}
```

**Query logic:**
- Join `qualified_leads` → `searches` → `profiles` to scope to the user
- `GROUP BY status` for stage counts
- `SUM(deal_value) WHERE status = 'won'` for won_value
- `SUM(deal_value) WHERE status NOT IN ('lost', 'archived')` for total_pipeline_value
- Conversion rate = `(won / total non-archived) * 100`
- Avg days to close = `AVG(status_changed_at - created_at) WHERE status = 'won'` (in days)

---

## Layer 3: Frontend — LeadDrawer Notes + Deal Value

### File: `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx`

Add two new sections between the status pills (line ~215) and the industry/type grid (line ~218):

### 3a. Notes Textarea

```tsx
{/* Notes */}
<div className="bg-surface-2 border border-border rounded-xl p-4">
  <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-2">
    Notes
  </h3>
  <textarea
    value={notes}
    onChange={(e) => setNotes(e.target.value)}
    onBlur={saveNotes}
    placeholder="Add notes about this lead..."
    className="w-full bg-surface-3 border border-border rounded-lg p-3 font-sans text-xs text-text-primary placeholder:text-text-dim resize-none focus:outline-none focus:border-secondary/40 min-h-[80px]"
  />
</div>
```

- Local `notes` state initialized from `lead.notes`
- Debounced auto-save on blur — calls PATCH `/api/leads/{id}/status` with `{ status: lead.status, notes: notes }`
- Show a small "Saved ✓" indicator briefly after save

### 3b. Deal Value Input

```tsx
{/* Deal Value */}
<div className="bg-surface-2 border border-border rounded-xl p-4">
  <h3 className="font-mono text-[10px] text-text-muted uppercase tracking-[0.15em] mb-2">
    Deal Value
  </h3>
  <div className="flex items-center gap-2">
    <span className="font-mono text-xs text-text-dim">$</span>
    <input
      type="number"
      value={dealValue ?? ""}
      onChange={(e) => setDealValue(e.target.value ? parseFloat(e.target.value) : null)}
      onBlur={saveDealValue}
      placeholder="0.00"
      className="flex-1 bg-surface-3 border border-border rounded-lg px-3 py-2 font-mono text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-secondary/40"
    />
  </div>
</div>
```

- Same debounced auto-save pattern as notes
- Both `saveNotes` and `saveDealValue` can share the same PATCH call

### 3c. Update the Lead interface

In both `LeadDrawer.tsx` and `pipeline/page.tsx`, add to the Lead interface:

```typescript
notes: string | null;
deal_value: number | null;
status_changed_at: string | null;
```

### 3d. Update `handleStatusChange` callback

When the drawer saves notes/deal_value, also bubble up to the parent so the pipeline list reflects changes without a full refetch. Add `onLeadUpdate` callback prop to `LeadDrawer` alongside existing `onStatusChange`.

---

## Layer 4: Frontend — Dashboard Funnel Widget

### File: `frontend/src/app/dashboard/page.tsx`

### 4a. Fetch funnel data

Add a new `useEffect` that calls `GET /api/dashboard/funnel` and stores in state:

```typescript
interface FunnelData {
  stages: Record<string, number>;
  total_pipeline_value: number;
  won_value: number;
  lost_value: number;
  conversion_rate: number;
  avg_days_to_close: number;
  total_leads: number;
}
```

### 4b. Funnel Bar (below existing stat cards)

A horizontal stacked bar showing proportional segments. Pure Tailwind — no charting library:

```
┌─────────────────────────────────────────────────────────┐
│  NEW (42)  │ CONTACTED (18) │ IN PROGRESS (7) │ WON (3)│
│  ████████████████  ████████  ███████  ███               │
│  gray            blue      amber    green               │
└─────────────────────────────────────────────────────────┘
```

Each segment is a `div` with `width: {percentage}%` and the appropriate background color. Colors match the existing `STATUS_DOT` map from `pipeline/page.tsx`:
- `new` → gray (`bg-text-muted`)
- `contacted` → blue (`bg-blue-400`)
- `in_progress` → amber (`bg-amber-400`)
- `won` → green (`bg-green-400`)
- `lost` → red (`bg-red-400`) — shown separately below the bar

### 4c. Stats Row (below funnel bar)

Four inline stat cards in a grid:

| Label | Value | Source |
|-------|-------|--------|
| Pipeline Value | `$127,500` | `total_pipeline_value` formatted |
| Won Revenue | `$45,000` | `won_value` formatted |
| Conversion Rate | `7.1%` | `conversion_rate` |
| Avg Days to Close | `12.3` | `avg_days_to_close` |

Same card styling as existing stat cards (`bg-surface-2 border border-border rounded-xl p-5`).

### 4d. Add a frontend API route (optional)

If you want to proxy through Next.js, add `frontend/src/app/api/funnel/route.ts` that forwards to the backend. Otherwise, call the backend directly like the existing dashboard stats do.

---

## File Summary

| # | File | Change | Est. Time |
|---|------|--------|-----------|
| 1 | `backend/db/models.py` | +3 columns on `QualifiedLead` | 10 min |
| 2 | `backend/supabase_migration.sql` | Append ALTER TABLE statements | 5 min |
| 3 | `backend/chat_server.py` | Extend PATCH request model + handler, add GET `/api/dashboard/funnel` endpoint | 30 min |
| 4 | `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx` | Add notes textarea, deal value input, auto-save logic | 30 min |
| 5 | `frontend/src/app/dashboard/pipeline/page.tsx` | Add `notes`, `deal_value`, `status_changed_at` to Lead interface | 5 min |
| 6 | `frontend/src/app/dashboard/page.tsx` | Fetch funnel data, render funnel bar + conversion stats row | 45 min |

**Total: ~2 hours**

---

## Implementation Order

1. **Migration SQL** — run it first so the columns exist
2. **db/models.py** — add the 3 new mapped columns
3. **chat_server.py** — extend PATCH, add funnel endpoint
4. **Restart backend** — verify endpoints work (`curl` test)
5. **LeadDrawer.tsx** — notes + deal value UI
6. **pipeline/page.tsx** — update Lead interface
7. **dashboard/page.tsx** — funnel widget
8. **Test end-to-end** — open a lead, add notes + deal value, change status, check dashboard funnel

---

## Existing Code References

- **QualifiedLead model:** `backend/db/models.py` line 89–127
- **PATCH status endpoint:** `backend/chat_server.py` line ~1134
- **UpdateLeadStatusRequest:** `backend/chat_server.py` line ~1120
- **Dashboard stats endpoint:** `backend/chat_server.py` line ~811
- **LeadDrawer status pills:** `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx` line ~200
- **Pipeline Lead interface:** `frontend/src/app/dashboard/pipeline/page.tsx` line ~8
- **Dashboard stat cards:** `frontend/src/app/dashboard/page.tsx` line ~118
- **STATUS_DOT colors:** `frontend/src/app/dashboard/pipeline/page.tsx` line ~44
