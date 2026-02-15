# Hunt Product Overview

Hunt is an AI-powered B2B pipeline acceleration platform. It helps teams move from ICP definition to qualified outreach targets in one connected workflow.

## Core Promise
- Replace manual, inconsistent prospecting with a repeatable AI pipeline.
- Qualify companies with transparent scoring and clear reasoning.
- Turn discovery into action fast with saved hunts, lead workflows, and enrichment.

## Who Hunt Is For
- Founders and sales teams building outbound pipeline.
- SDR and RevOps teams that need consistent lead qualification standards.
- Teams that want faster speed-to-qualified-lead without sacrificing fit quality.

## End-To-End User Flow
1. User defines ideal customer profile (ICP) in plain language.
2. Hunt generates semantic search queries and discovers companies.
3. Hunt qualifies each company with AI scoring and tiering.
4. Teams review, enrich, and work leads from a single dashboard.
5. Hunts and results stay saved and can be resumed anytime.

## Primary Product Surfaces
- **Landing page**: core value proposition and entry points.
- **Chat** (`/chat`): ICP capture, discovery launch, and guided workflow.
- **Dashboard** (`/dashboard`): hunts, leads, map, and settings.

## Business Outcomes Buyers Care About
- Faster pipeline creation from a clear ICP.
- Higher rep focus on high-fit targets instead of list cleaning.
- Explainable qualification outputs (score, reasoning, key signals, red flags).
- Better continuity through saved hunts and resumable sessions.

## Platform Foundations
- Auth/session: Supabase Auth.
- Protected app routes: `/chat`, `/dashboard`.
- Search sessions and chat state: `searches`.
- Lead records and scoring outputs: `qualified_leads`.
- Plan and quota state: `profiles`, `usage_tracking`.

## Sales Positioning Statements
- Hunt helps teams produce qualified pipeline faster with less manual prospecting overhead.
- Hunt combines discovery, qualification, and lead operations so reps spend more time selling.
- Hunt is strongest for teams that need repeatable ICP execution and clear lead prioritization.
