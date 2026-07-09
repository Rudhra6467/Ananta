"""iter39 Phase B — declarative BACKTEST endpoint + Deploy/Disable state invariant + no-AI regression.

Scope (per review_request):
  * POST /api/library/{id}/backtest → 200 with historical_results + bars, persists metrics
  * GET /api/library/{id} → backtested=true + backtest_meta after backtest
  * Non-wireable library id → 400
  * PUT /api/strategy/{key}/state {enabled:true} on DISABLED declarative flips to PAPER+enabled
  * PUT /api/strategy/{key}/state {status:DISABLED} → enabled=false
  * REGRESSION (no AI): /api/strategy/registry (11), /api/strategy/metrics, per-strategy config
    activate/deactivate on ema-cross (iter37), /api/cycle/run/BTC → 200
Runs in <30s. Restores baseline state at teardown.
"""
import os
import pytest
import requests

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("REACT_APP_BACKEND_URL", "")

BASE_URL = _load_frontend_env().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok

@pytest.fixture(scope="module")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module", autouse=True)
def restore_baseline(auth_headers):
    """Restore 3-enabled / 5-disabled baseline after all tests in the module."""
    yield
    baseline = {
        "ema-cross": ("PAPER", True),
        "supertrend": ("PAPER", True),
        "rsi-momentum": ("PAPER", True),
        "macd-trend": ("DISABLED", False),
        "bollinger-mr": ("DISABLED", False),
        "donchian-breakout": ("DISABLED", False),
        "atr-breakout": ("DISABLED", False),
        "keltner-breakout": ("DISABLED", False),
    }
    for k, (status, enabled) in baseline.items():
        try:
            requests.put(f"{API}/strategy/{k}/state",
                         json={"status": status, "enabled": enabled},
                         headers=auth_headers, timeout=10)
        except Exception:
            pass


# ── Backtest endpoint ────────────────────────────────────────────────────────

