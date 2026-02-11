"""
Usage Tracking — Per-user monthly limits and metering.

Plan tiers (SaaS):
  - free:       3 hunts/mo, 25 leads/hunt, 10 enrichments/mo
  - pro:        20 hunts/mo, 100 leads/hunt, 200 enrichments/mo
  - enterprise: unlimited hunts, 500 leads/hunt, 1000 enrichments/mo

Usage:
    from usage import get_usage, increment_usage, check_limit, check_quota

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
# Plan limits (aligned with SAAS_PLAN.md)
# ──────────────────────────────────────────────

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "free":       {"searches_run": 3,    "leads_qualified": 75,    "enrichments_used": 10},
    "pro":        {"searches_run": 20,   "leads_qualified": 2000,  "enrichments_used": 200},
    "enterprise": {"searches_run": None, "leads_qualified": None,  "enrichments_used": 1000},
}

# Leads per hunt cap (not stored in usage, enforced at pipeline time)
LEADS_PER_HUNT = {
    "free": 25,
    "pro": 100,
    "enterprise": 500,
}

# Deep research access
DEEP_RESEARCH_PLANS = {"pro", "enterprise"}


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
            enrichments_used=0,
        )
        db.add(row)
        await db.flush()

    return row


async def get_usage(db: AsyncSession, user_id: str, plan_tier: str = "free") -> dict:
    """
    Return current month's usage and limits for a user.

    Returns:
        {
            "plan": "free",
            "year_month": "2026-02",
            "leads_qualified": 12,
            "leads_limit": 75,
            "searches_run": 2,
            "searches_limit": 3,
            "enrichments_used": 5,
            "enrichments_limit": 10,
            "leads_per_hunt": 25,
            "deep_research": false,
        }
    """
    row = await _get_or_create_row(db, user_id)
    limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])

    return {
        "plan": plan_tier,
        "year_month": row.year_month,
        "leads_qualified": row.leads_qualified,
        "leads_limit": limits["leads_qualified"],
        "searches_run": row.searches_run,
        "searches_limit": limits["searches_run"],
        "enrichments_used": row.enrichments_used,
        "enrichments_limit": limits["enrichments_used"],
        "leads_per_hunt": LEADS_PER_HUNT.get(plan_tier, 25),
        "deep_research": plan_tier in DEEP_RESEARCH_PLANS,
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
    enrichments_used: int = 0,
) -> None:
    """Increment usage counters for the current month."""
    row = await _get_or_create_row(db, user_id)

    if leads_qualified:
        row.leads_qualified += leads_qualified
    if searches_run:
        row.searches_run += searches_run
    if enrichments_used:
        row.enrichments_used += enrichments_used

    await db.commit()


async def check_quota(
    db: AsyncSession,
    user_id: str,
    plan_tier: str = "free",
    action: str = "search",
    count: int = 1,
) -> dict | None:
    """
    Check if the user has quota for an action. Returns None if OK,
    or a dict with quota details if exceeded (for 429 response body).

    Actions: "search", "leads", "enrichment"
    """
    metric_map = {
        "search": "searches_run",
        "leads": "leads_qualified",
        "enrichment": "enrichments_used",
    }

    metric = metric_map.get(action)
    if not metric:
        return None  # Unknown action → allow

    ok = await check_limit(db, user_id, metric, count=count, plan_tier=plan_tier)
    if ok:
        return None  # Within limits

    # Build quota exceeded response
    row = await _get_or_create_row(db, user_id)
    limits = PLAN_LIMITS.get(plan_tier, PLAN_LIMITS["free"])
    limit_val = limits.get(metric)

    return {
        "error": "quota_exceeded",
        "action": action,
        "metric": metric,
        "limit": limit_val,
        "used": getattr(row, metric, 0),
        "plan": plan_tier,
        "upgrade_url": "/dashboard/settings?upgrade=true",
    }
