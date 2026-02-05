"""
Enrichment Module - Contact Information Lookup
Currently configured for MANUAL workflow (no API costs)
APIs can be enabled when pipeline is proven
"""

from typing import Optional
from dataclasses import dataclass
import httpx

from models import EnrichmentResult
from config import APOLLO_API_KEY, HUNTER_API_KEY


@dataclass
class EnrichmentConfig:
    """Configuration for enrichment behavior."""
    enable_api_enrichment: bool = False  # Set to True when ready to pay
    apollo_enabled: bool = False
    hunter_enabled: bool = False


# Global config - start with manual mode
ENRICHMENT_CONFIG = EnrichmentConfig(
    enable_api_enrichment=False,
    apollo_enabled=bool(APOLLO_API_KEY),
    hunter_enabled=bool(HUNTER_API_KEY)
)


async def enrich_contact(
    contact_name: Optional[str],
    company_domain: str,
    linkedin_url: Optional[str] = None
) -> EnrichmentResult:
    """
    Attempt to enrich contact information.
    
    Current mode: MANUAL (returns empty result with LinkedIn for manual lookup)
    Enable API enrichment when ready to pay for credits.
    
    Args:
        contact_name: Name of the contact
        company_domain: Company website domain
        linkedin_url: LinkedIn profile URL (for manual lookup)
        
    Returns:
        EnrichmentResult with any found contact info
    """
    
    # MANUAL MODE: Just return what we have for manual lookup
    if not ENRICHMENT_CONFIG.enable_api_enrichment:
        return EnrichmentResult(
            enrichment_source="manual_required"
        )
    
    # API MODE: Try enrichment services (when enabled)
    result = EnrichmentResult()
    
    # Try Apollo first (better coverage)
    if ENRICHMENT_CONFIG.apollo_enabled:
        apollo_result = await _enrich_with_apollo(contact_name, company_domain)
        if apollo_result.email:
            result.email = apollo_result.email
            result.mobile_number = apollo_result.mobile_number
            result.job_title = apollo_result.job_title
            result.enrichment_source = "apollo"
            return result
    
    # Fallback to Hunter
    if ENRICHMENT_CONFIG.hunter_enabled and not result.email:
        hunter_result = await _enrich_with_hunter(contact_name, company_domain)
        if hunter_result.email:
            result.email = hunter_result.email
            result.enrichment_source = "hunter"
            return result
    
    # No enrichment found
    result.enrichment_source = "not_found"
    return result


async def _enrich_with_apollo(
    contact_name: Optional[str],
    company_domain: str
) -> EnrichmentResult:
    """
    Enrich using Apollo.io API.
    
    Apollo API: https://apolloio.github.io/apollo-api-docs/
    Pricing: 50 free credits/month, then $49/mo for 2,400
    """
    if not APOLLO_API_KEY:
        return EnrichmentResult()
    
    try:
        async with httpx.AsyncClient() as client:
            # Apollo people search endpoint
            response = await client.post(
                "https://api.apollo.io/v1/people/match",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache"
                },
                json={
                    "api_key": APOLLO_API_KEY,
                    "name": contact_name,
                    "organization_name": company_domain.replace("www.", "").split(".")[0],
                    "domain": company_domain.replace("www.", "")
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                person = data.get("person", {})
                
                return EnrichmentResult(
                    email=person.get("email"),
                    mobile_number=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                    job_title=person.get("title"),
                    enrichment_source="apollo"
                )
            else:
                print(f"Apollo API error: {response.status_code}")
                return EnrichmentResult()
                
    except Exception as e:
        print(f"Apollo enrichment failed: {e}")
        return EnrichmentResult()


async def _enrich_with_hunter(
    contact_name: Optional[str],
    company_domain: str
) -> EnrichmentResult:
    """
    Enrich using Hunter.io API.
    
    Hunter API: https://hunter.io/api-documentation/v2
    Pricing: 25 free searches/month, then $49/mo for 500
    """
    if not HUNTER_API_KEY:
        return EnrichmentResult()
    
    try:
        async with httpx.AsyncClient() as client:
            # Hunter email finder endpoint
            params = {
                "domain": company_domain.replace("www.", ""),
                "api_key": HUNTER_API_KEY
            }
            
            # If we have a name, use email finder
            if contact_name:
                name_parts = contact_name.split()
                if len(name_parts) >= 2:
                    params["first_name"] = name_parts[0]
                    params["last_name"] = " ".join(name_parts[1:])
                    
                    response = await client.get(
                        "https://api.hunter.io/v2/email-finder",
                        params=params,
                        timeout=10.0
                    )
            else:
                # Domain search (find any email at domain)
                response = await client.get(
                    "https://api.hunter.io/v2/domain-search",
                    params=params,
                    timeout=10.0
                )
            
            if response.status_code == 200:
                data = response.json().get("data", {})
                
                # Handle different response formats
                email = data.get("email") or (data.get("emails", [{}])[0].get("value") if data.get("emails") else None)
                
                return EnrichmentResult(
                    email=email,
                    enrichment_source="hunter"
                )
            else:
                print(f"Hunter API error: {response.status_code}")
                return EnrichmentResult()
                
    except Exception as e:
        print(f"Hunter enrichment failed: {e}")
        return EnrichmentResult()


def enable_api_enrichment(enable: bool = True):
    """Enable or disable API-based enrichment."""
    global ENRICHMENT_CONFIG
    ENRICHMENT_CONFIG.enable_api_enrichment = enable
    print(f"API enrichment {'enabled' if enable else 'disabled'}")


def get_enrichment_status() -> dict:
    """Get current enrichment configuration status."""
    return {
        "api_enrichment_enabled": ENRICHMENT_CONFIG.enable_api_enrichment,
        "apollo_configured": ENRICHMENT_CONFIG.apollo_enabled,
        "hunter_configured": ENRICHMENT_CONFIG.hunter_enabled,
        "mode": "API" if ENRICHMENT_CONFIG.enable_api_enrichment else "MANUAL"
    }


# Test
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Enrichment Status:", get_enrichment_status())
        
        # Test manual mode
        result = await enrich_contact(
            contact_name="John Smith",
            company_domain="bostondynamics.com",
            linkedin_url="https://linkedin.com/in/johnsmith"
        )
        print(f"Result: {result}")
    
    asyncio.run(test())