class TestLibraryBacktest:
    """Declarative library backtest — real historical metrics, no LLM."""

    def test_backtest_wireable_supertrend_returns_real_metrics(self, auth_headers):
        r = requests.post(f"{API}/library/supertrend/backtest",
                          params={"symbol": "BTC/USD", "days": 14},
                          headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["id"] == "supertrend"
        assert body["engine_key"] == "supertrend"
        assert body["symbol"] == "BTC/USD"
        assert body["days"] == 14
        assert isinstance(body.get("bars"), int) and body["bars"] > 60
        hist = body["historical_results"]
        # Full metric shape
        for k in ("roi", "win_rate", "profit_factor", "sharpe", "sortino",
                  "max_drawdown", "avg_trade", "trade_count"):
            assert k in hist, f"missing metric {k}"
        assert isinstance(hist["trade_count"], int)
        assert isinstance(hist["roi"], (int, float))

    def test_backtest_persists_meta_on_library_doc(self, auth_headers):
        # Confirm previous backtest persisted onto GET /library/{id}
        r = requests.get(f"{API}/library/supertrend", timeout=15)
        assert r.status_code == 200
        doc = r.json()
        assert doc.get("backtested") is True, f"backtested flag not set: {doc.get('backtested')}"
        meta = doc.get("backtest_meta") or {}
        assert meta.get("symbol") == "BTC/USD"
        assert meta.get("days") == 14
        assert isinstance(meta.get("bars"), int) and meta["bars"] > 60
        # historical_results also persisted with expected fields
        hist = doc.get("historical_results") or {}
        for k in ("roi", "win_rate", "profit_factor", "trade_count"):
            assert k in hist, f"persisted metrics missing {k}: {hist}"

    def test_backtest_non_wireable_returns_400(self, auth_headers):
        # 'hunter' is a built-in engine strategy — not in the wireable declarative catalog
        # Confirm it exists in library first; if not, use any non-wireable doc
        r = requests.get(f"{API}/library", timeout=15)
        assert r.status_code == 200
        body = r.json()
        items = body.get("strategies") or body.get("items") or (body if isinstance(body, list) else [])
        non_wireable = next((x for x in items if not x.get("wireable")), None)
        if not non_wireable:
            pytest.skip("no non-wireable library entry to test 400 path")
        r2 = requests.post(f"{API}/library/{non_wireable['id']}/backtest",
                           params={"symbol": "BTC/USD", "days": 14},
                           headers=auth_headers, timeout=30)
        assert r2.status_code == 400, f"expected 400, got {r2.status_code}: {r2.text}"

    def test_backtest_requires_owner(self):
        # No auth header → 401/403
        r = requests.post(f"{API}/library/supertrend/backtest",
                          params={"symbol": "BTC/USD", "days": 14}, timeout=15)
        assert r.status_code in (401, 403), f"expected auth block, got {r.status_code}"


# ── Deploy/Disable toggle ────────────────────────────────────────────────────

class TestDeployToggle:
    """PUT /api/strategy/{key}/state — enabled↔status invariant per iter38 hardening."""

    def test_enable_disabled_declarative_promotes_to_paper(self, auth_headers):
        # Baseline: bollinger-mr should be DISABLED
        # Enable via {enabled: true} alone → should auto-promote to PAPER
        r = requests.put(f"{API}/strategy/bollinger-mr/state",
                         json={"enabled": True}, headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        # Server returns merged doc after iter38 hardening
        m = requests.get(f"{API}/strategy/metrics", timeout=10).json()
        metrics = m.get("metrics") or {}
        meta = metrics.get("bollinger-mr", {})
        assert meta.get("enabled") is True
        assert meta.get("status") == "PAPER", f"expected PAPER, got {meta.get('status')}"

    def test_disable_via_status_flips_enabled_false(self, auth_headers):
        # Now flip bollinger-mr back to DISABLED via {status: 'DISABLED'} → enabled must clamp to false
        r = requests.put(f"{API}/strategy/bollinger-mr/state",
                         json={"status": "DISABLED"}, headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text
        m = requests.get(f"{API}/strategy/metrics", timeout=10).json()
        meta = (m.get("metrics") or {}).get("bollinger-mr", {})
        assert meta.get("status") == "DISABLED"
        assert meta.get("enabled") is False, f"invariant broken: {meta}"


# ── Regression (no AI) ───────────────────────────────────────────────────────

class TestRegression:
    def test_registry_has_11_strategies(self):
        r = requests.get(f"{API}/strategy/registry", timeout=10)
        assert r.status_code == 200
        data = r.json()
        strategies = data.get("strategies") or data
        assert len(strategies) == 11, f"expected 11, got {len(strategies)}"
        keys = {s["key"] for s in strategies}
        for k in ("hunter", "squeeze", "continuation",
                  "ema-cross", "supertrend", "rsi-momentum",
                  "macd-trend", "bollinger-mr", "donchian-breakout",
                  "atr-breakout", "keltner-breakout"):
            assert k in keys, f"missing {k}"

    def test_metrics_returns_states_for_all(self):
        r = requests.get(f"{API}/strategy/metrics", timeout=10)
        assert r.status_code == 200
        metrics = r.json().get("metrics") or {}
        # Every declarative key should have a meta doc with status
        for k in ("ema-cross", "supertrend", "rsi-momentum", "macd-trend", "bollinger-mr"):
            assert k in metrics, f"metrics missing {k}"
            assert "status" in metrics[k]
            assert "enabled" in metrics[k]

    def test_per_strategy_config_activate_deactivate_ema_cross(self, auth_headers):
        # Create test config
        payload = {
            "strategy_key": "ema-cross",
            "name": "TEST_iter39_phase_b",
            "params": {"ema_fast": 5, "ema_slow": 20, "normal_lot_usd": 50, "stop_loss_pct": 8.0},
        }
        r = requests.post(f"{API}/strategy/configs", json=payload,
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json().get("config") or r.json()
        cid = cfg["id"]
        try:
            # Mark validation passed
            requests.put(f"{API}/strategy/configs/{cid}",
                         json={"validation_status": "passed"},
                         headers=auth_headers, timeout=10)
            # Activate
            ra = requests.post(f"{API}/strategy/configs/{cid}/activate",
                               headers=auth_headers, timeout=10)
            assert ra.status_code == 200, ra.text
            eff = requests.get(f"{API}/strategy/ema-cross/effective", timeout=10).json()
            assert eff.get("using_config") is True
            # Deactivate (per-strategy endpoint, not per-config)
            rd = requests.post(f"{API}/strategy/ema-cross/deactivate",
                               headers=auth_headers, timeout=10)
            assert rd.status_code == 200, rd.text
            eff2 = requests.get(f"{API}/strategy/ema-cross/effective", timeout=10).json()
            assert eff2.get("using_config") is False
        finally:
            requests.delete(f"{API}/strategy/configs/{cid}",
                            headers=auth_headers, timeout=10)

    def test_cycle_run_btc_returns_200(self, auth_headers):
        r = requests.post(f"{API}/cycle/run/BTC", headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
