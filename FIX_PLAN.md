# 🔧 The Magnet Hunter — Full Fix Plan

> Last updated: February 11, 2026
> Status: **Draft — awaiting approval to begin**

---

## Overview

The core AI pipeline (chat → search → crawl → qualify → export) is **functional and well-architected**. The dual-LLM security pattern, 4-tier model fallback chain, and live SSE streaming show real engineering. But it's a **single-user CLI tool dressed up as a SaaS**. The gap isn't features — it's infrastructure: auth, database, user isolation, and deployment.

**Total estimated effort:** ~26-28 days across 4 phases
**Shippable product (Phases 1+2):** ~11 days

---

## Current State Audit

### ✅ What Actually Works End-to-End
| Step | Component | Status |
|------|-----------|--------|
| Chat → AI extracts ICP | `chat_engine.py` | ✅ Dual-LLM, input sanitization, output validation |
| Query generation | `chat_engine.py` | ✅ Structured context → Exa search queries |
| Exa neural search | `chat_engine.py` | ✅ Finds matching companies |
| Web crawling | `scraper.py` | ✅ crawl4ai + Playwright, screenshots, markdown |
| LLM qualification | `intelligence.py` | ✅ 4-tier fallback, rate limiting, JSON parsing |
| Live SSE streaming | `chat_server.py` | ✅ Real-time results to frontend |
| CSV export | `ChatInterface.tsx` | ✅ Client-side with proper escaping |
| Hunter.io enrichment | `enrichment.py` | ✅ Finds decision-maker emails (25 free/mo) |

### 🩹 What's Held Together with Duct Tape
| Problem | File | Severity |
|---------|------|----------|
| `_kimi_tpd_exhausted` global flag — one user hitting Kimi daily limit silently breaks ALL users, never resets without process restart | `intelligence.py` | 🔴 High |
| Deep research hardcoded for magnets — prompt says "NdFeB, SmCo, Halbach arrays", targets `/products`, `/solutions`. Useless for any other industry | `deep_research.py` | 🔴 High |
| "Waterfall enrichment" is a lie — UI says "Waterfull · Apollo · Hunter" but only Hunter.io is implemented. Apollo & Waterfull config keys load but go nowhere | `enrichment.py` | 🟡 Medium |
| Excel export hardcodes column names — `KeyError` crash if any expected column is missing from CSV | `export.py` | 🟡 Medium |
| `watch_and_export()` is a stub — watches for file changes but does literally nothing ("You could trigger export here") | `export.py` | 🟡 Fake |
| In-memory rate limiter — resets on restart, doesn't work across workers | `chat_server.py` | 🟡 Medium |
| `dangerouslySetInnerHTML` renders LLM output as raw HTML — XSS vector | `ChatInterface.tsx` | 🟡 Medium |
| Mixed routing — chat goes through Next.js proxy, pipeline/enrich calls hit FastAPI directly on `localhost:8000` | `ChatInterface.tsx` | 🟡 Breaks in prod |
| No CSV file lock — concurrent pipeline writes could corrupt rows | `utils.py` | 🟢 Low |
| `filter_api_keys` uses `locals()` assignment which doesn't work in Python | `chat_engine.py` | 🟢 Low |

### 🕳️ What's Completely Missing
| Feature | Status |
|---------|--------|
| Authentication | Zero — no login, no sessions, no tokens. Anyone can hit every endpoint |
| Database / persistence | None — everything is in-memory or flat CSV files |
| User isolation | None — global state means users interfere with each other |
| Tests | Zero — not a single test file in the entire codebase |
| Error monitoring | Just `print()` statements — no Sentry, no structured logging |
| Apollo enrichment | Config loaded, never implemented |
| Waterfull enrichment | Config loaded, never implemented |
| Result persistence | Qualified leads vanish when you close the browser |
| Production deployment | CORS is localhost-only, no HTTPS, no reverse proxy |
| Multi-tenancy | One process, one global state |
| Billing / usage limits | Cost tracker exists but no per-user enforcement |
| CRM integration | No HubSpot, Salesforce, or webhook output |

