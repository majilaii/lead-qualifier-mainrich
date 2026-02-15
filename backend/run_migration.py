"""Run Tier 2 database migration against Supabase (direct connection, not pooler)."""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

# Parse the DATABASE_URL but switch to direct connection (port 5432, not pooler 6543)
raw_url = os.getenv("DATABASE_URL", "")
# Convert SQLAlchemy URL to plain postgres URL
dsn = raw_url.replace("postgresql+asyncpg://", "postgresql://")
# Use direct connection instead of pooler
dsn = dsn.replace(".pooler.supabase.com:6543", ".supabase.co:5432")
dsn = dsn.replace(".pooler.supabase.com:5432", ".supabase.co:5432")
# Also handle if port isn't specified
if ".pooler.supabase.com/" in dsn:
    dsn = dsn.replace(".pooler.supabase.com/", ".supabase.co:5432/")

MIGRATION_STATEMENTS = [
    # 1. Add notification_prefs column to profiles
    """
    ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{"pipeline_complete": true, "scheduled_run": true, "requalification": true, "weekly_digest": false}'::jsonb;
    """,

    # 2. Add email_drafts_used column to usage_tracking
    """
    ALTER TABLE usage_tracking
    ADD COLUMN IF NOT EXISTS email_drafts_used INTEGER NOT NULL DEFAULT 0;
    """,

    # 3. Create pipeline_schedules table
    """
    CREATE TABLE IF NOT EXISTS pipeline_schedules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        name TEXT,
        search_context JSONB NOT NULL DEFAULT '{}',
        frequency TEXT NOT NULL DEFAULT 'daily',
        run_at_hour INTEGER NOT NULL DEFAULT 8,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        is_running BOOLEAN NOT NULL DEFAULT FALSE,
        next_run_at TIMESTAMPTZ,
        last_run_at TIMESTAMPTZ,
        last_run_search_id UUID,
        last_error TEXT,
        consecutive_failures INTEGER NOT NULL DEFAULT 0,
        run_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    """,

    # 4. Create index on pipeline_schedules for scheduler polling
    """
    CREATE INDEX IF NOT EXISTS ix_schedules_next_run_active
    ON pipeline_schedules (next_run_at)
    WHERE is_active = TRUE AND is_running = FALSE;
    """,

    # 5. Create lead_snapshots table
    """
    CREATE TABLE IF NOT EXISTS lead_snapshots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        lead_id UUID NOT NULL REFERENCES qualified_leads(id) ON DELETE CASCADE,
        score INTEGER NOT NULL,
        tier TEXT NOT NULL,
        reasoning_snippet TEXT,
        scored_at TIMESTAMPTZ DEFAULT now()
    );
    """,

    # 6. Create index on lead_snapshots
    """
    CREATE INDEX IF NOT EXISTS ix_lead_snapshots_lead_scored
    ON lead_snapshots (lead_id, scored_at DESC);
    """,
]


async def main():
    print(f"Connecting to: {dsn[:50]}...")
    conn = await asyncpg.connect(dsn, ssl="require")
    print("Connected!\n")

    for i, stmt in enumerate(MIGRATION_STATEMENTS, 1):
        label = stmt.strip().split("\n")[0].strip()
        try:
            await conn.execute(stmt)
            print(f"  [{i}/{len(MIGRATION_STATEMENTS)}] OK: {label}")
        except Exception as e:
            print(f"  [{i}/{len(MIGRATION_STATEMENTS)}] WARN: {label}")
            print(f"       {e}")

    # Verify
    print("\n--- Verification ---")
    cols = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'notification_prefs'
    """)
    print(f"  profiles.notification_prefs: {'EXISTS' if cols else 'MISSING'}")

    cols = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'usage_tracking' AND column_name = 'email_drafts_used'
    """)
    print(f"  usage_tracking.email_drafts_used: {'EXISTS' if cols else 'MISSING'}")

    tables = await conn.fetch("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name IN ('pipeline_schedules', 'lead_snapshots')
        ORDER BY table_name
    """)
    for t in tables:
        print(f"  table {t['table_name']}: EXISTS")

    for name in ['pipeline_schedules', 'lead_snapshots']:
        if not any(t['table_name'] == name for t in tables):
            print(f"  table {name}: MISSING")

    await conn.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
