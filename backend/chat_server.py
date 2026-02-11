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

import json
import logging
import os
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

setup_logging()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Rate Limiter (in-memory, per-IP)
# ──────────────────────────────────────────────

class RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, client_id: str) -> bool:
        """Returns True if the request is allowed."""
        now = time.time()
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
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to API routes."""
    if request.url.path.startswith("/api/"):
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
        data = await get_usage(db, user.id, plan_tier="free")
        return data


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

    # Build ExtractedContext from the validated request
    context = ExtractedContext(
        industry=request.industry,
        company_profile=request.company_profile,
        technology_focus=request.technology_focus,
        qualifying_criteria=request.qualifying_criteria,
        disqualifiers=request.disqualifiers,
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
async def enrich_contacts(request: EnrichRequest):
    """
    Enrich contacts for qualified leads using Hunter.io.
    Streams SSE events: progress, result, complete.
    """
    from enrichment import enrich_contact, enable_api_enrichment, get_enrichment_status

    # Force-enable API enrichment for this request
    enable_api_enrichment(True)
    
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
    companies = [c.model_dump() for c in request.companies]
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
                                geo = _geocode_location(fail_country)
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
                        hq_location = qual_result.headquarters_location
                        country = None
                        latitude = None
                        longitude = None

                        if hq_location:
                            geo = _geocode_location(hq_location)
                            if geo:
                                country, latitude, longitude = geo

                        if not country:
                            country = _guess_country_from_domain(company.get("domain", ""))
                            if country:
                                geo = _geocode_location(country)
                                if geo:
                                    _, latitude, longitude = geo

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
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ]


@app.get("/api/leads/geo")
async def leads_geo(user=Depends(require_auth)):
    """All leads with lat/lng coordinates for map plotting."""
    from db import get_db as _get_db
    from db.models import Search, QualifiedLead

    async for db in _get_db():
        leads = (await db.execute(
            select(QualifiedLead)
            .join(Search, QualifiedLead.search_id == Search.id)
            .where(Search.user_id == user.id)
            .where(QualifiedLead.latitude.isnot(None))
            .where(QualifiedLead.longitude.isnot(None))
        )).scalars().all()

        return [
            {
                "id": l.id,
                "company_name": l.company_name,
                "domain": l.domain,
                "score": l.score,
                "tier": l.tier,
                "country": l.country,
                "latitude": l.latitude,
                "longitude": l.longitude,
                "status": l.status,
            }
            for l in leads
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

        lead.status = request.status
        await db.commit()
        return {"ok": True, "status": lead.status}


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

# ── Static Geocoding ──────────────────────────
# City/region → (lat, lng) for common headquarters locations.
# Covers major tech/business hubs worldwide — no API calls needed.
_CITY_COORDS: dict = {
    # USA cities
    "new york": (40.71, -74.01), "nyc": (40.71, -74.01),
    "los angeles": (34.05, -118.24), "la": (34.05, -118.24),
    "san francisco": (37.77, -122.42), "sf": (37.77, -122.42),
    "san jose": (37.34, -121.89), "silicon valley": (37.39, -122.03),
    "seattle": (47.61, -122.33), "boston": (42.36, -71.06),
    "chicago": (41.88, -87.63), "houston": (29.76, -95.37),
    "dallas": (32.78, -96.80), "austin": (30.27, -97.74),
    "denver": (39.74, -104.99), "phoenix": (33.45, -112.07),
    "atlanta": (33.75, -84.39), "miami": (25.76, -80.19),
    "washington": (38.91, -77.04), "dc": (38.91, -77.04),
    "charlotte": (35.23, -80.84), "raleigh": (35.78, -78.64),
    "detroit": (42.33, -83.05), "minneapolis": (44.98, -93.27),
    "portland": (45.52, -122.68), "san diego": (32.72, -117.16),
    "pittsburgh": (40.44, -80.00), "philadelphia": (39.95, -75.17),
    "salt lake city": (40.76, -111.89), "nashville": (36.16, -86.78),
    "columbus": (39.96, -83.00), "indianapolis": (39.77, -86.16),
    "milwaukee": (43.04, -87.91), "kansas city": (39.10, -94.58),
    "st. louis": (38.63, -90.20), "st louis": (38.63, -90.20),
    "tampa": (27.95, -82.46), "orlando": (28.54, -81.38),
    "new haven": (41.31, -72.92), "irvine": (33.68, -117.83),
    "palo alto": (37.44, -122.14), "mountain view": (37.39, -122.08),
    "cupertino": (37.32, -122.03), "sunnyvale": (37.37, -122.04),
    "santa clara": (37.35, -121.96), "redmond": (47.67, -122.12),
    "menlo park": (37.45, -122.18),
    # Europe
    "london": (51.51, -0.13), "paris": (48.86, 2.35),
    "berlin": (52.52, 13.41), "munich": (48.14, 11.58),
    "frankfurt": (50.11, 8.68), "hamburg": (53.55, 9.99),
    "düsseldorf": (51.23, 6.77), "dusseldorf": (51.23, 6.77),
    "cologne": (50.94, 6.96), "köln": (50.94, 6.96),
    "stuttgart": (48.78, 9.18), "hanover": (52.37, 9.74),
    "amsterdam": (52.37, 4.90), "rotterdam": (51.92, 4.48),
    "brussels": (50.85, 4.35), "zurich": (47.38, 8.54),
    "zürich": (47.38, 8.54), "geneva": (46.20, 6.14), "bern": (46.95, 7.45),
    "vienna": (48.21, 16.37), "prague": (50.08, 14.44),
    "warsaw": (52.23, 21.01), "budapest": (47.50, 19.04),
    "madrid": (40.42, -3.70), "barcelona": (41.39, 2.17),
    "rome": (41.90, 12.50), "milan": (45.46, 9.19),
    "lisbon": (38.72, -9.14), "dublin": (53.35, -6.26),
    "edinburgh": (55.95, -3.19), "manchester": (53.48, -2.24),
    "stockholm": (59.33, 18.07), "oslo": (59.91, 10.75),
    "copenhagen": (55.68, 12.57), "helsinki": (60.17, 24.94),
    "tallinn": (59.44, 24.75), "riga": (56.95, 24.11),
    # Asia
    "tokyo": (35.68, 139.69), "osaka": (34.69, 135.50),
    "kyoto": (35.01, 135.77), "nagoya": (35.18, 136.91),
    "seoul": (37.57, 126.98), "busan": (35.18, 129.08),
    "beijing": (39.90, 116.40), "shanghai": (31.23, 121.47),
    "shenzhen": (22.54, 114.06), "guangzhou": (23.13, 113.26),
    "hong kong": (22.32, 114.17), "taipei": (25.03, 121.57),
    "singapore": (1.35, 103.82), "kuala lumpur": (3.14, 101.69),
    "bangkok": (13.76, 100.50), "ho chi minh": (10.82, 106.63),
    "jakarta": (6.21, 106.85), "manila": (14.60, 120.98),
    "mumbai": (19.08, 72.88), "delhi": (28.61, 77.23),
    "new delhi": (28.61, 77.23), "bangalore": (12.97, 77.59),
    "bengaluru": (12.97, 77.59), "hyderabad": (17.39, 78.49),
    "chennai": (13.08, 80.27), "pune": (18.52, 73.86),
    "tel aviv": (32.09, 34.77), "haifa": (32.79, 34.99),
    "dubai": (25.20, 55.27), "abu dhabi": (24.45, 54.65),
    "riyadh": (24.71, 46.68),
    # Other
    "toronto": (43.65, -79.38), "vancouver": (49.28, -123.12),
    "montreal": (45.50, -73.57), "ottawa": (45.42, -75.70),
    "calgary": (51.05, -114.07),
    "sydney": (33.87, 151.21), "melbourne": (-37.81, 144.96),
    "brisbane": (-27.47, 153.03), "perth": (-31.95, 115.86),
    "auckland": (-36.85, 174.76), "wellington": (-41.29, 174.78),
    "são paulo": (-23.55, -46.63), "sao paulo": (-23.55, -46.63),
    "rio de janeiro": (-22.91, -43.17),
    "mexico city": (19.43, -99.13), "buenos aires": (-34.60, -58.38),
    "bogota": (4.71, -74.07), "lima": (-12.05, -77.04),
    "santiago": (-33.45, -70.67),
    "cape town": (-33.93, 18.42), "johannesburg": (-26.20, 28.05),
    "nairobi": (-1.29, 36.82), "lagos": (6.52, 3.38),
    "cairo": (30.04, 31.24), "istanbul": (41.01, 28.98),
    "moscow": (55.76, 37.62), "saint petersburg": (59.93, 30.32),
}

# Country centroids — fallback when city not matched
_COUNTRY_COORDS: dict = {
    "united states": (39.83, -98.58), "usa": (39.83, -98.58),
    "us": (39.83, -98.58), "united states of america": (39.83, -98.58),
    "united kingdom": (55.38, -3.44), "uk": (55.38, -3.44),
    "great britain": (55.38, -3.44), "england": (52.36, -1.17),
    "germany": (51.17, 10.45), "france": (46.23, 2.21),
    "italy": (41.87, 12.57), "spain": (40.46, -3.75),
    "netherlands": (52.13, 5.29), "belgium": (50.50, 4.47),
    "austria": (47.52, 14.55), "switzerland": (46.82, 8.23),
    "sweden": (60.13, 18.64), "norway": (60.47, 8.47),
    "denmark": (56.26, 9.50), "finland": (61.92, 25.75),
    "poland": (51.92, 19.15), "czech republic": (49.82, 15.47),
    "czechia": (49.82, 15.47), "portugal": (39.40, -8.22),
    "ireland": (53.14, -7.69), "scotland": (56.49, -4.20),
    "hungary": (47.16, 19.50), "romania": (45.94, 24.97),
    "greece": (39.07, 21.82), "croatia": (45.10, 15.20),
    "japan": (36.20, 138.25), "china": (35.86, 104.20),
    "south korea": (35.91, 127.77), "korea": (35.91, 127.77),
    "taiwan": (23.70, 120.96), "india": (20.59, 78.96),
    "singapore": (1.35, 103.82), "malaysia": (4.21, 101.98),
    "thailand": (15.87, 100.99), "vietnam": (14.06, 108.28),
    "indonesia": (-0.79, 113.92), "philippines": (12.88, 121.77),
    "australia": (-25.27, 133.78), "new zealand": (-40.90, 174.89),
    "canada": (56.13, -106.35), "mexico": (23.63, -102.55),
    "brazil": (-14.24, -51.93), "argentina": (-38.42, -63.62),
    "colombia": (4.57, -74.30), "chile": (-35.68, -71.54),
    "peru": (-9.19, -75.02),
    "south africa": (-30.56, 22.94), "nigeria": (9.08, 8.68),
    "kenya": (-0.02, 37.91), "egypt": (26.82, 30.80),
    "israel": (31.05, 34.85), "uae": (23.42, 53.85),
    "united arab emirates": (23.42, 53.85),
    "saudi arabia": (23.89, 45.08), "turkey": (38.96, 35.24),
    "russia": (61.52, 105.32), "ukraine": (48.38, 31.17),
    "hong kong": (22.32, 114.17),
}


def _geocode_location(location_str: str) -> Optional[tuple]:
    """
    Geocode a location string to (country, lat, lng) using static lookup.
    Tries city-level first, then country-level.
    Returns None if no match found.
    """
    if not location_str:
        return None

    loc = location_str.lower().strip()
    # Remove common noise
    for noise in ["headquartered in ", "based in ", "hq: ", "hq "]:
        if loc.startswith(noise):
            loc = loc[len(noise):]

    # Try to find a city match in the location string
    best_city = None
    best_len = 0
    for city, coords in _CITY_COORDS.items():
        if city in loc and len(city) > best_len:
            best_city = city
            best_len = len(city)

    if best_city:
        coords = _CITY_COORDS[best_city]
        # Try to determine country from the rest of the string
        country_name = None
        for cname in _COUNTRY_COORDS:
            if cname in loc:
                country_name = cname.title()
                break
        # Add small jitter (±0.05°) so co-located dots don't perfectly overlap
        jitter_lat = random.uniform(-0.05, 0.05)
        jitter_lng = random.uniform(-0.05, 0.05)
        return (country_name, coords[0] + jitter_lat, coords[1] + jitter_lng)

    # Try country match
    best_country = None
    best_len = 0
    for cname, coords in _COUNTRY_COORDS.items():
        if cname in loc and len(cname) > best_len:
            best_country = cname
            best_len = len(cname)

    if best_country:
        coords = _COUNTRY_COORDS[best_country]
        jitter_lat = random.uniform(-0.3, 0.3)
        jitter_lng = random.uniform(-0.3, 0.3)
        return (best_country.title(), coords[0] + jitter_lat, coords[1] + jitter_lng)

    return None


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
