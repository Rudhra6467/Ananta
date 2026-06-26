"""
Standalone backtesting engine for CryptoAtlas.

Pulls historical OHLCV from Kraken via CCXT, derives technical indicators
(EMA20/50, RSI14, MACD), synthesises macro-bias signals from the indicators
(so we don't burn LLM credits replaying 300+ historical hours), simulates
microstructure (bid/ask + orderbook imbalance) from candle internals, and
runs the existing FusionEngine + RiskEngine bar-by-bar against a $100 paper
account.

Strict capital-preservation rules enforced per-trade:
  * 1% hard stop-loss
  * 2% take-profit target

End-of-run metrics: Total Net P/L, Win Rate %, Max Drawdown %, Profit Factor.

Run via CLI:
    python -m backtest --symbols BTC/USDC ETH/USDC --days 14

Or import:
    from backtest import run_backtest
    result = run_backtest("BTC/USDC", candles, ...)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import ccxt

from models import KillSwitchStatus, MarketSnapshot, Portfolio, Position, RiskSettings
from risk_engine import fuse_signals, position_size_quantity

logger = logging.getLogger("backtest")


# ─────────────────────────────────────────────────────────────────────────────
# Data collection
# ─────────────────────────────────────────────────────────────────────────────
def fetch_history(
    symbol: str,
    days: int = 14,
    timeframe: str = "1h",
    exchange_name: str = "kraken",
) -> list[list[float]]:
    """Fetch hourly OHLCV candles for the requested window.

    Returns a list of [timestamp_ms, open, high, low, close, volume].
    Raises if the symbol isn't available on the chosen exchange.
    """
    ex_cls = getattr(ccxt, exchange_name)
    ex = ex_cls({"enableRateLimit": True, "timeout": 15000})
    ex.load_markets()
    if symbol not in ex.symbols:
        raise ValueError(f"{exchange_name} does not list {symbol}")

    since = int((datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000)
    needed = days * 24 + 10  # small buffer
    out: list[list[float]] = []
    cursor = since
    while len(out) < needed:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=720)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 720:
            break
        cursor = batch[-1][0] + 1
    return out[-needed:]


# ─────────────────────────────────────────────────────────────────────────────
# Technical indicators (pure functions, deterministic, no deps beyond stdlib)
# ─────────────────────────────────────────────────────────────────────────────
def ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average. Returns a list the same length as `values`."""
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(alpha * float(v) + (1 - alpha) * out[-1])
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    """Wilder's RSI. Returns a list the same length as `values`; warmup
    indices return 50.0 (neutral)."""
    n = len(values)
    if n < period + 1:
        return [50.0] * n
    gains: list[float] = [0.0]
    losses: list[float] = [0.0]
    for i in range(1, n):
        diff = float(values[i]) - float(values[i - 1])
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    out = [50.0] * period
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    for i in range(period, n):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 1e9
        out.append(100.0 - 100.0 / (1.0 + rs))
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, list[float]]:
    e_fast = ema(values, fast)
    e_slow = ema(values, slow)
    macd_line = [a - b for a, b in zip(e_fast, e_slow, strict=True)]
    sig_line = ema(macd_line, signal)
    hist = [a - b for a, b in zip(macd_line, sig_line, strict=True)]
    return {"macd": macd_line, "signal": sig_line, "hist": hist}


