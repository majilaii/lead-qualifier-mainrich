# 🧲 The Magnet Hunter

**AI-Powered B2B Lead Discovery & Qualification Pipeline**

Automatically discover, crawl, qualify, and research potential B2B customers using AI. Built for Mainrich International's magnet & motor business, designed to be generalized for any hardware B2B company.

---

## What It Does

```
Two modes:

CLI:   CSV / Exa Search ──→ Web Crawler ──→ AI Qualifier ──→ Deep Research ──→ CSV Output
            (find)            (scrape)        (score)          (analyze)

Chat:  Conversation ──→ AI Query Gen ──→ Exa Search ──→ Crawl + Qualify ──→ Live Results
         (describe)      (dual-LLM)       (find)         (stream SSE)       (scored UI)
```

| Step | Module | What Happens |
|------|--------|-------------|
| **1. Discovery** | `test_exa.py` | Finds company websites matching your ideal customer profile (ICP) using [Exa AI](https://exa.ai) neural search |
| **2. Crawling** | `scraper.py` | Visits each website with a headless browser, extracts page text as markdown + takes a screenshot |
| **3. Qualification** | `intelligence.py` | LLM reads the website content + screenshot and scores 1-10 on how likely this company needs your product |
| **4. Deep Research** | `deep_research.py` | For hot leads (score 8+), crawls multiple pages and generates a sales brief: products they make, who to talk to, what to say |
| **5. Enrichment** | `enrichment.py` | Looks up contact emails/phones via Apollo.io or Hunter.io (optional, manual mode by default) |
| **6. Export** | `export.py` | Combines results into Excel or Google Sheets |

### Output

Leads are automatically sorted into 3 buckets:

| File | Score | Action |
|------|-------|--------|
| `output/qualified_hot_leads.csv` | 8-10 🔥 | Ready for outreach |
| `output/review_manual_check.csv` | 4-7 🔍 | Human review needed |
| `output/rejected_with_reasons.csv` | 1-3 ❌ | Not a fit (with explanation) |

---

## Chat Interface (Web UI)

The chat interface lets you describe your ideal customer in plain English. An AI assistant asks follow-up questions to sharpen the search, then runs the full pipeline — discovery, crawling, and qualification — with live progress in the browser.

### How to Run

You need **two terminals** — one for the Python backend, one for the Next.js frontend.

**Terminal 1: Backend (FastAPI)**

```bash
cd backend
python -m venv venv              # First time only
source venv/bin/activate         # macOS/Linux (venv\Scripts\activate on Windows)
pip install -r requirements.txt  # First time only
playwright install chromium      # First time only

python -m uvicorn chat_server:app --reload --port 8000
```

You should see:
```
🧲 Starting Lead Discovery Chat Server...
✅ Chat engine ready
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Terminal 2: Frontend (Next.js)**

```bash
cd frontend
npm install    # First time only
npm run dev
```

Then open **http://localhost:3000/chat** in your browser.

### 🐳 Option B: Docker (Recommended)

Docker bundles Python 3.12, Node 22, Playwright, Chromium, and all dependencies into containers — no local setup required.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

```bash
# 1. Set up your API keys (one-time)
cp backend/.env.example backend/.env
# Edit backend/.env and add your KIMI_API_KEY or OPENAI_API_KEY

# 2. Build & start both services
docker compose up --build

# That's it. Open http://localhost:3000/chat
```

**Subsequent runs** (no rebuild needed):
```bash
docker compose up        # Foreground
docker compose up -d     # Detached (background)
docker compose down      # Stop everything
```

**Run the CLI pipeline via Docker:**
```bash
# Test with sample companies
docker compose run --rm backend python main.py --test

# Process your own leads
docker compose run --rm backend python main.py --input sample_leads.csv

# With deep research
docker compose run --rm backend python main.py --input sample_leads.csv --deep-research

# Discover leads via Exa
docker compose run --rm backend python test_exa.py --export

# Deep research on a single company
docker compose run --rm backend python deep_research.py "Maxon Group" "https://www.maxongroup.com"
```

> **Note:** Output files are volume-mounted — results appear in `backend/output/` on your host machine.

### Chat Flow

1. **Describe** what companies you're looking for (e.g., "robotics startups building humanoid robots")
2. **Answer** 2-3 follow-up questions — the AI tracks readiness across: industry, company profile, technology focus, and qualifying criteria
3. **Launch Search** — generates semantic queries via AI, searches the web via Exa
4. **Qualify** — crawls each company's website and scores them 1-10 with the LLM
5. **Results** — hot leads, needs-review, and rejected, with reasoning and signals for each

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

Same as the CLI pipeline — at minimum `KIMI_API_KEY` or `OPENAI_API_KEY` in `backend/.env`. For search, also add `EXA_API_KEY`.

---

## CLI Pipeline

### Quick Start

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
├── backend/                    # Python pipeline + chat API
│   ├── Dockerfile              # 🐳 Python 3.12 + Playwright/Chromium image
│   ├── .dockerignore           # 🐳 Files excluded from Docker build
│   ├── main.py                 # 🎯 CLI pipeline orchestrator
│   ├── chat_server.py          # 🌐 FastAPI server for the chat interface
│   ├── chat_engine.py          # 🧠 Dual-LLM chat engine (conversation + query gen)
│   │
│   ├── config.py               # ⚙️  Settings: API keys, prompts, keywords, thresholds
│   ├── models.py               # 📦 Pydantic data models
│   │
│   ├── test_exa.py             # 🔍 Step 1: Exa AI lead discovery
│   ├── scraper.py              # 🌐 Step 2: Web crawling (crawl4ai + Playwright)
│   ├── intelligence.py         # 🧠 Step 3: LLM qualification (Kimi / OpenAI)
│   ├── deep_research.py        # 🔬 Step 4: Multi-page research for hot leads
│   ├── enrichment.py           # 📇 Step 5: Contact enrichment (Apollo / Hunter)
│   ├── export.py               # 📊 Step 6: Export to Excel / Google Sheets
│   │
│   ├── utils.py                # 🔧 Helpers: checkpointing, cost tracking
│   ├── run.sh                  # 🚀 Convenience shell script
│   ├── sample_leads.csv        # 📄 Example input file
│   ├── requirements.txt        # 📦 Python dependencies
│   ├── .env.example            # 🔑 API key template — copy to .env
│   └── output/                 # 📁 Generated results (gitignored)
│
├── frontend/                   # Next.js web UI
│   ├── Dockerfile              # 🐳 Multi-stage Node 22 build (73 MB image)
│   ├── .dockerignore           # 🐳 Files excluded from Docker build
│   ├── next.config.ts          # Next.js config (standalone output for Docker)
│   ├── src/app/
│   │   ├── page.tsx            # Landing page
│   │   ├── chat/page.tsx       # Chat interface page
│   │   ├── api/chat/           # Next.js API proxy routes
│   │   │   ├── route.ts        # Chat message proxy (→ FastAPI)
│   │   │   └── search/route.ts # Search proxy (→ FastAPI)
│   │   ├── layout.tsx          # Root layout
│   │   ├── globals.css         # Global styles + animations
│   │   └── components/
│   │       ├── chat/
│   │       │   └── ChatInterface.tsx  # Full chat + pipeline UI
│   │       ├── Navbar.tsx
│   │       └── ...             # Landing page components
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```

---

## How Each Module Works

### `chat_server.py` — Chat API Server

FastAPI server that powers the chat interface. Endpoints:

| Endpoint | What |
|----------|------|
| `POST /api/chat` | Sends conversation to the LLM, returns response + readiness state |
| `POST /api/chat/search` | Generates Exa queries from structured context, executes search |
| `POST /api/pipeline/run` | Runs crawl + qualify on found companies, streams results via SSE |
| `GET /api/health` | Health check (reports LLM and Exa availability) |

Includes per-IP rate limiting (30 req/min) and CORS for the frontend.

### `chat_engine.py` — Dual-LLM Chat Engine

The brain behind the chat interface. Two isolated LLM pipelines:

1. **Conversation LLM** — Talks to the user with a hardened system prompt. Extracts structured search parameters (industry, tech focus, criteria) through natural conversation. Outputs constrained JSON.
2. **Query Generation LLM** — Receives *only* the validated structured context. Generates 4-8 semantic Exa search queries. Never sees raw user input.

Falls back through: Kimi K2.5 → GPT-4o-mini. Input sanitization strips prompt injection patterns, special tokens, and HTML.

### `test_exa.py` — Lead Discovery

Uses [Exa AI](https://exa.ai) neural search to find companies matching your ideal customer profile. Exa is like Google but understands *meaning*, not just keywords. Describe the company you want (e.g., "humanoid robot company building actuators") and it returns matching websites.

- **Input:** Natural language search queries (12 pre-built for robotics/motors/magnets)
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
3. Scores the company 1-10 on likelihood they need your product
4. Returns structured JSON with: `confidence_score`, `hardware_type`, `industry_category`, `reasoning`, `key_signals`, `red_flags`

**Model priority chain:**
1. **Kimi K2.5** (vision + text) — cheapest option, supports screenshots
2. **OpenAI GPT-4o** (vision fallback)
3. **GPT-4o-mini** (text-only fallback)
4. **Keyword matching** (zero-cost fallback if all APIs fail)

Includes a quick pre-filter that rejects obvious non-hardware companies (SaaS, agencies, consultancies) without burning any LLM tokens.

### `deep_research.py` — Sales Intelligence

For hot leads (score ≥ 8), crawls up to 5 pages on their site and generates:
- Products they manufacture
- Motor types they use (BLDC, stepper, servo, etc.)
- Magnet requirements (NdFeB, SmCo, Halbach)
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

To target a different industry, edit these in `backend/config.py`:

- **`POSITIVE_KEYWORDS`** — Terms that signal a good-fit company (e.g., "robotics", "BLDC", "actuator")
- **`NEGATIVE_KEYWORDS`** — Terms that signal a bad fit (e.g., "SaaS", "marketing agency", "law firm")
- **`SYSTEM_PROMPT_QUALIFIER`** — The system prompt telling the LLM exactly what makes a good customer
- **`INDUSTRY_CATEGORIES`** — How to classify leads by industry vertical

For Exa discovery queries, edit `LEAD_QUERIES` in `backend/test_exa.py`.

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
- Backend: `cd backend && source venv/bin/activate && python -m uvicorn chat_server:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev`

Check `http://localhost:8000/api/health` — it should return `{"status": "ok", "llm_available": true, ...}`. If `llm_available` is false, your API keys aren't configured. The frontend falls back to mock responses when the backend is down.

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
- [ ] Generalize ICP config — per-campaign keywords/prompts instead of hardcoded
- [ ] Email drafting module — auto-generate cold emails from deep research
- [ ] CRM integrations — push hot leads to HubSpot, Salesforce, etc.
- [ ] Multi-tenant auth — user accounts and campaign history
- [ ] Deep research in chat — trigger multi-page analysis from the web UI

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test with `cd backend && python main.py --test --clear-checkpoint`
5. Submit a PR

Please keep the modular architecture — each module should do one thing and be independently testable.

---

## License

Private — Mainrich International
