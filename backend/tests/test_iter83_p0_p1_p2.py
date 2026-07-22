"""iter83 pytest coverage:

P0 - Protective Exit Controls global toggles (4 flags) round-trip via /api/settings
P0 - Per-strategy overrides carry allowed_regimes + exit method via profile_overrides
P1 - POST /api/library/import/direct saves a strategy from raw JSON w/o AI
P2 - CLONE -> registry -> Lab run yields non-zero trades attributed to the clone;
     DELETE clone then confirms it disappears from /api/strategy/registry (orphan bug retest)
"""
import copy
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


# ---------- helpers ----------
def _login_token():
    email = os.environ.get("OWNER_EMAIL") or "owner@ananta.ai"
    pw = os.environ.get("OWNER_PASSWORD") or "aZKtwzAqI0SzlwFE6TRqw8aH"
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth():
    return {"Authorization": f"Bearer {_login_token()}"}


@pytest.fixture(scope="module")
def baseline_settings(auth):
    """Snapshot original settings + restore after tests."""
    r = requests.get(f"{BASE_URL}/api/settings", timeout=15)
    assert r.status_code == 200, r.text
    original = r.json()
    yield original
    restore = {
        "structural_stop_enabled": original.get("structural_stop_enabled", True),
        "ema_trend_loss_enabled": original.get("ema_trend_loss_enabled", True),
        "structure_failure_enabled": original.get("structure_failure_enabled", True),
        "strat_exit_enabled": original.get("strat_exit_enabled", True),
        "profile_overrides": original.get("profile_overrides", {}),
    }
    requests.put(f"{BASE_URL}/api/settings", json=restore, headers=auth, timeout=15)


