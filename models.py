"""
Pydantic Data Models

All structured data types used throughout the pipeline:
  - LeadInput: Raw lead from CSV (company_name, website_url, etc.)
  - CrawlResult: Output from web scraper (markdown, screenshot, etc.)
  - QualificationResult: LLM scoring output (score, reasoning, signals)
  - EnrichmentResult: Contact lookup data (email, phone, title)
  - ProcessedLead: Final combined result written to output CSV
  - ProcessingStats: Run statistics (counts, costs)
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class QualificationTier(str, Enum):
    """Lead qualification tiers based on score"""
    HOT = "hot"           # Score 8-10
    REVIEW = "review"     # Score 4-7
    REJECTED = "rejected" # Score 1-3


class LeadInput(BaseModel):
    """Input lead from Sales Navigator CSV"""
    company_name: str
    website_url: str
    contact_name: Optional[str] = None
    linkedin_profile_url: Optional[str] = None
    
    # Internal tracking
    row_index: int = 0


class QualificationResult(BaseModel):
    """Structured output from LLM qualification"""
    is_qualified: bool = Field(
        description="Whether the company is a potential customer for magnets/motors"
    )
    confidence_score: int = Field(
        ge=1, le=10,
        description="Confidence score from 1 (definitely not) to 10 (perfect fit)"
    )
    hardware_type: Optional[str] = Field(
        default=None,
        description="Type of hardware they build (e.g., 'Humanoid Robot', 'Drone', 'Surgical Device')"
    )
    industry_category: Optional[str] = Field(
        default=None,
        description="Industry category: robotics, aerospace, medical, automotive, industrial, motor_manufacturer, consumer_electronics"
    )
    reasoning: str = Field(
        description="Brief explanation of why they are/aren't qualified"
    )
    key_signals: list[str] = Field(
        default_factory=list,
        description="Key positive signals found (product names, technical terms)"
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Red flags that lowered the score"
    )


class CrawlResult(BaseModel):
    """Result from web crawler"""
    url: str
    success: bool
    markdown_content: Optional[str] = None
    screenshot_base64: Optional[str] = None
    title: Optional[str] = None
    error_message: Optional[str] = None
    crawl_time_seconds: float = 0.0


class EnrichmentResult(BaseModel):
    """Contact enrichment data (for future API integration)"""
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    work_phone: Optional[str] = None
    job_title: Optional[str] = None
    enrichment_source: Optional[str] = None  # apollo, hunter, manual


class ProcessedLead(BaseModel):
    """Final processed lead with all data"""
    # Original input
    company_name: str
    website_url: str
    contact_name: Optional[str] = None
    linkedin_profile_url: Optional[str] = None
    
    # Qualification results
    qualification_tier: QualificationTier
    confidence_score: int
    is_qualified: bool
    hardware_type: Optional[str] = None
    industry_category: Optional[str] = None
    reasoning: str
    key_signals: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    
    # Enrichment (optional)
    email: Optional[str] = None
    mobile_number: Optional[str] = None
    
    # Deep research (for hot leads)
    deep_research: Optional[dict] = None  # DeepResearchResult as dict
    
    # Metadata
    processed_at: datetime = Field(default_factory=datetime.now)
    crawl_success: bool = True
    error_message: Optional[str] = None
    
    def to_csv_dict(self) -> dict:
        """Convert to flat dict for CSV export"""
        # Extract deep research fields if available
        dr = self.deep_research or {}
        
        return {
            "company_name": self.company_name,
            "website_url": self.website_url,
            "contact_name": self.contact_name or "",
            "linkedin_profile_url": self.linkedin_profile_url or "",
            "qualification_tier": self.qualification_tier.value,
            "confidence_score": self.confidence_score,
            "is_qualified": self.is_qualified,
            "hardware_type": self.hardware_type or "",
            "industry_category": self.industry_category or "",
            "reasoning": self.reasoning,
            "key_signals": "; ".join(self.key_signals),
            "red_flags": "; ".join(self.red_flags),
            "email": self.email or "",
            "mobile_number": self.mobile_number or "",
            # Deep research fields
            "products_found": "; ".join(dr.get("products_found", [])),
            "motor_types_used": "; ".join(dr.get("motor_types_used", [])),
            "magnet_requirements": "; ".join(dr.get("magnet_requirements", [])),
            "industries_served": "; ".join(dr.get("industries_served", [])),
            "applications": "; ".join(dr.get("applications", [])),
            "decision_maker_titles": "; ".join(dr.get("decision_maker_titles", [])),
            "suggested_pitch_angle": dr.get("suggested_pitch_angle", ""),
            "talking_points": "; ".join(dr.get("talking_points", [])),
            "potential_volume": dr.get("potential_volume", ""),
            "processed_at": self.processed_at.isoformat(),
            "crawl_success": self.crawl_success,
            "error_message": self.error_message or "",
        }


class ProcessingStats(BaseModel):
    """Statistics for the processing run"""
    total_leads: int = 0
    processed: int = 0
    hot_leads: int = 0
    review_leads: int = 0
    rejected_leads: int = 0
    crawl_failures: int = 0
    
    # Cost tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    
    def summary(self) -> str:
        """Human-readable summary"""
        return f"""
╔══════════════════════════════════════════╗
║       LEAD QUALIFICATION SUMMARY         ║
╠══════════════════════════════════════════╣
║ Total Processed: {self.processed:>6} / {self.total_leads:<6}       ║
║ ────────────────────────────────────────║
║ 🔥 Hot Leads (8-10):     {self.hot_leads:>6}          ║
║ 🔍 Review Queue (4-7):   {self.review_leads:>6}          ║
║ ❌ Rejected (1-3):       {self.rejected_leads:>6}          ║
║ ⚠️  Crawl Failures:      {self.crawl_failures:>6}          ║
║ ────────────────────────────────────────║
║ 💰 Est. Cost: ${self.estimated_cost_usd:>7.4f}              ║
╚══════════════════════════════════════════╝
"""
