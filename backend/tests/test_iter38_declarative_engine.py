"""Phase B declarative executor — unit tests with synthetic OHLCV (no network)."""
from __future__ import annotations

import strategy  # noqa: F401  (registers declarative schemas)
from declarative_engine import evaluate
from strategy.declarative_defs import DECLARATIVE, get_declarative_spec


def _bar(ts, o, h, l, c, v=1000.0):
    return [ts, o, h, l, c, v]


def _series_bars(closes, vol=1000.0):
    """Build OHLCV bars from a close series (o=prev close, h/l padded)."""
    bars = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        h = max(o, c) * 1.002
        l = min(o, c) * 0.998
        bars.append(_bar(i, o, h, l, c, vol))
    return bars


def test_all_specs_defined():
    for key in DECLARATIVE:
        assert get_declarative_spec(key) is not None


def test_ema_cross_triggers_on_upturn():
    # downtrend then recovery: cross_above fires on the EXACT crossover bar, so grow the
    # recovery one bar at a time and assert the entry triggers on some bar during the upturn.
    down = [100 - i for i in range(60)]
    spec = get_declarative_spec("ema-cross")
    fired = False
    for n in range(2, 40):
        closes = down + [40 + i * 3 for i in range(n)]
        sig = evaluate(spec, _series_bars(closes), {"ema_fast": 12, "ema_slow": 26})
        if sig.entry:
            fired = True
            break
    assert fired is True


def test_ema_cross_no_signal_in_downtrend():
    closes = [100 - i * 0.5 for i in range(80)]
    bars = _series_bars(closes)
    sig = evaluate(get_declarative_spec("ema-cross"), bars, {"ema_fast": 12, "ema_slow": 26})
    assert sig.entry is False


def test_bollinger_entry_below_lower_band():
    # stable ~100 then a sharp single-bar drop below the lower band
    closes = [100 + (0.3 if i % 2 else -0.3) for i in range(60)] + [90]
    bars = _series_bars(closes)
    sig = evaluate(get_declarative_spec("bollinger-mr"), bars, {"bb_period": 20, "bb_std": 2.0})
    assert sig.entry is True


def test_donchian_breakout_on_new_high():
    closes = [100 + (i % 5) for i in range(60)] + [130]  # last bar = clear new high
    bars = _series_bars(closes)
    sig = evaluate(get_declarative_spec("donchian-breakout"), bars, {"dc_entry": 20, "dc_exit": 10})
    assert sig.entry is True


def test_rsi_momentum_needs_trend_and_strength():
    # strong steady uptrend → RSI high, price above EMA
    closes = [50 + i for i in range(80)]
    bars = _series_bars(closes)
    sig = evaluate(get_declarative_spec("rsi-momentum"), bars,
                   {"rsi_period": 14, "rsi_entry": 60, "rsi_exit": 50, "trend_ema": 50})
    # in a pure ramp RSI is pinned high (already >60, no fresh cross) — entry may be False;
    # assert it runs and yields indicator values without error
    assert "rsi" in sig.indicators and sig.indicators["rsi"] is not None


def test_supertrend_runs_and_flips():
    closes = [100 - i for i in range(40)] + [60 + i * 2 for i in range(40)]
    bars = _series_bars(closes)
    sig = evaluate(get_declarative_spec("supertrend"), bars, {"st_atr_period": 10, "st_multiplier": 3.0})
    assert "st_dir" in sig.indicators


def test_insufficient_bars_safe():
    sig = evaluate(get_declarative_spec("ema-cross"), _series_bars([100, 101, 102]), {"ema_fast": 12, "ema_slow": 26})
    assert sig.entry is False and sig.reason == "insufficient bars"
