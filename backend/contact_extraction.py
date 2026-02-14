"""
Contact Extraction — LLM-based structured people data from company websites.

Extracts person name, job title, email, phone, LinkedIn URL from /about, /team,
/contact pages using LLM analysis. Prioritizes decision-makers (CEO, VP Sales,
Head of Purchasing, Managing Director).

This module uses content already crawled by the scraper — no additional API cost
beyond the LLM call.
"""

import json
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

from openai import AsyncOpenAI
import httpx

from config import KIMI_API_KEY, KIMI_API_BASE, OPENAI_API_KEY

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPerson:
    """A person extracted from a company website."""
    full_name: str
    job_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None


EXTRACTION_PROMPT = """You are a contact extraction assistant. Extract all people mentioned on this company's web pages.

Focus on DECISION MAKERS — prioritize these roles:
- CEO, CTO, COO, CFO (C-suite)
- VP Sales, VP Marketing, VP Engineering, VP Operations
- Head of Purchasing, Head of Procurement
- Managing Director, General Manager
- Sales Director, Sales Manager
- Founder, Co-Founder, Owner

For each person found, extract:
- full_name: Their full name
- job_title: Their title/role
- email: Their email address (see rules below)
- phone: Their phone number (if shown anywhere on the page)
- linkedin_url: LinkedIn profile URL (if linked)

EMAIL EXTRACTION RULES (IMPORTANT):
1. If the person's email is explicitly shown, use it.
2. If the page has a GENERAL contact email (e.g. info@domain.com, sales@domain.com, contact@domain.com), include it as the person's email — it's better than nothing.
3. If you see OTHER people's emails on the page showing a pattern (e.g. firstname@domain.com or f.lastname@domain.com), try to construct this person's email following the same pattern.
4. If the email uses [at] or (at) or similar obfuscation, reconstruct it (e.g. "john [at] company [dot] com" → "john@company.com").

PHONE EXTRACTION RULES:
1. If the person's direct phone is shown, use it.
2. If there is a general company phone number on the page, include it for the most senior person.
3. Phone numbers should include country code if visible (e.g. +62, +65, +1).
4. Include both landline and mobile if available.

COMPANY: {company_name}
DOMAIN: {domain}

WEB PAGE CONTENT:
{content}

Return ONLY a JSON array of people found. If no people found, return [].
Example:
[
  {{
    "full_name": "John Smith",
    "job_title": "CEO",
    "email": "john@company.com",
    "phone": "+1-555-123-4567",
    "linkedin_url": "https://linkedin.com/in/johnsmith"
  }}
]

IMPORTANT:
- Only include people who actually appear in the content
- Do NOT invent names that aren't on the page
- Include ALL people found, not just decision-makers
- It is OK to assign a general company email/phone to a person if no personal one exists
- Prefer returning an email even if it's generic (info@, sales@) over returning null
"""


async def extract_contacts_from_content(
    company_name: str,
    domain: str,
    page_content: str,
    max_contacts: int = 20,
) -> list[ExtractedPerson]:
    """
    Use LLM to extract structured people data from crawled page content.
    
    Args:
        company_name: Company name for context
        domain: Company domain
        page_content: Markdown content from crawled pages (home + contact/about)
        max_contacts: Maximum number of contacts to extract
    
    Returns:
        List of ExtractedPerson objects
    """
    if not page_content or len(page_content.strip()) < 50:
        return []

    # Truncate content to avoid token limits (8k model, ~4 chars/token ≈ 2k tokens of content)
    content = page_content[:12000]

    prompt = EXTRACTION_PROMPT.format(
        company_name=company_name,
        domain=domain,
        content=content,
    )

    # Try Kimi first, fallback to OpenAI
    result_text = None

    if KIMI_API_KEY:
        try:
            client = AsyncOpenAI(
                api_key=KIMI_API_KEY,
                base_url=KIMI_API_BASE,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
            response = await client.chat.completions.create(
                model="moonshot-v1-8k",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            result_text = response.choices[0].message.content
        except Exception as e:
            logger.warning("Kimi contact extraction failed: %s", e)

    if not result_text and OPENAI_API_KEY:
        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )
            result_text = response.choices[0].message.content
        except Exception as e:
            logger.warning("OpenAI contact extraction failed: %s", e)

    if not result_text:
        return []

    # Parse JSON response
    try:
        # Strip markdown code fences if present
        cleaned = result_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        people_data = json.loads(cleaned)
        if not isinstance(people_data, list):
            return []

        contacts = []
        seen_names = set()
        for person in people_data[:max_contacts]:
            if not isinstance(person, dict):
                continue
            name = (person.get("full_name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            contacts.append(ExtractedPerson(
                full_name=name,
                job_title=(person.get("job_title") or "").strip() or None,
                email=_clean_email(person.get("email")),
                phone=(person.get("phone") or "").strip() or None,
                linkedin_url=_clean_linkedin_url(person.get("linkedin_url")),
            ))

        logger.info(
            "Extracted %d contacts from %s (%s) — %d with email, %d with phone",
            len(contacts), domain, company_name,
            sum(1 for c in contacts if c.email),
            sum(1 for c in contacts if c.phone),
        )
        for c in contacts:
            logger.info(
                "  → %s | %s | email=%s | phone=%s",
                c.full_name, c.job_title or "N/A",
                c.email or "NONE", c.phone or "NONE",
            )
        return contacts

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Failed to parse contact extraction result for %s: %s", domain, e)
        return []


def _clean_email(email: Optional[str]) -> Optional[str]:
    """Validate and clean an extracted email address."""
    if not email:
        return None
    email = email.strip().lower()
    # Basic email validation
    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return email
    return None


def _clean_linkedin_url(url: Optional[str]) -> Optional[str]:
    """Validate and clean a LinkedIn URL."""
    if not url:
        return None
    url = url.strip()
    if "linkedin.com" in url.lower():
        return url
    return None
