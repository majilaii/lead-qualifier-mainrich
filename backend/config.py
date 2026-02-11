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
QUALIFIED_FILE = OUTPUT_DIR / "qualified_hot_leads.csv"      # Score 8-10
REVIEW_FILE = OUTPUT_DIR / "review_manual_check.csv"         # Score 4-7
REJECTED_FILE = OUTPUT_DIR / "rejected_with_reasons.csv"     # Score 1-3
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
VISION_MODEL = os.getenv("VISION_MODEL", "kimi-k2.5-thinking")

# Model API endpoints
KIMI_API_BASE = "https://api.moonshot.ai/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"

# ===========================================
# Qualification Thresholds
# ===========================================
SCORE_HOT_LEAD = 8      # Score >= 8 → Hot lead (auto-enrich if enabled)
SCORE_REVIEW = 4        # Score 4-7 → Manual review needed
# Score < 4 → Rejected

# ===========================================
# Minimal Universal B2B Negative Keywords
# (Used only in legacy CLI fallback path)
# ===========================================
NEGATIVE_KEYWORDS = [
    "restaurant", "law firm", "hair salon", "real estate",
    "property management", "hotel", "hospitality", "food service",
]

# Legacy: kept for backward compatibility only. Not used in dynamic path.
POSITIVE_KEYWORDS: list[str] = []

# ===========================================
# Cost Tracking (approximate USD)
# ===========================================
COST_PER_1K_TOKENS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "kimi-k2.5-thinking": {"input": 0.0003, "output": 0.0012},  # Estimated
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
}
