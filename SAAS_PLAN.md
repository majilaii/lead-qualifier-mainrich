# ◈ Hunt — SaaS Roadmap (v2)

> Dual-purpose: power Mainrich's own lead generation across Europe & America **and** evolve into a paid SaaS product.

_Last updated: February 2026_

---

## Positioning

**Don't compete as "another lead gen tool."** Clay, Apollo, and Instantly will crush you on database size, integrations, and brand.

**Win on:** _"AI that reads company websites to find hidden B2B opportunities that databases miss."_

Best-fit verticals (where databases fail):
- **Manufacturing / hardware / industrial** — no LinkedIn presence, no Crunchbase profile, no BuiltWith tech stack
- **International / emerging markets** — blind spots in US-centric databases
- **Highly specific ICPs** — "companies that use servo motors in their products" — no database has that filter, but Hunt reads the product page and figures it out

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

**Why this wins:** Every hunt adds to the database. Re-crawls keep it fresh. Over 6 months, you have thousands of qualified, enriched leads with zero ongoing subscription cost.

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

## 🔴 Tier 1 — Power Features (Internal Use + SaaS Value)

_These make the tool immediately more useful for Mainrich's own prospecting AND are the features that make customers pay. Target: 1-2 weeks._

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

### 1.2 Bulk Domain Import
**Effort:** 0.5 day · **Impact:** 🔥🔥🔥 (essential for daily Mainrich workflow)

Skip the chat flow entirely. Paste a list of domains or upload a CSV → run the qualification pipeline directly.

- [ ] **Backend:** `POST /api/pipeline/bulk` — accepts `{ domains: ["acme.com", "example.de", ...], search_context: {...} }`
  - Creates a search record, then processes each domain through crawl → qualify → enrich
  - Streams results via SSE (reuses existing pipeline streaming)
- [ ] **Frontend:** "Bulk Import" button on dashboard or chat page
  - Textarea: paste domains (one per line) or upload CSV
  - Optional: set ICP context (industry, criteria) or pick a saved template
  - Shows pipeline progress with the existing pipeline UI
- [ ] **Use case:** After a manual LinkedIn Sales Navigator session, paste the domains you found → Hunt qualifies and enriches them all

### 1.3 Saved Search Templates (ICP Presets)
**Effort:** 0.5 day · **Impact:** 🔥🔥 (re-run monthly without re-explaining your ICP)

- [ ] **Database:** `search_templates` table (user_id, name, search_context JSON, created_at)
- [ ] **Backend:** CRUD endpoints for templates
  - `POST /api/templates` — save current search context as a named template
  - `GET /api/templates` — list user's templates
  - `DELETE /api/templates/:id`
- [ ] **Frontend:**
  - "Save as Template" button after completing chat parameters
  - Template picker in chat: "Use a saved ICP" → select → skip chat questions → go straight to search
  - Template picker in Bulk Import: apply saved ICP context to domain list
- [ ] **Built-in starter templates:** "Manufacturing — Europe", "SaaS — North America", "Industrial Automation — DACH"

### 1.4 LinkedIn Enrichment — People Data Labs or RocketReach (Hot Leads Only)
**Effort:** 1 day · **Impact:** 🔥🔥 (LinkedIn data without subscription)

For leads scoring 8+, find decision-makers' LinkedIn profiles programmatically. No Sales Nav subscription needed.

**Provider options (decide later):**
- **People Data Labs** — closest to old Proxycurl, person + company enrichment, ~$0.01/call, bulk-friendly
- **RocketReach** — email + phone + LinkedIn lookup, from $39/mo, has API

- [ ] **Backend:** `linkedin_enrichment.py`
  - `enrich_linkedin(company_domain)` → calls PDL Company Search or RocketReach Lookup API
  - Returns: name, title, email, phone, LinkedIn URL for C-suite / VP / Director level
  - Stores results in `lead_contacts` table with `source = 'pdl'` or `'rocketreach'`
  - Rate limited: only triggered on score 8+ leads (keeps costs low)
