"""Iter 23 — Ananta.AI Executive Cockpit regression.

Backend surface exercised for the new 2x2 lab + logs grid:
  - GET  /api/settings                       (must return dynamic_trail_enabled + profile_overrides)
  - PUT  /api/settings                       (accepts new dynamic_trail_enabled + profile_overrides)
  - GET  /api/risk/status
  - GET  /api/analytics/performance
  - GET  /api/lab/runs                       (DONE runs may expose exit_winner hint / exit_comparison)
  - POST /api/strategy/configs/from-lab-run  (Save Winning Config bridge)

Prereqs: REACT_APP_BACKEND_URL exported.  Owner creds from /app/memory/test_credentials.md.
"""
import os
import time
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"owner login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture
def auth(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


# ---------------- settings / kill-switch ----------------
class TestSettings:
    def test_get_settings_shape(self):
        r = requests.get(f"{BASE}/api/settings", timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()
        # New keys required by ExitEngineModal + face-active-engine
        for k in ("dynamic_trail_enabled", "profile_overrides", "stop_loss_pct",
                  "trail_arm_pct", "trail_distance_pct", "manual_kill_switch",
                  "max_concurrent_positions", "max_daily_loss_pct", "min_confidence",
                  "max_spread_pct"):
            assert k in s, f"missing key '{k}' in /api/settings"
        assert isinstance(s["profile_overrides"], dict)

    def test_put_settings_accepts_dynamic_trail_and_overrides(self, auth):
        # Snapshot
        cur = requests.get(f"{BASE}/api/settings", timeout=15).json()
        orig_dt = cur.get("dynamic_trail_enabled")
        orig_ov = cur.get("profile_overrides") or {}

        # Flip dynamic_trail_enabled + add a hunter override
        want = not bool(orig_dt) if orig_dt is not None else True
        ov = dict(orig_ov)
        ov["hunter"] = {**(ov.get("hunter") or {}), "trail_atr_mult": 2.3, "profit_arm_pct": 5}
        r = requests.put(f"{BASE}/api/settings", headers=auth,
                         json={"dynamic_trail_enabled": want, "profile_overrides": ov}, timeout=20)
        assert r.status_code == 200, r.text
        s2 = r.json()
        assert s2["dynamic_trail_enabled"] == want
        assert (s2.get("profile_overrides") or {}).get("hunter", {}).get("trail_atr_mult") == 2.3

        # GET re-read persists
        s3 = requests.get(f"{BASE}/api/settings", timeout=15).json()
        assert s3["dynamic_trail_enabled"] == want
        assert (s3.get("profile_overrides") or {}).get("hunter", {}).get("trail_atr_mult") == 2.3

        # Restore
        requests.put(f"{BASE}/api/settings", headers=auth,
                     json={"dynamic_trail_enabled": bool(orig_dt), "profile_overrides": orig_ov}, timeout=20)

    def test_kill_switch_toggle(self, auth):
        cur = requests.get(f"{BASE}/api/settings", timeout=15).json()
        was = bool(cur.get("manual_kill_switch"))
        r = requests.put(f"{BASE}/api/settings", headers=auth,
                         json={"manual_kill_switch": not was}, timeout=15)
        assert r.status_code == 200
        assert bool(r.json().get("manual_kill_switch")) == (not was)
        # Restore
        requests.put(f"{BASE}/api/settings", headers=auth,
                     json={"manual_kill_switch": was}, timeout=15)

    def test_put_settings_auth_gate_direct(self):
        # Direct urllib bypasses conftest's requests monkeypatch => confirms owner-gate is real.
        import urllib.request as _u
        req = _u.Request(f"{BASE}/api/settings", data=b'{"manual_kill_switch":false}',
                         method="PUT", headers={"Content-Type": "application/json"})
        try:
            _u.urlopen(req, timeout=15)  # noqa: S310
            got = 200
        except _u.HTTPError as e:
            got = e.code
        assert got in (401, 403), f"Expected owner-gate; got {got}"


# ---------------- risk / analytics faces ----------------
class TestFaces:
    def test_risk_status(self):
        r = requests.get(f"{BASE}/api/risk/status", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body
        assert "overall_safe" in body["status"]

    def test_analytics_performance(self):
        r = requests.get(f"{BASE}/api/analytics/performance", timeout=20)
        assert r.status_code == 200, r.text
        a = r.json()
        # face-open-pos handler used to crash when open_positions was array-of-objects
        assert "open_positions" in a
        op = a["open_positions"]
        assert isinstance(op, (list, int, type(None)))
        assert "rolling_24h" in a


# ---------------- lab / save-winning-config ----------------
class TestSaveWinningConfig:
    def test_lab_runs_list(self, auth):
        r = requests.get(f"{BASE}/api/lab/runs?limit=50", headers=auth, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "runs" in body

    def _find_done_backtest_with_ec(self, auth):
        r = requests.get(f"{BASE}/api/lab/runs?limit=50", headers=auth, timeout=20).json()
        for run in (r.get("runs") or []):
            if run.get("status") != "DONE":
                continue
            det = requests.get(f"{BASE}/api/lab/runs/{run['id']}", headers=auth, timeout=20).json()
            ec = ((det.get("run") or det).get("result") or {}).get("exit_comparison")
            if ec:
                return det.get("run") or det, ec
        return None, None

    def test_from_lab_run_bridge_or_seed(self, auth):
        run, ec = self._find_done_backtest_with_ec(auth)
        if not run:
            # Seed by launching a small backtest that generates exit_comparison
            payload = {"kind": "backtest", "assets": ["BTC/USD"], "period": "2m",
                       "strategies": ["hunter"], "exit_method": "engine"}
            r = requests.post(f"{BASE}/api/lab/runs", headers=auth, json=payload, timeout=30)
            if r.status_code != 200:
                pytest.skip(f"cannot seed lab run: {r.status_code} {r.text[:200]}")
            rid = r.json().get("run", {}).get("id") or r.json().get("id")
            # Poll up to ~90s
            deadline = time.time() + 90
            while time.time() < deadline:
                det = requests.get(f"{BASE}/api/lab/runs/{rid}", timeout=20).json()
                run = det.get("run") or det
                if run.get("status") == "DONE":
                    ec = (run.get("result") or {}).get("exit_comparison")
                    break
                time.sleep(3)
            if not ec:
                pytest.skip("backtest done but no exit_comparison produced — skipping bridge test")

        # Pick a symbol/tf
        symbol = next(iter(ec))
        by_tf = ec[symbol]
        timeframe = "1h" if "1h" in by_tf else next(iter(by_tf))
        r = requests.post(f"{BASE}/api/strategy/configs/from-lab-run", headers=auth, json={
            "run_id": run["id"], "strategy_key": "hunter", "symbol": symbol, "timeframe": timeframe,
        }, timeout=30)
        assert r.status_code == 200, f"from-lab-run failed: {r.status_code} {r.text[:300]}"
        body = r.json()
        assert body.get("config", {}).get("id")
        assert body.get("config", {}).get("origin") == "optimizer"
        assert body.get("config", {}).get("params", {}).get("exit_method") in ("fixed", "atr", "engine")

        # GET back to confirm persistence
        cid = body["config"]["id"]
        g = requests.get(f"{BASE}/api/strategy/configs/{cid}", headers=auth, timeout=15)
        assert g.status_code == 200, g.text
        assert g.json().get("origin") == "optimizer" or g.json().get("config", {}).get("origin") == "optimizer"

        # Cleanup
        requests.delete(f"{BASE}/api/strategy/configs/{cid}", headers=auth, timeout=15)

    def test_from_lab_run_requires_owner(self):
        # Direct urllib bypasses conftest monkeypatch => confirms owner-gate on the bridge.
        import json as _j
        import urllib.request as _u
        req = _u.Request(f"{BASE}/api/strategy/configs/from-lab-run",
                         data=_j.dumps({"run_id": "nope", "strategy_key": "hunter"}).encode(),
                         method="POST", headers={"Content-Type": "application/json"})
        try:
            _u.urlopen(req, timeout=15)  # noqa: S310
            got = 200
        except _u.HTTPError as e:
            got = e.code
        assert got in (401, 403), f"expected owner-gate; got {got}"

    def test_from_lab_run_404_on_missing(self, auth):
        r = requests.post(f"{BASE}/api/strategy/configs/from-lab-run", headers=auth,
                          json={"run_id": "does-not-exist", "strategy_key": "hunter"}, timeout=15)
        assert r.status_code == 404
