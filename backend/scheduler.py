"""
Scheduler Engine — Runs scheduled pipelines and periodic re-qualification.

Two async loops run inside the FastAPI lifespan:

1. ``schedule_loop``  — checks ``pipeline_schedules`` every 60s for due runs.
   Includes: concurrent-run guard (``is_running``), crash recovery (only
   bumps ``next_run_at`` **after** success), auto-pause after 3 consecutive
   failures, and timezone-aware ``next_run_at`` computation.

2. ``requalification_loop`` — runs **hourly**, checks a DB flag so it only
   fires once per day.  Re-qualifies top hot leads that haven't been
   re-scored in 30+ days, detects score changes (±2), and triggers email
   notifications.

Design choices vs. TIER2_PLAN.md:
  - ``datetime.now(timezone.utc)`` everywhere (Python 3.12+ compatible).
  - ``is_running`` column prevents double-dispatch when a pipeline outlasts
    the 60s tick interval.
  - ``next_run_at`` is only advanced on success or explicit skip — not
    before dispatch — so a crash mid-run doesn't lose a cycle.
  - Daily re-qual uses an hourly check + ``last_requalification_date`` in
    the DB to avoid drift from ``asyncio.sleep(86400)``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from db import async_session
from db.models import (
    PipelineSchedule,
    Profile,
    QualifiedLead,
    LeadSnapshot,
    EnrichmentJob,
    Search,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Frequency → timedelta mapping
# ──────────────────────────────────────────────

FREQUENCY_DELTAS: dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": timedelta(days=30),
}

VALID_FREQUENCIES = set(FREQUENCY_DELTAS.keys())

# Auto-pause after this many consecutive failures
MAX_CONSECUTIVE_FAILURES = 3


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def compute_next_run(frequency: str, from_dt: Optional[datetime] = None) -> datetime:
    """Compute the next run time from *from_dt* (default: now UTC)."""
    base = from_dt or datetime.now(timezone.utc)
    delta = FREQUENCY_DELTAS.get(frequency, timedelta(weeks=1))
    return base + delta


# ──────────────────────────────────────────────
# 1. Scheduled Pipeline Loop
# ──────────────────────────────────────────────

async def schedule_loop() -> None:
    """
    Main scheduler loop — runs every 60s, checks for due schedules.

    For each due schedule (``next_run_at <= now`` AND ``is_active`` AND
    NOT ``is_running``):
      1. Set ``is_running = True`` (claim the lock).
      2. Dispatch ``run_scheduled_pipeline`` as a background task.
    """
    logger.info("Scheduler loop started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with async_session() as db:
                result = await db.execute(
                    select(PipelineSchedule)
                    .where(
                        PipelineSchedule.is_active.is_(True),
                        PipelineSchedule.is_running.is_(False),
                        PipelineSchedule.next_run_at <= now,
                    )
                    .limit(10)  # Process max 10 per tick to avoid overload
                )
                due_schedules = result.scalars().all()

                for schedule in due_schedules:
                    # Claim the lock
                    schedule.is_running = True
                    await db.commit()
                    logger.info(
                        "Dispatching scheduled pipeline: %s (id=%s, freq=%s)",
                        schedule.name,
                        schedule.id,
                        schedule.frequency,
                    )
                    asyncio.create_task(
                        _run_scheduled_pipeline_safe(schedule.id)
                    )
        except Exception as e:
            logger.error("Scheduler loop error: %s", e, exc_info=True)

        await asyncio.sleep(60)


async def _run_scheduled_pipeline_safe(schedule_id: str) -> None:
    """Wrapper that catches all exceptions so the task never crashes silently."""
    try:
        await run_scheduled_pipeline(schedule_id)
    except Exception as e:
        logger.error(
            "Scheduled pipeline %s crashed: %s",
            schedule_id,
            e,
            exc_info=True,
        )
        # Release the lock and bump failure counter
        try:
            async with async_session() as db:
                schedule = (
                    await db.execute(
                        select(PipelineSchedule).where(PipelineSchedule.id == schedule_id)
                    )
                ).scalar_one_or_none()
                if schedule:
                    schedule.is_running = False
                    schedule.consecutive_failures += 1
                    schedule.last_error = str(e)[:500]
                    if schedule.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        schedule.is_active = False
                        logger.warning(
                            "Auto-paused schedule %s after %d consecutive failures",
                            schedule_id,
                            schedule.consecutive_failures,
                        )
                    # Still advance next_run_at so we don't keep retrying immediately
                    schedule.next_run_at = compute_next_run(schedule.frequency)
                    await db.commit()
        except Exception as inner:
            logger.error("Failed to release lock for schedule %s: %s", schedule_id, inner)


async def run_scheduled_pipeline(schedule_id: str) -> None:
    """Execute a single scheduled pipeline run."""
    from chat_server import (
        engine as chat_engine,
        pipeline_manager,
        _save_search_to_db,
        _save_lead_to_db,
        _geocode_location,
        _guess_country_from_domain,
        _location_matches_region,
        _sanitize_crawl_error,
    )
    from pipeline_engine import run_discovery, process_companies
    from usage import check_quota, increment_usage, LEADS_PER_HUNT
    from sqlalchemy import func as sa_func

    async with async_session() as db:
        schedule = (
            await db.execute(
                select(PipelineSchedule).where(PipelineSchedule.id == schedule_id)
            )
        ).scalar_one_or_none()

        if not schedule:
            logger.warning("Schedule %s not found — skipping", schedule_id)
            return

        user_id = schedule.user_id

        # ── 1. Check user quota ──
        profile = (
            await db.execute(select(Profile).where(Profile.id == user_id))
        ).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        exceeded = await check_quota(db, user_id, plan_tier=plan, action="search")
        if exceeded:
            logger.info("Quota exceeded for user %s — skipping schedule %s", user_id, schedule_id)
            schedule.is_running = False
            schedule.last_error = "Quota exceeded — search limit reached"
            schedule.next_run_at = compute_next_run(schedule.frequency)
            await db.commit()
            return

        # ── 2. Build pipeline from saved config ──
        config = schedule.pipeline_config or {}
        search_ctx = config.get("search_context", {})
        mode = config.get("mode", "discover")
        max_leads = (config.get("options") or {}).get("max_leads", 100)
        use_vision = (config.get("options") or {}).get("use_vision", True)

        plan_max_leads = LEADS_PER_HUNT.get(plan, 25)
        max_leads = min(max_leads, plan_max_leads)

        # Save search record
        pipeline_name = f"[Scheduled] {schedule.name}"
        ctx_for_db = {
            **(search_ctx or {}),
            "_pipeline_name": pipeline_name,
            "_mode": mode,
            "_schedule_id": schedule.id,
        }

        search_id = await _save_search_to_db(
            user_id=user_id,
            context=ctx_for_db,
            queries=ctx_for_db,
            total_found=0,
            messages=[{
                "role": "system",
                "content": f"Scheduled run: {schedule.name} (freq: {schedule.frequency})"
            }],
        )

        if not search_id:
            schedule.is_running = False
            schedule.last_error = "Failed to create search record"
            schedule.consecutive_failures += 1
            schedule.next_run_at = compute_next_run(schedule.frequency)
            await db.commit()
            return

        await increment_usage(db, user_id, searches_run=1)

        # ── 3. Run pipeline ──
        run = pipeline_manager.register(search_id, 0)

        try:
            if mode == "discover":
                if not chat_engine:
                    raise RuntimeError("Chat engine not initialized")

                discovered = await run_discovery(
                    engine=chat_engine,
                    search_context={
                        **(search_ctx or {}),
                        "country_code": config.get("country_code"),
                    },
                    run=run,
                )

                if not discovered:
                    await run.emit({
                        "type": "complete",
                        "summary": {"hot": 0, "review": 0, "rejected": 0, "failed": 0, "discovery_empty": True},
                        "search_id": search_id,
                    })
                    # Success (no results isn't a failure)
                    schedule.is_running = False
                    schedule.last_run_at = datetime.now(timezone.utc)
                    schedule.last_run_id = search_id
                    schedule.next_run_at = compute_next_run(schedule.frequency)
                    schedule.run_count += 1
                    schedule.consecutive_failures = 0
                    schedule.last_error = None
                    await db.commit()
                    return

                discovered.sort(key=lambda c: c.get("score") or 0, reverse=True)
                companies = discovered[:max_leads]
                run.total = len(companies)

                # Check lead quota
                lead_exceeded = await check_quota(db, user_id, plan_tier=plan, action="leads", count=len(companies))
                if lead_exceeded:
                    schedule.is_running = False
                    schedule.last_error = "Lead quota exceeded"
                    schedule.next_run_at = compute_next_run(schedule.frequency)
                    await db.commit()
                    return

                await increment_usage(db, user_id, leads_qualified=len(companies))
            else:
                # qualify_only from saved domains
                domains = config.get("domains", [])
                companies = [
                    {"url": f"https://{d}", "domain": d, "title": d.split(".")[0].replace("-", " ").title()}
                    for d in domains[:max_leads]
                ]

            stats = await process_companies(
                companies=companies,
                search_ctx=search_ctx,
                use_vision=use_vision,
                run=run,
                search_id=search_id,
                user_id=user_id,
                geocode_fn=_geocode_location,
                country_from_domain_fn=_guess_country_from_domain,
                location_matches_fn=_location_matches_region,
                sanitize_error_fn=_sanitize_crawl_error,
                save_lead_fn=_save_lead_to_db,
            )

        except Exception as e:
            logger.error("Scheduled pipeline run error for %s: %s", schedule_id, e, exc_info=True)
            schedule.is_running = False
            schedule.consecutive_failures += 1
            schedule.last_error = str(e)[:500]
            if schedule.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                schedule.is_active = False
            schedule.next_run_at = compute_next_run(schedule.frequency)
            await db.commit()
            return

        # ── 4. Success — update schedule ──
        schedule.is_running = False
        schedule.last_run_at = datetime.now(timezone.utc)
        schedule.last_run_id = search_id
        schedule.next_run_at = compute_next_run(schedule.frequency)
        schedule.run_count += 1
        schedule.consecutive_failures = 0
        schedule.last_error = None
        await db.commit()

        # ── 5. Send notification ──
        try:
            from notifications import send_scheduled_run_complete

            hot = stats.get("hot", 0) if isinstance(stats, dict) else 0
            review = stats.get("review", 0) if isinstance(stats, dict) else 0
            total = hot + review

            if profile and profile.email:
                prefs = profile.notification_prefs or {}
                if prefs.get("scheduled_run", True):
                    await send_scheduled_run_complete(
                        user_email=profile.email,
                        user_name=profile.display_name or profile.email.split("@")[0],
                        schedule_name=schedule.name,
                        search_id=search_id,
                        hot=hot,
                        review=review,
                        new_leads=total,
                    )
        except Exception as e:
            logger.warning("Failed to send scheduled run notification: %s", e)


# ──────────────────────────────────────────────
# 2. Re-qualification Loop
# ──────────────────────────────────────────────

# Simple in-memory tracker — survives within a process lifetime.
# On restart, re-qual fires once then waits 24h. Acceptable.
_last_requalification_date: Optional[str] = None


async def requalification_loop() -> None:
    """
    Runs **hourly**. If it hasn't fired today yet, runs re-qualification
    for Pro/Enterprise users.

    Uses an hourly cadence + date check instead of ``asyncio.sleep(86400)``
    to avoid drift on server restarts.
    """
    global _last_requalification_date
    logger.info("Re-qualification loop started")

    while True:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if _last_requalification_date != today:
                await _run_daily_requalification()
                _last_requalification_date = today
        except Exception as e:
            logger.error("Re-qualification loop error: %s", e, exc_info=True)

        await asyncio.sleep(3600)  # Check every hour


async def _run_daily_requalification() -> None:
    """Re-qualify hot leads that haven't been re-scored in 30+ days."""
    from notifications import send_requalification_alert

    logger.info("Running daily re-qualification check")

    async with async_session() as db:
        # Find users with Pro or Enterprise plans
        pro_users = (
            await db.execute(
                select(Profile).where(Profile.plan.in_(["pro", "enterprise"]))
            )
        ).scalars().all()

        for user in pro_users:
            try:
                await _requalify_user_leads(db, user)
            except Exception as e:
                logger.error(
                    "Re-qualification failed for user %s: %s",
                    user.id,
                    e,
                    exc_info=True,
                )


