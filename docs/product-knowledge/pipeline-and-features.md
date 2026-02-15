# Pipeline And Features

## Discovery Stage

Hunt converts structured ICP intent into semantic web search queries, then discovers candidate companies.

### Supported ICP Inputs
- Industry
- Company profile
- Technology focus
- Qualifying criteria (must-have signals)
- Disqualifiers (optional, must-not-have signals)
- Geographic region (optional)

### Discovery Outputs
- Company name/title
- Domain and website URL
- Search relevance metadata
- Initial company summary when available

## Qualification Stage

Hunt scores each discovered company from `0-100` and assigns one of three tiers:
- `Hot` (`70-100`): strong ICP fit and ready for outreach prioritization.
- `Review` (`40-69`): plausible fit, needs quick human validation.
- `Rejected` (`0-39`): low fit based on available evidence.

Per lead, Hunt stores:
- Score
- Tier
- Reasoning
- Key signals
- Red flags
- Domain and website

## Selective Deep Crawl Stage

Hunt performs deeper crawling primarily on high-value leads to improve contact capture and verification context. This keeps processing focused on likely winners instead of spending equal effort on low-fit accounts.

## Enrichment Stage

Hunt supports contact enrichment workflows and stores contact records on leads.

Typical outputs:
- Full name
- Job title
- Email
- Phone
- LinkedIn URL
- Provider/source tag

Notes:
- Enrichment is most valuable on `Hot` leads.
- Data availability depends on public coverage and provider results.

## Lead Operations

Leads are operationalized in dashboard workflows with status transitions:
- `new`
- `contacted`
- `in_progress`
- `won`
- `lost`
- `archived`

## Saved Hunts And Resume

Each hunt is stored and resumable. Saved state includes:
- ICP context
- Chat messages
- Discovery outputs
- Qualified leads and scoring notes

## Dashboard Modules

- **Hunts**: reopen and resume previous runs.
- **Leads/Pipeline**: filter, sort, inspect, and manage lead status.
- **Map**: geographic lead visualization.
- **Settings**: account, plan, and usage/billing controls.

## Buyer-Facing Summary

Hunt's pipeline is built to improve two things at once:
- lead quality through explicit scoring and tiering.
- team speed through one workflow from discovery to actionable pipeline.
