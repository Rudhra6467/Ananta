"""P2 Strategy Import Pipeline — end-to-end HTTP tests (iter36).
Verifies formats, detect (unauth), analyze (owner-gated, uses LLM — 1 call),
draft list/get/put/approve/delete, route-ordering, validation guardrails,
and library projection. Uses REACT_APP_BACKEND_URL (public preview)."""
from __future__ import annotations
import os
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@ananta.ai")
OWNER_PW = os.environ.get("OWNER_PASSWORD", "aZKtwzAqI0SzlwFE6TRqw8aH")

PINE = """//@version=5
strategy("TEST_EMA Cross", overlay=true)
fast = ta.ema(close, input.int(12))
slow = ta.ema(close, input.int(26))
if ta.crossover(fast, slow)
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
"""

FREQ = """
from freqtrade.strategy import IStrategy
class TestStrat(IStrategy):
    timeframe = '1h'
    minimal_roi = {"0": 0.1}
    stoploss = -0.10
    def populate_indicators(self, dataframe, metadata):
        return dataframe
    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[(dataframe['rsi'] < 30), 'enter_long'] = 1
        return dataframe
"""

JESSE = """
from jesse.strategies import Strategy
class Golden(Strategy):
    def should_long(self): return self.rsi < 30
    def should_short(self): return False
    def go_long(self): self.buy = 1, self.price
"""

JSON_SRC = '{"name":"TEST_JSON_Strat","entry":["rsi<30"],"exit":["rsi>70"],"timeframe":"4h"}'


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PW}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


# ---------- formats / detect (no auth) ----------

def test_formats_public():
    r = requests.get(f"{BASE_URL}/api/library/import/formats", timeout=10)
    assert r.status_code == 200
    formats = r.json()["formats"]
    keys = {f["key"] for f in formats}
    for expected in ("pine_script", "freqtrade", "jesse", "json"):
        assert expected in keys, f"missing format {expected}"


def test_detect_pine_public():
    r = requests.post(f"{BASE_URL}/api/library/import/detect",
                      json={"raw_content": PINE}, timeout=10)
    assert r.status_code == 200
    assert r.json()["best"] == "pine_script"


def test_detect_freqtrade_public():
    r = requests.post(f"{BASE_URL}/api/library/import/detect",
                      json={"raw_content": FREQ}, timeout=10)
    assert r.json()["best"] == "freqtrade"


def test_detect_jesse_public():
    r = requests.post(f"{BASE_URL}/api/library/import/detect",
                      json={"raw_content": JESSE}, timeout=10)
    assert r.json()["best"] == "jesse"


def test_detect_json_public():
    r = requests.post(f"{BASE_URL}/api/library/import/detect",
                      json={"raw_content": JSON_SRC}, timeout=10)
    assert r.json()["best"] == "json"


# ---------- route ordering ----------

def test_route_order_imports_not_shadowed(auth_headers):
    """/api/library/imports must not be captured by /api/library/{strategy_id}."""
    r = requests.get(f"{BASE_URL}/api/library/imports", headers=auth_headers, timeout=10)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:200]}"
    body = r.json()
    assert "drafts" in body and isinstance(body["drafts"], list)


# ---------- auth gating ----------

def test_analyze_requires_owner():
    # bypass conftest autoauth by using a fresh session with an unrelated header
    s = requests.Session()
    s.headers["X-No-Auth"] = "1"
    r = s.post(f"{BASE_URL}/api/library/import/analyze",
               json={"raw_content": PINE}, timeout=30,
               headers={"Authorization": ""})  # empty auth header — server should reject
    # server accepts empty as unauth; some frameworks reject as 401
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"


def test_list_drafts_requires_owner():
    r = requests.get(f"{BASE_URL}/api/library/imports", timeout=30,
                     headers={"Authorization": ""})
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ---------- happy path: analyze -> get -> put -> approve -> library visibility ----------

DRAFT = {}  # module-shared state


