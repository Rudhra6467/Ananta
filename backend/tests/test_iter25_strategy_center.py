"""Iter 25 — Strategy Center + Research Lab 2.0 (Phase 1) backend regression.

Covers:
- GET /api/strategy/metrics       (per-strategy scoreboard used by the Strategy Center cards)
- PUT /api/strategy/{key}/state   (status enum validation, unknown-key 404, valid transitions)
- POST /api/analytics/ai_query    (now accepts optional `strategy` field)
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

VALID_STATUSES = ["LIVE", "PAPER", "DISABLED", "TESTING", "OPTIMIZING", "ERROR"]
STRATEGIES = ["hunter", "squeeze", "continuation"]


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ─── /api/strategy/metrics ─────────────────────────────────────────────
class TestStrategyMetrics:
    def test_metrics_returns_all_three_strategies(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "metrics" in data
        m = data["metrics"]
        for k in STRATEGIES:
            assert k in m, f"missing strategy '{k}' in metrics"

    def test_metrics_shape_per_strategy(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15)
        m = r.json()["metrics"]
        # every strategy must expose the fields the Strategy Center card reads
        required = {"status", "enabled", "trades", "win_rate", "roi",
                    "health", "stars", "confidence", "last_trade"}
        for k in STRATEGIES:
            row = m[k]
            missing = required - set(row.keys())
            assert not missing, f"{k} missing keys: {missing}"
            # types
            assert isinstance(row["trades"], int)
            assert isinstance(row["stars"], int) and 0 <= row["stars"] <= 5
            assert 0 <= row["health"] <= 100
            assert row["status"] in VALID_STATUSES
            assert isinstance(row["enabled"], bool)


# ─── PUT /api/strategy/{key}/state ─────────────────────────────────────
class TestStrategyState:
    def test_reject_bad_status(self, api):
        r = api.put(f"{BASE_URL}/api/strategy/hunter/state",
                    json={"status": "BOGUS"}, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "status" in str(detail).lower()

    def test_reject_unknown_strategy(self, api):
        r = api.put(f"{BASE_URL}/api/strategy/{uuid.uuid4().hex}/state",
                    json={"status": "PAPER"}, timeout=15)
        assert r.status_code == 404, r.text

    def test_reject_empty_payload(self, api):
        r = api.put(f"{BASE_URL}/api/strategy/hunter/state",
                    json={}, timeout=15)
        assert r.status_code == 400, r.text

    def test_valid_transition_and_persist(self, api):
        # switch to TESTING then back to PAPER (per main-agent instructions).
        r1 = api.put(f"{BASE_URL}/api/strategy/hunter/state",
                     json={"status": "TESTING"}, timeout=15)
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["status"] == "TESTING"
        assert body["key"] == "hunter"

        # verify persistence via GET metrics
        m = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15).json()["metrics"]
        assert m["hunter"]["status"] == "TESTING"

        # reset back to PAPER (cleanup — matches main-agent instruction)
        r2 = api.put(f"{BASE_URL}/api/strategy/hunter/state",
                     json={"status": "PAPER"}, timeout=15)
        assert r2.status_code == 200
        m2 = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15).json()["metrics"]
        assert m2["hunter"]["status"] == "PAPER"

    def test_enabled_flag_persist(self, api):
        r = api.put(f"{BASE_URL}/api/strategy/squeeze/state",
                    json={"enabled": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("enabled") is True
        m = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15).json()["metrics"]
        assert m["squeeze"]["enabled"] is True


# ─── POST /api/analytics/ai_query — strategy scoping ───────────────────
class TestAIQueryStrategyField:
    def test_empty_question_400(self, api):
        r = api.post(f"{BASE_URL}/api/analytics/ai_query",
                     json={"question": "", "strategy": "hunter"}, timeout=15)
        assert r.status_code == 400, r.text

    def test_accepts_strategy_field_and_answers(self, api):
        # ONE grounded LLM call — keep this minimal to save credits.
        r = api.post(f"{BASE_URL}/api/analytics/ai_query",
                     json={"question": "How many closed trades exist for this strategy?",
                           "strategy": "hunter"}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_id" in data and isinstance(data["session_id"], str)
        assert "answer" in data and isinstance(data["answer"], str)
        assert len(data["answer"]) > 0
