# ◈ Hunt

**AI-Powered B2B Lead Discovery & Qualification Platform**

Discover, crawl, qualify, and research potential B2B customers using AI. Describe your ideal customer in plain English — Hunt finds them, scores them, and organises everything in a full-featured dashboard with pipeline management and a live map view.

---

## What It Does

```
Web App (primary):

  Chat  ──→  AI Query Gen  ──→  Exa Search  ──→  Crawl + Qualify  ──→  Dashboard
(describe)    (dual-LLM)         (find)          (stream SSE)       (map · pipeline · stats)

CLI (legacy, deprecated):

  CSV / Exa  ──→  Web Crawler  ──→  AI Qualifier  ──→  Deep Research  ──→  CSV Output
```

| Step | Module | What Happens |
|------|--------|-------------|
| **1. Discovery** | `test_exa.py` | Finds company websites matching your ideal customer profile (ICP) using [Exa AI](https://exa.ai) neural search |
| **2. Crawling** | `scraper.py` | Visits each website with a headless browser, extracts page text as markdown + takes a screenshot |
| **3. Qualification** | `intelligence.py` | LLM reads the website content + screenshot and scores 1-10 on how likely this company needs your product |
| **4. Deep Research** | `deep_research.py` | For hot leads (score 8+), crawls multiple pages and generates a sales brief: products they make, who to talk to, what to say |
| **5. Enrichment** | `enrichment.py` | Looks up contact emails/phones via Apollo.io or Hunter.io (optional, manual mode by default) |
| **6. Dashboard** | Frontend | Full pipeline view: stats, searchable leads table, detail drawer, interactive map, settings |

### Lead Tiers

Leads are automatically sorted into 3 tiers:

| Tier | Score | Action |
|------|-------|--------|
| 🔥 **Hot** | 70-100 | Ready for outreach |
| 🔍 **Review** | 40-69 | Human review needed |
| ❌ **Rejected** | 0-39 | Not a fit (with explanation) |

---

## Dashboard

Once logged in, the full dashboard is available at `/dashboard`. It includes:

| Page | Route | Description |
|------|-------|-------------|
| **Overview** | `/dashboard` | Stats cards (total leads, hot leads, searches, enrichments), recent hunts list |
| **Hunts** | `/dashboard/hunts` | Card grid of all saved searches — tier breakdown, delete, click to **resume** any previous hunt with full conversation + results restored |
| **Pipeline** | `/dashboard/pipeline` | Sortable leads table with tier/text filters. Click any row to open the detail drawer (score gauge, AI reasoning, signals, red flags, status management, enrichment data) |
| **Map** | `/dashboard/map` | Split-panel interactive map — left list + right Mapbox GL dark map with glowing dots (red=hot, amber=review, grey=rejected), click-to-fly, popups. **Live mode:** leads pop up on the map in real-time as the pipeline qualifies them |
| **Settings** | `/dashboard/settings` | API status indicators, usage stats, account info, sign out |

### Pipeline Statuses

Each lead can be moved through a CRM-like pipeline:

`new` → `contacted` → `in_progress` → `won` / `lost` / `archived`

---

## Quick Start

### Prerequisites

- **Python 3.9+** and **Node.js 18+** — or just [Docker Desktop](https://www.docker.com/products/docker-desktop/) (skips all local setup)
- **At least one LLM API key** (Kimi or OpenAI)
- **Supabase project** for auth + database (already provisioned)

### Option A: Local Development (recommended for contributors)

You need **two terminals** — one for the Python backend, one for the Next.js frontend.

**1. Clone & install**

```bash
git clone <repo-url>
cd lead-qualifier
```

**2. Backend setup**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate           # macOS/Linux (venv\Scripts\activate on Windows)
pip install -r requirements.txt
playwright install chromium        # headless browser for web scraping

# Configure environment
cp .env.example .env
# Edit .env — at minimum set KIMI_API_KEY or OPENAI_API_KEY and DATABASE_URL
```

**3. Frontend setup**

```bash
cd frontend
npm install

# .env.local should already exist with Supabase keys
# If not, create it:
cat > .env.local << 'EOF'
NEXT_PUBLIC_SUPABASE_URL=https://fwtxlbjnjfzqmqqmsssb.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAPBOX_TOKEN=<optional-mapbox-token>
EOF
```

**4. Run both servers**

```bash
# Terminal 1 — Backend (FastAPI on :8000)
cd backend
source venv/bin/activate
python3 -m uvicorn chat_server:app --reload --port 8000

# Terminal 2 — Frontend (Next.js on :3000)
cd frontend
npm run dev
```

Open **http://localhost:3000** → sign up → start hunting.

### Option B: Docker (recommended for deployment)

Docker bundles Python 3.12, Node 22, Playwright, Chromium, and all dependencies.

```bash
# 1. Configure API keys (one-time)
cp backend/.env.example backend/.env
# Edit backend/.env — add KIMI_API_KEY or OPENAI_API_KEY + DATABASE_URL

# 2. Build & start
docker compose up --build

# Open http://localhost:3000
```

**Day-to-day commands:**
```bash
docker compose up              # Start (foreground)
docker compose up -d           # Start (background)
docker compose down            # Stop everything
docker compose logs -f backend # Tail backend logs
docker compose build --no-cache # Full rebuild
```

### Chat Flow

1. **Describe** what companies you're looking for (e.g., "metal fabrication shops with CNC capabilities")
2. **Answer** 2-3 follow-up questions — the AI tracks readiness across: industry, company profile, technology focus, and qualifying criteria
3. **Launch Search** — generates semantic queries via AI, searches the web via Exa
4. **Qualify** — crawls each company's website and scores them with the LLM
5. **Results** — hot leads, needs-review, and rejected, with reasoning and signals for each
6. **Dashboard** — all results (including the full chat conversation) are saved to your account. Resume any previous hunt from the Hunts page — the conversation, search context, and qualified leads are fully restored

### Architecture & Security

The chat uses a **dual-LLM pattern** for prompt injection defense:

| Layer | What |
|-------|------|
| **Conversation LLM** | Talks to the user, asks follow-ups, extracts structured search parameters |
| **Query Generation LLM** | Takes *only* the validated structured context — never sees raw user text |
| **Input sanitization** | Strips injection patterns, LLM special tokens, HTML, control characters |
| **Output validation** | Generated queries are validated (count, length, category) before execution |
| **Rate limiting** | 30 requests/min per IP on the backend |

### Required API Keys

At minimum `KIMI_API_KEY` or `OPENAI_API_KEY` in `backend/.env`. For search, also add `EXA_API_KEY`. See the [Configuration](#2-configure-api-keys) section for the full list.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string: `postgresql+asyncpg://user:pass@host:5432/postgres` |
| `SUPABASE_URL` | ✅ | Supabase project URL (for JWT verification) |
| `KIMI_API_KEY` | ✅* | Moonshot Kimi API key (cheapest LLM option) |
| `OPENAI_API_KEY` | ✅* | OpenAI API key (fallback) |
| `EXA_API_KEY` | Recommended | Exa AI key for lead discovery |
| `APOLLO_API_KEY` | Optional | Contact enrichment (50 free/month) |
| `HUNTER_API_KEY` | Optional | Email finder (25 free/month) |

*At least one of `KIMI_API_KEY` or `OPENAI_API_KEY` is required.

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anonymous key |
| `NEXT_PUBLIC_API_URL` | ✅ | Backend URL (default: `http://localhost:8000`) |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Optional | Mapbox GL token for the map page (falls back to free CARTO tiles) |

---

## CLI Pipeline (Legacy)

### Quick Start

> **Note:** The CLI pipeline is deprecated in favour of the web dashboard. It still works but results are not saved to the database.

### Prerequisites

- **Python 3.11+** (or just [Docker Desktop](https://www.docker.com/products/docker-desktop/) — skips all local setup)
- **At least one LLM API key** (see Step 2)

### 1. Clone & Set Up Environment

```bash
git clone <your-repo-url>
cd lead-qualifier

# Create virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install browser for web crawling
playwright install chromium
```

### 2. Configure API Keys

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add your keys. **You need at minimum ONE of these:**

| Key | What For | Where to Get It | Cost |
|-----|----------|-----------------|------|
| `KIMI_API_KEY` | Lead qualification (vision + text) — **recommended** | [platform.moonshot.cn](https://platform.moonshot.cn/) | ~¥0.70/1M input tokens |
| `OPENAI_API_KEY` | Lead qualification (fallback) | [platform.openai.com](https://platform.openai.com/) | $0.15/1M input tokens (gpt-4o-mini) |
| `EXA_API_KEY` | Lead discovery (find companies) — **optional** | [dashboard.exa.ai](https://dashboard.exa.ai/) | $10 free credit on signup |

Optional enrichment keys (skip these initially):

| Key | What For | Free Tier |
|-----|----------|-----------|
| `APOLLO_API_KEY` | Email/phone lookup | 50 credits/month |
| `HUNTER_API_KEY` | Email finder | 25 searches/month |

### 3. Prepare Your Leads

**Option A: Use Exa to discover leads automatically** (requires `EXA_API_KEY`)

```bash
cd backend
python test_exa.py --export
# Creates output/exa_leads_YYYYMMDD_HHMM_for_qualifier.csv
```

**Option B: Import from LinkedIn Sales Navigator / your own CSV**

Create `backend/input_leads.csv`:

```csv
company_name,website_url,contact_name,linkedin_profile_url
Boston Dynamics,https://www.bostondynamics.com,Marc Raibert,https://linkedin.com/in/marcraibert
Figure AI,https://www.figure.ai,Brett Adcock,
```

**Option C: Use the included sample file**

```bash
cp backend/sample_leads.csv backend/input_leads.csv
```

### 4. Run

```bash
cd backend

# Quick test with 4 sample companies (Boston Dynamics, Figure AI, Maxon, HubSpot)
python main.py --test

# Process your own leads
python main.py --input input_leads.csv

# Process with deep research on hot leads (more pages crawled, sales brief generated)
python main.py --input input_leads.csv --deep-research

# Text-only mode (no screenshots sent to LLM — cheaper, faster)
python main.py --input input_leads.csv --no-vision

# Start fresh, ignore previous checkpoint
python main.py --input input_leads.csv --clear-checkpoint
```

Or use the convenience script:

```bash
chmod +x backend/run.sh
cd backend
./run.sh test              # Test with sample companies
./run.sh run               # Process input_leads.csv
./run.sh run --deep        # Process with deep research
./run.sh discover          # Run Exa discovery + export CSV
./run.sh export            # Export results to Excel
./run.sh deep 'Maxon' 'https://www.maxongroup.com'  # Deep research one company
```

---

## Project Structure

```
lead-qualifier/
│
├── docker-compose.yml          # 🐳 Orchestrates backend + frontend containers
│
├── backend/                    # Python pipeline + API server
│   ├── Dockerfile              # 🐳 Python 3.12 + Playwright/Chromium image
│   ├── chat_server.py          # 🌐 FastAPI server — chat, pipeline, dashboard API
│   ├── chat_engine.py          # 🧠 Dual-LLM chat engine (conversation + query gen)
│   ├── config.py               # ⚙️  Settings: API keys, thresholds (no hardcoded ICP)
│   ├── models.py               # 📦 Pydantic data models
│   ├── main.py                 # 🎯 CLI pipeline orchestrator (deprecated)
│   │
│   ├── test_exa.py             # 🔍 Step 1: Exa AI lead discovery
│   ├── scraper.py              # 🌐 Step 2: Web crawling (crawl4ai + Playwright)
│   ├── intelligence.py         # 🧠 Step 3: LLM qualification (Kimi / OpenAI)
│   ├── deep_research.py        # 🔬 Step 4: Multi-page research for hot leads
│   ├── enrichment.py           # 📇 Step 5: Contact enrichment (Apollo / Hunter)
│   ├── export.py               # 📊 Step 6: Export to Excel / Google Sheets
│   │
│   ├── db/                     # Database layer
│   │   ├── __init__.py         # SQLAlchemy async engine + session factory
│   │   └── models.py           # ORM models: profiles, searches, qualified_leads, etc.
│   ├── auth/
│   │   └── __init__.py         # Supabase JWT verification (JWKS)
│   │
│   ├── utils.py                # 🔧 Helpers: checkpointing, cost tracking
│   ├── usage.py                # 📊 Usage tracking
│   ├── logging_config.py       # 📝 Structured logging
│   ├── run.sh                  # 🚀 Convenience shell script
│   ├── supabase_migration.sql  # 🗄️  Database schema (CREATE TABLE statements)
│   ├── requirements.txt        # 📦 Python dependencies
│   ├── .env.example            # 🔑 API key template — copy to .env
│   └── output/                 # 📁 CLI output files (gitignored)
│
├── frontend/                   # Next.js 16 web UI
│   ├── Dockerfile              # 🐳 Multi-stage Node 22 build
│   ├── src/
│   │   ├── middleware.ts       # Auth guards (/chat/*, /dashboard/*)
│   │   ├── app/
│   │   │   ├── page.tsx        # Landing page
│   │   │   ├── layout.tsx      # Root layout
│   │   │   ├── globals.css     # Theme tokens + animations
│   │   │   │
│   │   │   ├── chat/page.tsx               # AI chat interface
│   │   │   ├── login/page.tsx              # Login page
│   │   │   ├── signup/page.tsx             # Signup page
│   │   │   │
│   │   │   ├── dashboard/
│   │   │   │   ├── layout.tsx              # Sidebar shell (nav, mobile bottom bar)
│   │   │   │   ├── page.tsx                # Overview (stats + recent hunts)
│   │   │   │   ├── hunts/page.tsx          # Saved searches grid
│   │   │   │   ├── pipeline/
│   │   │   │   │   ├── page.tsx            # Leads table (filter, sort, search)
│   │   │   │   │   └── LeadDrawer.tsx      # Detail slide-out (score, signals, status)
│   │   │   │   ├── map/page.tsx            # Interactive map (Mapbox GL, live pipeline)
│   │   │   │   └── settings/page.tsx       # API status, usage, account
│   │   │   │
│   │   │   ├── api/                        # Next.js API proxy routes
│   │   │   │   ├── chat/route.ts
│   │   │   │   ├── chat/search/route.ts
│   │   │   │   ├── enrich/route.ts
│   │   │   │   ├── pipeline/run/route.ts
│   │   │   │   └── usage/route.ts
│   │   │   │
│   │   │   └── components/
│   │   │       ├── Navbar.tsx              # Top nav (Dashboard link when logged in)
│   │   │       ├── Footer.tsx
│   │   │       ├── chat/ChatInterface.tsx  # Full chat + pipeline streaming UI
│   │   │       ├── hunt/HuntContext.tsx     # Global state context — persists chat, pipeline, map across navigation
│   │   │       ├── auth/
│   │   │       │   ├── AuthGuard.tsx
│   │   │       │   ├── SessionProvider.tsx
│   │   │       │   └── UserMenu.tsx
│   │   │       └── ...                     # Landing page components
│   │   └── lib/supabase/                   # Supabase client helpers
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```

---

## Database Schema

Hunt uses Supabase PostgreSQL. The schema is defined in `backend/supabase_migration.sql` and the ORM models live in `backend/db/models.py`.

| Table | Purpose |
|-------|---------|
| `profiles` | User profiles (synced from Supabase Auth via trigger) |
| `searches` | Saved search sessions — industry, criteria, query list, lead counts, **chat messages (JSONB)** |
| `qualified_leads` | Individual leads — company, score, tier, reasoning, signals, geo, status |
| `enrichment_results` | Contact data (email, phone, job title) linked to leads |
| `usage_tracking` | Per-user usage logs (searches, enrichments, costs) |

**Key columns on `qualified_leads`:**

| Column | Type | Description |
|--------|------|-------------|
| `score` | Integer | AI qualification score (0-100) |
| `tier` | String | `hot` / `review` / `rejected` |
| `status` | String | Pipeline status: `new` / `contacted` / `in_progress` / `won` / `lost` / `archived` |
| `country` | String | Extracted from LLM analysis or inferred from domain TLD |
| `latitude` / `longitude` | Float | Geo coordinates for map plotting (auto-geocoded from HQ location) |
| `key_signals` | Text | JSON array of positive signals |
| `red_flags` | Text | JSON array of concerns |
| `deep_research` | Text | Multi-page sales intelligence brief |

To run migrations against Supabase:
```bash
cd backend
python3 -c "
import asyncio, asyncpg
async def migrate():
    conn = await asyncpg.connect('postgresql://postgres.YOUR_REF:YOUR_PASS@YOUR_HOST:5432/postgres')
    with open('supabase_migration.sql') as f: await conn.execute(f.read())
    print('Done')
    await conn.close()
asyncio.run(migrate())
"
```

---

## How Each Module Works

### `chat_server.py` — API Server

FastAPI server that powers the entire platform. All dashboard endpoints require a Supabase JWT.

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/chat` | — | Send conversation to LLM, returns response + readiness state |
| `POST /api/chat/search` | ✅ | Generate Exa queries from structured context, execute search |
| `POST /api/pipeline/run` | ✅ | Run crawl + qualify on found companies, stream results via SSE |
| `GET /api/health` | — | Health check (LLM + Exa availability) |
| `GET /api/usage` | ✅ | Usage stats for the current user |
| `GET /api/dashboard/stats` | ✅ | Aggregate stats (total leads, hot, searches, enrichments) |
| `GET /api/searches` | ✅ | List all saved searches |
| `GET /api/searches/:id` | ✅ | Single search with lead counts |
| `DELETE /api/searches/:id` | ✅ | Delete a search and all its leads |
| `GET /api/leads` | ✅ | List leads (filterable by `tier`, `search_id`, sortable) |
| `GET /api/leads/geo` | ✅ | Leads with lat/lng for map plotting |
| `GET /api/leads/:id` | ✅ | Full lead detail + enrichment data |
| `PATCH /api/leads/:id/status` | ✅ | Update pipeline status (new/contacted/in_progress/won/lost/archived) |

Rate limited at 30 requests/min per IP. CORS configured for the frontend.

### `chat_engine.py` — Dual-LLM Chat Engine

The brain behind the chat interface. Two isolated LLM pipelines:

1. **Conversation LLM** — Talks to the user with a hardened system prompt. Extracts structured search parameters (industry, tech focus, criteria) through natural conversation. Outputs constrained JSON.
2. **Query Generation LLM** — Receives *only* the validated structured context. Generates 4-8 semantic Exa search queries. Never sees raw user input.

Falls back through: Kimi K2.5 → GPT-4o-mini. Input sanitization strips prompt injection patterns, special tokens, and HTML.

### `test_exa.py` — Lead Discovery

Uses [Exa AI](https://exa.ai) neural search to find companies matching your ideal customer profile. Exa is like Google but understands *meaning*, not just keywords. Describe the company you want (e.g., "humanoid robot company building actuators") and it returns matching websites.

- **Input:** Natural language search queries (generated dynamically from the chat, or manual)
- **Output:** Company URLs + titles + text snippets + relevance scores
- **Does NOT qualify leads** — just finds them. Qualification is `intelligence.py`'s job.

### `scraper.py` — Web Crawling

Launches a headless Chromium browser via [crawl4ai](https://github.com/unclecode/crawl4ai) to:
- Load the company's homepage
- Extract the full page as clean Markdown text
- Capture a screenshot (for vision model analysis)
- Auto-remove popups/overlays/cookie banners

Screenshots are resized to 720px wide JPEG to keep vision API costs low.

### `intelligence.py` — AI Qualification ⭐ (Core Value)

This is where the magic happens. The LLM:
1. Reads the website markdown text
2. Optionally analyzes the screenshot (vision mode)
3. Scores the company 1-10 on how well they match the user's ICP
4. Returns structured JSON with: `confidence_score`, `hardware_type`, `industry_category`, `headquarters_location`, `reasoning`, `key_signals`, `red_flags`

Qualification prompts are built dynamically from the user's search context (industry, technology focus, qualifying criteria, disqualifiers) — no hardcoded industry assumptions.

**Model priority chain:**
1. **Kimi K2.5** (vision + text) — cheapest option, supports screenshots
2. **OpenAI GPT-4o** (vision fallback)
3. **GPT-4o-mini** (text-only fallback)
4. **Keyword matching** (zero-cost fallback if all APIs fail)

Includes a quick pre-filter that rejects obvious non-fit companies (SaaS-only, agencies, consultancies) without burning any LLM tokens.

### `deep_research.py` — Sales Intelligence

For hot leads (score ≥ 8), crawls up to 5 pages on their site and generates:
- Products they manufacture or services they provide
- Technology stack and capabilities
- Company size and production volume estimates
- Decision-maker titles to target
- A suggested pitch angle and talking points

### `enrichment.py` — Contact Lookup

Two modes:
- **Manual mode** (default): Flags leads for manual LinkedIn/email lookup — zero cost
- **API mode**: Uses Apollo.io and/or Hunter.io to find emails and phone numbers

Start with manual mode. Enable API enrichment once the pipeline is proven and you're ready to do outreach.

### `export.py` — Export & Share

- **Excel:** Creates `.xlsx` with separate sheets for Hot / Review / Rejected
- **Google Sheets:** Uploads directly (requires Google Cloud service account)
- **Watch mode:** Auto-syncs to Sheets when files change

---

## CLI Reference

### `backend/main.py` — Main Pipeline

```
cd backend
python main.py [OPTIONS]

Options:
  --test                Run test with 4 sample companies
  --input FILE          Custom input CSV path (default: input_leads.csv)
  --no-vision           Disable screenshot analysis (text-only, cheaper)
  --auto-enrich         Auto-lookup emails for hot leads (needs Apollo/Hunter keys)
  --deep-research       Multi-page analysis on hot leads (generates sales brief)
  --clear-checkpoint    Delete previous progress and start fresh
```

### `backend/test_exa.py` — Lead Discovery

```
cd backend
python test_exa.py [OPTIONS]

Options:
  --query N    Run only query #N (1-12), e.g. --query 1 for humanoid robots
  --export     Export results to CSV (auto-creates qualifier-compatible format)
```

### `backend/deep_research.py` — Single Company Research

```
cd backend
python deep_research.py <company_name> <website_url>

Example:
  python deep_research.py "Maxon Group" "https://www.maxongroup.com"
```

### `backend/export.py` — Export Results

```
cd backend
python export.py [excel|sheets|watch]

  excel   → Creates .xlsx with Hot/Review/Rejected sheets
  sheets  → Uploads to Google Sheets (needs credentials.json)
  watch   → Auto-syncs on file changes
```

---

## Configuration Guide

All configuration is in `backend/config.py`. Key settings:

| Setting | Default | What It Controls |
|---------|---------|-----------------|
| `CONCURRENCY_LIMIT` | 5 | How many websites to crawl in parallel |
| `MAX_TOKENS_INPUT` | 6000 | Max tokens of website text sent to LLM per lead |
| `SCORE_HOT_LEAD` | 8 | Minimum score to be classified as a "hot" lead |
| `SCORE_REVIEW` | 4 | Minimum score for "review" bucket (below this → rejected) |
| `TEXT_MODEL` | gpt-4o-mini | LLM for text-only qualification |
| `VISION_MODEL` | kimi-k2.5-thinking | LLM for vision qualification |
| `REQUEST_TIMEOUT` | 30 | Seconds before a crawl times out |

### Customizing the ICP (Ideal Customer Profile)

Hunt's qualification logic is **fully dynamic** — driven by the user's search context from the chat interface. There are no hardcoded industry prompts.

When a user describes their ideal customer in chat, the AI extracts structured parameters (industry, technology focus, qualifying criteria, disqualifiers) and builds LLM prompts on-the-fly for each search.

For the CLI pipeline, you can still tweak `backend/config.py`:

- **`NEGATIVE_KEYWORDS`** — Universal B2B negatives (SaaS, agencies, etc.) used for quick pre-filtering
- **Score thresholds** — `SCORE_HOT_LEAD` (default: 8), `SCORE_REVIEW` (default: 4)

---

## Cost Estimates

| Operation | Cost per unit | Notes |
|-----------|--------------|-------|
| Exa search (1 query, ≤25 results) | ~$0.005 | 12 queries ≈ $0.06 |
| Exa content retrieval | ~$0.001/page | Included in search call |
| Kimi K2.5 qualification | ~$0.002/lead | Vision + text |
| GPT-4o-mini qualification | ~$0.001/lead | Text only |
| GPT-4o qualification | ~$0.01/lead | With vision |
| Deep research (per lead) | ~$0.005 | 3-5 pages crawled + LLM |
| Apollo enrichment | Free (50/mo) | Then $49/mo for 2,400 |
| Hunter enrichment | Free (25/mo) | Then $49/mo for 500 |

**Typical full run:** 100 leads ≈ **$0.20 – $0.50** with Kimi

---

## Resume & Checkpointing

The pipeline automatically saves progress. If it crashes or you stop it (`Ctrl+C`):
- Already-processed leads are skipped on re-run
- Output CSVs are appended to, not overwritten
- Checkpoint is stored in `output/.checkpoint.json`

To start completely fresh:
```bash
python main.py --clear-checkpoint
```

---

## Troubleshooting

### Chat interface not connecting to backend
Make sure both servers are running:
- Backend: `cd backend && source venv/bin/activate && python3 -m uvicorn chat_server:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev`

Check `http://localhost:8000/api/health` — it should return `{"status": "ok", "llm_available": true, ...}`.

### Dashboard shows no data
Make sure you've run at least one search from the chat interface (`/chat`). The pipeline saves results to the database automatically. Check that `DATABASE_URL` in `backend/.env` is set correctly.

### Map page is blank
The map requires a Mapbox GL token. Set `NEXT_PUBLIC_MAPBOX_TOKEN` in `frontend/.env.local` to enable the dark-v11 map style. Leads appear on the map automatically — the LLM extracts company headquarters from website content and a built-in geocoder converts locations to coordinates. If no HQ is found, the system falls back to domain TLD country detection.

### Docker build fails
```bash
# Make sure Docker Desktop is running, then:
docker compose build --no-cache   # Full rebuild
```

If you see Playwright/Chromium errors in the container, the Dockerfile already handles all system deps. If it persists, try: `docker compose down && docker system prune -f && docker compose up --build`.

### Docker containers can't communicate
The frontend waits for the backend health check before starting. If the backend is unhealthy:
```bash
docker compose logs backend    # Check for API key errors
curl http://localhost:8000/api/health   # Should return {"status": "ok"}
```

### "No LLM API configured"
→ Add `OPENAI_API_KEY` or `KIMI_API_KEY` to your `backend/.env` file.

### Playwright / Chromium errors
```bash
playwright install chromium
# On Linux, also run:
playwright install-deps chromium
```

### Many crawl failures / timeouts
Some sites block headless browsers (Cloudflare, etc.). These leads go to the "review" queue.
- Increase `REQUEST_TIMEOUT` in `backend/config.py` (default: 30s)
- Lower `CONCURRENCY_LIMIT` to avoid rate limits
- Manually visit the site for blocked leads

### Kimi API errors
Kimi K2.5 is a thinking model that requires `temperature=1`. This is already configured. If you see timeout errors, the model may need more time — try increasing the `httpx.Timeout` in `backend/intelligence.py`.

### Stale / wrong results
```bash
cd backend && python main.py --clear-checkpoint
```
Clears the checkpoint AND output CSVs for a clean run.

### "No EXA_API_KEY found"
The Exa discovery step (`test_exa.py`) is optional. You can skip it entirely and provide your own CSV.

---

## Roadmap

- [x] Chat interface — guided AI conversation to define ICP and launch searches
- [x] Web-based pipeline — full crawl + qualify with live streaming results
- [x] Dual-LLM security — prompt injection defense via isolated query generation
- [x] Docker — containerized deployment with `docker compose up`
- [x] Industry-agnostic — dynamic ICP from chat, no hardcoded keywords/prompts
- [x] Multi-tenant auth — Supabase user accounts, JWT-protected endpoints
- [x] Full dashboard — stats, hunts, pipeline table, lead detail drawer
- [x] Interactive map — Mapbox GL with glowing dots, fly-to, popups, **live pipeline updates**
- [x] Pipeline CRM — lead status management (new → contacted → won/lost)
- [x] Chat persistence — full conversation saved to DB, resume any hunt from the dashboard
- [x] Live map geocoding — LLM extracts HQ location, built-in geocoder plots leads automatically
- [ ] Email drafting module — auto-generate cold emails from deep research
- [ ] CRM integrations — push hot leads to HubSpot, Salesforce, etc.
- [ ] Deep research in chat — trigger multi-page analysis from the web UI
- [ ] Team workspaces — shared searches and lead assignments

---

## Contributing

### Getting Started

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Set up local dev (see [Quick Start](#option-a-local-development-recommended-for-contributors))
4. Make your changes
5. Test:
   - Backend: `cd backend && python -m pytest tests/`
   - Frontend: `cd frontend && npm run build` (type checks)
   - Manual: run both servers and exercise the changed feature
6. Submit a PR

### Architecture Notes

- **Backend** — Python 3.9+, FastAPI, SQLAlchemy async, asyncpg. All routes in `chat_server.py`. Database models in `db/models.py`. Auth via Supabase JWT (JWKS verification in `auth/__init__.py`).
- **Frontend** — Next.js 16, React 19, TypeScript 5, Tailwind CSS 4. Design tokens defined in `globals.css` (`--color-*`, `--font-*`). Dashboard pages under `src/app/dashboard/`. Auth via `@supabase/ssr`.
- **Qualification is dynamic** — The ICP is extracted from the user’s chat conversation and passed as structured context to the LLM. No hardcoded industry prompts. If you’re adding features, don’t assume a specific industry.
- **Dual-LLM security** — Raw user input never reaches the query generation LLM. Keep this separation.
- Keep the modular architecture — each module should do one thing and be independently testable.

### Code Style

- Python: follow existing patterns, type hints encouraged
- TypeScript: `font-mono` for UI labels, `font-sans` for body text, `text-[10px] uppercase tracking-[0.15em]` for micro-labels
- Colours: use theme tokens (`text-primary`, `secondary`, `hot`, `review`, `surface-2`, etc.) from `globals.css`

---

## License

Private — Mainrich International / Hunt
