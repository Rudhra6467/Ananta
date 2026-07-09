"""P3 Phase A — per-strategy engine config resolution (HTTP integration).

Verifies the full contract exposed by the review request:
- Activate a validated config: response has applied/applied_params/ignored_account_level.
- Global /api/settings is NOT clobbered (account-level fields untouched).
- /strategy/{key}/effective reflects using_config=true after activate, false after deactivate.
- Blocked (400) for configs whose validation_status != 'passed'.
- /strategy/metrics exposes active_config_id + active_config_name.
- Route ordering: /effective and /deactivate not shadowed by other /strategy routes.
- POST /api/cycle/run/BTC works cleanly with hunter config active.

Cleanup: any TEST_-prefixed config created here is deactivated + deleted.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://hunter-squeeze-labs.preview.emergentagent.com"

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_configs():
    """List of config ids created by these tests — cleaned up at module teardown."""
    ids: list[str] = []
    yield ids
    # teardown: deactivate hunter (in case still active) + delete configs
    try:
        tok = requests.post(f"{BASE_URL}/api/auth/login",
                            json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
                            timeout=15).json().get("token")
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        requests.post(f"{BASE_URL}/api/strategy/hunter/deactivate", headers=h, timeout=10)
        for cid in ids:
            requests.delete(f"{BASE_URL}/api/strategy/configs/{cid}", headers=h, timeout=10)
    except Exception as exc:  # pragma: no cover
        print(f"[cleanup] failed: {exc}")


# ---------------------------------------------------------------- helpers ---
def _snapshot_global_settings():
    r = requests.get(f"{BASE_URL}/api/settings", timeout=10)
    assert r.status_code == 200
    return r.json()


def _create_hunter_config(auth_headers, params: dict, name: str | None = None,
                          validated: bool = True) -> str:
    payload = {"strategy_key": "hunter",
               "name": name or f"TEST_iter37_{uuid.uuid4().hex[:6]}",
               "params": params}
    r = requests.post(f"{BASE_URL}/api/strategy/configs",
                      headers=auth_headers, json=payload, timeout=15)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    cid = r.json().get("config", {}).get("id") or r.json().get("id")
    assert cid, f"no id in create response: {r.json()}"
    if validated:
        rv = requests.put(f"{BASE_URL}/api/strategy/configs/{cid}",
                          headers=auth_headers,
                          json={"validation_status": "passed"}, timeout=15)
        assert rv.status_code == 200, f"validate failed: {rv.status_code} {rv.text}"
    return cid


# ---------------------------------------------------------------- tests ---
class TestActivateContract:
    def test_activate_returns_applied_and_ignored(self, auth_headers, created_configs):
        cid = _create_hunter_config(auth_headers,
            {"normal_lot_usd": 150.0, "rsi_reset_max": 42.0,
             "max_concurrent_positions": 2, "max_spread_pct": 1.5})
        created_configs.append(cid)

        pre = _snapshot_global_settings()
        pre_lot = pre.get("normal_lot_usd")
        pre_mcp = pre.get("max_concurrent_positions")

        r = requests.post(f"{BASE_URL}/api/strategy/configs/{cid}/activate",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        # contract keys
        assert body["activated"] == cid
        assert body["strategy_key"] == "hunter"
        assert isinstance(body["applied"], int) and body["applied"] >= 1
        assert isinstance(body["applied_params"], dict)
        assert isinstance(body["ignored_account_level"], list)
        # account-level fields must appear in ignored list
        assert "max_concurrent_positions" in body["ignored_account_level"]
        assert "max_spread_pct" in body["ignored_account_level"]
        # strategy-level fields must appear in applied_params
        assert "normal_lot_usd" in body["applied_params"]
        assert float(body["applied_params"]["normal_lot_usd"]) == 150.0

        # Global settings UNTOUCHED
        post = _snapshot_global_settings()
        assert post.get("normal_lot_usd") == pre_lot, "global normal_lot_usd was clobbered"
        assert post.get("max_concurrent_positions") == pre_mcp, "global max_concurrent_positions was clobbered"

    def test_effective_reports_using_config_after_activate(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/strategy/hunter/effective", timeout=10)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["strategy_key"] == "hunter"
        assert b["using_config"] is True
        assert isinstance(b["overrides"], dict) and b["overrides"]
        assert b["active_config_id"]

    def test_metrics_exposes_active_config(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/strategy/metrics", timeout=10)
        assert r.status_code == 200, r.text
        payload = r.json()
        # Payload shape: {"metrics": {"hunter": {...}, "squeeze": {...}, ...}}
        metrics = payload.get("metrics") if isinstance(payload, dict) else None
        assert isinstance(metrics, dict), f"unexpected metrics shape: {payload}"
        hunter = metrics.get("hunter")
        assert hunter is not None, f"no hunter row in metrics: {payload}"
        assert hunter.get("active_config_id"), "active_config_id missing on hunter metrics"
        assert hunter.get("active_config_name"), "active_config_name missing on hunter metrics"

    def test_cycle_run_btc_with_active_config(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/cycle/run/BTC",
                          headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"cycle/run failed: {r.status_code} {r.text[:400]}"

    def test_deactivate_reverts(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/strategy/hunter/deactivate",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("deactivated") == "hunter"

        eff = requests.get(f"{BASE_URL}/api/strategy/hunter/effective", timeout=10).json()
        assert eff["using_config"] is False
        assert eff["overrides"] == {}


class TestValidationGate:
    def test_activate_blocked_when_not_validated(self, auth_headers, created_configs):
        cid = _create_hunter_config(auth_headers, {"normal_lot_usd": 120.0},
                                    validated=False)
        created_configs.append(cid)
        r = requests.post(f"{BASE_URL}/api/strategy/configs/{cid}/activate",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"


class TestRouteOrdering:
    """/strategy/{key}/effective and /strategy/{key}/deactivate must not be shadowed."""

    def test_effective_route_reachable_for_arbitrary_key(self):
        r = requests.get(f"{BASE_URL}/api/strategy/hunter/effective", timeout=10)
        assert r.status_code == 200
        assert r.json().get("strategy_key") == "hunter"

    def test_effective_for_squeeze(self):
        r = requests.get(f"{BASE_URL}/api/strategy/squeeze/effective", timeout=10)
        assert r.status_code == 200
        assert r.json().get("strategy_key") == "squeeze"

    def test_deactivate_owner_gated(self):
        # unauthenticated deactivate must fail (route exists → not shadowed → 401/403)
        r = requests.post(f"{BASE_URL}/api/strategy/hunter/deactivate", timeout=10)
        assert r.status_code in (401, 403), f"expected auth gate, got {r.status_code} {r.text}"
