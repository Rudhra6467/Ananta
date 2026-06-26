"""
Iteration 2 - Judge View + PDF Download endpoints.

New endpoints under test:
- GET  /api/public/snapshot       (sanitized, public, no API keys)
- GET  /api/report/full.pdf
- GET  /api/report/reasoning.pdf?limit=N

Plus a small regression sanity check on iteration-1 endpoints.
"""
from __future__ import annotations

import os

import pytest
import requests

# ---- resolve BASE_URL from env (with frontend/.env fallback) ----
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except FileNotFoundError:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"


# ---- shared session with generous timeout for PDF cold-start ----
class TimeoutSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 60)
        return super().request(method, url, **kwargs)


@pytest.fixture(scope="module")
def client() -> requests.Session:
    s = TimeoutSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def original_settings(client) -> dict:
    """Snapshot settings before we PUT dummy API keys, restore after."""
    r = client.get(f"{API}/settings", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ============================================================
# Regression sanity check (iteration 1 endpoints still work)
# ============================================================
class TestRegression:
    def test_root(self, client):
        r = client.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "running"

    def test_portfolio(self, client):
        r = client.get(f"{API}/portfolio", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("equity", "cash", "starting_balance", "positions", "total_pnl"):
            assert k in body, f"missing field {k}"

    def test_settings(self, client):
        r = client.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        body = r.json()
        for k in ("max_spread_pct", "min_confidence", "enabled_symbols", "trading_mode"):
            assert k in body

    def test_risk_status(self, client):
        r = client.get(f"{API}/risk/status", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "status" in body and "thresholds" in body
        assert "overall_safe" in body["status"]

    def test_reasoning(self, client):
        r = client.get(f"{API}/reasoning?limit=5", timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_trades(self, client):
        r = client.get(f"{API}/trades?limit=5", timeout=30)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_market_snapshots(self, client):
        r = client.get(f"{API}/market/snapshots", timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert "symbols" in body and "snapshots" in body

    def test_put_settings_regression(self, client, original_settings):
        # Just toggle min_confidence to a known value and back
        r = client.put(
            f"{API}/settings",
            json={"min_confidence": 0.55},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert abs(r.json()["min_confidence"] - 0.55) < 1e-6
        # restore
        r = client.put(
            f"{API}/settings",
            json={"min_confidence": original_settings["min_confidence"]},
            timeout=15,
        )
        assert r.status_code == 200

    def test_portfolio_reset_regression(self, client):
        r = client.post(f"{API}/portfolio/reset", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        p = body["portfolio"]
        assert p["cash"] == p["starting_balance"]


# ============================================================
# /api/public/snapshot  - shape + sanitization
# ============================================================
class TestPublicSnapshot:
    DUMMY_KEYS = {
        "coinbase_api_key": "TEST_CB_KEY_XYZ123",
        "coinbase_api_secret": "TEST_CB_SECRET_ABC456",
        "kraken_api_key": "TEST_KRAKEN_KEY_DEF789",
        "kraken_api_secret": "TEST_KRAKEN_SECRET_GHI012",
    }

    def test_shape_contains_required_top_level_keys(self, client):
        r = client.get(f"{API}/public/snapshot", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        required = {
            "generated_at",
            "portfolio",
            "risk",
            "settings",
            "snapshots",
            "trades",
            "reasoning",
        }
        missing = required - set(body.keys())
        assert not missing, f"missing keys in /public/snapshot: {missing}"
        assert isinstance(body["snapshots"], list)
        assert isinstance(body["trades"], list)
        assert isinstance(body["reasoning"], list)

    def test_settings_contains_risk_thresholds_and_symbols(self, client):
        r = client.get(f"{API}/public/snapshot", timeout=60)
        assert r.status_code == 200
        s = r.json()["settings"]
        # Required non-sensitive fields must still be present
        for k in ("max_spread_pct", "min_confidence", "enabled_symbols",
                  "max_daily_loss_pct", "trading_mode"):
            assert k in s, f"public settings missing {k}"
        assert isinstance(s["enabled_symbols"], list)
        assert len(s["enabled_symbols"]) > 0

    def test_api_keys_stripped_after_being_set(self, client, original_settings):
        # 1) Set dummy API key material via PUT /api/settings
        put = client.put(f"{API}/settings", json=self.DUMMY_KEYS, timeout=15)
        assert put.status_code == 200, put.text

        try:
            # 2) Fetch public snapshot and ensure NONE of the dummy values appear
            r = client.get(f"{API}/public/snapshot", timeout=60)
            assert r.status_code == 200
            raw_text = r.text
            body = r.json()

            # a) settings object must NOT contain key fields at all
            s = body["settings"]
            for k in ("coinbase_api_key", "coinbase_api_secret",
                      "kraken_api_key", "kraken_api_secret"):
                assert k not in s, (
                    f"public/snapshot.settings still contains sensitive key '{k}'"
                )

            # b) Dummy values must not appear anywhere in the response body
            for v in self.DUMMY_KEYS.values():
                assert v not in raw_text, (
                    f"sensitive value '{v}' leaked in /public/snapshot response"
                )
        finally:
            # 3) Always restore - blank out the key fields
            restore = client.put(
                f"{API}/settings",
                json={
                    "coinbase_api_key": "",
                    "coinbase_api_secret": "",
                    "kraken_api_key": "",
                    "kraken_api_secret": "",
                },
                timeout=15,
            )
            # don't fail teardown if restore hiccups, but report it
            assert restore.status_code == 200, f"restore failed: {restore.text}"


# ============================================================
# /api/report/full.pdf
# ============================================================
class TestReportFullPdf:
    def test_returns_valid_pdf(self, client):
        r = client.get(f"{API}/report/full.pdf", timeout=60)
        assert r.status_code == 200, r.text[:500]

        # Content-Type
        ct = r.headers.get("Content-Type", "")
        assert "application/pdf" in ct.lower(), f"unexpected Content-Type: {ct}"

        # Content-Disposition
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd.lower(), f"missing attachment disp: {cd}"
        assert ".pdf" in cd.lower(), f"missing .pdf in disposition: {cd}"

        # Body
        assert r.content.startswith(b"%PDF-"), (
            f"PDF magic missing - first 12 bytes: {r.content[:12]!r}"
        )
        assert len(r.content) > 3 * 1024, (
            f"PDF unexpectedly small: {len(r.content)} bytes"
        )


# ============================================================
# /api/report/reasoning.pdf
# ============================================================
class TestReportReasoningPdf:
    def test_returns_valid_pdf_default(self, client):
        r = client.get(f"{API}/report/reasoning.pdf", timeout=60)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("Content-Type", "").lower()
        assert r.content.startswith(b"%PDF-")
        assert len(r.content) > 1024  # reasoning-only, smaller threshold

    def test_limit_param_accepted(self, client):
        r = client.get(f"{API}/report/reasoning.pdf?limit=10", timeout=60)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF-")
        # Content-Disposition still set
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd.lower()
        assert ".pdf" in cd.lower()

    def test_limit_param_zero_or_high(self, client):
        # 0 and a very high number both should be accepted (no 5xx)
        for n in (0, 999):
            r = client.get(f"{API}/report/reasoning.pdf?limit={n}", timeout=60)
            assert r.status_code == 200, f"limit={n} -> {r.status_code}: {r.text[:200]}"
            assert r.content.startswith(b"%PDF-")
