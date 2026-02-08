# 🧲 The Magnet Hunter

**AI-Powered B2B Lead Discovery & Qualification Pipeline**

Automatically discover, crawl, qualify, and research potential B2B customers using AI. Built for Mainrich International's magnet & motor business, designed to be generalized for any hardware B2B company.

---

## What It Does

```
CSV / Exa Search ──→ Web Crawler ──→ AI Qualifier ──→ Deep Research ──→ Output
     (find)           (scrape)        (score)          (analyze)        (CSV)
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

## Quick Start

### Prerequisites

- **Python 3.11+**
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
├── backend/                 # Python qualification pipeline
│   ├── main.py              # 🎯 Pipeline orchestrator — ties everything together
│   ├── config.py            # ⚙️  All settings: API keys, prompts, keywords, thresholds
│   ├── models.py            # 📦 Pydantic data models (LeadInput, QualificationResult, etc.)
│   │
│   ├── test_exa.py          # 🔍 Step 1: Discover leads via Exa AI semantic search
│   ├── scraper.py           # 🌐 Step 2: Crawl company websites (crawl4ai + Playwright)
│   ├── intelligence.py      # 🧠 Step 3: LLM-based lead qualification (Kimi / OpenAI)
│   ├── deep_research.py     # 🔬 Step 4: Deep multi-page analysis for hot leads
│   ├── enrichment.py        # 📇 Step 5: Contact enrichment (Apollo / Hunter)
│   ├── export.py            # 📊 Step 6: Export to Excel / Google Sheets
│   │
│   ├── utils.py             # 🔧 Helpers: checkpointing, cost tracking, deduplication
│   ├── run.sh               # 🚀 Convenience shell script for common commands
│   ├── sample_leads.csv     # 📄 Example input file (10 companies)
│   ├── requirements.txt     # 📦 Python dependencies
│   ├── .env.example         # 🔑 API key template — copy to .env
│   └── output/              # 📁 Generated results (gitignored)
│       ├── qualified_hot_leads.csv
│       ├── review_manual_check.csv
│       └── rejected_with_reasons.csv
│
├── frontend/                # Next.js landing page / dashboard (WIP)
│   ├── src/app/
│   │   ├── page.tsx         # Landing page
│   │   ├── layout.tsx       # Root layout
│   │   ├── globals.css      # Global styles
│   │   └── components/      # UI components
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```

---

## How Each Module Works

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

- [ ] Generalize ICP config — per-campaign keywords/prompts instead of hardcoded
- [ ] Email drafting module — auto-generate cold emails from deep research
- [ ] Web dashboard — Next.js frontend for campaign management
- [ ] Multi-tenant API — FastAPI wrapper for SaaS deployment
- [ ] CRM integrations — push hot leads to HubSpot, Salesforce, etc.

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
