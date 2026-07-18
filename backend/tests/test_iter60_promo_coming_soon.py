"""Iter 60 — Promo 'Coming Soon to Ananta' waitlist endpoints.

Backend endpoints under test:
- GET  /api/promo/coming-soon           -> {waitlist_joined, joined_at}
- POST /api/promo/coming-soon/waitlist  -> persists opt-in

These are not auth-gated. Backend also has no per-user isolation (single shared
document key='coming-soon'), so we exercise them sequentially.
"""
import os
import time
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")


def _reset_via_mongo():
    """Best-effort cleanup so the initial GET is false. Requires local mongo."""
    try:
        from pymongo import MongoClient
        mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        dbn = os.environ.get("DB_NAME", "cryptoatlas_db")
        MongoClient(mongo)[dbn].promo_state.delete_many({"key": "coming-soon"})
    except Exception:
        pass


def test_promo_get_initial_state_shape():
    r = requests.get(f"{BASE_URL}/api/promo/coming-soon", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "waitlist_joined" in data
    assert "joined_at" in data
    assert isinstance(data["waitlist_joined"], bool)


def test_promo_waitlist_post_then_get_persists():
    _reset_via_mongo()
    # Initial state (fresh)
    g0 = requests.get(f"{BASE_URL}/api/promo/coming-soon", timeout=10).json()
    assert g0["waitlist_joined"] is False
    assert g0["joined_at"] is None

    # Opt-in
    r = requests.post(
        f"{BASE_URL}/api/promo/coming-soon/waitlist",
        json={"email": "owner@ananta.ai"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    assert r.json()["waitlist_joined"] is True

    # Persisted GET
    time.sleep(0.2)
    g1 = requests.get(f"{BASE_URL}/api/promo/coming-soon", timeout=10).json()
    assert g1["waitlist_joined"] is True
    assert isinstance(g1["joined_at"], str) and len(g1["joined_at"]) > 0


def test_promo_waitlist_no_body_still_ok():
    """POST is not strict about body; empty JSON should still succeed (idempotent)."""
    r = requests.post(f"{BASE_URL}/api/promo/coming-soon/waitlist", json={}, timeout=10)
    assert r.status_code == 200
    assert r.json()["waitlist_joined"] is True


def test_promo_endpoints_not_auth_gated():
    """No Authorization header - should still return 200 (not 401/403)."""
    assert requests.get(f"{BASE_URL}/api/promo/coming-soon", timeout=10).status_code == 200
    assert requests.post(
        f"{BASE_URL}/api/promo/coming-soon/waitlist",
        json={"email": "anon@example.com"},
        timeout=10,
    ).status_code == 200