def compute_indicators(candles: list[list[float]]) -> dict[str, list[float]]:
    """Compute all indicators we use for backtesting from OHLCV candles."""
    closes = [c[4] for c in candles]
    return {
        "close": closes,
        "ema20": ema(closes, 20),
        "ema50": ema(closes, 50),
        "rsi14": rsi(closes, 14),
        **macd(closes, 12, 26, 9),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic macro + microstructure (deterministic from candle data)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class MacroBiasSim:
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    reason: str


def synthesize_macro(ind: dict[str, list[float]], i: int) -> MacroBiasSim:
    """Derive a BIAS/CONFIDENCE pair from indicators for hour i.

    Heuristic (kept simple on purpose — backtesting validates the *system*, not
    the prediction skill of the LLM):
      * BULLISH  if EMA20 > EMA50 AND 50 ≤ RSI ≤ 75 AND macd_hist > 0
      * BEARISH  if EMA20 < EMA50 AND 25 ≤ RSI ≤ 50 AND macd_hist < 0
      * NEUTRAL  otherwise
    Confidence scales with the magnitude of the EMA gap and MACD histogram.
    """
    if i < 50:  # warmup period
        return MacroBiasSim("NEUTRAL", 0.0, "Warmup period, insufficient history.")
    e20 = ind["ema20"][i]
    e50 = ind["ema50"][i]
    r = ind["rsi14"][i]
    h = ind["hist"][i]
    close = ind["close"][i]
    ema_gap_pct = (e20 - e50) / e50 * 100.0 if e50 > 0 else 0.0
    hist_norm = h / close * 100.0 if close > 0 else 0.0

    bull = e20 > e50 and 50.0 <= r <= 75.0 and h > 0
    bear = e20 < e50 and 25.0 <= r <= 50.0 and h < 0

    if bull:
        # Calibration target: 2% EMA gap + 0.2% MACD-hist (as % of close) ≈ ~0.8.
        # Chop with sub-0.5% EMA gap stays at 0.1-0.3.
        conf = max(0.0, min(1.0, abs(ema_gap_pct) * 0.25 + abs(hist_norm) * 1.5))
        return MacroBiasSim(
            "BULLISH",
            round(conf, 3),
            f"EMA20>EMA50 (gap {ema_gap_pct:+.2f}%), RSI {r:.1f}, MACD hist +{h:.3f}.",
        )
    if bear:
        conf = max(0.0, min(1.0, abs(ema_gap_pct) * 0.25 + abs(hist_norm) * 1.5))
        return MacroBiasSim(
            "BEARISH",
            round(conf, 3),
            f"EMA20<EMA50 (gap {ema_gap_pct:+.2f}%), RSI {r:.1f}, MACD hist {h:.3f}.",
        )
    return MacroBiasSim(
        "NEUTRAL",
        round(min(0.3, abs(ema_gap_pct) * 0.1), 3),
        f"Mixed signals: EMA gap {ema_gap_pct:+.2f}%, RSI {r:.1f}.",
    )


def synthesize_microstructure(candle: list[float]) -> dict[str, float]:
    """Derive synthetic bid/ask/spread/imbalance from a single OHLCV bar.

    No real orderbook history is available, so we approximate:
      * spread:    half of (high-low)/close, capped — proxy for typical spread
      * bid/ask:   close ± half-spread
      * imbalance: (close - open) / max(high - low, eps)
                   → positive = buyers won the bar, negative = sellers won.
    """
    o, h, lo, c, _v = candle[1], candle[2], candle[3], candle[4], candle[5]
    rng = max(h - lo, 1e-9)
    # candle-based spread proxy capped at 0.4%
    spread_pct = min(rng / c * 100.0 * 0.05, 0.4) if c > 0 else 0.05
    spread_abs = c * spread_pct / 100.0
    bid = c - spread_abs / 2.0
    ask = c + spread_abs / 2.0
    imbalance = (c - o) / rng  # in [-1, 1]
    return {
        "price": c,
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "orderbook_imbalance": imbalance,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backtest state + run loop
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TradeRecord:
    ts_ms: int
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    notional: float
    pnl: float = 0.0
    reason: str = ""
    exit_kind: str = ""  # "TAKE_PROFIT" | "STOP_LOSS" | "MACRO_SELL"


@dataclass
class BacktestResult:
    symbol: str
    starting_balance: float
    ending_equity: float
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)  # (ts_ms, equity)
    bars: int = 0


def _mtm_equity(portfolio: Portfolio, last_close: float, symbol: str) -> float:
    pos = next((p for p in portfolio.positions if p.symbol == symbol), None)
    pos_value = pos.quantity * last_close if pos else 0.0
    return portfolio.cash + pos_value


def _backtest_kill_switches(
    snap: MarketSnapshot,
    portfolio: Portfolio,
    settings: RiskSettings,
    macro_conf: float,
    mtm_equity: float,
    day_start_equity: float,
) -> KillSwitchStatus:
    """Mark-to-market kill switch evaluation (production engine uses cost-basis
    which is fine in live but skews backtest daily-loss tracking)."""
    daily_change_pct = ((mtm_equity - day_start_equity) / day_start_equity * 100.0) if day_start_equity > 0 else 0.0
    spread_breach = snap.spread_pct > settings.max_spread_pct
    daily_loss_breach = daily_change_pct <= -settings.max_daily_loss_pct
    confidence_breach = macro_conf < settings.min_confidence
    overall_safe = not (spread_breach or daily_loss_breach)
    return KillSwitchStatus(
        spread_breach=spread_breach,
        daily_loss_breach=daily_loss_breach,
        confidence_breach=confidence_breach,
        manual_kill=False,
        overall_safe=overall_safe,
        details={
            "spread_pct": round(snap.spread_pct, 4),
            "daily_change_pct": round(daily_change_pct, 4),
            "macro_confidence": round(macro_conf, 3),
            "mtm_equity": round(mtm_equity, 4),
            "day_start_equity": round(day_start_equity, 4),
        },
    )


def run_backtest(
    symbol: str,
    candles: list[list[float]],
    settings: RiskSettings | None = None,
    stop_loss_pct: float = 1.0,
    take_profit_pct: float = 2.0,
    starting_balance: float = 100.0,
    min_confidence: float | None = None,
) -> BacktestResult:
    """Replay `candles` hour-by-hour against the production FusionEngine.

    Per-trade SL/TP enforced *before* the macro/microstructure decision each
    bar, mirroring how a real exchange would fire OCO orders.

    `min_confidence` overrides the threshold from `settings` when provided.
    The default 0.6 (production) is intentionally conservative; backtest CLI
    runs typically use 0.4 to surface enough trades for review.
    """
    settings = settings or RiskSettings()
    settings.enabled_symbols = [symbol]
    if min_confidence is not None:
        settings.min_confidence = min_confidence

    ind = compute_indicators(candles)
    portfolio = Portfolio(starting_balance=starting_balance, cash=starting_balance, day_start_equity=starting_balance)
    portfolio.day_start_date = ""  # forces day-start reset on first bar

    result = BacktestResult(
        symbol=symbol,
        starting_balance=starting_balance,
        ending_equity=starting_balance,
        bars=len(candles),
    )
    # Per-position tracking for SL/TP (one entry per open position)
    sl_tp_state: dict[str, dict[str, float]] = {}
    last_day = ""

    for i, candle in enumerate(candles):
        ts_ms = int(candle[0])
        high, low, close = candle[2], candle[3], candle[4]
        day = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).date().isoformat()
        if day != last_day:
            portfolio.day_start_equity = _mtm_equity(portfolio, close, symbol)
            portfolio.day_start_date = day
            last_day = day

        # ── 1. Check SL/TP triggers against bar's high/low BEFORE any new decision ──
        position = next((p for p in portfolio.positions if p.symbol == symbol), None)
        if position and symbol in sl_tp_state:
            tp_price = sl_tp_state[symbol]["take_profit"]
            sl_price = sl_tp_state[symbol]["stop_loss"]
            exit_kind = ""
            exit_price = 0.0
            # If a single bar hits both, assume worst case (stop-loss first) — capital preservation bias.
            if low <= sl_price:
                exit_price = sl_price
                exit_kind = "STOP_LOSS"
            elif high >= tp_price:
                exit_price = tp_price
                exit_kind = "TAKE_PROFIT"
            if exit_kind:
                qty = position.quantity
                notional = qty * exit_price
                realized = (exit_price - position.avg_cost) * qty
                portfolio.cash += notional
                portfolio.realized_pnl += realized
                portfolio.positions = [p for p in portfolio.positions if p.symbol != symbol]
                sl_tp_state.pop(symbol, None)
                result.trades.append(
                    TradeRecord(
                        ts_ms=ts_ms, symbol=symbol, side="SELL", quantity=qty, price=exit_price,
                        notional=notional, pnl=realized,
                        reason=f"{exit_kind} @ {exit_price:.2f}",
                        exit_kind=exit_kind,
                    )
                )

        # ── 2. Build snapshot + macro + decide ──
        micro = synthesize_microstructure(candle)
        snap = MarketSnapshot(
            symbol=symbol,
            price=micro["price"],
            bid=micro["bid"],
            ask=micro["ask"],
            spread_pct=micro["spread_pct"],
            orderbook_imbalance=micro["orderbook_imbalance"],
            exchange="backtest",
        )
        macro = synthesize_macro(ind, i)
        mtm = _mtm_equity(portfolio, close, symbol)
        kill = _backtest_kill_switches(
            snap=snap, portfolio=portfolio, settings=settings,
            macro_conf=macro.confidence, mtm_equity=mtm,
            day_start_equity=portfolio.day_start_equity,
        )
        has_position = any(p.symbol == symbol and p.quantity > 0 for p in portfolio.positions)
        decision, _blocked, fusion = fuse_signals(
            snapshot=snap, macro_bias=macro.bias, macro_confidence=macro.confidence,
            settings=settings, kill=kill, has_position=has_position,
        )

        # ── 3. Execute decision ──
        if decision == "BUY" and not has_position:
            qty = position_size_quantity(decision, snap, portfolio, settings, macro.confidence)
            if qty > 0 and qty * snap.ask <= portfolio.cash:
                notional = qty * snap.ask
                portfolio.cash -= notional
                portfolio.positions.append(Position(symbol=symbol, quantity=qty, avg_cost=snap.ask))
                sl_tp_state[symbol] = {
                    "stop_loss": snap.ask * (1.0 - stop_loss_pct / 100.0),
                    "take_profit": snap.ask * (1.0 + take_profit_pct / 100.0),
                }
                result.trades.append(
                    TradeRecord(
                        ts_ms=ts_ms, symbol=symbol, side="BUY", quantity=qty, price=snap.ask,
                        notional=notional, reason=fusion,
                    )
                )
        elif decision == "SELL" and has_position:
            position = next(p for p in portfolio.positions if p.symbol == symbol)
            qty = position.quantity
            notional = qty * snap.bid
            realized = (snap.bid - position.avg_cost) * qty
            portfolio.cash += notional
            portfolio.realized_pnl += realized
            portfolio.positions = [p for p in portfolio.positions if p.symbol != symbol]
            sl_tp_state.pop(symbol, None)
            result.trades.append(
                TradeRecord(
                    ts_ms=ts_ms, symbol=symbol, side="SELL", quantity=qty, price=snap.bid,
                    notional=notional, pnl=realized,
                    reason=fusion, exit_kind="MACRO_SELL",
                )
            )

        result.equity_curve.append((ts_ms, _mtm_equity(portfolio, close, symbol)))

    # Close any dangling position at the last close (mark-to-market exit, not counted as a trade)
    final_close = candles[-1][4]
    result.ending_equity = _mtm_equity(portfolio, final_close, symbol)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Metrics:
    starting_balance: float
    ending_equity: float
    net_pnl: float
    net_pnl_pct: float
    total_trades: int
    closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    max_drawdown_pct: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None  # None when no losses (undefined)


