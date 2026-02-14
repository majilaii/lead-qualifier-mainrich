"""
Comprehensive tests for usage tracking module.

Verifies get_usage, check_limit, increment_usage, check_quota
against an in-memory SQLite database across all plan tiers.
"""

import pytest
import uuid
from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db import Base
from db.models import Profile, UsageTracking

# Use a valid UUID so the UUID column type can round-trip through SQLite
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_USER_PRO = "00000000-0000-4000-8000-000000000002"


def _patch_uuid_columns_for_sqlite():
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if hasattr(col.type, '__class__') and col.type.__class__.__name__ == 'UUID':
                col.type = String(36)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _patch_uuid_columns_for_sqlite()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        session.add(Profile(id=TEST_USER_ID, email="test@example.com", display_name="Test", plan_tier="free", plan="free"))
        session.add(Profile(id=TEST_USER_PRO, email="pro@example.com", display_name="Pro", plan_tier="pro", plan="pro"))
        await session.commit()
        yield session
    await engine.dispose()


# ═══════════════════════════════════════════════
# get_usage
# ═══════════════════════════════════════════════

class TestGetUsage:
    @pytest.mark.asyncio
    async def test_creates_row(self, db_session):
        from usage import get_usage
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["leads_qualified"] == 0
        assert data["searches_run"] == 0
        assert data["leads_limit"] == 75
        assert data["searches_limit"] == 3

    @pytest.mark.asyncio
    async def test_pro_plan_limits(self, db_session):
        from usage import get_usage
        data = await get_usage(db_session, TEST_USER_PRO, "pro")
        assert data["leads_limit"] == 2000
        assert data["searches_limit"] == 20
        assert data["enrichments_limit"] == 200
        assert data["deep_research"] is True

    @pytest.mark.asyncio
    async def test_free_plan_no_deep_research(self, db_session):
        from usage import get_usage
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["deep_research"] is False

    @pytest.mark.asyncio
    async def test_leads_per_hunt(self, db_session):
        from usage import get_usage
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["leads_per_hunt"] == 25


# ═══════════════════════════════════════════════
# increment_usage
# ═══════════════════════════════════════════════

class TestIncrementUsage:
    @pytest.mark.asyncio
    async def test_basic_increment(self, db_session):
        from usage import get_usage, increment_usage
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=10, searches_run=1)
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["leads_qualified"] == 10
        assert data["searches_run"] == 1

    @pytest.mark.asyncio
    async def test_multiple_increments(self, db_session):
        from usage import get_usage, increment_usage
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=10)
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=15)
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["leads_qualified"] == 25

    @pytest.mark.asyncio
    async def test_enrichments_increment(self, db_session):
        from usage import get_usage, increment_usage
        await increment_usage(db_session, TEST_USER_ID, enrichments_used=5)
        data = await get_usage(db_session, TEST_USER_ID, "free")
        assert data["enrichments_used"] == 5


# ═══════════════════════════════════════════════
# check_limit
# ═══════════════════════════════════════════════

class TestCheckLimit:
    @pytest.mark.asyncio
    async def test_within_limits(self, db_session):
        from usage import check_limit, increment_usage
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=40)
        ok = await check_limit(db_session, TEST_USER_ID, "leads_qualified", count=10, plan_tier="free")
        assert ok is True

    @pytest.mark.asyncio
    async def test_exceeded(self, db_session):
        from usage import check_limit, increment_usage
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=70)
        ok = await check_limit(db_session, TEST_USER_ID, "leads_qualified", count=10, plan_tier="free")
        assert ok is False

    @pytest.mark.asyncio
    async def test_exact_boundary(self, db_session):
        from usage import check_limit, increment_usage
        await increment_usage(db_session, TEST_USER_ID, leads_qualified=74)
        ok = await check_limit(db_session, TEST_USER_ID, "leads_qualified", count=1, plan_tier="free")
        assert ok is True  # 74 + 1 = 75 = limit

    @pytest.mark.asyncio
    async def test_enterprise_unlimited(self, db_session):
        from usage import check_limit, increment_usage
        await increment_usage(db_session, TEST_USER_PRO, leads_qualified=99999)
        ok = await check_limit(db_session, TEST_USER_PRO, "leads_qualified", count=1, plan_tier="enterprise")
        assert ok is True


# ═══════════════════════════════════════════════
# check_quota
# ═══════════════════════════════════════════════

class TestCheckQuota:
    @pytest.mark.asyncio
    async def test_within_quota(self, db_session):
        from usage import check_quota
        result = await check_quota(db_session, TEST_USER_ID, "free", "search", count=1)
        assert result is None  # OK

    @pytest.mark.asyncio
    async def test_exceeded_quota(self, db_session):
        from usage import check_quota, increment_usage
        await increment_usage(db_session, TEST_USER_ID, searches_run=3)
        result = await check_quota(db_session, TEST_USER_ID, "free", "search", count=1)
        assert result is not None
        assert result["error"] == "quota_exceeded"
        assert result["metric"] == "searches_run"
        assert result["plan"] == "free"

    @pytest.mark.asyncio
    async def test_unknown_action_allowed(self, db_session):
        from usage import check_quota
        result = await check_quota(db_session, TEST_USER_ID, "free", "unknown_action")
        assert result is None


# ═══════════════════════════════════════════════
# Plan limits constants
# ═══════════════════════════════════════════════

class TestPlanLimits:
    def test_all_plans_defined(self):
        from usage import PLAN_LIMITS
        assert "free" in PLAN_LIMITS
        assert "pro" in PLAN_LIMITS
        assert "enterprise" in PLAN_LIMITS

    def test_enterprise_has_unlimited(self):
        from usage import PLAN_LIMITS
        limits = PLAN_LIMITS["enterprise"]
        assert limits["searches_run"] is None
        assert limits["leads_qualified"] is None

    def test_free_most_restrictive(self):
        from usage import PLAN_LIMITS
        free = PLAN_LIMITS["free"]
        pro = PLAN_LIMITS["pro"]
        assert free["searches_run"] < pro["searches_run"]
        assert free["leads_qualified"] < pro["leads_qualified"]

    def test_leads_per_hunt_tiers(self):
        from usage import LEADS_PER_HUNT
        assert LEADS_PER_HUNT["free"] < LEADS_PER_HUNT["pro"]
        assert LEADS_PER_HUNT["pro"] < LEADS_PER_HUNT["enterprise"]


# ═══════════════════════════════════════════════
# Auto-create profile
# ═══════════════════════════════════════════════

class TestAutoCreateProfile:
    @pytest.mark.asyncio
    async def test_creates_profile_if_missing(self, db_session):
        """When get_usage is called for a user with no profile, it should auto-create."""
        from usage import get_usage
        new_user = "00000000-0000-4000-8000-000000000099"
        data = await get_usage(db_session, new_user, "free")
        assert data["leads_qualified"] == 0


@pytest.mark.asyncio
async def test_enterprise_plan_unlimited(db_session):
    from usage import check_limit

    ok = await check_limit(db_session, TEST_USER_ID, "leads_qualified", count=999999, plan_tier="enterprise")
    assert ok is True
