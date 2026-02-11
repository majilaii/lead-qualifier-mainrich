"""
Tests for usage tracking module.

Verifies get_usage, check_limit, increment_usage against
an in-memory SQLite database.
"""

import pytest
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db import Base
from db.models import Profile, UsageTracking


@pytest.fixture
async def db_session():
    """Create a fresh in-memory DB for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        # Create a test profile (mirrors Supabase auth.users row)
        profile = Profile(
            id="test-user-1",
            email="test@example.com",
            display_name="Test User",
            plan_tier="free",
        )
        session.add(profile)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_usage_creates_row(db_session):
    from usage import get_usage

    data = await get_usage(db_session, "test-user-1", "free")
    assert data["leads_qualified"] == 0
    assert data["searches_run"] == 0
    assert data["leads_limit"] == 50
    assert data["searches_limit"] == 5


@pytest.mark.asyncio
async def test_increment_usage(db_session):
    from usage import get_usage, increment_usage

    await increment_usage(db_session, "test-user-1", leads_qualified=10, searches_run=1)
    data = await get_usage(db_session, "test-user-1", "free")
    assert data["leads_qualified"] == 10
    assert data["searches_run"] == 1


@pytest.mark.asyncio
async def test_check_limit_within(db_session):
    from usage import check_limit, increment_usage

    await increment_usage(db_session, "test-user-1", leads_qualified=40)
    ok = await check_limit(db_session, "test-user-1", "leads_qualified", count=10, plan_tier="free")
    assert ok is True


@pytest.mark.asyncio
async def test_check_limit_exceeded(db_session):
    from usage import check_limit, increment_usage

    await increment_usage(db_session, "test-user-1", leads_qualified=45)
    ok = await check_limit(db_session, "test-user-1", "leads_qualified", count=10, plan_tier="free")
    assert ok is False


@pytest.mark.asyncio
async def test_scale_plan_unlimited(db_session):
    from usage import check_limit

    ok = await check_limit(db_session, "test-user-1", "leads_qualified", count=999999, plan_tier="scale")
    assert ok is True
