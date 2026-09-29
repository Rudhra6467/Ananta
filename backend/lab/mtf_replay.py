"""lab/mtf_replay.py — multi-timeframe replay from the 5m base (operator grant 2026-09-29:
"5m is the base clock; any timeframe that passes the replay may make paper TAKEs").

What it does
------------
1. Reads the research 5m bars (lab5_5m.sqlite, read-only).
2. Builds 15m / 30m / 1h / 4h / 1d candles from them (UTC-aligned, complete buckets only).
3. Runs the EXISTING parity replay `lab.backtest.run_backtest` — the exact live
   hunter / squeeze / regime / router / exit-engine code — on each timeframe, with the
   LIVE settings and Strategy Profiles read (read-only) from this deployment's Mongo.
4. Writes one JSON result per (coin, timeframe) cell so an interrupted run resumes.

Laws kept
---------
* Set A only. The research law's discovery window ends 2026-08-01T00:00Z (exclusive);
  every cell is hard-capped below it. Set B (Aug 2026 onward) is never read.
* Exits = what live Hands does (`exit_method_pref`, default "native" Universal Exit Engine),
  not the Lab's per-profile fixed $ targets.
* Costs = live taker fee (RiskSettings.taker_fee_pct) + the replay's per-leg slippage.
* Nothing is written to Mongo. Candles are served from memory.

Run (from backend/):
  .venv/bin/python -m lab.mtf_replay --db <path>/lab5_5m.sqlite --out mtf_replay_out
  .venv/bin/python -m lab.mtf_replay --out mtf_replay_out --report   # summarise finished cells
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

VERSION = "mtf.replay.v1"
DISC_END_UNIX = 1785542400  # 2026-08-01T00:00Z, research law discovery_end (exclusive)
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
COINS = ["BTC", "ETH", "SOL", "ADA", "DOGE", "AVAX", "BCH", "LINK", "LTC", "XRP"]
ERAS = [("E1_to_2020", 0, 1609459200), ("E2_2021_2023", 1609459200, 1704067200), ("E3_2024_2026", 1704067200, DISC_END_UNIX)]


# ---------------------------------------------------------------------------
# Candles
# ---------------------------------------------------------------------------
def load_5m(db_path: str, coin: str) -> list[list[float]]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT event_unix, open, high, low, close, volume FROM bars "
            "WHERE instrument=? AND event_unix < ? ORDER BY event_unix",
            (f"{coin}-USD-SPOT", DISC_END_UNIX),
        ).fetchall()
    finally:
        con.close()
    return [[float(t) * 1000.0, float(o), float(h), float(lo), float(c), float(v)] for t, o, h, lo, c, v in rows]


def resample(bars_5m: list[list[float]], tf: str) -> tuple[list[list[float]], dict]:
    """Aggregate 5m bars into UTC-aligned `tf` buckets. A bucket is kept only when every one
    of its 5m slots is present, so no candle is ever partly invented or partly missing."""
    if tf == "5m":
        return bars_5m, {"buckets": len(bars_5m), "dropped_incomplete": 0}
    step = TF_SEC[tf] * 1000
    need = TF_SEC[tf] // 300
    out: list[list[float]] = []
    dropped = 0
    cur_key, cur, count = None, None, 0
    for t, o, h, lo, c, v in bars_5m:
        key = t - (t % step)
        if key != cur_key:
            if cur is not None:
                if count == need:
                    out.append(cur)
                else:
                    dropped += 1
            cur_key, cur, count = key, [key, o, h, lo, c, v], 1
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], lo)
            cur[4] = c
            cur[5] += v
            count += 1
    if cur is not None:
        if count == need:
            out.append(cur)
        else:
            dropped += 1
    return out, {"buckets": len(out), "dropped_incomplete": dropped}


# ---------------------------------------------------------------------------
# Live configuration (read-only)
# ---------------------------------------------------------------------------
def live_config() -> dict[str, Any]:
    from dotenv import load_dotenv
    from pymongo import MongoClient

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    doc = db.settings.find_one({"id": "singleton"}, {"_id": 0}) or {}
    return {"settings_doc": doc, "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ---------------------------------------------------------------------------
# One cell
# ---------------------------------------------------------------------------
def _era_stats(trades: list[dict]) -> dict[str, Any]:
    from datetime import datetime

    out = {}
    for name, lo, hi in ERAS:
        tt = []
        for t in trades:
            try:
                ts = datetime.fromisoformat(str(t.get("entry_ts")).replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            if lo <= ts < hi:
                tt.append(t)
        out[name] = _stats(tt)
    return out


def _stats(trades: list[dict]) -> dict[str, Any]:
    full = [t for t in trades if not t.get("partial")]
    pnl = [float(t.get("pnl") or 0.0) for t in trades]
    wins = sum(1 for t in full if (t.get("pnl") or 0) > 0)
    gross_win = sum(p for p in pnl if p > 0)
    gross_loss = -sum(p for p in pnl if p < 0)
    return {
        "trades": len(full),
        "wins": wins,
        "win_rate": round(wins / len(full), 4) if full else None,
        "net_pnl_usd": round(sum(pnl), 4),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "avg_return_pct": round(sum(float(t.get("return_pct") or 0) for t in full) / len(full), 4) if full else None,
    }


def run_cell(db_path: str, coin: str, tf: str, cfg: dict, out_dir: str) -> dict[str, Any]:
    out_path = Path(out_dir) / f"{coin}_{tf}.json"
    if out_path.exists():
        return json.loads(out_path.read_text())
    t0 = time.time()
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from lab import backtest, data_store
    from models import RiskSettings

    b5 = load_5m(db_path, coin)
    series = {tf: resample(b5, tf)[0], "1d": resample(b5, "1d")[0]}
    info = {k: resample(b5, k)[1] for k in {tf, "1d"}}
    data_store.load_candles = lambda symbol, timeframe, *a, **k: series.get(timeframe, [])  # memory only, never Mongo

    doc = dict(cfg["settings_doc"])
    fields = getattr(RiskSettings, "model_fields", {})
    s = RiskSettings(**{k: v for k, v in doc.items() if k in fields and v is not None})
    exit_method = getattr(s, "exit_method_pref", None) or "native"
    bars = series[tf]
    if len(bars) < backtest.WARMUP_BARS + 5:
        res = {"coin": coin, "tf": tf, "error": "insufficient_history", "have": len(bars)}
    else:
        start_ms = int(bars[backtest.WARMUP_BARS][0])
        end_ms = int(bars[-1][0])
        assert end_ms < DISC_END_UNIX * 1000, "Set B leak guard"
        r = backtest.run_backtest(
            f"{coin}/USD", start_ms, end_ms, settings=s,
            profile_overrides=doc.get("profile_overrides") or {},
            timeframe=tf, strategies=["hunter", "squeeze"],
            exit_method=exit_method, live_entry_gates=True,
        )
        trades = r.get("trade_log") or []  # "trades" is a count; entries are independent (may overlap)
        by_strat = {k: _stats([t for t in trades if t.get("strategy") == k]) for k in ("hunter", "squeeze")}
        years = max(1e-9, (end_ms - start_ms) / (365.25 * 86400 * 1000))
        res = {
            "version": VERSION, "coin": coin, "tf": tf, "exit_method": exit_method,
            "taker_fee_pct": s.taker_fee_pct, "slippage_pct_per_leg": backtest.SLIPPAGE_PCT,
            "window": {"start": backtest._iso(start_ms), "end": backtest._iso(end_ms), "years": round(years, 2)},
            "candles": info,
            "entry_signals": r.get("entries"),
            "max_drawdown_pct_independent_trades": r.get("max_drawdown_pct"),
            "all": _stats(trades),
            "by_strategy": by_strat,
            "fires_per_year": {k: round(v["trades"] / years, 2) for k, v in by_strat.items()},
            "by_era": {k: _era_stats([t for t in trades if t.get("strategy") == k]) for k in ("hunter", "squeeze")},
            "exit_modules": _count(t.get("exit_reason") for t in trades),
            "error": r.get("error"),
        }
    res["seconds"] = round(time.time() - t0, 1)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=2, default=str))
    return res


def _count(xs) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def report(out_dir: str) -> dict[str, Any]:
    cells = [json.loads(p.read_text()) for p in sorted(Path(out_dir).glob("*_*.json")) if p.name != "config_snapshot.json"]
    table: dict[str, dict[str, Any]] = {}
    for c in cells:
        if c.get("error"):
            continue
        for k in ("hunter", "squeeze"):
            row = table.setdefault(f"{k}@{c['tf']}", {"trades": 0, "wins": 0, "net_pnl_usd": 0.0, "coins": 0, "eras_positive": {}})
            st = c["by_strategy"][k]
            row["trades"] += st["trades"]
            row["wins"] += st["wins"]
            row["net_pnl_usd"] += st["net_pnl_usd"]
            row["coins"] += 1
            for era, es in c["by_era"][k].items():
                row["eras_positive"].setdefault(era, 0.0)
                row["eras_positive"][era] += es["net_pnl_usd"]
    for row in table.values():
        row["win_rate"] = round(row["wins"] / row["trades"], 4) if row["trades"] else None
        row["net_pnl_usd"] = round(row["net_pnl_usd"], 2)
        row["eras_positive"] = {k: round(v, 2) for k, v in row["eras_positive"].items()}
    return {"version": VERSION, "cells_done": len(cells), "by_strategy_tf": table}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.expanduser("~/code/ananta-decision-agent/ananta-quant-research-db/lab5_5m.sqlite"))
    ap.add_argument("--out", default="mtf_replay_out")
    ap.add_argument("--coins", default=",".join(COINS))
    ap.add_argument("--tfs", default=",".join(TIMEFRAMES))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if a.report:
        print(json.dumps(report(a.out), indent=2))
        return
    Path(a.out).mkdir(parents=True, exist_ok=True)
    snap = Path(a.out) / "config_snapshot.json"
    if snap.exists():
        cfg = json.loads(snap.read_text())  # resume with the SAME settings the run started with
    else:
        cfg = live_config()
        snap.write_text(json.dumps(cfg, indent=2, default=str))
    # heavy cells last so short timeframes report first
    order = {"4h": 0, "1h": 1, "30m": 2, "15m": 3, "5m": 4}
    cells = sorted(((c, t) for c in a.coins.split(",") for t in a.tfs.split(",")), key=lambda x: (order.get(x[1], 9), x[0]))
    print(f"{VERSION}: {len(cells)} cells, workers={a.workers}, Set A only (< 2026-08-01Z)", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_cell, a.db, c, t, cfg, a.out): (c, t) for c, t in cells}
        for f in as_completed(futs):
            c, t = futs[f]
            try:
                r = f.result()
                bs = r.get("by_strategy") or {}
                print(f"  {c:<5} {t:<4} {r.get('seconds')}s  hunter={bs.get('hunter', {}).get('trades')} "
                      f"squeeze={bs.get('squeeze', {}).get('trades')} err={r.get('error')}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  {c:<5} {t:<4} FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
    print(json.dumps(report(a.out), indent=2))


if __name__ == "__main__":
    main()
