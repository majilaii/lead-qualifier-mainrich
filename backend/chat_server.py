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

from auth import require_auth
from chat_engine import ChatEngine, ExtractedContext
from logging_config import setup_logging
from stripe_billing import is_stripe_configured
from contact_extraction import extract_contacts_from_content
from linkedin_enrichment import enrich_linkedin, get_linkedin_status

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
    """Initialize chat engine and database on startup."""
    global engine
    
    # Initialize database
    from db import init_db
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database ready")
    
    logger.info("Starting Lead Discovery Chat Server...")
    engine = ChatEngine()
    logger.info("Chat engine ready")
    yield
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
async def chat(request: ChatRequest):
    """
    Process a chat message.
    Sends the conversation to the conversation LLM, which asks follow-up
    questions and extracts structured search parameters.
    """
    if not engine:
        raise HTTPException(status_code=503, detail="Chat engine not initialized")

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
# Pipeline SSE Endpoint
# ──────────────────────────────────────────────

class PipelineCompany(BaseModel):
    url: str = Field(..., max_length=500)
    domain: str = Field(..., max_length=200)
    title: str = Field(..., max_length=300)
    score: Optional[float] = None  # Exa relevance score for prioritization


class SearchContext(BaseModel):
    """User's search context — drives dynamic qualification criteria."""
    industry: Optional[str] = None
    company_profile: Optional[str] = None
    technology_focus: Optional[str] = None
    qualifying_criteria: Optional[str] = None
    disqualifiers: Optional[str] = None
    geographic_region: Optional[str] = None


