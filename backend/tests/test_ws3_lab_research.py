"""WS3 Research Lab regression tests — reuses existing DONE backtest runs.

Covers:
- GET /api/lab/presets returns 4 presets
- GET /api/lab/data/coverage returns bars_1h > 0 per symbol
- GET /api/lab/runs?limit=10 -> pick DONE backtest
- GET /api/lab/runs/{id} has result.per_symbol[sym].{sharpe,sortino,profit_factor,recommendation,strategy_breakdown}
  and result.multi_timeframe[sym].by_tf{15m,30m,1h} + verdict{best_tf,reason}
- GET /api/lab/runs/{id}/pdf returns application/pdf
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=60)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def done_backtest_id(auth):
    r = requests.get(f"{BASE_URL}/api/lab/runs?limit=20", headers=auth, timeout=15)
    assert r.status_code == 200
    runs = r.json().get("runs") or []
    for run in runs:
        if run.get("kind") == "backtest" and run.get("status") == "DONE":
            return run["id"]
    pytest.skip("No DONE backtest run available in DB")


def test_presets_returns_four(auth):
    r = requests.get(f"{BASE_URL}/api/lab/presets", headers=auth, timeout=15)
    assert r.status_code == 200
    presets = r.json().get("presets") or []
    assert len(presets) == 4, f"expected 4 presets, got {len(presets)}"
    ids = {p["id"] for p in presets}
    assert {"conservative", "aggressive", "high_volatility", "reversal_purist"}.issubset(ids)


def test_coverage_bars_1h_positive(auth):
    r = requests.get(f"{BASE_URL}/api/lab/data/coverage", headers=auth, timeout=15)
    assert r.status_code == 200
    symbols = r.json().get("symbols") or []
    assert len(symbols) > 0
    for s in symbols:
        assert s.get("bars_1h", 0) > 0, f"{s.get('symbol')} has no 1h bars"


def test_run_detail_has_required_metrics(auth, done_backtest_id):
    r = requests.get(f"{BASE_URL}/api/lab/runs/{done_backtest_id}", headers=auth, timeout=20)
    assert r.status_code == 200
    result = r.json().get("result") or {}
    per = result.get("per_symbol") or {}
    mtf = result.get("multi_timeframe") or {}
    assert per, "per_symbol missing"
    for sym, m in per.items():
        for key in ("sharpe", "sortino", "profit_factor", "recommendation", "strategy_breakdown"):
            assert key in m, f"per_symbol[{sym}] missing {key}"
        mt = mtf.get(sym)
        assert mt, f"multi_timeframe missing for {sym}"
        by_tf = mt.get("by_tf") or {}
        for tf in ("15m", "30m", "1h"):
            assert tf in by_tf, f"multi_timeframe[{sym}].by_tf missing {tf}"
        verdict = mt.get("verdict") or {}
        assert "best_tf" in verdict
        assert "reason" in verdict


def test_run_pdf_returns_application_pdf(auth, done_backtest_id):
    r = requests.get(f"{BASE_URL}/api/lab/runs/{done_backtest_id}/pdf", headers=auth, timeout=30)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF", "PDF magic bytes missing"
