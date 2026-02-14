# 🎯 HUNT — Dashboard & Platform Build Plan

> **Status:** Ready to execute
> **Brand:** Hunt (working name)
> **Target:** Chinese manufacturers/exporters → any B2B seller globally
> **Multi-user:** Individual accounts (MVP), org/team later
> **Map:** Mapbox GL (dark theme, zoom/pan, glowing dots)

---

## Phase 1 — De-Magnet & Rebrand (Backend)

Strip all Mainrich/magnet hardcoding. The dynamic `search_context` path already works for any industry — we just remove the fallback.

### 1.1 — `config.py`: Remove hardcoded ICP
- Delete `POSITIVE_KEYWORDS` (40+ magnet/motor terms)
- Delete `NEGATIVE_KEYWORDS` (30 terms) — or keep a minimal universal B2B negative list (e.g. "restaurant", "law firm", "hair salon")
- Delete `INDUSTRY_KEYWORDS` dict (7 fixed industry buckets)
- Delete `HARDCODED_QUERIES` / any magnet-specific search queries
- Keep: API keys, file paths, concurrency limits, score thresholds

### 1.2 — `intelligence.py`: Dynamic-only qualification
- Remove the hardcoded Mainrich system prompt (`SYSTEM_PROMPT` / `QUALIFICATION_PROMPT`) that references magnets, motors, Halbach arrays
- Remove the fallback path that uses hardcoded prompts when no `search_context` is provided
- If no `search_context` → refuse to qualify (return "needs context" instead of using magnet assumptions)
- Remove fixed `industry_category` enum from JSON schema (let LLM classify freely)
- Remove magnet/motor few-shot examples from prompts — replace with generic B2B examples
- Keep: The dynamic prompt-building path (already works perfectly for any vertical)

### 1.3 — `deep_research.py`: Already generic
- Minor: Remove any leftover `motor_types_used` / `magnet_requirements` legacy aliases
- The `_build_analysis_prompt()` function is already dynamic — no changes needed

### 1.4 — `chat_engine.py`: Update few-shot examples
- Replace magnet-specific few-shot examples (lines ~165-172, ~236-237) with diverse B2B examples
- E.g. "CNC machining" → SUFFICIENT, "LED lighting components" → SUFFICIENT
- Keep: The dual-LLM architecture, ExtractedContext, Readiness system

### 1.5 — `main.py`: Deprecate CLI
- Add deprecation warning at top: "This CLI is deprecated. Use the web dashboard at localhost:3000"
- Don't delete yet (keep for reference/testing) but it's no longer the primary interface

### 1.6 — `test_exa.py`: Low priority
- The 12 hardcoded Mainrich queries are test-only, not user-facing
- Leave as-is or delete — doesn't affect the product

---

## Phase 2 — Rebrand Frontend

### 2.1 — Brand swap: "The Magnet Hunter" → "Hunt"
Files to update (7 brand locations + 2 Mainrich locations):
- `layout.tsx` — page title metadata
- `chat/page.tsx` — page title
- `components/Navbar.tsx` — logo text, icon
- `components/Footer.tsx` — brand text, copyright (change "Mainrich International" to just "Hunt")
- `components/chat/ChatInterface.tsx` — HUD watermark (line ~761)
- `login/page.tsx` — header brand
- `signup/page.tsx` — header brand

New brand treatment:
- Name: **Hunt**
- Icon: ◈ (keep the diamond, it works)
- Tagline: "AI-Powered B2B Lead Discovery"
- No more "Mainrich International" references in UI

### 2.2 — Chat suggestions
Replace the 4 magnet/motor suggestions in `ChatInterface.tsx` (~line 189):
```
Old:
🤖 "Find robotics startups building humanoid robots in the US"
⚡ "Companies manufacturing BLDC motors for drones"
🏥 "Medical device makers that use precision motors or magnets"
🔋 "EV powertrain companies developing in-house motor technology"

New:
🏭 "Find US companies importing custom metal fabrication parts"
📱 "Consumer electronics brands looking for OEM component suppliers"
⚡ "European EV companies that need battery or motor components"
🏗️ "Construction equipment manufacturers in Southeast Asia"
```

