"""
Tests for enrichment.py

Verifies Hunter.io enrichment logic, status reporting,
and API enable/disable.
"""

import pytest
from unittest.mock import patch, AsyncMock


def test_enrichment_status_no_key():
    """Without HUNTER_API_KEY, status should report not configured."""
    with patch("enrichment.HUNTER_API_KEY", ""):
        from enrichment import get_enrichment_status

        status = get_enrichment_status()
        assert status["hunter_configured"] is False
        assert status["providers"] == []
        assert status["mode"] == "manual"


def test_enrichment_status_with_key():
    """With HUNTER_API_KEY, status should report configured."""
    with patch("enrichment.HUNTER_API_KEY", "test-key-123"):
        from enrichment import get_enrichment_status

        status = get_enrichment_status()
        assert status["hunter_configured"] is True
        assert "hunter" in status["providers"]
        assert status["mode"] == "hunter"


@pytest.mark.asyncio
async def test_enrich_contact_disabled():
    """When API is disabled, should return manual_required."""
    with patch("enrichment._api_enabled", False):
        from enrichment import enrich_contact

        result = await enrich_contact(None, "example.com")
        assert result.enrichment_source == "manual_required"


@pytest.mark.asyncio
async def test_enrich_contact_no_key():
    """When API enabled but no key, should return not_configured."""
    with patch("enrichment._api_enabled", True), \
         patch("enrichment.HUNTER_API_KEY", ""):
        from enrichment import enrich_contact

        result = await enrich_contact(None, "example.com")
        assert result.enrichment_source == "not_configured"


def test_enable_api_enrichment():
    from enrichment import enable_api_enrichment
    import enrichment

    enable_api_enrichment(True)
    assert enrichment._api_enabled is True

    enable_api_enrichment(False)
    assert enrichment._api_enabled is False
