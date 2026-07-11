"""HTTP-level verification for iter46 waitlist + system health selfcheck.

Covers the review contract:
  - POST /api/access/request (public, idempotent, 400 on bad input)
  - GET  /api/access/requests (owner-only, 403 without token)
  - POST /api/access/requests/{id}/approve|reject (owner)
  - GET  /api/health/selfcheck (fast <1.5s, expected keys)
Cleans up any TEST_ leads it creates.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

# --- auth fixtures ----------------------------------------------------------
@pytest.fixture(scope="module")
def owner_token():
    email = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
    pw = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text}")
    return r.json()["token"]


# --- health selfcheck -------------------------------------------------------
def test_health_selfcheck_shape_and_speed():
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/health/selfcheck", timeout=5)
    dt = time.time() - t0
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("backend", "database", "market_data", "engine", "ok"):
        assert k in data, f"missing key {k}: {data}"
    assert isinstance(data["ok"], bool)
    assert dt < 1.5, f"selfcheck took {dt:.2f}s (target <1.5s)"


# --- access waitlist public capture ----------------------------------------
class TestAccessRequestPublic:
    def _email(self):
        return f"TEST_iter46_{uuid.uuid4().hex[:10]}@example.com"

    def test_create_lead_public_ok(self, owner_token):
        email = self._email()
        r = requests.post(
            f"{BASE_URL}/api/access/request",
            json={"name": "Lead A", "email": email, "feature": "Ask Ananta", "platform": "web"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("status") == "pending"
        assert body.get("already_on_list") is False
        # verify listable by owner
        rl = requests.get(f"{BASE_URL}/api/access/requests", headers={"Authorization": f"Bearer {owner_token}"}, timeout=10)
        assert rl.status_code == 200, rl.text
        items = rl.json().get("requests", rl.json() if isinstance(rl.json(), list) else [])
        assert any(x.get("email", "").lower() == email.lower() for x in items)
        # cleanup: find + reject (soft delete) — best effort
        self._cleanup(owner_token, email)

    def test_idempotent_resubmit(self, owner_token):
        email = self._email()
        r1 = requests.post(f"{BASE_URL}/api/access/request", json={"name": "Dup", "email": email}, timeout=10)
        assert r1.status_code == 200
        assert r1.json().get("already_on_list") is False
        r2 = requests.post(f"{BASE_URL}/api/access/request", json={"name": "Dup2", "email": email}, timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("already_on_list") is True
        self._cleanup(owner_token, email)

    def test_bad_email_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/access/request", json={"name": "X", "email": "notanemail"}, timeout=10)
        assert r.status_code == 400, r.text

    def test_empty_name_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/access/request", json={"name": "   ", "email": "TEST_empty@example.com"}, timeout=10)
        assert r.status_code == 400, r.text

    def _cleanup(self, token, email):
        # list, find, reject to keep DB tidy
        try:
            rl = requests.get(f"{BASE_URL}/api/access/requests", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
            items = rl.get("requests", rl if isinstance(rl, list) else [])
            for it in items:
                if it.get("email", "").lower() == email.lower():
                    rid = it.get("id")
                    if rid:
                        requests.post(f"{BASE_URL}/api/access/requests/{rid}/reject", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        except Exception:
            pass


# --- owner-only endpoints ---------------------------------------------------
class TestAccessListOwnerOnly:
    def test_list_requires_owner_403(self):
        r = requests.get(f"{BASE_URL}/api/access/requests", timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_list_owner_ok(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/access/requests", headers={"Authorization": f"Bearer {owner_token}"}, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        # accept either {requests: [...]} or list
        assert isinstance(body, (dict, list))

    def test_approve_flow(self, owner_token):
        email = f"TEST_iter46_appr_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/access/request", json={"name": "Approve Me", "email": email}, timeout=10)
        assert r.status_code == 200
        rl = requests.get(f"{BASE_URL}/api/access/requests", headers={"Authorization": f"Bearer {owner_token}"}, timeout=10).json()
        items = rl.get("requests", rl if isinstance(rl, list) else [])
        target = next((x for x in items if x.get("email", "").lower() == email.lower()), None)
        assert target, "created lead not visible to owner"
        rid = target["id"]
        ra = requests.post(f"{BASE_URL}/api/access/requests/{rid}/approve", headers={"Authorization": f"Bearer {owner_token}"}, timeout=10)
        assert ra.status_code == 200, ra.text
        assert ra.json().get("status") == "approved"

    def test_unknown_id_404(self, owner_token):
        rr = requests.post(f"{BASE_URL}/api/access/requests/nonexistent-id-xyz/reject", headers={"Authorization": f"Bearer {owner_token}"}, timeout=10)
        assert rr.status_code == 404
