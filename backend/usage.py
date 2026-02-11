"""
Usage Tracking — Per-user monthly limits and metering.

Plan tiers:
  - free:  50 leads/month, 5 searches/month
  - pro:   500 leads/month, 50 searches/month
  - scale: unlimited

Usage:
    from usage import get_usage, increment_usage, check_limit

    usage = await get_usage(db, user_id)
    ok    = await check_limit(db, user_id, "leads_qualified", count=10)
    await increment_usage(db, user_id, leads_qualified=10)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UsageTracking

# ──────────────────────────────────────────────
# Plan limits
# ──────────────────────────────────────────────

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free":  {"leads_qualified": 50,   "searches_run": 5},
    "pro":   {"leads_qualified": 500,  "searches_run": 50},
    "scale": {"leads_qualified": None, "searches_run": None},  # unlimited
}


def _current_month() -> str:
    """Return 'YYYY-MM' for the current UTC month."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _get_or_create_row(
    db: AsyncSession, user_id: str
) -> UsageTracking:
    """Get the usage row for this user+month, creating if absent."""
    ym = _current_month()
    stmt = select(UsageTracking).where(
        UsageTracking.user_id == user_id,
        UsageTracking.year_month == ym,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is None:
        row = UsageTracking(
            id=str(uuid.uuid4()),
            user_id=user_id,
            year_month=ym,
            leads_qualified=0,
            searches_run=0,
        )
        db.add(row)
        await db.flush()

    return row


async def get_usage(db: AsyncSession, user_id: str, plan_tier: str = "free") -> dict:
    """
    Return current month's usage and limits for a user.

    Returns:
        {
            "year_month": "2026-02",
            "leads_qualified": 12,
            "leads_limit": 50,
            "searches_run": 2,
            "searches_limit": 5,
        }
    """
    row = await _get_or_create_row(db, user_id)
    limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])

    return {
        "year_month": row.year_month,
        "leads_qualified": row.leads_qualified,
        "leads_limit": limits["leads_qualified"],
        "searches_run": row.searches_run,
        "searches_limit": limits["searches_run"],
    }


async def check_limit(
    db: AsyncSession,
    user_id: str,
    metric: str,
    count: int = 1,
    plan_tier: str = "free",
) -> bool:
    """
    Check whether adding `count` more to `metric` would exceed the plan limit.
    Returns True if within limits, False if would exceed.
    """
    row = await _get_or_create_row(db, user_id)
    limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])
    limit_val = limits.get(metric)

    if limit_val is None:
        return True  # unlimited

    current = getattr(row, metric, 0)
    return (current + count) <= limit_val


async def increment_usage(
    db: AsyncSession,
    user_id: str,
    leads_qualified: int = 0,
    searches_run: int = 0,
) -> None:
    """Increment usage counters for the current month."""
    row = await _get_or_create_row(db, user_id)

    if leads_qualified:
        row.leads_qualified += leads_qualified
    if searches_run:
        row.searches_run += searches_run

    await db.commit()
