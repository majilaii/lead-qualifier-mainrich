-- =============================================
-- Tier 2 Migration: Scheduled Pipelines, Notifications,
-- AI Email Drafts, Re-qualification Alerts
-- =============================================

-- 1. Add notification_prefs JSONB column to profiles
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{"pipeline_complete": true, "scheduled_run": true, "requalification": true, "weekly_digest": false}'::jsonb;

-- 2. Add email_drafts_used to usage_tracking
ALTER TABLE usage_tracking
ADD COLUMN IF NOT EXISTS email_drafts_used INTEGER DEFAULT 0;

-- 3. Create lead_snapshots table
CREATE TABLE IF NOT EXISTS lead_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES qualified_leads(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,
    reasoning TEXT DEFAULT '',
    key_signals JSONB,
    snapshot_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lead_snapshots_lead_id ON lead_snapshots(lead_id);

-- 4. Create pipeline_schedules table
CREATE TABLE IF NOT EXISTS pipeline_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    pipeline_config JSONB NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_running BOOLEAN DEFAULT FALSE,
    run_at_hour INTEGER DEFAULT 9,
    timezone VARCHAR(50) DEFAULT 'UTC',
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ NOT NULL,
    last_run_id UUID,
    run_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pipeline_schedules_user_id ON pipeline_schedules(user_id);
CREATE INDEX IF NOT EXISTS ix_schedules_next_run_active ON pipeline_schedules(next_run_at)
    WHERE is_active = TRUE AND is_running = FALSE;
