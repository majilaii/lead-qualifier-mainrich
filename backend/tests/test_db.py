"""
Tests for db/__init__.py and db/models.py

Covers database initialization, Base class, model table existence,
relationship integrity, and field defaults.
"""

import pytest
import pytest_asyncio
from sqlalchemy import inspect, String
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db import Base


def _patch_uuid_columns():
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if hasattr(col.type, "__class__") and col.type.__class__.__name__ == "UUID":
                col.type = String(36)


# ═══════════════════════════════════════════════
# Database init & table creation
# ═══════════════════════════════════════════════

class TestDatabaseInit:
    @pytest_asyncio.fixture
    async def engine(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        _patch_uuid_columns()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield eng
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_tables_created(self, engine):
        async with engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        expected = {
            "profiles", "searches", "qualified_leads",
            "enrichment_results", "usage_tracking",
            "lead_contacts", "search_templates",
            "enrichment_jobs", "lead_snapshots",
        }
        assert expected.issubset(set(table_names))

    @pytest.mark.asyncio
    async def test_create_all_idempotent(self, engine):
        # Calling create_all again should not raise
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


# ═══════════════════════════════════════════════
# Model field tests
# ═══════════════════════════════════════════════

class TestProfileModel:
    @pytest_asyncio.fixture
    async def session(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        _patch_uuid_columns()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with Session() as s:
            yield s
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_create_profile(self, session):
        from db.models import Profile
        p = Profile(id="test-uuid", email="test@test.com", plan="free", plan_tier="free")
        session.add(p)
        await session.commit()

        from sqlalchemy import select
        row = (await session.execute(select(Profile).where(Profile.id == "test-uuid"))).scalar_one()
        assert row.email == "test@test.com"
        assert row.plan == "free"

    @pytest.mark.asyncio
    async def test_profile_defaults(self, session):
        from db.models import Profile
        p = Profile(id="test-2")
        session.add(p)
        await session.commit()
        assert p.plan_tier == "free"
        assert p.plan == "free"
        assert p.created_at is not None


class TestSearchModel:
    @pytest_asyncio.fixture
    async def session(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        _patch_uuid_columns()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with Session() as s:
            yield s
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_create_search_with_profile(self, session):
        from db.models import Profile, Search
        import uuid

        profile = Profile(id="u1", email="u1@test.com", plan="free")
        session.add(profile)
        await session.commit()

        search = Search(id=str(uuid.uuid4()), user_id="u1", industry="Tech")
        session.add(search)
        await session.commit()
        assert search.total_found == 0
        assert search.created_at is not None


class TestUsageTrackingModel:
    @pytest_asyncio.fixture
    async def session(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        _patch_uuid_columns()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with Session() as s:
            yield s
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_usage_defaults(self, session):
        from db.models import Profile, UsageTracking
        import uuid

        profile = Profile(id="u1", email="u1@test.com")
        session.add(profile)
        await session.commit()

        usage = UsageTracking(
            id=str(uuid.uuid4()), user_id="u1", year_month="2026-02",
        )
        session.add(usage)
        await session.commit()
        assert usage.leads_qualified == 0
        assert usage.searches_run == 0
        assert usage.enrichments_used == 0
        assert usage.linkedin_lookups == 0


class TestLeadContactModel:
    @pytest_asyncio.fixture
    async def session(self):
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        _patch_uuid_columns()
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with Session() as s:
            yield s
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_default_source(self, session):
        from db.models import Profile, Search, QualifiedLead, LeadContact
        import uuid

        profile = Profile(id="u1", email="u1@test.com")
        session.add(profile)
        await session.commit()

        search = Search(id=str(uuid.uuid4()), user_id="u1")
        session.add(search)
        await session.commit()

        lead = QualifiedLead(
            id=str(uuid.uuid4()), search_id=search.id,
            company_name="Acme", domain="acme.com",
            website_url="https://acme.com", score=85, tier="hot",
        )
        session.add(lead)
        await session.commit()

        contact = LeadContact(
            id=str(uuid.uuid4()), lead_id=lead.id,
            full_name="John Doe", email="john@acme.com",
        )
        session.add(contact)
        await session.commit()
        assert contact.source == "website"
