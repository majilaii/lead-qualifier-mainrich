# ◈ Hunt — SaaS Roadmap

> Turning Hunt from an internal tool into a paid B2B product.

---

## Positioning

**Don't compete as "another lead gen tool."** Clay, Apollo, and Instantly will crush you on database size, integrations, and brand.

**Win on:** _"AI that reads company websites to find hidden B2B opportunities that databases miss."_

Best-fit verticals (where databases fail):
- **Manufacturing / hardware / industrial** — no LinkedIn presence, no Crunchbase profile, no BuiltWith tech stack
- **International / emerging markets** — blind spots in US-centric databases
- **Highly specific ICPs** — "companies that use servo motors in their products" — no database has that filter, but Hunt reads the product page and figures it out

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
| Pipeline CRM (new → contacted → won/lost) | Shipped |
| Contact enrichment (Hunter.io) | Shipped |
| Docker deployment (hot-reload dev mode) | Shipped |

---

## 🔴 Tier 1 — Must-Have Before Launch

_Can't charge money without these. Target: 1 week._

### 1.1 Stripe Billing + Plan Gates
**Effort:** 2-3 days

**Plans:**

| Plan | Price | Hunts/mo | Leads/hunt | Enrichments/mo | Deep Research |
|------|-------|----------|------------|-----------------|---------------|
| **Free** | $0 | 3 | 25 | 10 | ❌ |
| **Pro** | $49/mo | 20 | 100 | 200 | ✅ |
| **Enterprise** | $199/mo | Unlimited | 500 | 1,000 | ✅ + priority |

**Implementation:**

