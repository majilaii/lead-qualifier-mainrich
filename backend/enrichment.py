"""
Enrichment Module — Contact Information Lookup via Hunter.io

Uses Hunter.io Domain Search to find email contacts at a company.
Free plan: 25 searches/month with full API access.

Usage:
  - enrich_contact(domain) → finds best contact at the company
  - enable_api_enrichment(True) → turns on API calls
  - get_enrichment_status() → check if Hunter is configured
"""

from typing import Optional
import logging
import httpx

from models import EnrichmentResult
from config import HUNTER_API_KEY

logger = logging.getLogger(__name__)


async def enrich_contact(
    contact_name: Optional[str],
    company_domain: str,
    linkedin_url: Optional[str] = None,
) -> EnrichmentResult:
    """
    Find contact info for a company using Hunter.io.

    Args:
        contact_name: Optional name of the person to find
        company_domain: Company website domain (e.g. "stripe.com")
        linkedin_url: Unused (kept for interface compatibility)

    Returns:
        EnrichmentResult with email, job_title, and source
    """
    if not HUNTER_API_KEY:
        return EnrichmentResult(enrichment_source="not_configured")

    clean_domain = company_domain.replace("www.", "").replace("https://", "").replace("http://", "").split("/")[0]

    try:
        async with httpx.AsyncClient() as client:
            params: dict = {
                "domain": clean_domain,
                "api_key": HUNTER_API_KEY,
            }

            # If we have a full name (first + last), use Email Finder for precision
            if contact_name and len(contact_name.strip().split()) >= 2:
                name_parts = contact_name.strip().split()
                params["first_name"] = name_parts[0]
                params["last_name"] = " ".join(name_parts[1:])

                resp = await client.get(
                    "https://api.hunter.io/v2/email-finder",
                    params=params,
                    timeout=10.0,
                )

                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    email = data.get("email")
                    if email:
                        logger.debug("Hunter found %s -- %s", contact_name, email)
                        return EnrichmentResult(
                            email=email,
                            job_title=data.get("position"),
                            enrichment_source="hunter",
                        )

            # Domain Search — find the best contact at the company
            resp = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": clean_domain, "api_key": HUNTER_API_KEY},
                timeout=10.0,
            )

            if resp.status_code == 200:
                data = resp.json().get("data", {})
                emails = data.get("emails", [])

                if not emails:
                    logger.debug("Hunter: no emails found for %s", clean_domain)
                    return EnrichmentResult(enrichment_source="not_found")

                # Pick the best contact — prefer senior / decision-maker roles
                best = emails[0]
                for e in emails:
                    dept = (e.get("department") or "").lower()
                    seniority = (e.get("seniority") or "").lower()
                    if dept in ("executive", "management", "engineering", "purchasing") or seniority in ("senior", "director"):
                        best = e
                        break

                email = best.get("value")
                title = best.get("position")
                name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip()

                if email:
                    logger.debug("Hunter found %s -- %s (%s)", name or clean_domain, email, title or 'no title')
                    return EnrichmentResult(
                        email=email,
                        job_title=title,
                        enrichment_source="hunter",
                    )

            elif resp.status_code == 401:
                logger.error("Hunter: invalid API key")
            elif resp.status_code == 429:
                logger.warning("Hunter: rate limit reached (25/month on free plan)")
            else:
                logger.warning("Hunter: HTTP %d", resp.status_code)

    except Exception as e:
        logger.error("Hunter error: %s", e)

    return EnrichmentResult(enrichment_source="not_found")


def get_enrichment_status() -> dict:
    """Get current enrichment configuration status."""
    configured = bool(HUNTER_API_KEY)
    providers = ["hunter"] if configured else []
    return {
        "hunter_configured": configured,
        "mode": "hunter" if configured else "manual",
        "providers": providers,
    }


if __name__ == "__main__":
    import asyncio

    async def test():
        print("Status:", get_enrichment_status())
        result = await enrich_contact(None, "stripe.com")
        print(f"Result: {result}")

    asyncio.run(test())
