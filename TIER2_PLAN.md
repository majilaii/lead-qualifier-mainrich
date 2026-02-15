# Tier 2 — Automation & Engagement

> **Goal:** Turn Hunt from a manual tool into an autonomous lead gen machine. Users wake up to new leads, get outreach drafted, and stay informed when things change.

_Last updated: February 2026_

---

## Build Sequence

```
Day 1-2:  Scheduled Pipelines (backend scheduler + frontend UI)
Day 2:    Email Notifications (Resend — required for schedules)
Day 3-4:  AI Email Drafts (LLM generation + LeadDrawer UI)
Day 4-5:  Re-qualification Alerts (re-crawl + score change detection)
```

---

## 2.1 Scheduled / Recurring Pipelines

_The killer feature. Pipelines run on autopilot. New leads appear in your database while you sleep._

### Database — New `pipeline_schedules` Table

**File: `backend/db/models.py`** — add after `SearchTemplate`:

```python
class PipelineSchedule(Base):
    __tablename__ = "pipeline_schedules"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False)
    name        = Column(Text, nullable=False)                          # "CNC Manufacturers DACH — Weekly"
    pipeline_config = Column(JSONB, nullable=False)                     # Full PipelineCreateRequest payload
    frequency   = Column(Text, nullable=False)                          # "daily" | "weekly" | "biweekly" | "monthly"
    is_active   = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=False)
    last_run_id = Column(UUID(as_uuid=True), nullable=True)             # FK to searches.id (last pipeline run)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("Profile", backref="schedules")
```

**Migration SQL** (append to `supabase_migration.sql` or run directly):

```sql
CREATE TABLE IF NOT EXISTS pipeline_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) NOT NULL,
    name TEXT NOT NULL,
    pipeline_config JSONB NOT NULL,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'biweekly', 'monthly')),
    is_active BOOLEAN DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ NOT NULL,
    last_run_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_schedules_next_run ON pipeline_schedules(next_run_at) WHERE is_active = TRUE;
CREATE INDEX idx_schedules_user ON pipeline_schedules(user_id);
```

### Backend — Scheduler Engine

**New file: `backend/scheduler.py`**

Responsibilities:
- Run an async loop that checks `pipeline_schedules` every 60 seconds
- For each schedule where `next_run_at <= now()` and `is_active = TRUE`:
  1. Check user quota (skip + log if exceeded)
  2. Call the same internal pipeline creation logic used by `POST /api/pipeline/create`
  3. Update `last_run_at`, `last_run_id`, compute `next_run_at`
  4. Send email notification when pipeline completes (calls notification service)
- All runs are fire-and-forget background tasks (same pattern as existing pipeline runs)

```python
import asyncio
from datetime import datetime, timedelta

FREQUENCY_DELTAS = {
    "daily":    timedelta(days=1),
    "weekly":   timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly":  timedelta(days=30),
}

async def scheduler_loop():
    """Main scheduler loop — runs every 60s, checks for due schedules."""
    while True:
        try:
            async with get_session() as db:
                due = await db.execute(
                    select(PipelineSchedule)
                    .where(PipelineSchedule.is_active == True)
                    .where(PipelineSchedule.next_run_at <= datetime.utcnow())
                )
                for schedule in due.scalars().all():
                    asyncio.create_task(run_scheduled_pipeline(schedule))
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(60)

async def run_scheduled_pipeline(schedule: PipelineSchedule):
    """Execute a single scheduled pipeline run."""
    # 1. Check user quota
    # 2. Create pipeline (reuse internal _create_and_run_pipeline logic)
    # 3. Update schedule: last_run_at, last_run_id, compute next_run_at
    # 4. On completion callback → send email notification
    next_run = datetime.utcnow() + FREQUENCY_DELTAS[schedule.frequency]
    schedule.last_run_at = datetime.utcnow()
    schedule.next_run_at = next_run
    # ... save to DB
```

**Wire into FastAPI lifespan** in `backend/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    from db import init_db
    await init_db()
    engine = ChatEngine()

    # Start scheduler
    from scheduler import scheduler_loop
    scheduler_task = asyncio.create_task(scheduler_loop())

    yield

    # Cleanup
    scheduler_task.cancel()
```

### Backend — Schedule CRUD Endpoints

**File: `backend/chat_server.py`** — add 5 new endpoints:

#### `POST /api/schedules`
Create a new schedule from a pipeline config.

