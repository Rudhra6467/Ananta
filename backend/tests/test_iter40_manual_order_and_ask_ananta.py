"""
Iteration 40 — V1 UX Freeze: manual orders + ask_ananta toggle + strategy state toggle.

Covers:
- POST /api/orders/manual (BUY notional MARKET; SELL fraction MARKET; LIMIT-below-market rests;
  validation errors; owner-auth 403 for public)
- PUT /api/settings ask_ananta_enabled true/false persistence
- PUT /api/strategy/{key}/state enable/disable still works
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---- ensure PAPER mode ----
@pytest.fixture(scope="session", autouse=True)
def ensure_paper(api, auth_headers):
    r = api.put(f"{BASE_URL}/api/settings", json={"trading_mode": "PAPER"}, headers=auth_headers, timeout=15)
    assert r.status_code == 200
    assert r.json()["trading_mode"] == "PAPER"


# ---------- ORDERS ----------
class TestManualOrders:
    def test_owner_required_public_403(self):
        # Use urllib directly to bypass the global conftest auth-injection monkeypatch.
        import json as _json
        import urllib.request as _u
        req = _u.Request(f"{BASE_URL}/api/orders/manual",
                         data=_json.dumps({"symbol": "BTC", "side": "BUY", "notional_usd": 25}).encode(),
                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _u.urlopen(req, timeout=15) as resp:
                code = resp.status
        except _u.HTTPError as e:
            code = e.code
        assert code in (401, 403), f"expected 401/403 for public mutation, got {code}"

    def test_buy_paper_market_notional(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "BUY", "order_type": "MARKET",
                           "notional_usd": 25.0}, headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"body={r.text[:300]}"
        j = r.json()
        assert j["ok"] is True
        assert j["resting"] is False
        assert j["trade"]["side"] == "BUY"
        assert j["trade"]["mode"] == "PAPER"
        assert j["trade"]["symbol"] == "BTC/USD"
        assert j["trade"]["quantity"] > 0

    def test_limit_buy_below_market_rests(self, api, auth_headers):
        # get a low limit price
        snap = api.get(f"{BASE_URL}/api/market/snapshot/BTC", timeout=15).json()
        low_limit = round(snap["ask"] * 0.5, 2)  # deep below market
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "BUY", "order_type": "LIMIT",
                           "notional_usd": 25.0, "limit_price": low_limit},
                     headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["resting"] is True
        assert j["order"]["side"] == "BUY"
        assert j["order"]["limit_price"] == low_limit
        # verify it's persisted in pending_orders
        pend = api.get(f"{BASE_URL}/api/pending_orders", timeout=15).json()
        assert any(o.get("limit_price") == low_limit for o in pend["items"])

    def test_sell_paper_market_fraction(self, api, auth_headers):
        # Make sure a position exists first
        api.post(f"{BASE_URL}/api/orders/manual",
                 json={"symbol": "ETH", "side": "BUY", "notional_usd": 30.0},
                 headers=auth_headers, timeout=30)
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "ETH", "side": "SELL", "order_type": "MARKET", "fraction": 0.5},
                     headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["ok"] is True
        assert j["trade"]["side"] == "SELL"

    def test_sell_no_position_404(self, api, auth_headers):
        # Pick an enabled symbol we don't have. First close PAXG if any (unlikely traded).
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "PAXG", "side": "SELL", "fraction": 1.0},
                     headers=auth_headers, timeout=30)
        # If it happens to have position, close it and retry
        if r.status_code == 200:
            r2 = api.post(f"{BASE_URL}/api/orders/manual",
                          json={"symbol": "PAXG", "side": "SELL", "fraction": 1.0},
                          headers=auth_headers, timeout=30)
            assert r2.status_code == 404
        else:
            assert r.status_code == 404, r.text[:300]

    def test_bad_side_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "HOLD", "notional_usd": 20},
                     headers=auth_headers, timeout=15)
        assert r.status_code == 400

    def test_buy_missing_amount_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "BUY", "order_type": "MARKET"},
                     headers=auth_headers, timeout=15)
        assert r.status_code == 400

    def test_symbol_not_enabled_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "SHIB", "side": "BUY", "notional_usd": 20},
                     headers=auth_headers, timeout=15)
        assert r.status_code == 400


# ---------- ASK ANANTA TOGGLE ----------
class TestAskAnantaToggle:
    def test_toggle_true_persists(self, api, auth_headers):
        r = api.put(f"{BASE_URL}/api/settings", json={"ask_ananta_enabled": True},
                    headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["ask_ananta_enabled"] is True
        # GET
        g = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g["ask_ananta_enabled"] is True

    def test_toggle_false_persists(self, api, auth_headers):
        r = api.put(f"{BASE_URL}/api/settings", json={"ask_ananta_enabled": False},
                    headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["ask_ananta_enabled"] is False
        g = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g["ask_ananta_enabled"] is False


# ---------- STRATEGY STATE TOGGLE ----------
class TestStrategyStateToggle:
    def _pick_key(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
        if r.status_code != 200:
            pytest.skip(f"/api/strategy/registry not available: {r.status_code}")
        items = r.json().get("items") or r.json().get("strategies") or []
        if not items:
            pytest.skip("no strategies registered")
        # prefer a non-hunter key so we don't disable production alpha
        for it in items:
            k = it.get("key") or it.get("id")
            if k and k != "hunter":
                return k
        return items[0].get("key") or items[0].get("id")

    def test_disable_then_enable(self, api, auth_headers):
        key = self._pick_key(api)
        # disable
        r = api.put(f"{BASE_URL}/api/strategy/{key}/state",
                    json={"enabled": False}, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        # accept either explicit status:DISABLED or enabled:false
        assert j.get("status") == "DISABLED" or j.get("enabled") is False, j
        # enable
        r2 = api.put(f"{BASE_URL}/api/strategy/{key}/state",
                     json={"enabled": True}, headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("status") in ("ENABLED", "ACTIVE") or j2.get("enabled") is True, j2
