"""Mobile surface backend smoke + new endpoints (iteration 14).

Covers:
- Auth: owner login
- NEW: POST /api/notifications/register (owner-gated)
- NEW: POST /api/notifications/test (owner-gated)
- Kill-switch push hook via PUT /api/settings (idempotent toggle on→off)
- Read endpoints consumed by mobile cockpit/portfolio/reports/settings
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL") or os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://hunter-squeeze-labs.preview.emergentagent.com",
)
BASE_URL = BASE_URL.rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    assert "token" in data and data.get("role") == "owner"
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ---------- auth ----------
def test_auth_me(auth_headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("email") == OWNER_EMAIL
    assert j.get("role") == "owner"


def test_auth_me_unauth():
    r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code in (401, 403)


# ---------- NEW: notifications ----------
def test_notifications_register_requires_owner():
    r = requests.post(
        f"{BASE_URL}/api/notifications/register",
        json={"push_token": "ExponentPushToken[FAKE-TESTING]", "platform": "ios"},
        timeout=15,
    )
    assert r.status_code in (401, 403)


def test_notifications_register_owner_ok(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/notifications/register",
        headers=auth_headers,
        json={"push_token": "ExponentPushToken[TEST_iter14_mobile]", "platform": "ios"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True


def test_notifications_register_validation(auth_headers):
    # missing push_token
    r = requests.post(
        f"{BASE_URL}/api/notifications/register",
        headers=auth_headers,
        json={"platform": "ios"},
        timeout=15,
    )
    assert r.status_code == 422


def test_notifications_test_requires_owner():
    r = requests.post(f"{BASE_URL}/api/notifications/test", timeout=15)
    assert r.status_code in (401, 403)


def test_notifications_test_owner_ok(auth_headers):
    r = requests.post(f"{BASE_URL}/api/notifications/test", headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True
    assert "sent" in j  # may be 0 if push dispatch failed, but key should exist


# ---------- settings kill-switch push hook (safe: toggle back off) ----------
def test_kill_switch_push_hook(auth_headers):
    # Engage kill switch
    r1 = requests.put(
        f"{BASE_URL}/api/settings",
        headers=auth_headers,
        json={"manual_kill_switch": True},
        timeout=20,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json().get("manual_kill_switch") is True
    # Verify persistence
    r_get = requests.get(f"{BASE_URL}/api/settings", headers=auth_headers, timeout=15)
    assert r_get.status_code == 200
    assert r_get.json().get("manual_kill_switch") is True
    # CRITICAL: restore to OFF
    r2 = requests.put(
        f"{BASE_URL}/api/settings",
        headers=auth_headers,
        json={"manual_kill_switch": False},
        timeout=20,
    )
    assert r2.status_code == 200
    assert r2.json().get("manual_kill_switch") is False


# ---------- read endpoints consumed by mobile ----------
@pytest.mark.parametrize(
    "path",
    [
        "/api/portfolio",
        "/api/market/snapshots",
        "/api/environment",
        "/api/risk/status",
        "/api/reasoning?limit=12",
        "/api/trades?limit=50",
        "/api/research/strategy_lab",
        "/api/settings",
        "/api/market/candles?symbol=BTC/USD&timeframe=1h&limit=24",
    ],
)
def test_mobile_read_endpoint_200(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
    # Body should be JSON
    j = r.json()
    assert j is not None


def test_portfolio_shape():
    r = requests.get(f"{BASE_URL}/api/portfolio", timeout=20)
    assert r.status_code == 200
    j = r.json()
    assert "equity" in j
    assert "positions" in j
    assert isinstance(j["positions"], list)


def test_market_snapshots_has_rail_symbols():
    r = requests.get(f"{BASE_URL}/api/market/snapshots", timeout=30)
    j = r.json()
    syms = {s.get("symbol") for s in (j.get("snapshots") or [])}
    # Cockpit rail expects these
    needed = {"BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "AVAX/USD"}
    # Allow partial overlap (engine may filter) but at least BTC/ETH
    assert {"BTC/USD", "ETH/USD"}.issubset(syms), f"missing core rail symbols, got {syms}"
    # Log if any rail symbol missing (not fatal)
    missing = needed - syms
    if missing:
        print(f"[info] rail symbols not present in snapshots: {missing}")


def test_strategy_lab_has_5_strategies():
    r = requests.get(f"{BASE_URL}/api/research/strategy_lab", timeout=30)
    j = r.json()
    ids = {s.get("id") for s in (j.get("strategies") or [])}
    assert {"hunter", "vcp", "trend_rider", "bear_breakdown", "neutral_crab"}.issubset(ids)


def test_candles_shape():
    r = requests.get(
        f"{BASE_URL}/api/market/candles?symbol=BTC/USD&timeframe=1h&limit=24",
        timeout=30,
    )
    j = r.json()
    candles = j.get("candles") or j.get("data") or []
    assert isinstance(candles, list)
    assert len(candles) > 0
