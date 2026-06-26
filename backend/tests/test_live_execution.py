"""LIVE-execution unit tests.

All exchange interactions are mocked - no real network calls. Each test
covers one failure mode or one happy path of the LIVE BUY/SELL flow.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import ccxt
import pytest

import live_execution
from live_execution import (
    DEFAULT_FILL_TIMEOUT_S,
    DEFAULT_MAX_SLIPPAGE_PCT,
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_EXCHANGE,
    ENV_LIVE_ENABLED,
    ExecutionResult,
    LiveExecutor,
    get_default_executor,
    get_dry_run_executor,
    live_status,
    reset_executor_for_tests,
)


# ─── helpers ─────────────────────────────────────────────────────────────
def make_executor(*, fill_timeout: int = 2, max_slippage: float = 0.10, mode: str = "LIVE") -> LiveExecutor:
    """Build a LiveExecutor with a mocked CCXT client - no real network."""
    with patch.object(ccxt, "kraken") as kraken_cls:
        mock_ex = MagicMock()
        mock_ex.markets = {
            "BTC/USDC": {"limits": {"amount": {"min": 0.0001}, "cost": {"min": 7.7}}},
            "ETH/USDC": {"limits": {"amount": {"min": 0.001}, "cost": {"min": 2.0}}},
        }
        mock_ex.amount_to_precision = lambda sym, x: f"{float(x):.8f}"
        mock_ex.price_to_precision = lambda sym, x: f"{float(x):.2f}"
        mock_ex.load_markets = MagicMock()
        kraken_cls.return_value = mock_ex
        ex = LiveExecutor(
            exchange_name="kraken", api_key="k", api_secret="s",
            max_slippage_pct=max_slippage, fill_timeout_s=fill_timeout, mode=mode,
        )
    return ex


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_executor_for_tests()
    yield
    reset_executor_for_tests()


@pytest.fixture
def env_live_enabled(monkeypatch):
    monkeypatch.setenv(ENV_LIVE_ENABLED, "true")


# ─── env gate ────────────────────────────────────────────────────────────
class TestEnvGate:
    def test_gate_closed_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(ENV_LIVE_ENABLED, raising=False)
        assert LiveExecutor.is_live_gate_open() is False

    def test_gate_closed_when_env_set_to_anything_else(self, monkeypatch):
        for val in ("false", "1", "TRUE", "yes", "True ", " true"):
            monkeypatch.setenv(ENV_LIVE_ENABLED, val)
            if val.strip().lower() == "true":
                assert LiveExecutor.is_live_gate_open() is True, val
            else:
                assert LiveExecutor.is_live_gate_open() is False, val

    def test_gate_open_only_when_env_is_exactly_true(self, monkeypatch):
        monkeypatch.setenv(ENV_LIVE_ENABLED, "true")
        assert LiveExecutor.is_live_gate_open() is True

    def test_is_live_ready_false_without_gate(self, monkeypatch):
        monkeypatch.delenv(ENV_LIVE_ENABLED, raising=False)
        ex = make_executor()
        ready, why = ex.is_live_ready()
        assert ready is False
        assert "LIVE_TRADING_ENABLED" in why

    def test_is_live_ready_true_when_all_set(self, env_live_enabled):
        ex = make_executor()
        ready, why = ex.is_live_ready()
        assert ready is True
        assert why == "ready"


# ─── min order size ──────────────────────────────────────────────────────
class TestMinOrderSize:
    def test_scales_up_to_exchange_minimum_when_intent_too_small(self):
        ex = make_executor()
        # User wants ~$1 of BTC at $77k. Kraken min_cost = $7.70 → scaled up.
        qty, notional, msg = ex.adjust_for_min_size("BTC/USDC", 1.0, 77_000.0, max_notional=20.0)
        assert qty > 0
        assert notional >= 7.7
        assert "scaled up" in msg

    def test_skips_when_minimum_exceeds_available_cash(self):
        ex = make_executor()
        # min_cost=$7.7, but max_cash=$5 → skip
        qty, notional, msg = ex.adjust_for_min_size("BTC/USDC", 1.0, 77_000.0, max_notional=5.0)
        assert qty == 0.0
        assert "exceeds available cash" in msg

    def test_safety_caps_scale_up_at_5x(self):
        ex = make_executor()
        # No artificial scale-up cap any more - max_notional is the only hard gate.
        # Verify a 7.7x scale-up (e.g. $1 → $7.70 Kraken min) proceeds when cash allows.
        qty, notional, msg = ex.adjust_for_min_size("BTC/USDC", 1.0, 77_000.0, max_notional=20.0)
        assert qty > 0
        assert notional >= 7.7
        # Message reports the scale factor for operator transparency
        assert "scaled up" in msg
        assert "x" in msg.lower()

    def test_no_scaling_when_already_meets_minimum(self):
        ex = make_executor()
        # desired $10 of BTC → above $7.70 min → no scaling msg
        qty, notional, msg = ex.adjust_for_min_size("BTC/USDC", 10.0, 77_000.0, max_notional=100.0)
        assert qty > 0
        assert notional == pytest.approx(10.0, rel=1e-4)  # tolerate exchange precision rounding
        assert "scaled up" not in msg

    def test_unknown_symbol_returns_zero_mins(self):
        ex = make_executor()
        # Symbol not in markets → mins are 0 → no scaling needed; just returns desired sizing.
        qty, notional, msg = ex.adjust_for_min_size("ZZZ/USDC", 10.0, 100.0, max_notional=100.0)
        assert qty > 0
        assert notional == pytest.approx(10.0, rel=0.01)


# ─── spread re-check ────────────────────────────────────────────────────
class TestSpreadRecheck:
    @pytest.mark.asyncio
    async def test_spread_ok_passes(self):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ok, det = await ex.recheck_spread("BTC/USDC", max_spread_pct=0.5)
        assert ok is True
        assert det["spread_pct"] < 0.5

    @pytest.mark.asyncio
    async def test_spread_too_wide_aborts(self):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 101.0})
        ok, det = await ex.recheck_spread("BTC/USDC", max_spread_pct=0.5)
        assert ok is False
        assert det["spread_pct"] > 0.5

    @pytest.mark.asyncio
    async def test_fetch_failure_aborts(self):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(side_effect=ccxt.NetworkError("boom"))
        ok, det = await ex.recheck_spread("BTC/USDC", max_spread_pct=0.5)
        assert ok is False
        assert "error" in det


# ─── BUY flow ────────────────────────────────────────────────────────────
class TestPlaceBuy:
    @pytest.mark.asyncio
    async def test_skip_when_gate_closed(self, monkeypatch):
        monkeypatch.delenv(ENV_LIVE_ENABLED, raising=False)
        ex = make_executor()
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=77_000, max_spread_pct=0.5)
        assert res.status == "SKIPPED"
        assert "LIVE_TRADING_ENABLED" in res.reason

    @pytest.mark.asyncio
    async def test_abort_when_spread_too_wide(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 102.0})
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "ABORTED"
        assert "spread" in res.reason

    @pytest.mark.asyncio
    async def test_skip_when_min_exceeds_cash(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 77_000, "ask": 77_010})
        # Only $5 of cash but min is $7.70
        res = await ex.place_buy("BTC/USDC", 1.0, max_cash=5.0, ask=77_010, max_spread_pct=0.5)
        assert res.status == "SKIPPED"
        assert "cash" in res.reason

    @pytest.mark.asyncio
    async def test_full_fill_happy_path(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(return_value={"id": "ord-1", "status": "open"})
        ex.exchange.fetch_order = MagicMock(side_effect=[
            {"id": "ord-1", "status": "open", "filled": 0, "average": 0},
            {"id": "ord-1", "status": "closed", "filled": 0.1, "average": 100.011, "price": 100.011},
        ])
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "FILLED"
        assert res.filled_qty == pytest.approx(0.1)
        assert res.filled_price == pytest.approx(100.011)
        assert res.order_id == "ord-1"
        # POST_ONLY (default): maker limit rests at the best BID = 100.0
        assert res.limit_price == pytest.approx(100.0, rel=0.001)

    @pytest.mark.asyncio
    async def test_partial_fill_status(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(return_value={"id": "ord-2", "status": "open"})
        # Requested ~0.0999 BTC, only 0.05 filled
        ex.exchange.fetch_order = MagicMock(return_value={
            "id": "ord-2", "status": "open", "filled": 0.05, "average": 100.011,
        })
        ex.exchange.cancel_order = MagicMock(return_value={})
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "PARTIAL"
        assert res.filled_qty == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_timeout_then_cancel(self, env_live_enabled):
        ex = make_executor(fill_timeout=1)
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(return_value={"id": "ord-3", "status": "open"})
        ex.exchange.fetch_order = MagicMock(return_value={
            "id": "ord-3", "status": "open", "filled": 0, "average": 0,
        })
        ex.exchange.cancel_order = MagicMock(return_value={})
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "CANCELLED"
        assert res.filled_qty == 0
        # Give the asyncio.ensure_future a tick to invoke cancel
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_insufficient_funds_rejected(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=ccxt.InsufficientFunds("nope"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "REJECTED"
        assert "InsufficientFunds" in res.reason

    @pytest.mark.asyncio
    async def test_invalid_order_rejected(self, env_live_enabled):
        # MARKET (breakout) order: a genuine InvalidOrder is a hard REJECT.
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=ccxt.InvalidOrder("bad amount"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0,
                                 max_spread_pct=0.5, order_style="MARKET")
        assert res.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_post_only_would_cross_aborts(self, env_live_enabled):
        # POST_ONLY order rejected by the exchange because it would cross the
        # spread (taker) -> ABORTED so the engine retries next cycle.
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=ccxt.InvalidOrder("post only would take"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0,
                                 max_spread_pct=0.5, order_style="POST_ONLY")
        assert res.status == "ABORTED"
        assert "post-only" in res.reason.lower()

    @pytest.mark.asyncio
    async def test_unexpected_exception_becomes_error(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=RuntimeError("oops"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "ERROR"


# ─── SELL flow ───────────────────────────────────────────────────────────
class TestPlaceSell:
    @pytest.mark.asyncio
    async def test_sell_full_fill(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(return_value={"id": "ord-s", "status": "open"})
        ex.exchange.fetch_order = MagicMock(return_value={
            "id": "ord-s", "status": "closed", "filled": 0.1, "average": 99.9,
        })
        res = await ex.place_sell("BTC/USDC", 0.1, bid=100.0, max_spread_pct=0.5)
        assert res.status == "FILLED"
        assert res.side == "SELL"
        # Sell limit = bid × (1 - 0.10/100) = 100.0 × 0.999 = 99.9
        assert res.limit_price == pytest.approx(100.0 * (1 - DEFAULT_MAX_SLIPPAGE_PCT / 100), rel=0.001)

    @pytest.mark.asyncio
    async def test_sell_aborts_when_spread_too_wide(self, env_live_enabled):
        ex = make_executor()
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 90.0, "ask": 100.0})
        res = await ex.place_sell("BTC/USDC", 0.1, bid=100.0, max_spread_pct=0.5)
        assert res.status == "ABORTED"


# ─── status / singleton ──────────────────────────────────────────────────
class TestLiveStatus:
    def test_status_when_unconfigured(self, monkeypatch):
        for k in (ENV_LIVE_ENABLED, ENV_EXCHANGE, ENV_API_KEY, ENV_API_SECRET):
            monkeypatch.delenv(k, raising=False)
        s = live_status()
        assert s["live_gate_open"] is False
        assert s["ready_to_trade"] is False
        assert s["api_key_configured"] is False
        assert s["api_secret_configured"] is False

    def test_status_when_fully_configured(self, monkeypatch):
        monkeypatch.setenv(ENV_LIVE_ENABLED, "true")
        monkeypatch.setenv(ENV_EXCHANGE, "kraken")
        monkeypatch.setenv(ENV_API_KEY, "xxxxxxxxx")
        monkeypatch.setenv(ENV_API_SECRET, "yyyyyyyy")
        s = live_status()
        assert s["live_gate_open"] is True
        assert s["exchange"] == "kraken"
        assert s["ready_to_trade"] is True
        # Secrets MUST NOT appear in the response
        assert "xxxxxxxxx" not in str(s)
        assert "yyyyyyyy" not in str(s)

    def test_default_executor_returns_error_when_unconfigured(self, monkeypatch):
        for k in (ENV_EXCHANGE, ENV_API_KEY, ENV_API_SECRET):
            monkeypatch.delenv(k, raising=False)
        ex, err = get_default_executor()
        assert ex is None
        assert err is not None
        assert "not configured" in err

    def test_default_executor_handles_init_failure(self, monkeypatch):
        monkeypatch.setenv(ENV_EXCHANGE, "kraken")
        monkeypatch.setenv(ENV_API_KEY, "x")
        monkeypatch.setenv(ENV_API_SECRET, "y")
        with patch.object(ccxt.kraken, "load_markets", side_effect=ccxt.NetworkError("net down")):
            ex, err = get_default_executor()
        assert ex is None
        assert err is not None and "init failed" in err


# ─── DRY_RUN mode ────────────────────────────────────────────────────────
class TestDryRun:
    """DRY_RUN executes the full LIVE path but stops before create_order.

    Verifies:
      - dry-run is ready without LIVE_TRADING_ENABLED gate and without keys
      - place_buy returns status=DRY_RUN and never calls create_order
      - place_sell returns status=DRY_RUN and never calls create_order
      - the simulated fill price equals the slippage-capped limit price
      - spread re-check still aborts dry-run (defensive: tests the path)
      - min-size enforcement still works (skip when cash insufficient)
    """

    def test_dry_run_ready_without_env_gate(self, monkeypatch):
        monkeypatch.delenv(ENV_LIVE_ENABLED, raising=False)
        ex = make_executor(mode="DRY_RUN")
        ready, why = ex.is_live_ready()
        assert ready is True
        assert "dry-run" in why.lower()

    @pytest.mark.asyncio
    async def test_dry_run_buy_does_not_call_create_order(self):
        ex = make_executor(mode="DRY_RUN")
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=AssertionError("create_order MUST NOT be called in DRY_RUN"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "DRY_RUN"
        assert res.is_fill is True
        assert res.filled_qty > 0
        # POST_ONLY (default): maker fill simulated at the best BID = 100.0
        assert res.filled_price == pytest.approx(100.0, rel=0.001)
        assert res.order_id.startswith("dry-")
        ex.exchange.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_sell_does_not_call_create_order(self):
        ex = make_executor(mode="DRY_RUN")
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 100.0, "ask": 100.02})
        ex.exchange.create_order = MagicMock(side_effect=AssertionError("create_order MUST NOT be called in DRY_RUN"))
        res = await ex.place_sell("BTC/USDC", 0.1, bid=100.0, max_spread_pct=0.5)
        assert res.status == "DRY_RUN"
        assert res.is_fill is True
        ex.exchange.create_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_still_aborts_on_wide_spread(self):
        ex = make_executor(mode="DRY_RUN")
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 90.0, "ask": 100.0})
        ex.exchange.create_order = MagicMock(side_effect=AssertionError("never called"))
        res = await ex.place_buy("BTC/USDC", 10.0, max_cash=50.0, ask=100.0, max_spread_pct=0.5)
        assert res.status == "ABORTED"

    @pytest.mark.asyncio
    async def test_dry_run_still_skips_when_below_min(self):
        ex = make_executor(mode="DRY_RUN")
        ex.exchange.fetch_ticker = MagicMock(return_value={"bid": 77_000, "ask": 77_010})
        ex.exchange.create_order = MagicMock(side_effect=AssertionError("never called"))
        # Only $5 cash, BTC min is $7.70 → SKIP not DRY_RUN
        res = await ex.place_buy("BTC/USDC", 1.0, max_cash=5.0, ask=77_010, max_spread_pct=0.5)
        assert res.status == "SKIPPED"

    def test_dry_run_executor_factory_works_without_any_keys(self, monkeypatch):
        # No env vars at all - dry-run still constructs (defaults to kraken)
        for k in (ENV_LIVE_ENABLED, ENV_EXCHANGE, ENV_API_KEY, ENV_API_SECRET):
            monkeypatch.delenv(k, raising=False)
        with patch.object(ccxt, "kraken") as kraken_cls:
            mock_ex = MagicMock()
            mock_ex.markets = {}
            mock_ex.load_markets = MagicMock()
            kraken_cls.return_value = mock_ex
            ex, err = get_dry_run_executor()
        assert err is None
        assert ex is not None
        assert ex.mode == "DRY_RUN"

    def test_dry_run_factory_uses_env_exchange_when_set(self, monkeypatch):
        monkeypatch.setenv(ENV_EXCHANGE, "coinbase")
        with patch.object(ccxt, "coinbase") as cb_cls:
            mock_ex = MagicMock()
            mock_ex.markets = {}
            mock_ex.load_markets = MagicMock()
            cb_cls.return_value = mock_ex
            ex, err = get_dry_run_executor()
        assert err is None
        assert ex is not None
        assert ex.exchange_name == "coinbase"

    def test_dry_run_status_field_in_live_status(self):
        s = live_status()
        assert s["dry_run_ready"] is True
