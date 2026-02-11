"""
Deep Research Module — Sales Intelligence for Hot Leads

For leads scoring 8+, this module crawls multiple pages on their site
and generates a sales brief dynamically based on the user's search context:

  - Products they manufacture
  - Technologies they use (relevant to the user's industry)
  - Company size & production volume estimates
  - Decision-maker titles to target
  - Suggested pitch angle & talking points

The module is industry-agnostic: it takes ``search_context`` from the chat
engine so it works for magnets, software, medical devices, or any vertical.

Usage:
  python deep_research.py "Maxon Group" "https://www.maxongroup.com"
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from scraper import crawl_company, truncate_to_tokens
from config import KIMI_API_KEY, KIMI_API_BASE

logger = logging.getLogger(__name__)


@dataclass
class DeepResearchResult:
    """Detailed research output for a hot lead."""
    company_name: str
    products_found: list[str] = field(default_factory=list)
    technologies_used: list[str] = field(default_factory=list)
    relevant_capabilities: list[str] = field(default_factory=list)
    industries_served: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)
    technical_specs_mentioned: list[str] = field(default_factory=list)
    company_size_estimate: str = "Unknown"
    potential_volume: str = "Unknown"
    decision_maker_titles: list[str] = field(default_factory=list)
    suggested_pitch_angle: str = ""
    talking_points: list[str] = field(default_factory=list)
    pages_analyzed: int = 0
    confidence: str = "None"



def _build_analysis_prompt(search_context: Optional[dict] = None) -> str:
    """Build an analysis prompt dynamically from the user's search context.

    If *search_context* is ``None`` the prompt falls back to a generic
    B2B sales-research template (no hardcoded magnet references).
    """
    if search_context:
        industry = search_context.get("industry") or "the target industry"
        tech = search_context.get("technology_focus") or ""
        criteria = search_context.get("qualifying_criteria") or ""
        profile = search_context.get("company_profile") or ""

        role_line = f"You are a B2B sales researcher helping a client in: {industry}."
        if tech:
            role_line += f" The client's products/technology focus: {tech}."
        if criteria:
            role_line += f" Key qualifying signals: {criteria}."
        if profile:
            role_line += f" Target company profile: {profile}."
    else:
        role_line = (
            "You are a B2B sales researcher. "
            "Analyze this company and suggest how to approach them as a potential customer or partner."
        )

    return role_line + """

Analyze the company below and produce a sales intelligence brief.

COMPANY: {company_name}
WEBSITE: {website_url}

WEBSITE CONTENT:
{content}

