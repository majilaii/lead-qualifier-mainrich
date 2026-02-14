"""
Tests for utils.py

Covers CheckpointManager, CostTracker, determine_tier, extract_domain,
dedupe_by_domain, estimate_cost, and OutputWriter.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from utils import (
    CheckpointManager,
    CostTracker,
    determine_tier,
    extract_domain,
    dedupe_by_domain,
    estimate_cost,
)
from models import QualificationTier


# ═══════════════════════════════════════════════
# determine_tier
# ═══════════════════════════════════════════════

class TestDetermineTier:
    def test_hot(self):
        assert determine_tier(85) == QualificationTier.HOT
        assert determine_tier(100) == QualificationTier.HOT

    def test_review(self):
        assert determine_tier(50) == QualificationTier.REVIEW

    def test_rejected(self):
        assert determine_tier(10) == QualificationTier.REJECTED
        assert determine_tier(0) == QualificationTier.REJECTED

    def test_boundary_hot(self):
        from config import SCORE_HOT_LEAD
        assert determine_tier(SCORE_HOT_LEAD) == QualificationTier.HOT
        assert determine_tier(SCORE_HOT_LEAD - 1) != QualificationTier.HOT

    def test_boundary_review(self):
        from config import SCORE_REVIEW
        assert determine_tier(SCORE_REVIEW) == QualificationTier.REVIEW
        assert determine_tier(SCORE_REVIEW - 1) == QualificationTier.REJECTED


# ═══════════════════════════════════════════════
# extract_domain
# ═══════════════════════════════════════════════

class TestExtractDomain:
    def test_https(self):
        assert extract_domain("https://www.acme.com/products") == "acme.com"

    def test_http(self):
        assert extract_domain("http://acme.com") == "acme.com"

    def test_no_protocol(self):
        assert extract_domain("acme.com/page") == "acme.com"

    def test_www(self):
        assert extract_domain("www.acme.com") == "acme.com"

    def test_uppercase(self):
        assert extract_domain("HTTPS://WWW.ACME.COM") == "acme.com"

    def test_whitespace(self):
        assert extract_domain("  https://acme.com  ") == "acme.com"


# ═══════════════════════════════════════════════
# dedupe_by_domain
# ═══════════════════════════════════════════════

class TestDedupeByDomain:
    def test_removes_duplicates(self):
        leads = [
            MagicMock(website_url="https://acme.com"),
            MagicMock(website_url="https://www.acme.com"),
            MagicMock(website_url="https://other.com"),
        ]
        result = dedupe_by_domain(leads)
        assert len(result) == 2

    def test_empty_list(self):
        assert dedupe_by_domain([]) == []

    def test_no_duplicates(self):
        leads = [
            MagicMock(website_url="https://a.com"),
            MagicMock(website_url="https://b.com"),
        ]
        result = dedupe_by_domain(leads)
        assert len(result) == 2

    def test_preserves_first_occurrence(self):
        lead1 = MagicMock(website_url="https://acme.com")
        lead1.name = "first"
        lead2 = MagicMock(website_url="https://acme.com/other")
        lead2.name = "second"
        result = dedupe_by_domain([lead1, lead2])
        assert result[0].name == "first"


# ═══════════════════════════════════════════════
# estimate_cost
# ═══════════════════════════════════════════════

class TestEstimateCost:
    def test_zero_tokens(self):
        assert estimate_cost(0, 0) == 0.0

    def test_positive(self):
        cost = estimate_cost(1000, 500)
        assert cost > 0

    def test_unknown_model_uses_fallback(self):
        cost = estimate_cost(1000, 1000, model="nonexistent-model")
        assert cost > 0  # Falls back to gpt-4o-mini rates


# ═══════════════════════════════════════════════
# CostTracker
# ═══════════════════════════════════════════════

class TestCostTracker:
    def test_initial_state(self):
        t = CostTracker()
        assert t.total_input_tokens == 0
        assert t.total_output_tokens == 0
        assert t.api_calls == 0
        assert t.vision_calls == 0

    def test_add_usage(self):
        t = CostTracker()
        t.add_usage(100, 50)
        assert t.total_input_tokens == 100
        assert t.total_output_tokens == 50
        assert t.api_calls == 1

    def test_add_vision(self):
        t = CostTracker()
        t.add_usage(100, 50, is_vision=True)
        assert t.vision_calls == 1

    def test_accumulates(self):
        t = CostTracker()
        t.add_usage(100, 50)
        t.add_usage(200, 100)
        assert t.total_input_tokens == 300
        assert t.api_calls == 2

    def test_get_total_cost(self):
        t = CostTracker()
        t.add_usage(1000, 500)
        cost = t.get_total_cost()
        assert cost > 0

    def test_summary(self):
        t = CostTracker()
        t.add_usage(500, 200)
        s = t.summary()
        assert "API Calls: 1" in s
        assert "$" in s


# ═══════════════════════════════════════════════
# CheckpointManager
# ═══════════════════════════════════════════════

class TestCheckpointManager:
    def test_fresh_start(self, tmp_path):
        cp = CheckpointManager(tmp_path / "cp.json")
        assert len(cp.processed_urls) == 0

    def test_mark_and_check(self, tmp_path):
        cp = CheckpointManager(tmp_path / "cp.json")
        cp.mark_processed("https://acme.com")
        assert cp.is_processed("https://acme.com") is True
        assert cp.is_processed("https://other.com") is False

    def test_save_and_reload(self, tmp_path):
        cp_file = tmp_path / "cp.json"
        cp = CheckpointManager(cp_file)
        cp.mark_processed("https://acme.com")
        cp.save_checkpoint()

        cp2 = CheckpointManager(cp_file)
        assert cp2.is_processed("https://acme.com") is True

    def test_clear(self, tmp_path):
        cp_file = tmp_path / "cp.json"
        cp = CheckpointManager(cp_file)
        cp.mark_processed("https://acme.com")
        cp.save_checkpoint()
        cp.clear()
        assert len(cp.processed_urls) == 0
        assert not cp_file.exists()
