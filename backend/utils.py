"""
Utility Functions

Helpers used across the pipeline:
  - CheckpointManager: Save/resume progress so you can stop and restart
  - OutputWriter: Writes processed leads to the correct CSV by score tier
  - CostTracker: Tracks LLM token usage and estimates API spend
  - determine_tier(score): Maps score → hot/review/rejected
  - extract_domain(url): Cleans URLs to bare domain
  - dedupe_by_domain(leads): Removes duplicate companies
"""

import json
import csv
import fcntl
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from models import ProcessedLead, ProcessingStats, QualificationTier
from config import (
    CHECKPOINT_FILE,
    QUALIFIED_FILE,
    REVIEW_FILE,
    REJECTED_FILE,
    SCORE_HOT_LEAD,
    SCORE_REVIEW,
    COST_PER_1K_TOKENS
)

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpointing for resume capability."""
    
    def __init__(self, checkpoint_file: Path = CHECKPOINT_FILE):
        self.checkpoint_file = checkpoint_file
        self.processed_urls: set[str] = set()
        self._load_checkpoint()
    
    def _load_checkpoint(self):
        """Load existing checkpoint if available."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_urls = set(data.get("processed_urls", []))
                    logger.info("Loaded checkpoint: %d already processed", len(self.processed_urls))
            except Exception as e:
                logger.warning("Could not load checkpoint: %s", e)
    
    def save_checkpoint(self):
        """Save current progress."""
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump({
                    "processed_urls": list(self.processed_urls),
                    "last_updated": datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.warning("Could not save checkpoint: %s", e)
    
    def mark_processed(self, url: str):
        """Mark a URL as processed."""
        self.processed_urls.add(url)
    
    def is_processed(self, url: str) -> bool:
        """Check if URL was already processed."""
        return url in self.processed_urls
    
    def clear(self):
        """Clear checkpoint (start fresh)."""
        self.processed_urls.clear()
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()


class OutputWriter:
    """Handles writing results to CSV files by tier."""
    
    def __init__(self):
        self.files_initialized = False
        self._init_files()
    
    def _init_files(self):
        """Initialize output files with headers."""
        headers = [
            "company_name", "website_url", "contact_name", 
            "linkedin_profile_url", "qualification_tier",
            "confidence_score", "is_qualified", "hardware_type",
            "industry_category", "reasoning", "key_signals",
            "red_flags", "email", "mobile_number",
            # Deep research fields
            "products_found", "technologies_used", "relevant_capabilities",
            "industries_served", "applications", "decision_maker_titles",
            "suggested_pitch_angle", "talking_points", "potential_volume",
            # Metadata
            "processed_at", "crawl_success", "error_message"
        ]
        for file_path in [QUALIFIED_FILE, REVIEW_FILE, REJECTED_FILE]:
            if not file_path.exists():
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
        self.files_initialized = True
    
    def write_lead(self, lead: ProcessedLead):
        """Write a processed lead to the appropriate file (with file locking)."""
        # Determine file based on tier
        if lead.qualification_tier == QualificationTier.HOT:
            file_path = QUALIFIED_FILE
        elif lead.qualification_tier == QualificationTier.REVIEW:
            file_path = REVIEW_FILE
        else:
            file_path = REJECTED_FILE
        
        row_data = lead.to_csv_dict()

        # Append with an exclusive lock so concurrent workers don't interleave rows
        with open(file_path, 'a', newline='', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                writer = csv.DictWriter(f, fieldnames=row_data.keys())
                writer.writerow(row_data)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def determine_tier(score: int) -> QualificationTier:
    """Determine qualification tier from score."""
    if score >= SCORE_HOT_LEAD:
        return QualificationTier.HOT
    elif score >= SCORE_REVIEW:
        return QualificationTier.REVIEW
    else:
        return QualificationTier.REJECTED


def estimate_cost(input_tokens: int, output_tokens: int, model: str = "gpt-4o-mini") -> float:
    """Estimate cost in USD for token usage."""
    rates = COST_PER_1K_TOKENS.get(model, COST_PER_1K_TOKENS["gpt-4o-mini"])
    input_cost = (input_tokens / 1000) * rates["input"]
    output_cost = (output_tokens / 1000) * rates["output"]
    return input_cost + output_cost


def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    url = url.lower().strip()
    
    # Remove protocol
    for prefix in ['https://', 'http://', 'www.']:
        if url.startswith(prefix):
            url = url[len(prefix):]
    
    # Remove path
    url = url.split('/')[0]
    
    return url


def dedupe_by_domain(leads: list) -> list:
    """Remove duplicate companies by domain."""
    seen_domains = set()
    unique_leads = []
    
    for lead in leads:
        domain = extract_domain(lead.website_url)
        if domain not in seen_domains:
            seen_domains.add(domain)
            unique_leads.append(lead)
    
    duplicates_removed = len(leads) - len(unique_leads)
    if duplicates_removed > 0:
        logger.info("Removed %d duplicate domains", duplicates_removed)
    
    return unique_leads


def print_lead_summary(lead: ProcessedLead):
    """Print a nice summary of a processed lead."""
    tier_emoji = {
        QualificationTier.HOT: "🔥",
        QualificationTier.REVIEW: "🔍", 
        QualificationTier.REJECTED: "❌"
    }
    
    emoji = tier_emoji.get(lead.qualification_tier, "•")
    
    logger.info("%s %s", emoji, lead.company_name)
    logger.info("   Score: %d/10 | %s", lead.confidence_score, lead.qualification_tier.value.upper())
    if lead.hardware_type:
        logger.debug("   Hardware: %s", lead.hardware_type)
    if lead.industry_category:
        logger.debug("   Industry: %s", lead.industry_category)
    logger.info("   Reason: %s...", lead.reasoning[:100])


class CostTracker:
    """Track API costs across the session."""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.api_calls = 0
        self.vision_calls = 0
    
    def add_usage(self, input_tokens: int, output_tokens: int, is_vision: bool = False):
        """Record token usage."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.api_calls += 1
        if is_vision:
            self.vision_calls += 1
    
    def get_total_cost(self, model: str = "gpt-4o-mini") -> float:
        """Get total estimated cost."""
        return estimate_cost(self.total_input_tokens, self.total_output_tokens, model)
    
    def summary(self) -> str:
        """Get cost summary string."""
        cost = self.get_total_cost()
        return (
            f"API Calls: {self.api_calls} (Vision: {self.vision_calls}) | "
            f"Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out | "
            f"Est. Cost: ${cost:.4f}"
        )


# Test
if __name__ == "__main__":
    # Test domain extraction
    test_urls = [
        "https://www.bostondynamics.com/products",
        "http://figure.ai",
        "maxongroup.com/en/company"
    ]
    
    for url in test_urls:
        print(f"{url} -> {extract_domain(url)}")
    
    # Test tier determination
    for score in [1, 3, 5, 7, 9]:
        print(f"Score {score} -> {determine_tier(score).value}")
