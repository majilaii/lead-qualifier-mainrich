"""
Index product knowledge documents for support-chat RAG.

Usage:
  cd backend
  python scripts/index_knowledge.py
"""

import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import async_session, init_db  # noqa: E402
from support_chat_engine import SupportChatEngine  # noqa: E402


async def main():
    await init_db()
    engine = SupportChatEngine()
    async with async_session() as db:
        stats = await engine.index_knowledge_base(db)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
