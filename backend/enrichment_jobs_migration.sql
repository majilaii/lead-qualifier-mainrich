-- Migration: Add enrichment_jobs table for batch enrichment tracking
-- Run this in your Supabase SQL editor

CREATE TABLE IF NOT EXISTS enrichment_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    action      VARCHAR(50) NOT NULL,              -- recrawl_contacts | requalify | full_recrawl | linkedin
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | running | complete | error | cancelled
    lead_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,       -- array of lead UUIDs to process
    total       INTEGER NOT NULL DEFAULT 0,
    processed   INTEGER NOT NULL DEFAULT 0,
    succeeded   INTEGER NOT NULL DEFAULT 0,
    failed      INTEGER NOT NULL DEFAULT 0,
    results     JSONB,                              -- per-lead results [{lead_id, status, message, ...}]
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_enrichment_jobs_user_status ON enrichment_jobs (user_id, status);

-- Enable RLS
ALTER TABLE enrichment_jobs ENABLE ROW LEVEL SECURITY;

-- Users can only see their own jobs
CREATE POLICY "Users see own enrichment jobs"
    ON enrichment_jobs FOR SELECT
    USING (user_id = auth.uid());

-- Backend service role can do everything
CREATE POLICY "Service role full access on enrichment_jobs"
    ON enrichment_jobs FOR ALL
    USING (true)
    WITH CHECK (true);

-- Grant service role access
GRANT ALL ON enrichment_jobs TO service_role;
