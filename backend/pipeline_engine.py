"""
Pipeline Engine — The core processing loop for lead qualification.

This module extracts the shared pipeline logic so it can be invoked from
any entry point: chat, manual config, bulk import, API, or scheduled runs.

Usage:
    from pipeline_engine import process_companies, run_discovery

    # Full pipeline with discovery
    companies = await run_discovery(engine, search_context)
    await process_companies(companies, search_ctx, use_vision, run, search_id, user_id)

    # Qualify-only (domains provided)
    await process_companies(companies, search_ctx, use_vision, run, search_id, user_id)
"""

import asyncio
import logging
import math
from typing import Optional

from chat_engine import ChatEngine, ExtractedContext
from models import CrawlResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Discovery — Exa query generation + search
# ──────────────────────────────────────────────

async def run_discovery(
    engine: ChatEngine,
    search_context: dict,
    run=None,
) -> list[dict]:
    """
    Generate Exa queries from a search context and execute them.

    Args:
        engine: ChatEngine instance with Exa client
        search_context: dict with industry, company_profile, etc.
        run: Optional PipelineRun to emit discovery stage events

    Returns:
        List of company dicts [{url, domain, title, score}, ...]
    """
    if run:
        await run.emit({
            "type": "stage",
            "stage": "discovery",
            "status": "running",
        })

    # Build ExtractedContext from the search_context dict
    context = ExtractedContext(
        industry=search_context.get("industry"),
        company_profile=search_context.get("company_profile"),
        technology_focus=search_context.get("technology_focus"),
        qualifying_criteria=search_context.get("qualifying_criteria"),
        disqualifiers=search_context.get("disqualifiers"),
        geographic_region=search_context.get("geographic_region"),
        country_code=search_context.get("country_code"),
    )

    result = await engine.generate_and_search(context)

    companies = result.companies or []

    if run:
        await run.emit({
            "type": "stage",
            "stage": "discovery",
            "status": "done",
            "count": len(companies),
            "queries_used": result.queries_used,
            "unique_domains": result.unique_domains,
        })

    return companies


# ──────────────────────────────────────────────
# Geo helpers (local to pipeline processing)
# ──────────────────────────────────────────────

def _make_spread_fn():
    """Create a geo-spread function to offset co-located pins in a spiral."""
    hit_count: dict[tuple[float, float], int] = {}

    def spread(
        lat: Optional[float], lng: Optional[float]
    ) -> tuple[Optional[float], Optional[float]]:
        if lat is None or lng is None:
            return lat, lng
        key = (round(lat, 6), round(lng, 6))
        n = hit_count.get(key, 0)
        hit_count[key] = n + 1
        if n == 0:
            return lat, lng
        angle = n * 2.399_963
        r = 0.0012 * math.sqrt(n)
        return lat + r * math.cos(angle), lng + r * math.sin(angle)

    return spread


# ──────────────────────────────────────────────
# Core processing loop — crawl → qualify → enrich
# ──────────────────────────────────────────────

