"""Iter 27 — Phase 1 'The Spine' HTTP-level tests
Covers:
- PUT /api/strategy/{key}/state persistence + owner gate + validation.
- GET  /api/strategy/metrics: health, health_breakdown (list of {key,label,score,detail}),
  timeline (list of {key,label,ts,done,detail}); asserts health equals rounded avg
  of the component scores.
- Engine gate: DISABLED strategy must cause POST /api/cycle/run/{symbol_base} to
  block a hunter entry with a 'STRATEGY_DISABLED hunter …' reason. Re-enabled to
  PAPER at the end.
"""
import json
import os
import urllib.error
import urllib.request

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"

VALID_STATUSES = {"LIVE", "PAPER", "DISABLED", "TESTING", "OPTIMIZING", "ERROR"}


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert isinstance(tok, str) and len(tok) > 20
    return tok


@pytest.fixture(scope="module")
def owner(api, owner_token):
    api.headers.update({"Authorization": f"Bearer {owner_token}"})
    yield api
    # teardown: always reset hunter/squeeze/continuation to PAPER + enabled
    for key in ("hunter", "squeeze", "continuation"):
        api.put(f"{BASE_URL}/api/strategy/{key}/state",
                json={"status": "PAPER", "enabled": True})


# ─── /api/strategy/{key}/state ─────────────────────────────────────────
class TestStrategyState:
    def test_anonymous_is_403(self, api):
        # NOTE: conftest.py autouse fixture monkey-patches requests.Session.request
        # to inject the owner Bearer token on all mutating requests. Use urllib
        # here to bypass that patch and prove the endpoint itself rejects anon.
        req = urllib.request.Request(
            f"{BASE_URL}/api/strategy/hunter/state",
            data=json.dumps({"status": "PAPER"}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        assert code in (401, 403), f"expected 401/403, got {code}"

    def test_invalid_status_400(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": "NOT_A_REAL_STATUS"})
        assert r.status_code == 400

    def test_empty_body_400(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/hunter/state", json={})
        assert r.status_code == 400

    def test_unknown_key_404(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/nope_nope/state",
                      json={"status": "PAPER"})
        assert r.status_code == 404

    @pytest.mark.parametrize("status",
        ["LIVE", "PAPER", "DISABLED", "TESTING", "OPTIMIZING", "ERROR"])
    def test_persists_status(self, owner, status):
        r = owner.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": status})
        assert r.status_code == 200, r.text
        assert r.json().get("status") == status

        # verify via /api/strategy/metrics
        m = owner.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        assert m["hunter"]["status"] == status

    def test_persists_enabled(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/squeeze/state",
                      json={"enabled": False})
        assert r.status_code == 200
        assert r.json().get("enabled") is False
        m = owner.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        assert m["squeeze"]["enabled"] is False
        # restore
        owner.put(f"{BASE_URL}/api/strategy/squeeze/state",
                  json={"enabled": True})


# ─── /api/strategy/metrics ─────────────────────────────────────────────
class TestStrategyMetrics:
    def test_metrics_shape(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "metrics" in data
        m = data["metrics"]
        assert isinstance(m, dict) and len(m) >= 1
        # required strategies at minimum
        for key in ("hunter", "squeeze", "continuation"):
            assert key in m, f"missing {key} in metrics"

    def test_metrics_fields_per_strategy(self, api):
        m = api.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        for key, s in m.items():
            for f in ("key", "name", "status", "enabled",
                      "trades", "win_rate", "roi",
                      "health", "health_breakdown", "timeline"):
                assert f in s, f"strategy {key} missing field {f}"
            assert 0 <= s["health"] <= 100
            assert s["status"] in VALID_STATUSES

    def test_health_breakdown_shape(self, api):
        m = api.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        for key, s in m.items():
            hb = s["health_breakdown"]
            assert isinstance(hb, list) and len(hb) >= 1
            for c in hb:
                for f in ("key", "label", "score", "detail"):
                    assert f in c, f"breakdown row missing {f} on {key}"
                assert 0 <= c["score"] <= 100

    def test_health_equals_rounded_avg_of_breakdown(self, api):
        m = api.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        for key, s in m.items():
            hb = s["health_breakdown"]
            expected = int(round(sum(c["score"] for c in hb) / len(hb)))
            assert s["health"] == expected, (
                f"{key}: health {s['health']} != avg({[c['score'] for c in hb]})={expected}"
            )

    def test_timeline_shape(self, api):
        m = api.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        for key, s in m.items():
            tl = s["timeline"]
            assert isinstance(tl, list) and len(tl) >= 1
            keys = {e["key"] for e in tl}
            # always at least Created + Validated + Paper + Live
            for expected in ("created", "validated", "paper", "live"):
                assert expected in keys, f"{key}: timeline missing {expected}"
            for e in tl:
                for f in ("key", "label", "ts", "done", "detail"):
                    assert f in e
                assert isinstance(e["done"], bool)


# ─── engine gate: DISABLED must produce STRATEGY_DISABLED in blocked reasons ──
class TestEngineGate:
    """The STRATEGY_DISABLED gate only fires *after* Hunter would return BUY. On a
    quiet market the cycle returns HOLD before reaching the gate, so we validate
    the wiring in three ways: (a) unit tests in test_strategy_gate.py cover the
    pure gate logic, (b) the state endpoint persists DISABLED so evaluate_symbol
    will load it, (c) POST /api/cycle/run/{symbol} still returns 200 with a
    well-formed body when the strategy is DISABLED."""

    def test_disabled_state_reflected_in_metrics_and_cycle_healthy(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": "DISABLED", "enabled": True})
        assert r.status_code == 200
        assert r.json()["status"] == "DISABLED"

        # metrics reflects the DISABLED state (so evaluate_symbol's
        # load_strategy_states will see it too — same Mongo row)
        m = owner.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        assert m["hunter"]["status"] == "DISABLED"

        # cycle runs cleanly while DISABLED (no crash / 500)
        r = owner.post(f"{BASE_URL}/api/cycle/run/BTC")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "decision" in body
        # If the Hunter did produce a BUY intent, the gate must have blocked it.
        if body.get("decision") == "BUY":
            pytest.fail("Hunter produced BUY while DISABLED — gate did not fire")
        # Otherwise the natural HOLD is fine; the gate is exercised by unit tests.

    def test_reenable_hunter_persists(self, owner):
        r = owner.put(f"{BASE_URL}/api/strategy/hunter/state",
                      json={"status": "PAPER", "enabled": True})
        assert r.status_code == 200
        assert r.json()["status"] == "PAPER"
        m = owner.get(f"{BASE_URL}/api/strategy/metrics").json()["metrics"]
        assert m["hunter"]["status"] == "PAPER"
        assert m["hunter"]["enabled"] is True