Request:
```json
{
  "name": "CNC Manufacturers DACH — Weekly",
  "pipeline_config": {
    "mode": "discover",
    "search_context": { "industry": "CNC machining", "geographic_region": "DACH" },
    "options": { "use_vision": true, "max_leads": 100 }
  },
  "frequency": "weekly"
}
```

Logic:
- Validate `frequency` is one of: daily, weekly, biweekly, monthly
- Compute `next_run_at` based on frequency (first run = now + frequency)
- Check SaaS tier gating: Free = 0 schedules, Pro = 2, Enterprise = unlimited
- Save to `pipeline_schedules`
- Return the created schedule

Response:
```json
{
  "id": "uuid",
  "name": "CNC Manufacturers DACH — Weekly",
  "frequency": "weekly",
  "is_active": true,
  "next_run_at": "2026-02-21T10:00:00Z",
  "created_at": "2026-02-14T10:00:00Z"
}
```

#### `GET /api/schedules`
List all schedules for the authenticated user.

Response:
```json
{
  "schedules": [
    {
      "id": "uuid",
      "name": "CNC Manufacturers DACH — Weekly",
      "frequency": "weekly",
      "is_active": true,
      "last_run_at": "2026-02-14T10:00:00Z",
      "next_run_at": "2026-02-21T10:00:00Z",
      "last_run_id": "uuid-of-search",
      "last_run_summary": { "hot": 5, "review": 12, "rejected": 8 }
    }
  ]
}
```

The `last_run_summary` is a join against the `qualified_leads` table for the `last_run_id` search — counts by tier.

#### `PATCH /api/schedules/{id}`
Update a schedule (pause/resume, change frequency, rename).

Request (all fields optional):
```json
{
  "is_active": false,
  "frequency": "monthly",
  "name": "Updated name"
}
```

- When `is_active` changes to `true`, recompute `next_run_at` from now
- When `frequency` changes, recompute `next_run_at`

#### `DELETE /api/schedules/{id}`
Delete a schedule. Verify ownership.

#### `POST /api/schedules/{id}/run-now`
Trigger an immediate run of a schedule (outside its normal cadence). Useful for "I don't want to wait until next week."

- Creates a pipeline from the schedule's `pipeline_config`
- Updates `last_run_at` and `last_run_id` but does NOT change `next_run_at`

### Frontend — Schedule UI

#### Schedule creation: "Schedule this" toggle on pipeline config

**File: `frontend/src/app/dashboard/new/page.tsx`**

After the existing "Launch Pipeline" button area, add a schedule toggle:

```
┌─────────────────────────────────────────────┐
│  [Launch Pipeline]    [Schedule Instead ▾]  │
│                                             │
│  ┌─── Schedule Options (collapsed) ───────┐ │
│  │  Frequency:  ○ Daily  ● Weekly         │ │
│  │              ○ Biweekly  ○ Monthly     │ │
│  │  Name: [CNC Manufacturers DACH — Wkly] │ │
│  │  [Create Schedule]                     │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

- Toggle reveals frequency picker
- "Create Schedule" calls `POST /api/schedules`
- Redirect to dashboard with success toast

#### Schedule list: Dashboard section

**File: `frontend/src/app/dashboard/page.tsx`**

Add a "Scheduled Pipelines" section between the stat cards and the recent pipeline runs table:

```
┌─────────────────────────────────────────────────────────┐
│  SCHEDULED PIPELINES                                     │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │  🔁 CNC Manufacturers DACH              Weekly    │   │
│  │     Next run: Feb 21, 2026                        │   │
│  │     Last run: 5 hot, 12 review (Feb 14)           │   │
│  │     [Run Now]  [Pause]  [Delete]                  │   │
│  └───────────────────────────────────────────────────┘   │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │  ⏸ Servo Motor Buyers USA              Monthly    │   │
│  │     Paused                                        │   │
│  │     Last run: 3 hot, 8 review (Feb 1)             │   │
│  │     [Resume]  [Delete]                            │   │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

- Fetch from `GET /api/schedules` on mount
- "Run Now" calls `POST /api/schedules/{id}/run-now`
- "Pause" / "Resume" calls `PATCH /api/schedules/{id}` with `{ is_active: false/true }`
- "Delete" calls `DELETE /api/schedules/{id}` with confirmation
- Empty state: "No scheduled pipelines yet. Create one from + New Pipeline."

