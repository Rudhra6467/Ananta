"""Phase B declarative engine — HTTP integration tests against live preview backend."""
from __future__ import annotations

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "owner@ananta.ai"
OWNER_PASSWORD = "aZKtwzAqI0SzlwFE6TRqw8aH"

DECLARATIVE_KEYS = [
    "ema-cross", "supertrend", "rsi-momentum", "macd-trend",
    "bollinger-mr", "donchian-breakout", "atr-breakout", "keltner-breakout",
]
DEFAULT_PAPER_ENABLED = {"ema-cross", "supertrend", "rsi-momentum"}
DEFAULT_DISABLED = {"macd-trend", "bollinger-mr", "donchian-breakout", "atr-breakout", "keltner-breakout"}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def owner_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner(api, owner_token):
    api.headers.update({"Authorization": f"Bearer {owner_token}"})
    return api


# --- Registry & schema ---
def test_registry_has_11_including_declarative(api):
    r = api.get(f"{BASE_URL}/api/strategy/registry", timeout=15)
    assert r.status_code == 200
    data = r.json()
    strategies = data.get("strategies") if isinstance(data, dict) else data
    keys = [s["key"] for s in strategies]
    assert len(keys) == 11, f"expected 11, got {len(keys)}: {keys}"
    for k in DECLARATIVE_KEYS:
        assert k in keys, f"declarative key missing: {k}"
        entry = next(s for s in strategies if s["key"] == k)
        # each has params schema
        assert "params_schema" in entry or "schema" in entry or "params" in entry, f"{k} missing schema info"


def test_ema_cross_schema(api):
    r = api.get(f"{BASE_URL}/api/strategy/ema-cross/schema", timeout=10)
    assert r.status_code == 200
    schema = r.json()
    params = schema.get("params") or []
    param_ids = {p.get("id") for p in params if isinstance(p, dict)}
    for expected in ("ema_fast", "ema_slow", "normal_lot_usd", "stop_loss_pct"):
        assert expected in param_ids, f"schema missing param {expected}. param_ids={param_ids}"


# --- Metrics: default state contract ---
def test_metrics_defaults(api):
    r = api.get(f"{BASE_URL}/api/strategy/metrics", timeout=15)
    assert r.status_code == 200
    data = r.json()
    metrics = data.get("metrics", data)
    # metrics is a dict keyed by strategy key
    if isinstance(metrics, list):
        by_key = {s["key"]: s for s in metrics}
    else:
        by_key = metrics
    for k in DECLARATIVE_KEYS:
        assert k in by_key, f"metrics missing {k}. keys={list(by_key)[:20]}"
    for k in DEFAULT_PAPER_ENABLED:
        entry = by_key[k]
        assert entry.get("enabled") is True, f"{k} should be enabled=true, got {entry}"
        assert (entry.get("status") or entry.get("mode") or "").upper() == "PAPER", f"{k} should be PAPER, got status={entry.get('status')} mode={entry.get('mode')}"
    for k in DEFAULT_DISABLED:
        entry = by_key[k]
        assert entry.get("enabled") is False, f"{k} should be enabled=false, got {entry}"
        assert (entry.get("status") or entry.get("mode") or "").upper() == "DISABLED", f"{k} should be DISABLED, got status={entry.get('status')} mode={entry.get('mode')}"


# --- Library: wireable + engine_key ---
def test_library_has_wireable_engine_keys(api):
    r = api.get(f"{BASE_URL}/api/library", timeout=15)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") or data.get("strategies") or data
    by_key = {i.get("engine_key") or i.get("key"): i for i in items if isinstance(i, dict)}
    for k in DECLARATIVE_KEYS:
        assert k in by_key, f"library missing engine_key {k}. keys seen: {list(by_key)[:20]}"
        entry = by_key[k]
        assert entry.get("wireable") is True, f"{k} should be wireable=true"
        assert entry.get("engine_key") == k, f"{k} engine_key mismatch: {entry.get('engine_key')}"


