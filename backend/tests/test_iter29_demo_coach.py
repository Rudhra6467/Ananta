"""Iter 29 backend tests — Competition Demo + AI Trading Coach.

Covers:
  - GET  /api/admin/demo/status
  - POST /api/admin/demo/load     (owner-gated, seeds ~42 trades / 5 configs / 2 runs / 3 strategy_meta)
  - GET  /api/strategy/metrics    (validates demo profile: hunter LIVE healthiest, continuation weakest)
  - POST /api/admin/demo/reset    (owner-gated, back to clean $1200)
  - POST /api/coach/weekly-review (owner-gated, JSON shape, whitelist + clamp)
  - POST /api/coach/apply         (owner-gated, whitelist enforcement, persistence)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")

WHITELIST_KEYS = {
    "min_confidence", "max_daily_loss_pct", "max_concurrent_positions",
    "max_spread_pct", "squeeze_vol_expansion_min", "rsi_reset_max",
}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner_token(session):
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token")
    assert tok, "no token in login response"
    return tok


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ---------------- Demo endpoints ----------------

class TestDemoEndpoints:

    def test_demo_status_public(self, session):
        r = session.get(f"{BASE_URL}/api/admin/demo/status", timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "loaded" in j and "demo_trades" in j
        assert isinstance(j["loaded"], bool)
        assert isinstance(j["demo_trades"], int)

    def test_demo_load_requires_owner(self, session):
        r = session.post(f"{BASE_URL}/api/admin/demo/load", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 without token, got {r.status_code}"

    def test_demo_load_owner_seeds_curated_data(self, session, owner_headers):
        r = session.post(f"{BASE_URL}/api/admin/demo/load", headers=owner_headers, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        # Expect 18+14+10 = 42 trades, 5 configs, 2 runs, 3 strategies
        assert j.get("trades") == 42, f"expected 42 trades, got {j.get('trades')}"
        assert j.get("configs") == 5
        assert j.get("runs") == 2
        assert set(j.get("strategies", [])) == {"hunter", "squeeze", "continuation"}

        # status reflects seeded trades
        s = session.get(f"{BASE_URL}/api/admin/demo/status", timeout=10).json()
        assert s["loaded"] is True
        assert s["demo_trades"] == 42

    def test_strategy_metrics_reflect_demo_profile(self, session, owner_headers):
        # After load, metrics endpoint should show all 3 strategies + hunter healthiest
        r = session.get(f"{BASE_URL}/api/strategy/metrics", timeout=15)
        assert r.status_code == 200
        j = r.json()
        # Response may be dict or list; normalise
        if isinstance(j, dict) and isinstance(j.get("metrics"), dict):
            by_key = j["metrics"]
        else:
            rows = j if isinstance(j, list) else j.get("items") or j.get("strategies") or []
            by_key = {(r.get("key") or r.get("strategy") or r.get("id")): r for r in rows}
        assert by_key, f"empty metrics response: {j}"
        for req in ("hunter", "squeeze", "continuation"):
            assert req in by_key, f"missing {req} in metrics keys={list(by_key)}"

        # Validate statuses seeded by demo
        assert (by_key["hunter"].get("status") or "").upper() == "LIVE"
        assert (by_key["squeeze"].get("status") or "").upper() == "PAPER"
        assert (by_key["continuation"].get("status") or "").upper() == "DISABLED"

        # hunter should have highest win_rate (~55%), continuation lowest (~40%)
        def wr(row):
            v = row.get("win_rate_pct") or row.get("win_rate") or 0
            return float(v)
        assert wr(by_key["hunter"]) > wr(by_key["continuation"]), \
            f"hunter win_rate {wr(by_key['hunter'])} !> continuation {wr(by_key['continuation'])}"

    def test_demo_reset_requires_owner(self, session):
        r = session.post(f"{BASE_URL}/api/admin/demo/reset", timeout=10)
        assert r.status_code in (401, 403)

    def test_demo_reset_owner_clears_book(self, session, owner_headers):
        r = session.post(f"{BASE_URL}/api/admin/demo/reset", headers=owner_headers, timeout=30)
        assert r.status_code == 200, r.text

        # After reset, demo trades cleared
        s = session.get(f"{BASE_URL}/api/admin/demo/status", timeout=10).json()
        assert s["demo_trades"] == 0
        assert s["loaded"] is False

        # Portfolio should be around clean $1200 starting balance
        p = session.get(f"{BASE_URL}/api/portfolio", timeout=10)
        assert p.status_code == 200
        pj = p.json()
        # tolerate small realised drift; starting balance must be 1200
        start = pj.get("starting_balance") or pj.get("cash") or 0
        assert abs(float(start) - 1200.0) < 1e-3 or abs(float(pj.get("cash", 0)) - 1200.0) < 5.0


# ---------------- Coach endpoints ----------------

class TestCoach:

    def test_weekly_review_requires_owner(self, session):
        r = session.post(f"{BASE_URL}/api/coach/weekly-review", timeout=10)
        assert r.status_code in (401, 403)

    def test_weekly_review_owner_shape_and_whitelist(self, session, owner_headers):
        # Re-seed demo so coach has data to talk about
        session.post(f"{BASE_URL}/api/admin/demo/load", headers=owner_headers, timeout=30)

        r = session.post(f"{BASE_URL}/api/coach/weekly-review", headers=owner_headers, timeout=120)
        assert r.status_code == 200, f"coach failed: {r.status_code} {r.text[:400]}"
        j = r.json()

        # shape
        for k in ("summary", "best_strategy", "worst_strategy", "common_mistake",
                  "recommendation", "estimated_impact", "confidence", "stats"):
            assert k in j, f"missing top-level key {k} in review keys={list(j)}"
        assert isinstance(j["summary"], str) and len(j["summary"]) > 5

        rec = j["recommendation"]
        for k in ("title", "detail", "setting_key", "suggested_value", "applyable"):
            assert k in rec, f"missing recommendation key {k}: {rec}"

        # If applyable, setting_key must be in whitelist and suggested_value clamped
        if rec.get("applyable"):
            assert rec["setting_key"] in WHITELIST_KEYS, f"non-whitelisted key: {rec['setting_key']}"
            from_ranges = {
                "min_confidence": (0.50, 0.95),
                "max_daily_loss_pct": (2.0, 20.0),
                "max_concurrent_positions": (1, 20),
                "max_spread_pct": (0.10, 2.0),
                "squeeze_vol_expansion_min": (1.2, 2.5),
                "rsi_reset_max": (30.0, 45.0),
            }
            lo, hi = from_ranges[rec["setting_key"]]
            v = rec["suggested_value"]
            assert v is not None and lo <= float(v) <= hi, \
                f"suggested_value {v} not in [{lo},{hi}] for {rec['setting_key']}"
            # current_value should also be present
            assert "current_value" in rec

    def test_coach_apply_rejects_non_whitelisted(self, session, owner_headers):
        r = session.post(f"{BASE_URL}/api/coach/apply",
                         headers=owner_headers,
                         json={"setting_key": "arbitrary_bogus_key", "value": 3.14},
                         timeout=10)
        assert r.status_code == 400, f"expected 400 non-whitelist, got {r.status_code} {r.text}"

    def test_coach_apply_requires_owner(self, session):
        r = session.post(f"{BASE_URL}/api/coach/apply",
                         json={"setting_key": "min_confidence", "value": 0.72}, timeout=10)
        assert r.status_code in (401, 403)

    def test_coach_apply_owner_persists_clamped(self, session, owner_headers):
        # Apply a min_confidence value inside allowed range
        target = 0.72
        r = session.post(f"{BASE_URL}/api/coach/apply",
                         headers=owner_headers,
                         json={"setting_key": "min_confidence", "value": target},
                         timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("setting_key") == "min_confidence"
        assert abs(float(j.get("applied_value")) - target) < 1e-6

        # Verify persistence via /api/settings
        s = session.get(f"{BASE_URL}/api/settings", timeout=10)
        assert s.status_code == 200
        sj = s.json()
        assert abs(float(sj.get("min_confidence")) - target) < 1e-6

    def test_coach_apply_clamps_out_of_range(self, session, owner_headers):
        # 5.0 is way above the 0.95 ceiling for min_confidence -> should clamp to 0.95
        r = session.post(f"{BASE_URL}/api/coach/apply",
                         headers=owner_headers,
                         json={"setting_key": "min_confidence", "value": 5.0},
                         timeout=15)
        assert r.status_code == 200, r.text
        assert abs(float(r.json()["applied_value"]) - 0.95) < 1e-6
