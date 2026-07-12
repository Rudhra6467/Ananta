"""
iter48 — P0 backend regression:
- Lab runs across timeframes (1h default, 30m, 15m) exercise on-demand CCXT backfill
- Public report PDFs return valid application/pdf
- Lab per-run PDF returns valid application/pdf after DONE
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://hunter-squeeze-labs.preview.emergentagent.com",
).rstrip("/")


def _login_owner():
    email = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
    pwd = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:150]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers():
    return {"Authorization": f"Bearer {_login_owner()}"}


def _wait_done(run_id, headers, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}", headers=headers, timeout=15)
        assert r.status_code == 200, f"poll {run_id}: {r.status_code} {r.text[:200]}"
        j = r.json()
        last = j
        status = j.get("status") or j.get("state")
        if status in ("DONE", "done", "COMPLETED", "completed", "error", "ERROR", "failed", "FAILED"):
            return j
        time.sleep(3)
    return last


@pytest.mark.parametrize("tf", ["15m", "30m", "1h"])
def test_lab_run_backtest_timeframes(owner_headers, tf):
    """POST /api/lab/runs with timeframe → poll → DONE with non-empty trades."""
    payload = {
        "kind": "backtest",
        "symbols": ["BTC/USD"],
        "period": "1m",
        "strategies": ["hunter"],
        "exit_method": "fixed",
        "timeframe": tf,
    }
    r = requests.post(f"{BASE_URL}/api/lab/runs", json=payload, headers=owner_headers, timeout=30)
    assert r.status_code in (200, 201), f"create run tf={tf}: {r.status_code} {r.text[:300]}"
    run = r.json()
    rid = run.get("id") or run.get("run_id") or run.get("_id")
    assert rid, f"missing id in run response: {run}"

    final = _wait_done(rid, owner_headers, timeout=240)
    status = (final.get("status") or final.get("state") or "").lower()
    assert status in ("done", "completed"), f"tf={tf} final status={status} full={str(final)[:500]}"

    per_symbol = final.get("per_symbol") or final.get("result", {}).get("per_symbol") or {}
    # non-empty per_symbol with at least one entry
    assert per_symbol, f"tf={tf} per_symbol empty: {str(final)[:400]}"
    # find trades count (may be under keys 'trades' or 'trades_count')
    trades_found = False
    for k, v in per_symbol.items():
        if not isinstance(v, dict):
            continue
        # 'trades' here is an INT count in the API; the actual trade list is 'trade_log'
        trade_log = v.get("trade_log") or v.get("trades_list") or []
        if isinstance(v.get("trades"), list):
            trade_log = v.get("trades")
        tcount = v.get("trades") if isinstance(v.get("trades"), int) else None
        if (isinstance(trade_log, list) and len(trade_log) > 0) or (tcount and tcount > 0):
            trades_found = True
            break
    assert trades_found, f"tf={tf} no non-empty trades in per_symbol"

    # PDF for this run
    pdf = requests.get(f"{BASE_URL}/api/lab/runs/{rid}/pdf", headers=owner_headers, timeout=30)
    assert pdf.status_code == 200, f"tf={tf} pdf status={pdf.status_code}"
    assert pdf.headers.get("content-type", "").startswith("application/pdf"), f"tf={tf} bad ct={pdf.headers.get('content-type')}"
    assert pdf.content[:4] == b"%PDF", f"tf={tf} not a real pdf head={pdf.content[:8]!r}"


def test_public_report_full_pdf():
    r = requests.get(f"{BASE_URL}/api/report/full.pdf", timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_public_report_trades_pdf():
    r = requests.get(f"{BASE_URL}/api/report/trades.pdf", timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
