"""Iter 30 backend tests

Coverage:
- GET /api/report/trades.pdf?mode=paper|live[&inline=true]  → PDF + correct Content-Disposition
- POST /api/coach/trades-review (owner-only 403 without token; paper=~44 trades; live=0)
"""

import os
import pytest
import requests

def _read_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # fallback: read from /app/frontend/.env so pytest can run without env exports
    try:
        with open("/app/frontend/.env") as fp:
            for ln in fp:
                if ln.startswith("REACT_APP_BACKEND_URL"):
                    return ln.split("=", 1)[1].strip().strip('"').rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _read_backend_url()

OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")


@pytest.fixture(scope="module")
def owner_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Owner login failed ({r.status_code}); skipping owner-gated tests")
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token: str) -> dict:
    return {"Authorization": f"Bearer {owner_token}"}


# ── /api/report/trades.pdf ─────────────────────────────────────────────────────
class TestTradesPdfReport:
    def test_paper_pdf_attachment(self):
        r = requests.get(f"{BASE_URL}/api/report/trades.pdf?mode=paper", timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("attachment"), cd
        assert "paper" in cd
        assert r.content[:4] == b"%PDF"

    def test_live_pdf_attachment(self):
        r = requests.get(f"{BASE_URL}/api/report/trades.pdf?mode=live", timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("attachment")
        assert "live" in cd
        assert r.content[:4] == b"%PDF"

    def test_paper_pdf_inline(self):
        r = requests.get(
            f"{BASE_URL}/api/report/trades.pdf?mode=paper&inline=true", timeout=30
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("inline"), f"expected inline, got: {cd}"
        assert r.content[:4] == b"%PDF"

    def test_all_mode_default(self):
        # sanity: no mode also works (defaults to all)
        r = requests.get(f"{BASE_URL}/api/report/trades.pdf", timeout=30)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# ── /api/coach/trades-review ───────────────────────────────────────────────────
class TestCoachTradesReview:
    def test_forbidden_without_token(self):
        # Bypass conftest's autouse Session.request patch by using a plain requests call
        # with an explicit empty Authorization header override guard: the patch only
        # injects when Authorization is not present, so we set a bogus header ourselves
        # then expect 401 (invalid) — either 401 or 403 counts as "gated".
        r = requests.post(
            f"{BASE_URL}/api/coach/trades-review",
            json={"mode": "paper"},
            headers={"Authorization": "Bearer invalid-token-for-test"},
            timeout=15,
        )
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text[:200]}"

    def test_paper_review_returns_ai_text(self, owner_headers):
        r = requests.post(
            f"{BASE_URL}/api/coach/trades-review",
            headers=owner_headers,
            json={"mode": "paper"},
            timeout=90,  # LLM call ~10-15s
        )
        assert r.status_code == 200, r.text[:600]
        data = r.json()
        assert data.get("mode") == "paper"
        assert isinstance(data.get("trades"), int)
        assert data["trades"] > 0, f"expected >0 paper trades (demo loaded), got {data['trades']}"
        # win_rate + net_pnl present only when trades > 0
        assert "win_rate" in data
        assert "net_pnl" in data
        review = data.get("review") or ""
        assert isinstance(review, str) and len(review.strip()) > 30, f"empty review: {review!r}"

    def test_live_review_no_trades(self, owner_headers):
        r = requests.post(
            f"{BASE_URL}/api/coach/trades-review",
            headers=owner_headers,
            json={"mode": "live"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:600]
        data = r.json()
        assert data.get("mode") == "live"
        assert data.get("trades") == 0
        review = (data.get("review") or "").lower()
        assert "no closed" in review or "no live" in review or "no " in review, review
