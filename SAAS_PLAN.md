# ◈ Hunt — SaaS Roadmap (v3 — Pipeline-First)

> Dual-purpose: power Mainrich's own lead generation across Europe & America **and** evolve into a paid SaaS product.

_Last updated: February 2026_

---

## Positioning

**Don't compete as "another lead gen tool."** Clay, Apollo, and Instantly will crush you on database size, integrations, and brand.

**Win on:** _"AI agent swarm that systematically hunts B2B leads your competitors can't find."_

Best-fit verticals (where databases fail):
- **Manufacturing / hardware / industrial** — no LinkedIn presence, no Crunchbase profile, no BuiltWith tech stack
- **International / emerging markets** — blind spots in US-centric databases
- **Highly specific ICPs** — "companies that use servo motors in their products" — no database has that filter, but Hunt reads the product page and figures it out

---

## Core Architecture — Pipeline First

The **pipeline** is the central primitive, not the chat. A pipeline is an autonomous agent swarm that discovers, crawls, qualifies, and enriches leads — and it can be launched from anywhere.

```
                         ┌──────────────────────────────┐
                         │         PIPELINE ENGINE       │
                         │                               │
                         │  ┌─────────┐  ┌───────────┐  │
                         │  │Discovery│  │  Crawl     │  │
                         │  │ Agents  │──│  Agents    │  │
                         │  └─────────┘  └─────┬─────┘  │
                         │                     │        │
                         │  ┌──────────┐ ┌─────▼─────┐  │
                         │  │ Enrich   │ │ Qualify    │  │
                         │  │ Agents   │◄│ Agents     │  │
                         │  └────┬─────┘ └───────────┘  │
                         │       │                       │
                         │  ┌────▼──────────┐            │
                         │  │Deep Research   │            │
                         │  │Agents (hot 8+) │            │
                         │  └───────────────┘            │
                         └──────────────▲───────────────┘
                                        │
                    ┌───────────────────┼──────────────────┐
                    │                   │                   │
           ┌────────┴────────┐ ┌───────┴────────┐ ┌───────┴───────┐
           │  GUIDED (Chat)  │ │ MANUAL CONFIG  │ │ PROGRAMMATIC  │
           │                 │ │  (Form UI)     │ │               │
           │  New users,     │ │  Power users,  │ │  API calls,   │
           │  new ICPs,      │ │  saved ICPs,   │ │  Scheduled,   │
           │  exploration    │ │  bulk import   │ │  Webhooks     │
           └─────────────────┘ └────────────────┘ └───────────────┘
```

### Five Entry Points, One Engine

| Entry Point | Who | How | Chat Required? |
|---|---|---|---|
| **Chat (guided)** | New users, new ICPs | Conversational ICP definition → auto-launches pipeline | Yes (by choice) |
| **Manual config (form)** | Power users | Form: industry, geo, criteria, go → pipeline runs | No |
| **Saved templates** | Repeat users | One-click from dashboard → pipeline runs | No |
| **Bulk import** | Users with lists | Paste domains or CSV → qualify + enrich pipeline | No |
| **API / Scheduled** | Automation | `POST /api/v1/pipeline/run` with config payload | No |

### Pipeline as Visible Entity

Every pipeline run is a **first-class object** on the dashboard:

```
Pipeline #47 — "CNC Manufacturers DACH"
Status: Running (3/5 stages complete)
├── Discovery:    ████████████████████ 8/8 queries done     (42 companies found)
├── Crawling:     ██████████████░░░░░░ 34/42 sites crawled
├── Qualifying:   ██████████░░░░░░░░░░ 28/34 scored          (7 hot, 15 review)
├── Enriching:    ████░░░░░░░░░░░░░░░░ 3/7 hot leads enriched
└── Deep Research: ░░░░░░░░░░░░░░░░░░░ waiting for enrichment
```

- Can be paused, cancelled, or restarted
- Agents work in parallel (not sequentially through a chat)
- Results stream into the dashboard in real-time
- Multiple pipelines can run concurrently

### Dashboard is the Command Center

