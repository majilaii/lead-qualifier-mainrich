"""
Shared test fixtures for the entire test suite.

Provides:
  - In-memory SQLite database with all tables
  - Test user profiles (free, pro, enterprise)
  - Mock LLM / HTTP clients
  - Sample data factories for leads, crawl results, etc.
"""

import os
import uuid
import pytest
import pytest_asyncio

from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db import Base
from db.models import Profile, UsageTracking, Search, QualifiedLead

# ── Deterministic test IDs ──────────────────────
TEST_USER_FREE = "00000000-0000-4000-8000-000000000001"
TEST_USER_PRO = "00000000-0000-4000-8000-000000000002"
TEST_USER_ENT = "00000000-0000-4000-8000-000000000003"


def _patch_uuid_columns_for_sqlite():
    """Replace PostgreSQL UUID columns with String(36) for SQLite compat."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if hasattr(col.type, "__class__") and col.type.__class__.__name__ == "UUID":
                col.type = String(36)


@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh in-memory SQLite engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _patch_uuid_columns_for_sqlite()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide a transactional DB session with test profiles pre-seeded."""
    Session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        # Seed profiles for free / pro / enterprise tiers
        for uid, plan in [
            (TEST_USER_FREE, "free"),
            (TEST_USER_PRO, "pro"),
            (TEST_USER_ENT, "enterprise"),
        ]:
            session.add(Profile(
                id=uid,
                email=f"{plan}@test.com",
                display_name=f"Test {plan.title()}",
                plan_tier=plan,
                plan=plan,
            ))
        await session.commit()
        yield session


# ── Sample data factories ──────────────────────

def make_crawl_result(**overrides):
    """Create a CrawlResult with sensible defaults."""
    from models import CrawlResult

    defaults = {
        "url": "https://www.example.com",
        "success": True,
        "markdown_content": "# Example Corp\nWe manufacture precision motors and actuators for robotics.",
        "screenshot_base64": None,
        "title": "Example Corp",
        "crawl_time_seconds": 1.5,
        "exa_text": None,
        "exa_highlights": None,
        "exa_score": None,
    }
    defaults.update(overrides)
    return CrawlResult(**defaults)


def make_lead_input(**overrides):
    """Create a LeadInput with sensible defaults."""
    from models import LeadInput

    defaults = {
        "company_name": "Test Company",
        "website_url": "https://www.testcompany.com",
        "contact_name": "John Doe",
        "linkedin_profile_url": "https://linkedin.com/in/johndoe",
        "row_index": 0,
    }
    defaults.update(overrides)
    return LeadInput(**defaults)


def make_processed_lead(**overrides):
    """Create a ProcessedLead with sensible defaults."""
    from models import ProcessedLead, QualificationTier

    defaults = {
        "company_name": "Test Company",
        "website_url": "https://www.testcompany.com",
        "qualification_tier": QualificationTier.REVIEW,
        "confidence_score": 55,
        "is_qualified": False,
        "reasoning": "Test reasoning",
    }
    defaults.update(overrides)
    return ProcessedLead(**defaults)


def make_qualification_result(**overrides):
    """Create a QualificationResult with sensible defaults."""
    from models import QualificationResult

    defaults = {
        "is_qualified": True,
        "confidence_score": 85,
        "reasoning": "Strong B2B manufacturing signals found.",
        "key_signals": ["motor manufacturer", "ISO certified"],
        "red_flags": [],
    }
    defaults.update(overrides)
    return QualificationResult(**defaults)
