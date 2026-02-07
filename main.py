"""
Main Orchestrator — The Magnet Hunter
AI-Powered B2B Lead Qualification Pipeline

This is the entry point. It loads leads from CSV, then for each lead:
  1. Crawls the company website (scraper.py)
  2. Qualifies via LLM analysis (intelligence.py)
  3. Optionally runs deep research (deep_research.py)
  4. Optionally enriches contacts (enrichment.py)
  5. Writes results to output/ CSVs sorted by score tier

Usage:
    python main.py --test                    # Test with sample companies
    python main.py --input leads.csv         # Process your own CSV
    python main.py --input leads.csv --deep-research  # With deep research
    python main.py --no-vision               # Text-only (cheaper)
    python main.py --clear-checkpoint        # Start fresh
"""

import asyncio
import argparse
import csv
from pathlib import Path
from datetime import datetime

from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel

from models import LeadInput, ProcessedLead, ProcessingStats, QualificationTier, QualificationResult
from scraper import crawl_company
from intelligence import LeadQualifier
from enrichment import enrich_contact, get_enrichment_status
from utils import (
    CheckpointManager,
    OutputWriter,
    CostTracker,
    determine_tier,
    dedupe_by_domain,
    print_lead_summary,
    extract_domain
)
from config import (
    INPUT_FILE,
    OUTPUT_DIR,
    CONCURRENCY_LIMIT,
    SCORE_HOT_LEAD,
    QUALIFIED_FILE,
    REVIEW_FILE,
    REJECTED_FILE,
)
from deep_research import DeepResearcher, print_report as print_deep_report

console = Console()


def load_leads(file_path: Path) -> list[LeadInput]:
    """Load leads from CSV file."""
    if not file_path.exists():
        console.print(f"[red]Error: Input file not found: {file_path}[/red]")
        console.print("[yellow]Create input_leads.csv with columns: company_name, website_url, contact_name, linkedin_profile_url[/yellow]")
        return []
    
    # Domains that are NOT real company websites (social/news/aggregator sites)
    BLOCKED_DOMAINS = {
        "linkedin.com", "linktr.ee", "twitter.com", "facebook.com",
        "youtube.com", "instagram.com", "tiktok.com", "reddit.com",
        "therobotreport.com", "roboticstomorrow.com", "thundersaidenergy.com",
        "wikipedia.org", "crunchbase.com", "bloomberg.com", "techcrunch.com",
        "github.com", "medium.com",
    }
    
    leads = []
    skipped = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            # Handle various column name formats
            lead = LeadInput(
                company_name=row.get('company_name') or row.get('Company Name') or row.get('company', ''),
                website_url=row.get('website_url') or row.get('Website') or row.get('website', ''),
                contact_name=row.get('contact_name') or row.get('Contact Name') or row.get('Full Name'),
                linkedin_profile_url=row.get('linkedin_profile_url') or row.get('LinkedIn URL') or row.get('linkedin'),
                row_index=i
            )
            
            # Skip rows without required data
            if not lead.company_name or not lead.website_url:
                continue
            
            # Skip non-company domains (social media, news sites, etc.)
            domain = extract_domain(lead.website_url)
            if any(domain == bd or domain.endswith('.' + bd) for bd in BLOCKED_DOMAINS):
                skipped.append(f"{lead.company_name} ({domain})")
                continue
            
            leads.append(lead)
    
    if skipped:
        console.print(f"[yellow]Filtered out {len(skipped)} non-company URLs:[/yellow]")
        for s in skipped:
            console.print(f"  [dim]• {s}[/dim]")
    
    return leads


