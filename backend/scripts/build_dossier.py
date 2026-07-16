"""
build_dossier.py — one-shot generator for the Ananta Trading Engine Technical Dossier.

Produces four deliverables, ALL grounded in Lab backtest run
    a7a8a0c0-2080-4405-97e7-f97c36cc2f76
(3 symbols · 1y · 1h · ATR trailing exit), the exact run behind the supplied PDF:

  1. Ananta_Trading_Engine_Technical_Dossier.pdf   (Parts 1-17, authored from source)
  2. ananta_trade_log.csv                           (every trade, parsed from the report PDF)
  3. ananta_per_candle_indicators.csv               (full indicator series, engine formulas)
  4. ananta_engine_config.json                      (machine-readable config export)

Run:  cd /app/backend && python scripts/build_dossier.py
Outputs to /app/frontend/public/dossier/ (served at <preview-host>/dossier/<file>).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

OUT = "/app/frontend/public/dossier"
os.makedirs(OUT, exist_ok=True)
SRC_PDF = "/tmp/dossier/backtest.pdf"

# ---------------------------------------------------------------------------
# RUN RESULTS — verbatim from the supplied backtest PDF (source of truth).
# ---------------------------------------------------------------------------
RUN = {
    "run_id": "a7a8a0c0-2080-4405-97e7-f97c36cc2f76",
    "kind": "backtest",
    "symbols": ["BTC/USD", "SOL/USD", "ETH/USD"],
    "period": "1y (2025-07-20 -> 2026-07-15)",
    "window_start": "2025-07-20", "window_end": "2026-07-15",
    "timeframe": "1h (live-execution baseline); 15m & 30m also replayed for comparison",
    "exit_method": "ATR Exit (x2.5 stop, 14p, arm 3%, trail x2)",
    "atr_params": {"multiplier": 2.5, "period": 14, "trail_activation_pct": 3.0, "trail_distance": 2.0},
    "position_size_usd": 75.0,
    "baseline_capital": 1200.0,
    "metric": "return_over_dd",
    "git_commit": "unknown",
    "generated": "2026-07-16T13:05:16",
    "strategies_selected": ["hunter", "squeeze", "continuation", "ema-cross", "supertrend",
                            "rsi-momentum", "macd-trend", "bollinger-mr", "donchian-breakout",
                            "atr-breakout", "keltner-breakout"],
}

PER_SYMBOL = {
    "BTC/USD": {"total_return_pct": -13.586, "trades": 197, "win_rate_pct": 34.0, "max_drawdown_pct": 1.03,
                "sharpe": -0.149, "sortino": -0.168, "profit_factor": 0.33, "net_pnl": -163.033,
                "avg_mfe_pct": 1.934, "avg_mae_pct": -1.694, "avg_profit_left_usd": 2.278,
                "total_profit_left_usd": 448.85, "avg_trade_quality": 53.3,
                "recommendation": "UNDERPERFORMING - -13.6% at 34.0% win rate; the edge is weak in this window. Re-test other timeframes or parameter presets.",
                "best_engine": "Fixed $3.00 / $2.25 - -7.45% net return at 34.0% win rate, profit factor 0.69, 0.80% max drawdown over 197 trades.",
                "regime": {"COMPRESSION": (10, 40.0, -2.29), "NEUTRAL": (70, 35.7, -54.67), "RANGE": (1, 0.0, -1.75),
                           "REVERSAL": (8, 50.0, -6.02), "TREND_UP": (108, 31.5, -98.31)},
                "exit_modules": {"ATR": (195, 34.4, -162.58), "EOD": (2, 0.0, -0.45)}},
    "SOL/USD": {"total_return_pct": -23.583, "trades": 249, "win_rate_pct": 36.5, "max_drawdown_pct": 1.53,
                "sharpe": -0.289, "sortino": -0.268, "profit_factor": 0.25, "net_pnl": -282.994,
                "avg_mfe_pct": 2.325, "avg_mae_pct": -2.232, "avg_profit_left_usd": 2.881,
                "total_profit_left_usd": 717.26, "avg_trade_quality": 51.3,
                "recommendation": "UNDERPERFORMING - -23.6% at 36.5% win rate; the edge is weak in this window. Re-test other timeframes or parameter presets.",
                "best_engine": "Fixed $5.00 / $4.00 - -25.25% net return at 30.9% win rate, profit factor 0.56, 1.89% max drawdown over 249 trades.",
                "regime": {"COMPRESSION": (6, 16.7, -7.69), "NEUTRAL": (58, 41.4, -45.84), "RANGE": (5, 40.0, -6.44),
                           "REVERSAL": (6, 0.0, -17.9), "TREND_UP": (174, 36.8, -205.12)},
                "exit_modules": {"ATR": (249, 36.5, -282.99)}},
    "ETH/USD": {"total_return_pct": -18.439, "trades": 227, "win_rate_pct": 37.0, "max_drawdown_pct": 1.28,
                "sharpe": -0.217, "sortino": -0.219, "profit_factor": 0.30, "net_pnl": -221.263,
                "avg_mfe_pct": 2.291, "avg_mae_pct": -2.036, "avg_profit_left_usd": 2.693,
                "total_profit_left_usd": 611.35, "avg_trade_quality": 52.3,
                "recommendation": "UNDERPERFORMING - -18.4% at 37.0% win rate; the edge is weak in this window. Re-test other timeframes or parameter presets.",
                "best_engine": "Fixed $5.00 / $4.00 - -12.86% net return at 37.0% win rate, profit factor 0.73, 1.52% max drawdown over 227 trades.",
                "regime": {"COMPRESSION": (6, 33.3, -4.59), "NEUTRAL": (61, 34.4, -60.15), "RANGE": (5, 40.0, -3.11),
                           "REVERSAL": (8, 25.0, -10.72), "TREND_UP": (147, 38.8, -142.69)},
                "exit_modules": {"ATR": (225, 36.9, -221.26), "EOD": (2, 50.0, -0.01)}},
}

MULTI_TF = {  # symbol -> tf -> (trades, return, win, maxdd, mfe, mae)
    "BTC/USD": {"15m": (0, None, None, None, None, None), "30m": (0, None, None, None, None, None),
                "1h": (197, -13.586, 34.0, 1.03, 1.934, -1.694)},
    "SOL/USD": {"15m": (0, None, None, None, None, None), "30m": (0, None, None, None, None, None),
                "1h": (249, -23.583, 36.5, 1.53, 2.325, -2.232)},
    "ETH/USD": {"15m": (0, None, None, None, None, None), "30m": (0, None, None, None, None, None),
                "1h": (227, -18.439, 37.0, 1.28, 2.291, -2.036)},
}

EXIT_CMP = {  # symbol -> list of (label, PF, win, expectancy, net_return, maxdd)
    "BTC/USD": [("Fixed $2.00/$1.50", 0.34, 20.3, -0.78, -12.75, 0.98),
                ("Fixed $3.00/$2.25 (best)", 0.69, 34.0, -0.45, -7.45, 0.80),
                ("Fixed $4.00/$3.00", 0.68, 35.0, -0.62, -10.20, 0.97),
                ("Fixed $5.00/$4.00", 0.64, 36.0, -0.91, -15.01, 1.32),
                ("ATR Baseline (x2.5, 14p)", 0.33, 34.0, -0.83, -13.59, 1.03)],
    "SOL/USD": [("Fixed $2.00/$1.50", 0.42, 24.1, -0.66, -13.62, 0.87),
                ("Fixed $3.00/$2.25", 0.51, 27.7, -0.80, -16.50, 1.06),
                ("Fixed $4.00/$3.00", 0.52, 28.1, -1.03, -21.42, 1.39),
                ("Fixed $5.00/$4.00 (best)", 0.56, 30.9, -1.22, -25.25, 1.89),
                ("ATR Baseline (x2.5, 14p)", 0.25, 36.5, -1.14, -23.58, 1.53)],
    "ETH/USD": [("Fixed $2.00/$1.50", 0.37, 21.6, -0.74, -14.04, 0.97),
                ("Fixed $3.00/$2.25", 0.49, 26.9, -0.84, -15.94, 1.18),
                ("Fixed $4.00/$3.00", 0.63, 32.2, -0.75, -14.25, 1.38),
                ("Fixed $5.00/$4.00 (best)", 0.73, 37.0, -0.68, -12.86, 1.52),
                ("ATR Baseline (x2.5, 14p)", 0.30, 37.0, -0.97, -18.44, 1.28)],
}


# ===========================================================================
# 1) TRADE LOG CSV — parse every trade row out of the report PDF
# ===========================================================================
def _clean(cell: str) -> str:
    return (cell or "").replace("\n", "").strip()


def _clean_ts(cell: str) -> str:
    # PDF wraps "YYYY-MM-DD\nHH:MM" — restore the date/time space (don't delete it)
    return " ".join((cell or "").split())


def parse_trade_log() -> list[dict]:
    import pdfplumber
    rows: list[dict] = []
    order = ["BTC/USD", "SOL/USD", "ETH/USD"]
    sym_idx = -1
    last_num = 10**9
    with pdfplumber.open(SRC_PDF) as pdf:
        for page in pdf.pages:
            for tbl in (page.extract_tables() or []):
                for r in tbl:
                    if not r or len(r) < 8:
                        continue
                    num_raw = _clean(r[0])
                    if not num_raw.isdigit():
                        continue
                    num = int(num_raw)
                    # a reset (# goes back down to a small value) => next symbol section
                    if num < last_num and num <= 3:
                        sym_idx += 1
                    last_num = num
                    if sym_idx < 0:
                        sym_idx = 0
                    rows.append({
                        "symbol": order[min(sym_idx, 2)],
                        "trade_num": num,
                        "entry_utc": _clean_ts(r[1]),
                        "exit_utc": _clean_ts(r[2]),
                        "entry_price": _clean(r[3]),
                        "exit_price": _clean(r[4]),
                        "size": _clean(r[5]),
                        "pnl_usd": _clean(r[6]),
                        "exit_module": _clean(r[7]),
                    })
    return rows


def write_trade_log():
    rows = parse_trade_log()
    counts = {"BTC/USD": 0, "SOL/USD": 0, "ETH/USD": 0}
    for r in rows:
        counts[r["symbol"]] += 1
    path = os.path.join(OUT, "ananta_trade_log.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "trade_num", "entry_utc", "exit_utc",
                                          "entry_price", "exit_price", "size", "pnl_usd", "exit_module"])
        w.writeheader()
        w.writerows(rows)
    print(f"[trade_log] wrote {len(rows)} rows -> {path}  counts={counts}  "
          f"(expected BTC 197 / SOL 249 / ETH 227)")
    return counts, len(rows)


# ===========================================================================
# 2) PER-CANDLE INDICATOR SNAPSHOTS — engine formulas over the same OHLCV
# ===========================================================================
def write_per_candle():
    from lab import data_store
    from setup_classifier import ema, rsi, atr, adx, percentile_rank

    W_START = int(datetime(2025, 7, 20, tzinfo=timezone.utc).timestamp() * 1000)
    W_END = int(datetime(2026, 7, 16, tzinfo=timezone.utc).timestamp() * 1000)
    PCT_WIN = 750  # trailing window used by the live regime classifier

    def sma(vals, p):
        out = [None] * len(vals)
        s = 0.0
        for i, v in enumerate(vals):
            s += v
            if i >= p:
                s -= vals[i - p]
            if i >= p - 1:
                out[i] = s / p
        return out

    def right_align(short, n):
        return [None] * (n - len(short)) + list(short)

    def supertrend_dir(highs, lows, closes, atr_p=10, mult=3.0):
        a = atr(highs, lows, closes, atr_p)
        n = len(closes)
        direction = [None] * n
        final_ub = final_lb = None
        d = 1
        for i in range(n):
            hl2 = (highs[i] + lows[i]) / 2.0
            bub = hl2 + mult * a[i]
            blb = hl2 - mult * a[i]
            if i == 0:
                final_ub, final_lb, d = bub, blb, 1
            else:
                final_ub = bub if (bub < final_ub or closes[i - 1] > final_ub) else final_ub
                final_lb = blb if (blb > final_lb or closes[i - 1] < final_lb) else final_lb
                if closes[i] > final_ub:
                    d = 1
                elif closes[i] < final_lb:
                    d = -1
            direction[i] = d
        return direction

    path = os.path.join(OUT, "ananta_per_candle_indicators.csv")
    header = ["symbol", "timestamp_utc", "open", "high", "low", "close", "volume",
              "ema20", "ema50", "ema200", "rsi14", "macd_line", "macd_signal", "macd_hist",
              "atr14", "adx14", "bb_upper", "bb_mid", "bb_lower", "bb_width_pct",
              "atr_percentile", "bb_width_percentile", "ema_stack", "higher_high_higher_low",
              "lower_high_lower_low", "regime", "strong_uptrend", "panic", "compression",
              # ---- catalog-strategy inputs (NOT active in this run; provided for completeness) ----
              "supertrend_dir_10_3", "donchian_high20", "donchian_low10",
              "keltner_upper_20_10_2", "keltner_mid20", "atr_breakout_level_14_1p5"]
    total = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for sym in RUN["symbols"]:
            bars = data_store.load_candles(sym, "1h")
            if not bars:
                print(f"[per_candle] {sym}: NO CANDLES in preview data_store — skipped")
                continue
            n = len(bars)
            o = [b[1] for b in bars]; h = [b[2] for b in bars]
            lo = [b[3] for b in bars]; c = [b[4] for b in bars]; v = [b[5] for b in bars]
            e20 = ema(c, 20); e50 = ema(c, 50); e200 = ema(c, 200)
            e12 = ema(c, 12); e26 = ema(c, 26)
            macd_line = [e12[i] - e26[i] for i in range(n)]
            macd_sig = ema(macd_line, 9)
            r14 = right_align(rsi(c, 14), n)
            a14 = atr(h, lo, c, 14)
            adx14 = adx(h, lo, c, 14)
            sma20 = sma(c, 20)
            bb_up = [None] * n; bb_mid = [None] * n; bb_lo = [None] * n; bbw = [None] * n
            for i in range(n):
                if i >= 19:
                    win = c[i - 19:i + 1]
                    m = sma20[i]
                    sd = (sum((x - m) ** 2 for x in win) / 20) ** 0.5
                    bb_up[i] = m + 2 * sd; bb_lo[i] = m - 2 * sd; bb_mid[i] = m
                    bbw[i] = (bb_up[i] - bb_lo[i]) / m * 100.0 if m else 0.0
            a10 = atr(h, lo, c, 10)
            kc_up = [(e20[i] + 2 * a10[i]) if a10[i] is not None else None for i in range(n)]
            st_dir = supertrend_dir(h, lo, c, 10, 3.0)
            dc_hi = [max(h[max(0, i - 19):i + 1]) for i in range(n)]
            dc_lo = [min(lo[max(0, i - 9):i + 1]) for i in range(n)]
            atr_bo = [(c[i - 1] + 1.5 * a14[i]) if i >= 1 else None for i in range(n)]

            for i in range(n):
                ts = bars[i][0]
                if ts < W_START or ts > W_END:
                    continue
                lo_p = max(0, i + 1 - PCT_WIN)
                atr_slice = a14[lo_p:i + 1]
                bbw_slice = [x for x in bbw[lo_p:i + 1] if x is not None]
                atr_pct = percentile_rank(atr_slice, a14[i]) if atr_slice else None
                bbw_pct = percentile_rank(bbw_slice, bbw[i]) if (bbw_slice and bbw[i] is not None) else None
                stack = "UP" if (e20[i] > e50[i] > e200[i]) else "DOWN" if (e20[i] < e50[i] < e200[i]) else "MIXED"
                # swing structure over last/prev 20 (regime._structure)
                hh_hl = lh_ll = False
                if i >= 39:
                    rh = h[i - 19:i + 1]; ph = h[i - 39:i - 19]
                    rl = lo[i - 19:i + 1]; pl = lo[i - 39:i - 19]
                    hh_hl = max(rh) > max(ph) and min(rl) > min(pl)
                    lh_ll = max(rh) < max(ph) and min(rl) < min(pl)
                rv = r14[i]
                strong = bool(stack == "UP" and c[i] > e20[i] and adx14[i] >= 20.0 and hh_hl)
                panic = bool(rv is not None and rv <= 22.0 and atr_pct is not None and atr_pct >= 70.0)
                compression = bool((bbw_pct is not None and atr_pct is not None and bbw_pct <= 30.0 and atr_pct <= 35.0)
                                   or (atr_pct is not None and atr_pct <= 10.0))
                if compression:
                    reg = "COMPRESSION"
                elif panic or (rv is not None and rv <= 32.0 and (stack == "DOWN" or lh_ll)):
                    reg = "REVERSAL"
                elif strong:
                    reg = "TREND_UP"
                elif stack == "DOWN" and adx14[i] >= 20.0:
                    reg = "TREND_DOWN"
                elif adx14[i] < 20.0:
                    reg = "RANGE"
                else:
                    reg = "NEUTRAL"

                def rnd(x, d=6):
                    return round(x, d) if isinstance(x, (int, float)) else ""
                w.writerow([
                    sym, datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                    rnd(o[i]), rnd(h[i]), rnd(lo[i]), rnd(c[i]), rnd(v[i], 4),
                    rnd(e20[i]), rnd(e50[i]), rnd(e200[i]), rnd(rv, 2),
                    rnd(macd_line[i]), rnd(macd_sig[i]), rnd(macd_line[i] - macd_sig[i]),
                    rnd(a14[i]), rnd(adx14[i], 2), rnd(bb_up[i]), rnd(bb_mid[i]), rnd(bb_lo[i]), rnd(bbw[i], 3),
                    rnd(atr_pct, 1), rnd(bbw_pct, 1), stack, hh_hl, lh_ll, reg, strong, panic, compression,
                    st_dir[i], rnd(dc_hi[i]), rnd(dc_lo[i]), rnd(kc_up[i]), rnd(e20[i]), rnd(atr_bo[i]),
                ])
                total += 1
            print(f"[per_candle] {sym}: {n} candles loaded, window rows written")
    print(f"[per_candle] wrote {total} rows -> {path}")
    return total


# ===========================================================================
# 3) CONFIG JSON EXPORT — machine-readable, exact
# ===========================================================================
def write_config_json():
    from models import RiskSettings
    import settings_spec
    from strategy.declarative_defs import DECLARATIVE
    from lab.backtest import EXIT_COMPARISON_CONFIGS, ATR_EXIT_DEFAULTS, WARMUP_BARS, ANALYSIS_LOOKBACK, SLIPPAGE_PCT

    def declify(d):
        return {k: {"name": v["name"], "library_id": v["library_id"],
                    "default_enabled": v["default_enabled"], "description": v["description"],
                    "params": [{"id": p.id, "label": p.label, "type": str(p.type), "default": p.default,
                                "min": p.min, "max": p.max, "step": p.step, "unit": p.unit,
                                "engine_backed": p.engine_backed} for p in v["params"]],
                    "spec": v["spec"]} for k, v in d.items()}

    cfg = {
        "meta": {
            "document": "Ananta Trading Engine — Machine-Readable Configuration Export",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "grounded_in_run": RUN["run_id"],
            "disclaimer": ("RiskSettings values below are the engine DEFAULTS from models.RiskSettings. "
                           "The backtest itself overrides position size to $75 and uses the ATR-exit method "
                           "with the atr_params shown under backtest_run. The eight declarative strategies were "
                           "SELECTED in the run config but the Lab backtester's entry scan wires only the three "
                           "core alpha models (hunter/squeeze/continuation) — see the Dossier, Part 3/15."),
        },
        "backtest_run": RUN,
        "execution_model": {
            "entry_fill": "signal evaluated on closed bar i; fill at bar i+1 OPEN",
            "exit_intrabar": "pessimistic LOW pass (stops/trail) then CLOSE pass (upside modules)",
            "slippage_pct_per_leg": SLIPPAGE_PCT,
            "fee_source": "RiskSettings.taker_fee_pct (applied to every leg)",
            "warmup_bars": WARMUP_BARS,
            "analysis_lookback_bars": ANALYSIS_LOOKBACK,
            "no_lookahead": True,
        },
        "risk_settings_defaults": RiskSettings().model_dump(),
        "risk_settings_hard_bounds": {
            "float_clamps": settings_spec.FLOAT_CLAMPS,
            "int_clamps": settings_spec.INT_CLAMPS,
            "profile_clamps": settings_spec.PROFILE_CLAMPS,
        },
        "atr_exit_defaults": ATR_EXIT_DEFAULTS,
        "exit_comparison_configs": EXIT_COMPARISON_CONFIGS,
        "regime_classifier": {
            "regimes": ["TREND_UP", "TREND_DOWN", "RANGE", "COMPRESSION", "REVERSAL", "NEUTRAL"],
            "priority": "compression > reversal(panic) > strong-trend > range > neutral",
            "thresholds": {
                "strong_uptrend": "ema20>ema50>ema200 AND price>ema20 AND ADX>=20 AND higher-high/higher-low",
                "panic": "RSI<=22 AND ATR percentile>=70",
                "compression": "(BBwidth pct<=30 AND ATR pct<=35) OR ATR pct<=10",
                "reversal": "panic OR (RSI<=32 AND (ema stack down OR lower-high/lower-low))",
                "range": "ADX<20",
            },
            "inputs": "EMA20/50/200, RSI14, ADX14, ATR14(+percentile), Bollinger bandwidth(20,2)(+percentile), swing structure",
        },
        "entry_quality_scoring": {
            "purpose": "research grading only — NEVER gates a trade",
            "grades": {"A+": ">=90", "A": ">=80", "B": ">=65", "C": "<65"},
            "hunter_components": ["rsi_reset", "volume_exhaustion", "zone_touches", "zone_strength",
                                  "trend_alignment", "structure"],
            "squeeze_components": ["compression", "atr_coil", "volume_spike", "breakout_strength", "entry_timing"],
        },
        "exit_engine_modules": {
            "A_structural_failure": {"priority": 1, "action": "EXIT_FULL",
                                     "logic": "structural stop / % stop / locked profit-floor breach"},
            "KILL_emergency": {"priority": 2, "action": "EXIT_FULL", "logic": "injected by caller (existential veto)"},
            "F_profit_protection": {"priority": 3, "action": "TIGHTEN",
                                    "logic": "breakeven at +1R, then lock +1% profit floor"},
            "B_momentum_exhaustion": {"priority": 4, "action": "EXIT_PARTIAL(50%)",
                                      "logic": "overbought zone + volume climax + exhaustion candle"},
            "S_structure_failure": {"priority": 5, "action": "EXIT_FULL",
                                    "logic": "lower-low + momentum dead (RSI<50 & below 20-EMA)"},
            "D_ema_trend_loss": {"priority": 5, "action": "EXIT_FULL", "logic": "close below 20-EMA / dead-cross"},
            "C_atr_trail": {"priority": 6, "action": "EXIT_FULL", "logic": "armed trail = peak - X*ATR, arms at +2R"},
            "E_time_exit": {"priority": 7, "action": "EXIT_FULL", "logic": "capital-efficiency time cap per profile"},
        },
        "strategies": {
            "core_alpha_models": {
                "hunter": {"type": "reversal", "thesis": "buy fear at validated support",
                           "gates": ["historical support zone", "pullback confirmation (no green-candle chase)",
                                     "volume exhaustion (falling volume slope)", "4H RSI momentum reset <= rsi_reset_max"],
                           "structural_stop": "0.4*ATR below the structure low"},
                "squeeze": {"type": "volatility expansion", "thesis": "buy expansion out of a coil",
                            "trigger": "Bollinger Bands inside Keltner Channels",
                            "entry": "CONTINUATION (inside-bar break) or RETEST (reclaim of 20-MA basis), not the first breakout candle",
                            "stop": "20-period MA (Bollinger basis)"},
                "continuation": {"type": "trend pullback", "thesis": "buy the dip in an established uptrend",
                                 "trigger": "50-EMA rising AND 20-EMA>50-EMA AND price>50-EMA",
                                 "entry": "controlled pullback to 20-EMA, volume drying, RSI 40-62, stabilising candle",
                                 "structural_stop": "below pullback low / 50-EMA buffered by 0.4*ATR"},
            },
            "declarative_catalog": declify(DECLARATIVE),
        },
        "results_summary": {"per_symbol": PER_SYMBOL, "multi_timeframe": MULTI_TF, "exit_comparison": EXIT_CMP},
    }
    path = os.path.join(OUT, "ananta_engine_config.json")
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2, default=str)
    print(f"[config] wrote -> {path}")


# ===========================================================================
# 4) TECHNICAL DOSSIER PDF
# ===========================================================================
def build_pdf(trade_counts, trade_total, candle_rows):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                    PageBreak, HRFlowable)

    BRAND = colors.HexColor("#0F766E")
    DARK = colors.HexColor("#111418")
    MUT = colors.HexColor("#5A5F68")
    LINE = colors.HexColor("#D7DBE0")
    NEG = colors.HexColor("#B42318")

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=16, textColor=BRAND, spaceAfter=6, spaceBefore=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, textColor=DARK, spaceAfter=4, spaceBefore=10)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, textColor=BRAND, spaceAfter=3, spaceBefore=6)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=8.8, leading=12.6, spaceAfter=4)
    small = ParagraphStyle("small", parent=body, fontSize=7.8, textColor=MUT, leading=10.5)
    note = ParagraphStyle("note", parent=body, fontSize=8.2, textColor=NEG, leading=11.5)
    bullet = ParagraphStyle("bul", parent=body, leftIndent=10, bulletIndent=0)

    E = []

    def P(t, s=body):
        E.append(Paragraph(t, s))

    def B(items, s=bullet):
        for it in items:
            E.append(Paragraph("• " + it, s))

    def gap(h=4):
        E.append(Spacer(1, h))

    def rule():
        E.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=4, spaceAfter=6))

    def tbl(data, widths, header=True, small_font=True):
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.4, LINE),
              ("FONTSIZE", (0, 0), (-1, -1), 7.4 if small_font else 8.2),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if header:
            st += [("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        t.setStyle(TableStyle(st))
        E.append(t)

    # -------- COVER --------
    E.append(Spacer(1, 40))
    P("ANANTA TRADING ENGINE", ParagraphStyle("cover", parent=h1, fontSize=26, alignment=1, textColor=DARK))
    P("Comprehensive Technical Dossier &amp; Quantitative Audit Package",
      ParagraphStyle("cs", parent=h2, alignment=1, textColor=BRAND, fontSize=13))
    gap(10)
    P("Prepared for independent quantitative research review. This documentation is written to be sufficient "
      "for an experienced systematic trader / researcher to understand, audit and recommend improvements to the "
      "engine <b>without access to the source code</b>.", ParagraphStyle("cc", parent=body, alignment=1, fontSize=9.5))
    gap(16)
    tbl([["Grounded in Lab run", RUN["run_id"]],
         ["Symbols", ", ".join(RUN["symbols"])],
         ["Period / timeframe", RUN["period"] + "  ·  " + RUN["timeframe"]],
         ["Exit method", RUN["exit_method"]],
         ["Report generated", RUN["generated"] + " (source PDF)"],
         ["Dossier generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
         ["Companion artifacts", "trade-log CSV · per-candle indicators CSV · config JSON"]],
        [55 * mm, 95 * mm], header=False, small_font=False)
    gap(10)
    P("<b>Provenance &amp; honesty note.</b> Every performance figure in this dossier is transcribed verbatim from "
      "the supplied backtest report (run " + RUN["run_id"] + "). Where a metric the review asks for is <b>not present "
      "in that run</b>, it is explicitly flagged as UNAVAILABLE rather than estimated. Engine mechanics are described "
      "from the actual source code.", small)
    E.append(PageBreak())

    # -------- PART 1 --------
    P("Part 1 — Project Overview", h1); rule()
    P("<b>What Ananta is.</b> Ananta is a single-operator algorithmic trading operating system for spot crypto. It "
      "researches, validates, paper-trades and (optionally) live-executes a small set of independent technical alpha "
      "models, wrapped in a deterministic risk layer and an AI copilot for analysis and reporting.")
    P("<b>Primary goal.</b> Trade with evidence, not assumptions: no strategy reaches real capital until it has been "
      "validated offline (Research Lab) and paper-traded. The engine is deliberately technical-first.")
    P("<b>Core philosophy.</b> (1) Entries and exits are <b>pure, deterministic compute</b> — zero LLM involvement, so "
      "behaviour is reproducible and auditable. (2) Independent alpha models with distinct 'personalities' rather than "
      "one monolithic strategy. (3) Regime-gating decides which model may even act. (4) Risk is owned by a separate, "
      "priority-arbitrated exit engine, not by the entry logic.")
    tbl([["Aspect", "Detail (this build)"],
         ["Supported exchange", "Kraken (LIVE via CCXT); Coinbase selectable"],
         ["Assets (this run)", "BTC/USD, SOL/USD, ETH/USD (spot)"],
         ["Timeframes", "1h live-execution baseline; 15m / 30m for comparison; 4h/1d used internally for regime & zones"],
         ["Order types", "Market/limit-style fills; PAPER post-only maker simulation; LIVE limit with slippage cap"],
         ["Workflows", "Research Lab (offline) → Paper trading → Live (interlocked)"],
         ["AI components", "Macro-context (Gemini), Ask-Ananta copilot, weekly review — ADVISORY only, never trade-gating"],
         ["Risk philosophy", "Deterministic kill-switches + priority-arbitrated Universal Exit Engine"]],
        [42 * mm, 108 * mm])
    gap(4)
    P("<b>High-level architecture (data → decision → execution).</b>", h3)
    P("Market data (CCXT/Kraken OHLCV + orderbook) → indicator &amp; regime layer → regime router (which model may act) "
      "→ independent alpha models (Hunter / Squeeze / Continuation) produce a technical entry signal → risk fusion &amp; "
      "kill-switches → position sizing → order execution (paper/live) → position watcher + Universal Exit Engine (modules "
      "A–F) → trade ledger &amp; analytics → AI reporting. A separate Research Lab replays the identical live functions "
      "over history for validation.", small)

    E.append(PageBreak())
    # -------- PART 2 --------
    P("Part 2 — Trading Engine Architecture", h1); rule()
    P("The live loop runs on a fixed cadence (default 90s trading loop; position watcher on its own interval). The "
      "offline Lab replays the <b>exact same functions</b> (classify_regime, router, evaluate_primary/squeeze/continuation, "
      "evaluate_exit_engine) bar-by-bar — only the clock and data source differ, giving live/backtest parity.")
    P("<b>What happens on every new candle:</b>", h3)
    B(["<b>Data ingestion</b> — pull/append OHLCV (1h execution series; 4h/1d for regime &amp; support zones) and an "
       "orderbook snapshot (spread + imbalance) for the risk gate.",
       "<b>Indicators</b> — EMA20/50/200, RSI14, MACD, ATR14, ADX14, Bollinger bandwidth are computed causally on the "
       "trailing analysis window (750 bars, matching live EXEC_BARS_LIMIT).",
       "<b>Regime</b> — classify_regime() labels the market (TREND_UP / TREND_DOWN / RANGE / COMPRESSION / REVERSAL / NEUTRAL).",
       "<b>Routing</b> — the regime decides which alpha model(s) are ALLOWED to evaluate (hunter_allowed / squeeze_allowed "
       "/ continuation_allowed).",
       "<b>Signal generation</b> — the first allowed model that fires wins; it returns an entry profile + structural stop + confidence.",
       "<b>Validation / risk fusion</b> — kill-switches (spread, daily-loss, manual) and a tri-state circuit breaker; only an "
       "existential VETO can block. Macro/news/sentiment can NEVER create or block an entry.",
       "<b>Position sizing</b> — fixed USD lot (this run: $75) capped at 95% of cash, or legacy %-of-equity scaled by confidence.",
       "<b>Execution</b> — entry fills at next-bar OPEN in the backtest (no look-ahead); taker fee + 0.05%/leg slippage on every leg.",
       "<b>Monitoring &amp; exit</b> — the position watcher runs the Universal Exit Engine (modules A–F) each tick; a pessimistic "
       "intrabar LOW pass catches stops/trails first, then a CLOSE pass handles upside modules.",
       "<b>Performance tracking</b> — the closing leg records MFE/MAE, exit module, best/worst achievable exit, hold time, "
       "trade-quality score into the ledger for analytics."])

    E.append(PageBreak())
    # -------- PART 3 --------
    P("Part 3 — Strategy Framework", h1); rule()
    P("Ananta ships <b>three core alpha models</b> (deterministic, hand-built) plus a <b>declarative catalog</b> of eight "
      "indicator strategies. All eleven were selected in this run's configuration.", body)
    E.append(Paragraph("IMPORTANT AUDIT CAVEAT — The offline Lab backtester's entry scan (lab/backtest.py::_scan_entry) "
                       "wires ONLY the three core models (hunter, squeeze, continuation). The eight declarative strategies "
                       "are registered, tunable and run in the live/paper engine, but they produced ZERO entries in this "
                       "backtest. Consequently ALL 673 trades in the supplied report originate from the three core models. "
                       "This is confirmed by the regime breakdowns, whose trade counts sum exactly to the per-symbol totals "
                       "(BTC 10+70+1+8+108=197, etc.).", note))
    gap(2)
    P("Core model — HUNTER (reversal · 'buys fear')", h3)
    B(["<b>Objective / thesis:</b> buy validated historical support after a capitulation, not a breakout.",
       "<b>Ideal:</b> deep oversold pullbacks into 1–2y support. <b>Worst:</b> trending-down knife-catches without a reset.",
       "<b>Gates (ALL required):</b> historical support zone · pullback confirmation (no green-candle chase) · volume "
       "exhaustion (falling volume slope) · 4H RSI(14) momentum reset ≤ rsi_reset_max.",
       "<b>Entry profiles:</b> AGGRESSIVE_PULLBACK / STABILIZED_REVERSAL / DEEP_DISCOUNT.",
       "<b>Structural stop:</b> 0.4×ATR below the structure low. Rejection reasons are logged (no-zone, chasing, "
       "volume-not-exhausted, rsi-not-reset)."])
    P("Core model — SQUEEZE (volatility expansion · 'buys expansion')", h3)
    B(["<b>Trigger:</b> Bollinger Bands fully inside Keltner Channels (volatility coiled).",
       "<b>Entry:</b> NOT the first breakout candle — either CONTINUATION (breakout → inside bar → break of its high) or "
       "RETEST (breakout → pull back to the 20-MA basis → reclaim).",
       "<b>Stop:</b> hard stop at the 20-period MA (Bollinger basis). ATR trail thereafter."])
    P("Core model — CONTINUATION (trend pullback · 'buys the dip in an uptrend')", h3)
    B(["<b>Trigger:</b> established uptrend — 50-EMA rising AND 20-EMA &gt; 50-EMA AND price above the 50-EMA.",
       "<b>Entry:</b> controlled pullback to the 20-EMA with volume drying up and RSI in a healthy 40–62 band (NOT the "
       "30–35 reversal zone), then a stabilising candle.",
       "<b>Structural stop:</b> below the pullback low / 50-EMA, buffered by 0.4×ATR."])
    gap(2)
    P("Declarative catalog (registered &amp; tunable; not active in this run's entries)", h3)
    dc = [["Key", "Name", "Entry logic (long-only)", "Exit logic", "Conf."]]
    from strategy.declarative_defs import DECLARATIVE
    for k, v in DECLARATIVE.items():
        er = v["spec"].get("entry_reason", "—")
        ex = "; ".join(f'{c.get("lhs")} {c.get("op")} {c.get("rhs")}' for c in v["spec"].get("exit", [])) or "(exit via risk engine)"
        dc.append([k, v["name"], er, ex, str(v["dna"].confidence)])
    tbl(dc, [24 * mm, 30 * mm, 47 * mm, 39 * mm, 10 * mm])
    P("Each declarative strategy exposes tunable parameters (periods, multipliers, thresholds) — see the config JSON "
      "export for exact defaults, bounds and the full boolean spec (indicators + entry/exit conditions).", small)
    P("Pseudocode (representative — EMA Cross): <font face='Courier'>if ema(fast) crosses_above ema(slow): enter_long(); "
      "if ema(fast) crosses_below ema(slow): exit()</font>. Every catalog strategy compiles to this same declarative "
      "form (indicators → entry conditions → exit conditions).", small)

    E.append(PageBreak())
    # -------- PART 4 & 5 --------
    P("Part 4 — Entry Decision Logic", h1); rule()
    P("Entries are <b>technical-first and conjunctive</b>: a core model fires only when ALL of its gates are simultaneously "
      "true (boolean AND), after the regime router has admitted that model. There is no weighted score that can rescue a "
      "failed gate; confidence is recorded for research but does not lower a gate. Priority order when multiple models are "
      "allowed: Hunter → Squeeze → Continuation (first trigger wins, one position at a time).")
    B(["<b>Regime filter</b> (router): e.g. Hunter is admitted in reversal/neutral regimes, Squeeze around compression→expansion, "
       "Continuation in established uptrends.",
       "<b>Trend filter:</b> EMA stack (20/50/200) + optional 4H HTF alignment (price&gt;EMA50&gt;EMA200).",
       "<b>Momentum filter:</b> RSI reset (Hunter) or RSI band (Continuation) or RSI breakout (declarative rsi-momentum).",
       "<b>Volatility filter:</b> ATR percentile &amp; Bollinger-in-Keltner coil (Squeeze) / ATR expansion (declarative).",
       "<b>Volume filter:</b> falling volume slope into support (Hunter) / volume spike on break (Squeeze).",
       "<b>Support/Resistance:</b> multi-year daily/4H horizontal zones with touch-count &amp; strength (Hunter).",
       "<b>Multi-timeframe:</b> 4h/1d used for regime &amp; zones; 1h for execution.",
       "<b>AI contribution:</b> NONE at the entry gate. Macro bias/confidence is advisory context only (see Part 14)."])
    P("Decision tree (core): regime admits model? → support/trend context valid? → pullback/coil confirmed (no chase)? → "
      "momentum reset/band ok? → volume ok? → risk gate (spread/daily-loss/veto) clear? → BUY with structural stop; else HOLD "
      "with an explicit reason code.", small)
    gap(4)
    P("Part 5 — Exit Decision Logic", h1); rule()
    P("Exits are owned by the <b>Universal Exit Engine</b>: every module is evaluated independently each tick and a single-pass "
      "priority arbitration executes the highest-priority firing module.")
    tbl([["Module", "Prio", "Action", "Trigger"],
         ["A Structural failure", "1", "EXIT_FULL", "structural stop / % stop / locked profit-floor breach"],
         ["KILL Emergency", "2", "EXIT_FULL", "existential circuit-breaker veto (hack/insolvency/reg)"],
         ["F Profit protection", "3", "TIGHTEN", "breakeven at +1R, then lock a +1% profit floor"],
         ["B Momentum exhaustion", "4", "EXIT 50%", "overbought zone + volume climax + exhaustion candle"],
         ["S Structure failure", "5", "EXIT_FULL", "lower-low AND momentum dead (RSI<50 & below 20-EMA)"],
         ["D EMA trend loss", "5", "EXIT_FULL", "close below 20-EMA / dead-cross"],
         ["C ATR trail", "6", "EXIT_FULL", "armed trailing stop = peak − X·ATR (arms at +2R)"],
         ["E Time exit", "7", "EXIT_FULL", "capital-efficiency time cap per strategy profile"]],
        [34 * mm, 10 * mm, 20 * mm, 86 * mm])
    P("<b>This run used the pure ATR exit</b> (not the full native engine): initial stop = entry − 2.5×ATR(14); once MFE ≥ 3% "
      "the stop trails at peak − 2.0×ATR and only ever tightens; exit when a bar LOW breaches the active stop. Positions still "
      "open at window end are marked out at the last close (labelled EOD). The Lab also A/B/C-tests Fixed-$ exits on the SAME "
      "entries (Part 10/11 tables).", small)

    E.append(PageBreak())
    # -------- PART 6 --------
    P("Part 6 — Risk Management System", h1); rule()
    from models import RiskSettings
    rs = RiskSettings().model_dump()

    def g(k, d="—"):
        return str(rs.get(k, d))
    B(["<b>Hard kill-switches</b> (block ALL new entries / force exit): manual kill, spread breach (spread &gt; "
       "max_spread_pct = " + g("max_spread_pct") + "%), daily-loss breach (day P&amp;L ≤ −max_daily_loss_pct = −" +
       g("max_daily_loss_pct") + "%).",
       "<b>Confidence gate:</b> min_confidence = " + g("min_confidence") + " (blocks new trades, not a hard stop).",
       "<b>Max concurrent positions:</b> " + g("max_concurrent_positions") + " (bounds = 1–20).",
       "<b>Position sizing:</b> fixed USD lot (normal $" + g("normal_lot_usd") + " / strong $" + g("strong_lot_usd") +
       "; this run $75) capped at 95% of cash; legacy path scales " + g("position_size_pct_min") + "–" +
       g("position_size_pct_max") + "% of equity by confidence.",
       "<b>Structural stop:</b> per-trade, set by the model (0.4×ATR below structure); default stop_loss_pct = " +
       g("stop_loss_pct") + "%.",
       "<b>Circuit breaker:</b> tri-state PASS / CAUTION / VETO; only existential VETO acts (sentiment/macro can never reach VETO).",
       "<b>Fees/slippage:</b> taker " + g("taker_fee_pct") + "% / maker " + g("maker_fee_pct") +
       "%; backtest applies 0.05% slippage per leg."])
    E.append(Paragraph("GAPS an auditor should note: no explicit portfolio-level max-exposure cap beyond position count "
                       "× lot; no correlation cap across BTC/ETH/SOL (highly correlated) — three independent $1,200 books "
                       "were run in parallel; no leverage (spot only); no volatility-scaled position sizing in this run "
                       "(flat $75).", note))
    P("Full numeric bounds for every tunable field are in the config JSON (risk_settings_hard_bounds).", small)

    E.append(PageBreak())
    # -------- PART 7 & 8 --------
    P("Part 7 — Backtest Configuration (this run)", h1); rule()
    tbl([["Parameter", "Value"],
         ["Run ID", RUN["run_id"]], ["Kind", "backtest (offline historical replay)"],
         ["Symbols", ", ".join(RUN["symbols"])], ["Period", RUN["period"]],
         ["Execution timeframe", "1h (15m & 30m replayed for comparison — both produced 0 trades)"],
         ["Exit method", RUN["exit_method"]],
         ["Position size", "$75 flat notional per trade"], ["Baseline capital", "$1,200 per symbol (independent books)"],
         ["Selection metric", "return_over_dd"],
         ["Commission", "RiskSettings.taker_fee_pct = " + g("taker_fee_pct") + "% per leg"],
         ["Slippage", "0.05% per leg (synthetic)"],
         ["Entry fill", "next-bar OPEN (signal on closed bar i → fill i+1)"],
         ["Exit fill", "pessimistic intrabar LOW pass then CLOSE pass"],
         ["Warm-up", "200 bars before the window (EMA200 / regime)"],
         ["Analysis lookback", "750 trailing bars fed to strategy fns (live parity)"],
         ["Look-ahead prevention", "point-in-time zones; closed-bar signals; next-bar fills"],
         ["Compounding", "realised P&L accrues to the per-symbol book (equity curve)"],
         ["Missing data / survivorship", "single continuous Kraken OHLCV series per symbol (no delisting universe)"],
         ["Randomisation", "none — fully deterministic"]],
        [50 * mm, 100 * mm])
    P("Part 8 — Complete Parameter Configuration", h1); rule()
    P("The full, machine-readable parameter set — every RiskSettings default and hard bound, ATR-exit params, exit-comparison "
      "grid, regime thresholds, entry-quality components, and every declarative strategy's tunables (EMA/RSI/MACD/ATR/Bollinger/"
      "Donchian/Keltner periods &amp; multipliers) with defaults and min/max — is provided in the companion file "
      "<b>ananta_engine_config.json</b>. Key live defaults:")
    tbl([["Field", "Default", "Field", "Default"],
         ["max_spread_pct", g("max_spread_pct"), "max_daily_loss_pct", g("max_daily_loss_pct")],
         ["min_confidence", g("min_confidence"), "max_concurrent_positions", g("max_concurrent_positions")],
         ["normal_lot_usd", g("normal_lot_usd"), "stop_loss_pct", g("stop_loss_pct")],
         ["trail_arm_pct", g("trail_arm_pct"), "trail_distance_pct", g("trail_distance_pct")],
         ["taker_fee_pct", g("taker_fee_pct"), "maker_fee_pct", g("maker_fee_pct")],
         ["rsi_reset_max", g("rsi_reset_max"), "squeeze_vol_expansion_min", g("squeeze_vol_expansion_min")]],
        [40 * mm, 25 * mm, 45 * mm, 40 * mm])

    E.append(PageBreak())
    # -------- PART 9 --------
    P("Part 9 — Trade Lifecycle (worked example)", h1); rule()
    P("Representative closed trade from the supplied report — BTC/USD trade #22:", body)
    tbl([["Stage", "Detail"],
         ["Market data", "1h BTC/USD candles; regime + support zones from 4h/1d"],
         ["Signal", "core-model trigger on closed bar (entry gates all true)"],
         ["Entry fill", "2025-10-01 13:00 UTC @ $116,332.93 (next-bar open + slippage)"],
         ["Position size", "$75 notional → 0.0006447 BTC"],
         ["Monitoring", "ATR stop = entry − 2.5×ATR; trails at peak − 2.0×ATR once MFE ≥ 3%"],
         ["Exit", "2025-10-02 05:00 UTC @ $118,381.83, module ATR"],
         ["Result", "+$0.72 net (after fees + slippage)"]],
        [34 * mm, 116 * mm])
    P("Every trade in the run is provided row-by-row in <b>ananta_trade_log.csv</b> (parsed directly from the report): "
      "trade #, entry/exit UTC, entry/exit price, size, net P&amp;L, exit module.", small)
    E.append(Paragraph("UNAVAILABLE in the supplied report's trade table (and therefore not in the CSV): per-trade strategy "
                       "attribution, entry profile, regime-at-entry, MFE/MAE, and indicator values at entry/exit. These fields "
                       "ARE captured by the engine internally (lab/backtest.py trade dicts) but were not rendered in the PDF. "
                       "The per-candle indicator CSV lets a reviewer reconstruct the indicator state at any trade timestamp.", note))

    E.append(PageBreak())
    # -------- PART 10 --------
    P("Part 10 — Performance Metrics", h1); rule()
    P("Metric definitions as computed by the Lab (lab/backtest.py::_summarize):")
    B(["<b>Total return %</b> = net realised P&amp;L / $1,200 starting book × 100.",
       "<b>Net P&amp;L</b> = Σ per-trade P&amp;L (net of taker fee + slippage on both legs).",
       "<b>Win rate</b> = winning trades / total trades.",
       "<b>Profit factor</b> = gross wins / gross losses.",
       "<b>Sharpe (per-trade)</b> = mean(trade return %) / stdev; <b>Sortino</b> uses downside deviation only. "
       "Annualisation-free (per-trade), so comparable across timeframes.",
       "<b>Max drawdown %</b> = largest peak-to-trough drop of the realised-P&amp;L equity curve (trades ordered by exit).",
       "<b>Expectancy</b> = net P&amp;L / trades. <b>MFE/MAE</b> = avg max favourable / adverse excursion %. "
       "<b>Profit left on table</b> = MFE$ − captured$. <b>Trade quality (0–100)</b> = 0.5·capture + 0.3·MAE-term + 0.2·speed."])
    P("Portfolio-level headline (this run) — three independent $1,200 books:", h3)
    net = sum(PER_SYMBOL[s]["net_pnl"] for s in PER_SYMBOL)
    tt = sum(PER_SYMBOL[s]["trades"] for s in PER_SYMBOL)
    tbl([["Metric", "BTC/USD", "SOL/USD", "ETH/USD", "Aggregate*"],
         ["Total return %", "-13.586", "-23.583", "-18.439", f"{net/3600*100:.2f}"],
         ["Net P&L $", "-163.033", "-282.994", "-221.263", f"{net:.2f}"],
         ["Trades", "197", "249", "227", str(tt)],
         ["Win rate %", "34.0", "36.5", "37.0", "—"],
         ["Profit factor", "0.33", "0.25", "0.30", "—"],
         ["Sharpe (per-trade)", "-0.149", "-0.289", "-0.217", "—"],
         ["Sortino (per-trade)", "-0.168", "-0.268", "-0.219", "—"],
         ["Max drawdown %", "1.03", "1.53", "1.28", "—"],
         ["Avg MFE %", "1.934", "2.325", "2.291", "—"],
         ["Avg MAE %", "-1.694", "-2.232", "-2.036", "—"],
         ["Total profit left $", "448.85", "717.26", "611.35", f"{448.85+717.26+611.35:.2f}"],
         ["Avg trade quality", "53.3", "51.3", "52.3", "—"]],
        [38 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm])
    P("*Aggregate = summed across the three independent $1,200 books (return = ΣnetP&amp;L / $3,600). The report itself "
      "does not present a consolidated portfolio view; win-rate/PF/Sharpe are intentionally left blank at aggregate to "
      "avoid a misleading blend.", small)

    E.append(PageBreak())
    # -------- PART 11 --------
    P("Part 11 — Strategy Performance Breakdown", h1); rule()
    E.append(Paragraph("UNAVAILABLE at the per-STRATEGY level. The supplied report aggregates all entries per SYMBOL and "
                       "breaks results down by REGIME and by EXIT MODULE — not by strategy. Because only the three core models "
                       "generated entries, per-strategy attribution exists in the run's stored data (strategy_breakdown bucket) "
                       "but was not rendered in this PDF, so it cannot be quoted here without re-reading the production database. "
                       "The closest available attributions (regime & exit module) are reproduced below.", note))
    for sym in RUN["symbols"]:
        d = PER_SYMBOL[sym]
        P(f"{sym} — regime breakdown", h3)
        rr = [["Regime", "N", "Win %", "Net P&L $"]] + [[k, str(x[0]), f"{x[1]}", f"{x[2]}"] for k, x in d["regime"].items()]
        tbl(rr, [40 * mm, 20 * mm, 25 * mm, 30 * mm])
        em = [["Exit module", "N", "Win %", "Net P&L $"]] + [[k, str(x[0]), f"{x[1]}", f"{x[2]}"] for k, x in d["exit_modules"].items()]
        tbl(em, [40 * mm, 20 * mm, 25 * mm, 30 * mm])
        P(f"<b>Verdict:</b> {d['recommendation']}", small)
        P(f"<b>Best exit engine (return/drawdown):</b> {d['best_engine']}", small)
        gap(4)

    E.append(PageBreak())
    # -------- Multi-TF + Exit comparison --------
    P("Multi-timeframe comparison", h2)
    for sym in RUN["symbols"]:
        rows = [["TF", "Trades", "Return %", "Win %", "MaxDD %", "Avg MFE %", "Avg MAE %"]]
        for tf, x in MULTI_TF[sym].items():
            rows.append([tf] + [("—" if y is None else str(y)) for y in x])
        P(sym, h3)
        tbl(rows, [18 * mm, 20 * mm, 24 * mm, 20 * mm, 22 * mm, 24 * mm, 22 * mm])
    P("Only the 1h series produced trades; 15m/30m produced none in this window — the models' edge is defined on 1h candles.", small)
    gap(4)
    P("Exit-engine A/B/C comparison (identical entries, exit is the only variable)", h2)
    for sym in RUN["symbols"]:
        rows = [["Exit config", "PF", "Win %", "Expectancy $", "Net ret %", "MaxDD %"]]
        for lab_, pf, win, exp_, ret, dd in EXIT_CMP[sym]:
            rows.append([lab_, f"{pf}", f"{win}", f"{exp_}", f"{ret}", f"{dd}"])
        P(sym, h3)
        tbl(rows, [46 * mm, 16 * mm, 18 * mm, 26 * mm, 22 * mm, 20 * mm])

    E.append(PageBreak())
    # -------- PART 12 --------
    P("Part 12 — Historical Trade Log", h1); rule()
    P(f"The complete trade log — <b>{trade_total} trades</b> "
      f"(BTC/USD {trade_counts.get('BTC/USD')} · SOL/USD {trade_counts.get('SOL/USD')} · "
      f"ETH/USD {trade_counts.get('ETH/USD')}) — is provided in <b>ananta_trade_log.csv</b>, parsed directly from the "
      "report. Columns: symbol, trade #, entry/exit UTC, entry/exit price, size, net P&amp;L $, exit module.")
    E.append(Paragraph("Fields requested by the review that are NOT in the report's trade table (strategy, direction=all-long, "
                       "SL/TP levels, indicators at entry/exit, signal confidence, entry/exit reasoning beyond the exit module, "
                       "market regime per trade, news/event) are UNAVAILABLE from this run's PDF. The per-candle indicators CSV "
                       "provides the full indicator state at every timestamp so any trade can be validated by joining on time.", note))

    E.append(PageBreak())
    # -------- PART 13 --------
    P("Part 13 — Market Regime Detection", h1); rule()
    P("classify_regime() (regime.py, pure compute) labels each bar from the asset's own trailing window using EMA20/50/200, "
      "RSI14, ADX14, ATR14 (+percentile), Bollinger bandwidth (+percentile) and crude swing structure.")
    tbl([["Regime", "Definition"],
         ["COMPRESSION", "(BBwidth pct ≤ 30 AND ATR pct ≤ 35) OR ATR pct ≤ 10 — volatility collapse"],
         ["REVERSAL", "panic (RSI ≤ 22 & ATR pct ≥ 70) OR (RSI ≤ 32 & down-stack/lower-low)"],
         ["TREND_UP", "EMA20>50>200 AND price>EMA20 AND ADX ≥ 20 AND higher-high/higher-low"],
         ["TREND_DOWN", "EMA20<50<200 AND ADX ≥ 20"],
         ["RANGE", "ADX < 20"],
         ["NEUTRAL", "none of the above"]],
        [34 * mm, 116 * mm])
    P("Priority when several conditions hold: compression &gt; reversal &gt; strong-trend &gt; range &gt; neutral. "
      "<b>Strategy switching already exists</b> at the ROUTER level (regime admits which model may act), but there is NO "
      "dynamic parameter/allocation rotation per regime — that is a clear integration point (Part 16/17). Fake-breakout, "
      "accumulation/distribution and explicit capitulation labels are not separately modelled.", small)

    gap(4)
    P("Part 14 — AI Components", h1); rule()
    B(["<b>Where AI is used:</b> (1) Macro-context engine (Gemini 3.1 Pro via the Emergent key) turns a news summary into a "
       "structured BIAS/CONFIDENCE/REASON, MD5-cached to avoid re-spend; (2) 'Ask Ananta' copilot; (3) weekly performance review.",
       "<b>Where decisions are deterministic:</b> ALL entries and exits, regime, routing, sizing and risk are pure compute "
       "(zero LLM). The AI cannot create, rescue or block a trade — risk_engine.fuse_signals is technical-first by design.",
       "<b>Limitations:</b> macro bias is advisory context only; no reinforcement learning; no LLM in the hot path.",
       "<b>Pipeline:</b> deterministic reasoning is recorded per decision (reason codes, rejections) for the analytics/research layer."])

    E.append(PageBreak())
    # -------- PART 15 --------
    P("Part 15 — Current Limitations (real-world performance risks)", h1); rule()
    B(["<b>Negative edge in this window:</b> all three symbols lost money (−13.6% / −23.6% / −18.4%) with profit factors "
       "0.25–0.33 and 34–37% win rate — the current entry+ATR-exit combination has no demonstrated edge on 1y/1h.",
       "<b>Only 3 of 11 strategies actually traded</b> in the backtest — the eight declarative strategies were selected but "
       "not wired into the offline entry scan, so the report does NOT validate them.",
       "<b>Exit gives back gains:</b> avg profit-left-on-table $2.28–$2.88/trade ($448–$717 per book) — MFE ~+1.9–2.3% but "
       "captured returns are negative; the ATR trail exits late / whipsaws (PF 0.25–0.33 vs Fixed-$ 0.56–0.73 best).",
       "<b>Execution realism:</b> 0.05%/leg slippage &amp; taker fees are modelled, but exchange latency, partial fills, "
       "orderbook depth, funding and downtime are not.",
       "<b>Whipsaw / sideways:</b> NEUTRAL + TREND_UP regimes dominate trades and are the biggest losers (BTC TREND_UP "
       "−$98.31 over 108 trades) — the models mis-fire in chop and shallow trends.",
       "<b>Correlation:</b> BTC/ETH/SOL are highly correlated; three parallel books overstate diversification.",
       "<b>Overfitting/robustness:</b> deterministic (good) but a single 1y window on 3 assets is thin; no walk-forward or "
       "Monte-Carlo in THIS run (the Lab supports both separately).",
       "<b>Indicator lag &amp; parameter sensitivity:</b> EMA/ATR/RSI are lagging; the exit-comparison shows results swing "
       "materially with the exit parameter — high sensitivity."])

    P("Part 16 — Planned Improvements (roadmap)", h1); rule()
    B(["Wire the 8 declarative strategies into the offline entry scan so the Lab can validate them (prerequisite to any "
       "multi-strategy claim).",
       "Regime-aware strategy rotation &amp; dynamic parameter selection (only trade a model in the regimes where its "
       "expectancy is positive).",
       "Dynamic / volatility-scaled position sizing (replace flat $75); risk-per-trade in R.",
       "Adaptive exits: the A/B/C test already shows Fixed-$ beats the ATR trail here — tune stop/trail per regime; consider "
       "partial profit-taking earlier to capture the $448–$717 left on the table.",
       "Walk-forward optimisation + Monte-Carlo (both exist in the Lab) as gating before promotion; Bayesian parameter search.",
       "Portfolio construction with correlation filters across BTC/ETH/SOL; news/volatility filters; orderbook-depth aware execution.",
       "Longer-term: meta strategy selection and reinforcement learning (research track)."])

    E.append(PageBreak())
    # -------- PART 17 --------
    P("Part 17 — Recommendations for the External Quantitative Reviewer", h1); rule()
    P("Focus areas, ranked by expected impact on this specific result set:")
    B(["<b>Exit optimisation first (highest ROI):</b> the ATR trail is the single worst config on 2 of 3 symbols "
       "(PF 0.25–0.33). Fixed-$ TP/SL already lifts BTC to PF 0.69 and ETH to 0.73 on identical entries. Grid/Bayesian-tune "
       "the exit per regime and re-run.",
       "<b>Entry quality &amp; regime gating:</b> TREND_UP and NEUTRAL produce the most trades and the biggest losses — "
       "tighten or disable core models in those regimes; the win rate (34–37%) needs either a higher bar or an asymmetric payoff.",
       "<b>Validate the 8 declarative strategies:</b> they are untested by this run; wire them in before any multi-strategy claim.",
       "<b>Reduce late entries / premature exits:</b> MFE ≈ +1.9–2.3% shows the move exists; capture is the problem — earlier "
       "partials + smarter trailing.",
       "<b>Robustness:</b> run walk-forward + Monte-Carlo across more assets/windows; add correlation-aware portfolio sizing.",
       "<b>Parameter sensitivity:</b> quantify sensitivity (the exit sweep already hints it is high) and prefer robust plateaus "
       "over sharp optima.",
       "<b>Data to request for a deeper audit:</b> per-trade strategy tag + indicators-at-entry (available in the engine's trade "
       "dicts / production DB), and the equity-curve series per book."])
    gap(6)
    rule()
    P("Companion artifacts (this package): <b>ananta_trade_log.csv</b> (every trade), "
      "<b>ananta_per_candle_indicators.csv</b> (" + f"{candle_rows:,}" + " rows — full indicator series with engine "
      "formulas over the identical OHLCV window), <b>ananta_engine_config.json</b> (complete machine-readable configuration). "
      "Together with the original backtest PDF they let a reviewer independently validate every trade and recommend "
      "evidence-based parameter changes.", small)

    doc = SimpleDocTemplate(os.path.join(OUT, "Ananta_Trading_Engine_Technical_Dossier.pdf"),
                            pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title="Ananta Trading Engine — Technical Dossier")
    doc.build(E)
    print("[pdf] wrote -> " + os.path.join(OUT, "Ananta_Trading_Engine_Technical_Dossier.pdf"))


if __name__ == "__main__":
    counts, total = write_trade_log()
    crows = write_per_candle()
    write_config_json()
    build_pdf(counts, total, crows)
    print("\nDONE. Files in", OUT)
    for fn in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, fn)
        print(f"  {fn}  ({os.path.getsize(p):,} bytes)")
