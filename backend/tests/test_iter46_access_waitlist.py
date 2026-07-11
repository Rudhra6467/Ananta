"""Access waitlist (MVP lead capture) — public request + idempotency + email validation
+ owner review/approve. Runs against the live Mongo in backend/.env; cleans its fixtures.

All DB-touching assertions share a single event loop (one asyncio.run) because the
module-level motor client binds to the first loop it sees."""
import asyncio

import pytest
from fastapi import HTTPException

import server
from server import AccessRequestReq

TEST_EMAIL = "_t46_lead@example.com"


def test_valid_email():
    assert server._valid_email("a@b.com")
    assert not server._valid_email("notanemail")
    assert not server._valid_email("a@@b.com")
    assert not server._valid_email("a@b")
    assert not server._valid_email("")


def test_access_waitlist_flow():
    async def go():
        from conftest import bind_loop_local_db
        bind_loop_local_db()
        col = server.db.access_requests
        await col.delete_many({"email": TEST_EMAIL})
        try:
            # capture
            r1 = await server.access_request(AccessRequestReq(name="Lead One", email=TEST_EMAIL, feature="Ask Ananta", platform="web"))
            assert r1["ok"] and r1["status"] == "pending" and r1["already_on_list"] is False
            # idempotent re-submit — no duplicate, attempts bumped
            r2 = await server.access_request(AccessRequestReq(name="Lead One", email=TEST_EMAIL, feature="Health"))
            assert r2["already_on_list"] is True
            docs = await col.find({"email": TEST_EMAIL}).to_list(10)
            assert len(docs) == 1 and docs[0]["attempts"] == 2

            # bad input -> 400
            with pytest.raises(HTTPException) as e1:
                await server.access_request(AccessRequestReq(name="", email=TEST_EMAIL))
            assert e1.value.status_code == 400
            with pytest.raises(HTTPException) as e2:
                await server.access_request(AccessRequestReq(name="X", email="garbage"))
            assert e2.value.status_code == 400

            # owner approve + 404 on unknown
            rid = docs[0]["id"]
            r = await server.access_request_action(rid, "approve")
            assert r["status"] == "approved"
            assert (await col.find_one({"id": rid}))["status"] == "approved"
            with pytest.raises(HTTPException) as e3:
                await server.access_request_action("nonexistent-id", "reject")
            assert e3.value.status_code == 404
        finally:
            await col.delete_many({"email": TEST_EMAIL})

    asyncio.run(go())
