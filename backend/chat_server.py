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
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from chat_engine import ChatEngine, ExtractedContext


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
    """Initialize chat engine on startup."""
    global engine
    print("🧲 Starting Lead Discovery Chat Server...")
    engine = ChatEngine()
    print("✅ Chat engine ready")
    yield
    print("👋 Shutting down")


app = FastAPI(
    title="Lead Discovery Chat API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
        "enrichment_available": bool(enrich["waterfall_chain"] and enrich["waterfall_chain"] != ["manual"]),
        "enrichment_providers": enrich["waterfall_chain"],
    }


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
async def search(request: SearchRequest):
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
    Enrich contacts for qualified leads using the waterfall pattern.
    Streams SSE events: progress, result, complete.
    
    Waterfall chain: Waterfull → Apollo → Hunter
    """
    from enrichment import enrich_contact, enable_api_enrichment, get_enrichment_status

    # Force-enable API enrichment for this request
    enable_api_enrichment(True)
    
    status = get_enrichment_status()
    if not status["waterfall_chain"] or status["waterfall_chain"] == ["manual"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No enrichment APIs configured. Add WATERFULL_API_KEY, APOLLO_API_KEY, or HUNTER_API_KEY to .env"
            },
        )

    companies = [c.model_dump() for c in request.companies]

    async def generate():
        total = len(companies)
        yield sse_event({"type": "init", "total": total, "providers": status["waterfall_chain"]})

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
                print(f"❌ Enrichment error for {company['domain']}: {e}")
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
                "providers_used": status["waterfall_chain"],
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


def sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@app.post("/api/pipeline/run")
async def run_pipeline(request: PipelineRequest):
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
                        }

                        stats[tier.value] += 1

                        yield sse_event({
                            "type": "result",
                            "index": i,
                            "total": total,
                            "company": result_data,
                        })

                    except Exception as e:
                        print(f"❌ Pipeline error for {company.get('title', '?')}: {e}")
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
            print(f"❌ Fatal pipeline error: {e}")
            yield sse_event({
                "type": "error",
                "error": str(e)[:200],
                "fatal": True,
            })
            return

        yield sse_event({
            "type": "complete",
            "summary": stats,
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
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chat_server:app", host="0.0.0.0", port=8000, reload=True)
