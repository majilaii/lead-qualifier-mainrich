# The Magnet Hunter 🧲

**B2B Lead Qualification Tool for Mainrich International**

Automatically qualify sales leads from Sales Navigator exports to find companies that need permanent magnets and custom motors.

## Features

- **Web Crawling**: Scrapes company websites using `crawl4ai`
- **AI Qualification**: Uses LLM (Kimi K2.5 / GPT-4o) for intelligent scoring
- **Vision Analysis**: Analyzes screenshots to verify hardware companies
- **Confidence Routing**: Automatically sorts leads into Hot/Review/Rejected buckets
- **Cost Optimized**: Token truncation, image resizing, quick keyword pre-filtering
- **Resume Support**: Checkpoint system to continue where you left off

## Quick Start

### 1. Install Dependencies

```bash
cd lead-qualifier
pip install -r requirements.txt

# Install playwright browsers (required for crawl4ai)
playwright install chromium
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

At minimum, you need **one** of:
- `OPENAI_API_KEY` - For GPT-4o-mini text analysis
- `KIMI_API_KEY` - For Kimi K2.5 vision analysis (recommended)

### 3. Prepare Your Leads

Create `input_leads.csv` with Sales Navigator export format:

```csv
company_name,website_url,contact_name,linkedin_profile_url
Boston Dynamics,https://www.bostondynamics.com,Marc Raibert,https://linkedin.com/in/marcraibert
Figure AI,https://www.figure.ai,Brett Adcock,
```

Or use the included `sample_leads.csv` to test.

### 4. Run

```bash
# Test with sample companies
python main.py --test

# Process your leads
python main.py --input input_leads.csv

# Text-only mode (cheaper, no vision)
python main.py --no-vision

# Start fresh (ignore checkpoint)
python main.py --clear-checkpoint
```

## Output Files

Results are saved to the `output/` folder:

| File | Description |
|------|-------------|
| `qualified_hot_leads.csv` | Score 8-10: Ready for outreach |
| `review_manual_check.csv` | Score 4-7: Needs human review |
| `rejected_with_reasons.csv` | Score 1-3: Not a fit (with explanation) |

## Scoring System

| Score | Tier | Action |
|-------|------|--------|
| 8-10 | 🔥 Hot | Immediate outreach candidate |
| 4-7 | 🔍 Review | Manual review needed |
| 1-3 | ❌ Rejected | Not a hardware company |

## Target Customers for Mainrich

**High Score (Want These):**
- Robotics companies (humanoids, cobots, industrial)
- Drone/UAV manufacturers
- Medical device companies (surgical robots, prosthetics)
- Motor manufacturers (potential partners)
- EV/e-mobility companies

**Low Score (Reject):**
- SaaS/software companies
- Marketing agencies
- Distributors/resellers
- Consulting firms

## Cost Estimates

| Model | Cost per 100 leads |
|-------|-------------------|
| GPT-4o-mini (text only) | ~$0.15 |
| GPT-4o (with vision) | ~$2.50 |
| Kimi K2.5 (with vision) | ~$0.40 |

Vision analysis adds accuracy but costs more. For initial testing, use `--no-vision`.

## Enrichment (Optional)

Enrichment APIs are **disabled by default** to save money. The tool will output leads with LinkedIn URLs for manual lookup.

To enable API enrichment later:
1. Add API keys to `.env` (Apollo, Hunter, etc.)
2. Run with `--auto-enrich` flag

## Architecture

```
lead-qualifier/
├── main.py          # CLI orchestrator
├── scraper.py       # Web crawling with crawl4ai
├── intelligence.py  # LLM qualification logic
├── enrichment.py    # Contact lookup APIs
├── models.py        # Pydantic data schemas
├── config.py        # Settings & keywords
├── utils.py         # Helpers & checkpointing
└── output/          # Results by tier
```

## Troubleshooting

**"No module named crawl4ai"**
```bash
pip install crawl4ai
playwright install chromium
```

**"OPENAI_API_KEY not set"**
```bash
export OPENAI_API_KEY=sk-your-key-here
# Or add to .env file
```

**"Rate limit exceeded"**
- Reduce `CONCURRENCY_LIMIT` in config.py
- Add delays between requests

**Resume after crash**
- Just run again - checkpoint auto-resumes
- Use `--clear-checkpoint` to start over

## License

Internal tool for Mainrich International.
