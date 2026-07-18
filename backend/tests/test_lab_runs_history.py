"""Phase C — Server-backed 'My Reports History' backend tests.
Endpoints under test:
  GET    /api/lab/runs                    (owner-only) — server-backed history
  GET    /api/lab/runs/{id}                (owner-only)
  GET    /api/lab/runs/{id}/pdf            (owner-only) — PDF for DONE runs
  DELETE /api/lab/runs/{id}                (owner-only) — remove one run
"""
import os
import urllib.request
import urllib.error

import pytest
import requests


def _raw_request(method: str, url: str, timeout: int = 20):
    """Bypass conftest's requests.Session autouse patch that injects owner auth
    on mutating verbs. urllib is untouched, so we get the true anonymous response.
    Returns (status_code, body_text)."""
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore") if e.fp else ""

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


# --- fixtures ---------------------------------------------------------------
@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"Owner login failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token")
    assert tok, "Login returned no token"
    return tok


@pytest.fixture(scope="module")
def owner_client(owner_token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {owner_token}",
        "Content-Type": "application/json",
    })
    return s


# --- owner-gate -------------------------------------------------------------
class TestOwnerGate:
    """Public/unauth requests must be rejected (401/403)."""

    def test_list_runs_public_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/lab/runs", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403 for public, got {r.status_code}"

    def test_delete_run_public_forbidden(self):
        code, _ = _raw_request("DELETE", f"{BASE_URL}/api/lab/runs/does-not-exist")
        assert code in (401, 403), f"expected 401/403 for public DELETE, got {code}"

    def test_get_run_pdf_public_forbidden(self):
        r = requests.get(f"{BASE_URL}/api/lab/runs/does-not-exist/pdf", timeout=20)
        assert r.status_code in (401, 403)


# --- list -------------------------------------------------------------------
class TestListRuns:
    def test_list_runs_owner_ok(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs?limit=50", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "runs" in data and isinstance(data["runs"], list)

    def test_list_runs_default_limit_and_shape(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs", timeout=30)
        assert r.status_code == 200
        runs = r.json()["runs"]
        # Server default limit is 30
        assert len(runs) <= 30
        if runs:
            row = runs[0]
            for k in ("id", "kind", "status", "created_at"):
                assert k in row, f"missing {k} in run row"
            # _id must NOT leak (mongo object id)
            assert "_id" not in row
            # result body must be excluded from list projection
            assert "result" not in row

    def test_list_runs_limit_max_cap(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs?limit=500", timeout=30)
        # limit is capped at 100 via Query(le=100); >100 -> 422
        assert r.status_code in (422, 400)

    def test_list_contains_non_health_validation_runs(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs?limit=100", timeout=30)
        assert r.status_code == 200
        runs = r.json()["runs"]
        # AnantaPdfs filters out health_sweep client-side, but the server list can include them
        non_health = [x for x in runs if x.get("kind") != "health_sweep"]
        # spec says ~23 non-health runs exist
        assert len(non_health) > 0, "no non-health validation runs present"


# --- get single -------------------------------------------------------------
class TestGetRun:
    def test_get_run_not_found(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs/definitely-missing-id-xyz", timeout=20)
        assert r.status_code == 404

    def test_get_run_ok(self, owner_client):
        lst = owner_client.get(f"{BASE_URL}/api/lab/runs?limit=5", timeout=20).json()["runs"]
        if not lst:
            pytest.skip("no runs available")
        rid = lst[0]["id"]
        r = owner_client.get(f"{BASE_URL}/api/lab/runs/{rid}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("id") == rid
        assert "_id" not in body


# --- pdf --------------------------------------------------------------------
class TestRunPdf:
    def test_pdf_not_found(self, owner_client):
        r = owner_client.get(f"{BASE_URL}/api/lab/runs/nonexistent-id/pdf", timeout=20)
        assert r.status_code == 404

    def test_pdf_download_for_done_run(self, owner_client):
        lst = owner_client.get(f"{BASE_URL}/api/lab/runs?limit=50", timeout=30).json()["runs"]
        done = next((x for x in lst if x.get("status") == "DONE" and x.get("kind") != "health_sweep"), None)
        if not done:
            pytest.skip("no DONE validation run available for PDF test")
        r = owner_client.get(f"{BASE_URL}/api/lab/runs/{done['id']}/pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-", "not a PDF payload"
        assert len(r.content) > 1000, "PDF body suspiciously small"


# --- delete -----------------------------------------------------------------
class TestDeleteRun:
    def test_delete_missing_returns_404(self, owner_client):
        """Non-destructive check that DELETE endpoint is wired and validates id."""
        r = owner_client.delete(f"{BASE_URL}/api/lab/runs/definitely-missing-id-xyz", timeout=20)
        assert r.status_code == 404
        body = r.json()
        assert "detail" in body

    def test_delete_public_forbidden(self):
        code, _ = _raw_request("DELETE", f"{BASE_URL}/api/lab/runs/any")
        assert code in (401, 403), f"expected 401/403 for public DELETE, got {code}"
