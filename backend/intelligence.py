"""
Intelligence Module — LLM-based Lead Qualification (Core Value)

This is the brain of the pipeline. Given website content + optional screenshot,
it uses an LLM to score the company 1-10 on how likely they match the user's
search criteria (fully dynamic, industry-agnostic).

Model priority:
  1. Kimi K2.5 (vision + text) — cheapest, best value
  2. OpenAI GPT-4o (vision fallback)
  3. GPT-4o-mini (text-only fallback)
  4. Keyword matching (no-API fallback)

Output: QualificationResult with confidence_score, hardware_type,
        industry_category, reasoning, key_signals, red_flags
"""

import asyncio
import json
import base64
import logging
import random
import time
from typing import Optional
import httpx

from openai import OpenAI, AsyncOpenAI, RateLimitError
from pydantic import ValidationError

from models import QualificationResult, CrawlResult
from config import (
    OPENAI_API_KEY,
    KIMI_API_KEY,
    KIMI_API_BASE,
    TEXT_MODEL,
    VISION_MODEL,
    POSITIVE_KEYWORDS,
    NEGATIVE_KEYWORDS,
    COST_PER_1K_TOKENS,
)

logger = logging.getLogger(__name__)


class KimiRateLimiter:
    """Sliding-window rate limiter to stay under Kimi's 20 RPM org limit.
    
    We target 10 RPM (6s between requests) because vision calls with
    base64 screenshots are heavyweight and Kimi counts in-flight requests.
    All Kimi API calls must `await limiter.acquire()` before firing.
    Retries also go through the limiter, so they don't pile up.
    """
    
    def __init__(self, max_rpm: int = 10):
        self._min_interval = 60.0 / max_rpm  # 6s at 10 RPM
        self._lock = asyncio.Lock()
        self._last_call = 0.0
    
    async def acquire(self):
        """Wait until we're allowed to make the next API call."""
        async with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


# Global rate limiter — shared across all concurrent qualification tasks
_kimi_rate_limiter = KimiRateLimiter(max_rpm=10)


class KimiDailyLimitError(Exception):
    """Raised when Kimi's daily token budget (TPD) is exhausted.
    Signals that we should fall back to another model for the rest of the run."""
    pass


class KimiTPDTracker:
    """Track Kimi daily token limit exhaustion with automatic 24-hour TTL reset.

    Replaces the old module-level ``_kimi_tpd_exhausted`` boolean which:
      - Was process-wide (one user hitting the limit broke ALL users)
      - Never auto-reset (required a full process restart)

    Now the flag auto-clears 24 hours after it was set so the next day's
    quota is picked up without manual intervention.
    """

    def __init__(self, ttl_seconds: int = 86400):
        self._exhausted_at: float = 0.0
        self._ttl = ttl_seconds  # default 24 hours

    @property
    def is_exhausted(self) -> bool:
        if self._exhausted_at == 0.0:
            return False
        if (time.monotonic() - self._exhausted_at) >= self._ttl:
            # TTL expired — auto-reset
            self._exhausted_at = 0.0
            return False
        return True

    def mark_exhausted(self) -> None:
        self._exhausted_at = time.monotonic()

    def reset(self) -> None:
        self._exhausted_at = 0.0


# Shared TPD tracker — auto-resets after 24 hours
_kimi_tpd_tracker = KimiTPDTracker(ttl_seconds=86400)