#### "Schedule this" on completed pipeline runs

**File: `frontend/src/app/dashboard/page.tsx`** (recent runs table)

Add a "🔁 Schedule" button on each completed pipeline row. Clicking it:
1. Reads the pipeline's `search_context` from the existing data
2. Opens a small modal with frequency picker + name field
3. Calls `POST /api/schedules` with the pipeline's config
4. Shows success toast

### SaaS Tier Gating

| Plan | Max Schedules |
|------|---------------|
| Free | 0 |
| Pro | 2 |
| Enterprise | Unlimited |

Check in both:
- Backend: `POST /api/schedules` rejects with 403 + clear message if at limit
- Frontend: Show upgrade modal instead of schedule UI for free users

### Requirements

Add to `backend/requirements.txt`:
```
# No new deps needed — using asyncio loop, not APScheduler
```

The scheduler is a simple async loop inside the FastAPI lifespan. No external dependency needed. If we later need cron expressions or more complex scheduling, we can add `APScheduler` then.

---

## 2.2 Email Notifications (Resend)

_Required for scheduled pipelines to be useful. Also powers re-qualification alerts._

### Setup

**Install:** Add `resend` to `backend/requirements.txt`:
```
resend==2.0.0
```

**Config:** Add to `backend/config.py`:
```python
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
NOTIFICATION_FROM_EMAIL = "Hunt <notifications@yourdomain.com>"  # Resend verified domain
APP_URL = os.getenv("APP_URL", "http://localhost:3000")
```

### Backend — Notification Service

**New file: `backend/notifications.py`**

```python
import resend
from config import RESEND_API_KEY, NOTIFICATION_FROM_EMAIL, APP_URL

resend.api_key = RESEND_API_KEY

async def send_pipeline_complete(user_email: str, user_name: str, pipeline_name: str,
                                  search_id: str, hot: int, review: int, total: int):
    """Send notification when a pipeline (manual or scheduled) completes."""
    resend.Emails.send({
        "from": NOTIFICATION_FROM_EMAIL,
        "to": user_email,
        "subject": f"◈ Pipeline complete — {hot} hot leads found",
        "html": f"""
            <h2>Hey {user_name},</h2>
            <p>Your pipeline <strong>{pipeline_name}</strong> just finished.</p>
            <table>
                <tr><td>🔥 Hot leads:</td><td><strong>{hot}</strong></td></tr>
                <tr><td>👀 Review:</td><td><strong>{review}</strong></td></tr>
                <tr><td>📊 Total qualified:</td><td><strong>{total}</strong></td></tr>
            </table>
            <p><a href="{APP_URL}/dashboard/pipeline?search={search_id}">View results →</a></p>
        """
    })

async def send_scheduled_run_complete(user_email: str, user_name: str,
                                       schedule_name: str, search_id: str,
                                       hot: int, review: int, new_leads: int):
    """Send notification when a scheduled pipeline run completes."""
    resend.Emails.send({
        "from": NOTIFICATION_FROM_EMAIL,
        "to": user_email,
        "subject": f"◈ Scheduled hunt complete — {new_leads} new leads",
        "html": f"""
            <h2>Hey {user_name},</h2>
            <p>Your scheduled pipeline <strong>{schedule_name}</strong> ran automatically.</p>
            <table>
                <tr><td>🆕 New leads found:</td><td><strong>{new_leads}</strong></td></tr>
                <tr><td>🔥 Hot:</td><td><strong>{hot}</strong></td></tr>
                <tr><td>👀 Review:</td><td><strong>{review}</strong></td></tr>
            </table>
            <p><a href="{APP_URL}/dashboard/pipeline?search={search_id}">View results →</a></p>
            <p style="color: #888; font-size: 12px;">
                Manage your schedules in <a href="{APP_URL}/dashboard">Dashboard</a>
            </p>
        """
    })

async def send_requalification_alert(user_email: str, user_name: str,
                                      changed_leads: list[dict]):
    """Send notification when re-qualified leads have score changes."""
    rows = "".join(
        f"<tr><td>{l['name']}</td><td>{l['old_score']}→{l['new_score']}</td><td>{l['change']}</td></tr>"
        for l in changed_leads
    )
    resend.Emails.send({
        "from": NOTIFICATION_FROM_EMAIL,
        "to": user_email,
        "subject": f"◈ {len(changed_leads)} leads changed score this week",
        "html": f"""
            <h2>Hey {user_name},</h2>
            <p>{len(changed_leads)} of your leads had score changes after re-qualification:</p>
            <table>
                <tr><th>Company</th><th>Score</th><th>Change</th></tr>
                {rows}
            </table>
            <p><a href="{APP_URL}/dashboard/pipeline">View leads →</a></p>
        """
    })

async def send_welcome(user_email: str, user_name: str):
    """Send welcome email on signup."""
    resend.Emails.send({
        "from": NOTIFICATION_FROM_EMAIL,
        "to": user_email,
        "subject": "Welcome to Hunt ◈",
        "html": f"""
            <h2>Welcome, {user_name}!</h2>
            <p>Hunt is your AI agent swarm for B2B lead discovery.</p>
            <p><a href="{APP_URL}/dashboard/new">Launch your first pipeline →</a></p>
        """
    })
```