- [ ] **Config:** `PDL_API_KEY` or `ROCKETREACH_API_KEY` in `.env` + `config.py`
- [ ] **Frontend:** "Find Decision Makers" button in LeadDrawer for hot leads
  - Shows LinkedIn profile links with titles + verified emails
  - "Open in LinkedIn" quick action
- [ ] **SaaS tier gating:** Free = none, Pro = 50/mo, Enterprise = 500/mo

### 1.5 Data Persistence + Global Dedup
**Effort:** 1 day · **Impact:** 🔥🔥🔥 (compounding database = your moat)

Every lead ever found is stored with a unique domain key. Re-encounters merge data instead of creating duplicates. Over time, this becomes a proprietary database.

- [ ] **Database:** Add unique constraint on `qualified_leads(domain, user_id)`
- [ ] **Merge logic:** When a domain is re-encountered in a new hunt:
  - Update score if re-qualified (keep history in `lead_snapshots`)
  - Merge new contacts into existing `lead_contacts` (dedup by email)
  - Update `last_seen_at` timestamp
  - Keep the highest score and the latest reasoning
- [ ] **Dashboard:** "Total leads in database" counter (cumulative across all hunts)
- [ ] **Search within your database:** Simple text search across stored leads (company name, industry, signals)
- [ ] **Export:** "Export all my leads" button (full database CSV/Excel download)

---

## 🟡 Tier 2 — Engagement & Automation

_Ship within 2-4 weeks. These turn qualified leads into actual revenue._

### 2.1 AI Email Drafts
**Effort:** 1-2 days · **Impact:** 🔥🔥🔥 (closes the loop from discovery → outreach)

- [ ] "Draft Email" button on hot leads (LeadDrawer + pipeline table)
- [ ] LLM prompt: takes deep research brief + company signals + user's product context → generates personalized cold email
- [ ] Editable in a modal before copying/sending
- [ ] Tone options: formal / casual / consultative
- [ ] Auto-fills recipient name + company from enrichment data
- [ ] Copy to clipboard or open in default mail client
- [ ] **SaaS value:** This is the feature that makes people upgrade — "Hunt doesn't just find leads, it writes the email for you"

### 2.2 Scheduled / Recurring Hunts
**Effort:** 2 days · **Impact:** 🔥🔥 (passive lead gen while you sleep)

- [ ] Database: `schedules` table (user_id, search_context / template_id, frequency, last_run, next_run, is_active)
- [ ] Backend: cron worker (APScheduler or simple loop) that triggers search + pipeline for due schedules
- [ ] Frontend: "Run weekly/monthly" toggle on completed hunts → saves schedule
- [ ] When scheduled hunt completes → email notification + new leads merged into database (with dedup)
- [ ] Dashboard: "Scheduled Hunts" section showing upcoming runs + last results
- [ ] **SaaS gating:** Free = none, Pro = 2 schedules, Enterprise = unlimited

### 2.3 Re-qualification Alerts
**Effort:** 1 day · **Impact:** 🔥🔥 (keeps your database alive)

Monthly re-crawl of your top leads. If their website changes (new products, expansion, new team members), re-score and alert you.

- [ ] **Database:** `lead_snapshots` table — store score + signals + timestamp each time a company is re-qualified
- [ ] **Backend:** Periodic re-crawl job for leads with `qualification_tier = 'hot'`
  - Compare new score vs. old score
  - If score changed by ±2 or new key signals appear → flag as "changed"
- [ ] **Frontend:**
  - Score trend indicator (↑ ↓ →) on lead cards
  - "3 companies changed this week" notification badge on dashboard
  - Historical chart in LeadDrawer showing score over time
- [ ] **Trigger re-crawl via scheduled hunts** — reuses the same infrastructure

### 2.4 Email Notifications
**Effort:** 1 day

- [ ] Integrate Resend (or Postmark) for transactional email
- [ ] Trigger on:
  - Hunt complete: "◈ Hunt complete — {hot_count} hot leads found"
  - Scheduled hunt results: "Your weekly hunt found 5 new hot leads"
  - Re-qualification alert: "3 leads changed score this week"