# =========================================================
# P0 - Protective Exit toggles round-trip
# =========================================================
class TestP0ProtectiveExitToggles:
    def test_all_four_toggles_persist_false(self, auth, baseline_settings):
        payload = {
            "structural_stop_enabled": False,
            "ema_trend_loss_enabled": False,
            "structure_failure_enabled": False,
            "strat_exit_enabled": False,
        }
        r = requests.put(f"{BASE_URL}/api/settings", json=payload, headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k, v in payload.items():
            assert body.get(k) is v, f"PUT response {k}={body.get(k)} != {v}"
        # GET roundtrip
        g = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        for k, v in payload.items():
            assert g.get(k) is v, f"GET {k}={g.get(k)} != {v}"

    def test_toggles_flip_back_to_true(self, auth):
        payload = {
            "structural_stop_enabled": True,
            "ema_trend_loss_enabled": True,
            "structure_failure_enabled": True,
            "strat_exit_enabled": True,
        }
        r = requests.put(f"{BASE_URL}/api/settings", json=payload, headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        for k, v in payload.items():
            assert g.get(k) is v


# =========================================================
# P0 - Per-strategy override: allowed_regimes + exit method
# =========================================================
class TestP0PerStrategyOverrides:
    def test_profile_overrides_carry_regime_and_method(self, auth, baseline_settings):
        override = {
            "hunter": {
                "allowed_regimes": ["trending"],
                "method": "atr_trailing",
                "trail_arm_pct": 2.1,
                "trail_distance_pct": 1.2,
                "stop_loss_pct": 3.3,
            }
        }
        r = requests.put(f"{BASE_URL}/api/settings",
                         json={"profile_overrides": override},
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        po = g.get("profile_overrides") or {}
        assert "hunter" in po, f"profile_overrides missing hunter: {po}"
        assert po["hunter"].get("allowed_regimes") == ["trending"]
        assert po["hunter"].get("method") == "atr_trailing"
        assert po["hunter"].get("trail_arm_pct") == 2.1
        assert po["hunter"].get("stop_loss_pct") == 3.3

    def test_clear_profile_overrides(self, auth):
        r = requests.put(f"{BASE_URL}/api/settings",
                         json={"profile_overrides": {}}, headers=auth, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g.get("profile_overrides") == {}


# =========================================================
# P1 - Save without AI direct JSON import
# =========================================================
class TestP1DirectImport:
    def test_import_direct_json_no_ai(self, auth):
        raw_json = (
            '{"name": "iter83 direct import",'
            ' "asset_class": "crypto",'
            ' "entry": "ema20 cross above ema50",'
            ' "exit": "trailing 2%",'
            ' "risk": "1% per trade"}'
        )
        r = requests.post(
            f"{BASE_URL}/api/library/import/direct",
            json={"raw_content": raw_json, "source_format": "json", "name": f"iter83-{uuid.uuid4().hex[:6]}"},
            headers=auth, timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        draft = r.json()
        assert draft.get("ai_skipped") is True, f"missing ai_skipped=True: {draft}"
        assert draft.get("id") or draft.get("draft_id"), f"draft has no id: {draft}"
        assert "extraction" in draft or "ai_summary" in str(draft), f"draft missing extraction: {draft}"

    def test_import_direct_rejects_empty(self, auth):
        r = requests.post(
            f"{BASE_URL}/api/library/import/direct",
            json={"raw_content": "", "source_format": "json"},
            headers=auth, timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_import_direct_rejects_bad_json(self, auth):
        r = requests.post(
            f"{BASE_URL}/api/library/import/direct",
            json={"raw_content": "{not valid json,,,}", "source_format": "json"},
            headers=auth, timeout=15,
        )
        assert r.status_code == 422, r.text


# =========================================================
# P2 - Custom clone deep-link precondition:
#      Clone -> registry lists it -> Lab non-zero trades -> DELETE removes from registry
# =========================================================
class TestP2CloneAndLab:
    @pytest.fixture(scope="class")
    def clone_key(self, auth):
        r = requests.post(f"{BASE_URL}/api/library/ema-cross/clone", headers=auth, timeout=30)
        assert r.status_code == 200, f"clone failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        key = body.get("id") or body.get("key")
        assert key and key.startswith("clone-"), f"unexpected clone response: {body}"
        yield key
        # teardown: best-effort delete
        try:
            requests.delete(f"{BASE_URL}/api/library/{key}", headers=auth, timeout=15)
        except Exception:
            pass

    def test_clone_appears_in_registry(self, clone_key):
        r = requests.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
        assert r.status_code == 200
        reg = r.json()
        items = reg.get("strategies", []) if isinstance(reg, dict) else reg
        keys = [s.get("key") if isinstance(s, dict) else s for s in items]
        assert clone_key in keys, f"clone {clone_key} not in registry keys sample {keys[:20]}"

    def test_lab_backtest_non_zero_trades(self, auth, clone_key):
        payload = {
            "kind": "backtest",
            "symbols": ["BTC/USD"],
            "period": "3m",
            "timeframe": "1h",
            "exit_method": "atr",
            "strategies": [clone_key],
        }
        r = requests.post(f"{BASE_URL}/api/lab/runs", json=payload, headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        rid = r.json().get("id") or r.json().get("run_id")
        assert rid, r.json()
        # poll up to 240s
        deadline = time.time() + 240
        status = None
        run = None
        while time.time() < deadline:
            g = requests.get(f"{BASE_URL}/api/lab/runs/{rid}", headers=auth, timeout=15)
            if g.status_code == 200:
                run = g.json()
                status = run.get("status")
                if status and status.upper() in ("DONE", "FAILED", "ERROR"):
                    break
            time.sleep(3)
        assert status and status.lower() == "done", f"run {rid} status={status} run={str(run)[:300]}"
        per_symbol = (run.get("result") or {}).get("per_symbol") or run.get("per_symbol") or {}
        btc = per_symbol.get("BTC/USD") or {}
        trades = btc.get("trades") or btc.get("trade_count") or 0
        entries = btc.get("entries") or 0
        assert (trades or 0) > 0 or (entries or 0) > 0, f"expected non-zero trades for clone, got per_symbol={btc}"
        breakdown = btc.get("strategy_breakdown") or (run.get("result") or {}).get("strategy_breakdown") or {}
        if breakdown:
            assert clone_key in breakdown, f"clone {clone_key} not in breakdown keys {list(breakdown.keys())}"

    def test_delete_removes_from_registry(self, auth, clone_key):
        d = requests.delete(f"{BASE_URL}/api/library/{clone_key}", headers=auth, timeout=15)
        assert d.status_code in (200, 204), d.text
        # give a beat, then confirm registry no longer has it
        time.sleep(1.0)
        r = requests.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
        assert r.status_code == 200
        reg = r.json()
        items = reg.get("strategies", []) if isinstance(reg, dict) else reg
        keys = [s.get("key") if isinstance(s, dict) else s for s in items]
        assert clone_key not in keys, f"ORPHAN: {clone_key} still listed after DELETE (iter82 bug regressed)"