### 2.3 — Landing page copy
Update the homepage sections (InfiniteRolodex, HowItWorks, Features, Pricing, etc.) to reflect the broader positioning. The current copy likely references magnets/motors — make it generic B2B export lead discovery.

---

## Phase 3 — Backend API Endpoints for Dashboard

New endpoints in `chat_server.py` (all require `Depends(require_auth)`):

### 3.1 — Dashboard stats
```
GET /api/dashboard/stats
→ { total_leads, hot_leads, review_leads, rejected_leads, total_searches, contacts_enriched, leads_this_month }
```

### 3.2 — Searches (Hunts) CRUD
```
GET  /api/searches              → List all user's searches (with lead counts per tier)
GET  /api/searches/:id          → Single search with its leads
DELETE /api/searches/:id        → Delete a search and its leads
```

### 3.3 — Leads
```
GET /api/leads                  → All user's leads across all searches
                                  Query params: ?tier=hot&sort=score&order=desc&search_id=xxx
GET /api/leads/:id              → Single lead with full detail (deep research, enrichment)
```

### 3.4 — Geocoding for map
```
GET /api/leads/geo              → All leads with lat/lng coordinates for map plotting
```
Geocoding strategy: Extract country from domain TLD (.de → Germany, .co.uk → UK) or from crawl content. Store `country`, `latitude`, `longitude` on the `qualified_leads` table. For domains like .com, use the company's HQ location extracted during crawl/qualification (add to LLM prompt: "What country is this company headquartered in?").

### 3.5 — Save pipeline results to DB
Modify existing endpoints to persist data:
- `POST /api/chat/search` → After Exa search, create a `searches` row
- `POST /api/pipeline/run` → After each company is qualified, create a `qualified_leads` row
- `POST /api/enrich` → After enrichment, create an `enrichment_results` row
- All tied to the authenticated user's `profiles.id`

---

## Phase 4 — Database Schema Updates

### 4.1 — Add geo columns to `qualified_leads`
```sql
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS country TEXT;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
```

### 4.2 — Add `status` to qualified_leads (for user pipeline management)
```sql
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';
-- Values: new, contacted, in_progress, won, lost, archived
```

### 4.3 — Update SQLAlchemy models
Add the new columns to `db/models.py` → `QualifiedLead`.

---

## Phase 5 — Dashboard Frontend

### 5.1 — Dashboard layout (`/dashboard/layout.tsx`)
- Sidebar navigation: Overview, Hunts, Pipeline, Map, Settings
- Responsive: sidebar collapses to bottom nav on mobile
- Dark theme matching existing aesthetic
- User menu in sidebar footer
- AuthGuard: redirect to /login if not authenticated

### 5.2 — Overview page (`/dashboard/page.tsx`)
- **Stats bar** at top: 4 cards
  - Total Leads (all time)
  - 🔥 Hot Leads
  - Searches Run
  - Contacts Enriched
- **Recent Hunts** list (last 5 searches with ICP summary + lead tier counts)
- **Quick Actions**: "Start New Hunt" button → links to /chat
- **Activity feed**: recent lead qualifications with tier badges

### 5.3 — Hunts page (`/dashboard/hunts/page.tsx`)
- Card grid of all saved searches
- Each card shows:
  - ICP summary (industry, tech focus, criteria — from search context)
  - Date created
  - Lead tier breakdown: `🔥 5 · 🔍 12 · ❌ 3`
  - "View Leads" button → links to Pipeline filtered by this search
- Delete hunt (with confirmation)

### 5.4 — Pipeline page (`/dashboard/pipeline/page.tsx`)
- **Filter bar**: [All] [🔥 Hot] [🔍 Review] [❌ Rejected] + search box + sort dropdown
- **Leads table**: 
  - Columns: Company, Domain, Score, Tier, Industry, Key Signals (truncated), Date
  - Sortable by score, date, tier
  - Click row → **Detail drawer** slides in from right