### 🔌 External Dependencies
| Service | Role | Status |
|---------|------|--------|
| Kimi / Moonshot API | Primary LLM | ✅ Works · $0.70/1M input tokens · Rate limited 20 RPM org-wide |
| OpenAI API | Fallback LLM | ✅ Works · More expensive · Used when Kimi fails |
| Exa AI | Lead discovery search | ✅ Works · $10 free credit on signup |
| Playwright / Chromium | Web crawling | ✅ Works · Requires `playwright install chromium` |
| Hunter.io | Contact enrichment | ✅ Works · 25 searches/month free |
| Waterfull API | Contact enrichment | ❌ Not implemented |
| Apollo API | Contact enrichment | ❌ Not implemented |
| Google Sheets API | Export | ⚠️ Functional but requires manual service account setup |

---

## Phase 1 — Ship-Blockers

> **Must fix before any real user touches this.**
> Estimated: ~7 days

### 1.1 Fix `_kimi_tpd_exhausted` global state bomb
- **File:** `backend/intelligence.py`
- **Problem:** Module-level `_kimi_tpd_exhausted = False` is a process-wide flag. One user hitting Kimi's daily token limit silently degrades qualification for ALL users. Flag never resets without a process restart.
- **Fix:** Replace with per-session or per-request state object. Pass exhaustion state through function params, or use a TTL-based reset that auto-clears after 24 hours.
- **Estimated effort:** 0.5 day

### 1.2 Make deep research dynamic (de-hardcode magnets)
- **File:** `backend/deep_research.py`
- **Problem:** The entire deep research prompt is hardcoded for Mainrich's magnet business — "magnet supplier (NdFeB, SmCo, Halbach arrays)". Target pages are hardcoded to `/products`, `/solutions`, `/technology`. Completely unusable for any other industry or user.
- **Fix:**
  - Accept `industry_context` / `product_context` as function parameters
  - Pull context from what `chat_engine.py` already extracts (it already builds dynamic prompts for qualification — deep research just ignores them)
  - Make target pages dynamic or auto-discovered
  - Add null check so missing Kimi API key doesn't crash with `AttributeError` on `client.chat.completions.create()`
- **Estimated effort:** 1 day

### 1.3 Authentication system
- **Files:** New + modifications across frontend & backend
- **Problem:** Zero authentication. No login, no sessions, no API tokens. Anyone can hit every endpoint. No way to track who's doing what.
- **Fix:**
  - Install & configure NextAuth.js (or Clerk for faster setup)
  - Google OAuth — standard, covers most users
  - WeChat OAuth — for Chinese market (requires WeChat Open Platform app registration)
  - Email/password with verification as fallback
  - Wire up existing `signup/page.tsx` and `login/page.tsx` (currently placeholder forms with `alert()`)
  - Add JWT/session token validation to all backend API calls
  - Protect `/chat` and future `/dashboard` routes with `AuthGuard` component
  - Add `user_id` parameter to backend endpoints so all state is per-user
- **Estimated effort:** 2-3 days

### 1.4 Database + persistence
- **Files:** New — schema, ORM layer, migrations
- **Problem:** Everything is in-memory or flat CSV files. Qualified leads vanish on page refresh. No search history. No user data persistence.
- **Fix:**
  - PostgreSQL for production (or SQLite for initial dev speed)
  - Core tables:
    - `users` — id, email, name, auth_provider, created_at
    - `searches` — id, user_id, icp_context, queries, created_at
    - `qualified_leads` — id, search_id, company data, score, tier, reasoning
    - `enrichment_results` — id, lead_id, email, job_title, source
    - `usage_tracking` — user_id, month, leads_used, plan_tier
  - Replace CSV file writes with DB inserts
  - Save qualified results so users can revisit them
  - Save search history & saved ICPs
- **Estimated effort:** 2 days

