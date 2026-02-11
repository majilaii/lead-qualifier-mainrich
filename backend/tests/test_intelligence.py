"""
Tests for KimiTPDTracker in intelligence.py

Verifies the 24-hour TTL auto-reset behaviour that replaced
the old global boolean _kimi_tpd_exhausted flag.
"""

import time
from unittest.mock import patch

import pytest


def test_tracker_starts_not_exhausted():
    from intelligence import KimiTPDTracker

    tracker = KimiTPDTracker(ttl_seconds=60)
    assert tracker.is_exhausted is False


def test_tracker_mark_exhausted():
    from intelligence import KimiTPDTracker

    tracker = KimiTPDTracker(ttl_seconds=60)
    tracker.mark_exhausted()
    assert tracker.is_exhausted is True


def test_tracker_manual_reset():
    from intelligence import KimiTPDTracker

    tracker = KimiTPDTracker(ttl_seconds=60)
    tracker.mark_exhausted()
    tracker.reset()
    assert tracker.is_exhausted is False


def test_tracker_auto_resets_after_ttl():
    from intelligence import KimiTPDTracker

    tracker = KimiTPDTracker(ttl_seconds=1)
    tracker.mark_exhausted()
    assert tracker.is_exhausted is True

    # Fast-forward monotonic clock past the TTL
    with patch("intelligence.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 2
        assert tracker.is_exhausted is False


def test_determine_tier_boundaries():
    from utils import determine_tier
    from models import QualificationTier

    assert determine_tier(9) == QualificationTier.HOT
    assert determine_tier(8) == QualificationTier.HOT
    assert determine_tier(7) == QualificationTier.REVIEW
    assert determine_tier(5) == QualificationTier.REVIEW
    assert determine_tier(4) == QualificationTier.REVIEW   # 4 is the review threshold
    assert determine_tier(3) == QualificationTier.REJECTED
    assert determine_tier(1) == QualificationTier.REJECTED


def test_extract_domain():
    from utils import extract_domain

    assert extract_domain("https://www.example.com/page") == "example.com"
    assert extract_domain("http://sub.domain.co.uk/path?q=1") == "sub.domain.co.uk"
    assert extract_domain("example.com") == "example.com"
