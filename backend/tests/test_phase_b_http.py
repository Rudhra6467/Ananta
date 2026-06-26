"""Phase B HTTP regression tests — Execution Friction Mitigation Layer.

Validates the PUBLIC backend API (via REACT_APP_BACKEND_URL) for:
  - GET /api/pending_orders shape
  - GET /api/settings includes maker_fee_pct + breakout_paper_slippage_pct
  - PUT /api/settings can update both (clamped 0..5) and they persist
  - POST /api/cycle/run/BTC works and emits reasoning.evidence.spread_pct_bid_based
  - GET /api/analytics/performance includes total_slippage_usd + total_friction_usd
  - Regression: /api/trades, /api/state, /api/risk/status
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback to reading frontend/.env directly so tests still run locally
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.strip().split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Pending orders endpoint shape ---
def test_pending_orders_shape(api):
    r = api.get(f"{BASE_URL}/api/pending_orders", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "count" in body
    assert isinstance(body["items"], list)
    assert body["count"] == len(body["items"])


# --- Settings: new fields exist + clamp + persist ---
def test_settings_has_phase_b_fields(api):
    r = api.get(f"{BASE_URL}/api/settings", timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    assert "maker_fee_pct" in s, "maker_fee_pct missing in settings"
    assert "breakout_paper_slippage_pct" in s, "breakout_paper_slippage_pct missing"
    # Defaults per spec
    assert float(s["maker_fee_pct"]) == pytest.approx(0.25, abs=0.0001)
    assert float(s["breakout_paper_slippage_pct"]) == pytest.approx(0.10, abs=0.0001)


def test_settings_put_clamps_and_persists(api):
    # Snapshot current values
    cur = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
    orig_maker = cur["maker_fee_pct"]
    orig_slip = cur["breakout_paper_slippage_pct"]

    # Out-of-range -> clamp to 5
    over = api.put(
        f"{BASE_URL}/api/settings",
        json={"maker_fee_pct": 999, "breakout_paper_slippage_pct": -10},
        timeout=15,
    )
    assert over.status_code == 200, over.text
    after = over.json()
    assert float(after["maker_fee_pct"]) == pytest.approx(5.0, abs=0.0001)
    assert float(after["breakout_paper_slippage_pct"]) == pytest.approx(0.0, abs=0.0001)

    # In-range -> exact + persisted on re-GET
    upd = api.put(
        f"{BASE_URL}/api/settings",
        json={"maker_fee_pct": 0.30, "breakout_paper_slippage_pct": 0.15},
        timeout=15,
    )
    assert upd.status_code == 200, upd.text
    re_get = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
    assert float(re_get["maker_fee_pct"]) == pytest.approx(0.30, abs=0.0001)
    assert float(re_get["breakout_paper_slippage_pct"]) == pytest.approx(0.15, abs=0.0001)

    # Restore originals so we don't pollute env state
    api.put(
        f"{BASE_URL}/api/settings",
        json={
            "maker_fee_pct": float(orig_maker),
            "breakout_paper_slippage_pct": float(orig_slip),
        },
        timeout=15,
    )
    final = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
    assert float(final["maker_fee_pct"]) == pytest.approx(float(orig_maker), abs=0.0001)
    assert float(final["breakout_paper_slippage_pct"]) == pytest.approx(float(orig_slip), abs=0.0001)


# --- Cycle run regression + spread-gate evidence ---
def test_cycle_run_btc_emits_decision_and_spread_evidence(api):
    r = api.post(f"{BASE_URL}/api/cycle/run/BTC", timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    # decision + reasoning_id should be present (per Phase B spec)
    assert "decision" in body, f"missing decision in {body}"
    # reasoning_id may be top-level or nested; accept either presence
    rid = body.get("reasoning_id") or (body.get("reasoning") or {}).get("id")
    assert rid, f"missing reasoning_id in {body}"

    # Fetch the reasoning doc via list endpoint and locate by id
    rr = api.get(f"{BASE_URL}/api/reasoning?limit=50&symbol=BTC", timeout=15)
    assert rr.status_code == 200, rr.text
    items = rr.json().get("items", [])
    match = next((d for d in items if d.get("id") == rid), None)
    assert match, f"reasoning_id {rid} not found in recent reasoning list (got {len(items)} docs)"
    evidence = match.get("evidence") or {}
    assert "spread_pct_bid_based" in evidence, (
        f"spread_pct_bid_based missing; got evidence keys={list(evidence.keys())}"
    )


# --- Analytics: friction + slippage fields in both windows ---
def test_analytics_includes_slippage_and_friction(api):
    r = api.get(f"{BASE_URL}/api/analytics/performance", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    # Expect two windows: e.g. last_30d / all_time (Phase A shape)
    found_windows = 0
    for key, win in body.items():
        if isinstance(win, dict) and ("total_slippage_usd" in win or "total_friction_usd" in win):
            found_windows += 1
            assert "total_slippage_usd" in win, f"{key} missing total_slippage_usd"
            assert "total_friction_usd" in win, f"{key} missing total_friction_usd"
            # Numbers
            assert isinstance(win["total_slippage_usd"], (int, float))
            assert isinstance(win["total_friction_usd"], (int, float))
    assert found_windows >= 2, f"expected >=2 analytic windows with friction; body={body}"


# --- Regression endpoints ---
@pytest.mark.parametrize("path", ["/api/trades", "/api/live/status", "/api/risk/status"])
def test_regression_endpoints_200(api, path):
    r = api.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