### 1.5 Fix production routing
- **Files:** `frontend/src/app/components/chat/ChatInterface.tsx`, `backend/chat_server.py`
- **Problem:** Chat requests go through Next.js API routes (`/api/chat`, `/api/chat/search`), but pipeline and enrichment calls go **directly** to `localhost:8000` via `BACKEND_URL`. This works locally but breaks in any real deployment.
- **Fix:**
  - Option A: Route ALL backend calls through Next.js API routes (add `/api/pipeline` and `/api/enrich` routes)
  - Option B: Set up a proper reverse proxy (nginx/Caddy) and make `BACKEND_URL` configurable via environment variable
  - Update CORS in `chat_server.py` from hardcoded localhost origins to configurable allowed origins via env var
- **Estimated effort:** 1 day

---

## Phase 2 — Integrity Fixes

> **Stop lying to users. Fix security holes.**
> Estimated: ~4 days

### 2.1 Remove or implement enrichment "waterfall"
- **File:** `backend/enrichment.py`
- **Problem:** The UI and code comments reference a "Waterfull · Apollo · Hunter waterfall chain" but the actual implementation only supports Hunter.io. `APOLLO_API_KEY` and `WATERFULL_API_KEY` are loaded in config but never used anywhere.
- **Fix (choose one):**
  - **Option A:** Implement Apollo.io integration (they have a free tier with 50 credits/mo). Add as second step in the waterfall.
  - **Option B:** Remove all references to Apollo and Waterfull from UI text, code comments, and config. Be honest that enrichment is Hunter.io only.
  - Clean up dead config keys regardless of which option.
- **Estimated effort:** 1-2 days

### 2.2 Fix `dangerouslySetInnerHTML` XSS risk
- **File:** `frontend/src/app/components/chat/ChatInterface.tsx`
- **Problem:** The `MessageContent` component renders LLM output using `dangerouslySetInnerHTML`. It converts markdown bold (`**text**`) to `<strong>` tags via regex, then injects the result as raw HTML. If the LLM hallucinates or is manipulated into outputting `<script>`, `<img onerror=...>`, or similar, it executes in the user's browser.
- **Fix:** Replace `dangerouslySetInnerHTML` with `react-markdown` + `rehype-sanitize`. This renders markdown safely without raw HTML injection.
- **Estimated effort:** 0.5 day

