"""
Deep Research Module - Enhanced analysis for high-potential leads
Scrapes multiple pages, extracts product details, identifies specific needs
"""

import asyncio
import json
import re
from typing import Optional
from dataclasses import dataclass

from openai import AsyncOpenAI

from scraper import crawl_company, truncate_to_tokens
from config import KIMI_API_KEY, KIMI_API_BASE


@dataclass
class DeepResearchResult:
    """Detailed research output for a hot lead."""
    company_name: str
    products_found: list[str]
    motor_types_used: list[str]
    magnet_requirements: list[str]
    industries_served: list[str]
    applications: list[str]
    technical_specs_mentioned: list[str]
    company_size_estimate: str
    potential_volume: str
    decision_maker_titles: list[str]
    suggested_pitch_angle: str
    talking_points: list[str]
    pages_analyzed: int
    confidence: str


ANALYSIS_PROMPT = """You are a technical sales researcher for a magnet supplier (NdFeB, SmCo, Halbach arrays).
Analyze this company and suggest how to sell magnets to them.

COMPANY: {company_name}
WEBSITE: {website_url}

WEBSITE CONTENT:
{content}

Return ONLY valid JSON (no markdown, no explanation):
{{
    "products_found": ["specific products they make"],
    "motor_types_used": ["BLDC", "stepper", "servo", "etc"],
    "magnet_requirements": ["NdFeB", "SmCo", "Halbach", "ferrite"],
    "industries_served": ["robotics", "medical", "automotive"],
    "applications": ["surgical robots", "drones", "EVs"],
    "technical_specs_mentioned": ["torque requirements", "size specs"],
    "company_size_estimate": "startup/mid-size/enterprise",
    "potential_volume": "prototype/small batch/mass production",
    "decision_maker_titles": ["VP Engineering", "CTO"],
    "suggested_pitch_angle": "one sentence sales approach",
    "talking_points": ["point 1", "point 2", "point 3"],
    "confidence": "High/Medium/Low"
}}"""


class DeepResearcher:
    """Performs deep research on high-potential leads."""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=KIMI_API_KEY,
            base_url=KIMI_API_BASE
        ) if KIMI_API_KEY else None
    
    def _get_target_pages(self, base_url: str) -> list[str]:
        """Generate list of important pages to crawl."""
        base = base_url.rstrip('/')
        return [
            base,
            f"{base}/products",
            f"{base}/solutions",
            f"{base}/technology",
            f"{base}/about",
        ]
    
    async def research_company(
        self, 
        company_name: str, 
        website_url: str,
        max_pages: int = 3
    ) -> DeepResearchResult:
        """Perform deep research on a company."""
        print(f"\n🔬 Deep Research: {company_name}")
        print(f"   Crawling up to {max_pages} pages...")
        
        # Crawl pages
        pages = self._get_target_pages(website_url)[:max_pages]
        all_content = []
        
        for url in pages:
            print(f"   📄 {url}")
            result = await crawl_company(url, take_screenshot=False)
            if result.success and result.markdown_content:
                # Keep only important content, truncate aggressively
                content = truncate_to_tokens(result.markdown_content, 2000)
                all_content.append(f"[{url}]\n{content}")
            await asyncio.sleep(0.5)
        
        if not all_content:
            print("   ❌ Could not crawl any pages")
            return self._empty_result(company_name)
        
        # Combine content - keep it short
        combined = "\n\n".join(all_content)
        combined = truncate_to_tokens(combined, 5000)  # ~5k tokens max
        
        print(f"   🧠 Analyzing {len(all_content)} pages...")
        
        try:
            response = await self.client.chat.completions.create(
                model="moonshot-v1-32k",
                messages=[{
                    "role": "user", 
                    "content": ANALYSIS_PROMPT.format(
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
                print("   ⚠️ Empty response")
                return self._empty_result(company_name)
            
            print(f"   ✅ Got response ({len(result_text)} chars)")
            
            # Parse JSON
            data = self._parse_json(result_text)
            
            return DeepResearchResult(
                company_name=company_name,
                products_found=data.get("products_found", []),
                motor_types_used=data.get("motor_types_used", []),
                magnet_requirements=data.get("magnet_requirements", []),
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
            print(f"   ❌ Error: {e}")
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
        return DeepResearchResult(
            company_name=company_name,
            products_found=[],
            motor_types_used=[],
            magnet_requirements=[],
            industries_served=[],
            applications=[],
            technical_specs_mentioned=[],
            company_size_estimate="Unknown",
            potential_volume="Unknown",
            decision_maker_titles=[],
            suggested_pitch_angle="",
            talking_points=[],
            pages_analyzed=0,
            confidence="None"
        )


def print_report(result: DeepResearchResult):
    """Print a nice formatted report."""
    print("\n" + "="*70)
    print(f"  DEEP RESEARCH REPORT: {result.company_name}")
    print(f"  Pages: {result.pages_analyzed} | Confidence: {result.confidence}")
    print("="*70)
    
    sections = [
        ("📦 PRODUCTS", result.products_found),
        ("⚡ MOTOR TYPES", result.motor_types_used),
        ("🧲 MAGNET NEEDS", result.magnet_requirements),
        ("🏭 INDUSTRIES", result.industries_served),
        ("🎯 APPLICATIONS", result.applications),
        ("📐 TECH SPECS", result.technical_specs_mentioned),
        ("👔 TARGET TITLES", result.decision_maker_titles),
        ("💬 TALKING POINTS", result.talking_points),
    ]
    
    for title, items in sections:
        if items:
            print(f"\n{title}:")
            for item in items[:5]:  # Limit to 5 items
                print(f"   • {item}")
    
    print(f"\n📊 BUSINESS INTEL:")
    print(f"   Company Size: {result.company_size_estimate}")
    print(f"   Volume Potential: {result.potential_volume}")
    
    if result.suggested_pitch_angle:
        print(f"\n💡 PITCH: {result.suggested_pitch_angle}")
    
    print("\n" + "="*70)


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
