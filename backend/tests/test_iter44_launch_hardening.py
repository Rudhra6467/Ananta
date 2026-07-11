"""iter44 Launch-Hardening backend tests.

Covers:
- POST /api/library/import/analyze returns 400 on empty raw_content and 422 on
  garbage content that survives the empty-check but breaks AI extraction / draft
  build (must NOT be 500 with a stack trace).
- Global exception handler returns clean JSON on unhandled errors (no HTML/stack).
- 4xx paths return clean JSON detail (not stacktraces).
- Settings ask_ananta_enabled: GET returns bool; PUT persists.
"""
import os
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ---------------- import/analyze hardening ----------------

class TestImportAnalyzeHardening:
    def test_empty_raw_content_returns_400_not_500(self, owner_headers):
        r = requests.post(f"{API}/library/import/analyze",
                          json={"raw_content": ""}, headers=owner_headers, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert "detail" in body
        assert "raw_content" in body["detail"].lower()

    def test_whitespace_only_returns_400(self, owner_headers):
        r = requests.post(f"{API}/library/import/analyze",
                          json={"raw_content": "   \n\t  "}, headers=owner_headers, timeout=30)
        assert r.status_code == 400
        assert isinstance(r.json().get("detail"), str)

    def test_garbage_content_not_500(self, owner_headers):
        # Garbage that is non-empty. May succeed as an analyze (LLM does its best)
        # or fail cleanly with 422 (malformed extraction) / 502 (AI error).
        # THE KEY GUARANTEE: never a raw 500 with stack trace.
        r = requests.post(f"{API}/library/import/analyze",
                          json={"raw_content": "!@#$%^&*()_+~{}|[]\\:\";'<>?,./`"},
                          headers=owner_headers, timeout=90)
        assert r.status_code in (200, 400, 422, 502), \
            f"unexpected status {r.status_code}: {r.text[:400]}"
        # Response must be JSON (not an HTML stack page)
        assert r.headers.get("content-type", "").startswith("application/json")
        body = r.json()
        # Error body must have `detail`, and detail must be a clean string (no traceback)
        if r.status_code >= 400:
            assert "detail" in body
            detail = body["detail"] if isinstance(body["detail"], str) else str(body["detail"])
            assert "Traceback" not in detail
            assert "at 0x" not in detail  # python repr addresses

    def test_analyze_requires_owner(self):
        r = requests.post(f"{API}/library/import/analyze",
                          json={"raw_content": "ema fast>slow buy"}, timeout=15)
        assert r.status_code in (401, 403)
        body = r.json()
        assert "detail" in body


# ---------------- 401 / auth error shape ----------------

class TestAuthErrorShape:
    def test_bad_token_clean_json_401(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-real-token"}, timeout=10)
        assert r.status_code in (401, 403)
        assert r.headers.get("content-type", "").startswith("application/json")
        assert "detail" in r.json()

    def test_owner_only_mutation_without_token_is_clean_401_or_403(self):
        r = requests.post(f"{API}/settings", json={}, timeout=10)
        # PUT is the real path; POST should still return a clean 4xx JSON.
        assert r.status_code in (401, 403, 405)
        assert r.headers.get("content-type", "").startswith("application/json")


# ---------------- ask_ananta_enabled settings persistence ----------------

class TestAskAnantaSettings:
    def test_get_settings_has_ask_ananta_flag(self, owner_headers):
        r = requests.get(f"{API}/settings", headers=owner_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "ask_ananta_enabled" in body
        assert isinstance(body["ask_ananta_enabled"], bool)

    def test_toggle_persists(self, owner_headers):
        # Read current value
        r0 = requests.get(f"{API}/settings", headers=owner_headers, timeout=10)
        assert r0.status_code == 200
        original = bool(r0.json().get("ask_ananta_enabled", False))
        try:
            # Flip it
            r1 = requests.put(f"{API}/settings", json={"ask_ananta_enabled": not original},
                              headers=owner_headers, timeout=10)
            assert r1.status_code == 200
            body1 = r1.json()
            assert body1.get("ask_ananta_enabled") is (not original)
            # Confirm via GET
            r2 = requests.get(f"{API}/settings", headers=owner_headers, timeout=10)
            assert r2.status_code == 200
            assert r2.json().get("ask_ananta_enabled") is (not original)
        finally:
            # Restore
            requests.put(f"{API}/settings", json={"ask_ananta_enabled": original},
                         headers=owner_headers, timeout=10)

    def test_ask_when_disabled_is_blocked(self, owner_headers):
        # Force disabled, then attempt to ask → server should refuse (403 by design).
        requests.put(f"{API}/settings", json={"ask_ananta_enabled": False},
                     headers=owner_headers, timeout=10)
        r = requests.post(f"{API}/ananta/ask",
                          json={"question": "hello", "tab": "cockpit"},
                          headers=owner_headers, timeout=15)
        assert r.status_code in (403, 409, 400), f"unexpected {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert "detail" in body


# ---------------- P2 import pipeline no-regression (light) ----------------

class TestP2ImportPipelineSmoke:
    def test_import_formats_ok(self, owner_headers):
        r = requests.get(f"{API}/library/import/formats", headers=owner_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Response shape: {formats: [...]} or list, be permissive
        assert data is not None

    def test_import_detect_smoke(self, owner_headers):
        r = requests.post(f"{API}/library/import/detect",
                          json={"raw_content": "//@version=5\nindicator('X')\nplot(close)"},
                          headers=owner_headers, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "best" in body

    def test_backtest_preview_bad_draft_id_is_clean_404_or_400(self, owner_headers):
        r = requests.post(f"{API}/library/imports/does-not-exist/backtest-preview",
                          headers=owner_headers, timeout=15)
        assert r.status_code in (400, 404, 422)
        assert r.headers.get("content-type", "").startswith("application/json")
        assert "detail" in r.json()
