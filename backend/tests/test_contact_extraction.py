"""
Tests for contact_extraction.py

Covers email/LinkedIn cleaning, prompt formatting, and LLM-based extraction.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from contact_extraction import (
    _clean_email,
    _clean_linkedin_url,
    ExtractedPerson,
    EXTRACTION_PROMPT,
    extract_contacts_from_content,
)


# ═══════════════════════════════════════════════
# _clean_email
# ═══════════════════════════════════════════════

class TestCleanEmail:
    def test_valid_email(self):
        assert _clean_email("john@acme.com") == "john@acme.com"

    def test_valid_with_dots(self):
        assert _clean_email("john.doe@acme.co.uk") == "john.doe@acme.co.uk"

    def test_valid_with_plus(self):
        assert _clean_email("john+test@acme.com") == "john+test@acme.com"

    def test_uppercase_normalised(self):
        assert _clean_email("John@Acme.COM") == "john@acme.com"

    def test_with_whitespace(self):
        assert _clean_email("  john@acme.com  ") == "john@acme.com"

    def test_none(self):
        assert _clean_email(None) is None

    def test_empty_string(self):
        assert _clean_email("") is None

    def test_invalid_no_at(self):
        assert _clean_email("john.acme.com") is None

    def test_invalid_no_domain(self):
        assert _clean_email("john@") is None

    def test_invalid_spaces(self):
        assert _clean_email("john @acme.com") is None


# ═══════════════════════════════════════════════
# _clean_linkedin_url
# ═══════════════════════════════════════════════

class TestCleanLinkedinUrl:
    def test_valid_url(self):
        url = "https://linkedin.com/in/johndoe"
        assert _clean_linkedin_url(url) == url

    def test_valid_www(self):
        url = "https://www.linkedin.com/in/janedoe"
        assert _clean_linkedin_url(url) == url

    def test_none(self):
        assert _clean_linkedin_url(None) is None

    def test_empty(self):
        assert _clean_linkedin_url("") is None

    def test_non_linkedin(self):
        assert _clean_linkedin_url("https://facebook.com/johndoe") is None

    def test_whitespace(self):
        url = "  https://linkedin.com/in/johndoe  "
        assert _clean_linkedin_url(url) == url.strip()


# ═══════════════════════════════════════════════
# ExtractedPerson dataclass
# ═══════════════════════════════════════════════

class TestExtractedPerson:
    def test_defaults(self):
        p = ExtractedPerson(full_name="Alice Bob")
        assert p.full_name == "Alice Bob"
        assert p.job_title is None
        assert p.email is None
        assert p.phone is None
        assert p.linkedin_url is None

    def test_full(self):
        p = ExtractedPerson(
            full_name="Alice Bob",
            job_title="CEO",
            email="alice@example.com",
            phone="+1-555-123",
            linkedin_url="https://linkedin.com/in/alice",
        )
        assert p.job_title == "CEO"
        assert p.email == "alice@example.com"


# ═══════════════════════════════════════════════
# EXTRACTION_PROMPT template
# ═══════════════════════════════════════════════

class TestExtractionPrompt:
    def test_has_placeholders(self):
        assert "{company_name}" in EXTRACTION_PROMPT
        assert "{domain}" in EXTRACTION_PROMPT
        assert "{content}" in EXTRACTION_PROMPT

    def test_format_succeeds(self):
        rendered = EXTRACTION_PROMPT.format(
            company_name="Acme Corp",
            domain="acme.com",
            content="About us page...",
        )
        assert "Acme Corp" in rendered
        assert "acme.com" in rendered


# ═══════════════════════════════════════════════
# extract_contacts_from_content
# ═══════════════════════════════════════════════

class TestExtractContacts:
    @pytest.mark.asyncio
    async def test_empty_content(self):
        result = await extract_contacts_from_content("Acme", "acme.com", "")
        assert result == []

    @pytest.mark.asyncio
    async def test_short_content(self):
        result = await extract_contacts_from_content("Acme", "acme.com", "hi")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_api_keys(self):
        with patch("contact_extraction.KIMI_API_KEY", ""), \
             patch("contact_extraction.OPENAI_API_KEY", ""):
            result = await extract_contacts_from_content(
                "Acme", "acme.com", "A" * 100,
            )
            assert result == []

    @pytest.mark.asyncio
    async def test_successful_extraction_via_kimi(self):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps([
                {
                    "full_name": "Jane Doe",
                    "job_title": "CEO",
                    "email": "jane@acme.com",
                    "phone": "+1-555-000",
                    "linkedin_url": "https://linkedin.com/in/janedoe",
                },
                {
                    "full_name": "Bob Smith",
                    "job_title": "Sales Manager",
                    "email": "bob@acme.com",
                    "phone": None,
                    "linkedin_url": None,
                },
            ])))
        ]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        with patch("contact_extraction.KIMI_API_KEY", "test-key"), \
             patch("contact_extraction.AsyncOpenAI", return_value=mock_client):
            result = await extract_contacts_from_content(
                "Acme", "acme.com", "A" * 100,
            )

        assert len(result) == 2
        assert result[0].full_name == "Jane Doe"
        assert result[0].email == "jane@acme.com"
        assert result[1].full_name == "Bob Smith"

    @pytest.mark.asyncio
    async def test_deduplication_by_name(self):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps([
                {"full_name": "Jane Doe", "job_title": "CEO"},
                {"full_name": "jane doe", "job_title": "CEO"},  # duplicate
            ])))
        ]
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        with patch("contact_extraction.KIMI_API_KEY", "test-key"), \
             patch("contact_extraction.AsyncOpenAI", return_value=mock_client):
            result = await extract_contacts_from_content("Acme", "acme.com", "A" * 100)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_code_fence_json(self):
        fenced = '```json\n[{"full_name": "Alice", "job_title": "VP"}]\n```'
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content=fenced))
        ]
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        with patch("contact_extraction.KIMI_API_KEY", "test-key"), \
             patch("contact_extraction.AsyncOpenAI", return_value=mock_client):
            result = await extract_contacts_from_content("X", "x.com", "A" * 100)

        assert len(result) == 1
        assert result[0].full_name == "Alice"

    @pytest.mark.asyncio
    async def test_kimi_fails_fallback_openai(self):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content='[{"full_name": "Fallback Person"}]'))
        ]

        mock_kimi = AsyncMock()
        mock_kimi.chat.completions.create = AsyncMock(side_effect=Exception("Kimi down"))

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(return_value=fake_response)

        call_count = 0
        original_cls = None

        def fake_async_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_kimi
            return mock_openai

        with patch("contact_extraction.KIMI_API_KEY", "kimi-key"), \
             patch("contact_extraction.OPENAI_API_KEY", "openai-key"), \
             patch("contact_extraction.AsyncOpenAI", side_effect=fake_async_openai):
            result = await extract_contacts_from_content("X", "x.com", "A" * 100)

        assert len(result) == 1
        assert result[0].full_name == "Fallback Person"

    @pytest.mark.asyncio
    async def test_max_contacts_limit(self):
        people = [{"full_name": f"Person {i}", "job_title": "Staff"} for i in range(30)]
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(people)))
        ]
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        with patch("contact_extraction.KIMI_API_KEY", "test-key"), \
             patch("contact_extraction.AsyncOpenAI", return_value=mock_client):
            result = await extract_contacts_from_content("X", "x.com", "A" * 100, max_contacts=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_unparseable_llm_response(self):
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content="I couldn't find any contacts."))
        ]
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        with patch("contact_extraction.KIMI_API_KEY", "test-key"), \
             patch("contact_extraction.AsyncOpenAI", return_value=mock_client):
            result = await extract_contacts_from_content("X", "x.com", "A" * 100)

        assert result == []