```
┌─────────────────────────────────────────────────────────┐
│  ◈ Hunt Dashboard                                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Active   │  │  Lead    │  │  Templates│  │  Map    │ │
│  │  Pipelines│  │  Database│  │  & ICPs   │  │  View   │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│                                                          │
│  ┌──────────────────────────────┐                        │
│  │  + New Pipeline               │                       │
│  │  ┌────────┐ ┌──────┐ ┌─────┐│                        │
│  │  │ Guided │ │ Form │ │Bulk ││                        │
│  │  │ (Chat) │ │Config│ │Imp. ││                        │
│  │  └────────┘ └──────┘ └─────┘│                        │
│  └──────────────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

- Landing page for logged-in users is the **dashboard**, not the chat
- Chat is accessible as one option from "New Pipeline"
- All pipeline results, leads, and stats live on the dashboard
- The chat is a "wizard" — helpful, but not the product

---

## Data Strategy — Three Layers (No Monthly Subscriptions)

Instead of paying $80-200/mo for Apollo + Sales Nav + Hunter forever, Hunt builds a **compounding proprietary database** from free/cheap sources:

```
LAYER 1 — DISCOVERY (free, unlimited)                          ← BUILT
  Exa search → website crawl → AI qualification
  Cost: ~$0.01/lead (LLM + Exa)

LAYER 2 — PEOPLE (free or cheap, API-based)                    ← PARTIALLY BUILT
  Hunter.io free tier (50/mo) for email lookup
  Contact page scraper (names/emails/phones from /about, /team, /contact)
  Cost: $0 for scraper, $0.02/lead for Hunter

LAYER 3 — LINKEDIN ENRICHMENT (pay-per-use, hot leads only)    ← NOT BUILT
  People Data Labs or RocketReach API for LinkedIn profiles + emails + phones
  Only triggered on score 8+ leads — not every lead
  Cost: ~$0.01-0.05/lead, only on ~10-20% of leads