def compute_metrics(result: BacktestResult) -> Metrics:
    closed = [t for t in result.trades if t.side == "SELL"]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl < 0]
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor: float | None = (gross_profit / gross_loss) if gross_loss > 0 else None

    # Max drawdown over equity curve
    max_dd_pct = 0.0
    peak = result.starting_balance
    for _, eq in result.equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            dd_pct = (peak - eq) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd_pct)

    win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
    net = result.ending_equity - result.starting_balance
    net_pct = net / result.starting_balance * 100.0

    return Metrics(
        starting_balance=result.starting_balance,
        ending_equity=result.ending_equity,
        net_pnl=net,
        net_pnl_pct=net_pct,
        total_trades=len(result.trades),
        closed_trades=len(closed),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=win_rate,
        max_drawdown_pct=max_dd_pct,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
    )


def metrics_to_dict(m: Metrics) -> dict:
    return {
        "starting_balance": round(m.starting_balance, 4),
        "ending_equity": round(m.ending_equity, 4),
        "net_pnl": round(m.net_pnl, 4),
        "net_pnl_pct": round(m.net_pnl_pct, 4),
        "total_trades": m.total_trades,
        "closed_trades": m.closed_trades,
        "winning_trades": m.winning_trades,
        "losing_trades": m.losing_trades,
        "win_rate_pct": round(m.win_rate_pct, 2),
        "max_drawdown_pct": round(m.max_drawdown_pct, 2),
        "gross_profit": round(m.gross_profit, 4),
        "gross_loss": round(m.gross_loss, 4),
        "profit_factor": (round(m.profit_factor, 3) if m.profit_factor is not None else None),
    }


