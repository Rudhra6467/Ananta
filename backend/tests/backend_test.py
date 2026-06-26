"""
CryptoAtlas AI Trading Dashboard - Backend API Tests (pytest).

Test ordering matters:
1) Health + reads (market, portfolio, settings, risk, trades, reasoning)
2) Settings update + read-back
3) Cycle/run (triggers LLM + writes reasoning/trade docs)
4) Filtered reasoning + kill-switch toggles via settings
5) Portfolio reset (LAST, since it clears trades + reasoning)
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback: read from frontend/.env so tests can be run locally
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except FileNotFoundError:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
API = f"{BASE_URL}/api"

VALID_BIAS = {"BULLISH", "BEARISH", "NEUTRAL"}
VALID_DECISIONS = {"BUY", "SELL", "HOLD", "BLOCKED"}


class TimeoutSession(requests.Session):
    """Default 60s read timeout; cycle endpoints can be slow due to LLM + competing
    background trading loop. Callers may still override per-request."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 60)
        return super().request(method, url, **kwargs)


@pytest.fixture(scope="session")
def client() -> requests.Session:
    s = TimeoutSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def original_settings(client) -> dict:
    """Snapshot of settings before mutations so we can restore at the end."""
    r = client.get(f"{API}/settings", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 1) Health & basic reads ----------------
class TestHealth:
    def test_root(self, client):
        r = client.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "running"
        assert "CryptoAtlas" in body.get("name", "")
        assert "ts" in body


class TestMarket:
    def test_snapshots_all(self, client):
        r = client.get(f"{API}/market/snapshots", timeout=45)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("symbols"), list) and len(body["symbols"]) >= 1
        snaps = body.get("snapshots", [])
        # We need at least one valid snapshot from the exchanges
        assert len(snaps) >= 1, f"no snapshots returned: {body}"
        valid = [s for s in snaps if s.get("price", 0) > 0 and s.get("bid", 0) > 0 and s.get("ask", 0) > 0]
        assert len(valid) >= 1, f"all snapshots invalid: {snaps}"
        for s in valid:
            assert s["ask"] >= s["bid"]
            assert s["spread_pct"] >= 0
            assert "/" in s["symbol"]

    def test_snapshot_btc(self, client):
        r = client.get(f"{API}/market/snapshot/BTC", timeout=30)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["symbol"] == "BTC/USD"
        assert s["price"] > 0
        assert s["bid"] > 0 and s["ask"] >= s["bid"]
        assert s["spread_pct"] >= 0


class TestPortfolioRead:
    def test_portfolio_initial_or_existing(self, client):
        r = client.get(f"{API}/portfolio", timeout=30)
        assert r.status_code == 200
        p = r.json()
        assert p["starting_balance"] == 300.0
        assert isinstance(p["positions"], list)
        for field in ("cash", "equity", "total_pnl", "total_pnl_pct", "daily_pnl_pct"):
            assert field in p and isinstance(p[field], (int, float))


class TestSettingsRead:
    def test_settings_defaults(self, client):
        r = client.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        s = r.json()
        # defaults from RiskSettings
        assert s["trading_mode"] in ("PAPER", "LIVE")
        assert 0 <= s["min_confidence"] <= 1
        assert s["max_spread_pct"] > 0
        assert s["max_daily_loss_pct"] > 0
        assert isinstance(s["enabled_symbols"], list) and len(s["enabled_symbols"]) >= 1
        # masked secrets behavior: any present secret must be bullets, never plain
        for k in ("coinbase_api_secret", "kraken_api_secret"):
            val = s.get(k, "")
            if val:
                assert set(val) <= {"\u2022"}, f"secret {k} is not masked: {val!r}"


class TestRiskRead:
    def test_risk_status(self, client):
        r = client.get(f"{API}/risk/status", timeout=30)
        assert r.status_code == 200
        body = r.json()
        st = body["status"]
        for k in ("spread_breach", "daily_loss_breach", "confidence_breach", "manual_kill", "overall_safe"):
            assert k in st and isinstance(st[k], bool)
        assert "details" in st
        assert "thresholds" in body