async def process_lead(
    lead: LeadInput,
    qualifier: LeadQualifier,
    output_writer: OutputWriter,
    checkpoint: CheckpointManager,
    cost_tracker: CostTracker,
    use_vision: bool = True,
    auto_enrich: bool = False,
    deep_research: bool = False,
    deep_researcher: DeepResearcher = None
) -> ProcessedLead:
    """Process a single lead through the pipeline."""
    
    # Step 1: Crawl website
    crawl_result = await crawl_company(lead.website_url, take_screenshot=use_vision)
    
    if not crawl_result.success:
        # Website failed to crawl - send to REVIEW queue, not rejected.
        # Crawl failure doesn't mean the company is irrelevant — it often means
        # the site has bot protection (Cloudflare, etc.)
        # Use keyword check on company name to give a rough score
        name_lower = lead.company_name.lower()
        from config import POSITIVE_KEYWORDS
        has_positive = any(kw.lower() in name_lower for kw in POSITIVE_KEYWORDS)
        score = 6 if has_positive else 5  # Default to review range (4-7)
        
        processed = ProcessedLead(
            company_name=lead.company_name,
            website_url=lead.website_url,
            contact_name=lead.contact_name,
            linkedin_profile_url=lead.linkedin_profile_url,
            qualification_tier=QualificationTier.REVIEW,
            confidence_score=score,
            is_qualified=False,
            reasoning=f"Website could not be crawled — manual review needed. Error: {crawl_result.error_message}",
            red_flags=["Crawl failed - needs manual website visit"],
            crawl_success=False,
            error_message=crawl_result.error_message
        )
    else:
        # Step 2: Qualify with LLM
        try:
            qual_result = await qualifier.qualify_lead(
                company_name=lead.company_name,
                website_url=lead.website_url,
                crawl_result=crawl_result,
                use_vision=use_vision
            )
        except Exception as e:
            print(f"  ❌ LLM qualification error for {lead.company_name}: {e}")
            qual_result = QualificationResult(
                is_qualified=False,
                confidence_score=3,
                reasoning=f"LLM analysis failed: {type(e).__name__}: {str(e)[:100]}",
                red_flags=["AI qualification error - needs manual review"]
            )
        
        # Determine tier
        tier = determine_tier(qual_result.confidence_score)
        
        # Step 3: Enrich if hot lead and auto-enrich enabled
        email = None
        mobile = None
        deep_research_result = None
        
        if auto_enrich and tier == QualificationTier.HOT:
            domain = extract_domain(lead.website_url)
            enrichment = await enrich_contact(
                contact_name=lead.contact_name,
                company_domain=domain,
                linkedin_url=lead.linkedin_profile_url
            )
            email = enrichment.email
            mobile = enrichment.mobile_number
        
        # Step 4: Deep research for hot leads
        if deep_research and tier == QualificationTier.HOT and deep_researcher:
            console.print(f"[cyan]🔬 Performing deep research on {lead.company_name}...[/cyan]")
            dr_result = await deep_researcher.research_company(
                company_name=lead.company_name,
                website_url=lead.website_url
            )
            print_deep_report(dr_result)
            # Convert to dict for storage
            from dataclasses import asdict
            deep_research_result = asdict(dr_result)
        
        processed = ProcessedLead(
            company_name=lead.company_name,
            website_url=lead.website_url,
            contact_name=lead.contact_name,
            linkedin_profile_url=lead.linkedin_profile_url,
            qualification_tier=tier,
            confidence_score=qual_result.confidence_score,
            is_qualified=qual_result.is_qualified,
            hardware_type=qual_result.hardware_type,
            industry_category=qual_result.industry_category,
            reasoning=qual_result.reasoning,
            key_signals=qual_result.key_signals,
            red_flags=qual_result.red_flags,
            email=email,
            mobile_number=mobile,
            crawl_success=True,
            deep_research=deep_research_result
        )
    
    # Save to appropriate output file
    output_writer.write_lead(processed)
    
    # Update checkpoint
    checkpoint.mark_processed(lead.website_url)
    checkpoint.save_checkpoint()
    
    return processed


