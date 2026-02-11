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
import re
import random
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
rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


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
    """Apply rate limiting to API routes (skip CORS preflight & health)."""
    if (
        request.url.path.startswith("/api/")
        and request.method != "OPTIONS"
        and request.url.path != "/api/health"
    ):
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.check(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a moment and try again.",
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
    return {
        "status": "ok",
        "llm_available": engine is not None
        and (engine.kimi_client is not None or engine.openai_client is not None),
        "exa_available": engine is not None and engine.exa_client is not None,
        "enrichment_available": bool(enrich["providers"]),
        "enrichment_providers": enrich["providers"],
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


def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@app.post("/api/pipeline/run")
async def run_pipeline(request: PipelineRequest, user=Depends(require_auth)):
    """
    Run the full crawl → qualify pipeline on search results.
    Streams Server-Sent Events (SSE) with live progress for each company.

    Event types:
      init     — { total: N }
      progress — { index, total, phase: "crawling"|"qualifying", company: {...} }
      result   — { index, total, company: { score, tier, reasoning, ... } }
      error    — { index, company, error }
      complete — { summary: { hot, review, rejected, failed } }
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

    # ── Smart prioritization: sort by Exa score (descending) so highest-signal
    # companies get processed first → user sees hot leads early ──
    companies.sort(key=lambda c: c.get("score") or 0, reverse=True)

    async def generate():
        from scraper import CrawlerPool, crawl_company
        from intelligence import LeadQualifier
        from utils import determine_tier

        total = len(companies)
        yield sse_event({"type": "init", "total": total})

        qualifier = LeadQualifier(search_context=search_ctx)
        stats = {"hot": 0, "review": 0, "rejected": 0, "failed": 0}

        # Save search to DB
        search_id = None
        try:
            search_id = await _save_search_to_db(
                user_id=user.id,
                context=search_ctx or {},
                queries=[],
                total_found=total,
                messages=request.messages,
            )
        except Exception as e:
            logger.warning("Failed to save search to DB: %s", e)

        try:
            async with CrawlerPool() as pool:
                for i, company in enumerate(companies):
                    try:
                        # Phase: Crawling
                        yield sse_event({
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

                        if not crawl_result.success:
                            # Still try to geocode from domain TLD
                            fail_country = _guess_country_from_domain(company.get("domain", ""))
                            fail_lat = None
                            fail_lng = None
                            if fail_country:
                                geo = await _geocode_location(fail_country)
                                if geo:
                                    _, fail_lat, fail_lng = geo

                            result_data = {
                                "title": company["title"],
                                "domain": company["domain"],
                                "url": company["url"],
                                "score": 5,
                                "tier": "review",
                                "reasoning": f"Website could not be crawled: {crawl_result.error_message or 'Unknown'}",
                                "hardware_type": None,
                                "key_signals": [],
                                "red_flags": ["Crawl failed — needs manual review"],
                                "country": fail_country,
                                "latitude": fail_lat,
                                "longitude": fail_lng,
                            }
                            stats["review"] += 1
                            yield sse_event({
                                "type": "result",
                                "index": i,
                                "total": total,
                                "company": result_data,
                            })
                            continue

                        # Phase: Qualifying
                        yield sse_event({
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

                        # Geocode: try LLM-extracted location, fall back to domain TLD
                        # Validate against user's search region to catch SEO-mislocated pages
                        hq_location = qual_result.headquarters_location
                        search_region = (search_ctx or {}).get("geographic_region")
                        domain_country = _guess_country_from_domain(company.get("domain", ""))
                        country = None
                        latitude = None
                        longitude = None

                        if hq_location:
                            # Cross-check: does the LLM location match the user's search region?
                            if _location_matches_region(hq_location, search_region):
                                geo = await _geocode_location(hq_location)
                                if geo:
                                    country, latitude, longitude = geo
                            else:
                                # LLM location conflicts with search region — likely an SEO mirror
                                # Prefer domain TLD if available, otherwise use search region
                                logger.info(
                                    "Geo mismatch for %s: LLM said '%s' but search region is '%s' — using domain/region fallback",
                                    company.get("domain"), hq_location, search_region,
                                )
                                if domain_country:
                                    geo = await _geocode_location(domain_country)
                                    if geo:
                                        country, latitude, longitude = geo
                                elif search_region:
                                    geo = await _geocode_location(search_region)
                                    if geo:
                                        country, latitude, longitude = geo

                        if not country:
                            if domain_country:
                                country = domain_country
                                # If we have a search region and the domain country
                                # matches the region's country, use the search region
                                # for geocoding (much more precise than country centroid).
                                # E.g. user wants "Paddington, London, UK" + domain is .co.uk
                                # → place at Paddington, not the UK centroid (which is in Scotland).
                                if search_region and _location_matches_region(domain_country, search_region):
                                    geo = await _geocode_location(search_region)
                                    if geo:
                                        _, latitude, longitude = geo
                                if not latitude:
                                    geo = await _geocode_location(country)
                                    if geo:
                                        _, latitude, longitude = geo
                            elif search_region:
                                # Last resort: use the user's search region centroid
                                geo = await _geocode_location(search_region)
                                if geo:
                                    country, latitude, longitude = geo

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
                        }

                        stats[tier.value] += 1

                        yield sse_event({
                            "type": "result",
                            "index": i,
                            "total": total,
                            "company": result_data,
                        })

                        # Save to DB
                        if search_id:
                            try:
                                await _save_lead_to_db(search_id, result_data)
                            except Exception as e:
                                logger.warning("Failed to save lead %s to DB: %s", company.get('title'), e)

                    except Exception as e:
                        logger.error("Pipeline error for %s: %s", company.get('title', '?'), e)
                        stats["failed"] += 1
                        yield sse_event({
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
            yield sse_event({
                "type": "error",
                "error": str(e)[:200],
                "fatal": True,
            })
            return

        yield sse_event({
            "type": "complete",
            "summary": stats,
            "search_id": search_id,
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
    from db.models import Search, QualifiedLead, EnrichmentResult_

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
        }

        if enrichment:
            result["enrichment"] = {
                "email": enrichment.email,
                "phone": enrichment.phone,
                "job_title": enrichment.job_title,
                "source": enrichment.source,
            }

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
# Save Pipeline Results to DB
# ──────────────────────────────────────────────

async def _save_search_to_db(user_id: str, context: dict, queries: list, total_found: int, messages: Optional[list] = None) -> str:
    """Save a search session to the database. Returns the search ID."""
    from db import get_db as _get_db
    from db.models import Search

    search_id = str(uuid.uuid4())
    async for db in _get_db():
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


async def _save_lead_to_db(search_id: str, company: dict) -> str:
    """Save a qualified lead to the database. Returns the lead ID."""
    from db import get_db as _get_db
    from db.models import QualifiedLead

    lead_id = str(uuid.uuid4())

    # Use pre-computed geo data from pipeline, fallback to TLD guess
    country = company.get("country") or _guess_country_from_domain(company.get("domain", ""))
    latitude = company.get("latitude")
    longitude = company.get("longitude")

    async for db in _get_db():
        lead = QualifiedLead(
            id=lead_id,
            search_id=search_id,
            company_name=company.get("title", ""),
            domain=company.get("domain", ""),
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
        )
        db.add(lead)
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

    # Query Nominatim
    try:
        async with _nominatim_lock:  # Nominatim rate limit: 1 req/sec
            await asyncio.sleep(0.15)  # Be polite to the free API

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": loc,
                        "format": "jsonv2",
                        "limit": 1,
                        "addressdetails": 1,
                        "accept-language": "en",
                    },
                    headers=_NOMINATIM_HEADERS,
                )
                resp.raise_for_status()
                results = resp.json()

        if not results:
            _nominatim_cache[loc] = None
            return None

        hit = results[0]
        lat = float(hit["lat"])
        lng = float(hit["lon"])

        # Extract country from address details
        addr = hit.get("address", {})
        country = addr.get("country", None)

        _nominatim_cache[loc] = (country, lat, lng)

        return (country, lat, lng)

    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", loc, e)
        _nominatim_cache[loc] = None
        return None


async def _geocode_with_fallback(location_str: str) -> Optional[tuple]:
    """Geocode with Nominatim. Handles all locations including broad regions."""
    if not location_str:
        return None
    return await _geocode_location(location_str)


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

    Handles cases like:
      - location="Marylebone, London" region="Paddington, London, UK" → True (both in London)
      - location="United Kingdom" region="Paddington, London, UK" → True (UK contains Paddington)
      - location="Edinburgh" region="Paddington, London, UK" → True (both in UK, close enough)
      - location="New York" region="Paddington, London, UK" → False
    """
    if not location_str or not search_region:
        return True  # No region constraint → anything is fine

    loc = location_str.lower().strip()
    region = search_region.lower().strip()

    # Country alias map: canonical names and abbreviations
    _COUNTRY_ALIASES = {
        "united states": ["usa", "america"],
        "usa": ["united states", "america"],
        "united kingdom": ["uk", "britain"],
        "uk": ["united kingdom", "britain"],
        "uae": ["united arab emirates", "emirates"],
        "united arab emirates": ["uae", "emirates"],
        "hong kong": ["hk"],
        "macao": ["macau"],
        "macau": ["macao"],
        "south korea": ["korea"],
        "new zealand": ["nz"],
    }

    # Expand both loc and region with aliases for matching
    # Use word-boundary matching to avoid substring issues
    loc_expanded = loc
    region_expanded = region
    for canon, aliases in _COUNTRY_ALIASES.items():
        # Use word boundary to check: "uk" should match standalone, not inside "duke"
        pattern = r'(?:^|[\s,;/\-()])' + re.escape(canon) + r'(?:$|[\s,;/\-()])'  
        if re.search(pattern, loc):
            loc_expanded += " " + " ".join(aliases)
        if re.search(pattern, region):
            region_expanded += " " + " ".join(aliases)

    # Direct substring match in either direction (using expanded forms)
    if region_expanded in loc_expanded or loc_expanded in region_expanded:
        return True

    # Check if they share a common city or country token
    # E.g. loc="Marylebone, London" region="Paddington, London, UK"
    # Both contain "london" → match
    # Exclude common geographic prefix words that appear in multiple country names
    _GEO_STOPWORDS = {"the", "and", "of", "in", "near", "united", "new", "south", "north", "east", "west", "central", "arab"}
    loc_tokens = {t.strip().strip(",") for t in loc_expanded.replace(",", " ").split() if len(t.strip()) > 2}
    region_tokens = {t.strip().strip(",") for t in region_expanded.replace(",", " ").split() if len(t.strip()) > 2}
    shared = loc_tokens & region_tokens
    # If they share a meaningful geographic token (city/country name), consider it a match
    if shared - _GEO_STOPWORDS:
        return True

    # Determine if the search_region is a broad region name (e.g. "Europe", "Asia")
    # vs a specific location (e.g. "Paddington, London, UK", "Central, Hong Kong")
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
    # Only match via shared tokens (already checked above) or country match.
    # Do NOT match just because both are in the same continent.
    # E.g. "Singapore" vs "Hong Kong" → both in Asia but should NOT match.

    # Check if the location's country matches a country in the search region
    for region_key, countries in _REGION_COUNTRIES.items():
        for country in countries:
            if country in region_expanded:
                # User's region contains this country — check if location also contains it
                return country in loc_expanded

    return True  # Can't determine → don't block
