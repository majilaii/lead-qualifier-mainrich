"""
LinkedIn Enrichment — People Data Labs API for decision-maker lookup.

For leads scoring 8+, finds decision-makers' LinkedIn profiles
programmatically. No Sales Navigator subscription needed.

Supports People Data Labs (PDL) and RocketReach as providers.
Only triggered on hot leads to keep costs low (~$0.01-0.05/lookup).

Usage:
    from linkedin_enrichment import enrich_linkedin, get_linkedin_status
    
    contacts = await enrich_linkedin("acme.com")
    status = get_linkedin_status()
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

import httpx

from config import PDL_API_KEY, ROCKETREACH_API_KEY

logger = logging.getLogger(__name__)


@dataclass
class LinkedInContact:
    """A person found via LinkedIn enrichment."""
    full_name: str
    job_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str = "pdl"  # pdl | rocketreach


# Decision-maker titles to prioritize
_DECISION_MAKER_TITLES = [
    "ceo", "chief executive", "chief technology", "cto", "coo", "cfo",
    "managing director", "general manager", "founder", "co-founder", "owner",
    "vp", "vice president", "director", "head of",
    "president",
    "purchasing", "procurement", "buying",
    "sales", "business development",
]


def _is_decision_maker(title: str) -> bool:
    """Check if a job title indicates a decision-maker."""
    if not title:
        return False
    lower = title.lower()
    return any(t in lower for t in _DECISION_MAKER_TITLES)


def _sort_by_seniority(contacts: list[LinkedInContact]) -> list[LinkedInContact]:
    """Sort contacts by seniority — C-suite first, then VP, then Director."""
    def score(c: LinkedInContact) -> int:
        t = (c.job_title or "").lower()
        if any(x in t for x in ["ceo", "chief executive", "founder", "owner", "president"]):
            return 0
        if any(x in t for x in ["cto", "coo", "cfo", "chief"]):
            return 1
        if any(x in t for x in ["managing director", "general manager"]):
            return 2
        if any(x in t for x in ["vp", "vice president"]):
            return 3
        if "director" in t or "head of" in t:
            return 4
        if "manager" in t:
            return 5
        return 6
    return sorted(contacts, key=score)


async def enrich_linkedin_pdl(domain: str, max_results: int = 5) -> list[LinkedInContact]:
    """
    Find decision-makers at a company using People Data Labs Company Enrichment API.
    
    Args:
        domain: Company website domain (e.g. "acme.com")
        max_results: Maximum number of contacts to return
    
    Returns:
        List of LinkedInContact objects sorted by seniority
    """
    if not PDL_API_KEY:
        return []

    clean_domain = domain.replace("www.", "").replace("https://", "").replace("http://", "").split("/")[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: Search for people at the company using Elasticsearch query
            resp = await client.post(
                "https://api.peopledatalabs.com/v5/person/search",
                json={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"job_company_website": clean_domain}},
                            ]
                        }
                    },
                    "size": 20,
                    "dataset": "all",
                    "titlecase": True,
                },
                headers={
                    "X-Api-Key": PDL_API_KEY,
                    "Content-Type": "application/json",
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                people = data.get("data", [])

                contacts = []
                for person in people:
                    name = person.get("full_name", "").strip()
                    if not name:
                        continue

                    title = person.get("job_title", "").strip()
                    linkedin = person.get("linkedin_url") or ""
                    # Ensure LinkedIn URL is fully qualified
                    if linkedin and not linkedin.startswith("http"):
                        linkedin = f"https://{linkedin}"
                    email = None
                    phone = None

                    # Get work email — prefer top-level work_email field first
                    # Note: on free/basic PDL plans, contact fields may be
                    # boolean (True = data exists but obfuscated, False = no data)
                    raw_work_email = person.get("work_email")
                    if isinstance(raw_work_email, str) and "@" in raw_work_email:
                        email = raw_work_email

                    if not email:
                        # Fall back to emails array — prefer professional type
                        raw_emails = person.get("emails")
                        if isinstance(raw_emails, list):
                            for e in raw_emails:
                                if isinstance(e, dict) and e.get("type") in ("professional", "current_professional"):
                                    email = e.get("address")
                                    break
                            if not email and raw_emails:
                                first = raw_emails[0]
                                email = first.get("address") if isinstance(first, dict) else None

                    # Get phone — prefer mobile_phone, then phone_numbers array
                    raw_mobile = person.get("mobile_phone")
                    if isinstance(raw_mobile, str) and len(raw_mobile) > 5:
                        phone = raw_mobile
                    if not phone:
                        raw_phones = person.get("phone_numbers")
                        if isinstance(raw_phones, list) and raw_phones:
                            first_phone = raw_phones[0]
                            if isinstance(first_phone, str):
                                phone = first_phone

                    contacts.append(LinkedInContact(
                        full_name=name,
                        job_title=title or None,
                        email=email,
                        phone=phone,
                        linkedin_url=linkedin or None,
                        source="pdl",
                    ))

                # Filter to decision-makers first, then fill with others
                decision_makers = [c for c in contacts if _is_decision_maker(c.job_title)]
                others = [c for c in contacts if not _is_decision_maker(c.job_title)]

                result = _sort_by_seniority(decision_makers)[:max_results]
                remaining = max_results - len(result)
                if remaining > 0:
                    result.extend(others[:remaining])

                logger.info("PDL found %d contacts for %s (%d decision-makers)",
                           len(result), clean_domain, len(decision_makers))
                return result

            elif resp.status_code == 401:
                logger.error("PDL: Invalid API key")
            elif resp.status_code == 402:
                logger.warning("PDL: Insufficient credits")
            elif resp.status_code == 429:
                logger.warning("PDL: Rate limit exceeded")
            else:
                logger.warning("PDL: HTTP %d — %s", resp.status_code, resp.text[:200])

    except Exception as e:
        logger.error("PDL enrichment error for %s: %s", clean_domain, e)

    return []


async def enrich_linkedin_rocketreach(domain: str, max_results: int = 5) -> list[LinkedInContact]:
    """
    Find decision-makers at a company using RocketReach Lookup API.
    
    Args:
        domain: Company website domain
        max_results: Maximum number of contacts to return
    
    Returns:
        List of LinkedInContact objects sorted by seniority
    """
    if not ROCKETREACH_API_KEY:
        return []

    clean_domain = domain.replace("www.", "").replace("https://", "").replace("http://", "").split("/")[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.rocketreach.co/v2/api/search",
                params={
                    "current_employer": clean_domain,
                    "page_size": 20,
                },
                headers={
                    "Api-Key": ROCKETREACH_API_KEY,
                    "Content-Type": "application/json",
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                profiles = data.get("profiles", [])

                contacts = []
                for person in profiles:
                    name = person.get("name", "").strip()
                    if not name:
                        continue

                    contacts.append(LinkedInContact(
                        full_name=name,
                        job_title=person.get("current_title"),
                        email=person.get("current_work_email") or person.get("email"),
                        phone=person.get("phone"),
                        linkedin_url=person.get("linkedin_url"),
                        source="rocketreach",
                    ))

                decision_makers = [c for c in contacts if _is_decision_maker(c.job_title)]
                others = [c for c in contacts if not _is_decision_maker(c.job_title)]

                result = _sort_by_seniority(decision_makers)[:max_results]
                remaining = max_results - len(result)
                if remaining > 0:
                    result.extend(others[:remaining])

                logger.info("RocketReach found %d contacts for %s", len(result), clean_domain)
                return result

            elif resp.status_code == 401:
                logger.error("RocketReach: Invalid API key")
            elif resp.status_code == 429:
                logger.warning("RocketReach: Rate limit exceeded")
            else:
                logger.warning("RocketReach: HTTP %d", resp.status_code)

    except Exception as e:
        logger.error("RocketReach enrichment error for %s: %s", clean_domain, e)

    return []


async def enrich_linkedin(domain: str, max_results: int = 5) -> list[LinkedInContact]:
    """
    Find decision-makers at a company using the best available provider.
    Tries PDL first, falls back to RocketReach.
    
    Args:
        domain: Company website domain
        max_results: Max contacts to return
    
    Returns:
        List of LinkedInContact objects
    """
    if PDL_API_KEY:
        contacts = await enrich_linkedin_pdl(domain, max_results)
        if contacts:
            return contacts

    if ROCKETREACH_API_KEY:
        contacts = await enrich_linkedin_rocketreach(domain, max_results)
        if contacts:
            return contacts

    return []


def get_linkedin_status() -> dict:
    """Get configuration status for LinkedIn enrichment."""
    pdl = bool(PDL_API_KEY)
    rr = bool(ROCKETREACH_API_KEY)
    providers = []
    if pdl:
        providers.append("pdl")
    if rr:
        providers.append("rocketreach")

    return {
        "available": pdl or rr,
        "pdl_configured": pdl,
        "rocketreach_configured": rr,
        "providers": providers,
    }
