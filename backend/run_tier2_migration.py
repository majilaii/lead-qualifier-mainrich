"""Run Tier 2 database migration."""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def migrate():
    url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)

    # 1. Add notification_prefs to profiles
    try:
        await conn.execute("""
            ALTER TABLE profiles
            ADD COLUMN IF NOT EXISTS notification_prefs JSONB
            DEFAULT '{"pipeline_complete": true, "scheduled_run": true, "requalification": true, "weekly_digest": false}'::jsonb
        """)
        print("OK: Added profiles.notification_prefs")
    except Exception as e:
        print(f"profiles.notification_prefs: {e}")

    # 2. Add email_drafts_used to usage_tracking
    try:
        await conn.execute("""
            ALTER TABLE usage_tracking
            ADD COLUMN IF NOT EXISTS email_drafts_used INTEGER DEFAULT 0
        """)
        print("OK: Added usage_tracking.email_drafts_used")
    except Exception as e:
        print(f"usage_tracking.email_drafts_used: {e}")

    # Verify everything
    checks = [
        ("profiles", "notification_prefs"),
        ("usage_tracking", "email_drafts_used"),
    ]
    for table, col in checks:
        r = await conn.fetchval(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1 AND column_name = $2",
            table, col,
        )
        print(f"  Verify {table}.{col}: {'EXISTS' if r else 'MISSING'}")

    for table in ["lead_snapshots", "pipeline_schedules"]:
        r = await conn.fetchval(
            "SELECT table_name FROM information_schema.tables WHERE table_name = $1",
            table,
        )
        print(f"  Verify {table} table: {'EXISTS' if r else 'MISSING'}")

    await conn.close()
    print("\nMigration complete!")


asyncio.run(migrate())
