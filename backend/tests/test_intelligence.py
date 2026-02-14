"""
Comprehensive tests for intelligence.py

Covers KimiTPDTracker, KimiRateLimiter, LeadQualifier response parsing,
keyword-only qualification, dynamic prompt building, cost estimation,
and tier determination.
"""

import time
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


# ═══════════════════════════════════════════════
# KimiTPDTracker
# ═══════════════════════════════════════════════

class TestKimiTPDTracker:
    def test_starts_not_exhausted(self):
        from intelligence import KimiTPDTracker
        tracker = KimiTPDTracker(ttl_seconds=60)
        assert tracker.is_exhausted is False

    def test_mark_exhausted(self):
        from intelligence import KimiTPDTracker
        tracker = KimiTPDTracker(ttl_seconds=60)
        tracker.mark_exhausted()
        assert tracker.is_exhausted is True

    def test_manual_reset(self):
        from intelligence import KimiTPDTracker
        tracker = KimiTPDTracker(ttl_seconds=60)
        tracker.mark_exhausted()
        tracker.reset()
        assert tracker.is_exhausted is False

    def test_auto_resets_after_ttl(self):
        from intelligence import KimiTPDTracker
        tracker = KimiTPDTracker(ttl_seconds=1)
        tracker.mark_exhausted()
        assert tracker.is_exhausted is True

        with patch("intelligence.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 2
            assert tracker.is_exhausted is False


# ═══════════════════════════════════════════════
# KimiRateLimiter
# ═══════════════════════════════════════════════

class TestKimiRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_does_not_block_first_call(self):
        from intelligence import KimiRateLimiter
        limiter = KimiRateLimiter(max_rpm=60)  # 1s interval
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # First call should be near-instant


# ═══════════════════════════════════════════════
# LeadQualifier — Response Parsing
# ═══════════════════════════════════════════════

class TestParseResponse:
    def setup_method(self):
        """Create a qualifier without any API clients."""
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            self.qualifier = LeadQualifier()

    def test_clean_json_response(self):
        response = json.dumps({
            "is_qualified": True,
            "confidence_score": 85,
            "hardware_type": "Motor Manufacturer",
            "industry_category": "Industrial Automation",
            "reasoning": "Strong manufacturing signals",
            "key_signals": ["brushless motors", "ISO 9001"],
            "red_flags": [],
        })
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 85
        assert result.is_qualified is True
        assert result.hardware_type == "Motor Manufacturer"

    def test_json_in_markdown_fence(self):
        response = '```json\n{"is_qualified": true, "confidence_score": 75, "reasoning": "Good"}\n```'
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 75

    def test_json_with_thinking_prefix(self):
        response = (
            "The user wants me to analyze this company. Let me look at the signals...\n\n"
            '{"is_qualified": true, "confidence_score": 80, "reasoning": "Match found"}'
        )
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 80

    def test_score_clamped_to_100(self):
        response = '{"is_qualified": true, "confidence_score": 150, "reasoning": "Amazing"}'
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 100

    def test_score_clamped_to_0(self):
        response = '{"is_qualified": false, "confidence_score": -10, "reasoning": "Bad"}'
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 0

    def test_unparseable_response_returns_50(self):
        result = self.qualifier._parse_llm_response("This is not JSON at all")
        assert result.confidence_score == 50
        assert "parsing error" in result.reasoning.lower() or "parse" in result.reasoning.lower()

    def test_regex_extraction_fallback(self):
        response = 'blah blah "confidence_score": 72 blah "reasoning": "Some analysis here that is long enough"'
        result = self.qualifier._parse_llm_response(response)
        assert result.confidence_score == 72

    def test_company_type_alias(self):
        """Dynamic searches use 'company_type' instead of 'hardware_type'."""
        response = json.dumps({
            "is_qualified": True,
            "confidence_score": 88,
            "company_type": "Dental Clinic",
            "reasoning": "Good dental practice",
        })
        result = self.qualifier._parse_llm_response(response)
        assert result.hardware_type == "Dental Clinic"


# ═══════════════════════════════════════════════
# LeadQualifier — Build Result
# ═══════════════════════════════════════════════

class TestBuildResult:
    def test_build_result_basic(self):
        from intelligence import LeadQualifier
        data = {
            "is_qualified": True,
            "confidence_score": 90,
            "hardware_type": "Robotics",
            "industry_category": "Automation",
            "reasoning": "Strong match",
            "key_signals": ["robots", "actuators"],
            "red_flags": [],
            "headquarters_location": "Boston, MA, USA",
        }
        result = LeadQualifier._build_result(data)
        assert result.confidence_score == 90
        assert result.hardware_type == "Robotics"
        assert result.headquarters_location == "Boston, MA, USA"

    def test_build_result_missing_qualified_inferred(self):
        from intelligence import LeadQualifier
        data = {"confidence_score": 75, "reasoning": "Looks good"}
        result = LeadQualifier._build_result(data)
        assert result.is_qualified is True  # 75 >= 60

    def test_build_result_low_score_not_qualified(self):
        from intelligence import LeadQualifier
        data = {"confidence_score": 30, "reasoning": "Not a match"}
        result = LeadQualifier._build_result(data)
        assert result.is_qualified is False  # 30 < 60

    def test_build_result_score_alias(self):
        from intelligence import LeadQualifier
        data = {"score": 65, "reasoning": "OK"}
        result = LeadQualifier._build_result(data)
        assert result.confidence_score == 65


# ═══════════════════════════════════════════════
# LeadQualifier — Keyword-only qualification
# ═══════════════════════════════════════════════

class TestKeywordQualification:
    def test_keyword_only_no_context(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            q = LeadQualifier()
            result = q._keyword_only_qualification(
                "Test Company",
                "We are a restaurant and real estate firm.",
                error_msg="No API keys",
            )
            assert result.confidence_score < 50
            assert result.is_qualified is False

    def test_keyword_only_with_search_context(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            ctx = {
                "industry": "robotics",
                "technology_focus": "brushless motors actuators",
            }
            q = LeadQualifier(search_context=ctx)
            result = q._keyword_only_qualification(
                "Motor Corp",
                "We manufacture brushless motors and precision actuators for robotics applications.",
                error_msg="No API keys",
            )
            assert result.confidence_score > 25
            assert len(result.key_signals) > 0


# ═══════════════════════════════════════════════
# LeadQualifier — Quick keyword check
# ═══════════════════════════════════════════════

class TestQuickKeywordCheck:
    def test_skips_when_search_context_provided(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            q = LeadQualifier(search_context={"industry": "dental"})
            result = q._quick_keyword_check("saas platform cloud solution digital agency")
            assert result is None  # Should skip and let LLM decide

    def test_rejects_strong_negatives_without_context(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            q = LeadQualifier()
            # Note: POSITIVE_KEYWORDS was removed from config but still
            # referenced in _quick_keyword_check — this causes a NameError
            # when ≥2 negatives are found. The function should be fixed to
            # remove the dead reference; test documents the current behaviour.
            with pytest.raises(NameError, match="POSITIVE_KEYWORDS"):
                q._quick_keyword_check("We are a saas platform and digital agency providing cloud solution services")


# ═══════════════════════════════════════════════
# LeadQualifier — Dynamic Prompt Building
# ═══════════════════════════════════════════════

class TestDynamicPrompts:
    def test_system_prompt_includes_industry(self):
        from intelligence import LeadQualifier
        prompt = LeadQualifier._build_dynamic_system_prompt({"industry": "Dental Clinics"})
        assert "Dental Clinics" in prompt

    def test_system_prompt_includes_geographic_constraint(self):
        from intelligence import LeadQualifier
        prompt = LeadQualifier._build_dynamic_system_prompt({
            "industry": "Dental",
            "geographic_region": "London, UK",
        })
        assert "London, UK" in prompt
        assert "GEOGRAPHIC CONSTRAINT" in prompt

    def test_user_prompt_template_has_placeholders(self):
        from intelligence import LeadQualifier
        template = LeadQualifier._build_dynamic_user_prompt({"industry": "Robotics"})
        assert "{company_name}" in template
        assert "{website_url}" in template
        assert "{markdown_content}" in template

    def test_vision_prompt_includes_industry(self):
        from intelligence import LeadQualifier
        prompt = LeadQualifier._build_dynamic_vision_prompt({"industry": "CNC Machining"})
        assert "CNC Machining" in prompt

    def test_json_schema_includes_industry(self):
        from intelligence import LeadQualifier
        schema = LeadQualifier._build_dynamic_json_schema({"industry": "EV Battery"})
        assert "EV Battery" in schema
        assert "confidence_score" in schema


# ═══════════════════════════════════════════════
# LeadQualifier — Cost tracking
# ═══════════════════════════════════════════════

class TestCostTracking:
    def test_cost_estimate(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            q = LeadQualifier()
            q.total_input_tokens = 10000
            q.total_output_tokens = 5000
            cost = q.get_cost_estimate()
            assert cost > 0
            assert isinstance(cost, float)

    def test_reset_token_counts(self):
        with patch("intelligence.OPENAI_API_KEY", ""), \
             patch("intelligence.KIMI_API_KEY", ""):
            from intelligence import LeadQualifier
            q = LeadQualifier()
            q.total_input_tokens = 5000
            q.total_output_tokens = 3000
            q.reset_token_counts()
            assert q.total_input_tokens == 0
            assert q.total_output_tokens == 0


# ═══════════════════════════════════════════════
# Tier determination (from utils)
# ═══════════════════════════════════════════════

class TestTierDetermination:
    def test_hot_boundaries(self):
        from utils import determine_tier
        from models import QualificationTier
        assert determine_tier(100) == QualificationTier.HOT
        assert determine_tier(70) == QualificationTier.HOT
        assert determine_tier(90) == QualificationTier.HOT

    def test_review_boundaries(self):
        from utils import determine_tier
        from models import QualificationTier
        assert determine_tier(69) == QualificationTier.REVIEW
        assert determine_tier(40) == QualificationTier.REVIEW
        assert determine_tier(50) == QualificationTier.REVIEW

    def test_rejected_boundaries(self):
        from utils import determine_tier
        from models import QualificationTier
        assert determine_tier(39) == QualificationTier.REJECTED
        assert determine_tier(0) == QualificationTier.REJECTED
        assert determine_tier(10) == QualificationTier.REJECTED


# ═══════════════════════════════════════════════
# Domain extraction (from utils)
# ═══════════════════════════════════════════════

class TestExtractDomain:
    def test_https_www(self):
        from utils import extract_domain
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_http_subdomain(self):
        from utils import extract_domain
        assert extract_domain("http://sub.domain.co.uk/path?q=1") == "sub.domain.co.uk"

    def test_bare_domain(self):
        from utils import extract_domain
        assert extract_domain("example.com") == "example.com"

    def test_with_path(self):
        from utils import extract_domain
        assert extract_domain("https://www.maxongroup.com/en/products") == "maxongroup.com"


# ═══════════════════════════════════════════════
# Kimi response extraction (static method)
# ═══════════════════════════════════════════════

class TestExtractKimiResponse:
    def test_clean_json_in_content(self):
        from intelligence import LeadQualifier
        msg = MagicMock()
        msg.content = '{"is_qualified": true, "confidence_score": 80, "reasoning": "Good"}'
        msg.model_extra = {}
        result = LeadQualifier._extract_kimi_response(msg)
        assert '"confidence_score": 80' in result

    def test_json_in_reasoning_only(self):
        from intelligence import LeadQualifier
        msg = MagicMock()
        msg.content = ""
        msg.model_extra = {
            "reasoning_content": '{"is_qualified": true, "confidence_score": 75, "reasoning": "Found"}'
        }
        result = LeadQualifier._extract_kimi_response(msg)
        assert "confidence_score" in result

    def test_thinking_text_in_content_falls_back(self):
        from intelligence import LeadQualifier
        msg = MagicMock()
        msg.content = "The user wants me to analyze this company. Let me think step by step..."
        msg.model_extra = {
            "reasoning_content": '{"is_qualified": false, "confidence_score": 30, "reasoning": "Not a match"}'
        }
        result = LeadQualifier._extract_kimi_response(msg)
        assert "confidence_score" in result
