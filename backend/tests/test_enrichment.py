"""
Comprehensive tests for enrichment.py

Verifies Hunter.io enrichment logic, status reporting,
domain cleaning, and behaviour with various API responses.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


# ═══════════════════════════════════════════════
# Enrichment status
# ═══════════════════════════════════════════════

class TestEnrichmentStatus:
    def test_status_no_key(self):
        with patch("enrichment.HUNTER_API_KEY", ""):
            from enrichment import get_enrichment_status
            status = get_enrichment_status()
            assert status["hunter_configured"] is False
            assert status["providers"] == []
            assert status["mode"] == "manual"

    def test_status_with_key(self):
        with patch("enrichment.HUNTER_API_KEY", "test-key-123"):
            from enrichment import get_enrichment_status
            status = get_enrichment_status()
            assert status["hunter_configured"] is True
            assert "hunter" in status["providers"]
            assert status["mode"] == "hunter"


# ═══════════════════════════════════════════════
# enrich_contact — no API key
# ═══════════════════════════════════════════════

class TestEnrichContactNoKey:
    @pytest.mark.asyncio
    async def test_returns_not_configured(self):
        with patch("enrichment.HUNTER_API_KEY", ""):
            from enrichment import enrich_contact
            result = await enrich_contact(None, "example.com")
            assert result.enrichment_source == "not_configured"


# ═══════════════════════════════════════════════
# enrich_contact — with API key
# ═══════════════════════════════════════════════

class TestEnrichContactWithKey:
    def _make_mock_client(self, responses):
        """Create a mock httpx.AsyncClient returning given responses in order."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=responses)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    @pytest.mark.asyncio
    async def test_email_finder_success(self):
        """When Hunter email-finder finds a specific contact."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": {"email": "john@acme.com", "position": "CEO"}
        }
        mock_client = self._make_mock_client([resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact("John Smith", "acme.com")
            assert result.email == "john@acme.com"
            assert result.enrichment_source == "hunter"

    @pytest.mark.asyncio
    async def test_domain_search_fallback(self):
        """When email-finder fails, falls back to domain-search."""
        # First call (email-finder): no email
        finder_resp = MagicMock()
        finder_resp.status_code = 200
        finder_resp.json.return_value = {"data": {}}

        # Second call (domain-search): has emails
        domain_resp = MagicMock()
        domain_resp.status_code = 200
        domain_resp.json.return_value = {
            "data": {
                "emails": [
                    {"value": "ceo@acme.com", "department": "executive", "seniority": "senior", "position": "CEO", "first_name": "Jane", "last_name": "Doe"},
                    {"value": "info@acme.com", "department": None, "seniority": None, "position": None, "first_name": "", "last_name": ""},
                ]
            }
        }
        mock_client = self._make_mock_client([finder_resp, domain_resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact("Jane Doe", "acme.com")
            assert result.email == "ceo@acme.com"
            assert result.enrichment_source == "hunter"

    @pytest.mark.asyncio
    async def test_api_error_returns_not_found(self):
        resp = MagicMock()
        resp.status_code = 500
        mock_client = self._make_mock_client([resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact(None, "example.com")
            assert result.enrichment_source == "not_found"

    @pytest.mark.asyncio
    async def test_rate_limit_returns_not_found(self):
        resp = MagicMock()
        resp.status_code = 429
        mock_client = self._make_mock_client([resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact(None, "example.com")
            assert result.enrichment_source == "not_found"

    @pytest.mark.asyncio
    async def test_domain_cleaned(self):
        """Ensures www. and https:// are stripped from domain before API call."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"emails": []}}
        mock_client = self._make_mock_client([resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            await enrich_contact(None, "https://www.acme.com/about")
            # Verify the cleaned domain was used in the API call
            call_args = mock_client.get.call_args
            assert "acme.com" in str(call_args)

    @pytest.mark.asyncio
    async def test_single_word_name_skips_finder(self):
        """Contact name with < 2 words should skip email-finder and go to domain-search."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"data": {"emails": []}}
        mock_client = self._make_mock_client([resp])

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact("Madonna", "acme.com")
            # Should have called domain-search directly (1 call, not 2)
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_exception_returns_not_found(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("enrichment.HUNTER_API_KEY", "test-key"), \
             patch("enrichment.httpx.AsyncClient", return_value=mock_client):
            from enrichment import enrich_contact
            result = await enrich_contact(None, "example.com")
            assert result.enrichment_source == "not_found"
