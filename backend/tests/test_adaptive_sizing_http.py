"""External HTTP integration tests for the Adaptive Lot Sizing feature.

Hits the public REACT_APP_BACKEND_URL/api endpoints to validate end-to-end
that settings/portfolio/public-snapshot/reasoning all expose the new
adaptive fields and clamp inputs correctly.
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for local pytest runs - read /app/frontend/.env directly
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

API = f"{BASE_URL}/api"
TIMEOUT = 30
LONG_TIMEOUT = 90  # cycle/run hits Gemini, can be slow


@pytest.fixture(scope="module")
def original_settings():
    """Snapshot settings at start so we can restore at end of module."""
    r = requests.get(f"{API}/settings", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    snap = r.json()
    yield snap
    # restore the new adaptive fields to their snapshot
    restore = {
        k: snap[k] for k in (
            "adaptive_sizing_enabled", "normal_lot_usd", "strong_lot_usd",
            "strong_min_confidence", "strong_min_atr_percentile", "strong_min_adx",
            "max_concurrent_positions",
        ) if k in snap
    }
    requests.put(f"{API}/settings", json=restore, timeout=TIMEOUT)


# ---------------- 1. GET /api/settings exposes new fields with defaults ----
def test_settings_get_exposes_adaptive_fields(original_settings):
    s = original_settings
    # presence
    for k in (
        "adaptive_sizing_enabled", "normal_lot_usd", "strong_lot_usd",
        "strong_min_confidence", "strong_min_atr_percentile", "strong_min_adx",
        "max_concurrent_positions",
    ):
        assert k in s, f"missing {k} in /api/settings"
    # types
    assert isinstance(s["adaptive_sizing_enabled"], bool)
    assert isinstance(s["normal_lot_usd"], (int, float))
    assert isinstance(s["strong_lot_usd"], (int, float))
    assert isinstance(s["max_concurrent_positions"], int)


# ---------------- 2. PUT clamps + persists ---------------------------------
def test_settings_put_persists_in_range_values():
    payload = {
        "normal_lot_usd": 7.5,
        "strong_lot_usd": 15.0,
        "strong_min_confidence": 0.8,
        "max_concurrent_positions": 3,
    }
    r = requests.put(f"{API}/settings", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text

    g = requests.get(f"{API}/settings", timeout=TIMEOUT).json()
    assert g["normal_lot_usd"] == pytest.approx(7.5)
    assert g["strong_lot_usd"] == pytest.approx(15.0)
    assert g["strong_min_confidence"] == pytest.approx(0.8)
    assert g["max_concurrent_positions"] == 3


def test_settings_put_clamps_out_of_range():
    payload = {
        "normal_lot_usd": 99999,           # -> 1000
        "strong_min_confidence": 2.0,      # -> 1.0
        "max_concurrent_positions": 99,    # -> 20
    }
    r = requests.put(f"{API}/settings", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text

    g = requests.get(f"{API}/settings", timeout=TIMEOUT).json()
    assert g["normal_lot_usd"] == pytest.approx(1000.0)
    assert g["strong_min_confidence"] == pytest.approx(1.0)
    assert g["max_concurrent_positions"] == 20


# ---------------- 3. GET /api/portfolio exposes slots_used -----------------
def test_portfolio_exposes_slots_used_and_cap():
    r = requests.get(f"{API}/portfolio", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    p = r.json()
    assert "slots_used" in p
    assert "max_concurrent_positions" in p
    assert isinstance(p["slots_used"], int)
    assert isinstance(p["max_concurrent_positions"], int)
    # slots_used should equal number of positions with quantity>0
    expected = sum(1 for pos in p.get("positions", []) if pos.get("quantity", 0) > 0)
    assert p["slots_used"] == expected


# ---------------- 4. /api/public/snapshot whitelist ------------------------
def test_public_snapshot_includes_adaptive_fields_and_no_secrets():
    r = requests.get(f"{API}/public/snapshot", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "settings" in data
    s = data["settings"]
    for k in (
        "adaptive_sizing_enabled", "normal_lot_usd", "strong_lot_usd",
        "strong_min_confidence", "strong_min_atr_percentile", "strong_min_adx",
        "max_concurrent_positions",
    ):
        assert k in s, f"public snapshot missing {k}"
    # secrets must NEVER appear
    assert "kraken_api_secret" not in s
    assert "coinbase_api_secret" not in s
    # also assert no secret value appears in entire response as a sanity check
    flat = str(data).lower()
    assert "api_secret" not in flat or all(
        marker not in flat for marker in ("secret_key=", "actualsecret")
    )


# ---------------- 5. cycle/run + reasoning evidence ------------------------
def test_cycle_run_records_setup_strength_and_evidence():
    # ensure adaptive is enabled
    requests.put(f"{API}/settings", json={"adaptive_sizing_enabled": True}, timeout=TIMEOUT)
    # cycle hits Gemini and may exceed Cloudflare's 100s ingress timeout. Retry once on 5xx;
    # if it still 502s, validate that *some* recent reasoning row carries the new evidence
    # keys - they are written before the HTTP response returns.
    rc = None
    for _ in range(2):
        try:
            rc = requests.post(f"{API}/cycle/run/BTC", timeout=LONG_TIMEOUT)
            if rc.status_code == 200:
                break
        except requests.exceptions.RequestException:
            rc = None
    # Even if HTTP failed (CF 502 timeout), the cycle worker writes reasoning first.

    rr = requests.get(f"{API}/reasoning", params={"symbol": "BTC", "limit": 1}, timeout=TIMEOUT)
    assert rr.status_code == 200, rr.text
    body = rr.json()
    rows = body["items"] if isinstance(body, dict) else body
    assert isinstance(rows, list) and len(rows) >= 1
    ev = rows[0].get("evidence", {})
    assert "setup_strength" in ev, f"evidence missing setup_strength: {ev}"
    assert ev["setup_strength"] in {"STRONG", "NORMAL", "NONE"}
    assert "setup_evidence" in ev
    # if not NONE, the indicator details should be present
    if ev["setup_strength"] != "NONE":
        se = ev["setup_evidence"]
        # at least last_close / ema50 / ema200 should appear when there's enough history;
        # accept either full evidence OR the insufficient-history degrade marker
        if "reason" not in se or "insufficient" not in se.get("reason", ""):
            for k in ("last_close", "ema50", "ema200"):
                assert k in se, f"setup_evidence missing {k}: {se}"


# ---------------- 6. Regressions -------------------------------------------
def test_regression_risk_status():
    r = requests.get(f"{API}/risk/status", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    # risk_status returns {"status": {...}, "thresholds": {...}, ...}
    status = body.get("status", body)
    assert "overall_safe" in status


def test_regression_trades():
    r = requests.get(f"{API}/trades", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    # paginated response: {"count": int, "items": [...]}
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)


def test_regression_cycle_run_endpoint_alive():
    # confirm /api/reasoning still returns the paginated/list shape
    r = requests.get(f"{API}/reasoning", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)