### Integration Points

1. **Pipeline completion callback** — in `backend/pipeline_engine.py`, after the pipeline finishes (all stages complete), call `send_pipeline_complete()`
2. **Scheduled run completion** — in `backend/scheduler.py`, after `run_scheduled_pipeline()` finishes, call `send_scheduled_run_complete()`
3. **Re-qualification** — see section 2.4 below
4. **Welcome email** — in the signup flow or first-login detection

### Frontend — Notification Settings

**File: `frontend/src/app/dashboard/settings/page.tsx`**

Add a "Notifications" section:

```
┌─────────────────────────────────────────────────────┐
│  NOTIFICATIONS                                       │
│                                                      │
│  ☑ Pipeline complete      — when a pipeline finishes │
│  ☑ Scheduled run results  — when a scheduled run     │
│                              finds new leads         │
│  ☑ Re-qualification alerts — when lead scores change │
│  ☐ Weekly digest          — summary of all activity  │
└─────────────────────────────────────────────────────┘
```

Store preferences as JSONB on the `profiles` table:
```sql
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT
  '{"pipeline_complete": true, "scheduled_run": true, "requalification": true, "weekly_digest": false}';
```

Check these flags before sending any notification in `notifications.py`.

---

## 2.3 AI Email Drafts

_Close the loop from discovery → outreach. "Draft Email" button on hot leads generates a personalized cold email from deep research data._

### Backend — Email Draft Endpoint

**File: `backend/chat_server.py`** — add new endpoint:

#### `POST /api/leads/{lead_id}/draft-email`

Request:
```json
{
  "tone": "consultative",
  "sender_context": "We manufacture custom NdFeB magnets for industrial applications"
}
```

`tone` options: `"formal"` | `"casual"` | `"consultative"` (default: `"consultative"`)

`sender_context` is optional — pulled from user's profile or previous chats if not provided.

Logic:
1. Fetch lead from DB (verify ownership)
2. Fetch `deep_research` JSON from the lead (if exists)
3. Fetch `lead_contacts` for the lead — pick the best contact (highest seniority: CEO > VP > Director > Manager)
4. Build LLM prompt with: company name, industry, signals, deep research brief, contact name + title, sender context, tone preference
5. Call Kimi API (same pattern as deep research) → generate email
6. Return draft

Response:
```json
{
  "draft": {
    "to_name": "Thomas Müller",
    "to_title": "Head of Purchasing",
    "to_email": "t.mueller@acme-cnc.de",
    "subject": "Custom magnets for your servo motor line",
    "body": "Dear Thomas,\n\nI noticed ACME CNC recently expanded...",
    "tone": "consultative"
  },
  "context_used": {
    "deep_research": true,
    "contact_source": "website",
    "signals_count": 4
  }
}
```

#### LLM Prompt Structure

```
You are a B2B cold email expert. Write a personalized cold email.

SENDER: {sender_context}
RECIPIENT: {contact_name}, {contact_title} at {company_name}
COMPANY INTEL:
- Industry: {industry}
- Products: {deep_research.products_found}
- Technologies: {deep_research.technologies_used}
- Size: {deep_research.company_size_estimate}
- Volume potential: {deep_research.potential_volume}
- Suggested pitch angle: {deep_research.suggested_pitch_angle}
- Talking points: {deep_research.talking_points}
- Key signals: {lead.reasoning}

TONE: {tone}

Rules:
- Max 150 words
- Reference something specific about THEIR business (not generic)
- One clear CTA (meeting, call, reply)
- No "I hope this email finds you well" or other filler
- Subject line: specific, no clickbait, under 8 words
```