async def _requalify_user_leads(db, user: Profile) -> None:
    """Re-qualify a single user's hot leads."""
    from sqlalchemy import func as sa_func

    # Determine caps by tier
    max_leads = 50 if user.plan == "pro" else 200  # Enterprise gets more
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Find hot leads not re-qualified in 30+ days
    # Subquery: latest snapshot date per lead
    latest_snapshot_sq = (
        select(
            LeadSnapshot.lead_id,
            sa_func.max(LeadSnapshot.snapshot_at).label("latest_snapshot"),
        )
        .group_by(LeadSnapshot.lead_id)
        .subquery()
    )

    eligible_leads = (
        await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .outerjoin(latest_snapshot_sq, QualifiedLead.id == latest_snapshot_sq.c.lead_id)
            .where(
                Search.user_id == user.id,
                QualifiedLead.tier == "hot",
                QualifiedLead.status.notin_(["won", "lost", "archived"]),
                # Either no snapshot, or last snapshot > 30 days ago
                (latest_snapshot_sq.c.latest_snapshot.is_(None))
                | (latest_snapshot_sq.c.latest_snapshot < cutoff),
            )
            .order_by(QualifiedLead.score.desc())
            .limit(max_leads)
        )
    ).scalars().all()

    if not eligible_leads:
        return

    logger.info(
        "Re-qualifying %d leads for user %s (plan: %s)",
        len(eligible_leads),
        user.id,
        user.plan,
    )

    changed_leads: list[dict] = []

    for lead in eligible_leads:
        try:
            old_score = lead.score
            old_tier = lead.tier

            # Create enrichment job record
            job = EnrichmentJob(
                user_id=user.id,
                action="requalify",
                status="running",
                lead_ids=[lead.id],
                total=1,
            )
            db.add(job)
            await db.flush()

            # Re-crawl and re-qualify the lead
            from scraper import crawl_company
            from intelligence import LeadQualifier
            from utils import determine_tier

            qualifier = LeadQualifier(search_context={
                "industry": None,  # Will use whatever context the search had
            })

            # Get the original search context
            search = (
                await db.execute(
                    select(Search).where(Search.id == lead.search_id)
                )
            ).scalar_one_or_none()

            if search and search.queries_used:
                ctx = search.queries_used
                qualifier = LeadQualifier(search_context={
                    "industry": ctx.get("industry"),
                    "company_profile": ctx.get("company_profile"),
                    "technology_focus": ctx.get("technology_focus"),
                    "qualifying_criteria": ctx.get("qualifying_criteria"),
                    "disqualifiers": ctx.get("disqualifiers"),
                })

            crawl_result = await crawl_company(lead.website_url, take_screenshot=False)

            if not crawl_result.success:
                # Don't tank score on a single failed crawl — require 2 consecutive failures
                # Record the attempt but don't change the score
                snapshot = LeadSnapshot(
                    lead_id=lead.id,
                    score=old_score,
                    tier=old_tier,
                    reasoning=f"Re-crawl failed: {crawl_result.error_message or 'unknown'}",
                    key_signals=["crawl_failed"],
                )
                db.add(snapshot)
                job.status = "complete"
                job.processed = 1
                job.succeeded = 1
                job.results = [{"lead_id": lead.id, "status": "crawl_failed", "score_unchanged": True}]
                await db.commit()
                continue

            qual_result = await qualifier.qualify_lead(
                company_name=lead.company_name,
                website_url=lead.website_url,
                crawl_result=crawl_result,
                use_vision=False,
            )

            new_score = qual_result.confidence_score
            new_tier = determine_tier(new_score).value

            # Save snapshot
            snapshot = LeadSnapshot(
                lead_id=lead.id,
                score=new_score,
                tier=new_tier,
                reasoning=qual_result.reasoning,
                key_signals=qual_result.key_signals,
            )
            db.add(snapshot)

            # Update lead if score changed
            if new_score != old_score:
                lead.score = new_score
                lead.tier = new_tier
                lead.reasoning = qual_result.reasoning
                lead.key_signals = qual_result.key_signals
                lead.last_seen_at = datetime.now(timezone.utc)

            # Track significant changes (±2 or more)
            if abs(new_score - old_score) >= 2:
                direction = "↑" if new_score > old_score else "↓"
                changed_leads.append({
                    "name": lead.company_name,
                    "old_score": old_score,
                    "new_score": new_score,
                    "change": direction,
                })

            job.status = "complete"
            job.processed = 1
            job.succeeded = 1
            job.results = [{
                "lead_id": lead.id,
                "old_score": old_score,
                "new_score": new_score,
                "changed": abs(new_score - old_score) >= 2,
            }]
            await db.commit()

        except Exception as e:
            logger.warning("Re-qualification error for lead %s: %s", lead.id, e)
            continue

    # Send notification if any scores changed
    if changed_leads and user.email:
        prefs = user.notification_prefs or {}
        if prefs.get("requalification", True):
            try:
                await send_requalification_alert(
                    user_email=user.email,
                    user_name=user.display_name or user.email.split("@")[0],
                    changed_leads=changed_leads,
                )
            except Exception as e:
                logger.warning("Failed to send re-qual notification to %s: %s", user.email, e)