- [ ] Settings toggle: enable/disable per notification type
- [ ] Welcome email on signup

### 2.5 Better Empty States & Error UX
**Effort:** 1 day

- [ ] Loading skeletons for dashboard stats, hunts grid, pipeline table, map
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
- [ ] Documented endpoints: `/api/v1/search`, `/api/v1/qualify`, `/api/v1/leads`, `/api/v1/enrich`
- [ ] Rate limiting per API key (tied to plan)
- [ ] API docs page (simple Swagger or custom)

### 3.3 Team Workspaces
**Effort:** 3-4 days

- [ ] `workspaces` table (id, name, owner_id, plan)
- [ ] `workspace_members` table (workspace_id, user_id, role: owner/admin/member/viewer)
- [ ] Invite flow: email invite → accept → join workspace
- [ ] All searches/leads scoped to workspace, not user
- [ ] Lead assignments: assign a lead to a team member
- [ ] Activity feed: "Sarah qualified 12 leads from the CNC search"
- [ ] Shared database: all team members contribute to the same lead pool

### 3.4 Shareable Hunt Links
**Effort:** 1 day

- [ ] Generate unique share token per search
- [ ] Public route `/share/[token]` — read-only view of results (no auth required)
- [ ] Shows: summary stats, tier breakdown, company list (no enrichment data — that's paid)
- [ ] "Share Results" button in pipeline header

### 3.5 Webhooks
**Effort:** 1 day

- [ ] `webhooks` table (user_id, url, events[], secret, is_active)
- [ ] Events: `hunt.complete`, `lead.qualified.hot`, `lead.status_changed`
- [ ] HMAC signature verification
- [ ] Delivery logs with retry

---

## SaaS Plans (Updated)

| Plan | Price | Hunts/mo | Leads/hunt | Hunter Enrichments | LinkedIn Lookups | Deep Research | AI Email Drafts | Recurring Hunts | CRM Push |
|------|-------|----------|------------|-------------------|-----------------|---------------|-----------------|-----------------|----------|
| **Free** | $0 | 3 | 25 | 10 | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Pro** | $49/mo | 20 | 100 | 200 | 50 | ✅ | ✅ | 2 schedules | ❌ |
| **Enterprise** | $199/mo | Unlimited | 500 | 1,000 | 500 | ✅ + priority | ✅ | Unlimited | ✅ |

**Unit economics per lead (Pro user, 100 leads/hunt):**
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
| **Analytics** | PostHog or Mixpanel — track funnel: signup → first hunt → qualified leads → upgrade | Before launch |
| **Uptime monitoring** | BetterUptime or similar | Before launch |
| **SOC 2 / privacy policy** | At minimum a privacy policy + terms of service page | Before launch |
| **Transactional email** | Resend or Postmark (welcome, hunt complete, billing) | Week 1 |
| **CDN / edge** | Vercel for frontend (if separating from Docker) | Nice-to-have |

---

## Build Sequence

```
NOW — Tier 1 (Internal Power + SaaS Core):
  Day 1-2:   Contact page scraper → structured people extraction
  Day 2-3:   Bulk domain import (paste domains → qualify all)
  Day 3:     Saved search templates / ICP presets
  Day 4-5:   LinkedIn enrichment via PDL or RocketReach (hot leads only)
  Day 5-6:   Data persistence + global dedup across hunts

WEEK 3-4 — Tier 2 (Engagement):
  Day 7-8:   AI email drafts (draft outreach for hot leads)
  Day 9-10:  Scheduled / recurring hunts
  Day 10-11: Re-qualification alerts (re-crawl + score change detection)
  Day 12:    Email notifications (hunt complete, alerts)
  Day 13:    Empty states + error UX polish

MONTH 2 — Tier 3 (SaaS Scale):
  Week 5-6:  CRM push (HubSpot + Pipedrive)
  Week 6-7:  Public API + API keys
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