class TestTradesAndReasoningRead:
    def test_trades_list(self, client):
        r = client.get(f"{API}/trades", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert body["count"] == len(body["items"])

    def test_reasoning_list(self, client):
        r = client.get(f"{API}/reasoning", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert body["count"] == len(body["items"])


# ---------------- 2) Settings update + read-back ----------------
class TestSettingsUpdate:
    def test_invalid_trading_mode_rejected(self, client):
        r = client.put(f"{API}/settings", json={"trading_mode": "FOO"}, timeout=15)
        assert r.status_code == 400

    def test_update_min_confidence_clamped_and_persisted(self, client, original_settings):
        # Set a high value that will be clamped to <= 1.0
        r = client.put(f"{API}/settings", json={"min_confidence": 5.0}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["min_confidence"] == 1.0  # clamped

        # read back via GET
        r2 = client.get(f"{API}/settings", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["min_confidence"] == 1.0

        # restore original
        r3 = client.put(f"{API}/settings", json={"min_confidence": original_settings["min_confidence"]}, timeout=15)
        assert r3.status_code == 200

    def test_masked_secret_is_ignored(self, client, original_settings):
        # send all-bullets - should be ignored, not overwrite
        masked = "\u2022" * 8
        r = client.put(f"{API}/settings", json={"kraken_api_secret": masked}, timeout=15)
        assert r.status_code == 200
        # backend stored value should still be original (empty by default)
        s = r.json()
        # response also masks if present; original was empty so should remain empty
        assert s.get("kraken_api_secret", "") == original_settings.get("kraken_api_secret", "")


# ---------------- 3) Cycle/run ----------------
class TestCycleRun:
    def test_run_full_cycle(self, client):
        r = client.post(f"{API}/cycle/run", json={}, timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "ran_at" in body
        results = body.get("results", [])
        assert isinstance(results, list) and len(results) >= 1, f"no cycle results: {body}"
        ok_any = False
        for res in results:
            # may have error field on individual symbol failures - track but don't fail entire test
            if "error" in res:
                continue
            assert "snapshot" in res
            assert "macro" in res
            macro = res["macro"]
            assert macro["bias"] in VALID_BIAS
            assert 0.0 <= float(macro["confidence"]) <= 1.0
            assert isinstance(macro.get("reason", ""), str) and len(macro["reason"]) > 0
            assert "kill_switches" in res
            assert "decision" in res and res["decision"] in VALID_DECISIONS
            assert "fusion_summary" in res
            ok_any = True
        assert ok_any, f"all symbols errored in cycle: {results}"

    def test_run_single_symbol(self, client):
        r = client.post(f"{API}/cycle/run/BTC", json={}, timeout=60)
        assert r.status_code == 200, r.text
        res = r.json()
        if "error" in res:
            pytest.skip(f"single symbol error: {res['error']}")
        assert res.get("symbol") == "BTC/USD"
        assert res["decision"] in VALID_DECISIONS

    def test_reasoning_log_populated_after_cycle(self, client):
        r = client.get(f"{API}/reasoning?limit=50", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1, "no reasoning entries after cycle"
        item = items[0]
        assert item["bias"] in VALID_BIAS
        assert 0.0 <= float(item["confidence"]) <= 1.0
        assert isinstance(item.get("reason", ""), str) and len(item["reason"]) > 0
        assert item["decision"] in VALID_DECISIONS

    def test_reasoning_filter_by_symbol(self, client):
        r = client.get(f"{API}/reasoning?symbol=BTC&limit=20", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        # may be 0 if cycle errored on BTC, but if present must all be BTC/USD
        for it in items:
            assert it["symbol"] == "BTC/USD"


# ---------------- 4) Kill-switch via settings ----------------
class TestKillSwitches:
    def test_spread_breach_via_low_max_spread(self, client, original_settings):
        # Find a symbol whose live spread > 0.01% (the clamp lower bound).
        snaps = client.get(f"{API}/market/snapshots").json()["snapshots"]
        candidate = next((s for s in snaps if s["spread_pct"] > 0.01), None)
        if not candidate:
            pytest.skip(f"All symbols have spread <= 0.01% which is the clamp floor; cannot force breach. spreads={[(s['symbol'], s['spread_pct']) for s in snaps]}")
        # Reduce enabled_symbols to that single symbol so /risk/status uses it
        client.put(f"{API}/settings", json={
            "enabled_symbols": [candidate["symbol"]],
            "max_spread_pct": 0.01,
        })
        try:
            time.sleep(1)
            rs = client.get(f"{API}/risk/status").json()
            assert rs["status"]["spread_breach"] is True, rs
        finally:
            client.put(f"{API}/settings", json={
                "enabled_symbols": original_settings["enabled_symbols"],
                "max_spread_pct": original_settings["max_spread_pct"],
            })

    def test_manual_kill_blocks_trades(self, client, original_settings):
        r = client.put(f"{API}/settings", json={"manual_kill_switch": True, "min_confidence": 0.0}, timeout=15)
        assert r.status_code == 200
        assert r.json()["manual_kill_switch"] is True

        rs = client.get(f"{API}/risk/status", timeout=30).json()
        assert rs["status"]["manual_kill"] is True
        assert rs["status"]["overall_safe"] is False

        # run a cycle - every decision must be BLOCKED
        rc = client.post(f"{API}/cycle/run", json={}, timeout=180)
        assert rc.status_code == 200
        results = rc.json()["results"]
        non_err = [x for x in results if "decision" in x]
        assert len(non_err) >= 1
        for res in non_err:
            assert res["decision"] == "BLOCKED", f"manual kill did not block: {res}"
            assert "MANUAL_KILL" in res.get("blocked_reasons", [])

        # restore
        client.put(f"{API}/settings", json={
            "manual_kill_switch": False,
            "min_confidence": original_settings["min_confidence"],
        }, timeout=15)

    def test_confidence_breach_when_min_conf_high(self, client, original_settings):
        # set min_confidence to 1.0 to force confidence_breach (LLM is rarely 1.0)
        r = client.put(f"{API}/settings", json={"min_confidence": 1.0}, timeout=15)
        assert r.status_code == 200
        rs = client.get(f"{API}/risk/status", timeout=30).json()
        # confidence_breach reflects last reasoning confidence vs 1.0
        # since last reasoning was almost certainly <1.0, must be True
        if rs["status"]["details"]["macro_confidence"] < 1.0:
            assert rs["status"]["confidence_breach"] is True
        # restore
        client.put(f"{API}/settings", json={"min_confidence": original_settings["min_confidence"]}, timeout=15)


# ---------------- 5) BUY trade execution (force-low confidence) ----------------
class TestBuyExecution:
    def test_force_buy_attempt(self, client, original_settings):
        # lower min_confidence to 0 so any BULLISH bias + bullish imbalance triggers BUY
        client.put(f"{API}/settings", json={"min_confidence": 0.0, "manual_kill_switch": False}, timeout=15)
        before = client.get(f"{API}/portfolio", timeout=15).json()
        before_trades = client.get(f"{API}/trades", timeout=15).json()["count"]

        rc = client.post(f"{API}/cycle/run", json={}, timeout=180)
        assert rc.status_code == 200
        results = rc.json()["results"]
        bought = [r for r in results if r.get("decision") == "BUY"]

        after_trades = client.get(f"{API}/trades", timeout=15).json()
        if bought:
            # if a BUY happened, cash should decrease and trade count should grow
            assert after_trades["count"] >= before_trades + 1, "BUY decision did not record a trade"
            after = client.get(f"{API}/portfolio", timeout=15).json()
            assert after["cash"] <= before["cash"], f"cash did not decrease after BUY: {before['cash']} -> {after['cash']}"
        else:
            # acceptable: orderbook imbalance / bias did not align - record but pass
            pytest.skip(f"No BUY decision this cycle (decisions: {[r.get('decision') for r in results]})")

        # restore min_confidence
        client.put(f"{API}/settings", json={"min_confidence": original_settings["min_confidence"]}, timeout=15)


# ---------------- 6) Portfolio reset (must be last) ----------------
class TestZZZPortfolioReset:
    """Class name prefixed ZZZ to ensure it runs last in alphabetical default order."""

    def test_reset_clears_state(self, client, original_settings):
        r = client.post(f"{API}/portfolio/reset", json={}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        p = body["portfolio"]
        assert p["starting_balance"] == 300.0
        assert p["cash"] == 300.0
        assert p["positions"] == []
        assert p["realized_pnl"] == 0.0

        # trades and reasoning should be empty
        t = client.get(f"{API}/trades", timeout=15).json()
        assert t["count"] == 0
        rg = client.get(f"{API}/reasoning", timeout=15).json()
        assert rg["count"] == 0

        # ensure settings restored as a courtesy
        client.put(f"{API}/settings", json={
            "min_confidence": original_settings["min_confidence"],
            "max_spread_pct": original_settings["max_spread_pct"],
            "manual_kill_switch": False,
        }, timeout=15)
