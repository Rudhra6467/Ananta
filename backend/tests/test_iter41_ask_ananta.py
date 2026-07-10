"""
Iteration 41 — V1 UX Freeze Phase 2: Ask Ananta endpoint + regressions.

Covers:
- POST /api/ananta/ask (owner): 403 when ask_ananta_enabled=false; 200 with
  answer+actions when true; 'Pause Hunter' produces strategy_disable action for
  key=hunter; empty question -> 400; public 401/403.
- Regression: PUT /api/settings ask_ananta_enabled toggle persists.
- Regression: PUT /api/strategy/{key}/state disable/enable.
- Regression: POST /api/orders/manual paper BUY/SELL still works.

Note: /api/ananta/ask consumes LLM credits — keep sends minimal (1-2).
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


def _set_ask_ananta(api, auth_headers, value: bool):
    r = api.put(f"{BASE_URL}/api/settings", json={"ask_ananta_enabled": value},
                headers=auth_headers, timeout=15)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["ask_ananta_enabled"] is value
    return r


# ---------- Restore known state at end of session ----------
@pytest.fixture(scope="session", autouse=True)
def restore_state(api, auth_headers):
    yield
    # leave ask_ananta_enabled = True per review request note
    try:
        api.put(f"{BASE_URL}/api/settings", json={"ask_ananta_enabled": True},
                headers=auth_headers, timeout=10)
    except Exception:
        pass


# ---------- Ask Ananta endpoint ----------
class TestAskAnantaEndpoint:
    def test_public_forbidden(self):
        # bypass conftest auth-injection
        import json as _json
        import urllib.request as _u
        req = _u.Request(f"{BASE_URL}/api/ananta/ask",
                         data=_json.dumps({"question": "hi"}).encode(),
                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _u.urlopen(req, timeout=15) as resp:
                code = resp.status
        except _u.HTTPError as e:
            code = e.code
        assert code in (401, 403), f"expected 401/403, got {code}"

    def test_disabled_returns_403(self, api, auth_headers):
        _set_ask_ananta(api, auth_headers, False)
        try:
            r = api.post(f"{BASE_URL}/api/ananta/ask",
                         json={"question": "What is happening?"},
                         headers=auth_headers, timeout=30)
            assert r.status_code == 403, r.text[:200]
            assert "disabled" in r.text.lower()
        finally:
            _set_ask_ananta(api, auth_headers, True)

    def test_empty_question_400(self, api, auth_headers):
        _set_ask_ananta(api, auth_headers, True)
        r = api.post(f"{BASE_URL}/api/ananta/ask",
                     json={"question": "   "}, headers=auth_headers, timeout=15)
        assert r.status_code == 400, r.text[:200]

    def test_pause_hunter_yields_strategy_disable_action(self, api, auth_headers):
        _set_ask_ananta(api, auth_headers, True)
        r = api.post(f"{BASE_URL}/api/ananta/ask",
                     json={"question": "Pause Hunter please", "tab": "cockpit"},
                     headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"body={r.text[:400]}"
        j = r.json()
        assert "answer" in j and isinstance(j["answer"], str) and len(j["answer"]) > 0
        assert "actions" in j and isinstance(j["actions"], list)
        # find strategy_disable for hunter
        matches = [a for a in j["actions"]
                   if a.get("type") == "strategy_disable"
                   and (a.get("params") or {}).get("key") == "hunter"]
        assert matches, f"expected strategy_disable action for hunter; got {j['actions']}"


# ---------- Regressions ----------
class TestSettingsToggleRegression:
    def test_ask_ananta_toggle_persists(self, api, auth_headers):
        _set_ask_ananta(api, auth_headers, False)
        g1 = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g1["ask_ananta_enabled"] is False
        _set_ask_ananta(api, auth_headers, True)
        g2 = api.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g2["ask_ananta_enabled"] is True


class TestStrategyStateRegression:
    def _pick_key(self, api):
        r = api.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
        if r.status_code != 200:
            pytest.skip(f"registry unavailable: {r.status_code}")
        items = r.json().get("items") or r.json().get("strategies") or []
        for it in items:
            k = it.get("key") or it.get("id")
            if k and k != "hunter":
                return k
        return items[0].get("key") if items else None

    def test_disable_then_enable(self, api, auth_headers):
        key = self._pick_key(api)
        if not key:
            pytest.skip("no non-hunter strategy")
        r = api.put(f"{BASE_URL}/api/strategy/{key}/state",
                    json={"enabled": False}, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
        r2 = api.put(f"{BASE_URL}/api/strategy/{key}/state",
                     json={"enabled": True}, headers=auth_headers, timeout=15)
        assert r2.status_code == 200


class TestManualOrderRegression:
    def test_paper_mode_and_buy_sell(self, api, auth_headers):
        # ensure paper
        r = api.put(f"{BASE_URL}/api/settings", json={"trading_mode": "PAPER"},
                    headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # buy $20 BTC
        b = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "BUY", "order_type": "MARKET",
                           "notional_usd": 20.0}, headers=auth_headers, timeout=30)
        assert b.status_code == 200, b.text[:200]
        assert b.json()["trade"]["side"] == "BUY"
        # sell 50% BTC (position exists from BUY)
        s = api.post(f"{BASE_URL}/api/orders/manual",
                     json={"symbol": "BTC", "side": "SELL", "order_type": "MARKET",
                           "fraction": 0.5}, headers=auth_headers, timeout=30)
        assert s.status_code == 200, s.text[:200]
        assert s.json()["trade"]["side"] == "SELL"
