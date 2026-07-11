"""P2 polish: TTL cleanup of orphan import drafts.

Verifies `_purge_orphan_import_drafts` deletes only UNAPPROVED drafts older than
the TTL, while keeping (a) recent unapproved drafts and (b) approved drafts of any age.
Runs against the live Mongo configured in backend/.env; cleans up its own fixtures.
"""
import asyncio
from datetime import UTC, datetime, timedelta

import server

OLD = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
RECENT = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

FIXTURES = [
    {"id": "_t44_old_orphan", "status": "draft", "created_at": OLD},
    {"id": "_t44_recent_orphan", "status": "draft", "created_at": RECENT},
    {"id": "_t44_old_approved", "status": "approved", "created_at": OLD},
]


def test_purge_orphan_import_drafts():
    async def run():
        from conftest import bind_loop_local_db
        bind_loop_local_db()
        col = server.db.strategy_imports
        ids = [f["id"] for f in FIXTURES]
        await col.delete_many({"id": {"$in": ids}})
        await col.insert_many([{**f} for f in FIXTURES])
        try:
            await server._purge_orphan_import_drafts(ttl_hours=48)
            remaining = {d["id"] async for d in col.find({"id": {"$in": ids}}, {"_id": 0, "id": 1})}
            assert "_t44_old_orphan" not in remaining      # purged
            assert "_t44_recent_orphan" in remaining        # too new → kept
            assert "_t44_old_approved" in remaining          # approved → kept
        finally:
            await col.delete_many({"id": {"$in": ids}})

    asyncio.run(run())
