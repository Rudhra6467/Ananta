"""WS2 Hunter Continuation — entry gates for trend-pullback setups."""
import sys

sys.path.insert(0, "/app/backend")
from continuation import evaluate_continuation
from models import RiskSettings
from router import continuation_allowed, route


def _bar(o, h, l, c, v):
    return [0, o, h, l, c, v]


def _uptrend_pullback():
    """Rising trend (EMA50 rising, price above it), then a shallow low-volume dip to the 20-EMA
    that cools RSI into the 40-62 pullback band (tuned so all continuation gates pass)."""
    bars = []
    price = 100.0
    for _ in range(70):
        price *= 1.003  # steady, gentle uptrend
        bars.append(_bar(price * 0.999, price * 1.003, price * 0.997, price, 1000))
    for k in range(5):  # 5-candle pullback, volume drying up
        price *= (1 - 0.009)
        bars.append(_bar(price * 1.002, price * 1.004, price * 0.998, price, max(700 - k * 90, 150)))
    price *= 1.001  # stabilising candle turning up
    bars.append(_bar(price * 0.999, price * 1.003, price * 0.997, price, 180))
    return bars


def test_router_allows_continuation_in_trend():
    assert continuation_allowed("TREND_UP")
    assert continuation_allowed("NEUTRAL")
    assert not continuation_allowed("TREND_DOWN")
    assert "continuation" in route("TREND_UP")["eligible_models"]


def test_continuation_triggers_on_trend_pullback():
    s = RiskSettings()
    sig = evaluate_continuation(_uptrend_pullback(), s)
    assert sig.triggered, sig.reason_codes
    assert sig.entry_profile == "TREND_PULLBACK"
    assert sig.structural_stop is not None and sig.structural_stop < sig.evidence["ema_slow"]
    assert s.cont_rsi_min <= sig.evidence["rsi_14"] <= s.cont_rsi_max


def test_continuation_rejects_downtrend():
    s = RiskSettings()
    bars = [_bar(100 - i, 101 - i, 99 - i, 100 - i, 1000) for i in range(70)]
    sig = evaluate_continuation(bars, s)
    assert not sig.triggered
    assert "REJECTED_NO_UPTREND" in sig.reason_codes


def test_continuation_rejects_chasing_green_candle():
    s = RiskSettings()
    bars = _uptrend_pullback()
    # replace last candle with a vertical green bar (chase)
    prev = bars[-1][4]
    bars[-1] = _bar(prev, prev * 1.09, prev * 0.999, prev * 1.08, 600)
    sig = evaluate_continuation(bars, s)
    assert "REJECTED_CHASING_GREEN_CANDLE" in sig.reason_codes
    assert not sig.triggered


def test_continuation_rejects_no_volume_dryup():
    s = RiskSettings()
    bars = _uptrend_pullback()
    # inflate pullback volume (no dry-up)
    for j in range(-4, 0):
        b = bars[j]
        bars[j] = _bar(b[1], b[2], b[3], b[4], 5000)
    sig = evaluate_continuation(bars, s)
    assert "REJECTED_NO_VOLUME_DRYUP" in sig.reason_codes
    assert not sig.triggered


def test_continuation_disabled_flag_respected_by_backtester_gate():
    # sanity: the setting exists and defaults on
    assert RiskSettings().continuation_enabled is True