async def run_pipeline(
    leads: list[LeadInput],
    use_vision: bool = True,
    auto_enrich: bool = False,
    clear_checkpoint: bool = False,
    deep_research: bool = False
):
    """Run the full qualification pipeline."""
    
    # Initialize components
    qualifier = LeadQualifier()
    checkpoint = CheckpointManager()
    output_writer = OutputWriter()
    cost_tracker = CostTracker()
    stats = ProcessingStats(total_leads=len(leads))
    
    # Initialize deep researcher if enabled
    deep_researcher = DeepResearcher() if deep_research else None
    
    if clear_checkpoint:
        checkpoint.clear()
        # Also clear output files so stale data doesn't pile up
        for f in [QUALIFIED_FILE, REVIEW_FILE, REJECTED_FILE]:
            if f.exists():
                f.unlink()
        output_writer = OutputWriter()  # Re-init to recreate headers
        console.print("[yellow]Checkpoint and output files cleared - starting fresh[/yellow]")
    
    # Dedupe by domain
    leads = dedupe_by_domain(leads)
    
    # Filter out already processed
    leads_to_process = [
        lead for lead in leads 
        if not checkpoint.is_processed(lead.website_url)
    ]
    
    skipped = len(leads) - len(leads_to_process)
    if skipped > 0:
        console.print(f"[green]Skipping {skipped} already processed leads[/green]")
    
    if not leads_to_process:
        console.print("[yellow]No new leads to process![/yellow]")
        return stats
    
    # Show configuration
    enrichment_status = get_enrichment_status()
    console.print(Panel(f"""
[bold]The Magnet Hunter - Lead Qualification Pipeline[/bold]
[cyan]Mainrich International[/cyan]

Leads to process: {len(leads_to_process)}
Vision analysis: {'Enabled' if use_vision else 'Disabled'}
Auto-enrich: {'Enabled' if auto_enrich else 'Disabled (Manual Mode)'}
Deep research: {'Enabled (hot leads)' if deep_research else 'Disabled'}
Enrichment mode: {enrichment_status['mode']}
Concurrency: {CONCURRENCY_LIMIT}
    """, title="Configuration"))
    
    # Process with progress bar
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    
    async def process_with_semaphore(lead: LeadInput) -> ProcessedLead:
        async with semaphore:
            return await process_lead(
                lead=lead,
                qualifier=qualifier,
                output_writer=output_writer,
                checkpoint=checkpoint,
                cost_tracker=cost_tracker,
                use_vision=use_vision,
                auto_enrich=auto_enrich,
                deep_research=deep_research,
                deep_researcher=deep_researcher
            )
    
    # Use tqdm for progress
    results = []
    for lead in tqdm(leads_to_process, desc="Qualifying leads", unit="lead"):
        try:
            result = await process_with_semaphore(lead)
            results.append(result)
        except (asyncio.CancelledError, KeyboardInterrupt):
            console.print(f"\n[yellow]⚠️ Interrupted! Saving progress ({len(results)} leads processed)...[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]❌ Error on {lead.company_name}: {e}[/red]")
            # Create a fallback result so we don't lose this lead
            result = ProcessedLead(
                company_name=lead.company_name,
                website_url=lead.website_url,
                contact_name=lead.contact_name,
                linkedin_profile_url=lead.linkedin_profile_url,
                qualification_tier=QualificationTier.REVIEW,
                confidence_score=3,
                is_qualified=False,
                reasoning=f"Processing error: {type(e).__name__}: {str(e)[:100]}",
                crawl_success=False,
                error_message=str(e)[:200]
            )
            results.append(result)
        
        # Update stats for every result
        if results:
            last = results[-1]
            stats.processed += 1
            if last.qualification_tier == QualificationTier.HOT:
                stats.hot_leads += 1
            elif last.qualification_tier == QualificationTier.REVIEW:
                stats.review_leads += 1
            else:
                stats.rejected_leads += 1
            if not last.crawl_success:
                stats.crawl_failures += 1
            if last.qualification_tier == QualificationTier.HOT:
                print_lead_summary(last)
        
        # Small delay between requests
        await asyncio.sleep(0.5)
    
    # Final stats
    stats.total_input_tokens = qualifier.total_input_tokens
    stats.total_output_tokens = qualifier.total_output_tokens
    stats.estimated_cost_usd = qualifier.get_cost_estimate()
    
    console.print(stats.summary())
    
    # Show output file locations
    console.print(f"\n[green]Output files:[/green]")
    console.print(f"  🔥 Hot leads: {OUTPUT_DIR / 'qualified_hot_leads.csv'}")
    console.print(f"  🔍 Review queue: {OUTPUT_DIR / 'review_manual_check.csv'}")
    console.print(f"  ❌ Rejected: {OUTPUT_DIR / 'rejected_with_reasons.csv'}")
    
    return stats


async def run_test(deep_research: bool = False):
    """Test with sample companies."""
    console.print("[yellow]Running test with sample companies...[/yellow]\n")
    
    test_companies = [
        LeadInput(
            company_name="Boston Dynamics",
            website_url="https://www.bostondynamics.com",
            row_index=0
        ),
        LeadInput(
            company_name="Figure AI",
            website_url="https://www.figure.ai", 
            row_index=1
        ),
        LeadInput(
            company_name="Maxon Group",
            website_url="https://www.maxongroup.com",
            contact_name="John Doe",
            row_index=2
        ),
        # Negative test case
        LeadInput(
            company_name="Random Marketing Agency",
            website_url="https://www.hubspot.com",
            row_index=3
        ),
    ]
    
    await run_pipeline(
        test_companies, 
        use_vision=True, 
        clear_checkpoint=True,
        deep_research=deep_research
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="The Magnet Hunter - B2B Lead Qualification Tool"
    )
    parser.add_argument(
        "--test", 
        action="store_true",
        help="Run test with sample companies"
    )
    parser.add_argument(
        "--clear-checkpoint",
        action="store_true", 
        help="Clear checkpoint and start fresh"
    )
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="Disable vision analysis (text-only, cheaper)"
    )
    parser.add_argument(
        "--auto-enrich",
        action="store_true",
        help="Enable auto-enrichment for hot leads (requires API keys)"
    )
    parser.add_argument(
        "--deep-research",
        action="store_true",
        help="Enable deep research for hot leads (crawls more pages, extracts detailed intel)"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Custom input CSV file path"
    )
    
    args = parser.parse_args()
    
    console.print("""
[bold cyan]╔══════════════════════════════════════════════════╗
║  🧲 THE MAGNET HUNTER                             ║
║  AI-Powered B2B Lead Qualification Pipeline       ║
╚══════════════════════════════════════════════════╝[/bold cyan]
    """)
    
    if args.test:
        asyncio.run(run_test(deep_research=args.deep_research))
    else:
        # Load leads from CSV
        input_file = Path(args.input) if args.input else INPUT_FILE
        leads = load_leads(input_file)
        
        if not leads:
            return
        
        console.print(f"[green]Loaded {len(leads)} leads from {input_file}[/green]\n")
        
        asyncio.run(run_pipeline(
            leads=leads,
            use_vision=not args.no_vision,
            auto_enrich=args.auto_enrich,
            clear_checkpoint=args.clear_checkpoint,
            deep_research=args.deep_research
        ))


if __name__ == "__main__":
    main()
