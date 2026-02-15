"""
Chat Server — FastAPI API for the Lead Discovery Chat Interface

Endpoints:
  POST /api/chat            — Process a chat message (conversation LLM)
  POST /api/chat/search     — Generate queries + execute Exa search
  POST /api/pipeline/run    — Run crawl + qualify pipeline (SSE stream)
  GET  /api/health          — Health check

Security layers:
  1. Input sanitization (in chat_engine.py)
  2. Rate limiting (per-IP, in-memory)
  3. CORS restricted to frontend origin
  4. Max request body size
  5. Dual-LLM architecture (query LLM never sees raw user input)

Run:
  uvicorn chat_server:app --reload --port 8000
"""

import asyncio
import json
import logging
import os
import math
import re
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete

from auth import require_auth, get_current_user
from chat_engine import ChatEngine, ExtractedContext
from logging_config import setup_logging
from pipeline_engine import process_companies as _process_companies_core, run_discovery
from stripe_billing import is_stripe_configured
from contact_extraction import extract_contacts_from_content
from linkedin_enrichment import enrich_linkedin, get_linkedin_status
from reddit_signals import get_reddit_pulse

setup_logging()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Rate Limiter (in-memory, per-IP)
# ──────────────────────────────────────────────

class RateLimiter:
    """Simple sliding-window rate limiter with automatic stale-IP cleanup."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # Prune stale IPs every 5 minutes

    def _maybe_cleanup(self):
        """Remove IPs with no recent requests to prevent unbounded memory growth."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        stale_keys = [
            k for k, timestamps in self._requests.items()
            if not timestamps or (now - max(timestamps)) > self.window
        ]
        for k in stale_keys:
            del self._requests[k]

    def check(self, client_id: str) -> bool:
        """Returns True if the request is allowed."""
        now = time.time()
        self._maybe_cleanup()
        # Prune old entries
        self._requests[client_id] = [
            t for t in self._requests[client_id] if now - t < self.window
        ]
        if len(self._requests[client_id]) >= self.max_requests:
            return False
        self._requests[client_id].append(now)
        return True

    def remaining(self, client_id: str) -> int:
        now = time.time()
        active = [t for t in self._requests.get(client_id, []) if now - t < self.window]
        return max(0, self.max_requests - len(active))


# ──────────────────────────────────────────────
# Pipeline Manager — background tasks + reconnectable streams
# ──────────────────────────────────────────────

class PipelineRun:
    """State for a single background pipeline run."""

    def __init__(self, search_id: str, total: int):
        self.search_id = search_id
        self.total = total
        self.status: str = "running"  # running | complete | error
        self.events: list[dict] = []  # all SSE events (for replay)
        self.processed: int = 0
        self.summary: Optional[dict] = None
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self.created_at = time.time()

    async def emit(self, event: dict):
        """Record an event and push to all live subscribers."""
        async with self._lock:
            self.events.append(event)
            if event.get("type") == "result" or (event.get("type") == "error" and not event.get("fatal")):
                self.processed += 1
            if event.get("type") == "complete":
                self.status = "complete"
                self.summary = event.get("summary")
            if event.get("type") == "error" and event.get("fatal"):
                self.status = "error"
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    async def subscribe(self, after: int = 0):
        """
        Yield all events starting from index `after`, then live events.
        This is the core of reconnectable SSE.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            # Replay past events
            for ev in self.events[after:]:
                yield ev
            # If already done, nothing more to wait for
            if self.status in ("complete", "error"):
                return
            self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
                if event.get("type") == "complete" or (event.get("type") == "error" and event.get("fatal")):
                    return
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)

    def snapshot(self) -> dict:
        """Quick JSON status for polling."""
        return {
            "search_id": self.search_id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "summary": self.summary,
        }


class PipelineManager:
    """Manages background pipeline tasks.  Singleton, lives for the process."""

    def __init__(self):
        self._runs: dict[str, PipelineRun] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def get(self, search_id: str) -> Optional[PipelineRun]:
        return self._runs.get(search_id)

    def register(self, search_id: str, total: int) -> PipelineRun:
        run = PipelineRun(search_id, total)
        self._runs[search_id] = run
        return run

    def set_task(self, search_id: str, task: asyncio.Task):
        self._tasks[search_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(search_id, None))

    async def cancel(self, search_id: str) -> bool:
        """Cancel a running pipeline. Returns True if it was running."""
        run = self._runs.get(search_id)
        if not run or run.status != "running":
            return False
        # Cancel the asyncio task
        task = self._tasks.get(search_id)
        if task and not task.done():
            task.cancel()
        # Emit a complete event so SSE subscribers get notified
        summary = {"hot": 0, "review": 0, "rejected": 0, "failed": 0, "stopped": True}
        # Count what we have so far
        for ev in run.events:
            if ev.get("type") == "result":
                tier = ev.get("company", {}).get("tier", "rejected")
                if tier in summary:
                    summary[tier] += 1
        await run.emit({"type": "complete", "summary": summary, "search_id": search_id, "stopped": True})
        return True

    def cleanup_old(self, max_age_seconds: int = 3600):
        """Remove completed runs older than max_age_seconds to prevent memory leak."""
        now = time.time()
        stale = [
            sid for sid, run in self._runs.items()
            if run.status != "running" and (now - run.created_at) > max_age_seconds
        ]
        for sid in stale:
            del self._runs[sid]
            self._tasks.pop(sid, None)


pipeline_manager = PipelineManager()


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., max_length=2500)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., max_length=50)


class SearchRequest(BaseModel):
    """Structured context for query generation — no raw user text."""
    industry: str = Field(..., max_length=500)
    company_profile: Optional[str] = Field(None, max_length=500)
    technology_focus: str = Field(..., max_length=500)
    qualifying_criteria: str = Field(..., max_length=500)
    disqualifiers: Optional[str] = Field(None, max_length=500)
    geographic_region: Optional[str] = Field(None, max_length=200)
    country_code: Optional[str] = Field(None, max_length=2)  # ISO 3166-1 alpha-2
    geo_bounds: Optional[list[float]] = Field(None, description="Map bounding box [sw_lat, sw_lng, ne_lat, ne_lng]")


class ChatResponseModel(BaseModel):
    message: str
    readiness: dict
    extracted_context: Optional[dict] = None
    error: Optional[str] = None


class SearchResponseModel(BaseModel):
    companies: list[dict]
    queries_used: list[dict]
    total_found: int
    unique_domains: int
    summary: Optional[str] = None


# ──────────────────────────────────────────────
# App Setup
# ──────────────────────────────────────────────

# Global instances
engine: Optional[ChatEngine] = None
rate_limiter = RateLimiter(max_requests=120, window_seconds=60)

# Tight limiter for anonymous /api/chat trial — 5 messages per hour per IP
# Authenticated users bypass this entirely
anon_chat_limiter = RateLimiter(max_requests=5, window_seconds=3600)


# ── Read-only routes exempt from rate limiting ──
_RATE_LIMIT_EXEMPT = {
    "/api/health",
    "/api/searches",
    "/api/usage",
    "/api/dashboard/stats",
    "/api/dashboard/funnel",
    "/api/billing/status",
}

# Prefix-based exemptions (pipeline stream/status are high-frequency)
_RATE_LIMIT_EXEMPT_PREFIXES = (
    "/api/pipeline/",  # covers /{id}/stream and /{id}/status
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize chat engine, database, and scheduler on startup."""
    global engine
    
    # Initialize database
    from db import init_db
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready")
    
    logger.info("Starting Lead Discovery Chat Server...")
    engine = ChatEngine()
    logger.info("Chat engine ready")

    # Start scheduler loops (fire-and-forget background tasks)
    from scheduler import schedule_loop, requalification_loop
    scheduler_task = asyncio.create_task(schedule_loop())
    requalification_task = asyncio.create_task(requalification_loop())
    logger.info("Scheduler loops started")

    yield

    # Cleanup
    scheduler_task.cancel()
    requalification_task.cancel()
    logger.info("Shutting down")


app = FastAPI(
    title="Lead Discovery Chat API",
    version="0.1.0",
    lifespan=lifespan,
)

# Auth routes removed — Supabase Auth handles registration/login natively.

# CORS — allow the Next.js frontend (configurable via env)
_allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to API routes (skip CORS preflight, health & read-only dashboard GETs)."""
    path = request.url.path.rstrip("/")
    if (
        request.url.path.startswith("/api/")
        and request.method != "OPTIONS"
        and path not in _RATE_LIMIT_EXEMPT
        and not any(path.startswith(p) for p in _RATE_LIMIT_EXEMPT_PREFIXES)
    ):
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.check(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please wait a moment and try again."},
            )
    return await call_next(request)


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check."""
    from enrichment import get_enrichment_status
    enrich = get_enrichment_status()
    li_status = get_linkedin_status()
    return {
        "status": "ok",
        "llm_available": engine is not None
        and (engine.kimi_client is not None or engine.openai_client is not None),
        "exa_available": engine is not None and engine.exa_client is not None,
        "enrichment_available": bool(enrich["providers"]),
        "enrichment_providers": enrich["providers"],
        "linkedin_available": li_status["available"],
        "linkedin_providers": li_status["providers"],
    }


@app.get("/api/usage")
async def get_user_usage(user=Depends(require_auth)):
    """Return current month's usage and limits for the authenticated user."""
    from usage import get_usage
    from db import get_db as _get_db

    async for db in _get_db():
        # Get user's plan from profile
        from db.models import Profile
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"
        data = await get_usage(db, user.id, plan_tier=plan)
        return data


# ──────────────────────────────────────────────
# Billing Endpoints (Stripe)
# ──────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern=r"^(pro|enterprise)$")


@app.post("/api/billing/checkout")
async def billing_checkout(request: CheckoutRequest, user=Depends(require_auth)):
    """Create a Stripe Checkout Session and return the URL."""
    from stripe_billing import create_checkout_session
    from db import get_db as _get_db

    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Billing not configured")

    async for db in _get_db():
        try:
            url = await create_checkout_session(
                db=db,
                user_id=user.id,
                user_email=user.email or "",
                plan=request.plan,
            )
            return {"url": url}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Checkout error: %s", e)
            raise HTTPException(status_code=500, detail="Failed to create checkout session")


@app.post("/api/billing/portal")
async def billing_portal(user=Depends(require_auth)):
    """Create a Stripe Customer Portal session and return the URL."""
    from stripe_billing import create_portal_session
    from db import get_db as _get_db

    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Billing not configured")

    async for db in _get_db():
        try:
            url = await create_portal_session(db=db, user_id=user.id)
            return {"url": url}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Portal error: %s", e)
            raise HTTPException(status_code=500, detail="Failed to create portal session")


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    """
    Stripe webhook receiver — no auth required (uses Stripe signature).
    Must receive the raw body for signature verification.
    """
    from stripe_billing import handle_webhook
    from db import get_db as _get_db

    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Billing not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    async for db in _get_db():
        try:
            result = await handle_webhook(payload, sig_header, db)
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Webhook error: %s", e)
            raise HTTPException(status_code=500, detail="Webhook processing failed")


@app.get("/api/billing/status")
async def billing_status(user=Depends(require_auth)):
    """Return current plan + billing status for the authenticated user."""
    from stripe_billing import get_billing_status
    from usage import get_usage
    from db import get_db as _get_db

    async for db in _get_db():
        billing = await get_billing_status(db, user.id)
        usage = await get_usage(db, user.id, plan_tier=billing["plan"])
        return {**billing, "usage": usage}


@app.post("/api/chat", response_model=ChatResponseModel)
async def chat(request: ChatRequest, req: Request, user=Depends(get_current_user)):
    """
    Process a chat message.
    Sends the conversation to the conversation LLM, which asks follow-up
    questions and extracts structured search parameters.

    Open to anonymous visitors as a capped trial (5 msgs/hour per IP).
    Authenticated users have no extra limit beyond the global rate limiter.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Chat engine not initialized")

    # Anonymous users get a tight trial cap to prevent credit abuse
    if not user:
        client_ip = req.client.host if req.client else "unknown"
        if not anon_chat_limiter.check(client_ip):
            remaining = anon_chat_limiter.remaining(client_ip)
            raise HTTPException(
                status_code=429,
                detail=(
                    "You've used all 5 free trial messages this hour. "
                    "Sign up for unlimited access!"
                ),
            )

    # Convert to dicts for the engine
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    result = await engine.process_message(messages)

    return ChatResponseModel(
        message=result.reply,
        readiness=result.readiness.to_dict(),
        extracted_context=result.extracted_context.to_dict(),
        error=result.error,
    )


@app.post("/api/chat/search", response_model=SearchResponseModel)
async def search(request: SearchRequest, user=Depends(require_auth)):
    """
    Generate queries from structured context and execute via Exa.
    This endpoint receives ONLY validated structured parameters —
    the raw user conversation never reaches the query generation LLM.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Chat engine not initialized")

    # ── Quota check: searches ──
    from usage import check_quota, increment_usage
    from db import get_db as _get_db
    from db.models import Profile

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        exceeded = await check_quota(db, user.id, plan_tier=plan, action="search")
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        # Increment search count
        await increment_usage(db, user.id, searches_run=1)

    # Build ExtractedContext from the validated request
    context = ExtractedContext(
        industry=request.industry,
        company_profile=request.company_profile,
        technology_focus=request.technology_focus,
        qualifying_criteria=request.qualifying_criteria,
        disqualifiers=request.disqualifiers,
        geographic_region=request.geographic_region,
        country_code=request.country_code,
        geo_bounds=request.geo_bounds,
    )

    result = await engine.generate_and_search(context)

    return SearchResponseModel(
        companies=result.companies,
        queries_used=result.queries_used,
        total_found=result.total_found,
        unique_domains=result.unique_domains,
    )


# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# Contact Enrichment SSE Endpoint
# ──────────────────────────────────────────────

class EnrichCompany(BaseModel):
    domain: str = Field(..., max_length=200)
    title: str = Field(..., max_length=300)
    url: str = Field(..., max_length=500)
    contact_name: Optional[str] = Field(None, max_length=200)
    linkedin_url: Optional[str] = Field(None, max_length=500)


class EnrichRequest(BaseModel):
    companies: list[EnrichCompany] = Field(..., max_length=50)