async def process_companies(
    companies: list[dict],
    search_ctx: Optional[dict],
    use_vision: bool,
    run,
    search_id: Optional[str],
    user_id: str,
    *,
    geocode_fn=None,
    country_from_domain_fn=None,
    location_matches_fn=None,
    sanitize_error_fn=None,
    save_lead_fn=None,
):
    """
    Process a list of companies through qualify → selective crawl → enrich.

    **Exa-first strategy**: Exa already crawls pages with its own headless
    browser and returns clean markdown.  We use that content as the PRIMARY
    signal for LLM qualification — no Playwright crawl needed to score.

    Only HOT leads (score ≥ 70) get a full Playwright crawl afterward for:
      • Screenshots (vision analysis confirmation)
      • Contact page scraping (/contact, /about, /team)
      • Address / HQ extraction from secondary pages

    This cuts crawl time by ~70-80% on a typical batch (most leads are
    review or rejected and never need a browser launch).

    Emits events to the PipelineRun for real-time streaming.

    Args:
        companies: List of company dicts [{url, domain, title, exa_text, ...}]
        search_ctx: Search context dict (industry, criteria, etc.)
        use_vision: Whether to use vision (screenshots) for hot-lead verification
        run: PipelineRun instance for event emission
        search_id: Database search record ID
        user_id: Authenticated user ID
        geocode_fn: async fn(location_str) -> (country, lat, lng) or None
        country_from_domain_fn: fn(domain) -> country or None
        location_matches_fn: fn(location, region) -> bool
        sanitize_error_fn: fn(error_str) -> sanitized_str
        save_lead_fn: async fn(search_id, company_data, user_id, contacts) -> lead_id
    """
    from scraper import CrawlerPool, crawl_company
    from intelligence import LeadQualifier
    from utils import determine_tier
    from contact_extraction import extract_contacts_from_content

    total = len(companies)
    await run.emit({"type": "init", "total": total})

    qualifier = LeadQualifier(search_context=search_ctx)
    stats = {"hot": 0, "review": 0, "rejected": 0, "failed": 0}
    spread = _make_spread_fn()

    # Collect hot leads for selective crawl phase
    hot_leads_to_crawl: list[tuple[int, dict, 'QualificationResult']] = []

    # Fallback crawler pool — only opened if some companies lack Exa text
    fallback_pool = None
    fallback_pool_cm = CrawlerPool()

    try:
        # ═══════════════════════════════════════════════════════
        # PHASE 1: Qualify leads (Exa text if available, crawl if not)
        # ═══════════════════════════════════════════════════════
        for i, company in enumerate(companies):
            try:
                # ── Phase: Qualifying (Exa-first) ──
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

                # Build a CrawlResult from Exa data — no browser needed
                exa_text = company.get("exa_text", "")
                exa_highlights = company.get("highlights", "")
                exa_score = company.get("score")
                has_exa = bool(exa_text and len(exa_text.strip()) > 50)

                if has_exa:
                    # Exa-first: use Exa text directly (no browser)
                    crawl_result = CrawlResult(
                        url=company["url"],
                        success=True,
                        markdown_content=exa_text,
                        title=company.get("title"),
                        exa_text=exa_text,
                        exa_highlights=exa_highlights or None,
                        exa_score=exa_score,
                    )
                else:
                    # No Exa text (qualify_only / bulk import) — crawl now
                    logger.info("No Exa text for %s — falling back to Playwright crawl", company.get("domain"))
                    if not fallback_pool:
                        fallback_pool = await fallback_pool_cm.__aenter__()
                    crawl_result = await crawl_company(
                        company["url"],
                        take_screenshot=use_vision,
                        crawler_pool=fallback_pool,
                    )

                qual_result = await qualifier.qualify_lead(
                    company_name=company["title"],
                    website_url=company["url"],
                    crawl_result=crawl_result,
                    use_vision=use_vision and not has_exa,  # Vision only if we crawled
                )

                tier = determine_tier(qual_result.confidence_score)

                # ── Geocoding ──
                hq_location = qual_result.headquarters_location
                search_region = (search_ctx or {}).get("geographic_region")
                domain_country = country_from_domain_fn(company.get("domain", "")) if country_from_domain_fn else None
                country, latitude, longitude = None, None, None

                if hq_location and geocode_fn:
                    geo = await geocode_fn(hq_location)
                    if geo:
                        resolved_country, resolved_lat, resolved_lng = geo
                        country_matches = location_matches_fn(
                            resolved_country or hq_location, search_region
                        ) if location_matches_fn and search_region else True
                        if country_matches:
                            country, latitude, longitude = resolved_country, resolved_lat, resolved_lng
                        else:
                            logger.info(
                                "Geo mismatch for %s: LLM said '%s' (resolved: %s) but search region is '%s' — using domain/region fallback",
                                company.get("domain"), hq_location, resolved_country, search_region,
                            )
                            if domain_country and geocode_fn:
                                geo2 = await geocode_fn(domain_country)
                                if geo2:
                                    country, latitude, longitude = geo2
                            elif search_region and geocode_fn:
                                geo2 = await geocode_fn(search_region)
                                if geo2:
                                    country, latitude, longitude = geo2

                if not country:
                    if domain_country:
                        country = domain_country
                        if geocode_fn:
                            if search_region and location_matches_fn and location_matches_fn(domain_country, search_region):
                                geo = await geocode_fn(search_region)
                                if geo:
                                    _, latitude, longitude = geo
                            if not latitude:
                                geo = await geocode_fn(country)
                                if geo:
                                    _, latitude, longitude = geo
                    elif search_region and geocode_fn:
                        geo = await geocode_fn(search_region)
                        if geo:
                            country, latitude, longitude = geo

                latitude, longitude = spread(latitude, longitude)

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
                    "contacts": [],  # Contacts extracted in Phase 2 for hot leads
                }

                stats[tier.value] += 1

                # Queue hot leads for Phase 2 (deep crawl for contacts + verification)
                if tier.value == "hot":
                    hot_leads_to_crawl.append((i, company, qual_result))

                await run.emit({
                    "type": "result",
                    "index": i,
                    "total": total,
                    "company": result_data,
                })

                if search_id and save_lead_fn:
                    try:
                        await save_lead_fn(search_id, result_data, user_id=user_id)
                    except Exception as e:
                        logger.error("Failed to save lead %s to DB: %s (type: %s)", company.get("title"), e, type(e).__name__, exc_info=True)

            except Exception as e:
                logger.error("Pipeline error for %s: %s", company.get("title", "?"), e)
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

        # ═══════════════════════════════════════════════════════
        # PHASE 2: Deep-crawl HOT leads only (contacts, screenshots)
        # ═══════════════════════════════════════════════════════
        if hot_leads_to_crawl:
            logger.info(
                "Phase 2: Deep-crawling %d hot leads for contacts & verification",
                len(hot_leads_to_crawl),
            )
            async with CrawlerPool() as pool:
                for (original_index, company, qual_result) in hot_leads_to_crawl:
                    try:
                        await run.emit({
                            "type": "progress",
                            "index": original_index,
                            "total": total,
                            "phase": "enriching",
                            "company": {
                                "title": company["title"],
                                "domain": company["domain"],
                                "note": "Deep crawl for contacts & verification",
                            },
                        })

                        # Full Playwright crawl for screenshot + content
                        deep_crawl = await crawl_company(
                            company["url"],
                            take_screenshot=use_vision,
                            crawler_pool=pool,
                        )

                        # Extract contacts from crawled content
                        extracted_contacts = []
                        contact_content = ""
                        if deep_crawl.success and deep_crawl.markdown_content:
                            contact_content = deep_crawl.markdown_content

                            # Also crawl /contact, /about pages for address & people
                            try:
                                contact_snippet = await pool.crawl_contact_pages(company["url"])
                                if contact_snippet:
                                    contact_content += (
                                        "\n\n=== ADDRESS & CONTACT INFO FROM OTHER PAGES ===\n"
                                        + contact_snippet
                                    )
                            except Exception as e:
                                logger.debug("Contact page sniff failed for %s: %s", company.get("domain"), e)

                        # Even if crawl failed, try contact extraction from Exa text
                        if not contact_content:
                            contact_content = company.get("exa_text", "")

                        if contact_content:
                            try:
                                people = await extract_contacts_from_content(
                                    company_name=company["title"],
                                    domain=company["domain"],
                                    page_content=contact_content,
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
                                logger.warning("Contact extraction failed for %s: %s", company.get("domain"), ce)

                        # Log Phase 2 results
                        logger.info(
                            "Phase 2 result for %s: crawl_success=%s, content_len=%d, contacts_found=%d",
                            company.get("domain"),
                            deep_crawl.success,
                            len(contact_content),
                            len(extracted_contacts),
                        )

                        # Emit enrichment update for this hot lead
                        if extracted_contacts or (deep_crawl.success and deep_crawl.screenshot_base64):
                            await run.emit({
                                "type": "enrichment",
                                "index": original_index,
                                "company": {
                                    "title": company["title"],
                                    "domain": company["domain"],
                                    "contacts": extracted_contacts,
                                    "has_screenshot": bool(deep_crawl.screenshot_base64),
                                },
                            })

                        # Update the saved lead with contacts if we have a save function
                        if search_id and save_lead_fn and extracted_contacts:
                            try:
                                await save_lead_fn(
                                    search_id,
                                    {"domain": company["domain"], "title": company["title"]},
                                    user_id=user_id,
                                    contacts=extracted_contacts,
                                )
                                logger.info("Saved %d scraped contacts for %s to DB", len(extracted_contacts), company.get("domain"))
                            except Exception as e:
                                logger.error("Failed to update hot lead %s with contacts: %s", company.get("title"), e, exc_info=True)

                    except Exception as e:
                        logger.error("Phase 2 crawl error for %s: %s", company.get("title", "?"), e)

    except Exception as e:
        logger.error("Fatal pipeline error: %s", e)
        await run.emit({
            "type": "error",
            "error": str(e)[:200],
            "fatal": True,
        })
        return stats
    finally:
        # Clean up fallback crawler pool if it was opened
        if fallback_pool:
            try:
                await fallback_pool_cm.__aexit__(None, None, None)
            except Exception:
                pass

    await run.emit({
        "type": "complete",
        "summary": stats,
        "search_id": search_id,
    })

    return stats