def log_metrics(symbol: str, m: Metrics) -> None:
    pf = f"{m.profit_factor:.3f}" if m.profit_factor is not None else "∞ (no losses)"
    logger.info("─" * 62)
    logger.info("BACKTEST RESULTS · %s", symbol)
    logger.info("─" * 62)
    logger.info("Starting balance : $%.2f", m.starting_balance)
    logger.info("Ending equity    : $%.2f", m.ending_equity)
    logger.info("Net P/L          : $%+.2f  (%+.2f%%)", m.net_pnl, m.net_pnl_pct)
    logger.info("Total trades     : %d  (%d closed)", m.total_trades, m.closed_trades)
    logger.info("Win rate         : %.2f%%  (%d W / %d L)", m.win_rate_pct, m.winning_trades, m.losing_trades)
    logger.info("Gross profit     : $%.4f", m.gross_profit)
    logger.info("Gross loss       : $%.4f", m.gross_loss)
    logger.info("Profit factor    : %s", pf)
    logger.info("Max drawdown     : %.2f%%", m.max_drawdown_pct)
    logger.info("─" * 62)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator + CLI
# ─────────────────────────────────────────────────────────────────────────────
def run_for_symbols(
    symbols: list[str],
    days: int = 14,
    stop_loss_pct: float = 1.0,
    take_profit_pct: float = 2.0,
    starting_balance: float = 100.0,
    exchange_name: str = "kraken",
    min_confidence: float = 0.4,
) -> dict:
    """Fetch + simulate + report for each symbol independently. Each symbol
    gets its own $100 simulated portfolio for clean per-asset comparison.

    `min_confidence` defaults to 0.4 (more permissive than production's 0.6) so
    backtests surface enough trades to review. Override to mirror production.
    """
    out: dict = {"per_symbol": {}, "exchange": exchange_name, "days": days, "min_confidence": min_confidence}
    for sym in symbols:
        t0 = time.time()
        logger.info("Fetching %d-day 1h history for %s from %s...", days, sym, exchange_name)
        candles = fetch_history(sym, days=days, exchange_name=exchange_name)
        logger.info("Fetched %d candles in %.1fs. Running simulation...", len(candles), time.time() - t0)
        result = run_backtest(
            sym, candles,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            starting_balance=starting_balance,
            min_confidence=min_confidence,
        )
        m = compute_metrics(result)
        log_metrics(sym, m)
        out["per_symbol"][sym] = {
            "metrics": metrics_to_dict(m),
            "first_ts": candles[0][0] if candles else None,
            "last_ts": candles[-1][0] if candles else None,
            "trade_count": len(result.trades),
            "trades_sample": [
                {
                    "ts_ms": t.ts_ms, "side": t.side, "qty": round(t.quantity, 8),
                    "price": round(t.price, 4), "notional": round(t.notional, 4),
                    "pnl": round(t.pnl, 4), "exit_kind": t.exit_kind,
                }
                for t in result.trades[-25:]
            ],
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Parameter sweep (Cartesian product of SL × TP per symbol)
# ─────────────────────────────────────────────────────────────────────────────
def run_sweep(
    symbol: str,
    candles: list[list[float]],
    sl_pcts: list[float],
    tp_pcts: list[float],
    starting_balance: float = 100.0,
    min_confidence: float = 0.4,
) -> list[dict]:
    """Cartesian product of (stop_loss_pct, take_profit_pct).
    Candles are passed in — we don't refetch per combination (1 fetch / N sims).
    Returns one dict per (sl, tp) cell with the full metrics block.
    """
    cells: list[dict] = []
    for sl in sl_pcts:
        for tp in tp_pcts:
            result = run_backtest(
                symbol, candles,
                stop_loss_pct=sl,
                take_profit_pct=tp,
                starting_balance=starting_balance,
                min_confidence=min_confidence,
            )
            m = compute_metrics(result)
            cells.append({"sl": sl, "tp": tp, "metrics": metrics_to_dict(m)})
    return cells


def _best_cell(cells: list[dict], metric_key: str = "net_pnl_pct") -> dict | None:
    """Pick the cell with the highest value of `metric_key`. Profit factor
    `None` (no losses) is treated as +inf — those cells win ties."""
    def keyfn(c: dict) -> float:
        v = c["metrics"].get(metric_key)
        if v is None:
            return float("inf")
        return float(v)
    return max(cells, key=keyfn) if cells else None


def _format_matrix(
    symbol: str,
    cells: list[dict],
    sl_pcts: list[float],
    tp_pcts: list[float],
    metric_key: str,
    fmt: str = "{:+.2f}",
    best: dict | None = None,
) -> list[str]:
    """Render a SL×TP matrix for a single metric as a list of log lines."""
    lookup = {(c["sl"], c["tp"]): c for c in cells}
    header_label = {
        "net_pnl_pct": "NET P/L %",
        "win_rate_pct": "WIN RATE %",
        "max_drawdown_pct": "MAX DRAWDOWN %",
        "closed_trades": "CLOSED TRADES",
        "profit_factor": "PROFIT FACTOR",
    }.get(metric_key, metric_key.upper())
    lines: list[str] = [
        f"{symbol} · {header_label}   (rows = stop-loss %, cols = take-profit %)",
    ]
    # column header
    header = "  SL \\ TP " + " ".join(f"{tp:>10.2f}%" for tp in tp_pcts)
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for sl in sl_pcts:
        row_cells: list[str] = []
        for tp in tp_pcts:
            cell = lookup.get((sl, tp))
            if cell is None:
                row_cells.append(f"{'—':>11}")
                continue
            v = cell["metrics"].get(metric_key)
            if v is None:
                txt = "    ∞    "
            else:
                txt = fmt.format(v)
            star = "★" if best and cell is best else " "
            row_cells.append(f"{txt:>10}{star}")
        lines.append(f"  {sl:>5.2f}%  " + " ".join(row_cells))
    return lines


def log_sweep_matrix(symbol: str, cells: list[dict], sl_pcts: list[float], tp_pcts: list[float]) -> None:
    """Print all four key metrics as separate matrices, highlighting the best
    cell by net P/L %."""
    best = _best_cell(cells, "net_pnl_pct")
    logger.info("═" * 70)
    logger.info("SWEEP RESULTS · %s · %d combinations", symbol, len(cells))
    logger.info("═" * 70)
    for line in _format_matrix(symbol, cells, sl_pcts, tp_pcts, "net_pnl_pct", "{:+.2f}", best):
        logger.info(line)
    logger.info("")
    for line in _format_matrix(symbol, cells, sl_pcts, tp_pcts, "win_rate_pct", "{:>5.1f}", best):
        logger.info(line)
    logger.info("")
    for line in _format_matrix(symbol, cells, sl_pcts, tp_pcts, "max_drawdown_pct", "{:>5.2f}", best):
        logger.info(line)
    logger.info("")
    for line in _format_matrix(symbol, cells, sl_pcts, tp_pcts, "closed_trades", "{:>5d}", best):
        logger.info(line)
    if best:
        m = best["metrics"]
        pf = f"{m['profit_factor']:.2f}" if m["profit_factor"] is not None else "∞"
        logger.info("")
        logger.info(
            "  BEST ★  SL=%.2f%% / TP=%.2f%%  →  net=%+.2f%%   win=%.1f%%   max-dd=%.2f%%   PF=%s   trades=%d",
            best["sl"], best["tp"], m["net_pnl_pct"], m["win_rate_pct"],
            m["max_drawdown_pct"], pf, m["closed_trades"],
        )
    logger.info("═" * 70)


def run_sweep_for_symbols(
    symbols: list[str],
    sl_pcts: list[float],
    tp_pcts: list[float],
    days: int = 14,
    starting_balance: float = 100.0,
    exchange_name: str = "kraken",
    min_confidence: float = 0.4,
) -> dict:
    """Fetch each symbol ONCE then sweep the full SL × TP grid against the
    cached candles. Returns a dict with per-symbol matrices + the best cell
    per symbol (by net P/L %)."""
    out: dict = {
        "per_symbol": {},
        "exchange": exchange_name,
        "days": days,
        "min_confidence": min_confidence,
        "sl_pcts": sl_pcts,
        "tp_pcts": tp_pcts,
    }
    for sym in symbols:
        t0 = time.time()
        logger.info("Fetching %d-day 1h history for %s from %s...", days, sym, exchange_name)
        candles = fetch_history(sym, days=days, exchange_name=exchange_name)
        logger.info("Fetched %d candles in %.1fs.  Running %d×%d sweep...",
                    len(candles), time.time() - t0, len(sl_pcts), len(tp_pcts))
        t1 = time.time()
        cells = run_sweep(
            sym, candles, sl_pcts, tp_pcts,
            starting_balance=starting_balance,
            min_confidence=min_confidence,
        )
        logger.info("Sweep finished in %.1fs (%d combinations).", time.time() - t1, len(cells))
        log_sweep_matrix(sym, cells, sl_pcts, tp_pcts)
        best = _best_cell(cells, "net_pnl_pct")
        out["per_symbol"][sym] = {
            "cells": cells,
            "best": best,
            "first_ts": candles[0][0] if candles else None,
            "last_ts": candles[-1][0] if candles else None,
        }
    return out


async def run_sweep_for_symbols_async(symbols: list[str], sl_pcts: list[float], tp_pcts: list[float], **kwargs) -> dict:
    return await asyncio.to_thread(run_sweep_for_symbols, symbols, sl_pcts, tp_pcts, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backtest", description="CryptoAtlas historical backtester")
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDC", "ETH/USDC"], help="Symbols to backtest")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days")
    parser.add_argument("--exchange", default="kraken", help="CCXT exchange id")
    parser.add_argument("--stop-loss", type=float, default=1.0, help="Stop-loss percent (default 1.0)")
    parser.add_argument("--take-profit", type=float, default=2.0, help="Take-profit percent (default 2.0)")
    parser.add_argument("--starting-balance", type=float, default=100.0)
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.4,
        help="Min macro confidence to trade. Default 0.4 (CLI). Production engine uses 0.6.",
    )
    parser.add_argument(
        "--sweep-sl",
        nargs="+",
        type=float,
        default=None,
        help="Sweep mode: list of stop-loss percentages to evaluate (e.g. 0.5 1.0 1.5 2.0). "
             "When provided, takes precedence over --stop-loss.",
    )
    parser.add_argument(
        "--sweep-tp",
        nargs="+",
        type=float,
        default=None,
        help="Sweep mode: list of take-profit percentages to evaluate (e.g. 1.5 2.0 3.0). "
             "When provided, takes precedence over --take-profit.",
    )
    parser.add_argument("--json", action="store_true", help="Also print results JSON to stdout")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    # Sweep mode triggers when EITHER --sweep-sl or --sweep-tp is provided.
    # If only one is provided, use the single scalar for the other axis.
    if args.sweep_sl or args.sweep_tp:
        sl_pcts = sorted(set(args.sweep_sl or [args.stop_loss]))
        tp_pcts = sorted(set(args.sweep_tp or [args.take_profit]))
        summary = run_sweep_for_symbols(
            args.symbols,
            sl_pcts=sl_pcts,
            tp_pcts=tp_pcts,
            days=args.days,
            starting_balance=args.starting_balance,
            exchange_name=args.exchange,
            min_confidence=args.min_confidence,
        )
    else:
        summary = run_for_symbols(
            args.symbols,
            days=args.days,
            stop_loss_pct=args.stop_loss,
            take_profit_pct=args.take_profit,
            starting_balance=args.starting_balance,
            exchange_name=args.exchange,
            min_confidence=args.min_confidence,
        )
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    return 0
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    return 0


# Async wrapper for FastAPI integration
async def run_for_symbols_async(symbols: list[str], **kwargs) -> dict:
    return await asyncio.to_thread(run_for_symbols, symbols, **kwargs)


if __name__ == "__main__":
    sys.exit(main())