class PipelineRequest(BaseModel):
    companies: list[PipelineCompany] = Field(..., max_length=50)
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
    search_id = None
    try:
        search_id = await _save_search_to_db(
            user_id=user.id,
            context=search_ctx or {},
            queries=[],
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
        """Background task — processes companies and emits events."""
        from scraper import CrawlerPool, crawl_company
        from intelligence import LeadQualifier
        from utils import determine_tier

        await run.emit({"type": "init", "total": total})

        qualifier = LeadQualifier(search_context=search_ctx)
        stats = {"hot": 0, "review": 0, "rejected": 0, "failed": 0}

        # ── Spread co-located pins in a spiral so they don't stack ──
        _geo_hit_count: dict[tuple[float, float], int] = {}

        def _spread_co_located(
            lat: Optional[float], lng: Optional[float]
        ) -> tuple[Optional[float], Optional[float]]:
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

        try:
            async with CrawlerPool() as pool:
                for i, company in enumerate(companies):
                    try:
                        # Phase: Crawling
                        await run.emit({
                            "type": "progress",
                            "index": i,
                            "total": total,
                            "phase": "crawling",
                            "company": {
                                "title": company["title"],
                                "domain": company["domain"],
                            },
                        })

                        crawl_result = await crawl_company(
                            company["url"],
                            take_screenshot=use_vision,
                            crawler_pool=pool,
                        )

                        if crawl_result.success and crawl_result.markdown_content:
                            try:
                                contact_snippet = await pool.crawl_contact_pages(company["url"])
                                if contact_snippet:
                                    crawl_result = crawl_result.model_copy(update={
                                        "markdown_content": (
                                            crawl_result.markdown_content
                                            + "\n\n=== ADDRESS & CONTACT INFO FROM OTHER PAGES ===\n"
                                            + contact_snippet
                                        )
                                    })
                                    logger.debug(
                                        "Appended contact page content for %s (+%d chars)",
                                        company.get("domain"), len(contact_snippet),
                                    )
                            except Exception as e:
                                logger.debug("Contact page sniff failed for %s: %s", company.get("domain"), e)

                        if not crawl_result.success:
                            fail_country = _guess_country_from_domain(company.get("domain", ""))
                            fail_lat = None
                            fail_lng = None
                            if fail_country:
                                geo = await _geocode_location(fail_country)
                                if geo:
                                    _, fail_lat, fail_lng = geo
                            fail_lat, fail_lng = _spread_co_located(fail_lat, fail_lng)

                            result_data = {
                                "title": company["title"],
                                "domain": company["domain"],
                                "url": company["url"],
                                "score": 5,
                                "tier": "review",
                                "reasoning": f"Website could not be crawled — {_sanitize_crawl_error(crawl_result.error_message)}. This company may still be relevant; visit the site manually to verify.",
                                "hardware_type": None,
                                "key_signals": [],
                                "red_flags": ["Crawl failed — needs manual review"],
                                "country": fail_country,
                                "latitude": fail_lat,
                                "longitude": fail_lng,
                            }
                            stats["review"] += 1
                            await run.emit({
                                "type": "result",
                                "index": i,
                                "total": total,
                                "company": result_data,
                            })
                            if search_id:
                                try:
                                    await _save_lead_to_db(search_id, result_data, user_id=user.id)
                                except Exception as e:
                                    logger.error("Failed to save crawl-failed lead %s to DB: %s", company.get('title'), e, exc_info=True)
                            continue

                        # Phase: Qualifying
                        await run.emit({
                            "type": "progress",
                            "index": i,
                            "total": total,
                            "phase": "qualifying",
                            "company": {
                                "title": company["title"],
                                "domain": company["domain"],
                            },
                        })

                        qual_result = await qualifier.qualify_lead(
                            company_name=company["title"],
                            website_url=company["url"],
                            crawl_result=crawl_result,
                            use_vision=use_vision,
                        )

                        tier = determine_tier(qual_result.confidence_score)

                        # Geocode
                        hq_location = qual_result.headquarters_location
                        search_region = (search_ctx or {}).get("geographic_region")
                        domain_country = _guess_country_from_domain(company.get("domain", ""))
                        country = None
                        latitude = None
                        longitude = None

                        if hq_location:
                            geo = await _geocode_location(hq_location)
                            if geo:
                                resolved_country, resolved_lat, resolved_lng = geo
                                country_matches = _location_matches_region(
                                    resolved_country or hq_location, search_region
                                )
                                if country_matches:
                                    country, latitude, longitude = resolved_country, resolved_lat, resolved_lng
                                else:
                                    logger.info(
                                        "Geo mismatch for %s: LLM said '%s' (resolved: %s) but search region is '%s' — using domain/region fallback",
                                        company.get("domain"), hq_location, resolved_country, search_region,
                                    )
                                    if domain_country:
                                        geo2 = await _geocode_location(domain_country)
                                        if geo2:
                                            country, latitude, longitude = geo2
                                    elif search_region:
                                        geo2 = await _geocode_location(search_region)
                                        if geo2:
                                            country, latitude, longitude = geo2

                        if not country:
                            if domain_country:
                                country = domain_country
                                if search_region and _location_matches_region(domain_country, search_region):
                                    geo = await _geocode_location(search_region)
                                    if geo:
                                        _, latitude, longitude = geo
                                if not latitude:
                                    geo = await _geocode_location(country)
                                    if geo:
                                        _, latitude, longitude = geo
                            elif search_region:
                                geo = await _geocode_location(search_region)
                                if geo:
                                    country, latitude, longitude = geo

                        latitude, longitude = _spread_co_located(latitude, longitude)

                        # Extract contacts
                        extracted_contacts = []
                        try:
                            from contact_extraction import extract_contacts_from_content
                            people = await extract_contacts_from_content(
                                company_name=company["title"],
                                domain=company["domain"],
                                page_content=crawl_result.markdown_content or "",
                            )
                            extracted_contacts = [
                                {
                                    "full_name": p.full_name,
                                    "job_title": p.job_title,
                                    "email": p.email,
                                    "phone": p.phone,
                                    "linkedin_url": p.linkedin_url,
                                    "source": "website",
                                }
                                for p in people
                            ]
                        except Exception as ce:
                            logger.debug("Contact extraction failed for %s: %s", company.get("domain"), ce)

                        result_data = {
                            "title": company["title"],
                            "domain": company["domain"],
                            "url": company["url"],
                            "score": qual_result.confidence_score,
                            "tier": tier.value,
                            "hardware_type": qual_result.hardware_type,
                            "industry_category": qual_result.industry_category,
                            "reasoning": qual_result.reasoning,
                            "key_signals": qual_result.key_signals,
                            "red_flags": qual_result.red_flags,
                            "country": country,
                            "latitude": latitude,
                            "longitude": longitude,
                            "contacts": extracted_contacts,
                        }

                        stats[tier.value] += 1

                        await run.emit({
                            "type": "result",
                            "index": i,
                            "total": total,
                            "company": result_data,
                        })

                        if search_id:
                            try:
                                await _save_lead_to_db(search_id, result_data, user_id=user.id, contacts=extracted_contacts)
                            except Exception as e:
                                logger.error("Failed to save lead %s to DB: %s (type: %s)", company.get('title'), e, type(e).__name__, exc_info=True)

                    except Exception as e:
                        logger.error("Pipeline error for %s: %s", company.get('title', '?'), e)
                        stats["failed"] += 1
                        await run.emit({
                            "type": "error",
                            "index": i,
                            "total": total,
                            "company": {
                                "title": company["title"],
                                "domain": company["domain"],
                            },
                            "error": str(e)[:200],
                        })

        except Exception as e:
            logger.error("Fatal pipeline error: %s", e)
            await run.emit({
                "type": "error",
                "error": str(e)[:200],
                "fatal": True,
            })
            return

        await run.emit({
            "type": "complete",
            "summary": stats,
            "search_id": search_id,
        })

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

            results.append({
                "id": s.id,
                "industry": s.industry,
                "company_profile": s.company_profile,
                "technology_focus": s.technology_focus,
                "qualifying_criteria": s.qualifying_criteria,
                "disqualifiers": s.disqualifiers,
                "total_found": s.total_found,
                "hot": tiers.get("hot", 0),
                "review": tiers.get("review", 0),
                "rejected": tiers.get("rejected", 0),
                "created_at": s.created_at.isoformat() if s.created_at else None,
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
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        query = (
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
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
# Export All Leads
# ──────────────────────────────────────────────

@app.get("/api/leads/export")
async def export_all_leads(user=Depends(require_auth)):
    """Export all user's leads as CSV."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead, LeadContact
    import csv
    import io

    async for db in _get_db():
        leads = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
            .order_by(QualifiedLead.score.desc())
        )).scalars().all()

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

    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hunt_leads_export.csv"},
    )


# ──────────────────────────────────────────────
# LinkedIn enrichment status (health)
# ──────────────────────────────────────────────

@app.get("/api/linkedin/status")
async def linkedin_status():
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

    domain = company.get("domain", "")
    country = company.get("country") or _guess_country_from_domain(domain)
    latitude = company.get("latitude")
    longitude = company.get("longitude")

    async for db in _get_db():
        existing_lead = None

        # Global dedup: check if we already have this domain for this user
        if user_id and domain:
            existing_lead = (await db.execute(
                select(QualifiedLead).where(
                    QualifiedLead.user_id == user_id,
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

            # Always update search_id to latest hunt
            existing_lead.search_id = search_id
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