#### Batch Draft Endpoint

**`POST /api/leads/batch-draft-email`**

Request:
```json
{
  "lead_ids": ["uuid1", "uuid2", "uuid3"],
  "tone": "consultative",
  "sender_context": "We manufacture custom NdFeB magnets"
}
```

- Runs drafts in parallel (asyncio.gather)
- Returns array of drafts
- Gated: Pro = 20 drafts/mo, Enterprise = unlimited

### Frontend — Draft Email UI

#### LeadDrawer: "Draft Email" Button

**File: `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx`**

Add a "Draft Email" button in the action buttons area (near the status pills / recrawl buttons):

```tsx
{/* Email Draft Button — only show for hot leads with contacts */}
{lead.tier === "hot" && (
  <button
    onClick={() => setShowEmailDraft(true)}
    className="flex items-center gap-1.5 bg-secondary/10 border border-secondary/20 text-secondary 
               font-mono text-[10px] uppercase tracking-[0.15em] px-3 py-2 rounded-lg 
               hover:bg-secondary/20 transition-colors cursor-pointer"
  >
    ✉ Draft Email
  </button>
)}
```

#### Email Draft Modal

**New component: `frontend/src/app/dashboard/pipeline/EmailDraftModal.tsx`**

```
┌──────────────────────────────────────────────────────────┐
│  DRAFT EMAIL                                        [×]  │
│                                                          │
│  To: Thomas Müller, Head of Purchasing                   │
│      t.mueller@acme-cnc.de                               │
│                                                          │
│  Tone: [Consultative ▾]  [Formal]  [Casual]             │
│                                                          │
│  Your context (optional):                                │
│  ┌────────────────────────────────────────────────────┐  │
│  │ We manufacture custom NdFeB magnets for industrial │  │
│  │ applications                                       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Generate Draft]                                        │
│                                                          │
│  ─── Generated Draft ──────────────────────────────────  │
│                                                          │
│  Subject: Custom magnets for your servo motor line       │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Dear Thomas,                                       │  │
│  │                                                    │  │
│  │ I noticed ACME CNC recently expanded your servo    │  │
│  │ motor line to include the SM-400 series. We        │  │
│  │ specialize in custom NdFeB magnets for exactly     │  │
│  │ this type of application...                        │  │
│  │                                                    │  │
│  │ [editable textarea]                                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Copy to Clipboard]  [Open in Mail Client]  [Regenerate]│
└──────────────────────────────────────────────────────────┘
```

Behavior:
- `sender_context` saved to localStorage so it persists across drafts
- Draft is editable — user can tweak before copying
- "Copy to Clipboard" copies subject + body
- "Open in Mail Client" opens `mailto:` link with subject + body pre-filled
- "Regenerate" calls the API again with same params
- Loading state while generating (show spinner + "Drafting personalized email...")

#### Batch Draft from Pipeline Table

**File: `frontend/src/app/dashboard/pipeline/page.tsx`**

Add a batch action when multiple hot leads are selected:

```
[✉ Draft Emails for 5 Hot Leads]
```

- Calls `POST /api/leads/batch-draft-email`
- Opens a results view showing all drafts stacked
- Each draft is individually editable + copyable

### SaaS Tier Gating

| Plan | Email Drafts / month |
|------|---------------------|
| Free | 0 |
| Pro | 20 |
| Enterprise | Unlimited |

Track in `usage_tracking` table with a new counter field or a separate `email_drafts` counter for the month.

### Requirements

No new backend dependencies — reuses existing Kimi LLM client.

---

## 2.4 Re-qualification Alerts

_Monthly re-crawl of your top leads. If their website changes, re-score and alert._

### How It Works

The infrastructure for this is **mostly already built**:
- `EnrichmentJob` model exists with `job_type = "requalify"`
- `LeadSnapshot` model exists (stores score + signals + timestamp per re-qualification)
- LeadDrawer already has "Requalify" button that triggers a recrawl

What's missing: **automated periodic re-qualification + change detection + alerting.**

### Backend — Re-qualification Scheduler

**Add to `backend/scheduler.py`** — a second loop (or extend the main loop):

