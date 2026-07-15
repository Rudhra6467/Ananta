"""Iter 56 — Demo login + onboarding paper-setup backend tests."""
import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")

DEMO_EMAIL = "review@ananta.ai"
DEMO_PASS = "AnantaDemo123!"
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASS = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS}, timeout=15)
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# ---------- AUTH ----------
class TestAuth:
    def test_demo_login_success(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and len(data["token"]) > 20
        # The login endpoint should reflect the actual logged-in identity
        assert data.get("role") == "demo", f"expected role=demo but got {data.get('role')} (server hardcodes owner)"
        assert data.get("email") == DEMO_EMAIL, f"expected demo email but got {data.get('email')}"

    def test_demo_me_returns_demo_role(self, demo_token):
        # /auth/me decodes the JWT — this is the source of truth
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {demo_token}"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("role") == "demo"
        assert data.get("email") == DEMO_EMAIL

    def test_owner_login_still_works(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {owner_token}"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("role") == "owner"

    def test_wrong_password_fails(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": "WrongPass!"}, timeout=15)
        assert r.status_code == 401


# ---------- ONBOARDING ----------
class TestOnboardingPaperSetup:
    def test_unauth_call_forbidden(self):
        r = requests.post(f"{BASE_URL}/api/onboarding/paper-setup",
                          json={"capital": 25000, "allocation_type": "fixed", "allocation_value": 1000, "strategies": ["hunter"]},
                          timeout=15)
        assert r.status_code == 403

    def test_paper_setup_fixed(self, demo_token):
        payload = {"capital": 25000, "allocation_type": "fixed", "allocation_value": 1000, "strategies": ["hunter"]}
        r = requests.post(f"{BASE_URL}/api/onboarding/paper-setup",
                          json=payload,
                          headers={"Authorization": f"Bearer {demo_token}"},
                          timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True
        # portfolio reset to 25000
        p = data.get("portfolio", {})
        assert p.get("starting_balance") == 25000.0
        assert p.get("cash") == 25000.0
        # strategy enabled
        assert "hunter" in data.get("strategies_enabled", [])

        # Verify portfolio persisted via GET
        pr = requests.get(f"{BASE_URL}/api/portfolio", timeout=15)
        assert pr.status_code == 200
        assert pr.json().get("starting_balance") == 25000.0

        # Verify sizing settings: fixed → adaptive_sizing_enabled=True, normal_lot_usd=1000
        sr = requests.get(f"{BASE_URL}/api/settings",
                          headers={"Authorization": f"Bearer {demo_token}"}, timeout=15)
        assert sr.status_code == 200
        s = sr.json()
        assert s.get("adaptive_sizing_enabled") is True
        assert s.get("normal_lot_usd") == 1000.0
        assert s.get("strong_lot_usd") == 1000.0
        assert s.get("trading_mode") == "PAPER"

    def test_paper_setup_percent(self, demo_token):
        payload = {"capital": 30000, "allocation_type": "percent", "allocation_value": 5, "strategies": ["hunter"]}
        r = requests.post(f"{BASE_URL}/api/onboarding/paper-setup",
                          json=payload,
                          headers={"Authorization": f"Bearer {demo_token}"},
                          timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        assert data["portfolio"]["starting_balance"] == 30000.0

        sr = requests.get(f"{BASE_URL}/api/settings",
                          headers={"Authorization": f"Bearer {demo_token}"}, timeout=15)
        s = sr.json()
        # percent path → adaptive_sizing_enabled=False, min==max==5
        assert s.get("adaptive_sizing_enabled") is False
        assert s.get("position_size_pct_min") == 5.0
        assert s.get("position_size_pct_max") == 5.0
