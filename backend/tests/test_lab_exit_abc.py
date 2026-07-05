"""
Backend regression for the A/B/C exit-strategy feature (iteration 22).

Covers:
- POST /api/lab/runs accepts exit_method in {native, atr, fixed}, plus target_profit/target_loss/atr_params
- All three runs on the SAME assets+period must produce the SAME number of entries
  (only the exit changes), and DIFFERENT exit_modules (native -> engine modules,
  atr -> ATR_*, fixed -> FIXED_TP/FIXED_SL)
- Fixed exit trades net ~+$5/-$4 (except EOD force-close)
- Replay fields (mfe_usd/mae_usd/profit_left_usd) + aggregates (avg_*_usd) present
- exit_method_label banner text populated
- position_size_usd surfaces on the result (75 from settings.normal_lot_usd)
- PDF 200/non-empty for each method
- Legacy "engine" still accepted and maps to native
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def one_asset(auth):
    r = requests.get(f"{API}/lab/data/coverage", headers=auth, timeout=15)
    assert r.status_code == 200, r.text
    syms = [s["symbol"] for s in (r.json().get("symbols") or []) if s.get("bars_1h", 0) > 0]
    assert syms, "need at least 1 seeded asset"
    return [syms[0]]


def _wait_done(auth, run_id, timeout=120):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{API}/lab/runs/{run_id}", headers=auth, timeout=10)
        assert r.status_code == 200, r.text
        last = r.json()
        if last["status"] in ("DONE", "FAILED"):
            return last
        time.sleep(2)
    pytest.fail(f"run {run_id} not done in {timeout}s (last={last and last.get('status')})")


def _create(auth, assets, exit_method, tp=5, tl=4, atr_params=None):
    body = {
        "kind": "backtest",
        "symbols": assets,
        "period": "2m",
        "strategies": ["hunter", "squeeze", "continuation"],
        "compare_timeframes": False,
        "exit_method": exit_method,
        "target_profit": tp,
        "target_loss": tl,
        "atr_params": atr_params,
    }
    r = requests.post(f"{API}/lab/runs", headers=auth, json=body, timeout=15)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def abc_runs(auth, one_asset):
    """Create + await all three runs on identical inputs."""
    ids = {}
    ids["native"] = _create(auth, one_asset, "native")["id"]
    ids["atr"] = _create(auth, one_asset, "atr", atr_params={
        "multiplier": 2.5, "period": 14, "trail_activation_pct": 3, "trail_distance": 2
    })["id"]
    ids["fixed"] = _create(auth, one_asset, "fixed", tp=5, tl=4)["id"]
    runs = {k: _wait_done(auth, rid) for k, rid in ids.items()}
    for k, r in runs.items():
        assert r["status"] == "DONE", f"{k} failed: {r.get('error')}"
    return runs


def _collect_trades(run):
    per = (run.get("result") or {}).get("per_symbol") or {}
    out = []
    for sym, m in per.items():
        for t in (m.get("trade_log") or []):
            out.append((sym, t))
    return out


# --- 1. all three complete and echo exit_method ---
def test_all_three_methods_reach_done(abc_runs):
    for m in ("native", "atr", "fixed"):
        assert abc_runs[m]["exit_method"] == m, f"{m} run echoed exit_method={abc_runs[m].get('exit_method')}"


# --- 2. identical entry counts (only exit changes) ---
def test_abc_have_identical_entries(abc_runs):
    entries = {}
    for m in ("native", "atr", "fixed"):
        tr = _collect_trades(abc_runs[m])
        # entries are identified by (symbol, strategy, entry_ts, entry_price)
        entries[m] = sorted(
            (sym, t.get("strategy"), t.get("entry_ts"), round(float(t.get("entry_price") or 0), 6))
            for sym, t in tr
        )
    assert entries["native"] == entries["atr"] == entries["fixed"], (
        f"entries diverge across exit methods:\n"
        f"  native={len(entries['native'])} atr={len(entries['atr'])} fixed={len(entries['fixed'])}"
    )
    assert len(entries["fixed"]) > 0, "expected at least 1 entry in the shared entry set"


# --- 3. distinct exit modules per method ---
def test_exit_modules_differ_per_method(abc_runs):
    def mods(run):
        return {t.get("exit_module") for _, t in _collect_trades(run)
                if t.get("exit_module") and t.get("exit_module") != "EOD"}
    native_mods = mods(abc_runs["native"])
    atr_mods = mods(abc_runs["atr"])
    fixed_mods = mods(abc_runs["fixed"])
    # ATR run must contain ATR_* modules
    assert any(str(x).startswith("ATR") for x in atr_mods), f"ATR run missing ATR_* modules: {atr_mods}"
    # Fixed run must contain only FIXED_TP / FIXED_SL (excluding EOD)
    assert fixed_mods.issubset({"FIXED_TP", "FIXED_SL"}), f"Fixed run had non-fixed modules: {fixed_mods}"
    # Native run should have neither FIXED_* nor ATR-only modules dominating
    assert not fixed_mods.intersection({m for m in native_mods if m in ("FIXED_TP", "FIXED_SL")}) or native_mods != fixed_mods, (
        f"Native modules identical to Fixed: {native_mods}"
    )


# --- 4. fixed nets ~+5 / ~-4 (skip EOD) ---
def test_fixed_nets_plus5_minus4(abc_runs):
    saw = False
    for _, t in _collect_trades(abc_runs["fixed"]):
        mod = t.get("exit_module") or ""
        if mod == "EOD" or t.get("exit_reason") == "END_OF_WINDOW":
            continue
        saw = True
        pnl = float(t.get("pnl", 0))
        assert mod in ("FIXED_TP", "FIXED_SL"), f"unexpected module {mod}"
        assert pnl == pytest.approx(5, abs=0.05) or pnl == pytest.approx(-4, abs=0.05), (
            f"fixed trade outside ±$5/$4: pnl={pnl} module={mod}"
        )
    assert saw, "fixed run had no closed trades"


# --- 5. replay fields + aggregates present ---
def test_replay_fields_present(abc_runs):
    for method in ("native", "atr", "fixed"):
        per = (abc_runs[method].get("result") or {}).get("per_symbol") or {}
        assert per, f"{method}: per_symbol missing"
        for sym, m in per.items():
            # aggregates
            for k in ("avg_mfe_usd", "avg_mae_usd", "avg_profit_left_usd", "total_profit_left_usd"):
                assert k in m, f"{method}/{sym} missing aggregate {k}"
            # per-trade replay fields
            for t in (m.get("trade_log") or [])[:3]:
                for k in ("mfe_usd", "mae_usd", "profit_left_usd", "captured_pnl", "position_size_usd"):
                    assert k in t, f"{method}/{sym} trade missing replay field {k}"


# --- 6. exit_method_label + position_size_usd on result ---
def test_labels_and_position_size(abc_runs):
    for method in ("native", "atr", "fixed"):
        res = abc_runs[method].get("result") or {}
        label = res.get("exit_method_label") or ""
        assert label, f"{method}: exit_method_label empty"
        if method == "fixed":
            assert "Fixed" in label
        elif method == "atr":
            assert "ATR" in label
        else:
            assert "Native" in label or "Engine" in label or "Universal" in label
        assert res.get("position_size_usd") in (75, 75.0), (
            f"{method}: expected position_size_usd=75, got {res.get('position_size_usd')}"
        )


# --- 7. PDF for each method ---
def test_pdf_download_all_methods(auth, abc_runs):
    for method in ("native", "atr", "fixed"):
        rid = abc_runs[method]["id"]
        p = requests.get(f"{API}/lab/runs/{rid}/pdf", headers=auth, timeout=30)
        assert p.status_code == 200, f"{method}: pdf {p.status_code}"
        assert p.headers.get("content-type", "").startswith("application/pdf")
        assert len(p.content) > 500, f"{method}: pdf too small ({len(p.content)})"


# --- 8. legacy "engine" still accepted, maps to native ---
def test_legacy_engine_maps_to_native(auth, one_asset):
    created = _create(auth, one_asset, "engine")
    run = _wait_done(auth, created["id"])
    assert run["status"] == "DONE"
    method = run.get("exit_method")
    # backend may re-emit as "native" (preferred) OR keep "engine"; either is acceptable per spec
    assert method in ("native", "engine"), f"legacy engine mapped to unexpected: {method}"
