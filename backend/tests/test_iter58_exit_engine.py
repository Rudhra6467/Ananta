"""
Iter 58 — Exit Engine overhaul tests
Covers:
  - GET /api/settings default values (stop_loss 2.2, trail_arm 1.6, trail_distance 0.9, profit_protection true)
  - PUT /api/settings persists exit_method_pref, profile_overrides, asset_exit_overrides, profit_protection_enabled
  - Regime router restrictions (Hunter/Squeeze/Continuation/NEUTRAL/RANGE/TREND_DOWN)
  - Exit Engine 'Test this Exit' lab backtest run (POST + poll GET until DONE)
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Auth failed: {r.status_code} {r.text}")
    return r.json().get("token")


@pytest.fixture(scope="module")
def auth(api, token):
    api.headers.update({"Authorization": f"Bearer {token}"})
    return api


# ─── Settings ────────────────────────────────────────────────────────────
class TestSettingsDefaults:
    def test_get_settings_new_defaults(self, api):
        r = api.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        d = r.json()
        # New exit-tuning defaults
        assert d.get("stop_loss_pct") == 2.2, f"expected 2.2 got {d.get('stop_loss_pct')}"
        assert d.get("trail_arm_pct") == 1.6, f"expected 1.6 got {d.get('trail_arm_pct')}"
        assert d.get("trail_distance_pct") == 0.9, f"expected 0.9 got {d.get('trail_distance_pct')}"
        assert d.get("profit_protection_enabled") is True

    def test_put_settings_persists_new_fields(self, auth):
        payload = {
            "exit_method_pref": "atr",
            "profit_protection_enabled": True,
            "profile_overrides": {"hunter": {"stop_loss_pct": 2.5, "trail_arm_pct": 1.8}},
            "asset_exit_overrides": {"BTC/USD": {"stop_loss_pct": 3.0, "trail_distance_pct": 1.1}},
        }
        r = auth.put(f"{BASE_URL}/api/settings", json=payload)
        assert r.status_code == 200, r.text
        # Verify persisted
        g = auth.get(f"{BASE_URL}/api/settings").json()
        assert g.get("exit_method_pref") == "atr"
        assert g.get("profit_protection_enabled") is True
        assert g.get("profile_overrides", {}).get("hunter", {}).get("stop_loss_pct") == 2.5
        assert g.get("asset_exit_overrides", {}).get("BTC/USD", {}).get("stop_loss_pct") == 3.0

        # Restore defaults to leave clean state
        auth.put(f"{BASE_URL}/api/settings", json={
            "exit_method_pref": "native",
            "profile_overrides": {},
            "asset_exit_overrides": {},
        })


# ─── Regime router ───────────────────────────────────────────────────────
class TestRegimeRouter:
    def test_router_module_direct(self):
        # Import backend router module directly for a fast unit-level check
        import sys
        sys.path.insert(0, "/app/backend")
        from router import route  # noqa: WPS433

        assert route("REVERSAL")["eligible_models"] == ["hunter"]
        assert route("COMPRESSION")["eligible_models"] == ["squeeze"]
        assert route("TREND_UP")["eligible_models"] == ["continuation"]
        for blocked in ("NEUTRAL", "RANGE", "TREND_DOWN"):
            assert route(blocked)["eligible_models"] == [], f"{blocked} should be blocked"


# ─── Lab backtest (Test this Exit) ───────────────────────────────────────
class TestLabExitBacktest:
    @pytest.mark.parametrize("exit_method", ["fixed", "atr", "native"])
    def test_lab_backtest_flow(self, auth, exit_method):
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "period": "3m",
            "timeframe": "1h",
            "exit_method": exit_method,
        }
        r = auth.post(f"{BASE_URL}/api/lab/runs", json=payload)
        assert r.status_code in (200, 201), r.text
        run = r.json()
        run_id = run.get("id") or run.get("run_id")
        assert run_id, f"no run id in response: {run}"

        # Poll until DONE (up to 120s)
        status = None
        deadline = time.time() + 120
        result = None
        while time.time() < deadline:
            g = auth.get(f"{BASE_URL}/api/lab/runs/{run_id}")
            assert g.status_code == 200, g.text
            body = g.json()
            status = body.get("status")
            if status in ("DONE", "FAILED", "ERROR"):
                result = body.get("result") or body.get("results")
                break
            time.sleep(3)

        assert status == "DONE", f"final status={status} for {exit_method}"
        assert result, f"no result payload for {exit_method}"
        per_symbol = result.get("per_symbol") or {}
        # At least one of the requested symbols should have output
        assert any(k in per_symbol for k in ("BTC/USD", "ETH/USD", "SOL/USD")), f"per_symbol empty: {list(per_symbol.keys())}"
        # exit_comparison (What-If) present on at least one symbol
        assert any("exit_comparison" in (v or {}) for v in per_symbol.values()), "exit_comparison missing on all symbols"