```

**Why this wins:** Every pipeline run adds to the database. Re-crawls keep it fresh. Over 6 months, you have thousands of qualified, enriched leads with zero ongoing subscription cost.

---

## Current State (what's built)

| ✅ Done | Status |
|---------|--------|
| Multi-tenant auth (Supabase) | Shipped |
| Chat-based ICP definition (dual-LLM) | Shipped |
| Exa AI search + web crawling + AI qualification | Shipped |
| Live pipeline streaming (SSE) | Shipped |
| Dashboard (stats, hunts, pipeline table, lead drawer) | Shipped |
| Interactive map (Mapbox GL, live dots, fly-to) | Shipped |
| Chat persistence + hunt resume | Shipped |
| Pipeline CRM (new → contacted → in_progress → won/lost) | Shipped |
| Funnel tracking (notes, deal value, status timestamps) | Shipped |
| Contact enrichment (Hunter.io free-tier API) | Shipped |
| Contact page sniffing (/about, /team, /contact crawl) | Shipped |
| Deep research on hot leads (multi-page analysis) | Shipped |
| Stripe billing (checkout, portal, webhooks) | Shipped |
| Usage tracking + quota enforcement | Shipped |
| Pricing page wired to Stripe | Shipped |
| Onboarding overlay (first-visit guided tour) | Shipped |
| Upgrade modals + usage meter in chat | Shipped |
| Docker deployment (hot-reload dev mode) | Shipped |

---

## 🔴 Tier 1 — Pipeline-First Restructure

_Decouple the pipeline from the chat. Make the dashboard the command center. Add multiple entry points. Target: 1-2 weeks._

### 1.0 Pipeline-First Architecture Refactor
**Effort:** 2-3 days · **Impact:** 🔥🔥🔥🔥 (foundational — everything else builds on this)

The backend pipeline endpoints are already decoupled (`/api/pipeline/run` only requires `companies` + auth, `search_context` is optional). The restructuring is primarily frontend + adding the form-based config flow.

#### Backend Changes

- [ ] **New endpoint: `POST /api/pipeline/create`** — creates a pipeline from a config, not from a chat
  ```json
  {
    "name": "CNC Manufacturers DACH",           // user-given or auto-generated
    "mode": "discover" | "qualify_only",        // discover = Exa search + full pipeline
                                                 // qualify_only = domains provided, skip search
    "search_context": {
      "industry": "CNC machining, precision manufacturing",
      "company_profile": "Manufacturers with 50-500 employees",
      "technology_focus": "CNC milling, turning, 5-axis",
      "qualifying_criteria": "Has product catalog, serves B2B",
      "disqualifiers": "Pure distributor, no manufacturing",
      "geographic_region": "Germany, Austria, Switzerland"
    },
    "domains": ["acme-cnc.de", "..."],          // only for qualify_only mode
    "template_id": "uuid",                      // optional — load context from template
    "options": {
      "use_vision": true,
      "enrich_hot_leads": true,
      "deep_research": true,
      "max_leads": 100
    }
  }
  ```
  - Returns `{ pipeline_id, status: "running" }` and starts streaming
  - This replaces the current split of `/api/chat/search` + `/api/pipeline/run` for new flows
  - Existing chat flow still works (chat produces search_context → calls same endpoint)

- [ ] **Pipeline status model** — add `pipeline_status` field to `searches` table:
  ```
  stages: { discovery, crawling, qualifying, enriching, research }
  each stage: { status: pending|running|done|failed, progress: 34/50, started_at, completed_at }
  ```
  - Exposed via `GET /api/pipeline/{id}/status` (already exists, enhance it)

- [ ] **Exa search as pipeline stage** — move `POST /api/chat/search` logic into the pipeline engine
  - Currently: chat calls `/api/chat/search` to get company list, then user triggers `/api/pipeline/run`
  - New: pipeline engine handles discovery internally when `mode: "discover"`
  - Discovery stage generates Exa queries from `search_context`, runs them, feeds results into crawl stage
  - No user intervention needed between discovery and qualification

#### Frontend Changes

- [ ] **Dashboard as default landing** — redirect `/chat` to `/dashboard` for logged-in users
  - Dashboard gets a prominent "+ New Pipeline" button
  - New Pipeline opens a creation modal/page with three tabs: **Guided (Chat)** | **Configure** | **Bulk Import**

- [ ] **Pipeline Config Form** (`/dashboard/new` or modal) — the "Configure" tab
  - Form fields matching `search_context`: industry, company profile, tech focus, criteria, disqualifiers, geography
  - Optional: name your pipeline, set options (vision, enrichment, deep research)
  - "Launch Pipeline" button → calls `POST /api/pipeline/create` → redirects to pipeline view
  - Template picker: "Load from template" dropdown pre-fills the form

- [ ] **Refactor HuntContext → PipelineContext**
  - Rename to reflect pipeline-first mental model
  - Separate concerns: `PipelineContext` manages pipeline state (creation, streaming, results)
  - Chat state is local to the chat component, not global
  - Pipeline context is global (active pipelines, results streaming)

- [ ] **Pipeline list view** on dashboard — shows all pipelines with status, progress, lead counts
  - Active pipelines show live progress bars per stage
  - Completed pipelines show summary (hot/review/rejected counts)
  - Click to open detailed pipeline view (existing pipeline table + map)

- [ ] **Chat becomes one option** — accessible from "+ New Pipeline → Guided"
  - Chat still works exactly as before
  - But when chat produces a `search_context` and the user launches, it creates a pipeline via the same `POST /api/pipeline/create` endpoint
  - Results open in the pipeline dashboard view, not in the chat

### 1.1 Contact Page Scraper → Structured People Data
**Effort:** 1 day · **Impact:** 🔥🔥🔥 (free people data from every crawl)

The crawler already visits company websites and can sniff /about, /team, /contact pages. But right now it only extracts address info. Upgrade it to extract **structured people data**.

- [ ] **LLM extraction pass** on contact/team page content → extract:
  - Person name, job title, email, phone number, LinkedIn URL
  - Prioritize: CEO, VP Sales, Head of Purchasing, Managing Director
- [ ] **Store in `lead_contacts` table:**
  ```sql
  CREATE TABLE lead_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES qualified_leads(id),
    full_name TEXT,
    job_title TEXT,
    email TEXT,
    phone TEXT,
    linkedin_url TEXT,
    source TEXT DEFAULT 'website',  -- website | hunter | pdl | rocketreach
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
  ```
- [ ] **Show in LeadDrawer:** "People at this company" section with name, title, email, phone
- [ ] **No API cost** — this uses content you're already crawling

### 1.2 Saved Search Templates (ICP Presets)
**Effort:** 0.5 day · **Impact:** 🔥🔥 (re-run monthly without re-explaining your ICP)

- [ ] **Database:** `search_templates` table (user_id, name, search_context JSON, created_at)
- [ ] **Backend:** CRUD endpoints for templates
  - `POST /api/templates` — save current search context as a named template
  - `GET /api/templates` — list user's templates
  - `DELETE /api/templates/:id`
- [ ] **Frontend:**
  - "Save as Template" button after completing a pipeline config
  - Template picker in the pipeline config form and chat
  - "Run again" button on completed pipelines → creates new pipeline from same config
- [ ] **Built-in starter templates:** "Manufacturing — Europe", "SaaS — North America", "Industrial Automation — DACH"

### 1.3 LinkedIn Enrichment — People Data Labs or RocketReach (Hot Leads Only)
**Effort:** 1 day · **Impact:** 🔥🔥 (LinkedIn data without subscription)

For leads scoring 8+, find decision-makers' LinkedIn profiles programmatically. No Sales Nav subscription needed.

- [ ] **Backend:** `linkedin_enrichment.py`
  - `enrich_linkedin(company_domain)` → calls PDL Company Search or RocketReach Lookup API
  - Returns: name, title, email, phone, LinkedIn URL for C-suite / VP / Director level
  - Stores results in `lead_contacts` table with `source = 'pdl'` or `'rocketreach'`
  - Rate limited: only triggered on score 8+ leads (keeps costs low)
- [ ] **Runs automatically as pipeline stage** — no manual "Find Decision Makers" button needed
  - Enrichment agents are part of the pipeline swarm
  - Also available as manual trigger from LeadDrawer for leads that weren't auto-enriched
- [ ] **SaaS tier gating:** Free = none, Pro = 50/mo, Enterprise = 500/mo

### 1.4 Data Persistence + Global Dedup
**Effort:** 1 day · **Impact:** 🔥🔥🔥 (compounding database = your moat)

Every lead ever found is stored with a unique domain key. Re-encounters merge data instead of creating duplicates. Over time, this becomes a proprietary database.

- [ ] **Database:** Add unique constraint on `qualified_leads(domain, user_id)`
- [ ] **Merge logic:** When a domain is re-encountered in a new pipeline:
  - Update score if re-qualified (keep history in `lead_snapshots`)
  - Merge new contacts into existing `lead_contacts` (dedup by email)
  - Update `last_seen_at` timestamp
  - Keep the highest score and the latest reasoning
- [ ] **Dashboard:** "Total leads in database" counter (cumulative across all pipelines)
- [ ] **Search within your database:** Simple text search across stored leads (company name, industry, signals)
- [ ] **Export:** "Export all my leads" button (full database CSV/Excel download)

---

## 🟡 Tier 2 — Automation & Engagement

_Ship within 2-4 weeks. These turn the pipeline engine into a revenue machine._

### 2.1 Scheduled / Recurring Pipelines
**Effort:** 2 days · **Impact:** 🔥🔥🔥 (passive lead gen while you sleep — this is the killer feature)

This is where the agent-swarm model truly shines. Pipelines run on a schedule, agents work autonomously, new leads appear in your database without lifting a finger.

- [ ] **Database:** `schedules` table (user_id, pipeline_config JSON, frequency, last_run, next_run, is_active)
- [ ] **Backend:** cron worker (APScheduler or simple loop) that triggers `POST /api/pipeline/create` for due schedules
- [ ] **Frontend:** "Schedule this" toggle on completed pipelines or pipeline config form
  - Frequency: daily / weekly / biweekly / monthly
  - Shows upcoming runs + last results on dashboard
- [ ] **When scheduled pipeline completes** → email notification + new leads merged into database (with dedup)
- [ ] **Dashboard:** "Scheduled Pipelines" section showing upcoming runs + status
- [ ] **SaaS gating:** Free = none, Pro = 2 schedules, Enterprise = unlimited

### 2.2 AI Email Drafts
**Effort:** 1-2 days · **Impact:** 🔥🔥🔥 (closes the loop from discovery → outreach)

- [ ] "Draft Email" button on hot leads (LeadDrawer + pipeline table)
- [ ] LLM prompt: takes deep research brief + company signals + user's product context → generates personalized cold email
- [ ] Editable in a modal before copying/sending
- [ ] Tone options: formal / casual / consultative
- [ ] Auto-fills recipient name + company from enrichment data
- [ ] Copy to clipboard or open in default mail client
- [ ] **Future:** Batch draft — "Draft emails for all 12 hot leads" → generates all at once

### 2.3 Re-qualification Alerts
**Effort:** 1 day · **Impact:** 🔥🔥 (keeps your database alive)

Monthly re-crawl of your top leads. If their website changes (new products, expansion, new team members), re-score and alert you.

- [ ] **Database:** `lead_snapshots` table — store score + signals + timestamp each time a company is re-qualified
- [ ] **Backend:** Periodic re-crawl job (reuses pipeline engine in `qualify_only` mode)
  - Compare new score vs. old score
  - If score changed by ±2 or new key signals appear → flag as "changed"
- [ ] **Frontend:**
  - Score trend indicator (↑ ↓ →) on lead cards
  - "3 companies changed this week" notification badge on dashboard
  - Historical chart in LeadDrawer showing score over time

### 2.4 Email Notifications
**Effort:** 1 day

- [ ] Integrate Resend (or Postmark) for transactional email
- [ ] Trigger on:
  - Pipeline complete: "◈ Pipeline complete — {hot_count} hot leads found"
  - Scheduled pipeline results: "Your weekly hunt found 5 new hot leads"
  - Re-qualification alert: "3 leads changed score this week"
- [ ] Settings toggle: enable/disable per notification type
- [ ] Welcome email on signup

### 2.5 Better Empty States & Error UX
**Effort:** 1 day

- [ ] Loading skeletons for dashboard stats, pipeline list, lead table, map
- [ ] Friendly error pages (500, 404, rate limit, quota exceeded)
- [ ] "No results" states with actionable guidance ("Try broadening your search criteria")
- [ ] Toast notifications for success/error (pipeline started, export complete, etc.)

---

## 🟢 Tier 3 — SaaS Scale & Competitive Moat

_Build over months 2-3. These create defensibility, lock-in, and justify higher pricing._

### 3.1 CRM Push (HubSpot + Pipedrive)
**Effort:** 2-3 days

- [ ] HubSpot OAuth2 flow → store access token per user
- [ ] Pipedrive OAuth2 flow (same pattern)
- [ ] "Push to CRM" button on hot leads → creates Contact + Company + Deal
- [ ] Map fields: domain → company, score → deal property, reasoning → note, contacts → contact records
- [ ] Settings page: connect/disconnect, field mapping config
- [ ] **SaaS value:** Enterprise feature — justifies $199/mo tier

### 3.2 Public API + API Keys
**Effort:** 2 days

- [ ] API key generation in Settings page (create/revoke)
- [ ] Store hashed keys in `api_keys` table
- [ ] Auth middleware: accept `Authorization: Bearer hunt_sk_xxx`
- [ ] Documented endpoints: `/api/v1/pipeline/create`, `/api/v1/pipeline/status`, `/api/v1/leads`, `/api/v1/enrich`
- [ ] Rate limiting per API key (tied to plan)
- [ ] API docs page (simple Swagger or custom)
- [ ] **This is the "programmatic" entry point** — enables integrations, Zapier, n8n, custom workflows

### 3.3 Team Workspaces
**Effort:** 3-4 days

- [ ] `workspaces` table (id, name, owner_id, plan)
- [ ] `workspace_members` table (workspace_id, user_id, role: owner/admin/member/viewer)
- [ ] Invite flow: email invite → accept → join workspace
- [ ] All pipelines/leads scoped to workspace, not user
- [ ] Lead assignments: assign a lead to a team member
- [ ] Activity feed: "Sarah's pipeline qualified 12 hot leads from the CNC search"
- [ ] Shared database: all team members contribute to the same lead pool

### 3.4 Shareable Pipeline Links
**Effort:** 1 day

- [ ] Generate unique share token per pipeline
- [ ] Public route `/share/[token]` — read-only view of results (no auth required)
- [ ] Shows: summary stats, tier breakdown, company list (no enrichment data — that's paid)
- [ ] "Share Results" button in pipeline header

### 3.5 Webhooks
**Effort:** 1 day

- [ ] `webhooks` table (user_id, url, events[], secret, is_active)
- [ ] Events: `pipeline.complete`, `lead.qualified.hot`, `lead.status_changed`
- [ ] HMAC signature verification
- [ ] Delivery logs with retry

---

## SaaS Plans (Updated)

| Plan | Price | Pipelines/mo | Leads/pipeline | Hunter Enrichments | LinkedIn Lookups | Deep Research | AI Email Drafts | Scheduled Pipelines | CRM Push |
|------|-------|------------|------------|-------------------|-----------------|---------------|-----------------|-----------------|----------|
| **Free** | $0 | 3 | 25 | 10 | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Pro** | $49/mo | 20 | 100 | 200 | 50 | ✅ | ✅ | 2 schedules | ❌ |
| **Enterprise** | $199/mo | Unlimited | 500 | 1,000 | 500 | ✅ + priority | ✅ | Unlimited | ✅ |

**Unit economics per lead (Pro user, 100 leads/pipeline):**
- Layer 1 (crawl + qualify): $0.01
- Layer 2 (Hunter, ~20% of leads): $0.004
- Layer 3 (PDL/RocketReach, ~10% hot leads): $0.001-0.005
- **Total: ~$0.015-0.02/lead → 100 leads = $1.50-2.00 cost → $49 revenue = 96%+ margin**

---

## Infrastructure for SaaS

| Item | What | Priority |
|------|------|----------|
| **Custom domain** | `app.hunt.so` or similar | Before launch |
| **Production deployment** | Railway / Fly.io / Render (not Docker on a laptop) | Before launch |
| **Environment separation** | Staging + production Supabase projects | Before launch |
| **Error monitoring** | Sentry (backend + frontend) | Before launch |
| **Analytics** | PostHog or Mixpanel — track funnel: signup → first pipeline → qualified leads → upgrade | Before launch |
| **Uptime monitoring** | BetterUptime or similar | Before launch |
| **SOC 2 / privacy policy** | At minimum a privacy policy + terms of service page | Before launch |
| **Transactional email** | Resend or Postmark (welcome, pipeline complete, billing) | Week 1 |
| **CDN / edge** | Vercel for frontend (if separating from Docker) | Nice-to-have |

---

## Build Sequence

```
NOW — Tier 1 (Pipeline-First Restructure):
  Day 1-2:   Pipeline-first architecture refactor
               - Backend: POST /api/pipeline/create endpoint, pipeline status model
               - Backend: Move Exa search into pipeline engine (discovery stage)
               - Frontend: Dashboard as landing, + New Pipeline button
               - Frontend: Pipeline config form (manual entry, template picker)
               - Frontend: Refactor HuntContext → PipelineContext
               - Frontend: Pipeline list view with live progress
               - Frontend: Chat becomes one option under "New Pipeline → Guided"
  Day 3:     Contact page scraper → structured people extraction
  Day 3-4:   Saved search templates / ICP presets
  Day 4-5:   LinkedIn enrichment via PDL or RocketReach (as pipeline stage)
  Day 5-6:   Data persistence + global dedup across pipelines