def test_analyze_pine_success(auth_headers):
    """Real LLM call — expected ~15s."""
    r = requests.post(f"{BASE_URL}/api/library/import/analyze",
                      headers=auth_headers,
                      json={"raw_content": PINE, "source_format": "auto",
                            "name": "TEST_ImportPine"}, timeout=90)
    assert r.status_code == 200, f"analyze failed: {r.status_code} {r.text[:500]}"
    d = r.json()
    for f in ("id", "name", "entry_rules", "exit_rules", "indicators", "parameters",
              "direction", "conversion_confidence", "conversion_report", "validation",
              "source_format", "imported"):
        assert f in d, f"draft missing field '{f}'"
    assert d["imported"] is True
    assert d["source_format"] == "pine_script"
    assert isinstance(d["entry_rules"], list) and len(d["entry_rules"]) >= 1
    assert d["validation"]["status"] in ("ready", "warnings", "blocked")
    DRAFT["id"] = d["id"]
    DRAFT["validation"] = d["validation"]


def test_get_draft(auth_headers):
    assert "id" in DRAFT
    r = requests.get(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                     headers=auth_headers, timeout=10)
    assert r.status_code == 200
    assert r.json()["id"] == DRAFT["id"]


def test_list_shows_draft(auth_headers):
    r = requests.get(f"{BASE_URL}/api/library/imports", headers=auth_headers, timeout=10)
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()["drafts"]}
    assert DRAFT["id"] in ids


def test_put_edit_revalidates(auth_headers):
    r = requests.put(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                     headers=auth_headers,
                     json={"patch": {"name": "TEST_ImportPine_Edited",
                                     "tags": ["ema", "trend"]}},
                     timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "TEST_ImportPine_Edited"
    assert "ema" in (d.get("tags") or [])
    assert "validation" in d


def test_approve_blocked_when_no_entry_rules(auth_headers):
    """Wipe entry_rules -> validation error -> approve returns 422."""
    r = requests.put(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                     headers=auth_headers, json={"patch": {"entry_rules": []}},
                     timeout=15)
    assert r.status_code == 200
    assert r.json()["validation"]["error_count"] >= 1

    r2 = requests.post(f"{BASE_URL}/api/library/imports/{DRAFT['id']}/approve",
                       headers=auth_headers, timeout=15)
    assert r2.status_code == 422, f"expected 422, got {r2.status_code}: {r2.text[:200]}"


def test_short_only_warns_but_not_blocked(auth_headers):
    """Restore entry_rules + set direction=short -> warning, but approve should proceed."""
    r = requests.put(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                     headers=auth_headers,
                     json={"patch": {"entry_rules": ["ta.crossover(fast, slow)"],
                                     "exit_rules": ["ta.crossunder(fast, slow)"],
                                     "direction": "short",
                                     "parameters": {"fast": 12, "slow": 26},
                                     "risk_management": {"stop_loss_pct": 5}}},
                     timeout=15)
    assert r.status_code == 200
    v = r.json()["validation"]
    assert v["warning_count"] >= 1
    assert v["error_count"] == 0
    # revert direction to long before approve
    r2 = requests.put(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                      headers=auth_headers, json={"patch": {"direction": "long"}}, timeout=15)
    assert r2.status_code == 200


def test_approve_finalizes_to_library(auth_headers):
    r = requests.post(f"{BASE_URL}/api/library/imports/{DRAFT['id']}/approve",
                      headers=auth_headers, timeout=20)
    assert r.status_code == 200, f"approve failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["approved"] is True
    lib_id = body["library_id"]
    DRAFT["library_id"] = lib_id
    # verify visibility in library
    r2 = requests.get(f"{BASE_URL}/api/library/{lib_id}", timeout=10)
    assert r2.status_code == 200, r2.text
    doc = r2.json()
    assert doc.get("imported") is True
    assert doc["id"] == lib_id


def test_library_listing_includes_imported(auth_headers):
    r = requests.get(f"{BASE_URL}/api/library", timeout=15)
    assert r.status_code == 200
    strategies = r.json().get("strategies", [])
    ids = {s["id"] for s in strategies}
    assert DRAFT.get("library_id") in ids
    # at least one item is imported=True
    assert any(s.get("imported") for s in strategies)


# ---------- cleanup ----------

def test_cleanup_delete_draft_and_library(auth_headers):
    # delete draft (approved status but still exists)
    r = requests.delete(f"{BASE_URL}/api/library/imports/{DRAFT['id']}",
                        headers=auth_headers, timeout=10)
    assert r.status_code in (200, 404)  # tolerate if already gone
    # delete imported library entry to keep environment clean
    lib_id = DRAFT.get("library_id")
    if lib_id:
        # No delete endpoint on library (owner delete may exist); best-effort via mongo not available here.
        # We leave the imported strategy — retest_context will note it.
        pass
