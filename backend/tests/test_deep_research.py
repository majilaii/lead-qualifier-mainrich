"""
Tests for deep_research.py

Covers prompt building, JSON parsing, and DeepResearchResult structure.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock


# ═══════════════════════════════════════════════
# DeepResearchResult
# ═══════════════════════════════════════════════

class TestDeepResearchResult:
    def test_defaults(self):
        from deep_research import DeepResearchResult
        r = DeepResearchResult(company_name="Acme")
        assert r.company_name == "Acme"
        assert r.products_found == []
        assert r.technologies_used == []
        assert r.company_size_estimate == "Unknown"
        assert r.confidence == "None"
        assert r.pages_analyzed == 0

    def test_with_data(self):
        from deep_research import DeepResearchResult
        r = DeepResearchResult(
            company_name="Acme",
            products_found=["Motor A", "Motor B"],
            technologies_used=["BLDC", "Stepper"],
            company_size_estimate="mid-size",
            potential_volume="mass production",
            confidence="High",
            pages_analyzed=3,
        )
        assert len(r.products_found) == 2
        assert r.confidence == "High"
        assert r.pages_analyzed == 3


# ═══════════════════════════════════════════════
# Prompt building
# ═══════════════════════════════════════════════

class TestPromptBuilding:
    def test_generic_prompt_without_context(self):
        from deep_research import _build_analysis_prompt
        prompt = _build_analysis_prompt(None)
        assert "{company_name}" in prompt
        assert "{website_url}" in prompt
        assert "{content}" in prompt
        assert "B2B sales researcher" in prompt

    def test_dynamic_prompt_with_context(self):
        from deep_research import _build_analysis_prompt
        ctx = {
            "industry": "Dental Equipment",
            "technology_focus": "CAD/CAM milling",
            "qualifying_criteria": "ISO 13485 certified",
            "company_profile": "Mid-size manufacturers",
        }
        prompt = _build_analysis_prompt(ctx)
        assert "Dental Equipment" in prompt
        assert "CAD/CAM milling" in prompt
        assert "ISO 13485" in prompt


# ═══════════════════════════════════════════════
# DeepResearcher
# ═══════════════════════════════════════════════

class TestDeepResearcher:
    def test_init_without_key(self):
        with patch("deep_research.KIMI_API_KEY", ""):
            from deep_research import DeepResearcher
            r = DeepResearcher()
            assert r.client is None

    def test_target_pages(self):
        with patch("deep_research.KIMI_API_KEY", ""):
            from deep_research import DeepResearcher
            r = DeepResearcher()
            pages = r._get_target_pages("https://example.com")
            assert "https://example.com" in pages
            assert "https://example.com/products" in pages
            assert "https://example.com/about" in pages

    def test_custom_target_paths(self):
        with patch("deep_research.KIMI_API_KEY", ""):
            from deep_research import DeepResearcher
            r = DeepResearcher(target_paths=["/custom", "/other"])
            pages = r._get_target_pages("https://example.com")
            assert "https://example.com/custom" in pages
            assert "https://example.com/other" in pages

    @pytest.mark.asyncio
    async def test_research_without_api_key(self):
        with patch("deep_research.KIMI_API_KEY", ""):
            from deep_research import DeepResearcher
            r = DeepResearcher()
            result = await r.research_company("Acme", "https://acme.com")
            assert result.company_name == "Acme"
            assert result.pages_analyzed == 0


# ═══════════════════════════════════════════════
# JSON parsing
# ═══════════════════════════════════════════════

class TestJsonParsing:
    def setup_method(self):
        with patch("deep_research.KIMI_API_KEY", ""):
            from deep_research import DeepResearcher
            self.researcher = DeepResearcher()

    def test_clean_json(self):
        data = {"products_found": ["Motor A"], "confidence": "High"}
        result = self.researcher._parse_json(json.dumps(data))
        assert result["confidence"] == "High"

    def test_json_in_code_fence(self):
        text = '```json\n{"products_found": ["Widget"], "confidence": "Medium"}\n```'
        result = self.researcher._parse_json(text)
        assert result["confidence"] == "Medium"

    def test_json_in_text(self):
        text = 'Here is the analysis:\n{"products_found": [], "confidence": "Low"}\nDone.'
        result = self.researcher._parse_json(text)
        assert result["confidence"] == "Low"

    def test_unparseable_returns_empty(self):
        result = self.researcher._parse_json("This is not JSON")
        assert result == {}


# ═══════════════════════════════════════════════
# print_report (smoke test)
# ═══════════════════════════════════════════════

class TestPrintReport:
    def test_print_report_no_crash(self):
        from deep_research import print_report, DeepResearchResult
        result = DeepResearchResult(
            company_name="Acme",
            products_found=["Motor A"],
            technologies_used=["BLDC"],
            pages_analyzed=2,
            confidence="High",
            suggested_pitch_angle="Target engineering team",
        )
        # Should not raise
        print_report(result)
