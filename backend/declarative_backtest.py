"""
declarative_backtest.py — replay a declarative strategy spec over historical OHLCV to
produce REAL catalog metrics (roi / win-rate / profit-factor / Sharpe / max-DD …), so
wired catalog strategies stop showing seeded numbers. Pure CPU, no network, no LLM.

Long-only spot, one position at a time, entry/exit from the spec + a hard stop — mirroring
how the live declarative path trades. Simplified vs the full FusionEngine backtest but
deterministic and honest for library display.
"""
from __future__ import annotations

import statistics

from declarative_engine import evaluate

_WARMUP = 40


def run_declarative_backtest(spec: dict, candles: list, params: dict, *,
                             lot_usd: float = 1000.0, fee_pct: float = 0.1,
                             slip_pct: float = 0.05, stop_pct: float = 8.0,
                             start_equity: float = 10000.0) -> dict:
    trades: list[dict] = []
    equity = start_equity
    peak = start_equity
    max_dd = 0.0
    in_pos = False
    entry_price = 0.0
    qty = 0.0

    n_bars = len(candles or [])
    if n_bars <= _WARMUP:
        return _metrics([], start_equity, start_equity, 0.0, n_bars)

    for i in range(_WARMUP, n_bars):
        window = candles[: i + 1]
        close = float(candles[i][4]); low = float(candles[i][3])
        sig = evaluate(spec, window, params)
        if in_pos:
            stop_price = entry_price * (1 - stop_pct / 100.0)
            exit_price = None; reason = ""
            if low <= stop_price:              # stop hit intrabar (worst-case first)
                exit_price = stop_price; reason = "stop"
            elif sig.exit:
                exit_price = close; reason = "signal"
            if exit_price is not None:
                fill = exit_price * (1 - slip_pct / 100.0)
                proceeds = qty * fill * (1 - fee_pct / 100.0)
                cost = qty * entry_price
                pnl = proceeds - cost
                equity += pnl
                trades.append({"pnl": pnl, "ret_pct": (pnl / cost * 100.0) if cost else 0.0, "reason": reason})
                in_pos = False
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak * 100.0 if peak else 0.0)
        elif sig.entry:
            entry_price = close * (1 + slip_pct / 100.0)
            qty = lot_usd / entry_price if entry_price else 0.0
            equity -= lot_usd * fee_pct / 100.0
            in_pos = qty > 0

    return _metrics(trades, start_equity, equity, max_dd, n_bars)


def _metrics(trades, start_equity, equity, max_dd, bars) -> dict:
    n = len(trades)
    rets = [t["ret_pct"] for t in trades]
    wins = [t for t in trades if t["pnl"] > 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
    downside = [r for r in rets if r < 0]

    def _sr(sample):
        if len(sample) > 1:
            sd = statistics.pstdev(sample)
            if sd:
                return statistics.mean(rets) / sd * (len(rets) ** 0.5)
        return 0.0

    return {
        "roi": round((equity - start_equity) / start_equity * 100.0, 2),
        "win_rate": round(len(wins) / n * 100.0, 1) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else round(gross_win, 2),
        "sharpe": round(_sr(rets), 2),
        "sortino": round(_sr(downside), 2),
        "max_drawdown": round(max_dd, 2),
        "avg_trade": round(statistics.mean(rets), 3) if rets else 0.0,
        "trade_count": n,
        "bars": bars,
    }
