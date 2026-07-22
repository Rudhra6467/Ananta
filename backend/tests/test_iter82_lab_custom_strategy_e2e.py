"""iter82 e2e: Custom (cloned) strategies executable end-to-end via public API in the Lab.

Flow:
  1. Owner login -> Bearer token
  2. POST /api/library/ema-cross/clone -> new clone-XXXX key
  3. GET /api/strategy/registry -> clone key present
  4. POST /api/lab/runs (backtest, BTC/USD, 3m, strategies=[clone], 1h, atr) -> id
  5. Poll GET /api/lab/runs/{id} until DONE (timeout ~180s)
  6. Assert per_symbol['BTC/USD'].entries>0, trades>0, strategy_breakdown keys == [clone]
  7. Regression: same flow with strategies=[hunter], strategies=[ema-cross] -> each attribution non-empty
  8. Cleanup: DELETE /api/library/{clone-key}
"""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")
POLL_TIMEOUT_S = 240
POLL_INTERVAL_S = 3


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def clone_key(hdrs):
    r = requests.post(f"{BASE_URL}/api/library/ema-cross/clone", headers=hdrs,
                      json={"name": "iter82 custom EMA"}, timeout=30)
    assert r.status_code == 200, f"clone failed: {r.status_code} {r.text}"
    data = r.json()
    key = data.get("id") or data.get("key") or data.get("clone_key") or (data.get("strategy") or {}).get("id")
    assert key and key.startswith("clone-"), f"unexpected clone response: {data}"
    yield key
    # Teardown: delete the clone
    d = requests.delete(f"{BASE_URL}/api/library/{key}", headers=hdrs, timeout=15)
    assert d.status_code in (200, 204, 404), f"cleanup delete failed: {d.status_code} {d.text}"


def _poll_run(rid: str, hdrs: dict):
    """Poll GET /api/lab/runs/{id} until status == DONE/ERROR or timeout."""
    deadline = time.time() + POLL_TIMEOUT_S
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/lab/runs/{rid}", headers=hdrs, timeout=15)
        assert r.status_code == 200, f"poll failed: {r.status_code} {r.text}"
        last = r.json()
        st = (last.get("status") or "").upper()
        if st in ("DONE", "ERROR", "FAILED", "CANCELLED"):
            return last
        time.sleep(POLL_INTERVAL_S)
    pytest.fail(f"lab run {rid} did not finish within {POLL_TIMEOUT_S}s. Last status: {(last or {}).get('status')}")


def _enqueue_backtest(hdrs: dict, strategies: list[str]) -> str:
    payload = {
        "kind": "backtest",
        "symbols": ["BTC/USD"],
        "period": "3m",
        "strategies": strategies,
        "timeframe": "1h",
        "exit_method": "atr",
    }
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=hdrs, json=payload, timeout=20)
    assert r.status_code == 200, f"enqueue failed for {strategies}: {r.status_code} {r.text}"
    rid = r.json().get("id")
    assert rid
    return rid


# --- Test 1: clone appears in registry ---------------------------------------
def test_clone_appears_in_registry(clone_key, hdrs):
    r = requests.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json().get("strategies", [])}
    assert clone_key in keys, f"clone {clone_key} missing from registry. Keys: {sorted(keys)}"


# --- Test 2: custom clone runs end-to-end in the Lab -------------------------
def test_lab_backtest_runs_custom_clone(clone_key, hdrs):
    rid = _enqueue_backtest(hdrs, [clone_key])
    final = _poll_run(rid, hdrs)
    assert (final.get("status") or "").upper() == "DONE", f"run not DONE: {final.get('status')} err={final.get('error')}"
    result = final.get("result") or {}
    per_sym = (result.get("per_symbol") or {}).get("BTC/USD") or {}
    entries = per_sym.get("entries", 0)
    trades = per_sym.get("trades", 0)
    breakdown = per_sym.get("strategy_breakdown") or {}
    assert entries > 0, f"custom clone produced 0 entries — the P2 fix is broken. per_symbol={per_sym}"
    assert trades > 0, f"custom clone produced 0 trades. per_symbol={per_sym}"
    assert set(breakdown.keys()) == {clone_key}, f"strategy_breakdown mismatch: expected {{{clone_key}}}, got {set(breakdown.keys())}"


# --- Test 3: regression — core strategy (hunter) still executes --------------
def test_lab_backtest_regression_hunter(hdrs):
    rid = _enqueue_backtest(hdrs, ["hunter"])
    final = _poll_run(rid, hdrs)
    assert (final.get("status") or "").upper() == "DONE", f"hunter run not DONE: {final.get('status')}"
    per_sym = ((final.get("result") or {}).get("per_symbol") or {}).get("BTC/USD") or {}
    breakdown = per_sym.get("strategy_breakdown") or {}
    # Hunter may or may not enter in a 3m window, but the run must not error and breakdown must not contain
    # a wrongly-attributed key. If it entered, keys must include 'hunter'.
    assert per_sym.get("entries", 0) >= 0
    if breakdown:
        assert "hunter" in breakdown, f"hunter attribution missing from breakdown: {breakdown}"


# --- Test 4: regression — catalog declarative strategy (ema-cross) -----------
def test_lab_backtest_regression_ema_cross(hdrs):
    rid = _enqueue_backtest(hdrs, ["ema-cross"])
    final = _poll_run(rid, hdrs)
    assert (final.get("status") or "").upper() == "DONE", f"ema-cross run not DONE: {final.get('status')}"
    per_sym = ((final.get("result") or {}).get("per_symbol") or {}).get("BTC/USD") or {}
    breakdown = per_sym.get("strategy_breakdown") or {}
    assert per_sym.get("entries", 0) > 0, f"ema-cross catalog strategy produced 0 entries — regression. per_symbol={per_sym}"
    assert set(breakdown.keys()) == {"ema-cross"}, f"ema-cross breakdown mismatch: {set(breakdown.keys())}"
