"""Competition Demo Workspace — one-click rich, curated preview data so judges
see every screen alive instantly. Idempotent: load_demo() wipes then seeds a
deterministic demo set; reset_demo() returns a clean $1200 paper book.

Showcases the 3 REAL built-in strategies (hunter / squeeze / continuation) with
varied lifecycle statuses, ~40 closed trades, saved configs and a completed lab run.
All demo trades are tagged note='DEMO' (NOT 'DEMO_SEED', so they count in metrics).
"""
from __future__ import annotations

import contextlib
import random
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from models import Portfolio, Position, TradeLog

DEMO_NOTE = "DEMO"
_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "LINK/USD", "AAVE/USD"]
_PRICES = {"BTC/USD": 61000, "ETH/USD": 3400, "SOL/USD": 150, "LINK/USD": 18, "AAVE/USD": 240}
_SECTORS = {"BTC/USD": "Store of Value", "ETH/USD": "Layer 1", "SOL/USD": "Layer 1", "LINK/USD": "DeFi", "AAVE/USD": "DeFi"}

# per-strategy demo personality: (n_trades, win_rate, avg_win$, avg_loss$, status)
_PROFILE = {
    "hunter": {"n": 18, "wr": 0.56, "win": 9.5, "loss": -5.5, "status": "LIVE"},
    "squeeze": {"n": 14, "wr": 0.50, "win": 8.0, "loss": -6.0, "status": "PAPER"},
    "continuation": {"n": 10, "wr": 0.40, "win": 7.0, "loss": -6.5, "status": "DISABLED"},
}
_EXITS = ["ATR_TRAIL", "PROFIT_FLOOR", "STOP_LOSS", "EMA_TREND_LOSS", "TIME_EXIT", "MOMENTUM_EXHAUSTION"]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _gen_trades(rng: random.Random) -> list[dict]:
    """Deterministic closed-trade ledger spread over the last ~30 days."""
    trades: list[dict] = []
    now = datetime.now(UTC)
    for strat, p in _PROFILE.items():
        n = p["n"]
        n_wins = round(n * p["wr"])
        win_flags = [True] * n_wins + [False] * (n - n_wins)
        rng.shuffle(win_flags)
        for i in range(n):
            sym = rng.choice(_SYMBOLS)
            base_price = _PRICES[sym]
            win = win_flags[i]
            pnl = round(rng.uniform(0.5, 1.6) * (p["win"] if win else p["loss"]), 2)
            entry_dt = now - timedelta(days=rng.uniform(1, 30), hours=rng.uniform(0, 20))
            hold_s = rng.uniform(3, 60) * 3600
            exit_dt = entry_dt + timedelta(seconds=hold_s)
            entry_price = round(base_price * rng.uniform(0.97, 1.03), 4)
            ret_pct = round(pnl / max(1.0, abs(p["win"])) * (2.1 if win else -1.8), 2)
            exit_price = round(entry_price * (1 + ret_pct / 100.0), 4)
            qty = round(75.0 / entry_price, 8)
            t = TradeLog(
                timestamp=_iso(exit_dt), symbol=sym, side="SELL", quantity=qty,
                price=exit_price, notional=round(qty * exit_price, 2), mode="PAPER",
                confidence=round(rng.uniform(0.72, 0.95), 2), pnl=pnl,
                fee_usd=round(qty * exit_price * 0.0025, 4), note=DEMO_NOTE,
                exit_reason=rng.choice(_EXITS), exit_module=rng.choice(["A", "C", "F", "D", "E", "B"]),
                sector=_SECTORS[sym], volatility_regime=rng.choice(["NORMAL", "LOW_COMPRESSION", "HIGH_PANIC"]),
                trade_result="WIN" if win else "LOSS",
                mfe_pct=round(abs(ret_pct) + rng.uniform(0.5, 3), 2),
                mae_pct=round(-rng.uniform(0.3, 4), 2),
                entry_price=entry_price, entry_timestamp=_iso(entry_dt),
                return_pct=ret_pct, hold_seconds=round(hold_s, 0),
                strategy=strat, regime_at_entry=rng.choice(["TREND_UP", "COMPRESSION", "REVERSAL", "RANGE"]),
                entry_quality_grade=rng.choice(["A+", "A", "B", "C"]),
            )
            trades.append(t.model_dump())
    return trades


