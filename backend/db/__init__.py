"""
Database Connection — SQLAlchemy async engine & session factory.

Connects to Supabase PostgreSQL (or local SQLite for offline dev).

Set DATABASE_URL in .env to your Supabase connection string (session pooler):
  DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

Usage:
    from db import get_db, init_db

    # In FastAPI lifespan:
    await init_db()

    # In a route:
    async def my_route(db: AsyncSession = Depends(get_db)):
        ...
"""

import os
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./lead_qualifier.db",
)

_connect_args: dict = {}
if "sqlite" in DATABASE_URL:
    _connect_args["check_same_thread"] = False
elif "asyncpg" in DATABASE_URL:
    # Disable prepared statement cache — required for Supabase pooled connections
    _connect_args["prepared_statement_cache_size"] = 0

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    # Connection pool tuning for PostgreSQL (ignored by SQLite)
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables. Safe to call multiple times (uses IF NOT EXISTS)."""
    from db.models import Base as _  # noqa: F401 — ensure models are loaded
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
