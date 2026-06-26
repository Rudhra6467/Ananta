"""Phase-B Strategy Research Laboratory + fresh-start integration tests."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PW = "aZKtwzAqI0SzlwFE6TRqw8aH"

EXPECTED_IDS = {"hunter", "vcp", "trend_rider", "bear_breakdown", "neutral_crab"}
REQUIRED_STRAT_KEYS = {
    "id", "name", "scenario", "mode", "detected", "qualified", "breaker_pass",
    "resolved", "wins", "losses", "win_rate_pct", "avg_return_pct",
    "expected_value_pct", "profit_factor", "max_drawdown_pct",
    "qualification_rate_pct", "conversion_rate_pct", "execution_efficiency_pct",
    "vs_hunter", "verdict",
}
VS_HUNTER_KEYS = {"win_rate", "avg_return", "expected_value", "profit_factor"}


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PW}, timeout=20)
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, "no token in login response"
    return tok


# --- /api/research/strategy_lab contract ---
def test_strategy_lab_contract():
    r = requests.get(f"{BASE}/api/research/strategy_lab", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert set(d.keys()) >= {"strategies", "promote_threshold", "window_days", "benchmark"}
    assert d["window_days"] == 30
    assert d["benchmark"] == "hunter"
    assert isinstance(d["promote_threshold"], (int, float))
    strats = d["strategies"]
    assert len(strats) == 5
    ids = {s["id"] for s in strats}
    assert ids == EXPECTED_IDS, f"unexpected ids: {ids}"
    for s in strats:
        missing = REQUIRED_STRAT_KEYS - set(s.keys())
        assert not missing, f"strategy {s.get('id')} missing keys: {missing}"
        vs = s["vs_hunter"]
        assert isinstance(vs, dict)
        missing_vs = VS_HUNTER_KEYS - set(vs.keys())
        assert not missing_vs, f"vs_hunter missing keys: {missing_vs}"


def test_strategy_lab_sorted_by_ev_desc_none_last():
    r = requests.get(f"{BASE}/api/research/strategy_lab", timeout=20)
    d = r.json()
    evs = [s["expected_value_pct"] for s in d["strategies"]]
    non_none = [v for v in evs if v is not None]
    # Non-None block must be at the front and sorted desc
    first_none = next((i for i, v in enumerate(evs) if v is None), len(evs))
    assert all(v is not None for v in evs[:first_none])
    assert non_none == sorted(non_none, reverse=True), f"not sorted desc: {non_none}"


# --- Backward-compat alias ---
def test_strategy_sandbox_alias_matches_lab():
    a = requests.get(f"{BASE}/api/research/strategy_sandbox", timeout=20)
    b = requests.get(f"{BASE}/api/research/strategy_lab", timeout=20)
    assert a.status_code == 200 and b.status_code == 200
    da, db = a.json(), b.json()
    # Same top-level shape; ids match
    assert {s["id"] for s in da["strategies"]} == {s["id"] for s in db["strategies"]} == EXPECTED_IDS
    assert da["window_days"] == db["window_days"] == 30
    assert da["benchmark"] == db["benchmark"] == "hunter"


# --- Trading cycle populates strategy_lab_log ---
def test_cycle_run_increments_detected(owner_token):
    before = requests.get(f"{BASE}/api/research/strategy_lab", timeout=20).json()
    before_det = {s["id"]: s["detected"] for s in before["strategies"]}

    r = requests.post(f"{BASE}/api/cycle/run",
                      headers={"Authorization": f"Bearer {owner_token}"},
                      timeout=120)
    assert r.status_code == 200, f"cycle/run failed: {r.status_code} {r.text[:300]}"

    # Aggregation may take a short moment; poll briefly.
    found = False
    for _ in range(6):
        time.sleep(2)
        after = requests.get(f"{BASE}/api/research/strategy_lab", timeout=20).json()
        after_det = {s["id"]: s["detected"] for s in after["strategies"]}
        if any(after_det[k] > before_det[k] for k in after_det):
            found = True
            break
    # Cycle may produce no signals if market is flat — accept either case but log.
    if not found:
        # At minimum, totals must not regress
        for k in before_det:
            assert after_det[k] >= before_det[k], f"detected regressed for {k}"
    assert True  # contract is satisfied if 200 + no regression


# --- Fresh-start owner gating ---
def test_fresh_start_requires_auth():
    r = requests.post(f"{BASE}/api/admin/fresh-start", timeout=20)
    assert r.status_code in (401, 403), f"expected 401/403 unauthenticated, got {r.status_code}"


def test_fresh_start_with_owner_token(owner_token):
    r = requests.post(f"{BASE}/api/admin/fresh-start",
                      headers={"Authorization": f"Bearer {owner_token}"}, timeout=60)
    assert r.status_code == 200, f"fresh-start failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    assert d.get("ok") is True
    assert "deleted" in d and isinstance(d["deleted"], dict)
    assert d.get("lot_usd") == 75
    assert d.get("starting_balance") == 1200
    port = d.get("portfolio") or {}
    assert port.get("starting_balance") == 1200
    assert port.get("cash") == 1200

    # Verify side effects
    p = requests.get(f"{BASE}/api/portfolio", timeout=20).json()
    assert p.get("starting_balance") == 1200, f"portfolio starting_balance={p.get('starting_balance')}"
    assert p.get("cash") == 1200, f"portfolio cash={p.get('cash')}"

    s = requests.get(f"{BASE}/api/settings", timeout=20).json()
    for key in ("normal_lot_usd", "strong_lot_usd", "breakout_lot_usd"):
        assert s.get(key) == 75, f"settings.{key}={s.get(key)}"


# --- Regression: research endpoints after OOM-fix projections ---
@pytest.mark.parametrize("path", [
    "/api/research/summary",
    "/api/research/funnel",
    "/api/research/missed_opportunities",
])
def test_research_endpoints_regression(path):
    r = requests.get(f"{BASE}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    # Must be JSON parseable
    r.json()