def _gen_configs() -> list[dict]:
    now = datetime.now(UTC)

    def cfg(key, ver, name, origin, stars, status, days_ago, params):
        cid = f"demo-{key}-{name.lower().replace(' ', '-')}"
        return {
            "id": cid, "tenant_id": "owner", "strategy_key": key, "strategy_version": ver,
            "name": name, "params": params, "parent_config_id": None, "origin": origin,
            "meta": {"demo": True}, "rating": {"stars": stars}, "validation_status": status,
            "created_at": _iso(now - timedelta(days=days_ago + 20)),
            "updated_at": _iso(now - timedelta(days=days_ago)),
        }

    return [
        cfg("hunter", "1.0.0", "Hunter Conservative BTC", "architect", 5, "passed", 1, {"stop_loss_pct": 8}),
        cfg("hunter", "1.0.0", "Hunter Aggressive", "optimizer", 3, "passed", 4, {"stop_loss_pct": 12}),
        cfg("squeeze", "1.0.0", "Squeeze Momentum", "user", 4, "passed", 2, {"trail_atr_mult": 2.5}),
        cfg("squeeze", "1.0.0", "Squeeze Tight", "optimizer", 2, "unvalidated", 6, {"trail_atr_mult": 1.8}),
        cfg("continuation", "1.0.0", "Continuation Trend", "user", 3, "unvalidated", 8, {"trail_atr_mult": 2.0}),
    ]


def _gen_lab_runs() -> list[dict]:
    now = datetime.now(UTC)
    return [
        {
            "id": "demo-wf-run", "kind": "walk_forward", "symbols": ["BTC/USD", "ETH/USD"],
            "period": "1y", "status": "DONE", "progress_pct": 100,
            "created_at": _iso(now - timedelta(days=2)), "finished_at": _iso(now - timedelta(days=2)),
            "git_hash": "demo", "error": None,
            "result": {"verdict": "ROBUST", "wfa_efficiency": 0.78, "oos_positive_folds": 3, "folds": 3},
        },
        {
            "id": "demo-bt-run", "kind": "backtest", "symbols": ["BTC/USD"],
            "period": "1y", "status": "DONE", "progress_pct": 100,
            "created_at": _iso(now - timedelta(days=1)), "finished_at": _iso(now - timedelta(days=1)),
            "git_hash": "demo", "error": None,
            "result": {"per_symbol": {"BTC/USD": {"total_return_pct": 14.2, "win_rate_pct": 56,
                                                  "profit_factor": 1.8, "max_drawdown_pct": -7.4}}},
        },
    ]


def _gen_portfolio(trades: list[dict]) -> dict:
    realized = round(sum(t.get("pnl", 0) for t in trades), 2)
    rng = random.Random(99)
    # two live-looking open positions for the LIVE Hunter strategy
    positions = []
    for sym in ["BTC/USD", "SOL/USD"]:
        px = _PRICES[sym]
        avg = round(px * rng.uniform(0.98, 1.0), 4)
        qty = round(75.0 / avg, 8)
        positions.append(Position(
            symbol=sym, quantity=qty, avg_cost=avg, peak_price=round(avg * 1.03, 4),
            entry_timestamp=_iso(datetime.now(UTC) - timedelta(hours=rng.uniform(5, 40))),
            fee_paid_buy=round(qty * avg * 0.0025, 4), sector=_SECTORS[sym],
            volatility_regime="NORMAL", strategy="hunter", entry_profile="STABILIZED_REVERSAL",
            entry_quality_grade="A", regime_at_entry="TREND_UP", structural_stop=round(avg * 0.9, 4),
        ).model_dump())
    p = Portfolio(
        starting_balance=1200.0, cash=round(1200.0 + realized - sum(pos["avg_cost"] * pos["quantity"] for pos in positions), 2),
        positions=positions, realized_pnl=realized,
        day_start_equity=round(1200.0 + realized - rng.uniform(2, 10), 2),
        day_start_date=datetime.now(UTC).date().isoformat(),
    ).model_dump()
    return p


async def load_demo(db: AsyncIOMotorDatabase) -> dict:
    """Wipe transient collections and seed the curated Competition Demo."""
    rng = random.Random(1337)  # deterministic
    wipe = ["trades", "reasoning", "research_log", "pending_orders", "strategy_configs",
            "strategy_meta", "lab_runs", "cooldowns", "shadow_positions", "shadow_trades",
            "stop_loss_simulation_logs", "strategy_sandbox_logs", "strategy_lab_log"]
    for c in wipe:
        with contextlib.suppress(Exception):
            await db[c].drop()

    trades = _gen_trades(rng)
    configs = _gen_configs()
    runs = _gen_lab_runs()
    meta = [{"key": k, "status": p["status"], "enabled": p["status"] != "DISABLED"} for k, p in _PROFILE.items()]
    portfolio = _gen_portfolio(trades)

    await db.trades.insert_many(trades)
    await db.strategy_configs.insert_many(configs)
    await db.lab_runs.insert_many(runs)
    await db.strategy_meta.insert_many(meta)
    await db.portfolio.replace_one({"id": "singleton"}, portfolio, upsert=True)

    return {
        "loaded": True, "trades": len(trades), "configs": len(configs),
        "runs": len(runs), "strategies": [m["key"] for m in meta],
        "realized_pnl": portfolio["realized_pnl"],
    }


_HIST_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "LINK/USD"]


