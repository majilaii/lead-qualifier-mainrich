"""
Configuration & Constants for Lead Qualifier

Everything configurable lives here:
  - API keys and model selection
  - Scoring thresholds (what counts as hot/review/rejected)
  - Positive & negative keywords for your ICP (Ideal Customer Profile)
  - LLM system prompts that drive qualification logic
  - Cost tracking rates

To adapt this for a different industry, edit:
  - POSITIVE_KEYWORDS / NEGATIVE_KEYWORDS
  - SYSTEM_PROMPT_QUALIFIER
  - INDUSTRY_CATEGORIES
  - LEAD_QUERIES in test_exa.py
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
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")

# ===========================================
# Processing Config
# ===========================================
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "10"))
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
# Industry Keywords for Mainrich Magnet Business
# ===========================================

# POSITIVE SIGNALS - Companies that need magnets/motors
POSITIVE_KEYWORDS = [
    # Magnet/Motor Technical Terms
    "halbach array", "halbach", "permanent magnet", "rare earth magnet",
    "neodymium", "NdFeB", "samarium cobalt", "SmCo", "ferrite magnet",
    "brushless DC", "BLDC", "PMSM", "servo motor", "stepper motor",
    "linear motor", "voice coil", "torque motor", "direct drive",
    "frameless motor", "slotless motor", "coreless motor",
    "torque density", "cogging torque", "back-EMF", "magnetic circuit",
    
    # Hardware Categories (they need motors/magnets)
    "robotics", "robot", "humanoid", "exoskeleton", "prosthetics",
    "drone", "UAV", "quadcopter", "eVTOL", "propulsion",
    "surgical robot", "medical device", "MRI", "imaging",
    "haptic", "haptics", "force feedback", "gimbal", "stabilizer",
    "reaction wheel", "momentum wheel", "satellite", "spacecraft",
    "electric vehicle", "EV", "e-bike", "electric motor",
    "actuator", "linear actuator", "rotary actuator",
    "CNC", "spindle", "motion control", "servo drive",
    "automation", "industrial automation", "factory automation",
    "pick and place", "assembly robot", "cobot", "collaborative robot",
    
    # Motor Manufacturers (potential partners like Johnson Electric)
    "motor manufacturer", "motor supplier", "motor design",
    "Johnson Electric", "Maxon", "Faulhaber", "Allied Motion",
    "Portescap", "Moog", "Kollmorgen", "Parker", "Nidec",
    "motor winding", "stator", "rotor", "armature",
]

# NEGATIVE SIGNALS - Companies that won't need magnets
NEGATIVE_KEYWORDS = [
    # Pure Software
    "SaaS", "software as a service", "cloud platform", "web app",
    "mobile app", "iOS app", "Android app", "software development",
    "digital transformation", "IT consulting", "tech consulting",
    
    # Marketing/Services
    "SEO", "digital marketing", "marketing agency", "PR agency",
    "content marketing", "social media marketing", "advertising agency",
    "web design agency", "branding agency",
    
    # Distributors (not manufacturers)
    "distributor", "wholesale", "reseller", "dropship",
    "trading company", "import export", "sourcing agent",
    
    # Finance/Consulting
    "investment", "venture capital", "private equity", "hedge fund",
    "management consulting", "strategy consulting", "advisory",
    "accounting", "legal services", "law firm",
    
    # Unrelated Industries
    "real estate", "property management", "construction contractor",
    "restaurant", "food service", "hospitality", "hotel",
    "retail store", "fashion", "apparel", "clothing brand",
]

# ===========================================
# Industry Classification
# ===========================================
INDUSTRY_CATEGORIES = {
    "robotics": ["robot", "humanoid", "cobot", "automation", "exoskeleton"],
    "aerospace": ["drone", "UAV", "satellite", "spacecraft", "eVTOL", "propulsion"],
    "medical": ["surgical", "medical device", "prosthetic", "MRI", "imaging"],
    "automotive": ["EV", "electric vehicle", "e-bike", "motor vehicle"],
    "industrial": ["CNC", "spindle", "factory", "manufacturing", "motion control"],
    "motor_manufacturer": ["motor manufacturer", "motor design", "motor supplier"],
    "consumer_electronics": ["gimbal", "haptic", "consumer", "wearable"],
}

# ===========================================
# LLM Prompts
# ===========================================

SYSTEM_PROMPT_QUALIFIER = """You are a specialized B2B lead qualification assistant for Mainrich International, a premium supplier of permanent magnets (Halbach arrays, NdFeB, SmCo) and custom motor components.

YOUR MISSION: Identify companies that need high-performance magnets or motors.

IDEAL CUSTOMERS (High Score 8-10):
- Companies BUILDING robots, drones, medical devices, EVs, or industrial equipment
- Motor manufacturers who need magnet supply (potential partners)
- R&D teams developing new motor/actuator designs
- Hardware startups in robotics, aerospace, or medical

POTENTIAL CUSTOMERS (Medium Score 4-7):
- Companies that might use motors but unclear from website
- Large manufacturers with diverse product lines
- Companies mentioning automation but unclear if they build or buy

REJECT (Low Score 1-3):
- Pure software companies (SaaS, apps, cloud platforms)
- Marketing/consulting agencies
- Distributors or trading companies (not manufacturers)
- Finance, real estate, hospitality businesses

IMPORTANT: Motor manufacturers (Maxon, Faulhaber, etc.) are PARTNERS not competitors - score them HIGH."""

USER_PROMPT_TEMPLATE = """Analyze this company website to determine if they need permanent magnets or custom motors.

COMPANY: {company_name}
WEBSITE: {website_url}

WEBSITE CONTENT (Markdown):
{markdown_content}

Based on this information, provide your qualification assessment."""

VISION_PROMPT_TEMPLATE = """Look at this screenshot of the company's website landing page.

VISUAL ANALYSIS INSTRUCTIONS:
1. Does the page show physical hardware, machinery, or robots? (POSITIVE)
2. Does it show software dashboards, apps, or generic business imagery? (NEGATIVE)
3. Are there product images of motors, actuators, or mechanical components? (VERY POSITIVE)
4. Is this clearly a manufacturing/engineering company or a services company?

Consider this visual evidence alongside the text analysis."""

# ===========================================
# Cost Tracking (approximate USD)
# ===========================================
COST_PER_1K_TOKENS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "kimi-k2.5-thinking": {"input": 0.0003, "output": 0.0012},  # Estimated
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
}
