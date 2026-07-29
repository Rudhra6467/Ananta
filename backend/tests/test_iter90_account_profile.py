"""iter90 — Account screen redesign backend verification.

Tests:
  * POST /api/auth/login (owner)  -> token
  * GET  /api/auth/profile         -> {email, display_name, avatar, role}
  * PATCH /api/auth/profile        -> display_name persists
  * POST /api/auth/change-password -> wrong current => 400 ; happy path OK (then revert)
  * POST /api/auth/change-email    -> invalid email => 400 ; wrong password => 400
                                       (NEGATIVE cases only; do NOT actually mutate the owner email)
Owner creds MUST be left equal to /app/memory/test_credentials.md at the end.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to /app/frontend/.env
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---- Login ----
class TestLogin:
    def test_login_owner(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("role") == "owner"
        assert (d.get("token") or d.get("access_token"))


# ---- Profile GET/PATCH ----
class TestProfile:
    def test_get_profile(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/profile", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "email" in d and d["email"] == OWNER_EMAIL
        assert "display_name" in d
        assert "avatar" in d
        assert d.get("role") == "owner"

    def test_patch_display_name_persists(self, auth_headers):
        # capture original
        r0 = requests.get(f"{BASE_URL}/api/auth/profile", headers=auth_headers, timeout=10)
        original = r0.json().get("display_name")

        new_name = "TEST_iter90_Owner"
        r = requests.patch(f"{BASE_URL}/api/auth/profile",
                           json={"display_name": new_name}, headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("display_name") == new_name

        # GET verifies persistence
        r2 = requests.get(f"{BASE_URL}/api/auth/profile", headers=auth_headers, timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("display_name") == new_name

        # revert
        rev = requests.patch(f"{BASE_URL}/api/auth/profile",
                             json={"display_name": original or ""}, headers=auth_headers, timeout=10)
        assert rev.status_code == 200


# ---- Change password ----
class TestChangePassword:
    def test_wrong_current_returns_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          json={"current_password": "definitelywrong-xyz",
                                "new_password": "someNewPass1234"},
                          headers=auth_headers, timeout=10)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"

    def test_happy_path_then_revert(self, auth_headers):
        new_pw = "TEST_iter90_TempPw_9182734"
        # change to new
        r = requests.post(f"{BASE_URL}/api/auth/change-password",
                          json={"current_password": OWNER_PASSWORD, "new_password": new_pw},
                          headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"change-password happy failed: {r.status_code} {r.text}"

        # verify new password logs in
        login_new = requests.post(f"{BASE_URL}/api/auth/login",
                                  json={"email": OWNER_EMAIL, "password": new_pw}, timeout=15)
        assert login_new.status_code == 200
        new_tok = login_new.json().get("token") or login_new.json().get("access_token")
        assert new_tok

        # revert to ORIGINAL using new token
        rev = requests.post(f"{BASE_URL}/api/auth/change-password",
                            json={"current_password": new_pw, "new_password": OWNER_PASSWORD},
                            headers={"Authorization": f"Bearer {new_tok}",
                                     "Content-Type": "application/json"},
                            timeout=10)
        assert rev.status_code == 200, f"REVERT failed! creds may be broken: {rev.status_code} {rev.text}"

        # confirm original creds work
        final = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
        assert final.status_code == 200, "ORIGINAL owner creds do not work after revert!"


# ---- Change email (NEGATIVE only) ----
class TestChangeEmailNegative:
    def test_invalid_email_returns_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/auth/change-email",
                          json={"current_password": OWNER_PASSWORD,
                                "new_email": "not-an-email"},
                          headers=auth_headers, timeout=10)
        assert r.status_code == 400, f"invalid email should 400, got {r.status_code}: {r.text}"

    def test_wrong_password_returns_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/auth/change-email",
                          json={"current_password": "definitely-wrong-pw",
                                "new_email": "still-valid@example.com"},
                          headers=auth_headers, timeout=10)
        assert r.status_code == 400


# ---- Final safety net: owner login MUST still work ----
class TestOwnerCredsIntact:
    def test_final_login_still_works(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
        assert r.status_code == 200, "Owner creds are NOT the documented ones — revert immediately."
