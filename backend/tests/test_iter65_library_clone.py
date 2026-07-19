"""Iter65 — POST /api/library/{strategy_id}/clone tests.

Verifies:
  - Cloning a rule-based (declarative) strategy returns a new independently-editable
    entry with engine_key set, wireable=true, origin='clone', declarative_spec+engine_params
    present, and the new id != original id.
  - Cloning a core strategy (hunter/squeeze/continuation, internal=True) returns HTTP 400
    with clear message.
  - Unauthenticated clone returns 401/403.
  - The cloned strategy appears in GET /api/library and in GET /api/strategy/registry (wired).
"""
import os
import urllib.request
import urllib.error
import json as _json

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def _raw_post(path: str) -> tuple[int, str]:
    """Unauthenticated POST via urllib (bypasses the conftest session patch)."""
    req = urllib.request.Request(f"{BASE_URL}{path}", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


@pytest.fixture(scope="module")
def library():
    r = requests.get(f"{BASE_URL}/api/library", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("strategies") or data.get("library") or data if isinstance(data, list) else data
    # Normalise: server returns {'strategies': [...]} usually.
    if isinstance(data, dict):
        for k in ("strategies", "library", "items", "data"):
            if isinstance(data.get(k), list):
                items = data[k]
                break
    assert isinstance(items, list) and items, f"library empty: {data!r}"
    return items


def _pick_rule_based(library):
    for s in library:
        if s.get("id") in ("ema-cross", "supertrend", "donchian-breakout"):
            return s
    # Fallback: any non-internal with declarative_spec.entry or wireable=True
    for s in library:
        if not s.get("internal") and (s.get("declarative_spec") or {}).get("entry"):
            return s
    return None


def _pick_core(library):
    for s in library:
        if s.get("id") in ("hunter", "squeeze", "continuation"):
            return s
    for s in library:
        if s.get("internal"):
            return s
    return None


@pytest.fixture(scope="module")
def cleanup_clones():
    yield
    # Best-effort DB cleanup of clone entries created by these tests.
    try:
        import sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        from pymongo import MongoClient
        load_dotenv("/app/backend/.env")
        c = MongoClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        n = db.strategy_library.delete_many({"origin": "clone"}).deleted_count
        print(f"[cleanup] deleted {n} clone rows")
    except Exception as e:
        print(f"[cleanup] failed: {e}")


class TestLibraryClone:
    def test_clone_rule_based_success(self, library, cleanup_clones):
        src = _pick_rule_based(library)
        assert src is not None, "no rule-based strategy in library"
        src_id = src["id"]
        src_name = src.get("name")

        r = requests.post(f"{BASE_URL}/api/library/{src_id}/clone",
                          json={}, timeout=30)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("cloned") is True
        new_id = body.get("id")
        assert new_id and new_id != src_id, f"new id must differ: {new_id} vs {src_id}"
        assert new_id.startswith("clone-")

        strat = body.get("strategy") or {}
        assert strat.get("id") == new_id
        assert strat.get("engine_key") == new_id
        assert strat.get("wireable") is True
        assert strat.get("internal") is False
        assert strat.get("origin") == "clone"
        assert strat.get("cloned_from") == src_id
        assert strat.get("name", "").endswith("(Copy)"), strat.get("name")
        if src_name:
            assert strat["name"].startswith(src_name)
        assert isinstance(strat.get("declarative_spec"), dict)
        assert (strat["declarative_spec"].get("entry")), "declarative_spec.entry missing"
        assert isinstance(strat.get("engine_params"), dict)

        # Verify it now appears in GET /api/library
        r2 = requests.get(f"{BASE_URL}/api/library", timeout=30)
        assert r2.status_code == 200
        items = r2.json().get("strategies", [])
        ids = [s.get("id") for s in items]
        assert new_id in ids, f"cloned id {new_id} missing from library GET"

        # And is independently editable (different engine_key from source)
        cloned = next(s for s in items if s.get("id") == new_id)
        assert cloned.get("engine_key") == new_id
        assert cloned.get("engine_key") != src.get("engine_key")

        # Survives in /api/strategy/registry as wired
        r3 = requests.get(f"{BASE_URL}/api/strategy/registry", timeout=30)
        assert r3.status_code == 200
        reg = r3.json()
        # registry can be a dict of schemas or list; check flexibly
        found = False
        if isinstance(reg, dict):
            if new_id in reg:
                found = True
            elif isinstance(reg.get("strategies"), list):
                found = any(s.get("key") == new_id or s.get("id") == new_id
                            for s in reg["strategies"])
            elif isinstance(reg.get("schemas"), list):
                found = any(s.get("key") == new_id for s in reg["schemas"])
        elif isinstance(reg, list):
            found = any((isinstance(s, dict) and (s.get("key") == new_id
                        or s.get("id") == new_id)) for s in reg)
        assert found, f"clone {new_id} not wired in registry: {str(reg)[:400]}"

    def test_clone_core_strategy_400(self, library):
        core = _pick_core(library)
        assert core is not None, "no core/internal strategy in library"
        r = requests.post(f"{BASE_URL}/api/library/{core['id']}/clone",
                          json={}, timeout=30)
        assert r.status_code == 400, f"expected 400 for core, got {r.status_code}: {r.text}"
        body = r.json()
        detail = (body.get("detail") or "").lower()
        assert ("rule-based" in detail or "built-in" in detail
                or "core engine" in detail), body

    def test_clone_missing_strategy_404(self):
        r = requests.post(f"{BASE_URL}/api/library/nope-does-not-exist/clone",
                          json={}, timeout=30)
        assert r.status_code == 404, r.text

    def test_clone_unauthenticated_forbidden(self, library):
        src = _pick_rule_based(library)
        assert src is not None
        status, body = _raw_post(f"/api/library/{src['id']}/clone")
        assert status in (401, 403), f"expected 401/403 unauthenticated, got {status}: {body}"

    def test_clone_with_custom_name(self, library, cleanup_clones):
        src = _pick_rule_based(library)
        custom = "TEST_CLONE Custom Name"
        r = requests.post(f"{BASE_URL}/api/library/{src['id']}/clone",
                          json={"name": custom}, timeout=30)
        assert r.status_code == 200, r.text
        strat = r.json().get("strategy") or {}
        assert strat.get("name") == custom
