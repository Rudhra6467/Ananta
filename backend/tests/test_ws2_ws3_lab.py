"""
Backend integration tests for WS2 (Hunter Continuation strategy) and WS3 (Research Lab
validation redesign — Mode C presets, multi-timeframe comparison, recommendations).

Exercises the REAL owner-gated /api/lab/* endpoints against the live backend.
The lab worker runs ONE job at a time — keep the number of NEW runs minimal and
prefer reusing existing DONE runs from the queue for schema assertions.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL") or "owner@ananta.ai"
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD") or "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


def _wait_for_done(run_id, headers, timeout_s=600, poll_s=4):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}", headers=headers, timeout=20)
        assert r.status_code == 200, r.text[:200]
        last = r.json()
        if last.get("status") == "DONE":
            return last
        if last.get("status") == "FAILED":
            pytest.fail(f"run {run_id} FAILED: {last.get('error')}")
        time.sleep(poll_s)
    pytest.fail(f"run {run_id} did not finish in {timeout_s}s; last_status={last and last.get('status')} progress={last and last.get('progress_pct')}")


def _find_existing_done(headers, filt):
    """Find the newest DONE run whose spec/results satisfy filt(run_summary, run_detail)."""
    r = requests.get(f"{BASE_URL}/api/lab/runs?limit=50", headers=headers, timeout=20)
    if r.status_code != 200:
        return None
    for row in r.json().get("runs", []):
        if row.get("status") != "DONE":
            continue
        detail = requests.get(f"{BASE_URL}/api/lab/runs/{row['id']}", headers=headers, timeout=20)
        if detail.status_code != 200:
            continue
        d = detail.json()
        try:
            if filt(row, d):
                return d
        except Exception:
            continue
    return None


# -------- WS3 Mode C: presets endpoint --------
def test_presets_returns_four_expected_ids(auth_headers):
    r = requests.get(f"{BASE_URL}/api/lab/presets", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    ids = [p["id"] for p in data["presets"]]
    for expected in ("conservative", "aggressive", "high_volatility", "reversal_purist"):
        assert expected in ids, f"missing preset '{expected}' — got {ids}"
    for p in data["presets"]:
        assert p.get("label") and p.get("description")
        assert isinstance(p.get("setting_overrides"), dict) and len(p["setting_overrides"]) > 0


# -------- WS3: data coverage on 1h --------
def test_coverage_has_bars_1h_per_symbol(auth_headers):
    r = requests.get(f"{BASE_URL}/api/lab/data/coverage", headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    symbols = data.get("symbols")
    assert isinstance(symbols, list) and len(symbols) > 0, data
    for row in symbols:
        assert row.get("bars_1h", 0) > 0, f"symbol {row.get('symbol')} has bars_1h={row.get('bars_1h')}"


# -------- WS3 Mode C: preset run schema (reuse if a DONE preset run exists, else create one) --------
@pytest.fixture(scope="module")
def conservative_run(auth_headers):
    """A DONE conservative-preset backtest on BTC/USD (either pre-existing or freshly submitted)."""
    def _is_conservative(row, detail):
        so = detail.get("setting_overrides") or {}
        return (row.get("kind") == "backtest"
                and "BTC/USD" in (row.get("symbols") or [])
                and so.get("stop_loss_pct") == 8.0
                and so.get("vcp_enabled") is True
                and so.get("rsi_reset_max") == 33.0
                and (detail.get("result") or {}).get("per_symbol", {}).get("BTC/USD"))
    existing = _find_existing_done(auth_headers, _is_conservative)
    if existing:
        return existing
    body = {"kind": "backtest", "symbols": ["BTC/USD"], "period": "3m", "preset": "conservative"}
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_headers, json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("kind") == "backtest"
    return _wait_for_done(r.json()["id"], auth_headers, timeout_s=600)


def test_preset_run_setting_overrides_applied(conservative_run):
    so = conservative_run.get("setting_overrides") or {}
    assert so.get("stop_loss_pct") == 8.0
    assert so.get("rsi_reset_min") == 30.0
    assert so.get("rsi_reset_max") == 33.0
    assert so.get("vol_exhaustion_ratio_max") == 0.5
    assert so.get("vcp_enabled") is True
    assert so.get("cont_pullback_max_pct") == 8.0
    assert conservative_run.get("kind") == "backtest"


def test_preset_run_per_symbol_has_full_metrics(conservative_run):
    per = (conservative_run.get("result") or {}).get("per_symbol") or {}
    assert "BTC/USD" in per, per.keys()
    m = per["BTC/USD"]
    for key in ("sharpe", "sortino", "profit_factor", "recommendation",
                "strategy_breakdown", "avg_mfe_pct", "avg_mae_pct"):
        assert key in m, f"missing '{key}' in per_symbol[BTC/USD]; got keys {sorted(m.keys())}"
    assert isinstance(m["recommendation"], str) and len(m["recommendation"]) > 5
    assert isinstance(m["strategy_breakdown"], dict)


def test_preset_run_multi_timeframe_has_15m_30m_1h(conservative_run):
    mtf = (conservative_run.get("result") or {}).get("multi_timeframe") or {}
    assert "BTC/USD" in mtf
    by_tf = mtf["BTC/USD"].get("by_tf") or {}
    for tf in ("15m", "30m", "1h"):
        assert tf in by_tf, f"missing tf '{tf}' — got {list(by_tf.keys())}"
    verdict = mtf["BTC/USD"].get("verdict") or {}
    assert "best_tf" in verdict and "reason" in verdict


def test_continuation_appears_in_strategy_breakdown(conservative_run):
    """WS2: with continuation_enabled defaulted True and cont_pullback_max_pct=8, the
    Continuation strategy should fire at least a few times on BTC/USD in the 3m window."""
    m = (conservative_run.get("result") or {}).get("per_symbol", {}).get("BTC/USD", {})
    sb = m.get("strategy_breakdown") or {}
    assert "continuation" in sb, f"'continuation' bucket missing from strategy_breakdown: {sb}"
    assert isinstance(sb["continuation"], dict)
    assert "n" in sb["continuation"] and sb["continuation"]["n"] >= 0


# -------- WS3 Mode A: multi-symbol backtest (reuse if possible) --------
@pytest.fixture(scope="module")
def two_symbol_run(auth_headers):
    def _is_two_sym(row, detail):
        syms = set(row.get("symbols") or [])
        return (row.get("kind") == "backtest"
                and syms == {"BTC/USD", "ETH/USD"}
                and not (detail.get("setting_overrides") or {})
                and (detail.get("result") or {}).get("multi_timeframe", {}).get("BTC/USD"))
    existing = _find_existing_done(auth_headers, _is_two_sym)
    if existing:
        return existing
    body = {"kind": "backtest", "symbols": ["BTC/USD", "ETH/USD"], "period": "3m"}
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_headers, json=body, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return _wait_for_done(r.json()["id"], auth_headers, timeout_s=900)


def test_mode_a_backtest_full_shape(two_symbol_run):
    result = two_symbol_run.get("result") or {}
    per = result.get("per_symbol") or {}
    assert set(per.keys()) >= {"BTC/USD", "ETH/USD"}
    mtf = result.get("multi_timeframe") or {}
    for sym in ("BTC/USD", "ETH/USD"):
        assert isinstance(per[sym].get("recommendation"), str) and len(per[sym]["recommendation"]) > 5
        by_tf = (mtf.get(sym) or {}).get("by_tf") or {}
        assert set(by_tf.keys()) >= {"15m", "30m", "1h"}
        assert (mtf[sym].get("verdict") or {}).get("reason")


# -------- PDF export --------
def test_pdf_download_for_completed_backtest(auth_headers, conservative_run):
    run_id = conservative_run["id"]
    r = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}/pdf", headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 2000, f"PDF suspiciously small: {len(r.content)} bytes"
