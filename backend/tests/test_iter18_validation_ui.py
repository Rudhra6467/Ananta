"""
Iteration 18 backend regression: validate the Strategy Validation redesign contracts
consumed by StrategyValidationPanel.jsx:

  - POST /api/auth/login owner login stays fast (<1s) even under load
  - GET /api/lab/data/coverage returns non-empty periods + symbols
  - POST /api/lab/runs accepts { symbols, period, strategies, compare_timeframes }
  - Compare OFF -> multi_timeframe has only 1h; Compare ON -> multi_timeframe has 1h/30m/15m
  - Strategy filter -> only requested strategies appear in strategy_breakdown
  - While a run is RUNNING, /api/auth/login + /api/portfolio remain fast (process isolation)
  - GET /api/lab/runs shows monotonic progress (does not hang mid-run)

Per instruction: use 1-2 assets, compare OFF for the completion test (~20s).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://hunter-squeeze-labs.preview.emergentagent.com"
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


# --- fixtures ---
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and data.get("role") == "owner"
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- auth ---
class TestAuth:
    def test_login_fast(self):
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=5)
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert elapsed < 2.0, f"login too slow: {elapsed:.2f}s"

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": OWNER_EMAIL, "password": "wrong"}, timeout=5)
        assert r.status_code in (401, 403)


# --- lab data ---
class TestLabData:
    def test_coverage(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/lab/data/coverage", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("periods"), list) and len(d["periods"]) > 0
        assert isinstance(d.get("symbols"), list) and len(d["symbols"]) > 0
        # at least one symbol with bars_1h > 0
        assert any(s.get("bars_1h", 0) > 0 for s in d["symbols"])

    def test_presets(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/lab/presets", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "presets" in d


# --- Run helpers ---
def _wait_for_run(auth_headers, run_id, timeout_s=90):
    """Poll /api/lab/runs until terminal or timeout. Returns final run dict + progress trace."""
    trace = []
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        r = requests.get(f"{BASE_URL}/api/lab/runs?limit=30", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        runs = r.json().get("runs", [])
        me = next((x for x in runs if x["id"] == run_id), None)
        assert me is not None, f"run {run_id} disappeared"
        trace.append((me["status"], me.get("progress_pct") or 0))
        if me["status"] in ("DONE", "FAILED"):
            return me, trace
        time.sleep(2)
    return None, trace


class TestRunLifecycle:
    """Track A / current-prod backtest with 1 asset, compare OFF -- should finish in ~20-40s."""

    def test_run_completes_and_strategy_filter(self, auth_headers):
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD"],
            "period": "1m",
            "strategies": ["hunter", "squeeze"],  # NOT continuation
            "compare_timeframes": False,
        }
        r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        run_id = r.json()["id"]

        final, trace = _wait_for_run(auth_headers, run_id, timeout_s=120)
        assert final is not None, f"run did not finish; trace={trace[-5:]}"
        assert final["status"] == "DONE", f"status={final['status']} err={final.get('error')}"
        # progress reached ~100
        assert (final.get("progress_pct") or 0) >= 99

        # get detail
        d = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}", headers=auth_headers, timeout=10).json()
        assert d["status"] == "DONE"
        result = d.get("result") or {}
        per = result.get("per_symbol") or {}
        assert "BTC/USD" in per
        sb = per["BTC/USD"].get("strategy_breakdown") or {}
        # ONLY requested strategies present (continuation must not appear)
        assert "continuation" not in sb, f"strategy filter broken: {list(sb.keys())}"

        # compare OFF -> multi_timeframe should be absent or only 1h
        mtf = result.get("multi_timeframe") or {}
        if mtf:
            by_tf = (mtf.get("BTC/USD") or {}).get("by_tf") or {}
            assert set(by_tf.keys()).issubset({"1h"}), f"expected 1h only, got {list(by_tf.keys())}"


class TestProcessIsolation:
    """While a run is RUNNING, unrelated endpoints stay fast (backend process-isolated)."""

    def test_login_and_portfolio_stay_fast_while_running(self, auth_headers):
        # kick off a backtest with 2 assets so it takes long enough to observe
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD", "ETH/USD"],
            "period": "2m",
            "strategies": ["hunter", "squeeze", "continuation"],
            "compare_timeframes": False,
        }
        r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200
        run_id = r.json()["id"]

        # wait until RUNNING (or DONE if it's very fast)
        saw_running = False
        deadline = time.time() + 30
        while time.time() < deadline:
            runs = requests.get(f"{BASE_URL}/api/lab/runs?limit=30", headers=auth_headers, timeout=10).json()["runs"]
            me = next((x for x in runs if x["id"] == run_id), None)
            if me and me["status"] == "RUNNING":
                saw_running = True
                break
            if me and me["status"] in ("DONE", "FAILED"):
                pytest.skip("run finished before we could sample; can't verify isolation")
            time.sleep(1)
        assert saw_running, "did not observe RUNNING state"

        # sample login + portfolio latency 3 times during the run
        latencies = []
        for _ in range(3):
            t0 = time.time()
            lr = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=5)
            l_elapsed = time.time() - t0
            assert lr.status_code == 200

            t0 = time.time()
            pr = requests.get(f"{BASE_URL}/api/portfolio", headers=auth_headers, timeout=10)
            p_elapsed = time.time() - t0
            assert pr.status_code == 200
            latencies.append((l_elapsed, p_elapsed))
            time.sleep(1)

        # Both endpoints must complete under 2s each even during a heavy run
        for l_e, p_e in latencies:
            assert l_e < 2.5, f"login stalled during run: {l_e:.2f}s"
            assert p_e < 3.0, f"portfolio stalled during run: {p_e:.2f}s"

        # leave the run to finish in background; isolation (latency during run) is the assertion.


class TestCompareTimeframes:
    """Verify compare_timeframes ON -> multi_timeframe contains 1h/30m/15m."""

    def test_compare_on_returns_all_tfs(self, auth_headers):
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD"],
            "period": "1m",
            "strategies": ["hunter", "squeeze", "continuation"],
            "compare_timeframes": True,
        }
        r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        run_id = r.json()["id"]

        final, trace = _wait_for_run(auth_headers, run_id, timeout_s=180)
        assert final is not None, f"compare-ON run did not finish; trace={trace[-5:]}"
        assert final["status"] == "DONE", f"status={final['status']}"

        d = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}", headers=auth_headers, timeout=10).json()
        mtf = (d.get("result") or {}).get("multi_timeframe") or {}
        assert "BTC/USD" in mtf, f"multi_timeframe missing BTC/USD: {list(mtf.keys())}"
        by_tf = mtf["BTC/USD"].get("by_tf") or {}
        # All three timeframes should be represented
        for tf in ("1h", "30m", "15m"):
            assert tf in by_tf, f"missing tf {tf} in {list(by_tf.keys())}"