async def seed_demo_history(db: AsyncIOMotorDatabase, capital: float = 25000.0,
                            enable_strategies: bool = True) -> dict:
    """Populate a realistic 3–7 day PAPER trade history + a couple of open positions
    on a fresh ``capital`` book, so the demo / App-Review account lands on a *populated*
    dashboard (non-zero P&L, a trade ledger and live analytics) instead of a blank book.

    Replaces the portfolio singleton and the trades collection. Deterministic."""
    rng = random.Random(2024)
    now = datetime.now(UTC)
    lot = max(200.0, min(capital * 0.04, 1500.0))  # ~$1k notional/trade, scaled to capital
    profiles = {"hunter": (9, 0.60), "squeeze": (7, 0.55), "continuation": (5, 0.40)}

    trades: list[dict] = []
    for strat, (n, wr) in profiles.items():
        nw = round(n * wr)
        flags = [True] * nw + [False] * (n - nw)
        rng.shuffle(flags)
        for win in flags:
            sym = rng.choice(_HIST_SYMBOLS)
            base = _PRICES[sym]
            entry_dt = now - timedelta(days=rng.uniform(0.3, 6.8), hours=rng.uniform(0, 12))
            hold_s = rng.uniform(2, 40) * 3600
            exit_dt = entry_dt + timedelta(seconds=hold_s)
            entry_price = round(base * rng.uniform(0.97, 1.03), 4)
            ret_pct = round(rng.uniform(1.2, 4.5) if win else -rng.uniform(0.8, 2.6), 2)
            exit_price = round(entry_price * (1 + ret_pct / 100.0), 4)
            qty = round(lot / entry_price, 8)
            pnl = round(qty * (exit_price - entry_price) - qty * exit_price * 0.0025 - qty * entry_price * 0.0025, 2)
            t = TradeLog(
                timestamp=_iso(exit_dt), symbol=sym, side="SELL", quantity=qty,
                price=exit_price, notional=round(qty * exit_price, 2), mode="PAPER",
                confidence=round(rng.uniform(0.72, 0.95), 2), pnl=pnl,
                fee_usd=round(qty * exit_price * 0.0025, 4), note=DEMO_NOTE,
                exit_reason=rng.choice(_EXITS), exit_module=rng.choice(["A", "C", "F", "D"]),
                sector=_SECTORS[sym], volatility_regime=rng.choice(["NORMAL", "LOW_COMPRESSION", "HIGH_PANIC"]),
                trade_result="WIN" if win else "LOSS",
                mfe_pct=round(abs(ret_pct) + rng.uniform(0.5, 2), 2), mae_pct=round(-rng.uniform(0.3, 2.5), 2),
                entry_price=entry_price, entry_timestamp=_iso(entry_dt),
                return_pct=ret_pct, hold_seconds=round(hold_s, 0), strategy=strat,
                regime_at_entry=rng.choice(["TREND_UP", "COMPRESSION", "REVERSAL", "RANGE"]),
                entry_quality_grade=rng.choice(["A+", "A", "B", "C"]),
            )
            trades.append(t.model_dump())
    realized = round(sum(t["pnl"] for t in trades), 2)

    positions = []
    for sym in ["BTC/USD", "SOL/USD"]:
        avg = round(_PRICES[sym] * rng.uniform(0.985, 1.0), 4)
        qty = round(lot / avg, 8)
        positions.append(Position(
            symbol=sym, quantity=qty, avg_cost=avg, peak_price=round(avg * 1.02, 4),
            entry_timestamp=_iso(now - timedelta(hours=rng.uniform(4, 30))),
            fee_paid_buy=round(qty * avg * 0.0025, 4), sector=_SECTORS[sym],
            volatility_regime="NORMAL", strategy="hunter", entry_profile="STABILIZED_REVERSAL",
            entry_quality_grade="A", regime_at_entry="TREND_UP", structural_stop=round(avg * 0.9, 4),
        ).model_dump())
    open_cost = sum(pos["avg_cost"] * pos["quantity"] for pos in positions)
    equity = capital + realized
    p = Portfolio(
        starting_balance=capital, cash=round(capital + realized - open_cost, 2),
        positions=positions, realized_pnl=realized,
        day_start_equity=round(equity - rng.uniform(equity * 0.002, equity * 0.01), 2),
        day_start_date=now.date().isoformat(),
    ).model_dump()

    await db.trades.delete_many({})
    await db.reasoning.delete_many({})
    if trades:
        await db.trades.insert_many(trades)
    await db.portfolio.replace_one({"id": "singleton"}, p, upsert=True)

    if enable_strategies:
        for k, status in (("hunter", "LIVE"), ("squeeze", "PAPER"), ("continuation", "PAPER")):
            await db.strategy_meta.update_one(
                {"key": k}, {"$set": {"key": k, "enabled": True, "status": status}}, upsert=True)

    return {"seeded": True, "trades": len(trades), "realized_pnl": realized,
            "open_positions": len(positions), "capital": capital}


async def demo_status(db: AsyncIOMotorDatabase) -> dict:
    n = await db.trades.count_documents({"note": DEMO_NOTE})
    return {"loaded": n > 0, "demo_trades": n}
