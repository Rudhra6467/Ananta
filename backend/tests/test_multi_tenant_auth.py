"""Multi-tenant Google sign-in + owner regression tests.

Covers the review-request checklist:
  * Owner login/portfolio (house book) unchanged
  * Google user isolation via seeded session_token (Bearer)
  * Per-tenant mutation isolation (manual order, onboarding paper-setup, settings)
  * Invalid session_id -> 401
  * Anonymous 403 on mutations
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"
QA_SESSION = "test_session_qa01"
QA_USER_ID = "user_qatest01"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "owner"
    return data["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Owner path (unchanged) ----------
class TestOwnerUnchanged:
    def test_owner_me(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me.get("role") == "owner"

    def test_owner_portfolio_house_book(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(owner_token), timeout=15)
        assert r.status_code == 200
        p = r.json()
        # House book starting balance is 25000 per problem statement
        assert p["starting_balance"] == 25000, f"expected 25000, got {p['starting_balance']}"

    def test_anonymous_portfolio_is_house_book(self):
        r = requests.get(f"{BASE_URL}/api/portfolio", timeout=15)
        assert r.status_code == 200
        p = r.json()
        assert p["starting_balance"] == 25000


# ---------- Google user isolation ----------
class TestGoogleUserIsolation:
    def test_google_me_role_user(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(QA_SESSION), timeout=15)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me.get("role") == "user", me
        # tenant_id must equal user_id
        assert me.get("tenant_id") == QA_USER_ID, me
        assert me.get("user_id") == QA_USER_ID, me

    def test_google_portfolio_isolated_book(self):
        # First hit provisions the isolated book (starting_balance 1200 per default Portfolio())
        r = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(QA_SESSION), timeout=15)
        assert r.status_code == 200
        p = r.json()
        assert p["starting_balance"] == 1200, f"expected 1200, got {p['starting_balance']}"

    def test_google_trades_are_scoped(self):
        r = requests.get(f"{BASE_URL}/api/trades", headers=_hdr(QA_SESSION), timeout=15)
        assert r.status_code == 200
        body = r.json()
        # /api/trades returns {count, items} shape
        trades = body["items"] if isinstance(body, dict) else body
        assert isinstance(trades, list)
        for t in trades:
            tid = t.get("tenant_id")
            assert tid == QA_USER_ID, f"foreign tenant trade leaked: {t}"


# ---------- Invalid session_id ----------
class TestInvalidGoogleSession:
    def test_invalid_session_id_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/google/session",
            json={"session_id": "definitely-not-a-real-emergent-session-id-xyz"},
            timeout=20,
        )
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ---------- Anonymous mutations still 403 ----------
class TestAnonymousMutations:
    def test_anon_put_settings_403(self):
        r = requests.put(f"{BASE_URL}/api/settings", json={"min_confidence": 0.8}, timeout=15)
        assert r.status_code == 403, r.status_code

    def test_anon_manual_order_403(self):
        r = requests.post(
            f"{BASE_URL}/api/orders/manual",
            json={"symbol": "SOL", "side": "BUY", "order_type": "MARKET", "notional_usd": 10},
            timeout=15,
        )
        assert r.status_code == 403, r.status_code


# ---------- Per-tenant mutation isolation ----------
class TestMutationIsolation:
    def test_google_manual_order_lands_only_in_own_book(self, owner_token):
        # Snapshot owner cash before
        r_owner_before = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(owner_token), timeout=15)
        assert r_owner_before.status_code == 200
        owner_cash_before = r_owner_before.json()["cash"]

        r_user_before = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(QA_SESSION), timeout=15)
        assert r_user_before.status_code == 200

        # Google user places a manual BUY
        r = requests.post(
            f"{BASE_URL}/api/orders/manual",
            headers=_hdr(QA_SESSION),
            json={"symbol": "SOL", "side": "BUY", "order_type": "MARKET", "notional_usd": 100},
            timeout=30,
        )
        assert r.status_code in (200, 201), f"manual order failed: {r.status_code} {r.text}"

        # Owner portfolio must be UNAFFECTED
        r_owner_after = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(owner_token), timeout=15)
        owner_cash_after = r_owner_after.json()["cash"]
        assert abs(owner_cash_after - owner_cash_before) < 1.0, (
            f"owner cash changed after Google user's trade: before={owner_cash_before} after={owner_cash_after}"
        )

        # Latest trade for the Google user should be tenant-tagged to QA_USER_ID
        rt = requests.get(f"{BASE_URL}/api/trades", headers=_hdr(QA_SESSION), timeout=15)
        assert rt.status_code == 200
        body = rt.json()
        trades = body["items"] if isinstance(body, dict) else body
        assert trades, "expected at least one trade for the Google user"
        sol_trades = [t for t in trades if "SOL" in (t.get("symbol") or "")]
        assert sol_trades, "expected a SOL trade in the Google user's book"
        for t in sol_trades:
            assert t.get("tenant_id") == QA_USER_ID, f"SOL trade tenant mismatch: {t}"

    def test_google_onboarding_paper_setup_resets_only_own_book(self, owner_token):
        owner_before = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(owner_token), timeout=15).json()
        payload = {
            "capital": 5000,
            "allocation_type": "fixed",
            "allocation_value": 100,
            "strategies": ["ema-cross"],
        }
        r = requests.post(
            f"{BASE_URL}/api/onboarding/paper-setup",
            headers=_hdr(QA_SESSION),
            json=payload,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        # Google user's book should reflect the new capital
        p_user = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(QA_SESSION), timeout=15).json()
        assert p_user["starting_balance"] == 5000, p_user

        owner_after = requests.get(f"{BASE_URL}/api/portfolio", headers=_hdr(owner_token), timeout=15).json()
        assert owner_after["starting_balance"] == owner_before["starting_balance"] == 25000
        assert abs(owner_after["cash"] - owner_before["cash"]) < 1.0

    def test_google_put_settings_scoped(self):
        r = requests.get(f"{BASE_URL}/api/settings", headers=_hdr(QA_SESSION), timeout=15)
        assert r.status_code == 200
        r2 = requests.put(
            f"{BASE_URL}/api/settings",
            headers=_hdr(QA_SESSION),
            json={"min_confidence": 0.77},
            timeout=15,
        )
        assert r2.status_code in (200, 204), r2.text
        r3 = requests.get(f"{BASE_URL}/api/settings", headers=_hdr(QA_SESSION), timeout=15)
        assert r3.status_code == 200
        assert abs(r3.json().get("min_confidence", 0) - 0.77) < 1e-6