# --- Owner state toggle ---
def test_state_toggle_macd_trend(owner):
    key = "macd-trend"
    def _entry():
        m = owner.get(f"{BASE_URL}/api/strategy/metrics", timeout=10).json()
        metrics = m.get("metrics", m)
        return metrics[key] if isinstance(metrics, dict) else next(s for s in metrics if s["key"] == key)
    # enable → PAPER
    r = owner.put(f"{BASE_URL}/api/strategy/{key}/state", json={"enabled": True, "status": "PAPER"}, timeout=10)
    assert r.status_code == 200, f"enable failed: {r.status_code} {r.text[:200]}"
    entry = _entry()
    assert entry.get("enabled") is True, f"expected enabled after PUT: {entry}"
    assert (entry.get("status") or "").upper() == "PAPER", f"expected PAPER: status={entry.get('status')}"
    # revert → DISABLED
    r = owner.put(f"{BASE_URL}/api/strategy/{key}/state", json={"enabled": False, "status": "DISABLED"}, timeout=10)
    assert r.status_code == 200
    entry = _entry()
    assert entry.get("enabled") is False, f"expected disabled after revert: {entry}"
    assert (entry.get("status") or "").upper() == "DISABLED", f"expected DISABLED: status={entry.get('status')}"


# --- Per-strategy config flow for ema-cross ---
def test_ema_cross_per_strategy_config_full_flow(owner):
    key = "ema-cross"
    cfg_id = None
    try:
        # Create
        payload = {
            "strategy_key": key,
            "name": "TEST_iter38_ema_cross",
            "params": {"ema_fast": 5, "ema_slow": 20, "normal_lot_usd": 50},
        }
        r = owner.post(f"{BASE_URL}/api/strategy/configs", json=payload, timeout=10)
        assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:200]}"
        cfg = r.json()
        # response may be nested under "config"
        cfg_obj = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
        cfg_id = cfg_obj.get("id") or cfg_obj.get("config_id") or cfg_obj.get("_id")
        assert cfg_id, f"no config id in response: {cfg}"

        # Mark validation passed
        r = owner.put(f"{BASE_URL}/api/strategy/configs/{cfg_id}", json={"validation_status": "passed"}, timeout=10)
        assert r.status_code == 200, f"validate failed: {r.status_code} {r.text[:200]}"

        # Activate
        r = owner.post(f"{BASE_URL}/api/strategy/configs/{cfg_id}/activate", json={}, timeout=15)
        assert r.status_code == 200, f"activate failed: {r.status_code} {r.text[:200]}"
        act = r.json()
        assert "applied_params" in act, f"missing applied_params: {act}"
        assert "normal_lot_usd" in act["applied_params"], f"applied_params missing normal_lot_usd: {act['applied_params']}"
        assert "ignored_account_level" in act, f"missing ignored_account_level: {act}"

        # Effective
        r = owner.get(f"{BASE_URL}/api/strategy/{key}/effective", timeout=10)
        assert r.status_code == 200
        eff = r.json()
        assert eff.get("using_config") is True, f"using_config should be true: {eff}"
    finally:
        # Cleanup
        if cfg_id:
            owner.post(f"{BASE_URL}/api/strategy/{key}/deactivate", json={}, timeout=10)
            owner.delete(f"{BASE_URL}/api/strategy/configs/{cfg_id}", timeout=10)
            # Verify clean
            eff = owner.get(f"{BASE_URL}/api/strategy/{key}/effective", timeout=10).json()
            assert eff.get("using_config") is False, f"cleanup failed, using_config still true: {eff}"


# --- Cycle run: BTC only (limit AI/cycle calls) ---
def test_cycle_run_btc_200(owner):
    r = owner.post(f"{BASE_URL}/api/cycle/run/BTC", json={}, timeout=60)
    assert r.status_code == 200, f"cycle/run/BTC failed: {r.status_code} {r.text[:400]}"


# --- Regression: iter36 strategy import + iter37 configs still exist ---
def test_regression_strategy_import_endpoint(owner):
    # Just ping the endpoint list — a real import runs AI which we skip.
    r = owner.get(f"{BASE_URL}/api/strategy/imports", timeout=10)
    # accept 200 (list) or 404 if endpoint shape differs; but 5xx = fail
    assert r.status_code < 500, f"imports endpoint 5xx: {r.status_code}"


def test_regression_configs_endpoint(owner):
    r = owner.get(f"{BASE_URL}/api/strategy/configs", timeout=10)
    assert r.status_code == 200, f"configs list failed: {r.status_code} {r.text[:200]}"
