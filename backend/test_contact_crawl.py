"""
Test script: Verify that contact/about page crawling finds real addresses.

Usage:
    python test_contact_crawl.py

Tests a few known company sites and checks whether the contact page
sniffing finds address-like content that the homepage alone misses.
"""

import asyncio
import sys
import os

# Ensure we can import from the backend directory
sys.path.insert(0, os.path.dirname(__file__))

from scraper import CrawlerPool, _extract_address_lines


# ── Test sites where address is typically on /contact, not homepage ──
TEST_SITES = [
    {
        "url": "https://www.thebuttsdental.co.uk",
        "name": "The Butts Dental (Brentford)",
        "expected_snippet": "TW8",  # Postcode TW8 8DL
    },
    {
        "url": "https://www.haascnc.com",
        "name": "Haas CNC (Oxnard, CA)",
        "expected_snippet": "Oxnard",  # HQ in Oxnard, CA
    },
    {
        "url": "https://www.sick.com",
        "name": "SICK AG (Waldkirch, Germany)",
        "expected_snippet": "Waldkirch",  # HQ in Waldkirch
    },
    {
        "url": "https://www.igus.co.uk",
        "name": "igus UK (Northampton)",
        "expected_snippet": "Northampton",  # UK office
    },
]


async def test_one(pool: CrawlerPool, site: dict) -> dict:
    """Test contact page crawling for a single site."""
    url = site["url"]
    name = site["name"]
    expected = site.get("expected_snippet", "")

    print(f"\n{'='*60}")
    print(f"🔍  {name}")
    print(f"    URL: {url}")
    print(f"    Looking for: '{expected}'")
    print(f"{'='*60}")

    # 1. Crawl homepage
    print("\n  📄 Homepage crawl...")
    home_result = await pool.crawl(url, take_screenshot=False)
    home_has_address = False
    if home_result.success and home_result.markdown_content:
        home_has_address = expected.lower() in home_result.markdown_content.lower() if expected else False
        print(f"     ✅ Success — {len(home_result.markdown_content)} chars")
        print(f"     {'✅' if home_has_address else '❌'} Homepage contains '{expected}': {home_has_address}")
    else:
        print(f"     ❌ Failed: {home_result.error_message}")

    # 2. Crawl contact pages
    print("\n  📬 Contact page sniff...")
    contact_snippet = await pool.crawl_contact_pages(url)
    contact_has_address = False
    if contact_snippet:
        contact_has_address = expected.lower() in contact_snippet.lower() if expected else False
        print(f"     ✅ Found content — {len(contact_snippet)} chars")
        print(f"     {'✅' if contact_has_address else '❌'} Contact pages contain '{expected}': {contact_has_address}")
        # Print the actual snippet (truncated)
        preview = contact_snippet[:500].replace('\n', '\n        ')
        print(f"\n     📋 Preview:\n        {preview}")
        if len(contact_snippet) > 500:
            print(f"        ... ({len(contact_snippet) - 500} more chars)")
    else:
        print(f"     ❌ No address content found on secondary pages")

    # 3. Verdict
    improved = not home_has_address and contact_has_address
    print(f"\n  📊 Verdict: {'🎉 IMPROVED — address found on contact page but NOT homepage!' if improved else '➡️  No improvement (address was already on homepage or still not found)'}")

    return {
        "name": name,
        "home_has_address": home_has_address,
        "contact_has_address": contact_has_address,
        "improved": improved,
        "contact_snippet_len": len(contact_snippet) if contact_snippet else 0,
    }


async def main():
    print("🧪 Contact Page Crawl Test")
    print("=" * 60)
    print(f"Testing {len(TEST_SITES)} sites...\n")

    results = []
    async with CrawlerPool() as pool:
        for site in TEST_SITES:
            try:
                result = await test_one(pool, site)
                results.append(result)
            except Exception as e:
                print(f"\n  💥 Error testing {site['name']}: {e}")
                results.append({
                    "name": site["name"],
                    "home_has_address": False,
                    "contact_has_address": False,
                    "improved": False,
                    "error": str(e),
                })

    # Summary
    print(f"\n\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    improved = sum(1 for r in results if r.get("improved"))
    already_ok = sum(1 for r in results if r.get("home_has_address"))
    not_found = sum(1 for r in results if not r.get("home_has_address") and not r.get("contact_has_address"))

    for r in results:
        status = "🎉 IMPROVED" if r.get("improved") else ("✅ Already on homepage" if r.get("home_has_address") else "❌ Not found")
        print(f"  {r['name']:40s} {status}")

    print(f"\n  Total: {len(results)} sites tested")
    print(f"  🎉 Improved by contact crawl: {improved}")
    print(f"  ✅ Already had address on homepage: {already_ok}")
    print(f"  ❌ Address not found anywhere: {not_found}")


if __name__ == "__main__":
    asyncio.run(main())