@app.post("/api/enrich")
async def enrich_contacts(request: EnrichRequest, user=Depends(require_auth)):
    """
    Enrich contacts for qualified leads using Hunter.io.
    Streams SSE events: progress, result, complete.
    """
    from enrichment import enrich_contact, get_enrichment_status
    from usage import check_quota, increment_usage
    from db import get_db as _get_db
    from db.models import Profile

    # ── Quota check: enrichments ──
    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        exceeded = await check_quota(
            db, user.id, plan_tier=plan,
            action="enrichment", count=len(request.companies),
        )
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        # Increment enrichment usage
        await increment_usage(db, user.id, enrichments_used=len(request.companies))

    status = get_enrichment_status()
    if not status["providers"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No enrichment APIs configured. Add HUNTER_API_KEY to your .env file."
            },
        )

    companies = [c.model_dump() for c in request.companies]
    user_id = user.id  # capture for use inside generator

    async def _persist_hunter_contact(domain: str, enriched: dict):
        """Save a Hunter.io contact to LeadContact table for the matching lead."""
        try:
            from db import get_db as _get_db2
            from db.models import QualifiedLead, LeadContact, Search

            async for db2 in _get_db2():
                # Find the lead by domain + user
                lead = (await db2.execute(
                    select(QualifiedLead)
                    .join(Search, QualifiedLead.search_id == Search.id)
                    .where(Search.user_id == user_id, QualifiedLead.domain == domain)
                    .order_by(QualifiedLead.created_at.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if not lead:
                    return

                # Check for existing contact with same email to avoid duplicates
                if enriched.get("email"):
                    existing = (await db2.execute(
                        select(LeadContact).where(
                            LeadContact.lead_id == lead.id,
                            LeadContact.email == enriched["email"],
                        )
                    )).scalar_one_or_none()
                    if existing:
                        return

                lc = LeadContact(
                    lead_id=lead.id,
                    full_name=enriched.get("title"),  # company title as fallback
                    job_title=enriched.get("job_title"),
                    email=enriched.get("email"),
                    phone=enriched.get("phone"),
                    linkedin_url=None,
                    source=enriched.get("source", "hunter"),
                )
                db2.add(lc)
                await db2.commit()
                logger.debug("Saved Hunter.io contact for %s (lead %s)", domain, lead.id)
        except Exception as e:
            logger.error("Failed to persist Hunter.io contact for %s: %s", domain, e)

    async def generate():
        total = len(companies)
        yield sse_event({"type": "init", "total": total, "providers": status["providers"]})

        results_found = 0

        for i, company in enumerate(companies):
            yield sse_event({
                "type": "progress",
                "index": i,
                "total": total,
                "company": {"title": company["title"], "domain": company["domain"]},
            })

            try:
                result = await enrich_contact(
                    contact_name=company.get("contact_name"),
                    company_domain=company["domain"],
                    linkedin_url=company.get("linkedin_url"),
                )

                enriched = {
                    "domain": company["domain"],
                    "title": company["title"],
                    "url": company["url"],
                    "email": result.email,
                    "phone": result.mobile_number,
                    "job_title": result.job_title,
                    "source": result.enrichment_source,
                    "found": bool(result.email or result.mobile_number),
                }

                if enriched["found"]:
                    results_found += 1
                    # Persist Hunter.io contact to database
                    await _persist_hunter_contact(company["domain"], enriched)

                yield sse_event({
                    "type": "result",
                    "index": i,
                    "total": total,
                    "contact": enriched,
                })

            except Exception as e:
                logger.error("Enrichment error for %s: %s", company['domain'], e)
                yield sse_event({
                    "type": "result",
                    "index": i,
                    "total": total,
                    "contact": {
                        "domain": company["domain"],
                        "title": company["title"],
                        "url": company["url"],
                        "email": None,
                        "phone": None,
                        "source": "error",
                        "found": False,
                    },
                })

        yield sse_event({
            "type": "complete",
            "summary": {
                "total": total,
                "found": results_found,
                "not_found": total - results_found,
                "providers_used": status["providers"],
            },
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────
# Reddit Market Signals
# ──────────────────────────────────────────────

class RedditPulseRequest(BaseModel):
    industry: Optional[str] = Field(None, max_length=200)
    technology: Optional[str] = Field(None, max_length=200)
    company_profile: Optional[str] = Field(None, max_length=200)
    custom_query: Optional[str] = Field(None, max_length=300)
    time_range: str = Field("month", pattern="^(day|week|month|year)$")


@app.post("/api/reddit/pulse")
async def reddit_pulse(request: RedditPulseRequest, user=Depends(require_auth)):
    """Get market sentiment and buying intent signals from Reddit.
    
    Searches relevant subreddits based on the user's industry/technology
    context and returns analyzed signals with sentiment, buying intent,
    and a market pulse summary.
    
    Cost: $0 (Reddit API is free). Only LLM cost for sentiment analysis.
    """
    if not any([request.industry, request.technology, request.company_profile, request.custom_query]):
        raise HTTPException(status_code=400, detail="At least one search parameter required")
    
    try:
        pulse = await get_reddit_pulse(
            industry=request.industry,
            technology=request.technology,
            company_profile=request.company_profile,
            custom_query=request.custom_query,
            time_range=request.time_range,
        )
        return pulse
    except Exception as e:
        logger.error("Reddit pulse error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Reddit signals: {str(e)}")


# ──────────────────────────────────────────────
# Chat Session Auto-Save Endpoint
# ──────────────────────────────────────────────

class ChatSessionRequest(BaseModel):
    session_id: Optional[str] = None
    messages: list[dict]
    extracted_context: Optional[dict] = None


@app.post("/api/chat/session")
async def save_chat_session(request: ChatSessionRequest, user=Depends(require_auth)):
    """
    Create or update a chat session (Search record) so in-progress chats
    appear on the dashboard before a pipeline is launched.
    """
    from db import get_db as _get_db
    from db.models import Search
    from sqlalchemy import select as _select

    ctx = request.extracted_context or {}
    # Normalise camelCase keys from frontend to snake_case
    context = {
        "industry": ctx.get("industry"),
        "company_profile": ctx.get("companyProfile") or ctx.get("company_profile"),
        "technology_focus": ctx.get("technologyFocus") or ctx.get("technology_focus"),
        "qualifying_criteria": ctx.get("qualifyingCriteria") or ctx.get("qualifying_criteria"),
        "disqualifiers": ctx.get("disqualifiers"),
        "geographic_region": ctx.get("geographicRegion") or ctx.get("geographic_region"),
        "country_code": ctx.get("countryCode") or ctx.get("country_code"),
        "geo_bounds": ctx.get("geoBounds") or ctx.get("geo_bounds"),
        "map_bounds": ctx.get("mapBounds") or ctx.get("map_bounds"),
        "show_map": ctx.get("showMap") if ctx.get("showMap") is not None else ctx.get("show_map"),
    }

    async for db in _get_db():
        await _ensure_profile_exists(db, user.id)

        if request.session_id:
            # Try to update existing session
            existing = (await db.execute(
                _select(Search).where(
                    Search.id == request.session_id,
                    Search.user_id == user.id,
                )
            )).scalar_one_or_none()

            if existing:
                existing.messages = request.messages
                existing.industry = context.get("industry") or existing.industry
                existing.company_profile = context.get("company_profile") or existing.company_profile
                existing.technology_focus = context.get("technology_focus") or existing.technology_focus
                existing.qualifying_criteria = context.get("qualifying_criteria") or existing.qualifying_criteria
                existing.disqualifiers = context.get("disqualifiers") or existing.disqualifiers
                existing.geographic_region = context.get("geographic_region") or existing.geographic_region
                existing.country_code = context.get("country_code") or existing.country_code
                # Geo/map bounds — always overwrite (user may clear them)
                if "geo_bounds" in context:
                    existing.geo_bounds = context["geo_bounds"]
                if "map_bounds" in context:
                    existing.map_bounds = context["map_bounds"]
                if context.get("show_map") is not None:
                    existing.show_map = bool(context["show_map"])
                await db.commit()
                return {"session_id": existing.id}

        # Create new session
        session_id = str(uuid.uuid4())
        search = Search(
            id=session_id,
            user_id=user.id,
            industry=context.get("industry"),
            company_profile=context.get("company_profile"),
            technology_focus=context.get("technology_focus"),
            qualifying_criteria=context.get("qualifying_criteria"),
            disqualifiers=context.get("disqualifiers"),
            geographic_region=context.get("geographic_region"),
            country_code=context.get("country_code"),
            geo_bounds=context.get("geo_bounds"),
            map_bounds=context.get("map_bounds"),
            show_map=bool(context.get("show_map")) if context.get("show_map") is not None else False,
            queries_used={"_mode": "chat_session"},
            total_found=0,
            messages=request.messages,
        )
        db.add(search)
        await db.commit()
        return {"session_id": session_id}


# ──────────────────────────────────────────────
# Pipeline SSE Endpoint
# ──────────────────────────────────────────────

class PipelineCompany(BaseModel):
    url: str = Field(..., max_length=500)
    domain: str = Field(..., max_length=200)
    title: str = Field(..., max_length=300)
    score: Optional[float] = None  # Exa relevance score for prioritization
    exa_text: Optional[str] = None  # Full page text from Exa's index (up to 10k chars)
    highlights: Optional[str] = None  # Exa search highlights


class SearchContext(BaseModel):
    """User's search context — drives dynamic qualification criteria."""
    industry: Optional[str] = None
    company_profile: Optional[str] = None
    technology_focus: Optional[str] = None
    qualifying_criteria: Optional[str] = None
    disqualifiers: Optional[str] = None
    geographic_region: Optional[str] = None
    geo_bounds: Optional[list[float]] = Field(None, description="Map bounding box [sw_lat, sw_lng, ne_lat, ne_lng]")


class PipelineRequest(BaseModel):
    companies: list[PipelineCompany] = Field(..., max_length=200)
    use_vision: bool = True
    search_context: Optional[SearchContext] = None
    messages: Optional[list[dict]] = None  # chat history [{role, content}]


class BulkImportRequest(BaseModel):
    """Bulk domain import — paste domains or upload CSV, skip chat flow."""
    domains: list[str] = Field(..., max_length=200)
    search_context: Optional[SearchContext] = None
    use_vision: bool = True


class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    search_context: dict


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    search_context: Optional[dict] = None


class LinkedInEnrichRequest(BaseModel):
    domain: str = Field(..., max_length=200)
    lead_id: str = Field(..., max_length=100)


class LeadSearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    tier: Optional[str] = None


class PipelineCreateRequest(BaseModel):
    """
    Unified pipeline creation — the primary entry point for all pipeline runs.

    Modes:
      - discover: generate Exa queries from search_context -> search -> crawl -> qualify
      - qualify_only: take provided domains -> crawl -> qualify (skip discovery)
    """
    name: Optional[str] = Field(None, max_length=255, description="Pipeline name (auto-generated if omitted)")
    mode: str = Field("discover", pattern="^(discover|qualify_only)$")
    search_context: Optional[SearchContext] = None
    domains: Optional[list[str]] = Field(None, max_length=200, description="Domains for qualify_only mode")
    template_id: Optional[str] = Field(None, max_length=100, description="Load search_context from a saved template")
    country_code: Optional[str] = Field(None, max_length=2, description="ISO 3166-1 alpha-2 for Exa geo filtering")
    geo_bounds: Optional[list[float]] = Field(None, description="Map bounding box [sw_lat, sw_lng, ne_lat, ne_lng]")
    options: Optional[dict] = Field(default_factory=lambda: {
        "use_vision": True,
        "max_leads": 100,
    })


def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@app.post("/api/pipeline/run")
async def run_pipeline(request: PipelineRequest, user=Depends(require_auth)):
    """
    Start the crawl → qualify pipeline as a **background task**.
    Returns immediately with ``{ search_id }`` — the frontend then
    connects to ``GET /api/pipeline/{search_id}/stream`` for live SSE.
    """
    # ── Quota check: leads ──
    from usage import check_quota, increment_usage, LEADS_PER_HUNT
    from db import get_db as _get_db
    from db.models import Profile

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        # Enforce leads-per-hunt cap
        max_leads = LEADS_PER_HUNT.get(plan, 25)
        companies_list = request.companies[:max_leads]

        # Check monthly leads quota
        exceeded = await check_quota(db, user.id, plan_tier=plan, action="leads", count=len(companies_list))
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        # Increment leads counter upfront (same pattern as searches_run)
        await increment_usage(db, user.id, leads_qualified=len(companies_list))

    companies = [c.model_dump() for c in companies_list]
    use_vision = request.use_vision
    search_ctx = request.search_context.model_dump() if request.search_context else None
    pipeline_messages = request.messages

    # Smart prioritization: sort by Exa score (descending)
    companies.sort(key=lambda c: c.get("score") or 0, reverse=True)

    # Save search to DB upfront so we have a search_id
    # Tag as chat-originated pipeline so the frontend can show "Resume Chat"
    pipeline_name = (search_ctx or {}).get("industry") or (search_ctx or {}).get("company_profile") or "Chat Pipeline"
    ctx_for_db = {
        "_mode": "chat_pipeline",
        "_pipeline_name": pipeline_name,
    }
    search_id = None
    try:
        search_id = await _save_search_to_db(
            user_id=user.id,
            context=search_ctx or {},
            queries=ctx_for_db,
            total_found=len(companies),
            messages=pipeline_messages,
        )
        logger.info("Saved search %s to DB for user %s", search_id, user.id)
    except Exception as e:
        logger.error("Failed to save search to DB: %s (type: %s)", e, type(e).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create search record")

    # Clean up old completed pipeline runs
    pipeline_manager.cleanup_old()

    # Register the run and spawn background task
    total = len(companies)
    run = pipeline_manager.register(search_id, total)

    async def _run_pipeline_bg():
        """Background task — delegates to shared pipeline engine."""
        await _process_companies_core(
            companies=companies,
            search_ctx=search_ctx,
            use_vision=use_vision,
            run=run,
            search_id=search_id,
            user_id=user.id,
            geocode_fn=_geocode_location,
            country_from_domain_fn=_guess_country_from_domain,
            location_matches_fn=_location_matches_region,
            sanitize_error_fn=_sanitize_crawl_error,
            save_lead_fn=_save_lead_to_db,
        )

    task = asyncio.create_task(_run_pipeline_bg())
    pipeline_manager.set_task(search_id, task)

    return {"search_id": search_id}


@app.get("/api/pipeline/{search_id}/stream")
async def pipeline_stream(search_id: str, after: int = 0, user=Depends(require_auth)):
    """
    Reconnectable SSE stream for a running (or completed) pipeline.
    Pass ``?after=N`` to skip the first N events (for reconnection).
    """
    run = pipeline_manager.get(search_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline not found — it may have already finished. Check /api/searches for results.")

    async def generate():
        async for event in run.subscribe(after=after):
            yield sse_event(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/pipeline/{search_id}/status")
async def pipeline_status(search_id: str, user=Depends(require_auth)):
    """Quick JSON snapshot of pipeline progress (no SSE)."""
    run = pipeline_manager.get(search_id)
    if not run:
        return {"search_id": search_id, "status": "not_found"}
    return run.snapshot()


@app.post("/api/pipeline/{search_id}/stop")
async def stop_pipeline(search_id: str, user=Depends(require_auth)):
    """Stop a running pipeline. Keeps any leads already processed."""
    cancelled = await pipeline_manager.cancel(search_id)
    if not cancelled:
        run = pipeline_manager.get(search_id)
        status = run.status if run else "not_found"
        return {"search_id": search_id, "stopped": False, "status": status}
    return {"search_id": search_id, "stopped": True, "status": "stopped"}


# ──────────────────────────────────────────────
# Pipeline Create — Unified Entry Point
# ──────────────────────────────────────────────

@app.post("/api/pipeline/create")
async def create_pipeline(request: PipelineCreateRequest, user=Depends(require_auth)):
    """
    Unified pipeline creation — the **primary** entry point for all pipeline runs.

    This replaces the split flow of /api/chat/search + /api/pipeline/run.
    The frontend can call this single endpoint from any entry point:
    chat, manual config form, saved template, or API.

    Modes:
      - discover: generate Exa queries from search_context → Exa search → crawl → qualify
      - qualify_only: take provided domains → crawl → qualify (skip discovery)

    Returns immediately with { pipeline_id, status: "running" }.
    Connect to GET /api/pipeline/{pipeline_id}/stream for live SSE.
    """
    from pipeline_engine import run_discovery, process_companies
    from usage import check_quota, increment_usage, LEADS_PER_HUNT
    from db import get_db as _get_db
    from db.models import Profile, SearchTemplate

    # ── Resolve search_context from template if needed ──
    search_ctx_model = request.search_context
    if request.template_id and not search_ctx_model:
        async for db in _get_db():
            from sqlalchemy import select as sa_select
            tmpl = (await db.execute(
                sa_select(SearchTemplate).where(
                    SearchTemplate.id == request.template_id,
                    SearchTemplate.user_id == user.id,
                )
            )).scalar_one_or_none()
            if not tmpl:
                raise HTTPException(status_code=404, detail="Template not found")
            ctx_data = tmpl.search_context or {}
            search_ctx_model = SearchContext(
                industry=ctx_data.get("industry"),
                company_profile=ctx_data.get("company_profile"),
                technology_focus=ctx_data.get("technology_focus"),
                qualifying_criteria=ctx_data.get("qualifying_criteria"),
                disqualifiers=ctx_data.get("disqualifiers"),
                geographic_region=ctx_data.get("geographic_region"),
            )

    search_ctx = search_ctx_model.model_dump() if search_ctx_model else None
    use_vision = (request.options or {}).get("use_vision", True)
    max_leads = (request.options or {}).get("max_leads", 100)

    # ── Validate mode requirements ──
    if request.mode == "discover" and not search_ctx:
        raise HTTPException(status_code=400, detail="search_context is required for discover mode")
    if request.mode == "qualify_only" and not request.domains:
        raise HTTPException(status_code=400, detail="domains are required for qualify_only mode")

    # ── Quota checks ──
    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        plan_max_leads = LEADS_PER_HUNT.get(plan, 25)
        max_leads = min(max_leads, plan_max_leads)

        # Check search quota (for discover mode)
        if request.mode == "discover":
            exceeded = await check_quota(db, user.id, plan_tier=plan, action="search")
            if exceeded:
                return JSONResponse(status_code=429, content=exceeded)
            await increment_usage(db, user.id, searches_run=1)

    # ── Clean domains for qualify_only mode ──
    clean_domains = []
    if request.mode == "qualify_only" and request.domains:
        seen = set()
        for d in request.domains:
            d = d.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            if d and d not in seen and "." in d:
                seen.add(d)
                clean_domains.append(d)
        clean_domains = clean_domains[:max_leads]

    # ── Generate pipeline name ──
    pipeline_name = request.name
    if not pipeline_name:
        if search_ctx:
            parts = []
            if search_ctx.get("industry"):
                parts.append(search_ctx["industry"][:30])
            if search_ctx.get("geographic_region"):
                parts.append(search_ctx["geographic_region"][:20])
            pipeline_name = " — ".join(parts) if parts else "Pipeline"
        elif clean_domains:
            pipeline_name = f"Bulk import ({len(clean_domains)} domains)"
        else:
            pipeline_name = "Pipeline"

    # ── Save search to DB ──
    search_id = None
    try:
        ctx_for_db = search_ctx or {}
        if request.mode == "qualify_only":
            ctx_for_db["_bulk_import"] = True
        ctx_for_db["_pipeline_name"] = pipeline_name
        ctx_for_db["_mode"] = request.mode

        initial_count = len(clean_domains) if request.mode == "qualify_only" else 0
        search_id = await _save_search_to_db(
            user_id=user.id,
            context=ctx_for_db,
            queries=ctx_for_db,  # Store full context (incl. _pipeline_name, _mode) in queries_used
            total_found=initial_count,
            messages=[{"role": "system", "content": f"Pipeline created: {pipeline_name} (mode: {request.mode})"}],
        )
        logger.info("Created pipeline %s (%s) for user %s", search_id, pipeline_name, user.id)
    except Exception as e:
        logger.error("Failed to create pipeline record: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create pipeline record")

    # ── Register with pipeline manager and spawn background task ──
    pipeline_manager.cleanup_old()
    initial_total = len(clean_domains) if request.mode == "qualify_only" else 0
    run = pipeline_manager.register(search_id, initial_total)

    async def _pipeline_bg():
        """Background task — handles discovery (if needed) + processing."""
        try:
            companies = []

            if request.mode == "discover":
                # ── Stage 1: Discovery ──
                if not engine:
                    await run.emit({"type": "error", "error": "Search engine not initialized", "fatal": True})
                    return

                discovered = await run_discovery(
                    engine=engine,
                    search_context={
                        **(search_ctx or {}),
                        "country_code": request.country_code,
                        **({"geo_bounds": request.geo_bounds} if request.geo_bounds else {}),
                    },
                    run=run,
                )

                if not discovered:
                    await run.emit({
                        "type": "complete",
                        "summary": {"hot": 0, "review": 0, "rejected": 0, "failed": 0, "discovery_empty": True},
                        "search_id": search_id,
                    })
                    return

                # Sort by Exa score (descending) and cap
                discovered.sort(key=lambda c: c.get("score") or 0, reverse=True)
                companies = discovered[:max_leads]
                run.total = len(companies)

                # Check leads quota now that we know the count
                try:
                    async for db in _get_db():
                        profile = (await db.execute(
                            select(Profile).where(Profile.id == user.id)
                        )).scalar_one_or_none()
                        plan = profile.plan if profile else "free"
                        exceeded = await check_quota(db, user.id, plan_tier=plan, action="leads", count=len(companies))
                        if exceeded:
                            await run.emit({"type": "error", "error": "Lead quota exceeded", "fatal": True})
                            return
                        await increment_usage(db, user.id, leads_qualified=len(companies))
                except Exception as e:
                    logger.error("Quota check in pipeline bg failed: %s", e)

            else:
                # ── qualify_only: build company list from domains ──
                companies = []
                for d in clean_domains:
                    title = d.split(".")[0].replace("-", " ").title()
                    companies.append({
                        "url": f"https://{d}",
                        "domain": d,
                        "title": title,
                    })

                # Quota check for leads
                try:
                    async for db in _get_db():
                        profile = (await db.execute(
                            select(Profile).where(Profile.id == user.id)
                        )).scalar_one_or_none()
                        plan = profile.plan if profile else "free"
                        exceeded = await check_quota(db, user.id, plan_tier=plan, action="leads", count=len(companies))
                        if exceeded:
                            await run.emit({"type": "error", "error": "Lead quota exceeded", "fatal": True})
                            return
                        await increment_usage(db, user.id, leads_qualified=len(companies))
                except Exception as e:
                    logger.error("Quota check in pipeline bg failed: %s", e)

            # ── Stage 2+: Process companies (crawl → qualify → enrich) ──
            await process_companies(
                companies=companies,
                search_ctx=search_ctx,
                use_vision=use_vision,
                run=run,
                search_id=search_id,
                user_id=user.id,
                geocode_fn=_geocode_location,
                country_from_domain_fn=_guess_country_from_domain,
                location_matches_fn=_location_matches_region,
                sanitize_error_fn=_sanitize_crawl_error,
                save_lead_fn=_save_lead_to_db,
            )

        except Exception as e:
            logger.error("Fatal pipeline create error: %s", e, exc_info=True)
            await run.emit({"type": "error", "error": str(e)[:200], "fatal": True})

    task = asyncio.create_task(_pipeline_bg())
    pipeline_manager.set_task(search_id, task)

    return {
        "pipeline_id": search_id,
        "name": pipeline_name,
        "mode": request.mode,
        "status": "running",
    }


# ──────────────────────────────────────────────
# Dashboard API Endpoints
# ──────────────────────────────────────────────

@app.get("/api/dashboard/stats")
async def dashboard_stats(user=Depends(require_auth)):
    """Return dashboard stats for the authenticated user."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, EnrichmentResult_

    async for db in _get_db():
        user_id = user.id

        # Total searches
        total_searches = (await db.execute(
            select(func.count(Search.id)).where(Search.user_id == user_id)
        )).scalar() or 0

        # Lead counts by tier
        lead_counts = (await db.execute(
            select(QualifiedLead.tier, func.count(QualifiedLead.id))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .group_by(QualifiedLead.tier)
        )).all()

        tier_map = {row[0]: row[1] for row in lead_counts}
        total_leads = sum(tier_map.values())

        # Enriched contacts count
        contacts_enriched = (await db.execute(
            select(func.count(EnrichmentResult_.id))
            .join(QualifiedLead, EnrichmentResult_.lead_id == QualifiedLead.id)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
        )).scalar() or 0

        # Leads this month
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        leads_this_month = (await db.execute(
            select(func.count(QualifiedLead.id))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .where(QualifiedLead.created_at >= month_start)
        )).scalar() or 0

        return {
            "total_leads": total_leads,
            "hot_leads": tier_map.get("hot", 0),
            "review_leads": tier_map.get("review", 0),
            "rejected_leads": tier_map.get("rejected", 0),
            "total_searches": total_searches,
            "contacts_enriched": contacts_enriched,
            "leads_this_month": leads_this_month,
        }


@app.get("/api/dashboard/funnel")
async def dashboard_funnel(user=Depends(require_auth)):
    """Return funnel metrics for the authenticated user."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        user_id = user.id

        # Stage counts
        stage_rows = (await db.execute(
            select(QualifiedLead.status, func.count(QualifiedLead.id))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .group_by(QualifiedLead.status)
        )).all()

        stages = {row[0]: row[1] for row in stage_rows}
        total_leads = sum(stages.values())

        # Total pipeline value (everything except lost/archived)
        total_pipeline_value = (await db.execute(
            select(func.coalesce(func.sum(QualifiedLead.deal_value), 0))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .where(QualifiedLead.status.notin_(["lost", "archived"]))
        )).scalar() or 0

        # Won value
        won_value = (await db.execute(
            select(func.coalesce(func.sum(QualifiedLead.deal_value), 0))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .where(QualifiedLead.status == "won")
        )).scalar() or 0

        # Lost value
        lost_value = (await db.execute(
            select(func.coalesce(func.sum(QualifiedLead.deal_value), 0))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .where(QualifiedLead.status == "lost")
        )).scalar() or 0

        # Conversion rate: won / (total non-archived) * 100
        non_archived = total_leads - stages.get("archived", 0)
        won_count = stages.get("won", 0)
        conversion_rate = round((won_count / non_archived) * 100, 1) if non_archived > 0 else 0

        # Avg days to close: AVG(status_changed_at - created_at) WHERE status = 'won'
        from sqlalchemy import extract, cast, Numeric
        avg_days_result = (await db.execute(
            select(
                func.avg(
                    extract("epoch", QualifiedLead.status_changed_at - QualifiedLead.created_at) / 86400.0
                )
            )
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user_id)
            .where(QualifiedLead.status == "won")
            .where(QualifiedLead.status_changed_at.isnot(None))
        )).scalar()
        avg_days_to_close = round(float(avg_days_result), 1) if avg_days_result else 0

        return {
            "stages": {
                "new": stages.get("new", 0),
                "contacted": stages.get("contacted", 0),
                "in_progress": stages.get("in_progress", 0),
                "won": stages.get("won", 0),
                "lost": stages.get("lost", 0),
                "archived": stages.get("archived", 0),
            },
            "total_pipeline_value": float(total_pipeline_value),
            "won_value": float(won_value),
            "lost_value": float(lost_value),
            "conversion_rate": conversion_rate,
            "avg_days_to_close": avg_days_to_close,
            "total_leads": total_leads,
        }


@app.get("/api/searches")
async def list_searches(user=Depends(require_auth)):
    """List all user's searches with lead counts per tier."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        searches = (await db.execute(
            select(Search)
            .where(Search.user_id == user.id)
            .order_by(Search.created_at.desc())
        )).scalars().all()

        results = []
        for s in searches:
            # Get tier counts for this search
            tier_counts = (await db.execute(
                select(QualifiedLead.tier, func.count(QualifiedLead.id))
                .where(QualifiedLead.search_id == s.id)
                .group_by(QualifiedLead.tier)
            )).all()
            tiers = {row[0]: row[1] for row in tier_counts}

            # Extract pipeline metadata from queries_used (where _pipeline_name etc. are stored)
            queries_ctx = s.queries_used if isinstance(s.queries_used, dict) else {}
            pipeline_name = queries_ctx.get("_pipeline_name") or s.industry or s.company_profile or "Untitled Pipeline"
            pipeline_mode = queries_ctx.get("_mode", "discover")

            # Build the reusable search_context for re-runs
            search_context = {}
            for key in ("industry", "company_profile", "technology_focus", "qualifying_criteria", "disqualifiers"):
                val = getattr(s, key, None)
                if val:
                    search_context[key] = val
            # geographic_region is not a column — pull from queries_used
            if queries_ctx.get("geographic_region"):
                search_context["geographic_region"] = queries_ctx["geographic_region"]

            # Check if this pipeline is currently running in memory
            live_run = pipeline_manager.get(s.id)
            run_status = "complete"
            run_progress = None
            if live_run:
                run_status = live_run.status  # running | complete | error
                if live_run.status == "running":
                    run_progress = {
                        "processed": live_run.processed,
                        "total": live_run.total,
                    }

            results.append({
                "id": s.id,
                "name": pipeline_name,
                "mode": pipeline_mode,
                "industry": s.industry,
                "company_profile": s.company_profile,
                "technology_focus": s.technology_focus,
                "qualifying_criteria": s.qualifying_criteria,
                "disqualifiers": s.disqualifiers,
                "geographic_region": queries_ctx.get("geographic_region"),
                "search_context": search_context,
                "total_found": s.total_found,
                "hot": tiers.get("hot", 0),
                "review": tiers.get("review", 0),
                "rejected": tiers.get("rejected", 0),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "run_status": run_status,
                "run_progress": run_progress,
            })

        return results


@app.get("/api/searches/{search_id}")
async def get_search(search_id: str, user=Depends(require_auth)):
    """Get a single search with its leads."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        search = (await db.execute(
            select(Search)
            .where(Search.id == search_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not search:
            raise HTTPException(status_code=404, detail="Search not found")

        leads = (await db.execute(
            select(QualifiedLead)
            .where(QualifiedLead.search_id == search_id)
            .order_by(QualifiedLead.score.desc())
        )).scalars().all()

        return {
            "search": {
                "id": search.id,
                "industry": search.industry,
                "company_profile": search.company_profile,
                "technology_focus": search.technology_focus,
                "qualifying_criteria": search.qualifying_criteria,
                "disqualifiers": search.disqualifiers,
                "geographic_region": search.geographic_region,
                "country_code": search.country_code,
                "geo_bounds": search.geo_bounds,
                "map_bounds": search.map_bounds,
                "show_map": search.show_map,
                "total_found": search.total_found,
                "messages": search.messages,
                "created_at": search.created_at.isoformat() if search.created_at else None,
            },
            "leads": [
                {
                    "id": l.id,
                    "company_name": l.company_name,
                    "domain": l.domain,
                    "website_url": l.website_url,
                    "score": l.score,
                    "tier": l.tier,
                    "hardware_type": l.hardware_type,
                    "industry_category": l.industry_category,
                    "reasoning": l.reasoning,
                    "key_signals": l.key_signals,
                    "red_flags": l.red_flags,
                    "deep_research": l.deep_research,
                    "country": l.country,
                    "latitude": l.latitude,
                    "longitude": l.longitude,
                    "status": l.status,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in leads
            ],
        }


@app.post("/api/searches/{search_id}/rerun")
async def rerun_search(search_id: str, user=Depends(require_auth)):
    """Re-run a pipeline with the same configuration as an existing search.
    
    Clones the ICP context from the original search and creates a brand-new
    pipeline run (new search_id, new leads).  Returns the same shape as
    POST /api/pipeline/create.
    """
    from db import get_db as _get_db
    from db.models import Search

    async for db in _get_db():
        original = (await db.execute(
            select(Search)
            .where(Search.id == search_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not original:
            raise HTTPException(status_code=404, detail="Search not found")

        # Reconstruct the PipelineCreateRequest from stored data
        queries_ctx = original.queries_used if isinstance(original.queries_used, dict) else {}
        stored_mode = queries_ctx.get("_mode", "discover")
        # chat_pipeline / chat_session are functionally "discover" — map them
        mode = stored_mode if stored_mode in ("discover", "qualify_only") else "discover"
        pipeline_name = queries_ctx.get("_pipeline_name", original.industry or "Pipeline")

        search_context = SearchContext(
            industry=original.industry,
            company_profile=original.company_profile,
            technology_focus=original.technology_focus,
            qualifying_criteria=original.qualifying_criteria,
            disqualifiers=original.disqualifiers,
            geographic_region=queries_ctx.get("geographic_region"),
            geo_bounds=original.geo_bounds,
        )

        create_req = PipelineCreateRequest(
            name=f"{pipeline_name} (re-run)",
            mode=mode,
            search_context=search_context,
            geo_bounds=original.geo_bounds,
            options={"use_vision": True, "max_leads": 100},
        )

        # Delegate to the existing create_pipeline endpoint logic
        return await create_pipeline(create_req, user)


@app.get("/api/pipeline/active")
async def list_active_pipelines(user=Depends(require_auth)):
    """List all currently running pipelines for this user (in-memory state).
    
    Returns a list of pipeline snapshots with progress info.
    """
    from db import get_db as _get_db
    from db.models import Search

    active = []
    # Get all running pipelines from the manager
    for sid, run in pipeline_manager._runs.items():
        if run.status != "running":
            continue
        # Verify this run belongs to the requesting user
        async for db in _get_db():
            search = (await db.execute(
                select(Search)
                .where(Search.id == sid, Search.user_id == user.id)
            )).scalar_one_or_none()
            if search:
                queries_ctx = search.queries_used if isinstance(search.queries_used, dict) else {}
                active.append({
                    "id": sid,
                    "name": queries_ctx.get("_pipeline_name", search.industry or "Pipeline"),
                    "mode": queries_ctx.get("_mode", "discover"),
                    "status": run.status,
                    "processed": run.processed,
                    "total": run.total,
                    "industry": search.industry,
                    "technology_focus": search.technology_focus,
                    "created_at": search.created_at.isoformat() if search.created_at else None,
                })

    return active


@app.delete("/api/searches/{search_id}")
async def delete_search(search_id: str, user=Depends(require_auth)):
    """Delete a search and its leads."""
    from db import get_db as _get_db
    from db.models import Search

    async for db in _get_db():
        search = (await db.execute(
            select(Search)
            .where(Search.id == search_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not search:
            raise HTTPException(status_code=404, detail="Search not found")

        await db.delete(search)
        await db.commit()
        return {"ok": True}


@app.get("/api/leads")
async def list_leads(
    user=Depends(require_auth),
    tier: Optional[str] = None,
    sort: str = "score",
    order: str = "desc",
    search_id: Optional[str] = None,
):
    """List all user's leads across all searches."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact
    from sqlalchemy.orm import selectinload

    async for db in _get_db():
        query = (
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
            .options(selectinload(QualifiedLead.contacts))
        )

        if tier:
            query = query.where(QualifiedLead.tier == tier)
        if search_id:
            query = query.where(QualifiedLead.search_id == search_id)

        # Sort
        sort_col = getattr(QualifiedLead, sort, QualifiedLead.score)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

        leads = (await db.execute(query)).scalars().all()

        return [
            {
                "id": l.id,
                "search_id": l.search_id,
                "company_name": l.company_name,
                "domain": l.domain,
                "website_url": l.website_url,
                "score": l.score,
                "tier": l.tier,
                "hardware_type": l.hardware_type,
                "industry_category": l.industry_category,
                "reasoning": l.reasoning,
                "key_signals": l.key_signals,
                "red_flags": l.red_flags,
                "deep_research": l.deep_research,
                "country": l.country,
                "latitude": l.latitude,
                "longitude": l.longitude,
                "status": l.status,
                "notes": l.notes,
                "deal_value": l.deal_value,
                "contact_count": len(l.contacts) if l.contacts else 0,
                "status_changed_at": l.status_changed_at.isoformat() if l.status_changed_at else None,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ]


@app.get("/api/leads/geo")
async def leads_geo(user=Depends(require_auth)):
    """All leads with lat/lng coordinates for map plotting, grouped by hunt."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        leads = (await db.execute(
            select(QualifiedLead, Search.industry, Search.technology_focus, Search.created_at.label("search_date"))
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
            .where(QualifiedLead.latitude.isnot(None))
            .where(QualifiedLead.longitude.isnot(None))
        )).all()

        return [
            {
                "id": row[0].id,
                "search_id": row[0].search_id,
                "company_name": row[0].company_name,
                "domain": row[0].domain,
                "website_url": row[0].website_url,
                "score": row[0].score,
                "tier": row[0].tier,
                "country": row[0].country,
                "latitude": row[0].latitude,
                "longitude": row[0].longitude,
                "status": row[0].status,
                "hardware_type": row[0].hardware_type,
                "industry_category": row[0].industry_category,
                "reasoning": row[0].reasoning,
                "key_signals": row[0].key_signals or [],
                "red_flags": row[0].red_flags or [],
                "search_label": row[1] or row[2] or "Untitled Hunt",
                "search_date": row[3].isoformat() if row[3] else None,
            }
            for row in leads
        ]


# ──────────────────────────────────────────────
# Search Within Database
# ──────────────────────────────────────────────

@app.get("/api/leads/search")
async def search_leads(
    q: str,
    tier: Optional[str] = None,
    user=Depends(require_auth),
):
    """Search across stored leads by company name, domain, industry, signals."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead
    from sqlalchemy import or_

    async for db in _get_db():
        query = (
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
        )

        # Text search across multiple columns
        search_term = f"%{q}%"
        query = query.where(
            or_(
                QualifiedLead.company_name.ilike(search_term),
                QualifiedLead.domain.ilike(search_term),
                QualifiedLead.industry_category.ilike(search_term),
                QualifiedLead.hardware_type.ilike(search_term),
                QualifiedLead.reasoning.ilike(search_term),
                QualifiedLead.country.ilike(search_term),
            )
        )

        if tier:
            query = query.where(QualifiedLead.tier == tier)

        query = query.order_by(QualifiedLead.score.desc()).limit(100)
        leads = (await db.execute(query)).scalars().all()

        return [
            {
                "id": l.id,
                "company_name": l.company_name,
                "domain": l.domain,
                "website_url": l.website_url,
                "score": l.score,
                "tier": l.tier,
                "hardware_type": l.hardware_type,
                "industry_category": l.industry_category,
                "reasoning": l.reasoning,
                "country": l.country,
                "status": l.status,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ]


# ──────────────────────────────────────────────
# Export Leads as CSV
# ──────────────────────────────────────────────

@app.get("/api/leads/export")
async def export_all_leads(
    user=Depends(require_auth),
    tier: str | None = None,
    search_id: str | None = None,
):
    """Export user's leads as CSV with optional tier/search_id filter."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact
    from fastapi.responses import Response
    from datetime import datetime as _dt
    import csv
    import io

    async for db in _get_db():
        query = (
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
        )
        if tier and tier in ("hot", "review", "rejected"):
            query = query.where(QualifiedLead.tier == tier)
        if search_id:
            query = query.where(QualifiedLead.search_id == search_id)
        query = query.order_by(QualifiedLead.score.desc())
        leads = (await db.execute(query)).scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Company Name", "Domain", "Website", "Score", "Tier",
            "Industry", "Product Type", "Reasoning", "Key Signals", "Red Flags",
            "Country", "Status", "Notes", "Deal Value",
            "Contact Names", "Contact Emails", "Contact Titles",
            "Created At", "Last Seen At",
        ])

        for lead in leads:
            # Get contacts for this lead
            contacts = (await db.execute(
                select(LeadContact).where(LeadContact.lead_id == lead.id)
            )).scalars().all()

            names = "; ".join(c.full_name for c in contacts if c.full_name)
            emails = "; ".join(c.email for c in contacts if c.email)
            titles = "; ".join(c.job_title for c in contacts if c.job_title)

            signals = "; ".join(lead.key_signals) if lead.key_signals else ""
            flags = "; ".join(lead.red_flags) if lead.red_flags else ""

            writer.writerow([
                lead.company_name, lead.domain, lead.website_url,
                lead.score, lead.tier,
                lead.industry_category or "", lead.hardware_type or "",
                lead.reasoning, signals, flags,
                lead.country or "", lead.status or "new",
                lead.notes or "", lead.deal_value or "",
                names, emails, titles,
                lead.created_at.isoformat() if lead.created_at else "",
                lead.last_seen_at.isoformat() if lead.last_seen_at else "",
            ])

        csv_content = output.getvalue()

        parts = ["leads"]
        if tier:
            parts.append(tier)
        if search_id:
            parts.append(search_id[:8])
        parts.append(_dt.now().strftime("%Y-%m-%d"))
        filename = "_".join(parts) + ".csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str, user=Depends(require_auth)):
    """Single lead with full detail."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, EnrichmentResult_, LeadContact

    async for db in _get_db():
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Get enrichment if exists
        enrichment = (await db.execute(
            select(EnrichmentResult_).where(EnrichmentResult_.lead_id == lead_id)
        )).scalar_one_or_none()

        # Get contacts
        contacts = (await db.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
            .order_by(LeadContact.created_at)
        )).scalars().all()

        result = {
            "id": lead.id,
            "search_id": lead.search_id,
            "company_name": lead.company_name,
            "domain": lead.domain,
            "website_url": lead.website_url,
            "score": lead.score,
            "tier": lead.tier,
            "hardware_type": lead.hardware_type,
            "industry_category": lead.industry_category,
            "reasoning": lead.reasoning,
            "key_signals": lead.key_signals,
            "red_flags": lead.red_flags,
            "deep_research": lead.deep_research,
            "country": lead.country,
            "latitude": lead.latitude,
            "longitude": lead.longitude,
            "status": lead.status,
            "notes": lead.notes,
            "deal_value": lead.deal_value,
            "status_changed_at": lead.status_changed_at.isoformat() if lead.status_changed_at else None,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "last_seen_at": lead.last_seen_at.isoformat() if lead.last_seen_at else None,
        }

        if enrichment:
            result["enrichment"] = {
                "email": enrichment.email,
                "phone": enrichment.phone,
                "job_title": enrichment.job_title,
                "source": enrichment.source,
            }

        if contacts:
            result["contacts"] = [
                {
                    "id": c.id,
                    "full_name": c.full_name,
                    "job_title": c.job_title,
                    "email": c.email,
                    "phone": c.phone,
                    "linkedin_url": c.linkedin_url,
                    "source": c.source,
                }
                for c in contacts
            ]

        return result


class UpdateLeadStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(new|contacted|in_progress|won|lost|archived)$")
    notes: Optional[str] = None
    deal_value: Optional[float] = None


@app.patch("/api/leads/{lead_id}/status")
async def update_lead_status(lead_id: str, request: UpdateLeadStatusRequest, user=Depends(require_auth)):
    """Update a lead's pipeline status."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        if lead.status != request.status:
            lead.status = request.status
            lead.status_changed_at = datetime.now(timezone.utc)
        if request.notes is not None:
            lead.notes = request.notes
        if request.deal_value is not None:
            lead.deal_value = request.deal_value
        await db.commit()
        return {
            "ok": True,
            "status": lead.status,
            "notes": lead.notes,
            "deal_value": lead.deal_value,
            "status_changed_at": lead.status_changed_at.isoformat() if lead.status_changed_at else None,
        }


@app.delete("/api/leads/{lead_id}")
async def delete_lead(lead_id: str, user=Depends(require_auth)):
    """Delete a single lead."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        await db.delete(lead)
        await db.commit()
        return {"ok": True}


# ──────────────────────────────────────────────
# Lead Contacts Endpoints
# ──────────────────────────────────────────────

@app.get("/api/leads/{lead_id}/contacts")
async def get_lead_contacts(lead_id: str, user=Depends(require_auth)):
    """Get all contacts (people) for a lead."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact

    async for db in _get_db():
        # Verify lead belongs to user
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        contacts = (await db.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
            .order_by(LeadContact.created_at)
        )).scalars().all()

        return [
            {
                "id": c.id,
                "full_name": c.full_name,
                "job_title": c.job_title,
                "email": c.email,
                "phone": c.phone,
                "linkedin_url": c.linkedin_url,
                "source": c.source,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in contacts
        ]


# ──────────────────────────────────────────────
# LinkedIn Enrichment Endpoint
# ──────────────────────────────────────────────

@app.post("/api/leads/{lead_id}/linkedin")
async def linkedin_enrich_lead(lead_id: str, user=Depends(require_auth)):
    """Find decision-makers for a lead via People Data Labs / RocketReach."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact, Profile
    from usage import check_quota, increment_usage

    li_status = get_linkedin_status()
    if not li_status["available"]:
        raise HTTPException(status_code=400, detail="No LinkedIn enrichment API configured. Add PDL_API_KEY or ROCKETREACH_API_KEY.")

    async for db in _get_db():
        # Verify lead belongs to user
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Check quota
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        if plan == "free":
            raise HTTPException(status_code=403, detail="LinkedIn enrichment requires Pro or Enterprise plan")

        # Check linkedin_lookups limit
        from usage import PLAN_LIMITS
        linkedin_limits = {"free": 0, "pro": 50, "enterprise": 500}
        from usage import _get_or_create_row
        usage_row = await _get_or_create_row(db, user.id)
        limit = linkedin_limits.get(plan, 0)
        if limit and usage_row.linkedin_lookups >= limit:
            raise HTTPException(status_code=429, detail=f"LinkedIn lookup limit reached ({limit}/month)")

        # Perform lookup
        contacts = await enrich_linkedin(lead.domain, max_results=5)

        if not contacts:
            return {"contacts": [], "message": "No decision-makers found"}

        # Save to DB (dedup by email)
        existing_emails = set()
        existing_contacts = (await db.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )).scalars().all()
        for ec in existing_contacts:
            if ec.email:
                existing_emails.add(ec.email.lower())

        saved = []
        for c in contacts:
            if c.email and c.email.lower() in existing_emails:
                continue
            lc = LeadContact(
                lead_id=lead_id,
                full_name=c.full_name,
                job_title=c.job_title,
                email=c.email,
                phone=c.phone,
                linkedin_url=c.linkedin_url,
                source=c.source,
            )
            db.add(lc)
            saved.append({
                "full_name": c.full_name,
                "job_title": c.job_title,
                "email": c.email,
                "phone": c.phone,
                "linkedin_url": c.linkedin_url,
                "source": c.source,
            })

        # Increment usage
        usage_row.linkedin_lookups += 1
        await db.commit()

        return {"contacts": saved, "total_found": len(contacts), "new_saved": len(saved)}


# ──────────────────────────────────────────────
# Lead Re-crawl / Re-qualify Endpoint
# ──────────────────────────────────────────────

class RecrawlRequest(BaseModel):
    """Options for re-crawling a lead."""
    action: str = Field(
        "recrawl_contacts",
        description="One of: recrawl_contacts, requalify, full_recrawl",
    )

@app.post("/api/leads/{lead_id}/recrawl")
async def recrawl_lead(lead_id: str, body: RecrawlRequest, user=Depends(require_auth)):
    """Re-crawl a single lead's website to find contacts, re-qualify, or both.

    Actions:
      - recrawl_contacts: Re-crawl the website + contact/about pages and
        extract contacts via LLM.  Keeps existing contacts, de-dupes by email.
      - requalify: Re-crawl and re-run the qualification LLM to update
        score, tier, signals, reasoning.
      - full_recrawl: Does both — re-qualify + re-extract contacts.
    """
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact
    from scraper import CrawlerPool, crawl_company
    from intelligence import LeadQualifier
    from utils import determine_tier

    if body.action not in ("recrawl_contacts", "requalify", "full_recrawl"):
        raise HTTPException(status_code=400, detail="Invalid action. Use: recrawl_contacts, requalify, full_recrawl")

    async for db in _get_db():
        # Verify lead belongs to user
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        search = (await db.execute(
            select(Search).where(Search.id == lead.search_id)
        )).scalar_one_or_none()

        url = lead.website_url or f"https://{lead.domain}"
        domain = lead.domain

        # ── Crawl the website ──
        try:
            async with CrawlerPool() as pool:
                crawl_result = await crawl_company(
                    url,
                    take_screenshot=False,
                    crawler_pool=pool,
                )

                contact_content = ""
                if crawl_result.success and crawl_result.markdown_content:
                    contact_content = crawl_result.markdown_content

                # Also crawl /contact, /about, /team pages
                try:
                    contact_snippet = await pool.crawl_contact_pages(url)
                    if contact_snippet:
                        contact_content += (
                            "\n\n=== ADDRESS & CONTACT INFO FROM OTHER PAGES ===\n"
                            + contact_snippet
                        )
                except Exception as e:
                    logger.debug("Contact page crawl failed for %s: %s", domain, e)

        except Exception as e:
            logger.error("Re-crawl failed for %s: %s", domain, e)
            raise HTTPException(status_code=500, detail=f"Crawl failed: {str(e)[:200]}")

        result: dict = {"domain": domain, "actions_completed": []}

        # ── Re-qualify if requested ──
        if body.action in ("requalify", "full_recrawl"):
            try:
                search_ctx = None
                if search:
                    search_ctx = {
                        "industry": search.industry,
                        "company_profile": search.company_profile,
                        "technology_focus": search.technology_focus,
                        "qualifying_criteria": search.qualifying_criteria,
                        "disqualifiers": search.disqualifiers,
                    }

                qualifier = LeadQualifier(search_context=search_ctx)
                from scraper import CrawlResult
                cr = CrawlResult(
                    url=url,
                    success=bool(contact_content),
                    markdown_content=contact_content or "",
                    title=lead.company_name,
                )
                qual_result = await qualifier.qualify_lead(
                    company_name=lead.company_name,
                    website_url=url,
                    crawl_result=cr,
                    use_vision=False,
                )
                new_tier = determine_tier(qual_result.confidence_score)

                lead.score = qual_result.confidence_score
                lead.tier = new_tier.value
                lead.reasoning = qual_result.reasoning
                lead.key_signals = json.dumps(qual_result.key_signals) if qual_result.key_signals else None
                lead.red_flags = json.dumps(qual_result.red_flags) if qual_result.red_flags else None
                lead.hardware_type = qual_result.hardware_type
                lead.industry_category = qual_result.industry_category

                result["new_score"] = qual_result.confidence_score
                result["new_tier"] = new_tier.value
                result["reasoning"] = qual_result.reasoning
                result["key_signals"] = qual_result.key_signals
                result["red_flags"] = qual_result.red_flags
                result["actions_completed"].append("requalify")
            except Exception as e:
                logger.error("Re-qualify failed for %s: %s", domain, e, exc_info=True)
                result["requalify_error"] = str(e)[:200]

        # ── Re-extract contacts if requested ──
        if body.action in ("recrawl_contacts", "full_recrawl") and contact_content:
            try:
                people = await extract_contacts_from_content(
                    company_name=lead.company_name,
                    domain=domain,
                    page_content=contact_content,
                )

                # De-dup against existing contacts
                existing_contacts = (await db.execute(
                    select(LeadContact).where(LeadContact.lead_id == lead_id)
                )).scalars().all()
                existing_emails = {c.email.lower() for c in existing_contacts if c.email}
                existing_names = {c.full_name.lower() for c in existing_contacts if c.full_name}

                new_contacts = []
                for p in people:
                    if p.email and p.email.lower() in existing_emails:
                        continue
                    if not p.email and p.full_name and p.full_name.lower() in existing_names:
                        continue
                    lc = LeadContact(
                        lead_id=lead_id,
                        full_name=p.full_name,
                        job_title=p.job_title,
                        email=p.email,
                        phone=p.phone,
                        linkedin_url=p.linkedin_url,
                        source="website_recrawl",
                    )
                    db.add(lc)
                    new_contacts.append({
                        "full_name": p.full_name,
                        "job_title": p.job_title,
                        "email": p.email,
                        "phone": p.phone,
                        "linkedin_url": p.linkedin_url,
                        "source": "website_recrawl",
                    })

                result["new_contacts"] = new_contacts
                result["total_contacts_found"] = len(people)
                result["actions_completed"].append("recrawl_contacts")
            except Exception as e:
                logger.error("Contact extraction failed for %s: %s", domain, e, exc_info=True)
                result["contacts_error"] = str(e)[:200]
        elif body.action in ("recrawl_contacts", "full_recrawl"):
            result["contacts_error"] = "Could not extract page content from website"

        lead.last_seen_at = datetime.now(timezone.utc)
        await db.commit()

        # Refresh contacts list to return all contacts
        all_contacts = (await db.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )).scalars().all()
        result["contacts"] = [
            {
                "id": c.id,
                "full_name": c.full_name,
                "job_title": c.job_title,
                "email": c.email,
                "phone": c.phone,
                "linkedin_url": c.linkedin_url,
                "source": c.source,
            }
            for c in all_contacts
        ]

        return result


# ──────────────────────────────────────────────
# Batch Enrichment / Re-crawl Jobs
# ──────────────────────────────────────────────

class BatchEnrichRequest(BaseModel):
    """Start a batch enrichment job."""
    lead_ids: list[str] = Field(..., min_length=1, max_length=200)
    action: str = Field(
        "recrawl_contacts",
        description="recrawl_contacts | requalify | full_recrawl | linkedin",
    )


# In-memory SSE for enrichment jobs (mirrors PipelineRun pattern)
class EnrichmentJobRun:
    """In-memory SSE state for a running enrichment job."""

    def __init__(self, job_id: str, total: int):
        self.job_id = job_id
        self.total = total
        self.events: list[dict] = []
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self.created_at = time.time()

    async def emit(self, event: dict):
        async with self._lock:
            self.events.append(event)
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    async def subscribe(self, after: int = 0):
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            for ev in self.events[after:]:
                yield ev
            if any(ev.get("type") == "complete" for ev in self.events):
                return
            self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
                if event.get("type") == "complete":
                    return
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


_enrichment_runs: dict[str, EnrichmentJobRun] = {}
_enrichment_tasks: dict[str, asyncio.Task] = {}


async def _run_batch_enrichment(job_id: str, user_id: str, lead_ids: list[str], action: str):
    """Background task: process each lead and emit SSE events."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact, EnrichmentJob
    from scraper import CrawlerPool, crawl_company
    from intelligence import LeadQualifier
    from utils import determine_tier

    run = _enrichment_runs.get(job_id)
    if not run:
        return

    total = len(lead_ids)
    results: list[dict] = []
    succeeded = 0
    failed = 0

    try:
        async for db in _get_db():
            # Mark job as running in DB
            job = (await db.execute(
                select(EnrichmentJob).where(EnrichmentJob.id == job_id)
            )).scalar_one_or_none()
            if job:
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                await db.commit()

            await run.emit({"type": "init", "total": total, "action": action, "job_id": job_id})

            for i, lead_id in enumerate(lead_ids):
                lead_result: dict = {"lead_id": lead_id, "index": i}
                try:
                    # Fetch lead
                    lead = (await db.execute(
                        select(QualifiedLead)
                        .join(Search, QualifiedLead.search_id == Search.id)
                        .where(QualifiedLead.id == lead_id, Search.user_id == user_id)
                    )).scalar_one_or_none()

                    if not lead:
                        lead_result["status"] = "skipped"
                        lead_result["message"] = "Not found or not owned"
                        failed += 1
                        results.append(lead_result)
                        await run.emit({"type": "progress", "index": i, "total": total, "lead_id": lead_id,
                                        "status": "skipped", "company": "Unknown"})
                        continue

                    await run.emit({
                        "type": "progress", "index": i, "total": total,
                        "lead_id": lead_id, "status": "processing",
                        "company": lead.company_name, "domain": lead.domain,
                    })

                    url = lead.website_url or f"https://{lead.domain}"
                    domain = lead.domain

                    if action == "linkedin":
                        # LinkedIn enrichment
                        try:
                            li_result = await enrich_linkedin(lead.company_name, lead.domain)
                            if li_result and li_result.get("contacts"):
                                existing = (await db.execute(
                                    select(LeadContact).where(LeadContact.lead_id == lead_id)
                                )).scalars().all()
                                existing_emails = {c.email.lower() for c in existing if c.email}
                                new_count = 0
                                for c in li_result["contacts"]:
                                    if c.get("email") and c["email"].lower() in existing_emails:
                                        continue
                                    db.add(LeadContact(
                                        lead_id=lead_id,
                                        full_name=c.get("full_name"),
                                        job_title=c.get("job_title"),
                                        email=c.get("email"),
                                        phone=c.get("phone"),
                                        linkedin_url=c.get("linkedin_url"),
                                        source="linkedin",
                                    ))
                                    new_count += 1
                                lead_result["new_contacts"] = new_count
                                lead_result["message"] = f"{new_count} new contacts"
                            else:
                                lead_result["message"] = "No contacts found"
                            lead_result["status"] = "success"
                            succeeded += 1
                        except Exception as e:
                            lead_result["status"] = "error"
                            lead_result["message"] = str(e)[:200]
                            failed += 1
                    else:
                        # Crawl-based actions
                        try:
                            async with CrawlerPool() as pool:
                                crawl_result = await crawl_company(url, take_screenshot=False, crawler_pool=pool)
                                contact_content = ""
                                if crawl_result.success and crawl_result.markdown_content:
                                    contact_content = crawl_result.markdown_content
                                try:
                                    contact_snippet = await pool.crawl_contact_pages(url)
                                    if contact_snippet:
                                        contact_content += "\n\n=== CONTACT PAGES ===\n" + contact_snippet
                                except Exception:
                                    pass

                            # Re-qualify
                            if action in ("requalify", "full_recrawl"):
                                search = (await db.execute(
                                    select(Search).where(Search.id == lead.search_id)
                                )).scalar_one_or_none()
                                search_ctx = None
                                if search:
                                    search_ctx = {
                                        "industry": search.industry,
                                        "company_profile": search.company_profile,
                                        "technology_focus": search.technology_focus,
                                        "qualifying_criteria": search.qualifying_criteria,
                                        "disqualifiers": search.disqualifiers,
                                    }
                                qualifier = LeadQualifier(search_context=search_ctx)
                                from scraper import CrawlResult as _CrawlResult
                                cr = _CrawlResult(
                                    url=url, success=bool(contact_content),
                                    markdown_content=contact_content or "", title=lead.company_name,
                                )
                                qual_result = await qualifier.qualify_lead(
                                    company_name=lead.company_name, website_url=url,
                                    crawl_result=cr, use_vision=False,
                                )
                                new_tier = determine_tier(qual_result.confidence_score)
                                lead.score = qual_result.confidence_score
                                lead.tier = new_tier.value
                                lead.reasoning = qual_result.reasoning
                                lead.key_signals = json.dumps(qual_result.key_signals) if qual_result.key_signals else None
                                lead.red_flags = json.dumps(qual_result.red_flags) if qual_result.red_flags else None
                                lead.hardware_type = qual_result.hardware_type
                                lead.industry_category = qual_result.industry_category
                                lead_result["new_score"] = qual_result.confidence_score
                                lead_result["new_tier"] = new_tier.value

                            # Re-extract contacts
                            if action in ("recrawl_contacts", "full_recrawl") and contact_content:
                                people = await extract_contacts_from_content(
                                    company_name=lead.company_name, domain=domain,
                                    page_content=contact_content,
                                )
                                existing = (await db.execute(
                                    select(LeadContact).where(LeadContact.lead_id == lead_id)
                                )).scalars().all()
                                existing_emails = {c.email.lower() for c in existing if c.email}
                                existing_names = {c.full_name.lower() for c in existing if c.full_name}
                                new_count = 0
                                for p in people:
                                    if p.email and p.email.lower() in existing_emails:
                                        continue
                                    if not p.email and p.full_name and p.full_name.lower() in existing_names:
                                        continue
                                    db.add(LeadContact(
                                        lead_id=lead_id,
                                        full_name=p.full_name, job_title=p.job_title,
                                        email=p.email, phone=p.phone,
                                        linkedin_url=p.linkedin_url, source="website_recrawl",
                                    ))
                                    new_count += 1
                                lead_result["new_contacts"] = new_count

                            lead.last_seen_at = datetime.now(timezone.utc)
                            lead_result["status"] = "success"
                            lead_result["message"] = "Done"
                            succeeded += 1
                        except Exception as e:
                            lead_result["status"] = "error"
                            lead_result["message"] = str(e)[:200]
                            failed += 1

                    results.append(lead_result)
                    await db.commit()

                    await run.emit({
                        "type": "result", "index": i, "total": total,
                        "lead_id": lead_id, "company": lead.company_name if lead else "Unknown",
                        "domain": lead.domain if lead else "",
                        **lead_result,
                    })

                except Exception as e:
                    logger.error("Batch enrichment error for lead %s: %s", lead_id, e, exc_info=True)
                    lead_result["status"] = "error"
                    lead_result["message"] = str(e)[:200]
                    failed += 1
                    results.append(lead_result)
                    await run.emit({
                        "type": "result", "index": i, "total": total,
                        "lead_id": lead_id, "status": "error", "message": str(e)[:200],
                    })

            # Update job in DB
            job = (await db.execute(
                select(EnrichmentJob).where(EnrichmentJob.id == job_id)
            )).scalar_one_or_none()
            if job:
                job.status = "complete"
                job.processed = total
                job.succeeded = succeeded
                job.failed = failed
                job.results = results
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()

            await run.emit({
                "type": "complete", "job_id": job_id,
                "total": total, "succeeded": succeeded, "failed": failed,
            })

    except Exception as e:
        logger.error("Fatal batch enrichment error for job %s: %s", job_id, e, exc_info=True)
        try:
            async for db in _get_db():
                job = (await db.execute(
                    select(EnrichmentJob).where(EnrichmentJob.id == job_id)
                )).scalar_one_or_none()
                if job:
                    job.status = "error"
                    job.error = str(e)[:500]
                    job.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
        if run:
            await run.emit({"type": "complete", "job_id": job_id, "error": str(e)[:200],
                            "total": total, "succeeded": succeeded, "failed": failed})


@app.post("/api/leads/batch-enrich")
async def start_batch_enrichment(body: BatchEnrichRequest, user=Depends(require_auth)):
    """Start a batch enrichment job. Returns job_id for SSE streaming."""
    from db import get_db as _get_db
    from db.models import EnrichmentJob

    if body.action not in ("recrawl_contacts", "requalify", "full_recrawl", "linkedin"):
        raise HTTPException(status_code=400, detail="Invalid action")

    async for db in _get_db():
        job = EnrichmentJob(
            user_id=user.id,
            action=body.action,
            status="pending",
            lead_ids=body.lead_ids,
            total=len(body.lead_ids),
        )
        db.add(job)
        await db.commit()
        job_id = job.id

    # Create in-memory run
    run = EnrichmentJobRun(job_id, len(body.lead_ids))
    _enrichment_runs[job_id] = run

    # Launch background task
    task = asyncio.create_task(
        _run_batch_enrichment(job_id, user.id, body.lead_ids, body.action)
    )
    _enrichment_tasks[job_id] = task
    task.add_done_callback(lambda _t: _enrichment_tasks.pop(job_id, None))

    return {"job_id": job_id, "total": len(body.lead_ids), "action": body.action}


@app.get("/api/leads/enrich-jobs")
async def list_enrichment_jobs(user=Depends(require_auth)):
    """List recent enrichment jobs for this user."""
    from db import get_db as _get_db
    from db.models import EnrichmentJob

    async for db in _get_db():
        jobs = (await db.execute(
            select(EnrichmentJob)
            .where(EnrichmentJob.user_id == user.id)
            .order_by(EnrichmentJob.created_at.desc())
            .limit(20)
        )).scalars().all()

        return [
            {
                "id": j.id,
                "action": j.action,
                "status": j.status,
                "total": j.total,
                "processed": j.processed,
                "succeeded": j.succeeded,
                "failed": j.failed,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]


@app.get("/api/leads/enrich-jobs/{job_id}")
async def get_enrichment_job(job_id: str, user=Depends(require_auth)):
    """Get enrichment job status + results."""
    from db import get_db as _get_db
    from db.models import EnrichmentJob

    async for db in _get_db():
        job = (await db.execute(
            select(EnrichmentJob)
            .where(EnrichmentJob.id == job_id, EnrichmentJob.user_id == user.id)
        )).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "id": job.id,
            "action": job.action,
            "status": job.status,
            "total": job.total,
            "processed": job.processed,
            "succeeded": job.succeeded,
            "failed": job.failed,
            "results": job.results,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }


@app.get("/api/leads/enrich-jobs/{job_id}/stream")
async def stream_enrichment_job(job_id: str, request: Request, user=Depends(require_auth)):
    """SSE stream for enrichment job progress. Reconnectable via ?after=N."""
    from db import get_db as _get_db
    from db.models import EnrichmentJob

    # Verify ownership
    async for db in _get_db():
        job = (await db.execute(
            select(EnrichmentJob)
            .where(EnrichmentJob.id == job_id, EnrichmentJob.user_id == user.id)
        )).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # If job completed and no in-memory run, return completed status from DB
        if job.status in ("complete", "error") and job_id not in _enrichment_runs:
            async def _completed_stream():
                data = json.dumps({
                    "type": "complete", "job_id": job_id,
                    "total": job.total, "succeeded": job.succeeded,
                    "failed": job.failed, "results": job.results,
                })
                yield f"data: {data}\n\n"
            return StreamingResponse(
                _completed_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )

    run = _enrichment_runs.get(job_id)
    if not run:
        raise HTTPException(status_code=404, detail="Job stream not available — job may have completed before server restart")

    after = int(request.query_params.get("after", "0"))

    async def _event_stream():
        async for event in run.subscribe(after):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────
# Search Templates CRUD
# ──────────────────────────────────────────────

@app.get("/api/templates")
async def list_templates(user=Depends(require_auth)):
    """List user's saved search templates."""
    from db import get_db as _get_db
    from db.models import SearchTemplate

    async for db in _get_db():
        templates = (await db.execute(
            select(SearchTemplate)
            .where(SearchTemplate.user_id == user.id)
            .order_by(SearchTemplate.updated_at.desc())
        )).scalars().all()

        return [
            {
                "id": t.id,
                "name": t.name,
                "search_context": t.search_context,
                "is_builtin": t.is_builtin,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in templates
        ]


@app.post("/api/templates")
async def create_template(request: TemplateCreate, user=Depends(require_auth)):
    """Save current search context as a named template."""
    from db import get_db as _get_db
    from db.models import SearchTemplate

    async for db in _get_db():
        await _ensure_profile_exists(db, user.id)

        template = SearchTemplate(
            user_id=user.id,
            name=request.name,
            search_context=request.search_context,
        )
        db.add(template)
        await db.commit()

        return {
            "id": template.id,
            "name": template.name,
            "search_context": template.search_context,
            "created_at": template.created_at.isoformat() if template.created_at else None,
        }


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(require_auth)):
    """Delete a search template."""
    from db import get_db as _get_db
    from db.models import SearchTemplate

    async for db in _get_db():
        template = (await db.execute(
            select(SearchTemplate)
            .where(SearchTemplate.id == template_id, SearchTemplate.user_id == user.id)
        )).scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        await db.delete(template)
        await db.commit()
        return {"ok": True}


# ──────────────────────────────────────────────
# Bulk Domain Import
# ──────────────────────────────────────────────

@app.post("/api/pipeline/bulk")
async def bulk_import(request: BulkImportRequest, user=Depends(require_auth)):
    """
    Bulk domain import — paste domains → qualify all.
    Skips the chat flow. Streams SSE like the regular pipeline.
    """
    from usage import check_quota, increment_usage, LEADS_PER_HUNT
    from db import get_db as _get_db
    from db.models import Profile

    # Clean and deduplicate domains
    domains = []
    seen = set()
    for d in request.domains:
        d = d.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if d and d not in seen and "." in d:
            seen.add(d)
            domains.append(d)

    if not domains:
        raise HTTPException(status_code=400, detail="No valid domains provided")

    # Quota check
    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        max_leads = LEADS_PER_HUNT.get(plan, 25)
        domains = domains[:max_leads]

        exceeded = await check_quota(db, user.id, plan_tier=plan, action="leads", count=len(domains))
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        exceeded = await check_quota(db, user.id, plan_tier=plan, action="search")
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        await increment_usage(db, user.id, leads_qualified=len(domains), searches_run=1)

    search_ctx = request.search_context.model_dump() if request.search_context else None
    use_vision = request.use_vision

    async def generate():
        from scraper import CrawlerPool, crawl_company
        from intelligence import LeadQualifier
        from utils import determine_tier, extract_domain

        total = len(domains)
        yield sse_event({"type": "init", "total": total})

        qualifier = LeadQualifier(search_context=search_ctx)
        stats = {"hot": 0, "review": 0, "rejected": 0, "failed": 0}
        _geo_hit_count: dict[tuple[float, float], int] = {}

        def _spread_co_located(lat, lng):
            if lat is None or lng is None:
                return lat, lng
            key = (round(lat, 6), round(lng, 6))
            n = _geo_hit_count.get(key, 0)
            _geo_hit_count[key] = n + 1
            if n == 0:
                return lat, lng
            angle = n * 2.399_963
            r = 0.0012 * math.sqrt(n)
            return lat + r * math.cos(angle), lng + r * math.sin(angle)

        # Save search
        search_id = None
        try:
            ctx = search_ctx or {}
            ctx["_bulk_import"] = True
            search_id = await _save_search_to_db(
                user_id=user.id,
                context=ctx,
                queries=[],
                total_found=total,
                messages=[{"role": "system", "content": f"Bulk import of {total} domains"}],
            )
        except Exception as e:
            logger.error("Failed to save bulk search: %s", e, exc_info=True)

        try:
            async with CrawlerPool() as pool:
                for i, domain in enumerate(domains):
                    title = domain.split(".")[0].replace("-", " ").title()
                    url = f"https://{domain}"

                    try:
                        yield sse_event({
                            "type": "progress",
                            "index": i, "total": total,
                            "phase": "crawling",
                            "company": {"title": title, "domain": domain},
                        })

                        crawl_result = await crawl_company(url, take_screenshot=use_vision, crawler_pool=pool)

                        if crawl_result.success and crawl_result.markdown_content:
                            try:
                                contact_snippet = await pool.crawl_contact_pages(url)
                                if contact_snippet:
                                    crawl_result = crawl_result.model_copy(update={
                                        "markdown_content": crawl_result.markdown_content
                                        + "\n\n=== ADDRESS & CONTACT INFO FROM OTHER PAGES ===\n"
                                        + contact_snippet
                                    })
                            except Exception:
                                pass

                            # Extract title from crawl
                            if crawl_result.title:
                                title = crawl_result.title.split("|")[0].split("-")[0].strip()[:80] or title

                        if not crawl_result.success:
                            c = _guess_country_from_domain(domain)
                            lat, lng = None, None
                            if c:
                                geo = await _geocode_location(c)
                                if geo:
                                    _, lat, lng = geo
                            lat, lng = _spread_co_located(lat, lng)
                            result_data = {
                                "title": title, "domain": domain, "url": url,
                                "score": 5, "tier": "review",
                                "reasoning": f"Website could not be crawled — {_sanitize_crawl_error(crawl_result.error_message)}. Visit the site manually to verify.",
                                "key_signals": [], "red_flags": ["Crawl failed — needs manual review"],
                                "country": c, "latitude": lat, "longitude": lng,
                            }
                            stats["review"] += 1
                            yield sse_event({"type": "result", "index": i, "total": total, "company": result_data})
                            if search_id:
                                try:
                                    await _save_lead_to_db(search_id, result_data, user_id=user.id)
                                except Exception:
                                    pass
                            continue

                        yield sse_event({
                            "type": "progress",
                            "index": i, "total": total,
                            "phase": "qualifying",
                            "company": {"title": title, "domain": domain},
                        })

                        qual_result = await qualifier.qualify_lead(
                            company_name=title, website_url=url,
                            crawl_result=crawl_result, use_vision=use_vision,
                        )
                        tier = determine_tier(qual_result.confidence_score)

                        # Geocode
                        hq = qual_result.headquarters_location
                        country, latitude, longitude = None, None, None
                        if hq:
                            geo = await _geocode_location(hq)
                            if geo:
                                country, latitude, longitude = geo
                        if not country:
                            dc = _guess_country_from_domain(domain)
                            if dc:
                                country = dc
                                geo = await _geocode_location(dc)
                                if geo:
                                    _, latitude, longitude = geo
                        latitude, longitude = _spread_co_located(latitude, longitude)

                        # Extract contacts
                        extracted_contacts = []
                        try:
                            people = await extract_contacts_from_content(title, domain, crawl_result.markdown_content or "")
                            extracted_contacts = [
                                {"full_name": p.full_name, "job_title": p.job_title, "email": p.email,
                                 "phone": p.phone, "linkedin_url": p.linkedin_url, "source": "website"}
                                for p in people
                            ]
                        except Exception:
                            pass

                        result_data = {
                            "title": title, "domain": domain, "url": url,
                            "score": qual_result.confidence_score, "tier": tier.value,
                            "hardware_type": qual_result.hardware_type,
                            "industry_category": qual_result.industry_category,
                            "reasoning": qual_result.reasoning,
                            "key_signals": qual_result.key_signals,
                            "red_flags": qual_result.red_flags,
                            "country": country, "latitude": latitude, "longitude": longitude,
                            "contacts": extracted_contacts,
                        }
                        stats[tier.value] += 1

                        yield sse_event({"type": "result", "index": i, "total": total, "company": result_data})

                        if search_id:
                            try:
                                await _save_lead_to_db(search_id, result_data, user_id=user.id, contacts=extracted_contacts)
                            except Exception:
                                pass

                    except Exception as e:
                        stats["failed"] += 1
                        yield sse_event({
                            "type": "error", "index": i, "total": total,
                            "company": {"title": title, "domain": domain},
                            "error": str(e)[:200],
                        })

        except Exception as e:
            yield sse_event({"type": "error", "error": str(e)[:200], "fatal": True})
            return

        yield sse_event({"type": "complete", "summary": stats, "search_id": search_id})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────
# LinkedIn enrichment status (health)
# ──────────────────────────────────────────────

@app.get("/api/linkedin/status")
async def linkedin_status(user=Depends(require_auth)):
    """Check if LinkedIn enrichment APIs are configured."""
    return get_linkedin_status()

async def _ensure_profile_exists(db, user_id: str, email: str = None) -> None:
    """Ensure a profile row exists for this user. Creates one if missing.
    
    This is a safety net for cases where the Supabase trigger didn't fire
    (e.g. user signed up before the trigger was created, or the trigger failed).
    """
    from db.models import Profile
    profile = (await db.execute(
        select(Profile).where(Profile.id == user_id)
    )).scalar_one_or_none()
    if profile is None:
        logger.info("Auto-creating missing profile for user %s", user_id)
        profile = Profile(
            id=user_id,
            email=email,
            plan_tier="free",
            plan="free",
        )
        db.add(profile)
        await db.flush()


async def _save_search_to_db(user_id: str, context: dict, queries: list, total_found: int, messages: Optional[list] = None) -> str:
    """Save a search session to the database. Returns the search ID."""
    from db import get_db as _get_db
    from db.models import Search

    search_id = str(uuid.uuid4())
    async for db in _get_db():
        # Ensure the user has a profile row (FK requirement)
        await _ensure_profile_exists(db, user_id)
        
        search = Search(
            id=search_id,
            user_id=user_id,
            industry=context.get("industry"),
            company_profile=context.get("company_profile") or context.get("companyProfile"),
            technology_focus=context.get("technology_focus") or context.get("technologyFocus"),
            qualifying_criteria=context.get("qualifying_criteria") or context.get("qualifyingCriteria"),
            disqualifiers=context.get("disqualifiers"),
            queries_used=queries,
            total_found=total_found,
            messages=messages,
        )
        db.add(search)
        await db.commit()
    return search_id


async def _save_lead_to_db(search_id: str, company: dict, user_id: str = None, contacts: list = None) -> str:
    """Save a qualified lead to the database with dedup. Returns the lead ID.
    
    If a lead with the same domain already exists for this user, merges data
    instead of creating a duplicate (updates score if higher, merges contacts).
    """
    from db import get_db as _get_db
    from db.models import QualifiedLead, LeadContact, LeadSnapshot
    from sqlalchemy.orm import selectinload

    domain = company.get("domain", "")
    country = company.get("country") or _guess_country_from_domain(domain)
    latitude = company.get("latitude")
    longitude = company.get("longitude")

    async for db in _get_db():
        existing_lead = None

        # Per-pipeline dedup: only dedup within the same search/pipeline
        if user_id and domain and search_id:
            existing_lead = (await db.execute(
                select(QualifiedLead)
                .options(selectinload(QualifiedLead.contacts))
                .where(
                    QualifiedLead.user_id == user_id,
                    QualifiedLead.search_id == search_id,
                    QualifiedLead.domain == domain,
                )
            )).scalar_one_or_none()

        if existing_lead:
            # Merge: update if re-encountered
            new_score = company.get("score", 5)

            # Save snapshot of current state before updating
            snapshot = LeadSnapshot(
                lead_id=existing_lead.id,
                score=existing_lead.score,
                tier=existing_lead.tier,
                reasoning=existing_lead.reasoning or "",
                key_signals=existing_lead.key_signals,
            )
            db.add(snapshot)

            # Update with better data
            if new_score > existing_lead.score:
                existing_lead.score = new_score
                existing_lead.tier = company.get("tier", existing_lead.tier)
                existing_lead.reasoning = company.get("reasoning", existing_lead.reasoning)
                existing_lead.key_signals = company.get("key_signals", existing_lead.key_signals)
                existing_lead.red_flags = company.get("red_flags", existing_lead.red_flags)

            existing_lead.last_seen_at = datetime.now(timezone.utc)

            if company.get("hardware_type"):
                existing_lead.hardware_type = company["hardware_type"]
            if company.get("industry_category"):
                existing_lead.industry_category = company["industry_category"]
            if latitude:
                existing_lead.latitude = latitude
                existing_lead.longitude = longitude
            if country:
                existing_lead.country = country

            # Merge contacts (dedup by email)
            if contacts:
                existing_emails = set()
                for c in existing_lead.contacts:
                    if c.email:
                        existing_emails.add(c.email.lower())

                for contact in contacts:
                    email = contact.get("email", "")
                    if email and email.lower() in existing_emails:
                        continue  # Skip duplicate
                    lc = LeadContact(
                        lead_id=existing_lead.id,
                        full_name=contact.get("full_name"),
                        job_title=contact.get("job_title"),
                        email=email or None,
                        phone=contact.get("phone"),
                        linkedin_url=contact.get("linkedin_url"),
                        source=contact.get("source", "website"),
                    )
                    db.add(lc)

            await db.commit()
            logger.info("Merged lead %s (domain: %s) — score %d→%d",
                       existing_lead.id, domain, snapshot.score, existing_lead.score)
            return existing_lead.id

        # New lead — create fresh
        lead_id = str(uuid.uuid4())
        lead = QualifiedLead(
            id=lead_id,
            search_id=search_id,
            user_id=user_id,
            company_name=company.get("title", ""),
            domain=domain,
            website_url=company.get("url", ""),
            score=company.get("score", 5),
            tier=company.get("tier", "review"),
            hardware_type=company.get("hardware_type"),
            industry_category=company.get("industry_category"),
            reasoning=company.get("reasoning", ""),
            key_signals=company.get("key_signals", []),
            red_flags=company.get("red_flags", []),
            country=country,
            latitude=latitude,
            longitude=longitude,
            status="new",
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(lead)

        # Save extracted contacts
        if contacts:
            for contact in contacts:
                lc = LeadContact(
                    lead_id=lead_id,
                    full_name=contact.get("full_name"),
                    job_title=contact.get("job_title"),
                    email=contact.get("email"),
                    phone=contact.get("phone"),
                    linkedin_url=contact.get("linkedin_url"),
                    source=contact.get("source", "website"),
                )
                db.add(lc)

        await db.commit()
    return lead_id


# Country lookup from TLD
_TLD_COUNTRY_MAP = {
    ".de": "Germany", ".uk": "United Kingdom", ".co.uk": "United Kingdom",
    ".fr": "France", ".it": "Italy", ".es": "Spain", ".nl": "Netherlands",
    ".be": "Belgium", ".at": "Austria", ".ch": "Switzerland",
    ".se": "Sweden", ".no": "Norway", ".dk": "Denmark", ".fi": "Finland",
    ".pl": "Poland", ".cz": "Czech Republic", ".pt": "Portugal",
    ".jp": "Japan", ".cn": "China", ".kr": "South Korea", ".tw": "Taiwan",
    ".in": "India", ".au": "Australia", ".nz": "New Zealand",
    ".ca": "Canada", ".mx": "Mexico", ".br": "Brazil", ".ar": "Argentina",
    ".za": "South Africa", ".il": "Israel", ".sg": "Singapore",
    ".hk": "Hong Kong", ".my": "Malaysia", ".th": "Thailand",
    ".id": "Indonesia", ".ph": "Philippines", ".vn": "Vietnam",
    ".ru": "Russia", ".tr": "Turkey", ".ae": "UAE", ".sa": "Saudi Arabia",
}

# ── Geocoding via Nominatim (OpenStreetMap) ──────────────────
# Uses the free Nominatim API to geocode any location on Earth.
# Results are cached in-memory to avoid redundant requests.
import httpx

_nominatim_cache: dict[str, Optional[tuple]] = {}
_nominatim_lock = asyncio.Lock()

# Nominatim requires a unique User-Agent per application
_NOMINATIM_HEADERS = {
    "User-Agent": "LeadQualifier/1.0 (lead-discovery-tool)",
    "Accept": "application/json",
}


async def _geocode_location(location_str: str) -> Optional[tuple]:
    """
    Geocode a location string to (country, lat, lng) using OpenStreetMap Nominatim.
    Results are cached in-memory. Returns None if no match found.

    Handles full street addresses by progressively stripping detail if
    the full query doesn't match (e.g. "Luisenstr. 14, 80333 Munich, Germany"
    → "80333 Munich, Germany" → "Munich, Germany").
    """
    if not location_str or not location_str.strip():
        return None

    loc = location_str.lower().strip()
    # Remove common noise prefixes
    for noise in ["headquartered in ", "based in ", "hq: ", "hq "]:
        if loc.startswith(noise):
            loc = loc[len(noise):]

    # Check cache first
    if loc in _nominatim_cache:
        cached = _nominatim_cache[loc]
        if cached is None:
            return None
        return cached

    # Build progressively less specific queries
    # e.g. "401 N Tryon St, Charlotte, NC 28202, USA"
    #  → "Charlotte, NC 28202, USA"
    #  → "NC 28202, USA"
    #  → "USA"
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    queries = []
    for i in range(len(parts)):
        queries.append(", ".join(parts[i:]))
    # Deduplicate while preserving order
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    # Query Nominatim with progressive fallback
    try:
        async with _nominatim_lock:  # Nominatim rate limit: 1 req/sec
            for query in unique_queries:
                await asyncio.sleep(0.15)  # Be polite to the free API

                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": query,
                            "format": "jsonv2",
                            "limit": 1,
                            "addressdetails": 1,
                            "accept-language": "en",
                        },
                        headers=_NOMINATIM_HEADERS,
                    )
                    resp.raise_for_status()
                    results = resp.json()

                if results:
                    hit = results[0]
                    lat = float(hit["lat"])
                    lng = float(hit["lon"])

                    # Extract country from address details
                    addr = hit.get("address", {})
                    country = addr.get("country", None)

                    result = (country, lat, lng)
                    _nominatim_cache[loc] = result

                    if query != unique_queries[0]:
                        logger.info(
                            "Nominatim: full address '%s' missed, fell back to '%s'",
                            unique_queries[0], query,
                        )
                    return result

        # None of the queries matched
        _nominatim_cache[loc] = None
        return None

    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", loc, e)
        _nominatim_cache[loc] = None
        return None


async def _geocode_with_fallback(location_str: str) -> Optional[tuple]:
    """Geocode with Nominatim. Handles all locations including broad regions."""
    if not location_str:
        return None
    return await _geocode_location(location_str)


def _sanitize_crawl_error(raw: str | None) -> str:
    """Turn raw crawl4ai error messages into short, user-friendly strings."""
    if not raw:
        return "Website unreachable"
    msg = str(raw)
    low = msg.lower()
    if "connection_refused" in low or "err_connection_refused" in low:
        return "Website refused the connection"
    if "timeout" in low or "timed out" in low or "err_timed_out" in low:
        return "Website took too long to respond"
    if "ssl" in low or "certificate" in low or "err_cert" in low:
        return "Website has an SSL/certificate issue"
    if "name_not_resolved" in low or "dns" in low or "err_name_not_resolved" in low:
        return "Domain could not be resolved (DNS error)"
    if "403" in msg or "forbidden" in low:
        return "Website blocked automated access (403)"
    if "404" in msg or "not found" in low:
        return "Page not found (404)"
    if "cloudflare" in low or "captcha" in low or "challenge" in low:
        return "Website is behind bot protection"
    if "err_connection_reset" in low or "connection_reset" in low:
        return "Connection was reset by the server"
    if "err_empty_response" in low:
        return "Website returned an empty response"
    if "429" in msg or "too many" in low:
        return "Website rate-limited the request"
    # Fallback: take first meaningful line, strip stack traces
    first_line = msg.split("\n")[0].strip()
    # Remove file paths and code context
    if "at line" in first_line or "File \"" in first_line:
        return "Website could not be accessed"
    # Cap length to avoid leaking internals
    if len(first_line) > 120:
        return first_line[:117] + "…"
    return first_line


def _guess_country_from_domain(domain: str) -> Optional[str]:
    """Guess country from domain TLD."""
    if not domain:
        return None
    domain = domain.lower()
    # Check compound TLDs first (.co.uk, etc.)
    for tld, country in _TLD_COUNTRY_MAP.items():
        if domain.endswith(tld):
            return country
    # .com, .org, .io — can't determine
    return None


# ── Region validation ─────────────────────────
# Maps broad region keywords to sets of countries that belong to them.
# Used to cross-check LLM-extracted HQ location against user's intended region.

_REGION_COUNTRIES: dict[str, set[str]] = {
    "europe": {
        "germany", "france", "italy", "spain", "netherlands", "belgium",
        "austria", "switzerland", "sweden", "norway", "denmark", "finland",
        "poland", "czech republic", "portugal", "united kingdom", "uk",
        "ireland", "greece", "hungary", "romania", "croatia", "slovakia",
        "slovenia", "lithuania", "latvia", "estonia", "luxembourg", "bulgaria",
    },
    "north america": {"united states", "usa", "us", "canada", "mexico"},
    "south america": {"brazil", "argentina", "chile", "colombia", "peru", "venezuela", "ecuador", "uruguay"},
    "asia": {
        "china", "japan", "south korea", "india", "singapore", "taiwan",
        "hong kong", "macao", "macau", "malaysia", "thailand", "indonesia", "philippines",
        "vietnam", "pakistan", "bangladesh",
        "uae", "united arab emirates", "emirates",
    },
    "middle east": {"uae", "united arab emirates", "emirates", "saudi arabia", "israel", "turkey", "qatar", "bahrain", "kuwait", "oman"},
    "oceania": {"australia", "new zealand"},
    "africa": {"south africa", "nigeria", "kenya", "egypt", "morocco"},
}


def _location_matches_region(location_str: str, search_region: str) -> bool:
    """
    Check whether a geocoded location is plausible given the user's search region.
    Returns True if the location seems consistent, False if it's a likely mismatch.

    The caller should pass the Nominatim-resolved country name as location_str
    when available (e.g. "United Kingdom") for most reliable matching.

    Handles cases like:
      - location="United Kingdom"  region="Paddington, London, UK"  → True
      - location="Marylebone, London" region="Paddington, London, UK" → True (both in London)
      - location="Germany" region="Europe" → True
      - location="United States" region="Paddington, London, UK" → False
    """
    if not location_str or not search_region:
        return True  # No region constraint → anything is fine

    loc = location_str.lower().strip()
    region = search_region.lower().strip()

    # Country alias map: canonical names and abbreviations
    _COUNTRY_ALIASES = {
        "united states": ["usa", "america", "us"],
        "usa": ["united states", "america", "us"],
        "united kingdom": ["uk", "britain", "england", "scotland", "wales"],
        "uk": ["united kingdom", "britain", "england", "scotland", "wales"],
        "england": ["uk", "united kingdom", "britain"],
        "scotland": ["uk", "united kingdom", "britain"],
        "wales": ["uk", "united kingdom", "britain"],
        "uae": ["united arab emirates", "emirates"],
        "united arab emirates": ["uae", "emirates"],
        "hong kong": ["hk"],
        "macao": ["macau"],
        "macau": ["macao"],
        "south korea": ["korea"],
        "new zealand": ["nz"],
    }

    # Build full alias sets for both loc and region
    loc_expanded = loc
    region_expanded = region
    for canon, aliases in _COUNTRY_ALIASES.items():
        pattern = r'(?:^|[\s,;/\-()])' + re.escape(canon) + r'(?:$|[\s,;/\-()])'  
        if re.search(pattern, loc):
            loc_expanded += " " + " ".join(aliases)
        if re.search(pattern, region):
            region_expanded += " " + " ".join(aliases)

    # Direct substring match in either direction (using expanded forms)
    if region_expanded in loc_expanded or loc_expanded in region_expanded:
        return True

    # Check if they share a common city or country token
    _GEO_STOPWORDS = {"the", "and", "of", "in", "near", "new", "south", "north", "east", "west", "central", "arab"}
    loc_tokens = {t.strip().strip(",") for t in loc_expanded.replace(",", " ").split() if len(t.strip()) > 2}
    region_tokens = {t.strip().strip(",") for t in region_expanded.replace(",", " ").split() if len(t.strip()) > 2}
    shared = loc_tokens & region_tokens
    if shared - _GEO_STOPWORDS:
        return True

    # Determine if the search_region is a broad region name (e.g. "Europe", "Asia")
    region_is_broad = False
    for region_key in _REGION_COUNTRIES:
        if region_key in region or region in region_key:
            region_is_broad = True
            break

    # If the user's search region IS a broad region, check if location falls within it
    if region_is_broad:
        for region_key, countries in _REGION_COUNTRIES.items():
            if region_key in region or region in region_key:
                for country in countries:
                    if country in loc_expanded:
                        return True
                return False

    # For specific location-based search regions (cities, neighborhoods):
    # Check if the location and region share the same country.
    # Build a set of all country names that appear in each string.
    all_country_names: set[str] = set()
    for countries in _REGION_COUNTRIES.values():
        all_country_names.update(countries)

    loc_countries = {c for c in all_country_names if c in loc_expanded}
    region_countries = {c for c in all_country_names if c in region_expanded}

    if loc_countries and region_countries:
        # Both contain country references — do they overlap?
        if loc_countries & region_countries:
            return True  # Same country → trust the LLM location
        else:
            return False  # Different countries → genuine mismatch

    return True  # Can't determine → don't block


# ──────────────────────────────────────────────
# Schedule CRUD Endpoints (Tier 2)
# ──────────────────────────────────────────────

class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    pipeline_config: dict
    frequency: str = Field(..., pattern="^(daily|weekly|biweekly|monthly)$")
    run_at_hour: int = Field(9, ge=0, le=23)
    timezone: str = Field("UTC", max_length=50)


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    frequency: Optional[str] = Field(None, pattern="^(daily|weekly|biweekly|monthly)$")
    run_at_hour: Optional[int] = Field(None, ge=0, le=23)
    timezone: Optional[str] = Field(None, max_length=50)


@app.post("/api/schedules")
async def create_schedule(request: ScheduleCreateRequest, user=Depends(require_auth)):
    """Create a new recurring pipeline schedule."""
    from db import get_db as _get_db
    from db.models import PipelineSchedule, Profile
    from usage import MAX_SCHEDULES
    from scheduler import compute_next_run

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        # Tier gating: check schedule limit
        max_allowed = MAX_SCHEDULES.get(plan, 0)
        if max_allowed is not None:
            current_count = (await db.execute(
                select(func.count(PipelineSchedule.id))
                .where(PipelineSchedule.user_id == user.id)
            )).scalar() or 0
            if current_count >= max_allowed:
                if max_allowed == 0:
                    return JSONResponse(status_code=403, content={
                        "error": "upgrade_required",
                        "detail": "Scheduled pipelines are available on Pro and Enterprise plans.",
                        "upgrade_url": "/dashboard/settings?upgrade=true",
                    })
                return JSONResponse(status_code=403, content={
                    "error": "schedule_limit",
                    "detail": f"Your {plan} plan allows {max_allowed} scheduled pipelines. Delete one or upgrade.",
                    "limit": max_allowed,
                    "current": current_count,
                })

        next_run = compute_next_run(request.frequency)
        schedule = PipelineSchedule(
            user_id=user.id,
            name=request.name,
            pipeline_config=request.pipeline_config,
            frequency=request.frequency,
            run_at_hour=request.run_at_hour,
            timezone=request.timezone,
            next_run_at=next_run,
        )
        db.add(schedule)
        await db.commit()

        return {
            "id": schedule.id,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "is_active": schedule.is_active,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
        }


@app.get("/api/schedules")
async def list_schedules(user=Depends(require_auth)):
    """List all schedules for the authenticated user."""
    from db import get_db as _get_db
    from db.models import PipelineSchedule, QualifiedLead, Search

    async for db in _get_db():
        result = await db.execute(
            select(PipelineSchedule)
            .where(PipelineSchedule.user_id == user.id)
            .order_by(PipelineSchedule.created_at.desc())
        )
        schedules = result.scalars().all()

        schedule_list = []
        for s in schedules:
            # Get last run summary if available
            last_run_summary = None
            if s.last_run_id:
                tier_counts = (await db.execute(
                    select(QualifiedLead.tier, func.count(QualifiedLead.id))
                    .where(QualifiedLead.search_id == s.last_run_id)
                    .group_by(QualifiedLead.tier)
                )).all()
                if tier_counts:
                    last_run_summary = {row[0]: row[1] for row in tier_counts}

            schedule_list.append({
                "id": s.id,
                "name": s.name,
                "frequency": s.frequency,
                "is_active": s.is_active,
                "is_running": s.is_running,
                "run_at_hour": s.run_at_hour,
                "timezone": s.timezone,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_id": s.last_run_id,
                "last_run_summary": last_run_summary,
                "run_count": s.run_count,
                "consecutive_failures": s.consecutive_failures,
                "last_error": s.last_error,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })

        return {"schedules": schedule_list}


@app.patch("/api/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest, user=Depends(require_auth)):
    """Update a schedule (pause/resume, change frequency, rename)."""
    from db import get_db as _get_db
    from db.models import PipelineSchedule
    from scheduler import compute_next_run

    async for db in _get_db():
        schedule = (await db.execute(
            select(PipelineSchedule)
            .where(PipelineSchedule.id == schedule_id, PipelineSchedule.user_id == user.id)
        )).scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        if request.name is not None:
            schedule.name = request.name
        if request.run_at_hour is not None:
            schedule.run_at_hour = request.run_at_hour
        if request.timezone is not None:
            schedule.timezone = request.timezone

        # Handle frequency change → recompute next_run_at
        if request.frequency is not None and request.frequency != schedule.frequency:
            schedule.frequency = request.frequency
            schedule.next_run_at = compute_next_run(request.frequency)

        # Handle activation/deactivation
        if request.is_active is not None:
            schedule.is_active = request.is_active
            if request.is_active:
                # Resuming — recompute next_run_at from now
                schedule.next_run_at = compute_next_run(schedule.frequency)
                schedule.consecutive_failures = 0
                schedule.last_error = None

        await db.commit()

        return {
            "id": schedule.id,
            "name": schedule.name,
            "frequency": schedule.frequency,
            "is_active": schedule.is_active,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        }


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, user=Depends(require_auth)):
    """Delete a schedule. Verify ownership."""
    from db import get_db as _get_db
    from db.models import PipelineSchedule

    async for db in _get_db():
        schedule = (await db.execute(
            select(PipelineSchedule)
            .where(PipelineSchedule.id == schedule_id, PipelineSchedule.user_id == user.id)
        )).scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        await db.delete(schedule)
        await db.commit()
        return {"ok": True}


@app.post("/api/schedules/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str, user=Depends(require_auth)):
    """Trigger an immediate run of a schedule (doesn't change next_run_at)."""
    from db import get_db as _get_db
    from db.models import PipelineSchedule
    from scheduler import _run_scheduled_pipeline_safe

    async for db in _get_db():
        schedule = (await db.execute(
            select(PipelineSchedule)
            .where(PipelineSchedule.id == schedule_id, PipelineSchedule.user_id == user.id)
        )).scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")

        if schedule.is_running:
            raise HTTPException(status_code=409, detail="Schedule is already running")

        # Claim the lock
        schedule.is_running = True
        await db.commit()

        # Fire and forget — but DON'T advance next_run_at (that's the point of run-now)
        asyncio.create_task(_run_scheduled_pipeline_safe(schedule.id))

        return {
            "ok": True,
            "message": f"Pipeline '{schedule.name}' triggered. Check dashboard for results.",
        }


# ──────────────────────────────────────────────
# Lead Snapshots Endpoint (Tier 2)
# ──────────────────────────────────────────────

@app.get("/api/leads/{lead_id}/snapshots")
async def get_lead_snapshots(lead_id: str, user=Depends(require_auth)):
    """Get score history (snapshots) for a lead."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadSnapshot

    async for db in _get_db():
        # Verify ownership
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        snapshots = (await db.execute(
            select(LeadSnapshot)
            .where(LeadSnapshot.lead_id == lead_id)
            .order_by(LeadSnapshot.snapshot_at.desc())
        )).scalars().all()

        return {
            "lead_id": lead_id,
            "current_score": lead.score,
            "current_tier": lead.tier,
            "snapshots": [
                {
                    "id": s.id,
                    "score": s.score,
                    "tier": s.tier,
                    "reasoning": s.reasoning,
                    "key_signals": s.key_signals,
                    "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else None,
                }
                for s in snapshots
            ],
        }


# ──────────────────────────────────────────────
# Notification Preferences Endpoint (Tier 2)
# ──────────────────────────────────────────────

@app.get("/api/notifications/preferences")
async def get_notification_preferences(user=Depends(require_auth)):
    """Get user's notification preferences."""
    from db import get_db as _get_db
    from db.models import Profile

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()

        return {
            "preferences": profile.notification_prefs or {
                "pipeline_complete": True,
                "scheduled_run": True,
                "requalification": True,
                "weekly_digest": False,
            }
        }


@app.patch("/api/notifications/preferences")
async def update_notification_preferences(request: Request, user=Depends(require_auth)):
    """Update user's notification preferences."""
    from db import get_db as _get_db
    from db.models import Profile

    body = await request.json()
    valid_keys = {"pipeline_complete", "scheduled_run", "requalification", "weekly_digest"}

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()

        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        current_prefs = profile.notification_prefs or {
            "pipeline_complete": True,
            "scheduled_run": True,
            "requalification": True,
            "weekly_digest": False,
        }

        # Only update valid keys
        for key in valid_keys:
            if key in body and isinstance(body[key], bool):
                current_prefs[key] = body[key]

        profile.notification_prefs = current_prefs
        await db.commit()

        return {"preferences": current_prefs}


# ──────────────────────────────────────────────
# AI Email Draft Endpoints (Tier 2)
# ──────────────────────────────────────────────

# Concurrency limiter for LLM calls — prevents rate-limit storms
_email_draft_semaphore = asyncio.Semaphore(3)


class EmailDraftRequest(BaseModel):
    tone: str = Field("consultative", pattern="^(formal|casual|consultative)$")
    sender_context: Optional[str] = Field(None, max_length=500)


class BatchEmailDraftRequest(BaseModel):
    lead_ids: list[str] = Field(..., max_length=10)
    tone: str = Field("consultative", pattern="^(formal|casual|consultative)$")
    sender_context: Optional[str] = Field(None, max_length=500)


@app.post("/api/leads/{lead_id}/draft-email")
async def draft_email(lead_id: str, request: EmailDraftRequest, user=Depends(require_auth)):
    """Generate a personalized cold email draft for a lead using AI."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact, Profile
    from usage import check_quota, increment_usage

    async for db in _get_db():
        # Verify ownership + get profile
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        # Quota check
        exceeded = await check_quota(db, user.id, plan_tier=plan, action="email_draft")
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        # Get lead
        lead = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id == lead_id, Search.user_id == user.id)
        )).scalar_one_or_none()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Get contacts
        contacts = (await db.execute(
            select(LeadContact)
            .where(LeadContact.lead_id == lead_id)
            .order_by(LeadContact.created_at.asc())
        )).scalars().all()

        # Pick best contact (prefer those with email, then highest seniority)
        best_contact = _pick_best_contact(contacts)

        # Generate draft
        async with _email_draft_semaphore:
            draft = await _generate_email_draft(
                lead=lead,
                contact=best_contact,
                tone=request.tone,
                sender_context=request.sender_context,
            )

        # Increment usage
        await increment_usage(db, user.id, email_drafts_used=1)

        return {
            "draft": draft,
            "context_used": {
                "deep_research": bool(lead.deep_research),
                "contact_source": best_contact.source if best_contact else None,
                "signals_count": len(lead.key_signals) if lead.key_signals else 0,
            },
        }


@app.post("/api/leads/batch-draft-email")
async def batch_draft_email(request: BatchEmailDraftRequest, user=Depends(require_auth)):
    """Generate email drafts for multiple leads in parallel."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact, Profile
    from usage import check_quota, increment_usage

    async for db in _get_db():
        profile = (await db.execute(
            select(Profile).where(Profile.id == user.id)
        )).scalar_one_or_none()
        plan = profile.plan if profile else "free"

        # Quota check for batch
        exceeded = await check_quota(db, user.id, plan_tier=plan, action="email_draft", count=len(request.lead_ids))
        if exceeded:
            return JSONResponse(status_code=429, content=exceeded)

        # Fetch all leads with contacts
        leads = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(QualifiedLead.id.in_(request.lead_ids), Search.user_id == user.id)
        )).scalars().all()

        if not leads:
            raise HTTPException(status_code=404, detail="No matching leads found")

        # Fetch contacts for all leads
        all_contacts = (await db.execute(
            select(LeadContact)
            .where(LeadContact.lead_id.in_([l.id for l in leads]))
        )).scalars().all()

        contacts_by_lead = {}
        for c in all_contacts:
            contacts_by_lead.setdefault(c.lead_id, []).append(c)

        # Generate drafts with semaphore (max 3 concurrent LLM calls)
        async def _draft_one(lead):
            try:
                contacts = contacts_by_lead.get(lead.id, [])
                best_contact = _pick_best_contact(contacts)
                async with _email_draft_semaphore:
                    draft = await _generate_email_draft(
                        lead=lead,
                        contact=best_contact,
                        tone=request.tone,
                        sender_context=request.sender_context,
                    )
                return {"lead_id": lead.id, "company_name": lead.company_name, "draft": draft, "status": "ok"}
            except Exception as e:
                return {"lead_id": lead.id, "company_name": lead.company_name, "status": "error", "error": str(e)[:200]}

        results = await asyncio.gather(*[_draft_one(lead) for lead in leads])

        # Increment usage for successful drafts
        success_count = sum(1 for r in results if r["status"] == "ok")
        if success_count > 0:
            await increment_usage(db, user.id, email_drafts_used=success_count)

        return {"drafts": results}


def _pick_best_contact(contacts: list) -> Optional[object]:
    """Pick the best contact from a list — prefer those with email, then highest seniority."""
    if not contacts:
        return None

    SENIORITY_KEYWORDS = [
        "ceo", "founder", "owner", "president", "managing director",
        "cto", "coo", "cfo", "chief",
        "vp", "vice president",
        "director", "head of",
        "manager",
    ]

    def seniority_score(contact):
        title = (contact.job_title or "").lower()
        has_email = 1 if contact.email else 0
        for i, keyword in enumerate(SENIORITY_KEYWORDS):
            if keyword in title:
                return (has_email, len(SENIORITY_KEYWORDS) - i)
        return (has_email, 0)

    return max(contacts, key=seniority_score)


async def _generate_email_draft(
    lead,
    contact,
    tone: str,
    sender_context: Optional[str],
) -> dict:
    """Generate a cold email draft using the LLM."""
    from config import KIMI_API_KEY, KIMI_API_BASE
    import httpx

    # Build context from deep research (sanitize to prevent prompt injection)
    deep = lead.deep_research or {}
    deep_context = ""
    if deep:
        # Truncate each field to prevent oversized / adversarial content
        parts = []
        for key in ["products_found", "technologies_used", "company_size_estimate",
                     "potential_volume", "suggested_pitch_angle", "talking_points"]:
            val = deep.get(key)
            if val:
                # Sanitize: strip any instruction-like patterns
                val_str = str(val)[:300].replace("IGNORE", "").replace("ignore previous", "")
                parts.append(f"- {key.replace('_', ' ').title()}: {val_str}")
        if parts:
            deep_context = "\n".join(parts)

    contact_name = contact.full_name if contact else "Decision Maker"
    contact_title = contact.job_title if contact else ""
    contact_email = contact.email if contact else None

    signals = lead.reasoning or ""
    if lead.key_signals:
        signals += "\n- " + "\n- ".join(str(s)[:100] for s in lead.key_signals[:5])

    prompt = f"""You are a B2B cold email expert. Write a personalized cold email.

SENDER: {sender_context or 'Not specified — keep the email generic about mutual benefit.'}
RECIPIENT: {contact_name}, {contact_title} at {lead.company_name}
COMPANY INTEL:
{deep_context or '- Limited info available. Focus on what we know from signals.'}

KEY SIGNALS:
{signals[:500]}

TONE: {tone}

Rules:
- Max 150 words
- Reference something specific about THEIR business (not generic)
- One clear CTA (meeting, call, reply)
- No "I hope this email finds you well" or other filler
- Subject line: specific, no clickbait, under 8 words
- Return ONLY a JSON object with keys: "subject", "body"
- The body should start with a greeting using the recipient's first name
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{KIMI_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "kimi-k2-turbo-preview",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            # Parse JSON from response
            import re as _re
            json_match = _re.search(r'\{[\s\S]*\}', content)
            if json_match:
                draft_data = json.loads(json_match.group())
            else:
                # Fallback: treat entire response as body
                draft_data = {"subject": f"Quick question for {lead.company_name}", "body": content}

            return {
                "to_name": contact_name,
                "to_title": contact_title,
                "to_email": contact_email,
                "subject": draft_data.get("subject", ""),
                "body": draft_data.get("body", ""),
                "tone": tone,
            }

    except Exception as e:
        logger.error("Email draft generation failed for %s: %s", lead.company_name, e)
        raise HTTPException(status_code=500, detail="Failed to generate email draft")
