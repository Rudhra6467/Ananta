"""
Regime classification audit — per-candle labels + standard proxies, for auditing the accuracy
of classify_regime (regime.py) against ADX / Efficiency-Ratio / Bollinger-bandwidth / ATR-percentile.

Uses the SAME classify_regime the live engine + Lab use (true labels, not a reimplementation) and
the SAME rolling window (ANALYSIS_LOOKBACK), so the export reflects exactly what the engine sees.
Pure compute, zero LLM.
"""
from __future__ import annotations

import io
from statistics import median

from regime import classify_regime
from setup_classifier import adx, atr, percentile_rank
from lab.data_store import coverage, load_candles

_H, _L, _C = 2, 3, 4
WINDOW = 750  # matches ANALYSIS_LOOKBACK / live EXEC_BARS_LIMIT


def _efficiency_ratio(closes: list[float], i: int, n: int = 10) -> float:
    """Kaufman Efficiency Ratio: net move / summed path over n bars (0..1). High = clean trend."""
    if i < n:
        return 0.0
    net = abs(closes[i] - closes[i - n])
    path = sum(abs(closes[k] - closes[k - 1]) for k in range(i - n + 1, i + 1))
    return round(net / path, 4) if path else 0.0


def _bbwidth(closes: list[float], i: int, period: int = 20, k: float = 2.0) -> float:
    if i < period - 1:
        return 0.0
    w = closes[i - period + 1:i + 1]
    m = sum(w) / period
    sd = (sum((c - m) ** 2 for c in w) / period) ** 0.5
    return (2 * k * sd) / m * 100.0 if m else 0.0


def audit(symbol: str, timeframe: str = "1h",
          start_ms: int | None = None, end_ms: int | None = None,
          stride: int = 1) -> dict:
    """Return {coverage, rows[], summary{distribution, avg_duration, transition_matrix, proxy_agreement}}.

    Each row: ts, o,h,l,c,v, regime, rsi, adx, atr_pct, bbw_pct, ema_stack, efficiency_ratio,
              adx_trend(bool), er_trend(bool), bb_compression(bool).
    """
    bars = load_candles(symbol, timeframe, start_ms, end_ms)
    if len(bars) < 60:
        return {"coverage": coverage(symbol, timeframe), "rows": [], "summary": {"error": "insufficient_candles"}}

    highs = [b[_H] for b in bars]
    lows = [b[_L] for b in bars]
    closes = [b[_C] for b in bars]

    # Proxy series computed once over the full history.
    adx_series = adx(highs, lows, closes)
    atr_series = atr(highs, lows, closes)
    bbw_all = [_bbwidth(closes, i) for i in range(len(closes))]

    rows: list[dict] = []
    labels: list[str] = []
    stride = max(1, int(stride))
    for i in range(59, len(bars), stride):
        window = bars[max(0, i + 1 - WINDOW): i + 1]
        reg = classify_regime(window)
        ev = reg.evidence or {}
        adx_v = float(adx_series[i]) if i < len(adx_series) else 0.0
        atr_pct = percentile_rank(atr_series[: i + 1], atr_series[i]) if i < len(atr_series) else 0.0
        bbw_pct = percentile_rank([b for b in bbw_all[: i + 1] if b > 0] or [0.0], bbw_all[i])
        er = _efficiency_ratio(closes, i)
        rows.append({
            "ts": int(bars[i][0]), "open": bars[i][1], "high": bars[i][2],
            "low": bars[i][3], "close": bars[i][4], "volume": bars[i][5],
            "regime": reg.regime,
            "rsi": ev.get("rsi"), "adx": round(adx_v, 2),
            "atr_pct": round(atr_pct, 1), "bbw_pct": round(bbw_pct, 1),
            "ema_stack": ev.get("ema_stack"), "efficiency_ratio": er,
            "adx_trend": adx_v >= 25.0,               # standard trend proxy
            "er_trend": er >= 0.30,                    # clean directional move
            "bb_compression": bbw_pct <= 20.0,         # squeeze proxy
        })
        labels.append(reg.regime)

    # ---- summary ----
    n = len(labels)
    dist: dict[str, int] = {}
    for lb in labels:
        dist[lb] = dist.get(lb, 0) + 1
    distribution = {k: {"count": v, "pct": round(100.0 * v / n, 1)} for k, v in sorted(dist.items())}

    # run-length durations per regime (in bars, at the given stride)
    durations: dict[str, list[int]] = {}
    transitions: dict[str, dict[str, int]] = {}
    run_lb, run_len = labels[0], 1
    for j in range(1, n):
        if labels[j] == run_lb:
            run_len += 1
        else:
            durations.setdefault(run_lb, []).append(run_len)
            transitions.setdefault(run_lb, {}).setdefault(labels[j], 0)
            transitions[run_lb][labels[j]] += 1
            run_lb, run_len = labels[j], 1
    durations.setdefault(run_lb, []).append(run_len)
    avg_duration = {k: {"mean_bars": round(sum(v) / len(v), 1), "median_bars": median(v), "runs": len(v)}
                    for k, v in durations.items()}

    # crude agreement: does classify_regime's TREND_* agree with adx_trend proxy?
    trend_rows = [r for r in rows if r["regime"] in ("TREND_UP", "TREND_DOWN")]
    trend_agree = sum(1 for r in trend_rows if r["adx_trend"]) / len(trend_rows) if trend_rows else None
    comp_rows = [r for r in rows if r["regime"] == "COMPRESSION"]
    comp_agree = sum(1 for r in comp_rows if r["bb_compression"]) / len(comp_rows) if comp_rows else None

    return {
        "coverage": coverage(symbol, timeframe),
        "rows": rows,
        "summary": {
            "candles_labelled": n, "stride": stride,
            "distribution": distribution,
            "avg_duration": avg_duration,
            "transition_matrix": transitions,
            "proxy_agreement": {
                "trend_vs_adx>=25": round(trend_agree, 3) if trend_agree is not None else None,
                "compression_vs_bbw<=20pct": round(comp_agree, 3) if comp_agree is not None else None,
            },
        },
    }


def to_csv(rows: list[dict]) -> str:
    cols = ["ts", "open", "high", "low", "close", "volume", "regime", "rsi", "adx",
            "atr_pct", "bbw_pct", "ema_stack", "efficiency_ratio", "adx_trend", "er_trend", "bb_compression"]
    buf = io.StringIO()
    buf.write(",".join(cols) + "\n")
    for r in rows:
        buf.write(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    return buf.getvalue()
