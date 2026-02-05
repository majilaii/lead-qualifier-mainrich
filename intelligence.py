"""
Intelligence Module - LLM-based Lead Qualification
Uses Kimi K2.5 for vision, with OpenAI fallback
"""

import json
import base64
from typing import Optional
import httpx

from openai import OpenAI, AsyncOpenAI
from pydantic import ValidationError

from models import QualificationResult, CrawlResult
from config import (
    OPENAI_API_KEY,
    KIMI_API_KEY,
    KIMI_API_BASE,
    TEXT_MODEL,
    VISION_MODEL,
    SYSTEM_PROMPT_QUALIFIER,
    USER_PROMPT_TEMPLATE,
    VISION_PROMPT_TEMPLATE,
    POSITIVE_KEYWORDS,
    NEGATIVE_KEYWORDS,
    COST_PER_1K_TOKENS,
)


class LeadQualifier:
    """Qualifies leads using LLM analysis of website content and screenshots."""
    
    def __init__(self):
        # Initialize OpenAI client
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        
        # Initialize Kimi client (uses OpenAI-compatible API)
        self.kimi_client = AsyncOpenAI(
            api_key=KIMI_API_KEY,
            base_url=KIMI_API_BASE
        ) if KIMI_API_KEY else None
        
        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    async def qualify_lead(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult,
        use_vision: bool = True
    ) -> QualificationResult:
        """
        Qualify a lead using LLM analysis.
        
        Args:
            company_name: Name of the company
            website_url: Company website URL
            crawl_result: Crawl result with markdown and screenshot
            use_vision: Whether to include screenshot analysis
            
        Returns:
            QualificationResult with score and reasoning
        """
        # If crawl failed, return low-confidence rejection
        if not crawl_result.success or not crawl_result.markdown_content:
            return QualificationResult(
                is_qualified=False,
                confidence_score=1,
                reasoning=f"Could not access website: {crawl_result.error_message}",
                red_flags=["Website inaccessible"]
            )
        
        # Quick keyword pre-check for obvious rejections
        quick_result = self._quick_keyword_check(crawl_result.markdown_content)
        if quick_result:
            return quick_result
        
        # Choose model and client based on availability and vision needs
        use_kimi_vision = (
            use_vision 
            and self.kimi_client 
            and crawl_result.screenshot_base64
        )
        
        try:
            if use_kimi_vision:
                print(f"  → Using Kimi vision for {company_name}")
                result = await self._qualify_with_kimi_vision(
                    company_name, website_url, crawl_result
                )
            elif self.kimi_client:
                print(f"  → Using Kimi text-only for {company_name}")
                result = await self._qualify_with_kimi_text(
                    company_name, website_url, crawl_result
                )
            elif self.openai_client:
                print(f"  → Using OpenAI for {company_name}")
                result = await self._qualify_with_openai(
                    company_name, website_url, crawl_result, use_vision
                )
            else:
                raise ValueError("No LLM API configured. Set OPENAI_API_KEY or KIMI_API_KEY.")
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ LLM Error for {company_name}: {e}")
            # Fallback to keyword-only analysis on LLM failure
            return self._keyword_only_qualification(
                company_name, 
                crawl_result.markdown_content,
                error_msg=str(e)
            )
    
    def _quick_keyword_check(self, content: str) -> Optional[QualificationResult]:
        """
        Quick pre-check for obvious negative signals.
        Returns a rejection result if clear negative signals found, None otherwise.
        """
        content_lower = content.lower()
        
        # Count strong negative signals
        strong_negatives = [
            "saas platform", "cloud solution", "digital agency",
            "marketing services", "seo agency", "consulting firm",
            "real estate", "property management", "law firm"
        ]
        
        negative_count = sum(1 for kw in strong_negatives if kw in content_lower)
        
        # If multiple strong negatives and no positive signals, quick reject
        if negative_count >= 2:
            positive_found = any(kw.lower() in content_lower for kw in POSITIVE_KEYWORDS[:20])
            if not positive_found:
                return QualificationResult(
                    is_qualified=False,
                    confidence_score=2,
                    reasoning="Website clearly indicates non-hardware business (software/services/consulting)",
                    red_flags=[f"Multiple negative signals: SaaS/consulting/services company"]
                )
        
        return None  # Proceed to full LLM analysis
    
    async def _qualify_with_kimi_vision(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult
    ) -> QualificationResult:
        """Qualify using Kimi K2.5 with vision capabilities."""
        
        # Build the user prompt with both text and image
        user_content = [
            {
                "type": "text",
                "text": USER_PROMPT_TEMPLATE.format(
                    company_name=company_name,
                    website_url=website_url,
                    markdown_content=crawl_result.markdown_content
                ) + self._get_json_schema_instruction() + "\n\nIMPORTANT: Return ONLY valid JSON. No explanations before or after."
            },
            {
                "type": "text", 
                "text": VISION_PROMPT_TEMPLATE
            }
        ]
        
        # Add image if available
        if crawl_result.screenshot_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{crawl_result.screenshot_base64}"
                }
            })
        
        response = await self.kimi_client.chat.completions.create(
            model="kimi-k2.5",  # Kimi's best vision model
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUALIFIER + " Always respond with valid JSON only."},
                {"role": "user", "content": user_content}
            ],
            temperature=1,  # kimi-k2.5 requires temperature=1
            max_tokens=1000
        )
        
        # Track tokens
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens
        
        return self._parse_llm_response(response.choices[0].message.content)
    
    async def _qualify_with_kimi_text(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult
    ) -> QualificationResult:
        """Qualify using Kimi with text only (no vision)."""
        
        prompt = USER_PROMPT_TEMPLATE.format(
            company_name=company_name,
            website_url=website_url,
            markdown_content=crawl_result.markdown_content
        )
        
        response = await self.kimi_client.chat.completions.create(
            model="moonshot-v1-32k",  # Use 32k model for text-only (faster, cheaper)
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUALIFIER + self._get_json_schema_instruction()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        # Track tokens
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens
        
        return self._parse_llm_response(response.choices[0].message.content)
    
    async def _qualify_with_openai(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult,
        use_vision: bool = True
    ) -> QualificationResult:
        """Qualify using OpenAI GPT-4o or GPT-4o-mini."""
        
        # Build messages
        user_content = []
        
        # Add text content
        user_content.append({
            "type": "text",
            "text": USER_PROMPT_TEMPLATE.format(
                company_name=company_name,
                website_url=website_url,
                markdown_content=crawl_result.markdown_content
            )
        })
        
        # Add vision if available and requested
        if use_vision and crawl_result.screenshot_base64:
            user_content.append({
                "type": "text",
                "text": VISION_PROMPT_TEMPLATE
            })
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{crawl_result.screenshot_base64}",
                    "detail": "low"  # Use low detail to save tokens
                }
            })
            model = "gpt-4o"  # Use full GPT-4o for vision
        else:
            model = TEXT_MODEL  # Use cheaper model for text-only
        
        response = await self.openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QUALIFIER + self._get_json_schema_instruction()},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1000
        )
        
        # Track tokens
        if response.usage:
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens
        
        return self._parse_llm_response(response.choices[0].message.content)
    
    def _get_json_schema_instruction(self) -> str:
        """Return JSON schema instruction for LLM."""
        return """

Respond with a JSON object in this exact format:
{
    "is_qualified": boolean,
    "confidence_score": integer from 1-10,
    "hardware_type": string or null (e.g., "Humanoid Robot", "Drone", "Medical Device"),
    "industry_category": string or null ("robotics", "aerospace", "medical", "automotive", "industrial", "motor_manufacturer", "consumer_electronics"),
    "reasoning": string (2-3 sentences explaining your decision),
    "key_signals": array of strings (positive signals found),
    "red_flags": array of strings (negative signals found)
}"""
    
    def _parse_llm_response(self, response_text: str) -> QualificationResult:
        """Parse LLM response into QualificationResult."""
        try:
            # Clean up response - strip whitespace and find JSON
            response_text = response_text.strip()
            
            # Try to find JSON object in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                response_text = json_match.group()
            
            data = json.loads(response_text)
            
            # Handle various field name formats from different LLMs
            score = data.get("confidence_score") or data.get("score") or 5
            qualified = data.get("is_qualified")
            if qualified is None:
                # Infer from score if not provided
                qualified = int(score) >= 6
            
            return QualificationResult(
                is_qualified=bool(qualified),
                confidence_score=min(10, max(1, int(score))),
                hardware_type=data.get("hardware_type") or data.get("category"),
                industry_category=data.get("industry_category") or data.get("industry"),
                reasoning=data.get("reasoning", "No reasoning provided"),
                key_signals=data.get("key_signals", []),
                red_flags=data.get("red_flags", [])
            )
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            # If parsing fails, try to extract fields from text using regex
            import re
            
            score = 5
            category = None
            reasoning = None
            
            # Try multiple field name patterns
            score_match = re.search(r'"(?:score|lead_score|confidence_score)"\s*:\s*(\d+)', response_text)
            if score_match:
                score = int(score_match.group(1))
            
            category_match = re.search(r'"(?:category|hardware_type)"\s*:\s*"([^"]+)"', response_text)
            if category_match:
                category = category_match.group(1)
                
            reasoning_match = re.search(r'"(?:reasoning|assessment)"\s*:\s*"?([^"]{20,500})', response_text)
            if reasoning_match:
                reasoning = reasoning_match.group(1)
            
            if score_match:
                return QualificationResult(
                    is_qualified=score >= 6,
                    confidence_score=min(10, max(1, score)),
                    hardware_type=category,
                    reasoning=reasoning or f"Score: {score}/10",
                    red_flags=["Partial parsing - some details may be missing"]
                )
            
            return QualificationResult(
                is_qualified=False,
                confidence_score=5,
                reasoning=f"Could not parse LLM response: {response_text[:200]}",
                red_flags=["Response parsing error"]
            )
    
    def _keyword_only_qualification(
        self, 
        company_name: str,
        content: str,
        error_msg: str = ""
    ) -> QualificationResult:
        """Fallback qualification using only keyword matching."""
        content_lower = content.lower()
        
        # Count positive and negative keywords
        positive_count = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in content_lower)
        negative_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in content_lower)
        
        # Simple scoring
        net_score = positive_count - (negative_count * 2)
        
        if net_score >= 5:
            score = 8
            qualified = True
        elif net_score >= 2:
            score = 6
            qualified = True
        elif net_score >= 0:
            score = 4
            qualified = False
        else:
            score = 2
            qualified = False
        
        return QualificationResult(
            is_qualified=qualified,
            confidence_score=score,
            reasoning=f"Keyword analysis (LLM unavailable: {error_msg[:50]}). Found {positive_count} positive and {negative_count} negative signals.",
            key_signals=[kw for kw in POSITIVE_KEYWORDS[:10] if kw.lower() in content_lower],
            red_flags=[kw for kw in NEGATIVE_KEYWORDS[:10] if kw.lower() in content_lower]
        )
    
    def get_cost_estimate(self) -> float:
        """Calculate estimated cost in USD."""
        # Use GPT-4o-mini pricing as baseline
        input_cost = (self.total_input_tokens / 1000) * 0.00015
        output_cost = (self.total_output_tokens / 1000) * 0.0006
        return input_cost + output_cost
    
    def reset_token_counts(self):
        """Reset token counters."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0


# Test function
async def test_qualifier():
    """Test the qualifier with a sample."""
    from scraper import crawl_company
    
    qualifier = LeadQualifier()
    
    # Test with Boston Dynamics (should be high score)
    print("Testing with Boston Dynamics...")
    crawl_result = await crawl_company("https://www.bostondynamics.com")
    
    if crawl_result.success:
        result = await qualifier.qualify_lead(
            company_name="Boston Dynamics",
            website_url="https://www.bostondynamics.com",
            crawl_result=crawl_result
        )
        print(f"Score: {result.confidence_score}/10")
        print(f"Qualified: {result.is_qualified}")
        print(f"Hardware: {result.hardware_type}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Est. Cost: ${qualifier.get_cost_estimate():.4f}")
    else:
        print(f"Crawl failed: {crawl_result.error_message}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_qualifier())
