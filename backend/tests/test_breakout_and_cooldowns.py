"""Tests for Phase: Systemic Breakout Filter + Symmetric Cooldowns + LLM cache."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from ai_reasoning import MacroBias, analyze_macro, clear_macro_cache
from breakout_classifier import detect_breakout
from models import Position, RiskSettings, MarketSnapshot
from position_watcher import EXIT_SL, EXIT_TRAIL, evaluate_exit


# ---------- helpers ----------
def _bars(n=50, base_vol=1.0, spike_vol=None):
    """Build OHLCV bars. By default flat-ish; pass spike_vol to amplify last bar."""
    bars = []
    for i in range(n):
        v = base_vol if (spike_vol is None or i < n - 1) else spike_vol
        bars.append([float(i * 3600 * 1000), 100.0, 100.5, 99.5, 100.0, v])
    return bars


# ---------- 1) Breakout classifier ----------
def test_breakout_fires_when_all_three_legs_met():
    bars = _bars(20, base_vol=1.0, spike_vol=10.0)  # last bar 10x volume
    is_b, ev = detect_breakout(bars, "BULLISH", 0.90, spread_pct=0.10)
    assert is_b is True
    assert ev["macro_ok"] and ev["volume_ok"] and ev["spread_ok"]


def test_breakout_blocked_when_confidence_low():
    bars = _bars(20, base_vol=1.0, spike_vol=10.0)
    is_b, ev = detect_breakout(bars, "BULLISH", 0.70, spread_pct=0.10)
    assert is_b is False
    assert ev["macro_ok"] is False


def test_breakout_blocked_when_spread_wide():
    bars = _bars(20, base_vol=1.0, spike_vol=10.0)
    is_b, ev = detect_breakout(bars, "BULLISH", 0.90, spread_pct=0.35)
    assert is_b is False
    assert ev["spread_ok"] is False


def test_breakout_blocked_when_volume_calm():
    bars = _bars(20, base_vol=5.0, spike_vol=0.5)  # last bar BELOW average -> low percentile
    is_b, ev = detect_breakout(bars, "BULLISH", 0.90, spread_pct=0.10)
    assert is_b is False
    assert ev["volume_ok"] is False


def test_breakout_blocked_when_history_too_short():
    bars = _bars(5)  # less than 14 needed
    is_b, ev = detect_breakout(bars, "BULLISH", 0.90, spread_pct=0.10)
    assert is_b is False
    assert "need >= 14" in ev["reason"]


# ---------- 2) Position-level trail overrides for breakout mode ----------
def _snap(price=100.0, imb=0.0):
    return MarketSnapshot(
        symbol="BTC/USD", price=price, bid=price - 0.05, ask=price + 0.05,
        spread_pct=0.1, orderbook_imbalance=imb, exchange="kraken",
    )


def test_watcher_uses_breakout_trail_params_for_breakout_position():
    """A non-breakout pos at +3% peak with 0.6% trail would EXIT_TRAIL.
    A breakout pos at the same state should NOT exit (needs +6% peak)."""
    settings = RiskSettings(
        trail_arm_pct=2.5, trail_distance_pct=0.6,
        breakout_trail_arm_pct=6.0, breakout_trail_distance_pct=2.0,
        stop_loss_pct=10.0, micro_flip_cooldown_seconds=0,
    )
    # peak hit +3% (103), now at 102.4 -> -0.58% from peak (above 0.6% threshold)
    normal_pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0,
                          peak_price=103.0, entry_timestamp="2020-01-01T00:00:00+00:00")
    reason_n, _ = evaluate_exit(normal_pos, _snap(price=102.38), settings)
    assert reason_n == EXIT_TRAIL  # normal trail fires

    breakout_pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0,
                            peak_price=103.0, entry_timestamp="2020-01-01T00:00:00+00:00",
                            breakout_mode=True)
    reason_b, details = evaluate_exit(breakout_pos, _snap(price=102.38), settings)
    assert reason_b is None  # arm not met for breakout (needs +6%)
    assert details["trail_arm_pct"] == 6.0
    assert details["trail_distance_pct"] == 2.0


def test_breakout_position_trail_exits_at_wider_threshold():
    settings = RiskSettings(
        breakout_trail_arm_pct=6.0, breakout_trail_distance_pct=2.0,
        stop_loss_pct=10.0, micro_flip_cooldown_seconds=0,
    )
    # peak +7% (107), pulled back to 104.85 -> -2.01% from peak (> 2.0% distance)
    pos = Position(symbol="BTC/USD", quantity=0.1, avg_cost=100.0,
                   peak_price=107.0, entry_timestamp="2020-01-01T00:00:00+00:00",
                   breakout_mode=True)
    reason, _ = evaluate_exit(pos, _snap(price=104.85), settings)
    assert reason == EXIT_TRAIL


# ---------- 3) Symmetric cooldown writes from watcher ----------
class _CooldownColl:
    def __init__(self):
        self.upserts: list[dict] = []
    async def replace_one(self, q, doc, upsert=False):
        self.upserts.append(doc)
        class _R:
            pass
        return _R()


@pytest.mark.asyncio
async def test_set_symbol_cooldown_writes_unlock_timestamp():
    from trading_engine import set_symbol_cooldown
    class _DB:
        cooldowns = _CooldownColl()
    db = _DB()
    await set_symbol_cooldown(db, "BTC/USD", 7200, EXIT_SL)
    assert len(db.cooldowns.upserts) == 1
    doc = db.cooldowns.upserts[0]
    assert doc["_id"] == "BTC/USD"
    assert doc["reason"] == EXIT_SL
    unlock = datetime.fromisoformat(doc["unlock_at"].replace("Z", "+00:00"))
    # ~2h from now, allow 60s drift
    expected = datetime.now(UTC) + timedelta(seconds=7200)
    assert abs((unlock - expected).total_seconds()) < 60


@pytest.mark.asyncio
async def test_get_symbol_cooldown_returns_none_when_expired():
    from trading_engine import get_symbol_cooldown
    expired_doc = {
        "_id": "BTC/USD",
        "unlock_at": (datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
        "reason": EXIT_SL,
    }
    class _Coll:
        deleted = []
        async def find_one(self, q):
            return expired_doc
        async def delete_one(self, q):
            self.deleted.append(q)
            class _R:
                deleted_count = 1
            return _R()
    class _DB:
        cooldowns = _Coll()
    db = _DB()
    out = await get_symbol_cooldown(db, "BTC/USD")
    assert out is None
    assert db.cooldowns.deleted == [{"_id": "BTC/USD"}]


@pytest.mark.asyncio
async def test_get_symbol_cooldown_returns_active_doc():
    from trading_engine import get_symbol_cooldown
    future_doc = {
        "_id": "ETH/USD",
        "unlock_at": (datetime.now(UTC) + timedelta(seconds=3600)).isoformat(),
        "reason": EXIT_TRAIL,
    }
    class _Coll:
        async def find_one(self, q):
            return future_doc
        async def delete_one(self, q):
            class _R:
                deleted_count = 0
            return _R()
    class _DB:
        cooldowns = _Coll()
    out = await get_symbol_cooldown(_DB(), "ETH/USD")
    assert out is not None
    assert out["reason"] == EXIT_TRAIL


# ---------- 4) LLM payload caching ----------
@pytest.mark.asyncio
async def test_analyze_macro_caches_on_identical_payload(monkeypatch):
    clear_macro_cache()
    call_count = {"n": 0}

    class _FakeChat:
        def __init__(self, *a, **kw): pass
        def with_model(self, *a, **kw): return self
        async def send_message(self, msg):
            call_count["n"] += 1
            return '{"bias":"BULLISH","confidence":0.9,"reason":"test"}'

    monkeypatch.setenv("EMERGENT_LLM_KEY", "fake-key")
    monkeypatch.setattr("ai_reasoning.LlmChat", _FakeChat)

    r1 = await analyze_macro("BTC/USD", "news payload v1")
    r2 = await analyze_macro("BTC/USD", "news payload v1")  # same payload
    r3 = await analyze_macro("BTC/USD", "news payload v2")  # different
    _r4 = await analyze_macro("ETH/USD", "news payload v1")  # different symbol

    assert call_count["n"] == 3, f"expected 3 LLM calls, got {call_count['n']}"
    assert r1.bias == "BULLISH" and r2.bias == "BULLISH"
    assert isinstance(r1, MacroBias) and isinstance(r3, MacroBias)
    # cached result should be identical object (not just equal)
    assert r2.reason == r1.reason


@pytest.mark.asyncio
async def test_analyze_macro_does_not_cache_neutral_fallback(monkeypatch):
    """When the key is missing we return a fallback — must NOT poison the cache."""
    clear_macro_cache()
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    r = await analyze_macro("BTC/USD", "anything")
    assert r.bias == "NEUTRAL" and r.confidence == 0.0
    # cache should remain empty (no key configured -> no successful call)
    from ai_reasoning import _LAST_CALL_CACHE
    assert "BTC/USD" not in _LAST_CALL_CACHE


# ---------- 5) Default value sanity ----------
def test_phase_defaults():
    s = RiskSettings()
    assert s.normal_lot_usd == 20.0
    assert s.strong_lot_usd == 30.0
    assert s.breakout_lot_usd == 50.0
    assert s.breakout_min_confidence == 0.85
    assert s.breakout_volume_percentile == 95.0
    assert s.breakout_max_spread_pct == 0.20
    assert s.breakout_trail_arm_pct == 5.0
    assert s.breakout_trail_distance_pct == 3.0
    assert s.sl_cooldown_seconds == 7200
    assert s.trail_cooldown_seconds == 1800