Return ONLY valid JSON (no markdown, no explanation):
{{
    "products_found": ["specific products they make or sell"],
    "technologies_used": ["key technologies, components, or methods they use"],
    "relevant_capabilities": ["capabilities relevant to your client's offering"],
    "industries_served": ["industry verticals they operate in"],
    "applications": ["specific applications or use-cases"],
    "technical_specs_mentioned": ["notable technical details on their site"],
    "company_size_estimate": "startup/mid-size/enterprise",
    "potential_volume": "prototype/small batch/mass production",
    "decision_maker_titles": ["VP Engineering", "CTO", "Head of Procurement"],
    "suggested_pitch_angle": "one sentence sales approach",
    "talking_points": ["point 1", "point 2", "point 3"],
    "confidence": "High/Medium/Low"
}}"""


# Default target page paths to crawl (generic, not magnet-specific)
_DEFAULT_TARGET_PATHS = [
    "",              # homepage
    "/products",
    "/solutions",
    "/services",
    "/technology",
    "/about",
]


class DeepResearcher:
    """Performs deep research on high-potential leads.

    Args:
        search_context: Optional dict with keys ``industry``,
            ``technology_focus``, ``qualifying_criteria``, ``company_profile``.
            When provided the analysis prompt is built dynamically.
        target_paths: Optional list of URL path suffixes to crawl (e.g.
            ``["/products", "/about"]``).  Defaults to a generic set.
    """

    def __init__(
        self,
        search_context: Optional[dict] = None,
        target_paths: Optional[list[str]] = None,
    ):
        self.client = AsyncOpenAI(
            api_key=KIMI_API_KEY,
            base_url=KIMI_API_BASE
        ) if KIMI_API_KEY else None
        self.search_context = search_context
        self._analysis_prompt = _build_analysis_prompt(search_context)
        self._target_paths = target_paths or _DEFAULT_TARGET_PATHS

    def _get_target_pages(self, base_url: str) -> list[str]:
        """Generate list of important pages to crawl."""
        base = base_url.rstrip('/')
        return [f"{base}{p}" for p in self._target_paths]
    
    async def research_company(
        self, 
        company_name: str, 
        website_url: str,
        max_pages: int = 3
    ) -> DeepResearchResult:
        """Perform deep research on a company."""
        logger.info("Deep Research: %s", company_name)
        
        if not self.client:
            logger.error("No Kimi API key configured -- cannot run deep research")
            return self._empty_result(company_name)
        
        logger.debug("Crawling up to %d pages...", max_pages)
        
        # Crawl pages
        pages = self._get_target_pages(website_url)[:max_pages]
        all_content = []
        
        for url in pages:
            logger.debug("Crawling page: %s", url)
            result = await crawl_company(url, take_screenshot=False)
            if result.success and result.markdown_content:
                # Keep only important content, truncate aggressively
                content = truncate_to_tokens(result.markdown_content, 2000)
                all_content.append(f"[{url}]\n{content}")
            await asyncio.sleep(0.5)
        
        if not all_content:
            logger.error("Could not crawl any pages")
            return self._empty_result(company_name)
        
        # Combine content - keep it short
        combined = "\n\n".join(all_content)
        combined = truncate_to_tokens(combined, 5000)  # ~5k tokens max
        
        logger.info("Analyzing %d pages...", len(all_content))
        
        try:
            response = await self.client.chat.completions.create(
                model="kimi-k2-turbo-preview",
                messages=[{
                    "role": "user", 
                    "content": self._analysis_prompt.format(
                        company_name=company_name,
                        website_url=website_url,
                        content=combined
                    )
                }],
                temperature=0.3,
                max_tokens=1500
            )
            
            result_text = response.choices[0].message.content
            
            if not result_text:
                logger.warning("Empty response")
                return self._empty_result(company_name)
            
            logger.info("Got response (%d chars)", len(result_text))
            
            # Parse JSON
            data = self._parse_json(result_text)
            
            return DeepResearchResult(
                company_name=company_name,
                products_found=data.get("products_found", []),
                technologies_used=data.get("technologies_used", data.get("motor_types_used", [])),
                relevant_capabilities=data.get("relevant_capabilities", data.get("magnet_requirements", [])),
                industries_served=data.get("industries_served", []),
                applications=data.get("applications", []),
                technical_specs_mentioned=data.get("technical_specs_mentioned", []),
                company_size_estimate=data.get("company_size_estimate", "Unknown"),
                potential_volume=data.get("potential_volume", "Unknown"),
                decision_maker_titles=data.get("decision_maker_titles", []),
                suggested_pitch_angle=data.get("suggested_pitch_angle", ""),
                talking_points=data.get("talking_points", []),
                pages_analyzed=len(all_content),
                confidence=data.get("confidence", "Low")
            )
            
        except Exception as e:
            logger.error("Deep research error: %s", e)
            return self._empty_result(company_name)
    
    def _parse_json(self, text: str) -> dict:
        """Parse JSON from response, handling various formats."""
        text = text.strip()
        
        # Remove markdown code blocks
        if "```json" in text:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
        elif "```" in text:
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
        
        # Try direct parse
        try:
            return json.loads(text)
        except:
            pass
        
        # Find JSON object in text
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        
        # Return empty dict as fallback
        return {}
    
    def _empty_result(self, company_name: str) -> DeepResearchResult:
        """Return empty result."""
        return DeepResearchResult(company_name=company_name)


def print_report(result: DeepResearchResult):
    """Log a formatted deep research report."""
    logger.info("=" * 70)
    logger.info("DEEP RESEARCH REPORT: %s", result.company_name)
    logger.info("Pages: %d | Confidence: %s", result.pages_analyzed, result.confidence)
    logger.info("=" * 70)
    
    sections = [
        ("PRODUCTS", result.products_found),
        ("TECHNOLOGIES", result.technologies_used),
        ("KEY CAPABILITIES", result.relevant_capabilities),
        ("INDUSTRIES", result.industries_served),
        ("APPLICATIONS", result.applications),
        ("TECH SPECS", result.technical_specs_mentioned),
        ("TARGET TITLES", result.decision_maker_titles),
        ("TALKING POINTS", result.talking_points),
    ]
    
    for title, items in sections:
        if items:
            logger.info("%s:", title)
            for item in items[:5]:  # Limit to 5 items
                logger.info("   - %s", item)
    
    logger.info("BUSINESS INTEL:")
    logger.info("   Company Size: %s", result.company_size_estimate)
    logger.info("   Volume Potential: %s", result.potential_volume)
    
    if result.suggested_pitch_angle:
        logger.info("PITCH: %s", result.suggested_pitch_angle)
    
    logger.info("=" * 70)


async def main():
    """CLI for deep research."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python deep_research.py <company_name> <website_url>")
        print("Example: python deep_research.py 'Maxon Group' 'https://www.maxongroup.com'")
        sys.exit(1)
    
    company = sys.argv[1]
    url = sys.argv[2]
    
    researcher = DeepResearcher()
    result = await researcher.research_company(company, url)
    print_report(result)


if __name__ == "__main__":
    asyncio.run(main())
