"""Iter 6 HTTP integration tests: Vault Engine + Swing pivot.

Run via REACT_APP_BACKEND_URL against the live backend. Asserts:
  * /api/settings exposes new swing defaults + vault fields, no micro_flip_* keys.
  * /api/settings PUT clamps + persists vault_sync_enabled / vault_max_override_usd / htf_trend_enabled.
  * POST /api/cycle/run/BTC returns a decision and reasoning with 'vault' + 'htf_evidence'.
  * /api/public/snapshot (the closest equivalent to "state") has settings WITHOUT micro_flip_* keys.
  * /api/reasoning?limit=5 returns items after a cycle ran.

SAFETY: Tests verify trading_mode stays PAPER throughout. LIVE/DRY_RUN never touched.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    return s


@pytest.fixture(scope="module", autouse=True)
def safety_guard(http):
    r = http.get(f"{API}/settings", timeout=30)
    assert r.status_code == 200, r.text
    mode = r.json().get("trading_mode")
    assert mode == "PAPER", f"REFUSE: trading_mode is {mode!r}, must be PAPER for tests"
    yield
    # final re-check
    r2 = http.get(f"{API}/settings", timeout=30)
    assert r2.json().get("trading_mode") == "PAPER", "trading_mode drifted off PAPER during tests"


# ----- /api/settings: defaults shape -----
class TestSettingsShape:
    def test_swing_defaults_and_no_micro_flip(self, http):
        r = http.get(f"{API}/settings", timeout=30)
        assert r.status_code == 200
        d = r.json()

        # swing values (current persisted values; check they match spec)
        assert d["stop_loss_pct"] == pytest.approx(10.0, abs=0.001), d.get("stop_loss_pct")
        assert d["trail_arm_pct"] == pytest.approx(5.0, abs=0.001), d.get("trail_arm_pct")
        assert d["trail_distance_pct"] == pytest.approx(3.0, abs=0.001), d.get("trail_distance_pct")
        assert d["min_confidence"] == pytest.approx(0.80, abs=0.001), d.get("min_confidence")
        assert d["max_daily_loss_pct"] == pytest.approx(10.0, abs=0.001), d.get("max_daily_loss_pct")
        assert d["normal_lot_usd"] == pytest.approx(20.0, abs=0.001), d.get("normal_lot_usd")
        assert d["strong_lot_usd"] == pytest.approx(30.0, abs=0.001), d.get("strong_lot_usd")
        assert d["breakout_lot_usd"] == pytest.approx(50.0, abs=0.001), d.get("breakout_lot_usd")

        # vault + htf must be present
        assert "vault_sync_enabled" in d
        assert "vault_max_override_usd" in d
        assert "htf_trend_enabled" in d
        assert isinstance(d["vault_sync_enabled"], bool)
        assert isinstance(d["htf_trend_enabled"], bool)
        assert isinstance(d["vault_max_override_usd"], (int, float))

        # micro_flip_* and exit_imbalance_threshold MUST be gone
        leaked = [k for k in d if k.startswith("micro_flip_")]
        assert not leaked, f"micro_flip_* keys still in /api/settings: {leaked}"
        assert "exit_imbalance_threshold" not in d


# ----- /api/settings: PUT validation + persistence -----
class TestSettingsPutVault:
    def test_put_vault_fields_persist_and_clamp(self, http):
        # snapshot original
        orig = http.get(f"{API}/settings", timeout=30).json()
        try:
            # toggle vault_sync on, set override above ceiling -> clamp to 1_000_000
            r = http.put(
                f"{API}/settings",
                json={
                    "vault_sync_enabled": True,
                    "vault_max_override_usd": 99_999_999.0,  # > 1_000_000, expect clamp
                    "htf_trend_enabled": False,
                },
                timeout=30,
            )
            assert r.status_code == 200, r.text
            saved = r.json()
            assert saved["vault_sync_enabled"] is True
            assert saved["htf_trend_enabled"] is False
            assert saved["vault_max_override_usd"] == pytest.approx(1_000_000.0, abs=0.01), saved["vault_max_override_usd"]

            # also test lower clamp: 0 -> 1.0
            r2 = http.put(f"{API}/settings", json={"vault_max_override_usd": 0.0}, timeout=30)
            assert r2.status_code == 200
            assert r2.json()["vault_max_override_usd"] == pytest.approx(1.0, abs=0.01)

            # in-range persists (re-GET)
            r3 = http.put(
                f"{API}/settings",
                json={
                    "vault_sync_enabled": False,
                    "vault_max_override_usd": 250.0,
                    "htf_trend_enabled": True,
                },
                timeout=30,
            )
            assert r3.status_code == 200
            g = http.get(f"{API}/settings", timeout=30).json()
            assert g["vault_sync_enabled"] is False
            assert g["htf_trend_enabled"] is True
            assert g["vault_max_override_usd"] == pytest.approx(250.0, abs=0.01)
        finally:
            # restore
            http.put(
                f"{API}/settings",
                json={
                    "vault_sync_enabled": orig.get("vault_sync_enabled"),
                    "vault_max_override_usd": orig.get("vault_max_override_usd"),
                    "htf_trend_enabled": orig.get("htf_trend_enabled"),
                },
                timeout=30,
            )


# ----- POST /api/cycle/run/BTC + GET /api/reasoning -----
class TestCycleAndReasoning:
    def test_run_cycle_btc_returns_decision_with_vault_and_htf_evidence(self, http):
        # may 502 from Cloudflare on slow Gemini; retry once then inspect persisted reasoning
        decision = None
        last_err = None
        body = None
        for attempt in range(2):
            try:
                r = http.post(f"{API}/cycle/run/BTC", timeout=120)
                if r.status_code == 200:
                    body = r.json()
                    decision = body.get("decision")
                    break
                last_err = f"{r.status_code}: {r.text[:200]}"
            except requests.RequestException as e:
                last_err = str(e)
            time.sleep(2)

        # Fall back to persisted reasoning if HTTP timed out at ingress
        if body is None:
            time.sleep(3)
            rr = http.get(f"{API}/reasoning", params={"limit": 5, "symbol": "BTC/USD"}, timeout=30)
            assert rr.status_code == 200, f"reasoning fetch failed after cycle retry: {last_err}"
            items = rr.json()["items"]
            assert items, f"no reasoning row persisted; last error: {last_err}"
            body = items[0]
            decision = body.get("decision")

        assert decision in {"HOLD", "BUY", "SELL", "BLOCKED"}, f"unexpected decision: {decision!r} body={body}"

        reasoning_id = body.get("reasoning_id")
        assert isinstance(reasoning_id, str) and reasoning_id, f"reasoning_id missing: {body}"

        # Inspect evidence on the persisted reasoning row (cycle/run response doesn't include it).
        time.sleep(1)
        rr = http.get(f"{API}/reasoning", params={"limit": 20, "symbol": "BTC/USD"}, timeout=30)
        assert rr.status_code == 200
        rows = rr.json()["items"]
        match = next((x for x in rows if x.get("id") == reasoning_id), None)
        assert match is not None, f"reasoning row {reasoning_id} not found in last 20 rows"
        ev = match.get("evidence") or {}
        assert isinstance(ev, dict) and ev, f"evidence empty on reasoning row: {match}"
        assert "vault" in ev, f"evidence missing 'vault' key: {sorted(ev.keys())}"
        assert "htf_evidence" in ev, f"evidence missing 'htf_evidence' key: {sorted(ev.keys())}"

    def test_reasoning_list_returns_items(self, http):
        r = http.get(f"{API}/reasoning", params={"limit": 5}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and isinstance(body["items"], list)
        assert body["count"] >= 1, f"expected >=1 reasoning row after cycle, got {body['count']}"


# ----- /api/public/snapshot (the "state" surface) -----
class TestPublicSnapshotNoMicroFlip:
    def test_public_settings_omits_micro_flip(self, http):
        r = http.get(f"{API}/public/snapshot", timeout=60)
        assert r.status_code == 200
        body = r.json()
        for k in ("portfolio", "risk", "settings", "snapshots"):
            assert k in body, f"public/snapshot missing top-level {k}"
        ps = body["settings"]
        leaked = [k for k in ps if k.startswith("micro_flip_")]
        assert not leaked, f"public_settings leaks micro_flip_*: {leaked}"
        assert "exit_imbalance_threshold" not in ps
        # vault fields should be in public surface
        assert "vault_sync_enabled" in ps
        assert "vault_max_override_usd" in ps
        assert "htf_trend_enabled" in ps
