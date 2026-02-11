-- ============================================================
-- Supabase Migration — Lead Qualifier tables
--
-- Run this in your Supabase SQL Editor (Dashboard → SQL Editor).
-- It creates the app-specific tables and links profiles to
-- Supabase's built-in auth.users table.
-- ============================================================

-- 1. Profiles (linked to auth.users)
CREATE TABLE IF NOT EXISTS profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT UNIQUE,
    display_name TEXT,
    plan_tier   TEXT NOT NULL DEFAULT 'free',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-create a profile when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data ->> 'full_name', NEW.raw_user_meta_data ->> 'name', split_part(NEW.email, '@', 1))
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: runs after every auth.users INSERT
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();


-- 2. Searches
CREATE TABLE IF NOT EXISTS searches (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    industry            TEXT,
    company_profile     TEXT,
    technology_focus    TEXT,
    qualifying_criteria TEXT,
    disqualifiers       TEXT,
    queries_used        JSONB,
    total_found         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_searches_user ON searches(user_id);


-- 3. Qualified Leads
CREATE TABLE IF NOT EXISTS qualified_leads (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id         UUID NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    company_name      TEXT NOT NULL,
    domain            TEXT NOT NULL,
    website_url       TEXT NOT NULL,
    score             INTEGER NOT NULL,
    tier              TEXT NOT NULL,           -- hot, review, rejected
    hardware_type     TEXT,
    industry_category TEXT,
    reasoning         TEXT NOT NULL DEFAULT '',
    key_signals       JSONB,
    red_flags         JSONB,
    deep_research     JSONB,
    country           TEXT,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    status            TEXT NOT NULL DEFAULT 'new',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_leads_search   ON qualified_leads(search_id);
CREATE INDEX IF NOT EXISTS ix_leads_domain   ON qualified_leads(domain);
CREATE INDEX IF NOT EXISTS ix_leads_s_d      ON qualified_leads(search_id, domain);


-- 4. Enrichment Results
CREATE TABLE IF NOT EXISTS enrichment_results (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id    UUID UNIQUE NOT NULL REFERENCES qualified_leads(id) ON DELETE CASCADE,
    email      TEXT,
    phone      TEXT,
    job_title  TEXT,
    source     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- 5. Usage Tracking
CREATE TABLE IF NOT EXISTS usage_tracking (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    year_month       TEXT NOT NULL,             -- "2026-02"
    leads_qualified  INTEGER NOT NULL DEFAULT 0,
    searches_run     INTEGER NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_usage_user_month ON usage_tracking(user_id, year_month);


-- 6. Row Level Security (RLS) — users can only access their own data
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE searches ENABLE ROW LEVEL SECURITY;
ALTER TABLE qualified_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrichment_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read/update their own profile
CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE USING (auth.uid() = id);

-- Searches: users can CRUD their own searches
CREATE POLICY "Users can manage own searches"
    ON searches FOR ALL USING (auth.uid() = user_id);

-- Qualified Leads: accessible via search ownership
CREATE POLICY "Users can manage own leads"
    ON qualified_leads FOR ALL
    USING (search_id IN (SELECT id FROM searches WHERE user_id = auth.uid()));

-- Enrichment Results: accessible via lead → search ownership
CREATE POLICY "Users can manage own enrichment"
    ON enrichment_results FOR ALL
    USING (lead_id IN (
        SELECT ql.id FROM qualified_leads ql
        JOIN searches s ON ql.search_id = s.id
        WHERE s.user_id = auth.uid()
    ));

-- Usage Tracking: users can read their own usage
CREATE POLICY "Users can view own usage"
    ON usage_tracking FOR SELECT USING (auth.uid() = user_id);

-- Allow the backend service role to insert/update usage
-- (The backend uses the service_role key or a direct PostgreSQL connection,
--  which bypasses RLS anyway, but we keep this explicit for clarity.)
CREATE POLICY "Service can manage usage"
    ON usage_tracking FOR ALL
    USING (true)
    WITH CHECK (true);


-- ============================================================
-- Funnel: add notes, deal_value, status_changed_at to qualified_leads
-- ============================================================
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS deal_value DOUBLE PRECISION;
ALTER TABLE qualified_leads ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ DEFAULT NOW();