WEEK 3-4 — Tier 2 (Automation):
  Day 7-8:   Scheduled / recurring pipelines (the killer feature)
  Day 9-10:  AI email drafts (draft outreach for hot leads)
  Day 10-11: Re-qualification alerts (re-crawl + score change detection)
  Day 12:    Email notifications (pipeline complete, alerts)
  Day 13:    Empty states + error UX polish

MONTH 2 — Tier 3 (SaaS Scale):
  Week 5-6:  CRM push (HubSpot + Pipedrive)
  Week 6-7:  Public API + API keys (programmatic entry point)
  Week 7-8:  Team workspaces
  Week 8:    Shareable links + webhooks

MONTH 3 — Launch:
  Deploy to production, custom domain, Sentry, analytics
  Launch on Product Hunt / Indie Hackers / LinkedIn
```

---

## Revenue Model

**Conservative estimates (manufacturing niche):**

| Milestone | Timeline | MRR |
|-----------|----------|-----|
| 10 free users | Week 1-2 | $0 |
| 5 Pro ($49) | Month 1 | $245 |
| 20 Pro + 2 Enterprise ($199) | Month 3 | $1,378 |
| 50 Pro + 10 Enterprise | Month 6 | $4,440 |
| 100 Pro + 25 Enterprise | Month 12 | $9,875 |

**Break-even costs:**
- LLM API: ~$0.01/lead qualified (Kimi K2.5)
- Exa search: ~$0.005/query
- Hunter.io: ~$0.02/enrichment (free tier covers light usage)
- LinkedIn enrichment (PDL/RocketReach): ~$0.01-0.05/lookup (hot leads only)
- Hosting: ~$50/mo (Railway)
- Supabase: Free tier → $25/mo
- Stripe: 2.9% + $0.30/transaction

At 50 Pro users ($2,450 MRR), costs are ~$250/mo. **90%+ margins.**

---

## Key Decisions Needed

1. **Pricing:** $49/$199 or higher ($79/$299) given the niche value?
2. **Free tier:** Keep generous to convert, or gate behind a 14-day trial?
3. **Domain/brand:** "Hunt" is generic. Need a memorable, ownable name + domain.
4. **Vertical vs. horizontal:** Commit to "AI lead gen for manufacturers" or keep it general?
5. **LinkedIn strategy:** Use Sales Nav manually for 1 month to validate, then integrate People Data Labs or RocketReach API for programmatic lookups?
