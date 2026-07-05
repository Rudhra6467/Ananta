"""
lab/backtest.py — deterministic historical replay engine (Research Lab, Increment 1).

PARITY GUARANTEE: this reuses the EXACT live functions — classify_regime, route,
evaluate_primary (Hunter), evaluate_squeeze, evaluate_exit_engine (Universal Exit
Engine). No forked "backtest_*" logic. Only the data source and the clock differ.

Execution model (conservative / no look-ahead):
  * Signals are evaluated on CLOSED bars up to index i; entry fills at bar i+1 OPEN.
  * Exits: a pessimistic intrabar pass feeds the bar LOW to catch stop / trail hits
    first (filled at the breached level), then a bar-CLOSE pass handles the upside
    modules (Profit-Protection tighten, Momentum partial, EMA/Time exits).
  * Taker fee + slippage applied to every leg.
  * Module E / EMA settle-gate age off the SIMULATED bar clock (injected `now`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from exit_engine import (
    ACT_EXIT_FULL, ACT_EXIT_PARTIAL, ACT_NONE, ACT_TIGHTEN,
    PARTIAL_FRACTION, evaluate_exit_engine, get_profile,
)
from dataclasses import replace as _dc_replace
from levels import compute_levels, nearest_support
from models import Position, Portfolio, RiskSettings
from primary_layer import evaluate_primary
from regime import classify_regime
from setup_classifier import ema, atr
from router import continuation_allowed, hunter_allowed, squeeze_allowed
from squeeze import evaluate_squeeze
from continuation import evaluate_continuation
from lab import data_store

logger = logging.getLogger("ananta.lab.backtest")

_O, _H, _L, _C, _V = 1, 2, 3, 4, 5
WARMUP_BARS = 200          # EMA200 / regime need deep history before the test window
ANALYSIS_LOOKBACK = 750    # trailing 1h bars fed to strategy fns — MATCHES live (EXEC_BARS_LIMIT=750)
SLIPPAGE_PCT = 0.05        # per-leg synthetic slippage (%)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _trade_quality(return_pct: float, mfe_pct: float, mae_pct: float, hold_h: float) -> float:
    """v1 composite 0..100: capture of the favourable move, drawdown penalty, speed."""
    capture = max(0.0, min(1.0, return_pct / mfe_pct)) if mfe_pct and mfe_pct > 0 else 0.0
    mae_term = max(0.0, min(1.0, 1.0 - abs(mae_pct) / 10.0))
    hold_eff = max(0.0, min(1.0, 1.0 - hold_h / 240.0))
    return round(100.0 * (0.5 * capture + 0.3 * mae_term + 0.2 * hold_eff), 1)


ALL_STRATEGIES = ("hunter", "squeeze", "continuation")

# Default ATR-exit parameters (used when exit_method == "atr" and the caller omits a field).
ATR_EXIT_DEFAULTS = {"multiplier": 2.5, "period": 14, "trail_activation_pct": 3.0, "trail_distance": 2.0}


def run_backtest(
    symbol: str,
    start_ms: int,
    end_ms: int,
    settings: RiskSettings | None = None,
    setting_overrides: dict | None = None,
    profile_overrides: dict | None = None,
    timeframe: str = "1h",
    strategies: list | tuple | set | None = None,
    exit_method: str = "fixed",
    target_profit: float = 5.0,
    target_loss: float = 4.0,
    atr_params: dict | None = None,
) -> dict:
    """Replay one symbol over [start_ms, end_ms] on `timeframe` candles.

    `timeframe` selects the execution candle series (1h = live parity; 15m/30m used
    for the multi-timeframe comparison in the Lab report).
    `setting_overrides` patches RiskSettings fields (stop_loss_pct, trail_arm_pct,
    rsi_reset_max, ... — Option B / sweeps on entry & risk params).
    `profile_overrides` = {strategy: {field: value}} patches the exit StrategyProfile
    per strategy (e.g. {"squeeze": {"trail_atr_mult": 2.0}}). Both keep live behaviour
    unchanged when omitted.
    """
    s = settings or RiskSettings()
    if setting_overrides:
        for k, v in setting_overrides.items():
            if hasattr(s, k):
                setattr(s, k, v)

    allowed = {x.lower() for x in strategies} if strategies else set(ALL_STRATEGIES)
    # normalise exit method: legacy "engine" == "native" (full Universal Exit Engine)
    if exit_method == "engine":
        exit_method = "native"
    atrp = {**ATR_EXIT_DEFAULTS, **(atr_params or {})}
    bars = data_store.load_candles(symbol, timeframe)
    daily = data_store.load_candles(symbol, "1d")
    if len(bars) < WARMUP_BARS + 5:
        return {"error": f"insufficient_{timeframe}_history", "symbol": symbol, "have": len(bars)}

    start_idx = next((i for i, b in enumerate(bars) if b[0] >= start_ms), None)
    end_idx = next((i for i, b in enumerate(bars) if b[0] > end_ms), len(bars))
    if start_idx is None or start_idx < WARMUP_BARS:
        return {"error": "window_before_warmup", "symbol": symbol,
                "need_warmup_bars": WARMUP_BARS, "start_idx": start_idx}

    lot = float(s.normal_lot_usd)
    cash = float(Portfolio().starting_balance)
    pos: Position | None = None
    trades: list[dict] = []
    equity_curve: list[float] = []
    peak_equity = cash
    max_dd = 0.0
    zone_cache: dict[int, list[dict]] = {}

    def _zones_at(ts_ms: int, hwin: list) -> list[dict]:
        day = ts_ms // 86_400_000
        if day not in zone_cache:
            d_bars = [d for d in daily if d[0] <= ts_ms][-ANALYSIS_LOOKBACK:]  # point-in-time, no look-ahead
            zone_cache[day] = compute_levels(d_bars, hwin) if d_bars else []
        return zone_cache[day]

    # per-position scratch (one position open at a time): entry confidence + ATR-exit stop state
    pmeta = {"confidence": None, "atr_stop": None, "armed": False}

    def _replay(qty: float, pnl: float) -> dict:
        """Trade-replay analytics: $ position size, MFE/MAE in $, captured vs left-on-table."""
        mfe_usd = (pos.peak_price - pos.avg_cost) * qty
        mae_usd = (pos.trough_price - pos.avg_cost) * qty
        return {
            "position_size_usd": round(pos.avg_cost * qty, 2),
            "mfe_usd": round(mfe_usd, 4), "mae_usd": round(mae_usd, 4),
            "captured_pnl": round(pnl, 4),
            "profit_left_usd": round(max(0.0, mfe_usd - pnl), 4),
            "confidence": pmeta.get("confidence"),
        }

    def _close(exit_price: float, module, reason, ts, frac: float):
        nonlocal cash, pos
        qty = pos.quantity * frac
        fill = exit_price * (1.0 - SLIPPAGE_PCT / 100.0)
        fee = qty * fill * (s.taker_fee_pct / 100.0)
        gross = (fill - pos.avg_cost) * qty
        pnl = gross - fee - pos.fee_paid_buy * frac
        cash += qty * fill - fee
        pos.fee_paid_buy *= (1.0 - frac)
        pos.quantity -= qty
        hold_h = max(0.0, (ts - _entry_ms[0]) / 3_600_000.0)
        ret_pct = (fill - pos.avg_cost) / pos.avg_cost * 100.0
        trades.append({
            "symbol": symbol, "strategy": pos.strategy, "entry_profile": pos.entry_profile,
            "regime_at_entry": pos.regime_at_entry, "exit_module": module, "exit_reason": reason,
            "entry_price": round(pos.avg_cost, 8), "exit_price": round(fill, 8),
            "qty": round(qty, 8), "pnl": round(pnl, 6), "return_pct": round(ret_pct, 4),
            "mfe_pct": pos.mfe_pct, "mae_pct": pos.mae_pct,
            "potential_best_exit": round(pos.peak_price, 8), "potential_worst_exit": round(pos.trough_price, 8),
            "entry_ts": pos.entry_timestamp, "exit_ts": _iso(ts), "hold_hours": round(hold_h, 2),
            "partial": frac < 1.0,
            "trade_quality_score": _trade_quality(ret_pct, pos.mfe_pct, pos.mae_pct, hold_h),
            **_replay(qty, pnl),
        })

    _entry_ms = [0]

    def _close_fixed(fill: float, module, reason, ts):
        """Fixed-$ target exit: close the FULL position at an exact limit-style fill that nets
        the requested profit/loss (after entry+exit fees). Used when exit_method == 'fixed'."""
        nonlocal cash, pos
        qty = pos.quantity
        fee = qty * fill * (s.taker_fee_pct / 100.0)
        pnl = (fill - pos.avg_cost) * qty - fee - pos.fee_paid_buy
        cash += qty * fill - fee
        hold_h = max(0.0, (ts - _entry_ms[0]) / 3_600_000.0)
        ret_pct = (fill - pos.avg_cost) / pos.avg_cost * 100.0
        trades.append({
            "symbol": symbol, "strategy": pos.strategy, "entry_profile": pos.entry_profile,
            "regime_at_entry": pos.regime_at_entry, "exit_module": module, "exit_reason": reason,
            "entry_price": round(pos.avg_cost, 8), "exit_price": round(fill, 8),
            "qty": round(qty, 8), "pnl": round(pnl, 6), "return_pct": round(ret_pct, 4),
            "mfe_pct": pos.mfe_pct, "mae_pct": pos.mae_pct,
            "potential_best_exit": round(pos.peak_price, 8), "potential_worst_exit": round(pos.trough_price, 8),
            "entry_ts": pos.entry_timestamp, "exit_ts": _iso(ts), "hold_hours": round(hold_h, 2),
            "partial": False,
            "trade_quality_score": _trade_quality(ret_pct, pos.mfe_pct, pos.mae_pct, hold_h),
            **_replay(qty, pnl),
        })
        pos.quantity = 0.0

    use_fixed = exit_method == "fixed"
    use_atr = exit_method == "atr"
    atr_mult = float(atrp["multiplier"])
    atr_period = int(atrp["period"])
    atr_trail_act = float(atrp["trail_activation_pct"])
    atr_trail_dist = float(atrp["trail_distance"])

    for i in range(start_idx, end_idx):
        bar = bars[i]
        window = bars[max(0, i + 1 - ANALYSIS_LOOKBACK): i + 1]   # bounded trailing window (parity w/ live)
        px = bar[_C]

        # ---- manage an open position on THIS bar (before considering new entries) ----
        if pos is not None:
            pos.peak_price = max(pos.peak_price, bar[_H])
            pos.trough_price = min(pos.trough_price, bar[_L]) if pos.trough_price else bar[_L]
            pos.mfe_pct = round((pos.peak_price - pos.avg_cost) / pos.avg_cost * 100, 4)
            pos.mae_pct = round((pos.trough_price - pos.avg_cost) / pos.avg_cost * 100, 4)
            now_dt = _dt(bar[0])

            if use_fixed:
                # Fixed-$ target exit: compute the exact fill prices that net +target_profit /
                # -target_loss (after fees), then trigger when the bar's range reaches them.
                # Loss checked first (pessimistic) in case a bar spans both levels.
                taker = s.taker_fee_pct / 100.0
                denom = pos.quantity * (1.0 - taker)
                base = pos.fee_paid_buy + pos.avg_cost * pos.quantity
                tp_fill = (target_profit + base) / denom
                sl_fill = (base - target_loss) / denom
                if bar[_L] <= sl_fill:
                    _close_fixed(sl_fill, "FIXED_SL", "FIXED_TARGET_LOSS", bar[0])
                    pos = None
                elif bar[_H] >= tp_fill:
                    _close_fixed(tp_fill, "FIXED_TP", "FIXED_TARGET_PROFIT", bar[0])
                    pos = None
            elif use_atr:
                # Pure ATR exit: fixed initial stop = entry - mult*ATR(entry); once the trade
                # is up >= trail_activation %, trail a stop at peak - trail_distance*ATR. Only
                # tightens (never loosens). Exit when the bar LOW breaches the active stop.
                highs = [b[_H] for b in window]
                lows = [b[_L] for b in window]
                closes = [b[_C] for b in window]
                atr_val = atr(highs, lows, closes, atr_period)[-1] if len(closes) >= 2 else None
                stop = pmeta["atr_stop"]
                if stop is None and atr_val:
                    stop = pos.avg_cost - atr_mult * atr_val
                    pmeta["atr_stop"] = stop
                if atr_val and pos.mfe_pct >= atr_trail_act:
                    trail_stop = pos.peak_price - atr_trail_dist * atr_val
                    if stop is None or trail_stop > stop:
                        stop = trail_stop
                        pmeta["atr_stop"] = stop
                        pmeta["armed"] = True
                if stop is not None and bar[_L] <= stop:
                    reason = "ATR_TRAIL_STOP" if pmeta["armed"] else "ATR_INITIAL_STOP"
                    _close(stop, "ATR", reason, bar[0], 1.0)
                    pos = None
            else:
                # per-strategy exit-profile override (sweeps): patch the live profile
                pos_profile = None
                if profile_overrides and pos.strategy in profile_overrides:
                    pos_profile = _dc_replace(get_profile(pos.strategy), **profile_overrides[pos.strategy])

                # pessimistic pass 1: feed the LOW to catch hard-stop / trail breaches
                d_low = evaluate_exit_engine(pos, bar[_L], window, s, now=now_dt, profile_override=pos_profile)
                if d_low.action == ACT_EXIT_FULL and d_low.module in ("A", "C", "KILL"):
                    lvl = d_low.stop_price if d_low.stop_price is not None else bar[_L]
                    _close(lvl, d_low.module, d_low.exit_reason, bar[0], 1.0)
                    pos = None
                else:
                    # pass 2: bar CLOSE handles upside modules (F tighten, B partial, D, E)
                    d = evaluate_exit_engine(pos, px, window, s, now=now_dt, profile_override=pos_profile)
                    if d.action == ACT_TIGHTEN and d.new_floor:
                        pos.locked_profit_floor = d.new_floor
                    elif d.action == ACT_EXIT_PARTIAL:
                        pos.momentum_partial_taken = True
                        _close(px, d.module, d.exit_reason, bar[0], PARTIAL_FRACTION)
                        if pos.quantity <= 1e-12:
                            pos = None
                    elif d.action == ACT_EXIT_FULL:
                        _close(px, d.module, d.exit_reason, bar[0], 1.0)
                        pos = None

        # ---- entry evaluation on closed bar i -> fill at bar i+1 OPEN ----
        if pos is None and i + 1 < len(bars):
            regime = classify_regime(window)
            strategy = entry_profile = struct_stop = None
            _conf = None
            if "hunter" in allowed and hunter_allowed(regime.regime):
                zones = _zones_at(bar[0], window)
                # WS1 parity: multi-timeframe trend filter (4h EMA50 > EMA200) — same gate as live.
                _htf = None
                if s.htf_trend_enabled:
                    _wc = [b[_C] for b in window]
                    if len(_wc) >= 200:
                        _e50 = ema(_wc, 50)[-1]
                        _e200 = ema(_wc, 200)[-1]
                        _htf = (_wc[-1] > _e50 > _e200)
                    else:
                        _htf = False
                sig = evaluate_primary(symbol, px, window, zones, s, regime=regime, htf_trend_aligned=_htf)
                if sig.triggered:
                    strategy, entry_profile, struct_stop = "hunter", sig.entry_profile, sig.structural_stop
                    _conf = getattr(sig, "confidence", None) or getattr(sig, "score", None)
            if strategy is None and "squeeze" in allowed and squeeze_allowed(regime.regime):
                sq = evaluate_squeeze(window)
                if sq.triggered:
                    strategy, entry_profile, struct_stop = "squeeze", sq.entry_profile, sq.stop_20ma
                    _conf = getattr(sq, "confidence", None) or getattr(sq, "score", None)
            if strategy is None and "continuation" in allowed and s.continuation_enabled and continuation_allowed(regime.regime):
                ct = evaluate_continuation(window, s, regime=regime)
                if ct.triggered:
                    strategy, entry_profile, struct_stop = "continuation", ct.entry_profile, ct.structural_stop
                    _conf = getattr(ct, "confidence", None) or getattr(ct, "score", None)
            if strategy is not None:
                fill = bars[i + 1][_O] * (1.0 + SLIPPAGE_PCT / 100.0)
                qty = lot / fill
                fee = qty * fill * (s.taker_fee_pct / 100.0)
                cash -= qty * fill + fee
                _entry_ms[0] = bars[i + 1][0]
                pmeta.update(confidence=(round(_conf, 3) if isinstance(_conf, (int, float)) else None),
                             atr_stop=None, armed=False)
                pos = Position(
                    symbol=symbol, quantity=qty, avg_cost=fill, peak_price=fill, trough_price=fill,
                    fee_paid_buy=fee, entry_timestamp=_iso(bars[i + 1][0]),
                    structural_stop=struct_stop, strategy=strategy, entry_profile=entry_profile,
                    regime_at_entry=regime.regime,
                )

        # ---- equity curve + drawdown ----
        eq = cash + (pos.quantity * px if pos else 0.0)
        equity_curve.append(round(eq, 2))
        peak_equity = max(peak_equity, eq)
        if peak_equity > 0:
            max_dd = max(max_dd, (peak_equity - eq) / peak_equity * 100.0)

    # force mark-out of any still-open position at the last close (for reporting)
    if pos is not None:
        _close(bars[end_idx - 1][_C], "EOD", "END_OF_WINDOW", bars[end_idx - 1][0], 1.0)
        pos = None

    return _summarize(symbol, start_ms, end_ms, s, trades, equity_curve, max_dd, timeframe,
                      exit_method=exit_method, target_profit=target_profit, target_loss=target_loss,
                      lot=lot, atrp=atrp)


def _exit_method_label(exit_method: str, target_profit: float, target_loss: float, atrp: dict | None = None) -> str:
    if exit_method == "fixed":
        return f"Fixed $ Target (TP ${target_profit:g} / SL ${target_loss:g})"
    if exit_method == "atr":
        a = atrp or ATR_EXIT_DEFAULTS
        return (f"ATR Exit (×{a['multiplier']:g} stop, {int(a['period'])}p, "
                f"arm {a['trail_activation_pct']:g}%, trail ×{a['trail_distance']:g})")
    return "Native Strategy Exit (Universal Engine)"


def _summarize(symbol, start_ms, end_ms, s, trades, equity_curve, max_dd, timeframe="1h",
               exit_method="fixed", target_profit=5.0, target_loss=4.0, lot=75.0, atrp=None) -> dict:
    closed = [t for t in trades if not t["partial"]] or trades
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    net = sum(t["pnl"] for t in trades)
    start_cap = float(Portfolio().starting_balance)
    rets = [t["return_pct"] for t in trades]
    mfes = [t["mfe_pct"] for t in trades if t["mfe_pct"] is not None]
    maes = [t["mae_pct"] for t in trades if t["mae_pct"] is not None]

    def _bucket(key):
        out: dict[str, dict] = {}
        for t in trades:
            k = t.get(key) or "—"
            g = out.setdefault(k, {"n": 0, "wins": 0, "net": 0.0})
            g["n"] += 1; g["wins"] += 1 if t["pnl"] > 0 else 0; g["net"] += t["pnl"]
        return {k: {"n": v["n"], "win_pct": round(v["wins"] / v["n"] * 100, 1),
                    "net_pnl": round(v["net"], 4)} for k, v in out.items()}

    # Sharpe / Sortino computed on per-trade returns (annualisation-free, comparable
    # across timeframes since it's per-trade risk-adjusted return).
    sharpe = sortino = None
    if len(rets) >= 2:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
        sd = var ** 0.5
        sharpe = round(mean_r / sd, 3) if sd > 0 else None
        downside = [r for r in rets if r < 0]
        if downside:
            dvar = sum(r ** 2 for r in downside) / len(downside)
            dsd = dvar ** 0.5
            sortino = round(mean_r / dsd, 3) if dsd > 0 else None
    win_rate = round(len(wins) / n * 100, 1) if n else 0.0
    total_ret = round(net / start_cap * 100, 3) if start_cap else 0.0
    profit_factor = None
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 2)

    return {
        "symbol": symbol, "start_ms": start_ms, "end_ms": end_ms,
        "timeframe": timeframe,
        "exit_method": exit_method,
        "exit_method_label": _exit_method_label(exit_method, target_profit, target_loss, atrp),
        "target_profit": target_profit,
        "target_loss": target_loss,
        "position_size_usd": round(lot, 2),
        "target_profit_pct": round(target_profit / lot * 100, 2) if lot else None,
        "target_loss_pct": round(target_loss / lot * 100, 2) if lot else None,
        "atr_params": (atrp if exit_method == "atr" else None),
        "starting_capital": start_cap,
        "ending_capital": round(equity_curve[-1], 2) if equity_curve else start_cap,
        "total_return_pct": total_ret,
        "net_pnl": round(net, 4),
        "trades": n,
        "win_rate_pct": win_rate,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": profit_factor,
        "avg_return_pct": round(sum(rets) / len(rets), 3) if rets else 0.0,
        "avg_mfe_pct": round(sum(mfes) / len(mfes), 3) if mfes else None,
        "avg_mae_pct": round(sum(maes) / len(maes), 3) if maes else None,
        "avg_profit_left_usd": round(sum(t.get("profit_left_usd", 0) for t in trades) / n, 3) if n else None,
        "total_profit_left_usd": round(sum(t.get("profit_left_usd", 0) for t in trades), 2),
        "avg_mfe_usd": round(sum(t.get("mfe_usd", 0) for t in trades) / n, 3) if n else None,
        "avg_mae_usd": round(sum(t.get("mae_usd", 0) for t in trades) / n, 3) if n else None,
        "avg_trade_quality": round(sum(t["trade_quality_score"] for t in trades) / n, 1) if n else None,
        "exit_module_breakdown": _bucket("exit_module"),
        "regime_breakdown": _bucket("regime_at_entry"),
        "strategy_breakdown": _bucket("strategy"),
        "recommendation": _recommend(total_ret, win_rate, max_dd, sharpe, profit_factor, n),
        "trade_log": trades,
    }


def _recommend(total_ret, win_rate, max_dd, sharpe, profit_factor, n) -> str:
    """Plain-English verdict for the report — institutional-style auto-recommendation."""
    if n < 5:
        return "INSUFFICIENT SAMPLE — fewer than 5 trades; widen the window or add assets before judging."
    if total_ret > 0 and (sharpe or 0) >= 0.3 and (profit_factor or 0) >= 1.3 and max_dd <= 25:
        return (f"DEPLOY-READY — {total_ret:+.1f}% with a {win_rate}% win rate, Sharpe {sharpe}, "
                f"profit factor {profit_factor} and a contained {max_dd:.1f}% drawdown.")
    if total_ret > 0 and (profit_factor or 0) >= 1.0:
        return (f"PROMISING — profitable ({total_ret:+.1f}%) but Sharpe {sharpe}/PF {profit_factor} are thin; "
                f"optimise risk params (stop/trail) before promoting.")
    if max_dd > 30:
        return (f"TOO RISKY — {max_dd:.1f}% drawdown is excessive; tighten stops or reduce size regardless "
                f"of the {total_ret:+.1f}% return.")
    return (f"UNDERPERFORMING — {total_ret:+.1f}% at {win_rate}% win rate; the edge is weak in this window. "
            f"Re-test other timeframes or parameter presets.")
