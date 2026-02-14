"""
Tests for pipeline_engine.py

Covers run_discovery, _make_spread_fn (geo-spread), and process_companies
with mocked scraper/intelligence/contact extraction.
"""

import math
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from pipeline_engine import _make_spread_fn, run_discovery


# ═══════════════════════════════════════════════
# _make_spread_fn (geo-spread helper)
# ═══════════════════════════════════════════════

class TestMakeSpreadFn:
    def test_first_hit_no_offset(self):
        spread = _make_spread_fn()
        lat, lng = spread(34.0, -118.0)
        assert lat == 34.0
        assert lng == -118.0

    def test_second_hit_offset(self):
        spread = _make_spread_fn()
        spread(34.0, -118.0)  # first (no offset)
        lat, lng = spread(34.0, -118.0)  # same coords → offset
        assert lat != 34.0 or lng != -118.0
        # Should be close to original
        assert abs(lat - 34.0) < 0.01
        assert abs(lng - (-118.0)) < 0.01

    def test_none_passthrough(self):
        spread = _make_spread_fn()
        lat, lng = spread(None, None)
        assert lat is None
        assert lng is None

    def test_partial_none(self):
        spread = _make_spread_fn()
        lat, lng = spread(34.0, None)
        assert lat == 34.0
        assert lng is None

    def test_different_coords_no_conflict(self):
        spread = _make_spread_fn()
        lat1, lng1 = spread(34.0, -118.0)
        lat2, lng2 = spread(40.0, -74.0)
        assert lat1 == 34.0  # first hit
        assert lat2 == 40.0  # different coord, also first hit

    def test_multiple_same_coords_diverge(self):
        spread = _make_spread_fn()
        coords = []
        for _ in range(5):
            coords.append(spread(34.0, -118.0))
        # All 5 should be distinct tuples
        unique = set(coords)
        assert len(unique) == 5


# ═══════════════════════════════════════════════
# run_discovery
# ═══════════════════════════════════════════════