```python
async def requalification_loop():
    """Runs daily. Re-qualifies top leads older than 30 days."""
    while True:
        try:
            async with get_session() as db:
                # Find users with Pro/Enterprise plans
                # For each user, find hot leads (score 8+) not re-qualified in 30+ days
                # Create requalify enrichment jobs for top 20 leads
                # After completion, compare old vs new scores
                # If any changed by ±2 → queue notification
                pass
        except Exception as e:
            logger.error(f"Requalification error: {e}")
        await asyncio.sleep(86400)  # Run daily
```

Logic per user:
1. Query `qualified_leads` where `tier = 'hot'` and `status NOT IN ('won', 'lost', 'archived')`
2. Exclude leads re-qualified in the last 30 days (check `lead_snapshots` table)
3. For each eligible lead (cap at 20/user/run):
   a. Create an `EnrichmentJob` with `job_type = "requalify"`
   b. Pipeline engine re-crawls + re-scores
   c. New snapshot saved to `lead_snapshots`
4. After all jobs complete, compare snapshots:
   - If `abs(new_score - old_score) >= 2` → flag as "changed"
   - If new signals appear that weren't in the old snapshot → flag
5. Collect all changed leads → call `send_requalification_alert()`

### Frontend — Score Change Indicators

#### Score Trend Indicator on Lead Cards

**File: `frontend/src/app/dashboard/pipeline/page.tsx`**

Next to the score badge, show a trend arrow if snapshots exist:

```tsx
{lead.score_trend === "up" && <span className="text-green-400 text-[10px]">↑</span>}
{lead.score_trend === "down" && <span className="text-red-400 text-[10px]">↓</span>}
{lead.score_trend === "stable" && <span className="text-text-dim text-[10px]">→</span>}
```

#### Dashboard Notification Badge

**File: `frontend/src/app/dashboard/page.tsx`**

Add an alert card when there are recent score changes:

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ 3 leads changed score this week                      │
│                                                          │
│  ACME CNC         7 → 9  ↑  (new product line detected) │
│  Müller GmbH      8 → 6  ↓  (website down / redesigned) │
│  TechServo AG     6 → 8  ↑  (expansion announcement)    │
│                                                          │
│  [View in Pipeline →]                                    │
└─────────────────────────────────────────────────────────┘
```

#### LeadDrawer — Score History

**File: `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx`**

Add a "Score History" section that shows snapshots over time:

```
SCORE HISTORY
  Feb 14  ●───── 9/10  "Added servo motor line, new B2B partnerships"
  Jan 15  ●───── 7/10  "Initial qualification"
```

Backend endpoint needed: `GET /api/leads/{id}/snapshots` — returns all `lead_snapshots` for the lead, ordered by `created_at DESC`.

### SaaS Tier Gating

| Plan | Re-qualification |
|------|-----------------|
| Free | ❌ Manual only (existing button) |
| Pro | Auto monthly, top 50 leads |
| Enterprise | Auto weekly, all hot leads |

---

## File Summary

| # | File | Change | Est. Time |
|---|------|--------|-----------|
| 1 | `backend/db/models.py` | Add `PipelineSchedule` model + `notification_prefs` on Profile | 20 min |
| 2 | `backend/supabase_migration.sql` | Pipeline schedules table + notification_prefs column | 10 min |
| 3 | `backend/scheduler.py` | **New** — scheduler loop + re-qualification loop | 2 hrs |
| 4 | `backend/main.py` | Wire scheduler into FastAPI lifespan | 10 min |
| 5 | `backend/chat_server.py` | Schedule CRUD endpoints (5) + email draft endpoint (2) | 2 hrs |
| 6 | `backend/notifications.py` | **New** — Resend email sending (4 notification types) | 1 hr |
| 7 | `backend/requirements.txt` | Add `resend==2.0.0` | 1 min |
| 8 | `frontend/src/app/dashboard/new/page.tsx` | Schedule toggle + frequency picker | 1 hr |
| 9 | `frontend/src/app/dashboard/page.tsx` | Scheduled Pipelines section + re-qual alert card | 1.5 hrs |
| 10 | `frontend/src/app/dashboard/pipeline/EmailDraftModal.tsx` | **New** — email draft modal component | 1.5 hrs |
| 11 | `frontend/src/app/dashboard/pipeline/LeadDrawer.tsx` | Draft Email button + score history section | 1 hr |
| 12 | `frontend/src/app/dashboard/pipeline/page.tsx` | Score trend indicators + batch draft button | 30 min |
| 13 | `frontend/src/app/dashboard/settings/page.tsx` | Notification preferences toggles | 30 min |

**Total: ~4-5 days**
