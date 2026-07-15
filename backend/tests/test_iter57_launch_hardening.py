"""Iter 57 Launch Hardening — Demo history seed, waitlist Resend, onboarding role-awareness."""
import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / "frontend" / ".env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

DEMO_EMAIL = "review@ananta.ai"
DEMO_PASS = "AnantaDemo123!"
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASS = "aZKtwzAqI0SzlwFE6TRqw8aH"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PASS)


# ---------- DEMO paper-setup pre-seeds history ----------
class TestDemoPaperSetupSeedsHistory:
    def test_demo_setup_seeds_realistic_history(self, demo_token):
        payload = {"capital": 25000, "allocation_type": "fixed", "allocation_value": 1000, "strategies": ["hunter"]}
        r = requests.post(
            f"{BASE_URL}/api/onboarding/paper-setup",
            json=payload,
            headers={"Authorization": f"Bearer {demo_token}"},
            timeout=45,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert body["portfolio"]["starting_balance"] == 25000.0
        assert "hunter" in body.get("strategies_enabled", [])

        # Verify portfolio has non-zero realized_pnl + open positions
        pr = requests.get(f"{BASE_URL}/api/portfolio", timeout=15)
        assert pr.status_code == 200
        pf = pr.json()
        # Non-zero P&L
        assert abs(pf.get("realized_pnl", 0.0)) > 0, f"expected non-zero realized_pnl, got {pf.get('realized_pnl')}"
        # Equity should differ from starting balance
        assert pf.get("equity", 25000.0) != 25000.0, f"expected equity != starting_balance, got {pf.get('equity')}"
        # 2 open positions per demo_seed.seed_demo_history
        positions = pf.get("positions", [])
        open_positions = [p for p in positions if p.get("quantity", 0) > 0]
        assert len(open_positions) >= 2, f"expected ≥2 open positions, got {len(open_positions)}"

        # Verify trades: ~21 (9+7+5) closed demo trades with note=DEMO
        tr = requests.get(f"{BASE_URL}/api/trades?limit=100", timeout=15)
        assert tr.status_code == 200
        trades_body = tr.json()
        trades = trades_body if isinstance(trades_body, list) else trades_body.get("items", trades_body.get("trades", []))
        demo_trades = [t for t in trades if t.get("note") == "DEMO"]
        assert 18 <= len(demo_trades) <= 25, f"expected ~21 demo trades, got {len(demo_trades)}"


# ---------- OWNER paper-setup does NOT inject demo history ----------
class TestOwnerPaperSetupNoSeed:
    def test_owner_setup_is_fresh_book(self, owner_token):
        payload = {"capital": 15000, "allocation_type": "fixed", "allocation_value": 500, "strategies": ["hunter"]}
        r = requests.post(
            f"{BASE_URL}/api/onboarding/paper-setup",
            json=payload,
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        body = r.json()
        assert body["portfolio"]["starting_balance"] == 15000.0

        # Trades should be wiped and NOT re-seeded
        tr = requests.get(f"{BASE_URL}/api/trades?limit=100", timeout=15)
        assert tr.status_code == 200
        trades_body = tr.json()
        trades = trades_body if isinstance(trades_body, list) else trades_body.get("items", trades_body.get("trades", []))
        assert len(trades) == 0, f"owner paper-setup should not seed trades; got {len(trades)}"

        # Portfolio realized_pnl should be 0
        pr = requests.get(f"{BASE_URL}/api/portfolio", timeout=15)
        pf = pr.json()
        assert pf.get("realized_pnl", 0.0) == 0.0
        open_positions = [p for p in pf.get("positions", []) if p.get("quantity", 0) > 0]
        assert len(open_positions) == 0


# ---------- Access request (public) still returns ok (email fire-and-forget) ----------
class TestAccessRequestEmail:
    def test_public_access_request_ok(self):
        r = requests.post(
            f"{BASE_URL}/api/access/request",
            json={"name": "TEST_Regression Bot", "email": "test_regression_iter57@example.com",
                  "feature": "Live Trading", "platform": "web"},
            timeout=15,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("status") in ("pending", "approved", "rejected")


# ---------- Approve/Reject endpoints don't 500 even when user email fails ----------
class TestAccessDecisionEndpoint:
    def _seed_lead(self, email: str) -> str:
        r = requests.post(
            f"{BASE_URL}/api/access/request",
            json={"name": "TEST_Approval Target", "email": email, "feature": "Demo", "platform": "web"},
            timeout=15,
        )
        assert r.status_code == 200
        # fetch id
        return email

    def _find_id(self, owner_token: str, email: str) -> str:
        lr = requests.get(
            f"{BASE_URL}/api/access/requests",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=15,
        )
        assert lr.status_code == 200
        for req in lr.json().get("requests", []):
            if req.get("email") == email:
                return req["id"]
        pytest.fail(f"could not find seeded lead {email}")

    def test_approve_returns_ok_even_when_email_fails(self, owner_token):
        email = "test_iter57_approve@example.com"
        self._seed_lead(email)
        rid = self._find_id(owner_token, email)
        r = requests.post(
            f"{BASE_URL}/api/access/requests/{rid}/approve",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=15,
        )
        assert r.status_code == 200, f"approve endpoint returned {r.status_code}: {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert body.get("status") == "approved"

    def test_reject_returns_ok_even_when_email_fails(self, owner_token):
        email = "test_iter57_reject@example.com"
        self._seed_lead(email)
        rid = self._find_id(owner_token, email)
        r = requests.post(
            f"{BASE_URL}/api/access/requests/{rid}/reject",
            headers={"Authorization": f"Bearer {owner_token}"},
            timeout=15,
        )
        assert r.status_code == 200, f"reject endpoint returned {r.status_code}: {r.text}"
        assert r.json().get("status") == "rejected"