class TestRunDiscovery:
    @pytest.mark.asyncio
    async def test_emits_stage_events(self):
        mock_run = MagicMock()
        mock_run.emit = AsyncMock()

        mock_result = MagicMock()
        mock_result.companies = [
            {"url": "https://acme.com", "domain": "acme.com", "title": "Acme"},
        ]
        mock_result.queries_used = 3
        mock_result.unique_domains = 1

        mock_engine = AsyncMock()
        mock_engine.generate_and_search = AsyncMock(return_value=mock_result)

        ctx = {"industry": "Manufacturing"}
        companies = await run_discovery(mock_engine, ctx, run=mock_run)

        assert len(companies) == 1
        assert companies[0]["domain"] == "acme.com"

        # Check stage events
        calls = mock_run.emit.call_args_list
        assert calls[0][0][0]["type"] == "stage"
        assert calls[0][0][0]["status"] == "running"
        assert calls[1][0][0]["type"] == "stage"
        assert calls[1][0][0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_no_run_no_crash(self):
        """run=None should work without emitting events."""
        mock_result = MagicMock()
        mock_result.companies = []
        mock_result.queries_used = 0
        mock_result.unique_domains = 0

        mock_engine = AsyncMock()
        mock_engine.generate_and_search = AsyncMock(return_value=mock_result)

        companies = await run_discovery(mock_engine, {"industry": "Tech"}, run=None)
        assert companies == []

    @pytest.mark.asyncio
    async def test_context_fields_passed(self):
        """Verify search_context fields are mapped to ExtractedContext."""
        mock_result = MagicMock()
        mock_result.companies = []
        mock_result.queries_used = 0
        mock_result.unique_domains = 0

        mock_engine = AsyncMock()
        mock_engine.generate_and_search = AsyncMock(return_value=mock_result)

        ctx = {
            "industry": "Dental",
            "company_profile": "Mid-size labs",
            "technology_focus": "CAD/CAM",
            "geographic_region": "Europe",
            "country_code": "DE",
        }

        await run_discovery(mock_engine, ctx, run=None)

        call_args = mock_engine.generate_and_search.call_args
        context_arg = call_args[0][0]  # first positional arg
        assert context_arg.industry == "Dental"
        assert context_arg.geographic_region == "Europe"
        assert context_arg.country_code == "DE"


# ═══════════════════════════════════════════════
# process_companies (integration-style with heavy mocking)
# ═══════════════════════════════════════════════

class TestProcessCompanies:
    def _make_companies(self, n=1):
        return [
            {
                "url": f"https://company{i}.com",
                "domain": f"company{i}.com",
                "title": f"Company {i}",
                "exa_text": f"Company {i} manufactures precision motors." * 5,
                "highlights": "motor manufacturer",
                "score": 0.95,
            }
            for i in range(n)
        ]

    @pytest.mark.asyncio
    async def test_basic_pipeline_run(self):
        from pipeline_engine import process_companies
        from models import QualificationResult

        mock_run = MagicMock()
        mock_run.emit = AsyncMock()

        mock_qual = QualificationResult(
            is_qualified=True,
            confidence_score=60,
            reasoning="Review-tier lead",
            key_signals=["some signal"],
            red_flags=[],
        )

        with patch("intelligence.LeadQualifier") as MockQualifier, \
             patch("scraper.CrawlerPool"), \
             patch("scraper.crawl_company"):
            instance = MockQualifier.return_value
            instance.qualify_lead = AsyncMock(return_value=mock_qual)

            stats = await process_companies(
                companies=self._make_companies(2),
                search_ctx={"industry": "Manufacturing"},
                use_vision=False,
                run=mock_run,
                search_id="search-1",
                user_id="user-1",
            )

        assert stats["review"] == 2
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_hot_lead_triggers_phase2(self):
        from pipeline_engine import process_companies
        from models import QualificationResult

        mock_run = MagicMock()
        mock_run.emit = AsyncMock()

        hot_qual = QualificationResult(
            is_qualified=True,
            confidence_score=90,
            reasoning="Hot lead",
            key_signals=["motor manufacturer"],
            red_flags=[],
        )

        mock_crawl = MagicMock()
        mock_crawl.success = True
        mock_crawl.markdown_content = "Deep crawl content here"
        mock_crawl.screenshot_base64 = None

        with patch("intelligence.LeadQualifier") as MockQualifier, \
             patch("scraper.CrawlerPool") as MockPool, \
             patch("scraper.crawl_company", new_callable=AsyncMock, return_value=mock_crawl), \
             patch("contact_extraction.extract_contacts_from_content", new_callable=AsyncMock, return_value=[]):
            instance = MockQualifier.return_value
            instance.qualify_lead = AsyncMock(return_value=hot_qual)

            # CrawlerPool as context manager
            pool_instance = AsyncMock()
            pool_instance.crawl_contact_pages = AsyncMock(return_value="")
            MockPool.return_value.__aenter__ = AsyncMock(return_value=pool_instance)
            MockPool.return_value.__aexit__ = AsyncMock()

            stats = await process_companies(
                companies=self._make_companies(1),
                search_ctx={},
                use_vision=False,
                run=mock_run,
                search_id=None,
                user_id="user-1",
            )

        assert stats["hot"] == 1

    @pytest.mark.asyncio
    async def test_error_handling(self):
        from pipeline_engine import process_companies

        mock_run = MagicMock()
        mock_run.emit = AsyncMock()

        with patch("intelligence.LeadQualifier") as MockQualifier, \
             patch("scraper.CrawlerPool"), \
             patch("scraper.crawl_company"):
            instance = MockQualifier.return_value
            instance.qualify_lead = AsyncMock(side_effect=Exception("Boom"))

            stats = await process_companies(
                companies=self._make_companies(1),
                search_ctx={},
                use_vision=False,
                run=mock_run,
                search_id=None,
                user_id="user-1",
            )

        assert stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_complete_event_emitted(self):
        from pipeline_engine import process_companies
        from models import QualificationResult

        mock_run = MagicMock()
        mock_run.emit = AsyncMock()

        mock_qual = QualificationResult(
            is_qualified=False,
            confidence_score=20,
            reasoning="Not relevant",
        )

        with patch("intelligence.LeadQualifier") as MockQualifier, \
             patch("scraper.CrawlerPool"), \
             patch("scraper.crawl_company"):
            instance = MockQualifier.return_value
            instance.qualify_lead = AsyncMock(return_value=mock_qual)

            await process_companies(
                companies=self._make_companies(1),
                search_ctx={},
                use_vision=False,
                run=mock_run,
                search_id="s-1",
                user_id="u-1",
            )

        # Last emit should be "complete"
        last_call = mock_run.emit.call_args_list[-1]
        assert last_call[0][0]["type"] == "complete"
        assert "summary" in last_call[0][0]