class LeadQualifier:
    """Qualifies leads using LLM analysis of website content and screenshots."""
    
    def __init__(self, search_context: Optional[dict] = None):
        # Initialize OpenAI client
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        
        # Initialize Kimi client (uses OpenAI-compatible API)
        self.kimi_client = AsyncOpenAI(
            api_key=KIMI_API_KEY,
            base_url=KIMI_API_BASE,
            timeout=httpx.Timeout(120.0, connect=10.0)  # 120s read timeout, 10s connect
        ) if KIMI_API_KEY else None
        
        # Global rate limiter to stay under Kimi's 20 RPM org limit
        self.rate_limiter = _kimi_rate_limiter
        
        # Dynamic search context (from chat interface) — overrides hardcoded prompts
        self.search_context = search_context
        
        # Build prompts: dynamic if context provided, else generic B2B defaults
        if search_context:
            self._system_prompt = self._build_dynamic_system_prompt(search_context)
            self._user_prompt_template = self._build_dynamic_user_prompt(search_context)
            self._vision_prompt = self._build_dynamic_vision_prompt(search_context)
            self._json_schema = self._build_dynamic_json_schema(search_context)
        else:
            # Generic B2B fallback (no magnet/Mainrich assumptions)
            self._system_prompt = (
                "You are a B2B lead qualification assistant. Evaluate whether a company "
                "is a legitimate business that could be a potential B2B customer or partner.\n\n"
                "HIGH SCORE (8-10): Company clearly manufactures products or provides B2B services.\n"
                "MEDIUM SCORE (4-7): Company might be relevant but evidence is unclear.\n"
                "LOW SCORE (1-3): Pure software/SaaS, consulting, or unrelated services.\n\n"
                "IMPORTANT: Be objective. Score based ONLY on website content."
            )
            self._user_prompt_template = (
                "Analyze this company website to determine if they are a legitimate B2B company.\n\n"
                "COMPANY: {company_name}\nWEBSITE: {website_url}\n\n"
                "WEBSITE CONTENT (Markdown):\n{markdown_content}\n\n"
                "Based on this information, provide your qualification assessment."
            )
            self._vision_prompt = (
                "Look at this screenshot of the company's website.\n\n"
                "VISUAL ANALYSIS:\n"
                "1. Does the page show physical products, hardware, or manufacturing?\n"
                "2. Is this a real B2B company or a services/consulting firm?\n"
                "3. What visual evidence supports or contradicts a match?\n\n"
                "Consider this visual evidence alongside the text analysis."
            )
            self._json_schema = None  # use legacy _get_json_schema_instruction
        
        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
    
    # ── Dynamic Prompt Builders ────────────────

    @staticmethod
    def _build_dynamic_system_prompt(ctx: dict) -> str:
        """Build a qualification system prompt from the user's search context."""
        industry = ctx.get("industry") or "the specified industry"
        profile = ctx.get("company_profile") or ""
        tech = ctx.get("technology_focus") or ""
        criteria = ctx.get("qualifying_criteria") or ""
        disqualifiers = ctx.get("disqualifiers") or ""

        parts = [
            f"You are a B2B lead qualification assistant. Your job is to evaluate whether a company is a good match for a client searching for: {industry}.",
            "",
        ]

        if profile:
            parts.append(f"TARGET COMPANY PROFILE: {profile}")
        if tech:
            parts.append(f"TECHNOLOGY/PRODUCT FOCUS: {tech}")

        parts.append("")
        parts.append("SCORING GUIDELINES:")
        parts.append("HIGH SCORE (8-10): Company clearly matches the search criteria. Strong signals on their website.")
        parts.append("MEDIUM SCORE (4-7): Company might match but evidence is unclear or partial.")
        parts.append("LOW SCORE (1-3): Company clearly does not match the criteria.")

        if criteria:
            parts.append(f"\nQUALIFYING SIGNALS (score higher): {criteria}")
        if disqualifiers:
            parts.append(f"\nDISQUALIFYING SIGNALS (score lower): {disqualifiers}")

        parts.append("")
        parts.append("IMPORTANT: Be objective. Score based ONLY on what the website content shows, not assumptions.")
        parts.append("If the website is in a foreign language, still analyze the content — look for relevant products, services, and signals.")

        return "\n".join(parts)

    @staticmethod
    def _build_dynamic_user_prompt(ctx: dict) -> str:
        """Build user prompt template with dynamic context."""
        industry = ctx.get("industry") or "the target industry"
        return (
            f"Analyze this company website to determine if they match this search: {industry}\n\n"
            "COMPANY: {company_name}\n"
            "WEBSITE: {website_url}\n\n"
            "WEBSITE CONTENT (Markdown):\n{markdown_content}\n\n"
            "Based on this information, provide your qualification assessment."
        )

    @staticmethod
    def _build_dynamic_vision_prompt(ctx: dict) -> str:
        """Build vision prompt with dynamic context."""
        industry = ctx.get("industry") or "the target industry"
        return (
            "Look at this screenshot of the company's website.\n\n"
            "VISUAL ANALYSIS:\n"
            f"1. Does the page show products/services relevant to: {industry}?\n"
            "2. Is this clearly a business in the target industry or something unrelated?\n"
            "3. What visual evidence supports or contradicts a match?\n\n"
            "Consider this visual evidence alongside the text analysis."
        )

    @staticmethod
    def _build_dynamic_json_schema(ctx: dict) -> str:
        """Build JSON schema instruction with dynamic fields."""
        industry = ctx.get("industry") or "the target industry"
        return f"""

Respond with a JSON object in this exact format:
{{
    "is_qualified": boolean,
    "confidence_score": integer from 1-10,
    "company_type": string or null (what kind of company is this, e.g. "Dental Clinic", "Robotics Startup", "Motor Manufacturer"),
    "industry_category": string or null (their industry sector),
    "reasoning": string (2-3 sentences explaining how well they match the search for: {industry}),
    "key_signals": array of strings (positive signals found that match the search),
    "red_flags": array of strings (signals that suggest they don't match),
    "headquarters_location": string or null (the company's ACTUAL headquarters city/country — look for 'About Us', 'Contact', or footer address. Ignore the language or origin of the page itself. e.g. "Charlotte, NC, USA", "Munich, Germany")
}}"""
    
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
        kimi_available = self.kimi_client and not _kimi_tpd_tracker.is_exhausted
        use_kimi_vision = (
            use_vision 
            and kimi_available
            and crawl_result.screenshot_base64
        )
        
        try:
            # ── Tier 1: Kimi Vision (cheapest + best) ──
            if use_kimi_vision:
                try:
                    logger.info("Using Kimi vision for %s", company_name)
                    return await self._qualify_with_kimi_vision(
                        company_name, website_url, crawl_result
                    )
                except KimiDailyLimitError:
                    logger.warning("Kimi daily limit hit -- falling back to text-only")
                    # Fall through to text
            
            # ── Tier 2: Kimi Text-only (no screenshot tokens) ──
            if kimi_available:
                try:
                    logger.info("Falling back to Kimi text-only for %s", company_name)
                    return await self._qualify_with_kimi_text(
                        company_name, website_url, crawl_result
                    )
                except KimiDailyLimitError:
                    logger.warning("Kimi daily limit fully exhausted -- switching to OpenAI")
                    # Fall through to OpenAI
            
            # ── Tier 3: OpenAI ──
            if self.openai_client:
                logger.info("Using OpenAI for %s", company_name)
                return await self._qualify_with_openai(
                    company_name, website_url, crawl_result, use_vision
                )
            
            # ── Tier 4: Keyword-only ──
            logger.info("No LLM available, using keyword analysis for %s", company_name)
            return self._keyword_only_qualification(
                company_name,
                crawl_result.markdown_content,
                error_msg="All LLM APIs unavailable (Kimi TPD exhausted, no OpenAI key)"
            )
            
        except (asyncio.CancelledError, Exception) as e:
            logger.warning("LLM Error for %s: %s", company_name, e)
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
        
        NOTE: When using dynamic search context (chat interface), we SKIP this check
        entirely and let the LLM decide. The hardcoded keywords are Mainrich-specific
        and would misfire for other industries.
        """
        # Skip keyword shortcut when using dynamic context — let LLM decide
        if self.search_context:
            return None
        
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
        
        json_schema = self._json_schema or self._get_json_schema_instruction()
        
        # Build the user prompt with both text and image
        user_content = [
            {
                "type": "text",
                "text": self._user_prompt_template.format(
                    company_name=company_name,
                    website_url=website_url,
                    markdown_content=crawl_result.markdown_content
                ) + json_schema + "\n\nCRITICAL: Your response must be ONLY the JSON object. Do NOT include any explanation, analysis, or thinking. Start your response with { and end with }."
            },
            {
                "type": "text", 
                "text": self._vision_prompt
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
        
        # Try up to 4 times with rate-limiter + exponential backoff on 429
        last_error = None
        for attempt in range(4):
            try:
                await self.rate_limiter.acquire()  # Serialize: max 15 RPM across all tasks
                response = await self.kimi_client.chat.completions.create(
                    model="moonshot-v1-128k-vision-preview",
                    messages=[
                        {"role": "system", "content": self._system_prompt + " You MUST respond with ONLY a valid JSON object. No explanation or thinking text. Start with { and end with }."},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )
                
                # Track tokens
                if response.usage:
                    self.total_input_tokens += response.usage.prompt_tokens
                    self.total_output_tokens += response.usage.completion_tokens
                
                response_text = self._extract_kimi_response(response.choices[0].message)
                return self._parse_llm_response(response_text)
            except RateLimitError as e:
                last_error = e
                error_msg = str(e).lower()
                # Daily token limit (TPD) — no point retrying, bail immediately
                if 'tpd' in error_msg or 'tokens per day' in error_msg:
                    _kimi_tpd_tracker.mark_exhausted()
                    logger.error("Kimi daily token limit (TPD) exhausted -- will auto-reset in 24h")
                    raise KimiDailyLimitError(str(e))
                # RPM limit — exponential backoff: 3-4s, 6-7s, 12-13s, 24-25s
                backoff = (3 * (2 ** attempt)) + random.uniform(0, 1)
                logger.warning("Kimi vision rate-limited (attempt %d/4), backing off %.1fs...", attempt+1, backoff)
                await asyncio.sleep(backoff)
            except (asyncio.CancelledError, Exception) as e:
                last_error = e
                if attempt < 3:
                    logger.warning("Kimi vision attempt %d failed: %s: %s, retrying...", attempt+1, type(e).__name__, str(e)[:80])
                    await asyncio.sleep(2)
        
        # All RPM retries failed - return low-confidence result
        logger.error("Kimi vision failed after 4 attempts: %s", last_error)
        return QualificationResult(
            is_qualified=False,
            confidence_score=3,
            reasoning=f"LLM analysis failed: {last_error}",
            red_flags=["Could not complete AI analysis"]
        )
    
    async def _qualify_with_kimi_text(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult
    ) -> QualificationResult:
        """Qualify using Kimi with text only (no vision)."""
        
        json_schema = self._json_schema or self._get_json_schema_instruction()
        
        prompt = self._user_prompt_template.format(
            company_name=company_name,
            website_url=website_url,
            markdown_content=crawl_result.markdown_content
        )
        
        # Try up to 4 times with rate-limiter + exponential backoff on 429
        last_error = None
        for attempt in range(4):
            try:
                await self.rate_limiter.acquire()  # Serialize: max 15 RPM across all tasks
                response = await self.kimi_client.chat.completions.create(
                    model="kimi-k2-turbo-preview",
                    messages=[
                        {"role": "system", "content": self._system_prompt + json_schema + " Respond with ONLY the JSON object."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )
                
                # Track tokens
                if response.usage:
                    self.total_input_tokens += response.usage.prompt_tokens
                    self.total_output_tokens += response.usage.completion_tokens
                
                response_text = self._extract_kimi_response(response.choices[0].message)
                return self._parse_llm_response(response_text)
            except RateLimitError as e:
                last_error = e
                error_msg = str(e).lower()
                # Daily token limit (TPD) — no point retrying, bail immediately
                if 'tpd' in error_msg or 'tokens per day' in error_msg:
                    _kimi_tpd_tracker.mark_exhausted()
                    logger.error("Kimi daily token limit (TPD) exhausted -- will auto-reset in 24h")
                    raise KimiDailyLimitError(str(e))
                # RPM limit — exponential backoff: 3-4s, 6-7s, 12-13s, 24-25s
                backoff = (3 * (2 ** attempt)) + random.uniform(0, 1)
                logger.warning("Kimi text rate-limited (attempt %d/4), backing off %.1fs...", attempt+1, backoff)
                await asyncio.sleep(backoff)
            except (asyncio.CancelledError, Exception) as e:
                last_error = e
                if attempt < 3:
                    logger.warning("Kimi text attempt %d failed: %s: %s, retrying...", attempt+1, type(e).__name__, str(e)[:80])
                    await asyncio.sleep(2)
        
        # All RPM retries failed
        logger.error("Kimi text failed after 4 attempts: %s", last_error)
        return QualificationResult(
            is_qualified=False,
            confidence_score=3,
            reasoning=f"LLM analysis failed: {last_error}",
            red_flags=["Could not complete AI analysis"]
        )
    
    async def _qualify_with_openai(
        self,
        company_name: str,
        website_url: str,
        crawl_result: CrawlResult,
        use_vision: bool = True
    ) -> QualificationResult:
        """Qualify using OpenAI GPT-4o or GPT-4o-mini."""
        
        json_schema = self._json_schema or self._get_json_schema_instruction()
        
        # Build messages
        user_content = []
        
        # Add text content
        user_content.append({
            "type": "text",
            "text": self._user_prompt_template.format(
                company_name=company_name,
                website_url=website_url,
                markdown_content=crawl_result.markdown_content
            )
        })
        
        # Add vision if available and requested
        if use_vision and crawl_result.screenshot_base64:
            user_content.append({
                "type": "text",
                "text": self._vision_prompt
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
                {"role": "system", "content": self._system_prompt + json_schema},
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
    
    @staticmethod
    def _extract_kimi_response(message) -> str:
        """Extract response text from Kimi thinking model.
        
        Kimi K2.5 is a thinking model that puts reasoning in
        model_extra['reasoning_content'] and the final answer in content.
        Sometimes content is empty and the JSON is only in reasoning_content.
        
        Key issue: sometimes Kimi puts chain-of-thought text in 'content'
        that starts with "The user wants me to..." — that's thinking, not the answer.
        We need to detect this and look for actual JSON elsewhere.
        """
        content = message.content or ""
        reasoning = ""
        if hasattr(message, 'model_extra') and isinstance(message.model_extra, dict):
            reasoning = message.model_extra.get('reasoning_content', '') or ''
        
        # Detect if content is actually thinking/chain-of-thought (not the JSON answer)
        content_stripped = content.strip()
        is_thinking = (
            content_stripped.startswith("The user wants") or
            content_stripped.startswith("Let me") or
            content_stripped.startswith("I need to") or
            content_stripped.startswith("I'll ") or
            content_stripped.startswith("Looking at") or
            content_stripped.startswith("Based on") or
            content_stripped.startswith("Analyzing") or
            (len(content_stripped) > 200 and not content_stripped.startswith('{'))
        )
        
        # If content looks like clean JSON, prefer it
        if content_stripped.startswith('{') or content_stripped.startswith('```'):
            return content
        
        # If content is thinking text, check reasoning for the actual JSON
        if is_thinking and reasoning.strip() and '{' in reasoning:
            return reasoning
        
        # If content has a JSON block somewhere inside (after thinking text), return all of it
        # The parser will extract the JSON from the end
        if '{' in content and '}' in content:
            return content
        
        # Fall back to reasoning_content
        if reasoning.strip() and '{' in reasoning:
            return reasoning
        
        # Return whatever we have
        return content or reasoning

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
    "red_flags": array of strings (negative signals found),
    "headquarters_location": string or null (the company's ACTUAL headquarters city/country — look for 'About Us', 'Contact', or footer address. Ignore the language or origin of the page itself. e.g. "Charlotte, NC, USA", "Munich, Germany")
}"""
    
    def _parse_llm_response(self, response_text: str) -> QualificationResult:
        """Parse LLM response into QualificationResult."""
        try:
            import re
            # Clean up response - strip whitespace
            response_text = response_text.strip()
            
            # Debug: log what we're trying to parse
            preview = response_text[:120].replace('\n', ' ')
            if not response_text.startswith('{'):
                logger.warning("LLM response doesn't start with JSON: \"%s...\"", preview)
            
            # Remove markdown code fences: ```json ... ```
            cleaned = re.sub(r'```(?:json)?\s*', '', response_text).strip()
            
            # Strategy: find the LAST complete JSON object in the text.
            # Kimi thinking models put chain-of-thought first, then the JSON answer at the end.
            # Search from the end backwards for the outermost { } pair.
            last_close = cleaned.rfind('}')
            if last_close != -1:
                # Walk backwards to find the matching opening brace
                depth = 0
                for i in range(last_close, -1, -1):
                    if cleaned[i] == '}':
                        depth += 1
                    elif cleaned[i] == '{':
                        depth -= 1
                    if depth == 0:
                        fragment = cleaned[i:last_close + 1]
                        try:
                            data = json.loads(fragment)
                            if isinstance(data, dict) and any(k in data for k in ('confidence_score', 'score', 'is_qualified', 'reasoning')):
                                return self._build_result(data)
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break
            
            # Fallback: try all { positions from the start
            for m in re.finditer(r'\{', cleaned):
                # Find matching close brace
                start = m.start()
                depth = 0
                for i in range(start, len(cleaned)):
                    if cleaned[i] == '{':
                        depth += 1
                    elif cleaned[i] == '}':
                        depth -= 1
                    if depth == 0:
                        fragment = cleaned[start:i + 1]
                        if len(fragment) > 30:
                            try:
                                data = json.loads(fragment)
                                if isinstance(data, dict) and any(k in data for k in ('confidence_score', 'score', 'is_qualified', 'reasoning')):
                                    return self._build_result(data)
                            except (json.JSONDecodeError, ValueError):
                                pass
                        break
            
            # Last resort: regex extraction of score from raw text
            score_match = re.search(r'"(?:score|lead_score|confidence_score)"\s*:\s*(\d+)', response_text)
            if score_match:
                score = int(score_match.group(1))
                category_match = re.search(r'"(?:category|hardware_type)"\s*:\s*"([^"]+)"', response_text)
                reasoning_match = re.search(r'"(?:reasoning|assessment)"\s*:\s*"([^"]{10,500})"', response_text)
                return QualificationResult(
                    is_qualified=score >= 6,
                    confidence_score=min(10, max(1, score)),
                    hardware_type=category_match.group(1) if category_match else None,
                    reasoning=reasoning_match.group(1) if reasoning_match else f"Score: {score}/10",
                    red_flags=["Partial parsing - some details may be missing"]
                )
            
            return QualificationResult(
                is_qualified=False,
                confidence_score=5,
                reasoning=f"Could not parse LLM response: {response_text[:200]}",
                red_flags=["Response parsing error"]
            )
        except Exception as e:
            return QualificationResult(
                is_qualified=False,
                confidence_score=5,
                reasoning=f"Parse error: {str(e)[:100]}",
                red_flags=["Response parsing error"]
            )
    
    @staticmethod
    def _build_result(data: dict) -> QualificationResult:
        """Build a QualificationResult from a parsed JSON dict."""
        score = data.get("confidence_score") or data.get("score") or 5
        qualified = data.get("is_qualified")
        if qualified is None:
            qualified = int(score) >= 6
        # Accept both legacy "hardware_type" and dynamic "company_type" field names
        hw_type = data.get("hardware_type") or data.get("company_type") or data.get("category")
        return QualificationResult(
            is_qualified=bool(qualified),
            confidence_score=min(10, max(1, int(score))),
            hardware_type=hw_type,
            industry_category=data.get("industry_category") or data.get("industry"),
            reasoning=data.get("reasoning", "No reasoning provided"),
            key_signals=data.get("key_signals", []),
            red_flags=data.get("red_flags", []),
            headquarters_location=data.get("headquarters_location"),
        )

    def _keyword_only_qualification(
        self, 
        company_name: str,
        content: str,
        error_msg: str = ""
    ) -> QualificationResult:
        """Fallback qualification using only keyword matching."""
        content_lower = content.lower()
        
        if self.search_context:
            # Dynamic: extract keywords from the user's search context
            ctx_text = " ".join(v for v in self.search_context.values() if v).lower()
            ctx_words = [w.strip() for w in ctx_text.replace(",", " ").split() if len(w.strip()) > 3]
            matched = [w for w in ctx_words if w in content_lower]
            score = min(10, max(1, len(matched) * 2 + 3))
            return QualificationResult(
                is_qualified=score >= 6,
                confidence_score=score,
                reasoning=f"Keyword analysis (LLM unavailable: {error_msg[:50]}). Found {len(matched)} relevant terms from search context.",
                key_signals=matched[:10],
                red_flags=["LLM unavailable — keyword-only analysis"]
            )
        
        # Legacy: hardcoded Mainrich keywords
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
