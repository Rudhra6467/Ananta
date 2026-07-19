"""Backend confirmation for the 'Use my live Exit Engine settings' toggle."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


def _wait(run_id, headers, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        r = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}", headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("status") in ("DONE", "ERROR", "FAILED"):
            return d
        time.sleep(2)
    raise TimeoutError(f"run {run_id} did not finish")


def test_use_live_exit_true_sets_live_source(owner_headers):
    spec = {
        "kind": "backtest",
        "symbols": ["BTC/USD"],
        "period": "1m",
        "strategies": ["ema_ribbon"],
        "use_live_exit_settings": True,
    }
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=owner_headers, json=spec, timeout=20)
    assert r.status_code in (200, 201), r.text
    run_id = r.json()["id"]
    try:
        d = _wait(run_id, owner_headers)
        assert d["status"] == "DONE", d
        assert d.get("exit_source") == "live", f"expected exit_source=live, got {d.get('exit_source')}"
        assert d.get("exit_method") == "engine", f"expected exit_method=engine, got {d.get('exit_method')}"
        # PDF must reflect the mode
        pdf = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}/pdf", headers=owner_headers, timeout=30)
        assert pdf.status_code == 200
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(pdf.content)) as p:
            text = "\n".join((page.extract_text() or "") for page in p.pages)
        assert "Live Exit Engine (deployed config)" in text, "PDF should mention 'Live Exit Engine (deployed config)'"
        assert "Exit method used: Live Exit Engine (deployed config)" in text
        assert "Exit settings" in text
    finally:
        requests.delete(f"{BASE_URL}/api/lab/runs/{run_id}", headers=owner_headers, timeout=15)


def test_use_live_exit_false_is_manual(owner_headers):
    spec = {
        "kind": "backtest",
        "symbols": ["BTC/USD"],
        "period": "1m",
        "strategies": ["ema_ribbon"],
        "use_live_exit_settings": False,
        "exit_method": "atr",
    }
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=owner_headers, json=spec, timeout=20)
    assert r.status_code in (200, 201), r.text
    run_id = r.json()["id"]
    try:
        d = _wait(run_id, owner_headers)
        assert d["status"] == "DONE", d
        assert d.get("exit_source") == "manual", f"expected exit_source=manual, got {d.get('exit_source')}"
        pdf = requests.get(f"{BASE_URL}/api/lab/runs/{run_id}/pdf", headers=owner_headers, timeout=30)
        assert pdf.status_code == 200
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(pdf.content)) as p:
            text = "\n".join((page.extract_text() or "") for page in p.pages)
        assert "Manual override (selected for this run)" in text, "PDF should mention 'Manual override (selected for this run)'"
    finally:
        requests.delete(f"{BASE_URL}/api/lab/runs/{run_id}", headers=owner_headers, timeout=15)
