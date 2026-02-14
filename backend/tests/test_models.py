"""
Tests for models.py and config.py

Validates Pydantic data models, enum values, serialization,
and configuration constants.
"""

import pytest
from datetime import datetime


# ═══════════════════════════════════════════════
# QualificationTier enum
# ═══════════════════════════════════════════════

class TestQualificationTier:
    def test_enum_values(self):
        from models import QualificationTier
        assert QualificationTier.HOT.value == "hot"
        assert QualificationTier.REVIEW.value == "review"
        assert QualificationTier.REJECTED.value == "rejected"

    def test_enum_is_string(self):
        from models import QualificationTier
        assert isinstance(QualificationTier.HOT, str)
        assert QualificationTier.HOT == "hot"


# ═══════════════════════════════════════════════
# LeadInput
# ═══════════════════════════════════════════════

class TestLeadInput:
    def test_required_fields(self):
        from models import LeadInput
        lead = LeadInput(company_name="Acme", website_url="https://acme.com")
        assert lead.company_name == "Acme"
        assert lead.website_url == "https://acme.com"
        assert lead.contact_name is None
        assert lead.linkedin_profile_url is None
        assert lead.row_index == 0

    def test_optional_fields(self):
        from models import LeadInput
        lead = LeadInput(
            company_name="Acme",
            website_url="https://acme.com",
            contact_name="Jane Doe",
            linkedin_profile_url="https://linkedin.com/in/jane",
            row_index=42,
        )
        assert lead.contact_name == "Jane Doe"
        assert lead.row_index == 42


# ═══════════════════════════════════════════════
# QualificationResult
# ═══════════════════════════════════════════════

class TestQualificationResult:
    def test_score_range_valid(self):
        from models import QualificationResult
        r = QualificationResult(is_qualified=True, confidence_score=100, reasoning="Perfect")
        assert r.confidence_score == 100

    def test_score_range_min(self):
        from models import QualificationResult
        r = QualificationResult(is_qualified=False, confidence_score=0, reasoning="Bad")
        assert r.confidence_score == 0

    def test_score_out_of_range_high(self):
        from models import QualificationResult
        with pytest.raises(Exception):
            QualificationResult(is_qualified=True, confidence_score=101, reasoning="Too high")

    def test_score_out_of_range_low(self):
        from models import QualificationResult
        with pytest.raises(Exception):
            QualificationResult(is_qualified=False, confidence_score=-1, reasoning="Negative")

    def test_default_lists(self):
        from models import QualificationResult
        r = QualificationResult(is_qualified=True, confidence_score=50, reasoning="Meh")
        assert r.key_signals == []
        assert r.red_flags == []
        assert r.hardware_type is None
        assert r.industry_category is None

    def test_headquarters_location(self):
        from models import QualificationResult
        r = QualificationResult(
            is_qualified=True,
            confidence_score=80,
            reasoning="Good",
            headquarters_location="Munich, Germany",
        )
        assert r.headquarters_location == "Munich, Germany"


# ═══════════════════════════════════════════════
# CrawlResult
# ═══════════════════════════════════════════════

class TestCrawlResult:
    def test_successful_crawl(self):
        from models import CrawlResult
        r = CrawlResult(url="https://example.com", success=True, markdown_content="# Hello")
        assert r.success
        assert r.markdown_content == "# Hello"
        assert r.error_message is None

    def test_failed_crawl(self):
        from models import CrawlResult
        r = CrawlResult(url="https://bad.com", success=False, error_message="Timeout")
        assert not r.success
        assert r.error_message == "Timeout"

    def test_exa_fields(self):
        from models import CrawlResult
        r = CrawlResult(
            url="https://example.com",
            success=True,
            exa_text="Exa content here",
            exa_highlights="highlight1; highlight2",
            exa_score=0.95,
        )
        assert r.exa_text == "Exa content here"
        assert r.exa_score == 0.95


# ═══════════════════════════════════════════════
# EnrichmentResult
# ═══════════════════════════════════════════════

class TestEnrichmentResult:
    def test_defaults(self):
        from models import EnrichmentResult
        r = EnrichmentResult()
        assert r.email is None
        assert r.mobile_number is None
        assert r.enrichment_source is None

    def test_with_data(self):
        from models import EnrichmentResult
        r = EnrichmentResult(email="a@b.com", job_title="CEO", enrichment_source="hunter")
        assert r.email == "a@b.com"
        assert r.enrichment_source == "hunter"


# ═══════════════════════════════════════════════
# ProcessedLead
# ═══════════════════════════════════════════════

