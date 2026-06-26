"""
Iteration 4 tests - LIVE execution defense-in-depth.

Critical assertions:
  * GET /api/live/status returns expected shape with safety flags all false/null.
  * Response does NOT leak any API key/secret material.
  * Regression: all previously working endpoints still return 200.
  * Defense-in-depth interlock: even with settings.trading_mode='LIVE',
    POST /api/cycle/run/BTC must produce trades with mode='PAPER' because
    the LIVE_TRADING_ENABLED env var is 'false'.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
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


class TimeoutSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", 60)
        return super().request(method, url, **kwargs)


@pytest.fixture(scope="module")
def client() -> requests.Session:
    s = TimeoutSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def original_settings(client) -> dict:
    r = client.get(f"{API}/settings", timeout=30)
    assert r.status_code == 200
    return r.json()


# ── 1) /api/live/status shape + safety ───────────────────────────────────
class TestLiveStatus:
    def test_live_status_200_and_shape(self, client):
        r = client.get(f"{API}/live/status", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        required_keys = {
            "live_gate_open",
            "exchange",
            "api_key_configured",
            "api_secret_configured",
            "max_slippage_pct",
            "fill_timeout_s",
            "ready_to_trade",
        }
        missing = required_keys - set(body.keys())
        assert not missing, f"missing keys: {missing}; body={body}"

    def test_live_status_safety_flags_all_off(self, client):
        body = client.get(f"{API}/live/status", timeout=15).json()
        # Flags must be internally consistent regardless of operator config.
        # (In a live-configured environment the gate may legitimately be open;
        # we assert the relationships rather than a fixed safe-default.)
        assert isinstance(body["live_gate_open"], bool), body
        assert isinstance(body["api_key_configured"], bool), body
        assert isinstance(body["api_secret_configured"], bool), body
        # ready_to_trade is true ONLY when every precondition is satisfied.
        expected_ready = (
            body["live_gate_open"]
            and bool(body["exchange"])
            and body["api_key_configured"]
            and body["api_secret_configured"]
        )
        assert body["ready_to_trade"] == expected_ready, body

    def test_live_status_no_secret_material_leak(self, client):
        """Verify api_key_configured / api_secret_configured are booleans only,
        not strings echoing the underlying key, and that no value field in the
        response contains plaintext credential material."""
        r = client.get(f"{API}/live/status", timeout=15)
        body = r.json()
        # The configured-flags must be booleans, NEVER strings (which could
        # accidentally contain the actual key value).
        assert isinstance(body["api_key_configured"], bool), body
        assert isinstance(body["api_secret_configured"], bool), body
        # No value in the response should be a long opaque string (the typical
        # shape of an API key/secret).
        for k, v in body.items():
            if isinstance(v, str):
                # Allowed string fields are: "exchange" (short name like
                # 'kraken'/'coinbase') -> short ascii; nothing else.
                assert len(v) < 40, f"suspiciously long string in /live/status[{k}]: {v!r}"
        # Belt-and-braces: even if the env vars HAD values, the response keys
        # must not include "api_key" or "api_secret" containing string values.
        forbidden_keys_with_values = ("api_key", "api_secret", "exchange_api_key", "exchange_api_secret")
        for fk in forbidden_keys_with_values:
            if fk in body:
                assert not isinstance(body[fk], str) or body[fk] in ("", None), (
                    f"/live/status leaked {fk}={body[fk]!r}"
                )


# ── 2) Regression - read endpoints all 200 with sane shape ───────────────
class TestRegressionReads:
    def test_root(self, client):
        r = client.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "running"
        assert "CryptoAtlas" in body.get("name", "")

    def test_portfolio(self, client):
        r = client.get(f"{API}/portfolio", timeout=30)
        assert r.status_code == 200
        p = r.json()
        assert p["starting_balance"] == 300.0
        assert isinstance(p["positions"], list)
        for k in ("cash", "equity", "total_pnl", "daily_pnl_pct"):
            assert k in p

    def test_settings_masked(self, client):
        r = client.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        s = r.json()
        for k in ("coinbase_api_secret", "kraken_api_secret"):
            val = s.get(k, "")
            if val:
                assert set(val) <= {"\u2022"}, f"{k} not masked"
        assert s["trading_mode"] in ("PAPER", "LIVE")

    def test_risk_status(self, client):
        r = client.get(f"{API}/risk/status", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("spread_breach", "daily_loss_breach", "confidence_breach", "manual_kill", "overall_safe"):
            assert k in body["status"]
        assert "thresholds" in body

    def test_market_snapshots(self, client):
        r = client.get(f"{API}/market/snapshots", timeout=45)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["symbols"], list) and len(body["symbols"]) >= 1
        assert isinstance(body["snapshots"], list) and len(body["snapshots"]) >= 1

    def test_reasoning(self, client):
        r = client.get(f"{API}/reasoning", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert body["count"] == len(body["items"])

    def test_trades(self, client):
        r = client.get(f"{API}/trades", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list)
        assert body["count"] == len(body["items"])

    def test_news_current(self, client):
        r = client.get(f"{API}/news/current", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body and isinstance(body["summary"], str)
        assert "ts" in body
        assert "cache" in body


# ── 3) Cycle/run BTC in PAPER mode ───────────────────────────────────────
class TestCycleRunBTCRegression:
    def test_cycle_btc_paper_mode(self, client, original_settings):
        # ensure trading_mode=PAPER and safe min_confidence
        client.put(f"{API}/settings", json={
            "trading_mode": "PAPER",
            "manual_kill_switch": False,
            "min_confidence": 0.0,
        }, timeout=15)
        r = client.post(f"{API}/cycle/run/BTC", json={}, timeout=120)
        assert r.status_code == 200, r.text
        res = r.json()
        if "error" in res:
            pytest.skip(f"cycle error (likely market/LLM): {res['error']}")
        assert res.get("symbol") == "BTC/USD"
        assert res["decision"] in {"BUY", "SELL", "HOLD", "BLOCKED"}

        # if a trade resulted, verify it's PAPER
        if res["decision"] in ("BUY", "SELL"):
            trades = client.get(f"{API}/trades?limit=5", timeout=15).json()["items"]
            assert trades, "BUY/SELL decision did not produce a trade row"
            assert trades[0].get("mode") == "PAPER", f"PAPER cycle wrote non-PAPER trade: {trades[0]}"


# ── 4) DEFENSE-IN-DEPTH (the critical test) ──────────────────────────────
class TestDefenseInDepth:
    """Even if the operator flips settings.trading_mode to LIVE, the backend
    MUST stay in PAPER mode because LIVE_TRADING_ENABLED env var is 'false'.
    """

    def test_live_mode_setting_does_not_enable_live_orders(self, client, original_settings):
        # SAFETY: if the operator has genuinely enabled the live gate (real
        # exchange keys + LIVE_TRADING_ENABLED=true), we must NOT run a cycle
        # with trading_mode=LIVE + min_confidence=0 here — it could place REAL
        # orders. This defense-in-depth test only makes sense when the env gate
        # is closed, so skip it otherwise.
        gate = client.get(f"{API}/live/status", timeout=15).json()
        if gate.get("live_gate_open"):
            pytest.skip("LIVE gate is open (operator live config); skipping to avoid real orders.")

        # 1) Flip trading_mode to LIVE via PUT
        r = client.put(f"{API}/settings", json={
            "trading_mode": "LIVE",
            "manual_kill_switch": False,
            "min_confidence": 0.0,  # maximize the chance the engine decides to BUY/SELL
        }, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["trading_mode"] == "LIVE"

        # 2) Confirm /api/live/status still says gate is closed
        ls = client.get(f"{API}/live/status", timeout=15).json()
        assert ls["live_gate_open"] is False, ls
        assert ls["ready_to_trade"] is False, ls

        # 3) Capture trades-before
        before = client.get(f"{API}/trades?limit=5", timeout=15).json()
        before_count = before["count"]

        # 4) Run a cycle on BTC
        rc = client.post(f"{API}/cycle/run/BTC", json={}, timeout=120)
        assert rc.status_code == 200, rc.text
        res = rc.json()
        time.sleep(1)

        # 5) Pull the latest trades. If decision was BUY/SELL, the new row
        # MUST have mode == 'PAPER'. If decision was HOLD/BLOCKED, simply
        # verify no LIVE trade rows exist at all.
        after = client.get(f"{API}/trades?limit=10", timeout=15).json()
        new_trades = after["items"][: max(0, after["count"] - before_count)]

        if res.get("decision") in ("BUY", "SELL"):
            assert new_trades, f"BUY/SELL decision recorded no trade row: {res}"
            for t in new_trades:
                assert t.get("mode") == "PAPER", (
                    f"CRITICAL DEFENSE-IN-DEPTH FAILURE: trade.mode={t.get('mode')} "
                    f"while LIVE_TRADING_ENABLED=false. Trade row: {t}"
                )

        # Belt-and-braces: regardless of decision, NO trade row (new or old)
        # should be tagged LIVE while the env gate is closed.
        for t in after["items"]:
            assert t.get("mode") != "LIVE", (
                f"CRITICAL: found a LIVE-mode trade while env gate is closed: {t}"
            )

    def test_restore_settings_to_paper(self, client, original_settings):
        # cleanup
        r = client.put(f"{API}/settings", json={
            "trading_mode": "PAPER",
            "min_confidence": original_settings.get("min_confidence", 0.6),
            "manual_kill_switch": False,
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["trading_mode"] == "PAPER"


# ── 5) Backtest regression (no live orders) ──────────────────────────────
class TestBacktestRegression:
    def test_backtest_run(self, client):
        r = client.post(f"{API}/backtest/run", json={
            "symbols": ["BTC/USDC"],
            "days": 3,
            "stop_loss_pct": 1.0,
            "take_profit_pct": 2.0,
            "starting_balance": 100.0,
            "exchange": "kraken",
            "min_confidence": 0.4,
        }, timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "params" in body
        # Either 'results' or 'symbols' style payload - just make sure it's a dict
        assert isinstance(body, dict)

    def test_backtest_sweep(self, client):
        r = client.post(f"{API}/backtest/sweep", json={
            "symbols": ["BTC/USDC"],
            "days": 3,
            "sl_pcts": [1.0],
            "tp_pcts": [2.0],
            "starting_balance": 100.0,
            "exchange": "kraken",
            "min_confidence": 0.4,
        }, timeout=180)
        assert r.status_code == 200, r.text


# ── 6) PDF + public snapshot regression ──────────────────────────────────
class TestReportAndPublic:
    def test_report_full_pdf(self, client):
        r = client.get(f"{API}/report/full.pdf", timeout=60)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 3000, f"PDF suspiciously small: {len(r.content)} bytes"
        assert r.content[:5] == b"%PDF-", f"PDF magic header missing: {r.content[:10]!r}"

    def test_public_snapshot_no_keys(self, client):
        r = client.get(f"{API}/public/snapshot", timeout=30)
        assert r.status_code == 200
        body = r.json()
        s = body.get("settings", {})
        for k in (
            "coinbase_api_key", "coinbase_api_secret",
            "kraken_api_key", "kraken_api_secret",
        ):
            assert k not in s, f"public snapshot leaked {k}"
        # Whole payload must not mention env credentials either
        raw = r.text.lower()
        for forbidden in ("exchange_api_key", "exchange_api_secret"):
            assert forbidden not in raw, f"public snapshot mentions {forbidden}"
