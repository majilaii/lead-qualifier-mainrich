"""
Configuration & Constants for Lead Qualifier

Everything configurable lives here:
  - API keys and model selection
  - Scoring thresholds (what counts as hot/review/rejected)
  - Cost tracking rates

The qualification logic is now fully dynamic — driven by each user's
search context from the chat interface. No hardcoded industry prompts.
"""

from pathlib import Path
from typing import Literal
import os
from dotenv import load_dotenv

load_dotenv()

# ===========================================
# Paths
# ===========================================
BASE_DIR = Path(__file__).parent
INPUT_FILE = BASE_DIR / "input_leads.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Output files by qualification tier
QUALIFIED_FILE = OUTPUT_DIR / "qualified_hot_leads.csv"      # Score 70-100
REVIEW_FILE = OUTPUT_DIR / "review_manual_check.csv"         # Score 40-69
REJECTED_FILE = OUTPUT_DIR / "rejected_with_reasons.csv"     # Score 0-39
CHECKPOINT_FILE = OUTPUT_DIR / ".checkpoint.json"            # Resume support

# ===========================================
# API Keys
# ===========================================
def _get_valid_key(key_name: str) -> str:
    """Get API key, returning empty string if it's a placeholder."""
    key = os.getenv(key_name, "")
    # Filter out placeholder values
    if not key or "your" in key.lower() or key.startswith("sk-your"):
        return ""
    return key

OPENAI_API_KEY = _get_valid_key("OPENAI_API_KEY")
KIMI_API_KEY = _get_valid_key("KIMI_API_KEY")
ANTHROPIC_API_KEY = _get_valid_key("ANTHROPIC_API_KEY")

# Enrichment (optional - skip for manual workflow)
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")

# LinkedIn Enrichment (hot leads only)
PDL_API_KEY = os.getenv("PDL_API_KEY", "")  # People Data Labs
ROCKETREACH_API_KEY = os.getenv("ROCKETREACH_API_KEY", "")  # RocketReach

# ===========================================
# Stripe Billing
# ===========================================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")
STRIPE_ENT_PRICE_ID = os.getenv("STRIPE_ENT_PRICE_ID", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ===========================================
# Processing Config
# ===========================================
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "5"))
MAX_TOKENS_INPUT = 6000  # Truncate markdown to save costs
SCREENSHOT_WIDTH = 1280
SCREENSHOT_HEIGHT = 720
REQUEST_TIMEOUT = 30  # seconds

# ===========================================
# Model Selection
# ===========================================
TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")
VISION_MODEL = os.getenv("VISION_MODEL", "kimi-k2.5")

# Model API endpoints
KIMI_API_BASE = "https://api.moonshot.ai/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"

# ===========================================
# Qualification Thresholds
# ===========================================
SCORE_HOT_LEAD = 70     # Score >= 70 → Hot lead (auto-enrich if enabled)
SCORE_REVIEW = 40       # Score 40-69 → Manual review needed
# Score < 40 → Rejected

# ===========================================
# Minimal Universal B2B Negative Keywords
# (Used only in legacy CLI keyword-fallback path when no LLM is available)
# ===========================================
NEGATIVE_KEYWORDS = [
    "restaurant", "law firm", "hair salon", "real estate",
    "property management", "hotel", "hospitality", "food service",
]

# ===========================================
# Notifications (Resend)
# ===========================================
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
NOTIFICATION_FROM_EMAIL = os.getenv("NOTIFICATION_FROM_EMAIL", "Hunt <notifications@yourdomain.com>")
APP_URL = os.getenv("APP_URL", FRONTEND_URL)  # Reuse FRONTEND_URL as default

# ===========================================
# Cost Tracking (approximate USD)
# ===========================================
COST_PER_1K_TOKENS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "kimi-k2.5-thinking": {"input": 0.0003, "output": 0.0012},  # Estimated
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
}
