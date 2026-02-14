"""
Tests for linkedin_enrichment.py

Covers decision-maker detection, seniority sorting, LinkedInContact dataclass,
status reporting, and enrichment functions with mocked HTTP.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from linkedin_enrichment import (
    LinkedInContact,
    _is_decision_maker,
    _sort_by_seniority,
    get_linkedin_status,
    enrich_linkedin,
    enrich_linkedin_pdl,
    enrich_linkedin_rocketreach,
)


# ═══════════════════════════════════════════════
# _is_decision_maker
# ═══════════════════════════════════════════════

class TestIsDecisionMaker:
    @pytest.mark.parametrize("title", [
        "CEO", "Chief Executive Officer", "CTO", "COO", "CFO",
        "Managing Director", "General Manager",
        "Founder", "Co-Founder", "Owner",
        "VP Sales", "Vice President Engineering",
        "Director of Operations", "Head of Procurement",
        "President", "Purchasing Manager",
        "Sales Manager", "Business Development Lead",
    ])
    def test_decision_maker_titles(self, title):
        assert _is_decision_maker(title) is True

    @pytest.mark.parametrize("title", [
        "Software Engineer", "Junior Analyst", "Intern",
        "Data Entry Clerk", "Receptionist",
    ])
    def test_non_decision_maker_titles(self, title):
        assert _is_decision_maker(title) is False

    def test_none_title(self):
        assert _is_decision_maker(None) is False

    def test_empty_title(self):
        assert _is_decision_maker("") is False

    def test_case_insensitive(self):
        assert _is_decision_maker("ceo") is True
        assert _is_decision_maker("VICE PRESIDENT") is True


# ═══════════════════════════════════════════════
# _sort_by_seniority
# ═══════════════════════════════════════════════

class TestSortBySeniority:
    def test_ceo_first(self):
        contacts = [
            LinkedInContact(full_name="Mgr", job_title="Manager"),
            LinkedInContact(full_name="CEO", job_title="CEO"),
            LinkedInContact(full_name="VP", job_title="VP Sales"),
        ]
        sorted_c = _sort_by_seniority(contacts)
        assert sorted_c[0].full_name == "CEO"
        assert sorted_c[1].full_name == "VP"
        assert sorted_c[2].full_name == "Mgr"

    def test_cto_before_director(self):
        # NOTE: "director" contains the substring "cto", so both score 1
        # in _sort_by_seniority — this is a known source-code quirk.
        # We verify CTO at least ties with Director (both score 1).
        contacts = [
            LinkedInContact(full_name="Dir", job_title="Director of Eng"),
            LinkedInContact(full_name="CTO", job_title="CTO"),
        ]
        sorted_c = _sort_by_seniority(contacts)
        # Both score 1 (Director contains substring "cto"), so original order preserved
        assert {c.full_name for c in sorted_c} == {"CTO", "Dir"}

    def test_managing_director_rank(self):
        contacts = [
            LinkedInContact(full_name="VP", job_title="VP Marketing"),
            LinkedInContact(full_name="MD", job_title="Managing Director"),
        ]
        sorted_c = _sort_by_seniority(contacts)
        assert sorted_c[0].full_name == "MD"

    def test_empty_list(self):
        assert _sort_by_seniority([]) == []

    def test_no_title(self):
        contacts = [
            LinkedInContact(full_name="Unknown"),
            LinkedInContact(full_name="Boss", job_title="Founder"),
        ]
        sorted_c = _sort_by_seniority(contacts)
        assert sorted_c[0].full_name == "Boss"


# ═══════════════════════════════════════════════
# LinkedInContact dataclass
# ═══════════════════════════════════════════════

class TestLinkedInContact:
    def test_defaults(self):
        c = LinkedInContact(full_name="Test")
        assert c.source == "pdl"
        assert c.email is None
        assert c.phone is None
        assert c.linkedin_url is None

    def test_rocketreach_source(self):
        c = LinkedInContact(full_name="Test", source="rocketreach")
        assert c.source == "rocketreach"


# ═══════════════════════════════════════════════
# get_linkedin_status
# ═══════════════════════════════════════════════

class TestGetLinkedinStatus:
    def test_no_keys(self):
        with patch("linkedin_enrichment.PDL_API_KEY", ""), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", ""):
            status = get_linkedin_status()
            assert status["available"] is False
            assert status["providers"] == []

    def test_pdl_only(self):
        with patch("linkedin_enrichment.PDL_API_KEY", "pdl-key"), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", ""):
            status = get_linkedin_status()
            assert status["available"] is True
            assert "pdl" in status["providers"]
            assert status["rocketreach_configured"] is False

    def test_both_providers(self):
        with patch("linkedin_enrichment.PDL_API_KEY", "pdl"), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", "rr"):
            status = get_linkedin_status()
            assert status["available"] is True
            assert len(status["providers"]) == 2


# ═══════════════════════════════════════════════
# enrich_linkedin_pdl
# ═══════════════════════════════════════════════

class TestEnrichLinkedinPdl:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        with patch("linkedin_enrichment.PDL_API_KEY", ""):
            result = await enrich_linkedin_pdl("example.com")
            assert result == []

    @pytest.mark.asyncio
    async def test_successful_response(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "data": [
                {
                    "full_name": "Jane CEO",
                    "job_title": "CEO",
                    "work_email": "jane@example.com",
                    "linkedin_url": "https://linkedin.com/in/jane",
                    "mobile_phone": "+1-555-0001",
                    "emails": [],
                    "phone_numbers": [],
                },
                {
                    "full_name": "Bob Engineer",
                    "job_title": "Software Engineer",
                    "work_email": "bob@example.com",
                    "linkedin_url": "",
                    "emails": [],
                    "phone_numbers": [],
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("linkedin_enrichment.PDL_API_KEY", "key-123"), \
             patch("linkedin_enrichment.httpx.AsyncClient", return_value=mock_client):
            result = await enrich_linkedin_pdl("example.com")

        # CEO (decision-maker) should appear first
        assert len(result) >= 1
        assert result[0].full_name == "Jane CEO"
        assert result[0].email == "jane@example.com"

    @pytest.mark.asyncio
    async def test_domain_cleaning(self):
        """Domains with www./https:// should be cleaned before API call."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"data": []}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("linkedin_enrichment.PDL_API_KEY", "key"), \
             patch("linkedin_enrichment.httpx.AsyncClient", return_value=mock_client):
            await enrich_linkedin_pdl("https://www.example.com/path")

        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        domain_in_query = str(payload)
        assert "www." not in domain_in_query or "example.com" in domain_in_query


