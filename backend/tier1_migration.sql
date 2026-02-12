-- ============================================================
-- Tier 1 Power Features Migration
-- Run in Supabase SQL Editor after the initial migration.
-- ============================================================

-- 1. Lead Contacts — structured people data from websites & enrichment APIs
CREATE TABLE IF NOT EXISTS lead_contacts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id      UUID NOT NULL REFERENCES qualified_leads(id) ON DELETE CASCADE,
    full_name    TEXT,
    job_title    TEXT,
    email        TEXT,
    phone        TEXT,
    linkedin_url TEXT,
    source       TEXT NOT NULL DEFAULT 'website',  -- website | hunter | pdl | rocketreach
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lead_contacts_lead ON lead_contacts(lead_id);
CREATE INDEX IF NOT EXISTS ix_lead_contacts_email ON lead_contacts(email) WHERE email IS NOT NULL;

-- 2. Search Templates — saved ICP presets
CREATE TABLE IF NOT EXISTS search_templates (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    search_context JSONB NOT NULL,
    is_builtin     BOOLEAN NOT NULL DEFAULT false,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_search_templates_user ON search_templates(user_id);

-- 3. Lead Snapshots — historical score tracking for re-qualification
CREATE TABLE IF NOT EXISTS lead_snapshots (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id     UUID NOT NULL REFERENCES qualified_leads(id) ON DELETE CASCADE,
    score       INTEGER NOT NULL,
    tier        TEXT NOT NULL,
    reasoning   TEXT NOT NULL DEFAULT '',
    key_signals JSONB,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lead_snapshots_lead ON lead_snapshots(lead_id);

-- 4. Add user_id + last_seen_at to qualified_leads for global dedup
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES profiles(id);
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT now();

-- Backfill user_id from search → profile
UPDATE qualified_leads ql
SET user_id = s.user_id
FROM searches s
WHERE ql.search_id = s.id
AND ql.user_id IS NULL;

-- Deduplicate: keep the highest-scored row per (user_id, domain), delete the rest
DELETE FROM qualified_leads
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, domain
                   ORDER BY score DESC NULLS LAST, created_at DESC NULLS LAST
               ) AS rn
        FROM qualified_leads
        WHERE user_id IS NOT NULL
    ) ranked
    WHERE rn > 1
);

-- Create index for global dedup (domain per user)
CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_user_domain
    ON qualified_leads(user_id, domain)
    WHERE user_id IS NOT NULL;

-- 5. Add linkedin_lookups to usage_tracking
ALTER TABLE usage_tracking ADD COLUMN IF NOT EXISTS linkedin_lookups INTEGER NOT NULL DEFAULT 0;

-- 6. RLS for new tables
ALTER TABLE lead_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE search_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own contacts" ON lead_contacts FOR ALL
    USING (lead_id IN (
        SELECT ql.id FROM qualified_leads ql
        JOIN searches s ON ql.search_id = s.id
        WHERE s.user_id = auth.uid()
    ));

CREATE POLICY "Users can manage own templates" ON search_templates FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Users can view own snapshots" ON lead_snapshots FOR ALL
    USING (lead_id IN (
        SELECT ql.id FROM qualified_leads ql
        JOIN searches s ON ql.search_id = s.id
        WHERE s.user_id = auth.uid()
    ));

-- Service role bypass for lead_contacts (backend inserts)
CREATE POLICY "Service can manage contacts" ON lead_contacts FOR ALL
    USING (true) WITH CHECK (true);
CREATE POLICY "Service can manage snapshots" ON lead_snapshots FOR ALL
    USING (true) WITH CHECK (true);
