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
import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./lead_qualifier.db",
)

_connect_args: dict = {}
if "sqlite" in DATABASE_URL:
    _connect_args["check_same_thread"] = False
elif "asyncpg" in DATABASE_URL:
    # Disable prepared statement cache — required for Supabase pooled connections
    # asyncpg uses "statement_cache_size" (newer) or "prepared_statement_cache_size" (older)
    _connect_args["prepared_statement_cache_size"] = 0
    _connect_args["statement_cache_size"] = 0

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    # Connection pool tuning for PostgreSQL (ignored by SQLite)
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,  # Recycle connections every 5 min to avoid stale pooler connections
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables. Safe to call multiple times (uses IF NOT EXISTS)."""
    from db.models import Base as _  # noqa: F401 — ensure models are loaded
    
    # Log which database we're connecting to (mask password)
    _safe_url = DATABASE_URL
    if "@" in _safe_url:
        # Mask password: postgresql+asyncpg://user:PASSWORD@host → postgresql+asyncpg://user:***@host
        prefix, rest = _safe_url.split("@", 1)
        if ":" in prefix:
            scheme_user = prefix.rsplit(":", 1)[0]
            _safe_url = f"{scheme_user}:***@{rest}"
    logger.info("Connecting to database: %s", _safe_url)
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created successfully")
    except Exception as e:
        logger.error("Database initialization FAILED: %s (type: %s)", e, type(e).__name__, exc_info=True)
        raise


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
