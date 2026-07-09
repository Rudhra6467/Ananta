"""
Iter34 P1 Phase-1 tests: Strategy Library catalog, filters, chips, favorite, ai-grade,
multi-metric leaderboard sort, and Active Watchlist add/remove.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# -------- Library catalog --------
class TestLibraryCatalog:
    def test_library_has_16_strategies(self):
        r = requests.get(f"{BASE_URL}/api/library?limit=100")
        assert r.status_code == 200
        d = r.json()
        assert d.get("count") == 16
        assert len(d.get("strategies", [])) == 16
        s = d["strategies"][0]
        # rich metadata contract
        for key in ("id", "name", "source", "style", "risk", "timeframe",
                    "ai_summary", "ai_health_score", "ai_grade", "ai_confidence",
                    "historical_results", "rating", "favorite", "internal"):
            assert key in s, f"missing key {key} on library item"

    def test_library_facets_contract(self):
        r = requests.get(f"{BASE_URL}/api/library/facets")
        assert r.status_code == 200
        d = r.json()
        for k in ("market_regime", "market_type", "style", "timeframe",
                  "risk", "ai_grade", "source"):
            assert k in d and isinstance(d[k], list) and len(d[k]) > 0

    def test_library_detail_by_id(self):
        r = requests.get(f"{BASE_URL}/api/library?limit=100")
        sid = r.json()["strategies"][0]["id"]
        r2 = requests.get(f"{BASE_URL}/api/library/{sid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == sid

    def test_library_detail_404(self):
        r = requests.get(f"{BASE_URL}/api/library/NON_EXISTENT_ID_XYZ")
        assert r.status_code == 404

    def test_search_q_filters(self):
        r = requests.get(f"{BASE_URL}/api/library?q=hunter")
        assert r.status_code == 200
        # at least one result should match (case-insensitive) or empty ok if no match
        items = r.json()["strategies"]
        assert all(("hunter" in (it["name"] + it.get("description", "")).lower())
                   for it in items) or len(items) == 0

    def test_filter_risk_multi_select(self):
        r = requests.get(f"{BASE_URL}/api/library?risk=Conservative,Aggressive")
        assert r.status_code == 200
        for it in r.json()["strategies"]:
            assert it["risk"] in ("Conservative", "Aggressive"), f"got risk={it['risk']}"

    def test_filter_ai_grade(self):
        r = requests.get(f"{BASE_URL}/api/library?ai_grade=A")
        assert r.status_code == 200
        for it in r.json()["strategies"]:
            assert it["ai_grade"] == "A"

    def test_filter_min_health(self):
        r = requests.get(f"{BASE_URL}/api/library?min_health=80")
        assert r.status_code == 200
        for it in r.json()["strategies"]:
            assert (it.get("ai_health_score") or 0) >= 80

    def test_chip_top_internal(self):
        r = requests.get(f"{BASE_URL}/api/library?chip=top_internal")
        assert r.status_code == 200
        items = r.json()["strategies"]
        assert len(items) >= 1
        # Internal strategies should be at the TOP (sorted first)
        internal_count = sum(1 for it in items if it.get("internal"))
        assert internal_count >= 1, "no internal strategies present"
        # First internal_count items should all be internal
        for it in items[:internal_count]:
            assert it.get("internal") is True, \
                f"top_internal chip: non-internal item ranked ahead of internals: {it['name']}"

    def test_chip_top_rated(self):
        r = requests.get(f"{BASE_URL}/api/library?chip=top_rated")
        assert r.status_code == 200
        items = r.json()["strategies"]
        assert len(items) >= 1
        ratings = [it.get("rating", 0) for it in items]
        assert ratings == sorted(ratings, reverse=True), f"ratings not desc: {ratings}"

    def test_chip_healthiest(self):
        r = requests.get(f"{BASE_URL}/api/library?chip=healthiest")
        assert r.status_code == 200
        items = r.json()["strategies"]
        scores = [it.get("ai_health_score") or 0 for it in items]
        assert scores == sorted(scores, reverse=True), f"health not desc: {scores}"

    def test_chip_trending(self):
        r = requests.get(f"{BASE_URL}/api/library?chip=trending")
        assert r.status_code == 200
        assert len(r.json()["strategies"]) >= 1


# -------- Favorite --------
class TestLibraryFavorite:
    def test_favorite_requires_owner(self):
        r = requests.get(f"{BASE_URL}/api/library?limit=1")
        sid = r.json()["strategies"][0]["id"]
        r2 = requests.post(f"{BASE_URL}/api/library/{sid}/favorite")
        assert r2.status_code in (401, 403), r2.status_code

    def test_favorite_toggle_and_filter(self, owner_headers):
        r = requests.get(f"{BASE_URL}/api/library?limit=100")
        # Pick a non-internal catalog item to avoid mutating engine strategies
        cat = [s for s in r.json()["strategies"] if not s.get("internal")][0]
        sid = cat["id"]
        original = bool(cat.get("favorite"))

        # Toggle 1
        r1 = requests.post(f"{BASE_URL}/api/library/{sid}/favorite", headers=owner_headers)
        assert r1.status_code == 200
        new_state = r1.json().get("favorite")
        assert new_state != original

        # Filter favorite=1 should reflect state when new_state is True
        if new_state:
            rf = requests.get(f"{BASE_URL}/api/library?favorite=1")
            assert rf.status_code == 200
            ids = [it["id"] for it in rf.json()["strategies"]]
            assert sid in ids

        # Toggle back to original (cleanup)
        r2 = requests.post(f"{BASE_URL}/api/library/{sid}/favorite", headers=owner_headers)
        assert r2.status_code == 200
        assert r2.json().get("favorite") == original


# -------- AI grade (ONE run only, LLM credits) --------
class TestLibraryAIGrade:
    def test_ai_grade_requires_owner(self):
        r = requests.get(f"{BASE_URL}/api/library?limit=1")
        sid = r.json()["strategies"][0]["id"]
        r2 = requests.post(f"{BASE_URL}/api/library/{sid}/ai-grade")
        assert r2.status_code in (401, 403)

    def test_ai_grade_one_strategy(self, owner_headers):
        # Pick the catalog item with LOWEST rating to minimize impact if mutated
        r = requests.get(f"{BASE_URL}/api/library?limit=100")
        cats = [s for s in r.json()["strategies"] if not s.get("internal")]
        cats.sort(key=lambda x: x.get("rating", 0))
        sid = cats[0]["id"]

        r2 = requests.post(f"{BASE_URL}/api/library/{sid}/ai-grade",
                           headers=owner_headers, timeout=90)
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert "ai_summary" in d
        assert d.get("ai_grade") in ("A", "B", "C", "D", "F")
        assert 0 <= (d.get("ai_health_score") or 0) <= 100
        # ai_confidence is documented (library_ai.py:28) as integer 0-100
        assert 0 <= (d.get("ai_confidence") or 0) <= 100


# -------- Leaderboard sort --------
class TestLeaderboardSort:
    SORT_OPTIONS = [
        "net_pnl", "roi", "win_rate", "ai_health_score", "sharpe", "sortino",
        "profit_factor", "max_drawdown", "avg_trade", "trades", "rating"
    ]

    @pytest.mark.parametrize("metric", SORT_OPTIONS)
    def test_leaderboard_sort_returns_200(self, metric):
        r = requests.get(f"{BASE_URL}/api/analytics/leaderboard?sort={metric}&source=all")
        assert r.status_code == 200, f"{metric}: {r.text[:200]}"
        d = r.json()
        assert "leaderboard" in d
        rows = d["leaderboard"]
        assert isinstance(rows, list)
        if rows:
            r0 = rows[0]
            assert "rank" in r0

    def test_leaderboard_source_live(self):
        r = requests.get(f"{BASE_URL}/api/analytics/leaderboard?sort=roi&source=live")
        assert r.status_code == 200

    def test_leaderboard_source_library(self):
        r = requests.get(f"{BASE_URL}/api/analytics/leaderboard?sort=roi&source=library")
        assert r.status_code == 200

    def test_leaderboard_max_drawdown_asc(self):
        r = requests.get(f"{BASE_URL}/api/analytics/leaderboard?sort=max_drawdown&source=all")
        assert r.status_code == 200
        rows = r.json()["leaderboard"]
        vals = [row.get("max_drawdown") for row in rows if row.get("max_drawdown") is not None]
        assert vals == sorted(vals), f"max_drawdown not asc: {vals}"


# -------- Active Watchlist --------
class TestActiveWatchlist:
    def test_watchlist_search_public(self):
        r = requests.get(f"{BASE_URL}/api/watchlist/search?q=BTC")
        assert r.status_code == 200
        d = r.json()
        assert "results" in d or "options" in d or isinstance(d, list)

    def test_watchlist_add_requires_owner(self):
        r = requests.post(f"{BASE_URL}/api/watchlist/add", json={"symbol": "BTC/USD"})
        assert r.status_code in (401, 403)

    def test_watchlist_add_invalid_symbol_returns_400(self, owner_headers):
        r = requests.post(f"{BASE_URL}/api/watchlist/add",
                          json={"symbol": "ZZ_NOT_A_TRADABLE_PAIR"},
                          headers=owner_headers)
        # Backend should reject non-tradable symbols
        assert r.status_code == 400, r.text

    def test_watchlist_add_and_remove_roundtrip(self, owner_headers):
        # Get current watchlist via settings
        rs = requests.get(f"{BASE_URL}/api/settings")
        assert rs.status_code == 200
        current = list(rs.json().get("enabled_symbols") or [])
        # Search for a symbol not in current watchlist (search excludes already-added)
        rr = requests.get(f"{BASE_URL}/api/watchlist/search?q=DOGE")
        assert rr.status_code == 200
        sd = rr.json()
        # extract list of candidates
        cands = sd.get("results") or sd.get("options") or (sd if isinstance(sd, list) else [])
        pick = None
        for c in cands:
            sym = c.get("symbol") if isinstance(c, dict) else c
            if sym and sym not in current:
                pick = sym
                break
        if not pick:
            pytest.skip("No unused symbol available to add")

        # Add
        ra = requests.post(f"{BASE_URL}/api/watchlist/add",
                           json={"symbol": pick}, headers=owner_headers)
        assert ra.status_code == 200, ra.text

        # Verify added
        rs2 = requests.get(f"{BASE_URL}/api/settings")
        assert pick in (rs2.json().get("enabled_symbols") or [])

        # Remove (cleanup)
        rd = requests.post(f"{BASE_URL}/api/watchlist/remove",
                           json={"symbol": pick}, headers=owner_headers)
        assert rd.status_code == 200

        # Verify removed - restored to original state
        rs3 = requests.get(f"{BASE_URL}/api/settings")
        final = list(rs3.json().get("enabled_symbols") or [])
        assert pick not in final
        assert sorted(final) == sorted(current), \
            f"watchlist mutated: before={current} after={final}"

    def test_watchlist_remove_keeps_at_least_one(self, owner_headers):
        # Try to remove ALL but one; final removal should be rejected
        rs = requests.get(f"{BASE_URL}/api/settings")
        syms = list(rs.json().get("enabled_symbols") or [])
        if len(syms) < 1:
            pytest.skip("watchlist empty")
        # Just try removing everything one by one; last should fail
        # SAFETY: only remove up to len-1 items, then attempt one more expected-fail
        temp_removed = []
        try:
            while len(syms) - len(temp_removed) > 1:
                s = [x for x in syms if x not in temp_removed][0]
                r = requests.post(f"{BASE_URL}/api/watchlist/remove",
                                  json={"symbol": s}, headers=owner_headers)
                assert r.status_code == 200
                temp_removed.append(s)
            # Now try removing the last one
            last = [x for x in syms if x not in temp_removed][0]
            r = requests.post(f"{BASE_URL}/api/watchlist/remove",
                              json={"symbol": last}, headers=owner_headers)
            assert r.status_code in (400, 409), \
                f"expected 400/409 when removing last symbol; got {r.status_code}"
        finally:
            # CLEANUP: re-add anything we removed
            for s in temp_removed:
                requests.post(f"{BASE_URL}/api/watchlist/add",
                              json={"symbol": s}, headers=owner_headers)
            # Verify restored
            rs2 = requests.get(f"{BASE_URL}/api/settings")
            final = list(rs2.json().get("enabled_symbols") or [])
            assert sorted(final) == sorted(syms), \
                f"CRITICAL: watchlist not restored. before={syms} after={final}"