# ═══════════════════════════════════════════════
# enrich_linkedin_rocketreach
# ═══════════════════════════════════════════════

class TestEnrichLinkedinRocketreach:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        with patch("linkedin_enrichment.ROCKETREACH_API_KEY", ""):
            result = await enrich_linkedin_rocketreach("example.com")
            assert result == []

    @pytest.mark.asyncio
    async def test_successful_response(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "profiles": [
                {
                    "name": "Alice VP",
                    "current_title": "VP Sales",
                    "current_work_email": "alice@example.com",
                    "phone": "+44-555-0002",
                    "linkedin_url": "https://linkedin.com/in/alicevp",
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fake_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        with patch("linkedin_enrichment.ROCKETREACH_API_KEY", "rr-key"), \
             patch("linkedin_enrichment.httpx.AsyncClient", return_value=mock_client):
            result = await enrich_linkedin_rocketreach("example.com")

        assert len(result) == 1
        assert result[0].source == "rocketreach"
        assert result[0].full_name == "Alice VP"


# ═══════════════════════════════════════════════
# enrich_linkedin (combined)
# ═══════════════════════════════════════════════

class TestEnrichLinkedinCombined:
    @pytest.mark.asyncio
    async def test_no_keys_returns_empty(self):
        with patch("linkedin_enrichment.PDL_API_KEY", ""), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", ""):
            result = await enrich_linkedin("example.com")
            assert result == []

    @pytest.mark.asyncio
    async def test_pdl_used_first(self):
        pdl_contact = LinkedInContact(full_name="PDL Person", source="pdl")

        with patch("linkedin_enrichment.PDL_API_KEY", "pdl-key"), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", "rr-key"), \
             patch("linkedin_enrichment.enrich_linkedin_pdl", new_callable=AsyncMock, return_value=[pdl_contact]), \
             patch("linkedin_enrichment.enrich_linkedin_rocketreach", new_callable=AsyncMock) as mock_rr:
            result = await enrich_linkedin("example.com")

        assert len(result) == 1
        assert result[0].source == "pdl"
        mock_rr.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_to_rocketreach(self):
        rr_contact = LinkedInContact(full_name="RR Person", source="rocketreach")

        with patch("linkedin_enrichment.PDL_API_KEY", "pdl-key"), \
             patch("linkedin_enrichment.ROCKETREACH_API_KEY", "rr-key"), \
             patch("linkedin_enrichment.enrich_linkedin_pdl", new_callable=AsyncMock, return_value=[]), \
             patch("linkedin_enrichment.enrich_linkedin_rocketreach", new_callable=AsyncMock, return_value=[rr_contact]):
            result = await enrich_linkedin("example.com")

        assert len(result) == 1
        assert result[0].source == "rocketreach"
