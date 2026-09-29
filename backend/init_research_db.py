"""Initialize the Ananta research database indexes.

Usage:
    cd backend
    python init_research_db.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from research_database import RESEARCH_COLLECTIONS, ensure_research_indexes

ROOT = Path(__file__).parent
load_dotenv(ROOT / '.env')


async def main() -> None:
    url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    db = client[db_name]
    await client.admin.command('ping')
    await ensure_research_indexes(db)
    print(f'Initialized {len(RESEARCH_COLLECTIONS)} research collections/index sets in {db_name}.')
    print('Collections:', ', '.join(RESEARCH_COLLECTIONS))
    client.close()


if __name__ == '__main__':
    asyncio.run(main())
