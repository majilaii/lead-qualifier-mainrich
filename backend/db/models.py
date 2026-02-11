"""
Database Models — SQLAlchemy ORM models for Supabase PostgreSQL.

Supabase manages authentication in its ``auth.users`` table.  We create a
lightweight ``profiles`` table (keyed by the Supabase user UUID) for
app-specific data like plan tier, and reference it from the other tables.

Tables:
  - profiles:           App-specific user data (plan_tier etc.)
  - searches:           Saved search sessions with ICP context
  - qualified_leads:    Qualified companies with scores and reasoning
  - enrichment_results: Contact info found via Hunter/Apollo
  - usage_tracking:     Per-user monthly lead usage for billing limits
"""

from datetime import datetime, timezone
from typing import Optional

import uuid as _uuid

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Double,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    """App-specific user data.  ``id`` is the Supabase auth.users UUID."""
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)  # Supabase user UUID
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan_tier: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    searches: Mapped[list["Search"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    usage: Mapped[list["UsageTracking"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(_uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id"), index=True)
    # ICP context from the chat conversation
    industry: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    company_profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technology_focus: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qualifying_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disqualifiers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Search metadata
    queries_used: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # chat history [{role, content}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="searches")
    leads: Mapped[list["QualifiedLead"]] = relationship(back_populates="search", cascade="all, delete-orphan")


class QualifiedLead(Base):
    __tablename__ = "qualified_leads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(_uuid.uuid4()))
    search_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("searches.id"), index=True)
    # Company info
    company_name: Mapped[str] = mapped_column(String(500))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    website_url: Mapped[str] = mapped_column(String(1000))
    # Qualification
    score: Mapped[int] = mapped_column(Integer)
    tier: Mapped[str] = mapped_column(String(20))  # hot, review, rejected
    hardware_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    industry_category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    key_signals: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    red_flags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Deep research data (optional, for hot leads)
    deep_research: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Geo data for map view
    country: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    # Pipeline status
    status: Mapped[str] = mapped_column(String(20), default="new")  # new, contacted, in_progress, won, lost, archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    search: Mapped["Search"] = relationship(back_populates="leads")
    enrichment: Mapped[Optional["EnrichmentResult_"]] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_leads_search_domain", "search_id", "domain"),
    )


class EnrichmentResult_(Base):
    """Contact enrichment data for a qualified lead."""
    __tablename__ = "enrichment_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(_uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("qualified_leads.id"), unique=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    lead: Mapped["QualifiedLead"] = relationship(back_populates="enrichment")


class UsageTracking(Base):
    """Per-user monthly usage tracking for billing/limits."""
    __tablename__ = "usage_tracking"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(_uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id"), index=True)
    year_month: Mapped[str] = mapped_column(String(7))  # "2026-02"
    leads_qualified: Mapped[int] = mapped_column(Integer, default=0)
    searches_run: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    profile: Mapped["Profile"] = relationship(back_populates="usage")

    __table_args__ = (
        Index("ix_usage_user_month", "user_id", "year_month", unique=True),
    )