class TestProcessedLead:
    def test_to_csv_dict_keys(self):
        from models import ProcessedLead, QualificationTier
        lead = ProcessedLead(
            company_name="Acme",
            website_url="https://acme.com",
            qualification_tier=QualificationTier.HOT,
            confidence_score=90,
            is_qualified=True,
            reasoning="Great match",
        )
        d = lead.to_csv_dict()
        assert d["company_name"] == "Acme"
        assert d["qualification_tier"] == "hot"
        assert d["confidence_score"] == 90
        assert d["is_qualified"] is True
        assert "processed_at" in d

    def test_csv_dict_empty_optionals(self):
        from models import ProcessedLead, QualificationTier
        lead = ProcessedLead(
            company_name="Acme",
            website_url="https://acme.com",
            qualification_tier=QualificationTier.REJECTED,
            confidence_score=10,
            is_qualified=False,
            reasoning="Not relevant",
        )
        d = lead.to_csv_dict()
        assert d["contact_name"] == ""
        assert d["email"] == ""
        assert d["hardware_type"] == ""

    def test_csv_dict_joins_lists(self):
        from models import ProcessedLead, QualificationTier
        lead = ProcessedLead(
            company_name="Acme",
            website_url="https://acme.com",
            qualification_tier=QualificationTier.HOT,
            confidence_score=85,
            is_qualified=True,
            reasoning="Match",
            key_signals=["motor", "actuator"],
            red_flags=["small company"],
        )
        d = lead.to_csv_dict()
        assert d["key_signals"] == "motor; actuator"
        assert d["red_flags"] == "small company"

    def test_csv_dict_with_deep_research(self):
        from models import ProcessedLead, QualificationTier
        lead = ProcessedLead(
            company_name="Acme",
            website_url="https://acme.com",
            qualification_tier=QualificationTier.HOT,
            confidence_score=90,
            is_qualified=True,
            reasoning="Great",
            deep_research={
                "products_found": ["Motor A", "Motor B"],
                "technologies_used": ["BLDC"],
                "suggested_pitch_angle": "Approach via engineering team",
            },
        )
        d = lead.to_csv_dict()
        assert d["products_found"] == "Motor A; Motor B"
        assert d["suggested_pitch_angle"] == "Approach via engineering team"


# ═══════════════════════════════════════════════
# ProcessingStats
# ═══════════════════════════════════════════════

class TestProcessingStats:
    def test_summary_format(self):
        from models import ProcessingStats
        stats = ProcessingStats(
            total_leads=100,
            processed=80,
            hot_leads=20,
            review_leads=30,
            rejected_leads=30,
            crawl_failures=5,
            estimated_cost_usd=0.1234,
        )
        summary = stats.summary()
        assert "80" in summary
        assert "100" in summary
        assert "20" in summary
        assert "0.1234" in summary

    def test_defaults(self):
        from models import ProcessingStats
        stats = ProcessingStats()
        assert stats.total_leads == 0
        assert stats.processed == 0
        assert stats.estimated_cost_usd == 0.0


# ═══════════════════════════════════════════════
# Config constants
# ═══════════════════════════════════════════════

class TestConfig:
    def test_score_thresholds(self):
        from config import SCORE_HOT_LEAD, SCORE_REVIEW
        assert SCORE_HOT_LEAD == 70
        assert SCORE_REVIEW == 40
        assert SCORE_HOT_LEAD > SCORE_REVIEW

    def test_output_dir_exists(self):
        from config import OUTPUT_DIR
        assert OUTPUT_DIR.exists()

    def test_cost_per_1k_tokens_structure(self):
        from config import COST_PER_1K_TOKENS
        assert "gpt-4o-mini" in COST_PER_1K_TOKENS
        for model, rates in COST_PER_1K_TOKENS.items():
            assert "input" in rates
            assert "output" in rates
            assert rates["input"] >= 0
            assert rates["output"] >= 0

    def test_concurrency_limit_positive(self):
        from config import CONCURRENCY_LIMIT
        assert CONCURRENCY_LIMIT > 0

    def test_negative_keywords_exist(self):
        from config import NEGATIVE_KEYWORDS
        assert len(NEGATIVE_KEYWORDS) > 0
        assert "restaurant" in NEGATIVE_KEYWORDS

    def test_valid_key_filter(self):
        from config import _get_valid_key
        import os
        # Placeholder keys should return empty
        os.environ["_TEST_KEY"] = "sk-your-key-here"
        assert _get_valid_key("_TEST_KEY") == ""
        os.environ["_TEST_KEY"] = "your_api_key"
        assert _get_valid_key("_TEST_KEY") == ""
        # Real-looking keys should pass
        os.environ["_TEST_KEY"] = "sk-abc123real"
        assert _get_valid_key("_TEST_KEY") == "sk-abc123real"
        # Missing keys return empty
        assert _get_valid_key("_NONEXISTENT_KEY_12345") == ""
        del os.environ["_TEST_KEY"]
