"""
Iter 58 (this session) — Catalog wiring + What-If shape.

Covers:
  A. GET /api/library returns 16 items with:
     - turtle / time-series-momentum / stochastic-momentum / vwap-mr: wireable=true, engine_key set
     - pairs-trading: reference_only=true, reference_note set, wireable falsy
  B. /api/strategy/registry and /api/strategy/metrics include the 4 new keys
  C. Deploy path: PUT /api/strategy/turtle/state -> status=PAPER
  D. Exit Engine 'Test' backtest returns result.exit_comparison[sym][tf].rows with winner_key
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")

NEW_KEYS = ["turtle", "time-series-momentum", "stochastic-momentum", "vwap-mr"]


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


# ─── A. Library wiring + reference-only pairs-trading ─────────────────────
class TestLibraryWiring:
    def test_library_has_16_items_and_wired_flags(self, api):
        r = api.get(f"{BASE_URL}/api/library")
        assert r.status_code == 200, r.text
        body = r.json()
        items = body if isinstance(body, list) else (body.get("strategies") or body.get("items") or body.get("library") or [])
        assert len(items) == 16, f"expected 16 library items, got {len(items)}"
        by_id = {e.get("id"): e for e in items}
        # 4 new wired
        for k in NEW_KEYS:
            e = by_id.get(k)
            assert e is not None, f"missing library entry: {k}"
            assert e.get("wireable") is True, f"{k}.wireable should be True: {e}"
            assert e.get("engine_key") == k, f"{k}.engine_key should be {k}: got {e.get('engine_key')}"
            assert not e.get("reference_only"), f"{k} should NOT be reference_only"
        # pairs-trading is reference-only
        pt = by_id.get("pairs-trading")
        assert pt is not None, "pairs-trading missing"
        assert pt.get("reference_only") is True, f"pairs-trading.reference_only expected True: {pt}"
        assert pt.get("reference_note") and "2-asset" in pt.get("reference_note"), \
            f"pairs-trading.reference_note wrong: {pt.get('reference_note')!r}"
        assert not pt.get("wireable"), f"pairs-trading.wireable should be falsy: {pt.get('wireable')}"


# ─── B. Registry + metrics include new keys ───────────────────────────────
class TestRegistryAndMetrics:
    def test_registry_includes_new_keys(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/registry")
        assert r.status_code == 200, r.text
        strategies = r.json().get("strategies") or []
        keys = {s.get("key") for s in strategies}
        for k in NEW_KEYS:
            assert k in keys, f"registry missing key: {k} (have: {sorted(keys)})"

    def test_metrics_includes_new_keys(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/metrics")
        assert r.status_code == 200, r.text
        body = r.json()
        m = body.get("metrics") if isinstance(body, dict) else body
        keys = set()
        if isinstance(m, list):
            keys = {x.get("key") for x in m if isinstance(x, dict)}
        elif isinstance(m, dict):
            keys = set(m.keys())
        for k in NEW_KEYS:
            assert k in keys, f"metrics missing key: {k} (have sample: {list(keys)[:20]})"


# ─── C. Deploy path via PUT /api/strategy/{key}/state ─────────────────────
class TestDeployPath:
    def test_set_turtle_to_paper(self, auth):
        r = auth.put(f"{BASE_URL}/api/strategy/turtle/state", json={"status": "PAPER", "enabled": True})
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc.get("status") == "PAPER", f"expected PAPER got {doc.get('status')}"
        assert doc.get("enabled") is True, doc
        # Cleanup — disable so we don't leave a strategy running
        auth.put(f"{BASE_URL}/api/strategy/turtle/state", json={"status": "DISABLED", "enabled": False})


# ─── D. Exit Engine 'Test' - What-If exit_comparison at result top level ─
class TestExitEngineWhatIf:
    def test_lab_backtest_returns_topLevel_exit_comparison(self, auth):
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "period": "3m",
            "timeframe": "1h",
            "strategies": ["hunter"],
            "exit_method": "atr",
            "atr_params": {"multiplier": 2.5, "period": 14, "trail_activation_pct": 1.6, "trail_distance": 2.0},
        }
        r = auth.post(f"{BASE_URL}/api/lab/runs", json=payload)
        assert r.status_code in (200, 201), r.text
        run_id = (r.json().get("id") or r.json().get("run_id"))
        assert run_id, f"no run id: {r.json()}"

        status = None
        result = None
        deadline = time.time() + 150
        while time.time() < deadline:
            g = auth.get(f"{BASE_URL}/api/lab/runs/{run_id}")
            assert g.status_code == 200, g.text
            body = g.json()
            status = body.get("status")
            if status in ("DONE", "FAILED", "ERROR"):
                result = body.get("result") or body.get("results")
                break
            time.sleep(3)

        assert status == "DONE", f"final status={status}"
        assert result, "result missing"
        per_symbol = result.get("per_symbol") or {}
        assert any(k in per_symbol for k in ("BTC/USD", "ETH/USD", "SOL/USD")), \
            f"per_symbol empty: {list(per_symbol.keys())}"

        # THIS SESSION'S FIX: exit_comparison at RESULT top-level, keyed by symbol -> timeframe
        ec = result.get("exit_comparison")
        assert isinstance(ec, dict) and ec, f"exit_comparison missing/empty at result top level: {ec}"
        # Pick any populated symbol
        got_rows = False
        for sym, tf_map in ec.items():
            if not isinstance(tf_map, dict):
                continue
            for tf, block in tf_map.items():
                if not isinstance(block, dict):
                    continue
                rows = block.get("rows") or {}
                if rows:
                    got_rows = True
                    # winner_key present
                    assert "winner_key" in block, f"winner_key missing in {sym}/{tf}: {block.keys()}"
                    # rows have expected fields
                    for rkey, row in rows.items():
                        for f in ("label", "total_return_pct", "win_rate_pct", "profit_factor", "max_drawdown_pct", "trades"):
                            assert f in row, f"row {rkey} missing field {f}: {row.keys()}"
                    break
            if got_rows:
                break
        assert got_rows, f"no populated rows found in exit_comparison[sym][tf]: {ec}"