- [ ] **Backend:** `stripe_billing.py` — Stripe SDK integration
  - Checkout Session creation (plan subscribe)
  - Webhook handler (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`)
  - Customer portal session URL generation
- [ ] **Database:** Add columns to `profiles` table
  ```sql
  ALTER TABLE profiles ADD COLUMN stripe_customer_id TEXT;
  ALTER TABLE profiles ADD COLUMN stripe_subscription_id TEXT;
  ALTER TABLE profiles ADD COLUMN plan TEXT DEFAULT 'free';  -- free | pro | enterprise
  ALTER TABLE profiles ADD COLUMN plan_period_start TIMESTAMPTZ;
  ALTER TABLE profiles ADD COLUMN plan_period_end TIMESTAMPTZ;
  ```
- [ ] **API endpoints:**
  - `POST /api/billing/checkout` — create Stripe Checkout session
  - `POST /api/billing/portal` — create Stripe billing portal session
  - `POST /api/billing/webhook` — Stripe webhook receiver
  - `GET /api/billing/status` — current plan + usage for the user
- [ ] **Frontend:** API proxy routes
  - `POST /api/billing/checkout/route.ts`
  - `POST /api/billing/portal/route.ts`
  - `GET /api/billing/status/route.ts`

### 1.2 Usage Quotas & Enforcement
**Effort:** 1 day

- [ ] **Backend middleware:** `check_quota()` dependency injected into `/api/chat/search`, `/api/pipeline/run`, `/api/enrich`
  - Query `usage_tracking` table: count hunts + leads + enrichments in current billing period
  - Compare against plan limits
  - Return `429 { error: "quota_exceeded", limit: 25, used: 25, plan: "free", upgrade_url: "..." }` when exceeded
- [ ] **Frontend:** Intercept 429 responses globally
  - Show upgrade modal with plan comparison
  - Disable "Launch Search" / "Qualify" buttons when quota is near/exceeded
  - Show usage bar in header or chat input area

### 1.3 Pricing Page
**Effort:** 1 day

- [ ] Wire existing `Pricing.tsx` to Stripe Checkout
  - Each plan button → `POST /api/billing/checkout` with `plan_id`
  - Redirect to Stripe Checkout → return to `/dashboard` on success
  - Handle already-subscribed state (show "Current Plan" badge, "Manage" → Stripe portal)
- [ ] Add pricing link to Navbar, landing page CTA, and upgrade modals

### 1.4 Onboarding Flow
**Effort:** 1 day

- [ ] **First-visit detection:** Check if user has 0 searches in DB
- [ ] **Guided chat:** Pre-fill the first message with a walkthrough prompt, or show a 3-step tooltip overlay:
  1. "Describe your ideal customer"
  2. "We'll ask a few follow-ups to sharpen the search"
  3. "Launch → watch leads appear on the map in real-time"
- [ ] **Demo hunt (optional):** "Try with sample data" button that runs a pre-baked search so they see the product in action without using a credit

---

## 🟡 Tier 2 — First Month After Launch

_Ship these within 30 days of going live. Target: 1-2 weeks._

### 2.1 CRM Push (HubSpot)
**Effort:** 2 days

- [ ] HubSpot OAuth2 flow → store access token per user in `profiles`
- [ ] "Push to HubSpot" button on hot leads (ResultsSummaryCard + LeadDrawer)
- [ ] Create HubSpot Contact + Company + Deal from qualified lead data
- [ ] Map fields: domain → company, score → deal property, reasoning → note
- [ ] Settings page: connect/disconnect HubSpot, field mapping config

### 2.2 Email Notifications
**Effort:** 1 day

- [ ] Integrate Resend (or Postmark) for transactional email
- [ ] Trigger on pipeline `complete` event:
  - Subject: "◈ Hunt complete — {hot_count} hot leads found"
  - Body: summary card (hot/review/rejected counts) + "View Results" CTA
- [ ] Settings toggle: enable/disable email notifications
- [ ] Welcome email on signup

### 2.3 Scheduled / Recurring Hunts
**Effort:** 2 days

- [ ] Database: `schedules` table (user_id, search_context, cron expression, last_run, next_run, is_active)
- [ ] Backend: cron worker (APScheduler or simple loop) that triggers search + pipeline for due schedules
- [ ] Frontend: "Run weekly" toggle on completed hunts → saves schedule
- [ ] Email notification when scheduled hunt completes
- [ ] Dashboard: "Scheduled Hunts" section showing upcoming runs

### 2.4 Shareable Hunt Links
**Effort:** 1 day

- [ ] Generate unique share token per search: `GET /api/searches/:id/share` → returns `{ share_url: "https://app/share/abc123" }`
- [ ] Public route `/share/[token]` — read-only view of results (no auth required)
- [ ] Shows: summary stats, tier breakdown, company list (no enrichment data — that's paid)
- [ ] "Share Results" button in ResultsSummaryCard header

### 2.5 Better Empty States & Error UX
**Effort:** 1 day

- [ ] Loading skeletons for dashboard stats, hunts grid, pipeline table, map
- [ ] Friendly error pages (500, 404, rate limit, quota exceeded)
- [ ] "No results" states with actionable guidance ("Try broadening your search criteria")
- [ ] Toast notifications for success/error (pipeline started, export complete, etc.)

---

## 🟢 Tier 3 — Competitive Moat

_Build over months 2-3. These create defensibility and lock-in._

### 3.1 Public API + API Keys
**Effort:** 2 days

- [ ] API key generation in Settings page (create/revoke)
- [ ] Store hashed keys in `api_keys` table
- [ ] Auth middleware: accept `Authorization: Bearer hunt_sk_xxx` in addition to Supabase JWT
- [ ] Documented endpoints: `/api/v1/search`, `/api/v1/qualify`, `/api/v1/leads`
- [ ] Rate limiting per API key (tied to plan)
- [ ] API docs page (simple Swagger or custom)

### 3.2 Team Workspaces
**Effort:** 3-4 days

- [ ] `workspaces` table (id, name, owner_id, plan)
- [ ] `workspace_members` table (workspace_id, user_id, role: owner/admin/member/viewer)
- [ ] Invite flow: email invite → accept → join workspace
- [ ] All searches/leads scoped to workspace, not user
- [ ] Lead assignments: assign a lead to a team member
- [ ] Activity feed: "Sarah qualified 12 leads from the CNC search"

### 3.3 Lead Tracking Over Time
**Effort:** 2 days

- [ ] `lead_snapshots` table — store score + signals each time a company is re-qualified
- [ ] When a recurring hunt re-encounters a known domain, compare old vs. new score
- [ ] UI: score trend indicator (↑ ↓ →) on lead cards
- [ ] Alert: "3 companies improved their score this week"
- [ ] Historical chart in LeadDrawer

### 3.4 AI Email Drafts
**Effort:** 1-2 days

- [ ] "Draft Email" button on hot leads (LeadDrawer + ResultsSummaryCard)
- [ ] LLM prompt: takes deep research brief + company signals + user's product context → generates cold email
- [ ] Editable in a modal before copying/sending
- [ ] Tone options: formal / casual / consultative
- [ ] Copy to clipboard or push to connected email tool

### 3.5 Webhooks
**Effort:** 1 day

- [ ] `webhooks` table (user_id, url, events[], secret, is_active)
- [ ] Settings page: add/remove webhook URLs, select events
- [ ] Events: `hunt.complete`, `lead.qualified.hot`, `lead.status_changed`
- [ ] HMAC signature verification (webhook secret)
- [ ] Delivery logs with retry

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

## Launch Sequence

```
Week 1:  Stripe + quotas + pricing page + onboarding
Week 2:  Deploy to production (Railway/Fly), custom domain, Sentry, analytics
Week 3:  Launch on Product Hunt / Indie Hackers / LinkedIn
Week 4:  Email notifications + shareable links + empty states polish
Month 2: HubSpot integration + recurring hunts + API keys
Month 3: Team workspaces + AI email drafts + webhooks
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
- Hosting: ~$50/mo (Railway)
- Supabase: Free tier → $25/mo
- Stripe: 2.9% + $0.30/transaction

At 50 Pro users ($2,450 MRR), costs are ~$200/mo. Healthy margins.

---

## Key Decisions Needed

1. **Pricing:** Are these prices right for manufacturing B2B? Could charge more ($79/$299) given the niche.
2. **Free tier:** Keep it generous enough to convert, or gate everything behind a trial?
3. **Domain/brand:** "Hunt" is generic. Need a memorable, ownable name + domain.
4. **Solo vs. team:** Ship solo-user first and add teams later? Or build multi-tenant from day 1?
5. **Vertical vs. horizontal:** Commit to "AI lead gen for manufacturers" or keep it general?
