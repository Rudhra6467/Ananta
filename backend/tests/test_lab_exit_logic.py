"""
Backend tests for the new EXIT LOGIC feature on /api/lab/runs.

Covers:
- POST /api/lab/runs accepts exit_method / target_profit / target_loss
- Fixed exit run nets ~+$5 / ~-$4 per trade and stores exit_method_label + trade_log
- Engine exit run stores 'Universal Exit Engine (ATR-based)' label
- Runs list surfaces exit_method / target_profit / target_loss (needed by web badges)
- PDF endpoint returns 200 non-empty for a completed run
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def assets(auth):
    r = requests.get(f"{API}/lab/data/coverage", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    syms = [s["symbol"] for s in (r.json().get("symbols") or []) if s.get("bars_1h", 0) > 0]
    assert len(syms) >= 1, "need at least 1 seeded asset"
    return syms[:2]


def _wait_done(auth, run_id, timeout=90):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{API}/lab/runs/{run_id}", headers=auth, timeout=10)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("DONE", "FAILED"):
            return last
        time.sleep(2)
    pytest.fail(f"run {run_id} did not finish in {timeout}s (last={last and last.get('status')})")


def _create(auth, assets, exit_method, tp=5, tl=4):
    body = {
        "kind": "backtest",
        "symbols": assets,
        "period": "2m",
        "strategies": ["hunter", "squeeze", "continuation"],
        "compare_timeframes": False,
        "exit_method": exit_method,
        "target_profit": tp,
        "target_loss": tl,
    }
    r = requests.post(f"{API}/lab/runs", headers=auth, json=body, timeout=15)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    return r.json()


# --- FIXED exit ---
def test_fixed_exit_run_creates_and_completes(auth, assets):
    created = _create(auth, assets, "fixed", tp=5, tl=4)
    assert created.get("id")
    # optional: server may echo params back
    if "exit_method" in created:
        assert created["exit_method"] == "fixed"
    run = _wait_done(auth, created["id"])
    assert run["status"] == "DONE", f"run failed: {run.get('error')}"
    # fields for badge + banner
    assert run.get("exit_method") == "fixed"
    assert float(run.get("target_profit", 0)) == 5
    assert float(run.get("target_loss", 0)) == 4
    result = run.get("result") or {}
    assert "exit_method_label" in result and "Fixed" in result["exit_method_label"]
    # trade log must be present + fixed exits should net ~+5 / ~-4
    per = result.get("per_symbol") or {}
    assert per, "expected per_symbol block"
    saw_trade = False
    for sym, m in per.items():
        tl = m.get("trade_log") or []
        for t in tl:
            saw_trade = True
            mod = t.get("exit_module", "")
            # end-of-window forced mark-out is exempt (still open at last bar)
            if mod == "EOD" or t.get("exit_reason") == "END_OF_WINDOW":
                continue
            # every closed fixed trade should land ~+5 or ~-4 (±$0.05 rounding)
            assert mod in ("FIXED_TP", "FIXED_SL"), f"unexpected exit_module in fixed run: {mod!r}"
            assert t["pnl"] == pytest.approx(5, abs=0.05) or t["pnl"] == pytest.approx(-4, abs=0.05), (
                f"fixed-exit trade P&L outside ±$5/$4 window: {t['pnl']} on {sym} module={mod}"
            )
            # trade_log shape
            for k in ("entry_ts", "exit_ts", "entry_price", "exit_price", "qty", "pnl", "exit_module"):
                assert k in t, f"trade missing key {k}"
    assert saw_trade, "expected at least one trade in trade_log"
    return run["id"]


# --- ENGINE exit ---
def test_engine_exit_run_creates_and_completes(auth, assets):
    created = _create(auth, assets, "engine")
    run = _wait_done(auth, created["id"])
    assert run["status"] == "DONE", f"run failed: {run.get('error')}"
    assert run.get("exit_method") == "engine"
    result = run.get("result") or {}
    label = result.get("exit_method_label", "")
    assert "Universal" in label or "Engine" in label or "ATR" in label, f"bad engine label: {label!r}"


# --- runs list surfaces fields needed by UI badge ---
def test_runs_list_has_exit_fields(auth):
    r = requests.get(f"{API}/lab/runs?limit=8", headers=auth, timeout=15)
    assert r.status_code == 200
    runs = r.json().get("runs") or []
    assert runs, "expected at least the runs we just created"
    # at least one row must have exit_method populated
    with_exit = [x for x in runs if x.get("exit_method")]
    assert with_exit, "runs list is missing exit_method field on rows"


# --- PDF ---
def test_pdf_download_for_completed_run(auth):
    r = requests.get(f"{API}/lab/runs?limit=8", headers=auth, timeout=15)
    runs = [x for x in r.json().get("runs") or [] if x["status"] == "DONE"]
    assert runs, "need a completed run"
    rid = runs[0]["id"]
    p = requests.get(f"{API}/lab/runs/{rid}/pdf", headers=auth, timeout=30)
    assert p.status_code == 200, p.status_code
    assert p.headers.get("content-type", "").startswith("application/pdf")
    assert len(p.content) > 500, f"PDF too small: {len(p.content)} bytes"
