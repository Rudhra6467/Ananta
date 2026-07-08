"""Iter 26 — Strategy Architect (AI + Manual credit switch) backend tests.

Covers:
- POST /api/strategy/architect/chat: owner-gated (403 without token),
  400 on empty message. NO real LLM call is made here (main agent already
  verified the happy path via UI screenshot at ~22s latency; we intentionally
  do NOT burn Anthropic credits during regression).
- POST /api/strategy/configs (manual + architect origin): schema-validated,
  persists, and shows up in GET /api/strategy/configs.
- Iter25 regression: GET /api/strategy/metrics + PUT /api/strategy/{key}/state
  still work (baseline unchanged).
"""
import os
import re
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    envp = Path(__file__).resolve().parent.parent.parent / "frontend" / ".env"
    if envp.exists():
        m = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", envp.read_text(), re.M)
        if m:
            BASE_URL = m.group(1).strip().rstrip("/")

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"

STRATEGIES = ["hunter", "squeeze", "continuation"]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── /api/strategy/architect/chat ──────────────────────────────────────
class TestArchitectChatGating:
    """Owner gating + input validation — no LLM call is made in this class."""

    def test_requires_owner_403(self, anon):
        r = anon.post(f"{BASE_URL}/api/strategy/architect/chat",
                      json={"message": "design me a strategy"}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_empty_message_400(self, auth):
        r = auth.post(f"{BASE_URL}/api/strategy/architect/chat",
                      json={"message": "   "}, timeout=15)
        assert r.status_code == 400, r.text
        assert "message" in str(r.json().get("detail", "")).lower()

    def test_missing_message_422(self, auth):
        # Pydantic validation on ArchitectChat requires `message`
        r = auth.post(f"{BASE_URL}/api/strategy/architect/chat",
                      json={}, timeout=15)
        assert r.status_code in (400, 422), r.text


# ─── /api/strategy/configs — manual + architect origin ─────────────────
class TestStrategyConfigsManualPath:
    """No-credit manual flow used by StrategyArchitect.jsx's ManualAdd."""

    created_ids: list[str] = []

    def test_owner_required_for_create(self, anon):
        r = anon.post(f"{BASE_URL}/api/strategy/configs",
                      json={"strategy_key": "hunter", "params": {}}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_duplicate_creates_variant(self, auth):
        # simulates source=duplicate (params:{} uses schema defaults)
        name = f"TEST_iter26_dup_{uuid.uuid4().hex[:6]}"
        r = auth.post(f"{BASE_URL}/api/strategy/configs",
                      json={"strategy_key": "hunter", "params": {}, "origin": "user", "name": name},
                      timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg["name"] == name
        assert cfg["strategy_key"] == "hunter"
        assert cfg["origin"] == "user"
        self.__class__.created_ids.append(cfg["id"])

        # persistence — GET /api/strategy/configs must include it
        g = auth.get(f"{BASE_URL}/api/strategy/configs?strategy_key=hunter", timeout=15)
        assert g.status_code == 200
        ids = [c["id"] for c in g.json()["configs"]]
        assert cfg["id"] in ids

    def test_architect_origin_saves(self, auth):
        # simulates saveDesign() from StrategyArchitect.jsx (origin='architect')
        name = f"TEST_iter26_arch_{uuid.uuid4().hex[:6]}"
        r = auth.post(f"{BASE_URL}/api/strategy/configs",
                      json={"strategy_key": "hunter", "params": {}, "origin": "architect",
                            "name": name, "meta": {"architect": True, "base": "Hunter"}},
                      timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg["origin"] == "architect"
        assert cfg["meta"].get("architect") is True
        self.__class__.created_ids.append(cfg["id"])

    def test_unknown_strategy_key_rejected(self, auth):
        r = auth.post(f"{BASE_URL}/api/strategy/configs",
                      json={"strategy_key": "does_not_exist", "params": {}}, timeout=15)
        assert r.status_code == 400, r.text

    def test_invalid_params_rejected(self, auth):
        # backend re-validates params against the schema (422 with detail.errors)
        r = auth.post(f"{BASE_URL}/api/strategy/configs",
                      json={"strategy_key": "hunter",
                            "params": {"rsi_reset_min": 9999}, "name": "TEST_iter26_bad"},
                      timeout=15)
        assert r.status_code == 422, r.text
        assert "errors" in r.json().get("detail", {})

    def test_zzz_cleanup(self, auth):
        """Delete the two configs we created so the DB is clean for next agent."""
        for cid in list(self.__class__.created_ids):
            d = auth.delete(f"{BASE_URL}/api/strategy/configs/{cid}", timeout=15)
            assert d.status_code in (200, 204), d.text


# ─── Iter25 regression — must still pass ──────────────────────────────
class TestIter25Regression:
    def test_metrics_still_returns_three(self, anon):
        r = anon.get(f"{BASE_URL}/api/strategy/metrics", timeout=15)
        assert r.status_code == 200, r.text
        m = r.json()["metrics"]
        for k in STRATEGIES:
            assert k in m

    def test_set_state_paper_roundtrip(self, auth):
        # PAPER -> TESTING -> PAPER, verify persistence at each step
        r1 = auth.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": "TESTING"}, timeout=15)
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "TESTING"

        r2 = auth.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": "PAPER"}, timeout=15)
        assert r2.status_code == 200
        # verify via metrics
        m = requests.get(f"{BASE_URL}/api/strategy/metrics", timeout=15).json()["metrics"]
        assert m["hunter"]["status"] == "PAPER"

    def test_bad_status_400(self, auth):
        r = auth.put(f"{BASE_URL}/api/strategy/hunter/state",
                     json={"status": "BOGUS"}, timeout=15)
        assert r.status_code == 400
