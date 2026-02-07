"""
Exa AI Lead Discovery Test - Mainrich International
Discovers companies that need permanent magnets & custom motors

Usage:
    python test_exa.py                  # Run all queries
    python test_exa.py --query 1        # Run specific query only
    python test_exa.py --export         # Export results to CSV
"""

import os
import csv
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from exa_py import Exa

# ============================================================
# CONFIG
# ============================================================
EXA_API_KEY = os.getenv("EXA_API_KEY", "")

if not EXA_API_KEY:
    print("❌ No EXA_API_KEY found in .env")
    print("   1. Go to https://dashboard.exa.ai/ and sign up (free $10 credit)")
    print("   2. Copy your API key")
    print("   3. Add EXA_API_KEY=your-key-here to your .env file")
    exit(1)

exa = Exa(api_key=EXA_API_KEY)

# ============================================================
# SEARCH QUERIES - Tailored for Mainrich's ICP
# ============================================================
LEAD_QUERIES = [
    # ---- TIER 1: Dream leads ----
    {
        "id": 1,
        "name": "🤖 Humanoid & Bipedal Robot Companies",
        "query": "humanoid robot company building actuators and motors for robot joints",
        "category": "company",
        "num_results": 15,
    },
    {
        "id": 2,
        "name": "🚁 Drone & eVTOL Manufacturers",
        "query": "drone UAV eVTOL manufacturer building electric propulsion systems with brushless motors",
        "category": "company",
        "num_results": 15,
    },
    {
        "id": 3,
        "name": "🏥 Surgical & Medical Robot Companies",
        "query": "surgical robot medical device company with precision motors and actuators",
        "category": "company",
        "num_results": 10,
    },
    {
        "id": 4,
        "name": "⚡ Motor & Actuator OEMs (Partners)",
        "query": "brushless DC motor manufacturer BLDC servo motor supplier for robotics and automation",
        "category": "company",
        "num_results": 15,
    },
    {
        "id": 5,
        "name": "🚗 EV Powertrain & E-Mobility",
        "query": "electric vehicle powertrain motor manufacturer traction motor permanent magnet",
        "category": "company",
        "num_results": 10,
    },
    # ---- TIER 2: High-value targets ----
    {
        "id": 6,
        "name": "🦾 Industrial Cobots & Automation",
        "query": "collaborative robot cobot manufacturer with servo motors for industrial automation",
        "category": "company",
        "num_results": 10,
    },
    {
        "id": 7,
        "name": "🛰️ Aerospace Actuators & Satellites",
        "query": "satellite reaction wheel aerospace actuator motor manufacturer for space applications",
        "category": "company",
        "num_results": 10,
    },
    {
        "id": 8,
        "name": "🦿 Exoskeleton & Prosthetics",
        "query": "exoskeleton prosthetic limb company building powered actuators and motors",
        "category": "company",
        "num_results": 10,
    },
    # ---- TIER 3: Emerging startups ----
    {
        "id": 9,
        "name": "🧪 Robotics Startups (Series A-C)",
        "query": "robotics startup building hardware robots Series A Series B funding",
        "category": "company",
        "num_results": 15,
    },
    {
        "id": 10,
        "name": "🔬 Lab Automation & Biotech Hardware",
        "query": "lab automation liquid handling robot biotech hardware company with precision motors",
        "category": "company",
        "num_results": 10,
    },
    {
        "id": 11,
        "name": "🛡️ Defense Robotics & Autonomous Systems",
        "query": "defense robotics autonomous ground vehicle unmanned systems manufacturer",
        "category": "company",
        "num_results": 10,
    },
    {
        "id": 12,
        "name": "🌬️ Wind Turbine & Energy Generators",
        "query": "wind turbine direct drive permanent magnet generator manufacturer renewable energy",
        "category": "company",
        "num_results": 10,
    },
]