- **Detail drawer** (`LeadDrawer.tsx`):
  - Full company info: name, domain, URL
  - Score gauge (visual 0-100 with color)
  - Tier badge (Hot/Review/Rejected)
  - Reasoning (full text)
  - Key signals (green badges)
  - Red flags (red badges)
  - Deep research section (if available): products, technologies, pitch angle, talking points
  - Enrichment section (if available): email, phone, job title
  - Status dropdown: New → Contacted → In Progress → Won → Lost
  - "Visit Website" external link

### 5.5 — Map page (`/dashboard/map/page.tsx`) ⭐ THE HERO
Inspired by the Palantir-style conflict monitor screenshot.

**Layout**: Split panel
- **Left panel** (30% width): Scrollable lead list
  - Filter toggles at top: [All] [🔥] [🔍] [❌]
  - Each entry: Company name, tier badge, score, country flag
  - Click → highlight on map + expand details
  - Stats summary at top: `12 Hot · 8 Review · 5 Rejected`

- **Right panel** (70% width): Mapbox GL map
  - Dark style: `mapbox://styles/mapbox/dark-v11`
  - **Glowing dots** at company locations:
    - 🔴 Red glow = Hot (score 8-10)
    - 🟠 Amber glow = Review (score 4-7)
    - ⚫ Grey = Rejected (score 1-3)
  - Dot size proportional to score
  - Click dot → popup with company name, score, tier, domain
  - Click popup "View Details" → opens detail drawer
  - **Legend** in top-right corner (toggleable)
  - **Stats bar** at very top: `● LIVE PIPELINE  47 leads  12 hot  8 review  5 rejected`
  - Cluster dots when zoomed out, expand when zoomed in
  - Smooth fly-to animation when clicking a lead in the list

- **Connection lines** (stretch goal, not MVP):
  - Lines from China (your location) to each lead's country
  - Color-coded by tier
  - Shows the "export corridor" visually

### 5.6 — Settings page (`/dashboard/settings/page.tsx`)
- **API Status**: Green/red dots for each configured API (Kimi, OpenAI, Exa, Hunter)
- **Usage meter**: Leads qualified this month / limit
- **Plan info**: Current tier (free/pro)
- **Account**: Email, display name

---

## Phase 6 — Navbar & Routing

### 6.1 — Update `Navbar.tsx`
- When logged in: show "Dashboard" link instead of/alongside "Start Hunting"
- Keep landing page public (marketing)
- Chat page (`/chat`) remains the "New Hunt" entry point

### 6.2 — Middleware
- `/dashboard/*` routes → require auth (redirect to /login)
- `/chat` → require auth
- `/`, `/login`, `/signup` → public

---

## Execution Order

```
Phase 1 (Backend cleanup)     ~30 min    Strip magnet hardcoding
Phase 2 (Frontend rebrand)    ~20 min    Brand swap + suggestions
Phase 3 (API endpoints)       ~40 min    Dashboard data APIs
Phase 4 (DB schema)           ~10 min    Add geo + status columns
Phase 5 (Dashboard UI)        ~90 min    All 6 pages + map
Phase 6 (Routing)             ~10 min    Navbar + auth guards
                              ─────────
                              ~3.5 hrs total
```

---

## Environment Variables Needed

```env
# Frontend (.env.local) — add:
NEXT_PUBLIC_MAPBOX_TOKEN=pk.xxx    # Get from mapbox.com → Account → Access tokens

# Backend (.env) — no new vars needed
```

---

## Dependencies to Install

```bash
# Frontend
npm install mapbox-gl @types/mapbox-gl    # Map
npm install react-map-gl                   # React wrapper for Mapbox
```

---

## What We're NOT Doing (MVP scope control)

- ❌ Org/team model (Phase 2 of product, not this sprint)
- ❌ Connection lines on map (stretch goal)
- ❌ CSV export as a featured capability (buried download button only)
- ❌ Real-time collaboration / shared cursors
- ❌ Google Sheets integration
- ❌ CLI pipeline (deprecated, kept for reference)
- ❌ Landing page full rewrite (light copy update only)