### 2.3 Fix export.py fragility
- **File:** `backend/export.py`
- **Problem:**
  - `to_excel()` hardcodes a list of expected column names and accesses them directly → `KeyError` crash if any column is missing (e.g. when deep research fields aren't present)
  - `watch_and_export()` is a complete stub — sets up a file watcher but the callback contains only a comment: "You could trigger export here"
- **Fix:**
  - Make `to_excel()` dynamic: read whatever columns exist in the CSV, apply formatting to known columns, pass through unknown ones
  - Either implement `watch_and_export()` properly (auto-export on CSV change) or delete it entirely
- **Estimated effort:** 0.5 day

### 2.4 Usage tracking & free tier limits
- **Depends on:** Phase 1.4 (database)
- **Problem:** Cost estimation logic exists in `utils.py` but there's no per-user tracking or enforcement. Free tier promises "50 leads/month" but nothing stops anyone from doing 5,000.
- **Fix:**
  - Track leads qualified per user per calendar month in `usage_tracking` table
  - Check limit before starting pipeline — return clear error if exceeded
  - Show usage meter in UI: "12/50 leads used this month"
  - Show graceful upgrade prompt when limit is approached or hit
- **Estimated effort:** 1 day

---

## Phase 3 — Reliability

> **Stop things from randomly breaking. Add confidence.**
> Estimated: ~4.5 days

### 3.1 Add retry logic to scraper
- **File:** `backend/scraper.py`
- **Problem:** Single-attempt crawl per URL. If a page is slow, returns a 5xx, or has a transient network issue, the lead is just marked as failed with no retry.
- **Fix:** Add 1-2 retries with exponential backoff (e.g. wait 2s, then 5s). Only on transient errors (timeout, 5xx), not on 4xx.
- **Estimated effort:** 0.5 day

### 3.2 Fix `filter_api_keys` bug in chat_engine
- **File:** `backend/chat_engine.py`
- **Problem:** The `filter_api_keys` function assigns to `locals()` dict — e.g. `locals()[key] = None`. This is a Python anti-pattern: modifying `locals()` does NOT affect actual local variables. The placeholder API key filtering silently does nothing.
- **Fix:** Use the same dict-based filtering pattern that `config.py` uses correctly (check against a set of known placeholder prefixes, return `None` if matched).
- **Estimated effort:** 0.5 day

### 3.3 Replace `print()` with structured logging
- **Files:** All backend `.py` files
- **Problem:** Every backend file uses bare `print()` for logging. No log levels, no timestamps, no structured output. Impossible to debug issues in production or send to a log aggregator.
- **Fix:**
  - Replace all `print()` calls with Python's built-in `logging` module
  - Use appropriate levels: `DEBUG` for crawl/parse details, `INFO` for pipeline progress, `WARNING` for fallbacks, `ERROR` for failures
  - Configure a standard format with timestamps
  - Prep for Sentry/Datadog integration later
- **Estimated effort:** 1 day

### 3.4 Add CSV file locking
- **File:** `backend/utils.py`
- **Problem:** `append_result_to_csv()` opens and writes to CSV files without any locking mechanism. When the pipeline runs with concurrency (e.g. 5 parallel crawls), multiple coroutines could write simultaneously, corrupting rows.
- **Fix:** Add `threading.Lock` or use the `filelock` library for cross-process safety.
- **Estimated effort:** 0.5 day

### 3.5 Basic test suite
- **Files:** New — `backend/tests/`
- **Problem:** Zero test files in the entire codebase. The most complex logic (LLM JSON response parsing, search query validation, pre-filter keywords) is completely untested.
- **Fix — minimum viable test coverage:**
  - `test_intelligence.py` — LLM JSON response parser (the most complex parsing logic with multiple fallback strategies)
  - `test_chat_engine.py` — Search query validator, input sanitization
  - `test_enrichment.py` — Domain cleaning, contact ranking logic
  - `test_intelligence_prefilter.py` — Pre-filter keyword matching (SaaS/consulting rejection)
  - Use `pytest` with a few mocked LLM responses
- **Estimated effort:** 2 days

---

## Phase 4 — Scale & Market

> **When users show up and start paying.**
> Estimated: ~11-13 days

### 4.1 Redis rate limiting
- **File:** `backend/chat_server.py`
- **Problem:** Current rate limiter is an in-memory dict that resets on process restart and doesn't work across multiple workers/instances.
- **Fix:** Replace with Redis-backed rate limiter (e.g. `slowapi` with Redis backend).
- **Estimated effort:** 1 day

### 4.2 Background job queue
- **Problem:** Pipeline runs block the FastAPI request handler. Long qualification runs (20+ companies × 35s each) tie up the web server.
- **Fix:** Celery or RQ with Redis broker. Pipeline runs become background jobs. Frontend polls for status or subscribes via WebSocket.
- **Estimated effort:** 2 days

### 4.3 Stripe billing
- **Problem:** Pro tier ($49/mo) is advertised on the pricing page but there's no payment flow.
- **Fix:**
  - Stripe Checkout for subscription creation
  - Webhook handler for payment events
  - Plan upgrade/downgrade flow
  - Invoice history page
  - Stripe Customer Portal for self-service billing management
- **Estimated effort:** 2-3 days

### 4.4 i18n — Chinese + Serbian localization
- **Problem:** Platform targets Chinese and Serbian users but everything is English-only.
- **Fix:**
  - Set up `next-intl` or `next-i18next`
  - Create translation files: `zh-CN.json`, `sr.json`, `en.json`
  - Language switcher in navbar
  - Currency localization (CNY, RSD, USD, EUR)
  - Region-specific landing page variants
- **Estimated effort:** 2-3 days

### 4.5 CRM integrations
- **Problem:** Qualified leads can only be exported as CSV. No direct CRM push.
- **Fix:**
  - HubSpot integration (create contacts + deals via API)
  - Salesforce integration (create leads via API)
  - Webhook output (POST results to user-configured URL)
- **Estimated effort:** 2-3 days

### 4.6 Result caching & dedup
- **Problem:** No caching of search or qualification results. Re-searching the same ICP re-crawls and re-qualifies every company. Costs money and time for no reason.
- **Fix:**
  - Cache qualification results by domain (TTL: 7-30 days)
  - Dedup across searches — if a company was already qualified this month, skip and show cached result
  - Show "cached" badge on results that were previously qualified
- **Estimated effort:** 1 day

---

## Timeline Summary

| Phase | Focus | Days | Cumulative | Milestone |
|-------|-------|------|------------|-----------|
| **Phase 1** | Global state, dynamic research, auth, DB, routing | ~7 | 7 | Functional multi-user platform |
| **Phase 2** | Enrichment honesty, XSS fix, export fix, usage limits | ~4 | 11 | **Shippable product** |
| **Phase 3** | Retries, logging, file locks, tests | ~4.5 | 15.5 | Reliable product |
| **Phase 4** | Redis, job queue, billing, i18n, CRM | ~11-13 | 26-28 | Scalable business |

---

## File Impact Map

```
backend/
├── intelligence.py        ← Phase 1.1 (global state fix)
├── deep_research.py       ← Phase 1.2 (de-hardcode magnets)
├── chat_engine.py         ← Phase 3.2 (filter_api_keys fix)
├── chat_server.py         ← Phase 1.5 (CORS) + Phase 4.1 (Redis)
├── enrichment.py          ← Phase 2.1 (waterfall honesty)
├── export.py              ← Phase 2.3 (fragility fix)
├── scraper.py             ← Phase 3.1 (retry logic)
├── utils.py               ← Phase 3.4 (file locking)
├── config.py              ← Phase 2.1 (dead config cleanup)
├── models.py              ← No changes needed
├── main.py                ← Phase 3.3 (logging)
├── tests/                 ← Phase 3.5 (NEW — test suite)
│   ├── test_intelligence.py
│   ├── test_chat_engine.py
│   ├── test_enrichment.py
│   └── conftest.py
├── db/                    ← Phase 1.4 (NEW — database)
│   ├── schema.sql
│   ├── models.py
│   └── connection.py
└── auth/                  ← Phase 1.3 (NEW — auth middleware)
    └── middleware.py

frontend/src/app/
├── components/
│   └── chat/
│       └── ChatInterface.tsx  ← Phase 1.5 (routing) + Phase 2.2 (XSS fix)
├── signup/page.tsx            ← Phase 1.3 (wire to real auth)
├── login/page.tsx             ← Phase 1.3 (wire to real auth)
├── dashboard/page.tsx         ← Phase 1.4 (NEW)
├── api/
│   ├── auth/[...nextauth]/    ← Phase 1.3 (NEW)
│   ├── pipeline/route.ts      ← Phase 1.5 (NEW — proxy)
│   └── enrich/route.ts        ← Phase 1.5 (NEW — proxy)
└── components/
    └── auth/
        ├── AuthGuard.tsx      ← Phase 1.3 (NEW)
        └── UserMenu.tsx       ← Phase 1.3 (NEW)
```

---

## Decision Points

Before starting, these decisions need to be made:

1. **Auth provider:** NextAuth.js (free, more control) vs Clerk (faster, managed, $25/mo at scale)?
2. **Database:** PostgreSQL (production-ready) vs SQLite (faster to start, migrate later)?
3. **Enrichment:** Implement Apollo (adds value) vs remove fake waterfall (saves time)?
4. **WeChat OAuth:** Register WeChat Open Platform app now (takes 1-2 weeks for approval) or defer?
5. **Deployment target:** Vercel + Railway? Docker Compose on VPS? AWS?