def run_search(query_config: dict) -> list[dict]:
    """Run a single Exa search and return parsed results."""
    print(f"\n{'='*60}")
    print(f"  {query_config['name']}")
    print(f"  Query: {query_config['query'][:80]}...")
    print(f"{'='*60}")

    try:
        results = exa.search(
            query=query_config["query"],
            type="auto",
            category=query_config.get("category", "company"),
            num_results=query_config.get("num_results", 10),
            contents={
                "text": {"max_characters": 1500},
                "highlights": {"max_characters": 500},
            },
        )
    except Exception as e:
        print(f"  ❌ Search failed: {e}")
        return []

    leads = []
    for i, r in enumerate(results.results, 1):
        # Extract domain from URL
        from urllib.parse import urlparse
        domain = urlparse(r.url).netloc.replace("www.", "")

        lead = {
            "company_url": r.url,
            "domain": domain,
            "title": r.title or "",
            "source_query": query_config["name"],
            "query_id": query_config["id"],
            "text_snippet": (r.text or "")[:300].replace("\n", " ").strip(),
            "highlights": "; ".join(r.highlights) if hasattr(r, 'highlights') and r.highlights else "",
            "exa_score": getattr(r, "score", None),
            "published_date": getattr(r, "published_date", None),
        }
        leads.append(lead)

        score_str = f" (score: {lead['exa_score']:.2f})" if lead['exa_score'] else ""
        print(f"  {i:>2}. {lead['title'][:60]:<60} {domain}{score_str}")

    print(f"\n  → Found {len(leads)} results")
    return leads


def export_to_csv(all_leads: list[dict], filepath: str):
    """Export all leads to CSV for use with lead-qualifier."""
    # Dedupe by domain
    seen = set()
    unique = []
    for lead in all_leads:
        if lead["domain"] not in seen:
            seen.add(lead["domain"])
            unique.append(lead)

    fieldnames = [
        "company_url", "domain", "title", "source_query",
        "text_snippet", "highlights", "exa_score", "published_date"
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(unique)

    print(f"\n✅ Exported {len(unique)} unique leads to {filepath}")
    print(f"   (Deduped from {len(all_leads)} total results)")

    # Also export in lead-qualifier compatible format
    qualifier_path = filepath.replace(".csv", "_for_qualifier.csv")
    with open(qualifier_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "website_url", "contact_name", "linkedin_profile_url"])
        writer.writeheader()
        for lead in unique:
            writer.writerow({
                "company_name": lead["title"].split(" - ")[0].split(" | ")[0].strip(),
                "website_url": f"https://{lead['domain']}",
                "contact_name": "",
                "linkedin_profile_url": "",
            })

    print(f"   Also created {qualifier_path} (ready for lead-qualifier)")


def main():
    parser = argparse.ArgumentParser(description="Exa AI Lead Discovery for Mainrich")
    parser.add_argument("--query", type=int, help="Run specific query by ID (1-12)")
    parser.add_argument("--export", action="store_true", help="Export results to CSV")
    args = parser.parse_args()

    print("🧲 Mainrich Lead Discovery - Powered by Exa AI")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Queries: {len(LEAD_QUERIES)}")

    all_leads = []

    if args.query:
        # Run single query
        query = next((q for q in LEAD_QUERIES if q["id"] == args.query), None)
        if not query:
            print(f"❌ Query ID {args.query} not found (1-{len(LEAD_QUERIES)})")
            return
        leads = run_search(query)
        all_leads.extend(leads)
    else:
        # Run all queries
        for query in LEAD_QUERIES:
            leads = run_search(query)
            all_leads.extend(leads)

    # Summary
    print(f"\n{'='*60}")
    print(f"  📊 SUMMARY")
    print(f"{'='*60}")

    domains = set(l["domain"] for l in all_leads)
    print(f"  Total results: {len(all_leads)}")
    print(f"  Unique domains: {len(domains)}")

    by_query = {}
    for lead in all_leads:
        by_query.setdefault(lead["source_query"], []).append(lead)
    for qname, leads in by_query.items():
        print(f"    {qname}: {len(leads)}")

    # Export
    if args.export or len(all_leads) > 0:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        export_path = f"output/exa_leads_{timestamp}.csv"
        export_to_csv(all_leads, export_path)


if __name__ == "__main__":
    main()
