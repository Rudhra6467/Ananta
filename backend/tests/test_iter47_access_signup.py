"""iter47: verify POST /api/access/request supports Sign Up funnel payloads.

Frontend SignUp.jsx submits: { name, email, feature:'Sign Up', platform:'web' }.
The backend must accept it, return 200 with {ok, status, already_on_list}, be
idempotent per email, and validate name/email.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://hunter-squeeze-labs.preview.emergentagent.com",
).rstrip("/")

API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def owner_token(client):
    r = client.post(
        f"{API}/auth/login",
        json={"email": "owner@ananta.ai", "password": "aZKtwzAqI0SzlwFE6TRqw8aH"},
    )
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token")


def _unique_email(tag: str) -> str:
    return f"TEST_iter47_{tag}_{uuid.uuid4().hex[:8]}@example.com"


class TestSignupAccessRequest:
    def test_signup_payload_success(self, client):
        email = _unique_email("ok")
        r = client.post(
            f"{API}/access/request",
            json={
                "name": "TEST_iter47 Signup",
                "email": email,
                "feature": "Sign Up",
                "platform": "web",
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("status") in ("pending", "approved")
        assert data.get("already_on_list") is False

    def test_signup_idempotent_second_submit(self, client):
        email = _unique_email("dup")
        payload = {
            "name": "TEST_iter47 Dup",
            "email": email,
            "feature": "Sign Up",
            "platform": "web",
        }
        r1 = client.post(f"{API}/access/request", json=payload, timeout=10)
        assert r1.status_code == 200
        assert r1.json().get("already_on_list") is False
        # Second submit → already_on_list=true
        r2 = client.post(f"{API}/access/request", json=payload, timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("already_on_list") is True

    def test_signup_rejects_bad_email(self, client):
        r = client.post(
            f"{API}/access/request",
            json={"name": "TEST_iter47", "email": "not-an-email", "feature": "Sign Up"},
            timeout=10,
        )
        assert r.status_code in (400, 422), r.text

    def test_signup_rejects_empty_name(self, client):
        r = client.post(
            f"{API}/access/request",
            json={"name": "   ", "email": _unique_email("emptyname"), "feature": "Sign Up"},
            timeout=10,
        )
        assert r.status_code in (400, 422), r.text

    def test_signup_response_time_reasonable(self, client):
        """Verify endpoint responds well under 3s (SignUp submit should not hang)."""
        t0 = time.time()
        r = client.post(
            f"{API}/access/request",
            json={
                "name": "TEST_iter47 Perf",
                "email": _unique_email("perf"),
                "feature": "Sign Up",
                "platform": "web",
            },
            timeout=10,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200
        assert elapsed < 3.0, f"POST /api/access/request took {elapsed:.2f}s (too slow)"


class TestCleanupSignupLeads:
    """Reject all TEST_iter47_* leads created above."""

    def test_reject_all_iter47_leads(self, client, owner_token):
        h = {"Authorization": f"Bearer {owner_token}"}
        r = client.get(f"{API}/access/requests?status=pending", headers=h, timeout=10)
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        rejected = 0
        for row in rows:
            email = (row.get("email") or "").lower()
            if "test_iter47_" in email and email.endswith("@example.com"):
                rid = row.get("id") or row.get("_id")
                if rid:
                    rr = client.post(
                        f"{API}/access/requests/{rid}/reject", headers=h, timeout=10
                    )
                    if rr.status_code == 200:
                        rejected += 1
        print(f"[iter47 cleanup] rejected {rejected} TEST_iter47 leads")
