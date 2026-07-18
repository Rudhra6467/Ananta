"""
lab/runner.py — async job queue + background worker for the Research Lab.

Runs ONE research job at a time off the request path. Jobs are CPU-bound pure-compute
(no LLM, no network beyond the local SQLite store), executed in a single-worker thread
pool so the FastAPI event loop stays responsive and progress can be streamed to Mongo.

lab_runs doc:
  {id, kind, symbols, period, start_ms, end_ms, metric, folds, min_trades,
   grid?, setting_overrides?, profile_overrides?, target?, values?,
   status(QUEUED|RUNNING|DONE|FAILED), progress_pct, git_hash,
   created_at, started_at, finished_at, result, error}
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone

from lab import backtest, data_store, optimize

logger = logging.getLogger("ananta.lab.runner")

VALID_KINDS = {"backtest", "grid_search", "sensitivity", "walk_forward", "health_sweep"}
_PERIOD_MONTHS = {"1m": 1, "2m": 2, "3m": 3, "quarter": 3, "6m": 6, "1y": 12, "2y": 24}
# Extra execution timeframes reported alongside the 1h live-parity baseline (Lab PDF).
COMPARE_TIMEFRAMES = ["30m", "15m"]


def _tf_metrics(r: dict) -> dict:
    """Trim a full backtest result to the headline metrics stored per timeframe."""
    if not r or "error" in r:
        return {"error": (r or {}).get("error", "no_result")}
    return {k: r.get(k) for k in (
        "timeframe", "trades", "total_return_pct", "win_rate_pct", "max_drawdown_pct",
        "avg_return_pct", "avg_mfe_pct", "avg_mae_pct", "avg_trade_quality", "net_pnl")}


def _tf_verdict(by_tf: dict) -> dict:
    """Pick the timeframe with the best return-over-drawdown (min 1 trade). Ties broken
    by higher return. Returns {best_tf, score, reason} for the Lab report headline."""
    best = None
    for tf, m in by_tf.items():
        if not m or "error" in m or not m.get("trades"):
            continue
        ret = m.get("total_return_pct") or 0.0
        dd = max(abs(m.get("max_drawdown_pct") or 0.0), 0.1)
        score = ret / dd
        if best is None or (score, ret) > (best["score"], best["ret"]):
            best = {"best_tf": tf, "score": round(score, 3), "ret": ret,
                    "win": m.get("win_rate_pct"), "trades": m.get("trades")}
    if best is None:
        return {"best_tf": None, "reason": "no timeframe produced trades in this window"}
    return {"best_tf": best["best_tf"], "score": best["score"],
            "reason": (f'{best["best_tf"]} led on return-over-drawdown '
                       f'({best["ret"]:+.2f}% over {best["trades"]} trades, {best["win"]}% win)')}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd="/app", text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def resolve_window(symbols: list[str], period: str,
                   start_ms: int | None, end_ms: int | None) -> tuple[int | None, int | None]:
    """Map a period dropdown to a [start_ms, end_ms] window off the latest seeded candle.
    Falls back to a now-anchored window when no local history exists yet (fresh deploys)."""
    if period == "custom" and start_ms and end_ms:
        return int(start_ms), int(end_ms)
    maxes = [data_store.coverage(s, "1h")["max_ts"] for s in symbols]
    maxes = [m for m in maxes if m]
    months = _PERIOD_MONTHS.get(period, 3)
    end = min(maxes) if maxes else int(time.time() * 1000)
    start = end - months * 30 * 86_400_000
    return start, end


def _bars_per_day(tf: str) -> int:
    return {"15m": 96, "30m": 48, "1h": 24, "4h": 6, "1d": 1}.get(tf, 24)


def ensure_history(symbols: list[str], timeframes: list[str], period: str) -> dict:
    """Backfill any (symbol, timeframe) that lacks enough local candles for the requested
    window. Fresh containers / newly-added assets start with an empty candle store, so we
    fetch on demand from CCXT (Kraken -> Coinbase). Blocking network I/O — call from a
    worker thread/process. The daily series is always ensured (used for HTF context)."""
    months = _PERIOD_MONTHS.get(period, 3)
    days = months * 31 + 10
    needed_tfs = list(dict.fromkeys(list(timeframes) + ["1d"]))
    report: dict = {}
    for sym in symbols:
        for tf in needed_tfs:
            cov = data_store.coverage(sym, tf)
            need = max(30, int(months * 30 * _bars_per_day(tf) * 0.5))
            if cov["count"] < need:
                fetch_days = max(days, months * 31 + 40) if tf == "1d" else days
                try:
                    report[f"{sym}|{tf}"] = data_store.backfill(sym, tf, fetch_days)
                except Exception as e:  # noqa: BLE001
                    report[f"{sym}|{tf}"] = {"error": str(e)}
    return report


async def create_run(db, spec: dict) -> dict:
    """Validate + persist a QUEUED run. Returns the created doc (minus heavy fields)."""
    kind = spec.get("kind")
    if kind not in VALID_KINDS:
        raise ValueError(f"invalid kind '{kind}' (expected {sorted(VALID_KINDS)})")
    symbols = spec.get("symbols") or []
    if not symbols:
        raise ValueError("symbols required")
    if kind in ("grid_search", "walk_forward") and not spec.get("grid"):
        raise ValueError(f"{kind} requires a 'grid'")
    if kind == "sensitivity" and not (spec.get("target") and spec.get("values")):
        raise ValueError("sensitivity requires 'target' and 'values'")

    start_ms, end_ms = resolve_window(symbols, spec.get("period", "3m"),
                                      spec.get("start_ms"), spec.get("end_ms"))
    doc = {
        "id": str(uuid.uuid4()),
        "kind": kind, "symbols": symbols, "period": spec.get("period", "3m"),
        "start_ms": start_ms, "end_ms": end_ms,
        "metric": spec.get("metric", "return_over_dd"),
        "folds": int(spec.get("folds", 5)), "min_trades": int(spec.get("min_trades", 8)),
        "grid": spec.get("grid"), "setting_overrides": spec.get("setting_overrides"),
        "profile_overrides": spec.get("profile_overrides"),
        "target": spec.get("target"), "values": spec.get("values"),
        "label": spec.get("label"),
        "strategies": spec.get("strategies") or None,
        "timeframe": spec.get("timeframe") or "1h",
        "compare_timeframes": bool(spec.get("compare_timeframes", False)),
        "exit_method": spec.get("exit_method") or "fixed",
        "target_profit": float(spec.get("target_profit", 5.0)),
        "target_loss": float(spec.get("target_loss", 4.0)),
        "atr_params": spec.get("atr_params") or None,
        "status": "QUEUED", "progress_pct": 0.0, "git_hash": git_hash(),
        "created_at": _now(), "started_at": None, "finished_at": None,
        "result": None, "error": None,
    }
    await db.lab_runs.insert_one(doc)
    doc.pop("_id", None)
    return doc


def _run_backtest_one(kwargs: dict) -> dict:
    """Picklable single-backtest wrapper — executed in a worker PROCESS (no GIL contention
    with the FastAPI event loop, so live API calls / login stay responsive during a run)."""
    return backtest.run_backtest(**kwargs)


def _run_multi_exit_one(kwargs: dict) -> dict:
    """Picklable exit-comparison wrapper — replays the identical entry set under the 5 fixed
    exit configs in ONE worker process (a true A/B/C test; only the exit engine varies)."""
    return backtest.run_multi_exit(**kwargs)


def _first_exit_winner(result: dict) -> dict | None:
    """Extract the first symbol/timeframe that has a winning exit config, for the list hint.
    Prefers the 1h block (live-parity). Returns None when no winner exists."""
    ec = (result or {}).get("exit_comparison") or {}
    for symbol, by_tf in ec.items():
        tf = "1h" if by_tf.get("1h") else (next(iter(by_tf), None))
        block = by_tf.get(tf) or {}
        wk = block.get("winner_key")
        if wk:
            return {"symbol": symbol, "timeframe": tf,
                    "winner_key": wk, "winner_label": (block.get("rows") or {}).get(wk, {}).get("label", wk)}
    return None



def _run_optimize(run: dict) -> dict:
    """Picklable optimizer body (grid/sensitivity/walk_forward) — executed in a worker
    PROCESS. Runs with a no-op progress callback (parent shows an indeterminate bar)."""
    kind = run["kind"]
    symbols = run["symbols"]
    metric = run.get("metric", "return_over_dd")
    min_trades = run.get("min_trades", 8)
    start, end = run.get("start_ms"), run.get("end_ms")
    noop = lambda *_a, **_k: None  # noqa: E731
    if kind == "grid_search":
        return optimize.grid_search(symbols, start, end, run["grid"], metric, min_trades, progress_cb=noop)
    if kind == "sensitivity":
        return optimize.sensitivity(symbols, start, end, run["target"], run["values"],
                                    metric, min_trades, progress_cb=noop)
    if kind == "walk_forward":
        return optimize.walk_forward(symbols, run["grid"], run.get("folds", 5),
                                     metric, min_trades, progress_cb=noop)
    raise ValueError(f"unknown kind {kind}")



class LabWorker:
    """Polls lab_runs for QUEUED jobs and executes them one at a time.

    Compute runs in a worker PROCESS (not a thread): a backtest is CPU-bound and, in a
    thread, would hold Python's GIL and stall the FastAPI event loop — that starves
    concurrent API calls (login, portfolio, etc.). A separate process keeps the API
    fully responsive while a validation runs.
    """

    # Hard per-backtest wall-clock budget. A single 1h backtest is ~10s and a 15m one
    # ~40s; 300s is a generous ceiling that guarantees a run can never hang forever.
    BACKTEST_BUDGET_S = 300
    # Exit comparison runs 5 backtests sequentially in one process → a larger ceiling.
    EXIT_COMPARISON_BUDGET_S = 900

    def __init__(self, db, poll_seconds: int = 3):
        self.db = db
        self.poll = poll_seconds
        self._task: asyncio.Task | None = None
        self._pool = ProcessPoolExecutor(max_workers=1)
        self._stop = asyncio.Event()

    def _reset_pool(self):
        """Recycle the process pool (after a timeout or an abrupt worker crash)."""
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._pool = ProcessPoolExecutor(max_workers=1)

    async def _run_cell(self, fn, arg, budget):
        """Run one picklable job in the worker process with timeout + crash recovery.
        A dead worker (BrokenProcessPool) is recycled and the cell retried ONCE, so a single
        crash never poisons the rest of a multi-strategy sweep. Returns {"error": ...} on failure."""
        for attempt in (1, 2):
            loop = asyncio.get_event_loop()
            try:
                return await asyncio.wait_for(loop.run_in_executor(self._pool, fn, arg), timeout=budget)
            except asyncio.TimeoutError:
                self._reset_pool()
                return {"error": "timed_out"}
            except BrokenProcessPool as e:
                self._reset_pool()  # worker died — rebuild the pool and retry once
                if attempt == 2:
                    return {"error": f"worker_crashed: {e}"}
            except Exception as e:  # noqa: BLE001
                return {"error": str(e)}

    def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("LabWorker started (poll=%ss, process-isolated)", self.poll)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await self._task
        self._pool.shutdown(wait=False)

    async def _loop(self):
        # recover any run stuck in RUNNING from a previous boot
        await self.db.lab_runs.update_many({"status": "RUNNING"},
                                           {"$set": {"status": "QUEUED", "progress_pct": 0.0}})
        while not self._stop.is_set():
            try:
                run = await self.db.lab_runs.find_one_and_update(
                    {"status": "QUEUED"},
                    {"$set": {"status": "RUNNING", "started_at": _now()}},
                    sort=[("created_at", 1)],
                )
                if not run:
                    await asyncio.sleep(self.poll)
                    continue
                await self._execute(run)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("LabWorker loop error: %s", e)
                await asyncio.sleep(self.poll)

    async def _set_progress(self, rid: str, pct: float):
        await self.db.lab_runs.update_one(
            {"id": rid}, {"$set": {"progress_pct": round(min(100.0, max(0.0, pct)), 1)}})

    async def _execute(self, run: dict):
        rid = run["id"]
        try:
            if run["kind"] == "backtest":
                result = await self._run_backtest(run)
            elif run["kind"] == "health_sweep":
                result = await self._run_health_sweep(run)
            else:
                result = await self._run_optimize(run)
            update = {"status": "DONE", "progress_pct": 100.0, "result": result, "finished_at": _now()}
            # Lightweight top-level winner hint so the runs LIST (which strips `result`)
            # can offer a one-click "Save Winning Config" without re-fetching the full run.
            hint = _first_exit_winner(result)
            if hint:
                update["exit_winner"] = hint
            await self.db.lab_runs.update_one({"id": rid}, {"$set": update})
            # Strategy Health sweep: also upsert the fast-read "latest" doc for the dashboard.
            if run["kind"] == "health_sweep":
                await self.db.strategy_health.update_one(
                    {"id": "latest"},
                    {"$set": {"id": "latest", "run_id": rid, **result}}, upsert=True)
            logger.info("LabWorker DONE run=%s kind=%s", rid, run["kind"])
        except Exception as e:
            logger.exception("LabWorker run %s failed: %s", rid, e)
            await self.db.lab_runs.update_one({"id": rid}, {"$set": {
                "status": "FAILED", "error": str(e), "finished_at": _now()}})

    async def _run_backtest(self, run: dict) -> dict:
        """Orchestrate a backtest cell-by-cell in the parent (accurate progress), while each
        individual replay executes in the worker process. 1h is always run (live parity);
        30m/15m are only added when the user enabled the multi-timeframe comparison."""
        rid = run["id"]
        symbols = run["symbols"]
        start, end = run.get("start_ms"), run.get("end_ms")
        overrides = dict(setting_overrides=run.get("setting_overrides"),
                         profile_overrides=run.get("profile_overrides"),
                         strategies=run.get("strategies"),
                         exit_method=run.get("exit_method", "fixed"),
                         target_profit=run.get("target_profit", 5.0),
                         target_loss=run.get("target_loss", 4.0),
                         atr_params=run.get("atr_params"))
        timeframes = ["1h"] + (COMPARE_TIMEFRAMES if run.get("compare_timeframes") else [])
        base_tf = run.get("timeframe") or "1h"
        # Primary execution timeframe the user picked (1h default; 30m/15m optional).
        if base_tf != "1h":
            timeframes = [base_tf] + [t for t in timeframes if t != base_tf]
        loop = asyncio.get_event_loop()

        # Fresh deploys / newly-added assets have an empty local candle store — backfill
        # the needed history on demand from CCXT before replaying (keeps validation working
        # in any environment, incl. production, without a manual seed step).
        await self._set_progress(rid, 2)
        try:
            await loop.run_in_executor(self._pool, ensure_history, symbols, timeframes, run.get("period", "3m"))
        except BrokenProcessPool as e:
            logger.warning("ensure_history worker crashed for run %s: %s — recycling pool", rid, e)
            self._reset_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning("ensure_history failed for run %s: %s", rid, e)
        # Re-anchor the window now that data is present (create_run may have seen no data).
        start, end = resolve_window(symbols, run.get("period", "3m"), run.get("start_ms"), run.get("end_ms"))

        out, multi_tf, exit_cmp = {}, {}, {}
        tf_results: dict[str, dict] = {}
        cmp_overrides = dict(setting_overrides=run.get("setting_overrides"),
                             profile_overrides=run.get("profile_overrides"),
                             strategies=run.get("strategies"))
        # Each cell = 1 chosen-config backtest + 1 exit-comparison (5 configs in one task).
        total = (len(symbols) or 1) * len(timeframes) * 2
        step = 0
        for sym in symbols:
            for tf in timeframes:
                kwargs = {"symbol": sym, "start_ms": start, "end_ms": end, "timeframe": tf, **overrides}
                r = await self._run_cell(_run_backtest_one, kwargs, self.BACKTEST_BUDGET_S)
                if "error" in r:
                    r["symbol"] = sym
                tf_results[f"{sym}|{tf}"] = r
                if tf == base_tf:
                    out[sym] = r
                step += 1
                await self._set_progress(rid, step / total * 100)

                # Exit-engine comparison: 5 fixed configs replayed on the SAME entries.
                cmp_kwargs = {"symbol": sym, "start_ms": start, "end_ms": end, "timeframe": tf, **cmp_overrides}
                cr = await self._run_cell(_run_multi_exit_one, cmp_kwargs, self.EXIT_COMPARISON_BUDGET_S)
                if "error" in cr:
                    cr["symbol"] = sym
                exit_cmp.setdefault(sym, {})[tf] = cr
                step += 1
                await self._set_progress(rid, step / total * 100)
            tf_metrics = {tf: _tf_metrics(tf_results.get(f"{sym}|{tf}")) for tf in timeframes}
            multi_tf[sym] = {"by_tf": tf_metrics, "verdict": _tf_verdict(tf_metrics)}
        em = run.get("exit_method", "fixed")
        if em == "engine":
            em = "native"
        tp, tl = run.get("target_profit", 5.0), run.get("target_loss", 4.0)
        ap = {**{"multiplier": 2.5, "period": 14, "trail_activation_pct": 3.0, "trail_distance": 2.0},
              **(run.get("atr_params") or {})}
        if em == "fixed":
            label = "Fixed $ Target (TP $%g / SL $%g)" % (tp, tl)
        elif em == "atr":
            label = "ATR Exit (×%g stop, %dp, arm %g%%, trail ×%g)" % (
                ap["multiplier"], int(ap["period"]), ap["trail_activation_pct"], ap["trail_distance"])
        else:
            label = "Native Strategy Exit (Universal Engine)"
        return {
            "per_symbol": out, "multi_timeframe": multi_tf,
            "exit_comparison": exit_cmp,
            "exit_method": em,
            "exit_method_label": label,
            "target_profit": tp, "target_loss": tl,
            "atr_params": (ap if em == "atr" else None),
        }

    async def _run_optimize(self, run: dict) -> dict:
        """Grid/sensitivity/walk_forward run as a single unit in the worker process. Progress
        is shown as an indeterminate crawl since sub-step callbacks can't cross the process."""
        rid = run["id"]
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(self._pool, _run_optimize, run)
        pct = 0.0
        while not fut.done():
            pct = min(95.0, pct + 3.0)  # gentle crawl so the bar is alive, never claims done
            await self._set_progress(rid, pct)
            await asyncio.sleep(2)
        return await fut

    async def _run_health_sweep(self, run: dict) -> dict:
        """Strategy Health precompute — LIGHTWEIGHT & reliable.

        Per strategy (in isolation): one fast backtest per symbol×timeframe (for the multi-TF
        comparison + regime/capture from the 1h base), plus ONE exit-engine comparison on the
        primary symbol's 1h (for 'best exit'). No per-cell A/B/C sweep, so it completes quickly
        and never stalls. Progress is driven directly here (monotonic 0→100)."""
        from lab.health_sweep import SWEEP_SYMBOLS, aggregate_strategy, strategy_name

        rid = run["id"]
        strategies = run.get("strategies") or []
        symbols = run.get("symbols") or SWEEP_SYMBOLS
        period = run.get("period", "3m")
        tfs = ["1h"] + COMPARE_TIMEFRAMES
        loop = asyncio.get_event_loop()

        await self._set_progress(rid, 1)
        try:
            await loop.run_in_executor(self._pool, ensure_history, symbols, tfs, period)
        except BrokenProcessPool:
            self._reset_pool()
        except Exception as e:  # noqa: BLE001
            logger.warning("health sweep ensure_history failed: %s", e)

        start, end = resolve_window(symbols, period, None, None)
        cells_per_strat = len(symbols) * len(tfs) + 1  # backtests + 1 exit comparison
        total_cells = max(1, len(strategies) * cells_per_strat)
        done = 0
        cards: list[dict] = []

        for sk in strategies:
            per_symbol, multi_tf, exit_cmp = {}, {}, {}
            base = {"strategies": [sk], "exit_method": "native", "target_profit": 5.0, "target_loss": 4.0}
            for sym in symbols:
                by_tf = {}
                for tf in tfs:
                    r = await self._run_cell(_run_backtest_one,
                                             {"symbol": sym, "start_ms": start, "end_ms": end, "timeframe": tf, **base},
                                             self.BACKTEST_BUDGET_S)
                    if "error" in r:
                        r["symbol"] = sym
                    by_tf[tf] = _tf_metrics(r)
                    if tf == "1h":
                        per_symbol[sym] = r
                    done += 1
                    await self._set_progress(rid, min(99.0, done / total_cells * 100.0))
                multi_tf[sym] = {"by_tf": by_tf, "verdict": _tf_verdict(by_tf)}
            # one exit-engine comparison on the primary symbol / 1h → "best exit"
            psym = symbols[0]
            cr = await self._run_cell(_run_multi_exit_one,
                                      {"symbol": psym, "start_ms": start, "end_ms": end, "timeframe": "1h", "strategies": [sk]},
                                      self.EXIT_COMPARISON_BUDGET_S)
            if "error" not in cr:
                exit_cmp[psym] = {"1h": cr}
            done += 1
            await self._set_progress(rid, min(99.0, done / total_cells * 100.0))
            try:
                cards.append(aggregate_strategy(sk, {"per_symbol": per_symbol, "multi_timeframe": multi_tf, "exit_comparison": exit_cmp}))
            except Exception as e:  # noqa: BLE001 — one bad strategy must not kill the sweep
                logger.warning("health sweep aggregate %s failed: %s", sk, e)
                cards.append({"strategy": sk, "name": strategy_name(sk), "error": str(e),
                              "recommendation": {"badge": "Not Recommended Currently", "tone": "negative",
                                                 "reason": "Aggregation failed for this strategy."}})
        return {
            "mode": run.get("label") or "manual",
            "period": period, "symbols": symbols,
            "strategies": cards,
            "generated_at": _now(),
            "strategy_count": len(cards),
        }




class LabDataAppender:
    """Nightly, credit-free CCXT tail-append so the local history self-updates.
    Keeps the Binance-seeded 2-year base fresh with new 4h/1d candles each day."""

    def __init__(self, db, interval_hours: int = 24):
        self.db = db
        self.interval = interval_hours * 3600
        self._task: asyncio.Task | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lab-append")
        self._stop = asyncio.Event()

    def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("LabDataAppender started (every %sh)", self.interval // 3600)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await self._task
        self._pool.shutdown(wait=False)

    async def _symbols(self) -> list[str]:
        from lab.seed_history import BINANCE_MAP
        doc = await self.db.settings.find_one({"id": "singleton"}, {"enabled_symbols": 1})
        return (doc or {}).get("enabled_symbols") or list(BINANCE_MAP.keys())

    def _append_all(self, symbols: list[str]) -> dict:
        summary = {}
        for sym in symbols:
            for tf in ("15m", "30m", "1h", "4h", "1d"):
                try:
                    summary[f"{sym}/{tf}"] = data_store.append_latest(sym, tf)["inserted"]
                except Exception as e:
                    logger.warning("append %s %s failed: %s", sym, tf, e)
        return summary

    async def _loop(self):
        await asyncio.sleep(90)  # let boot settle
        loop = asyncio.get_event_loop()
        while not self._stop.is_set():
            try:
                syms = await self._symbols()
                res = await loop.run_in_executor(self._pool, self._append_all, syms)
                logger.info("LabDataAppender cycle: %d series updated", len(res))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("LabDataAppender error: %s", e)
            await asyncio.sleep(self.interval)



async def daily_scope_strategies(db) -> list[str]:
    """Daily-sweep strategy set = 3 core + every catalog strategy the owner has ENABLED."""
    from lab.health_sweep import CORE_STRATEGIES
    keys = list(CORE_STRATEGIES)
    try:
        metas = await db.strategy_meta.find({"enabled": True}, {"_id": 0, "key": 1}).to_list(500)
        for m in metas:
            k = m.get("key")
            if k and k not in keys:
                keys.append(k)
    except Exception as e:  # noqa: BLE001
        logger.warning("daily_scope_strategies failed: %s", e)
    return keys


async def enqueue_health_sweep(db, *, strategies: list[str], symbols: list[str] | None = None,
                               period: str = "3m", mode: str = "manual") -> dict:
    """Queue a Strategy Health sweep as a lab_run (kind=health_sweep). Reuses the LabWorker
    queue so it runs one-at-a-time off the request path, with progress + cancel for free."""
    from lab.health_sweep import SWEEP_SYMBOLS
    return await create_run(db, {
        "kind": "health_sweep",
        "symbols": symbols or SWEEP_SYMBOLS,
        "period": period,
        "strategies": strategies,
        "compare_timeframes": True,
        "label": mode,
    })


class HealthSweepScheduler:
    """Runs the scoped Strategy Health sweep once per day (core + enabled strategies, 3m window).
    Enqueues a health_sweep lab_run that the LabWorker executes in the background."""

    def __init__(self, db, interval_hours: int = 24):
        self.db = db
        self.interval = interval_hours * 3600
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("HealthSweepScheduler started (every %sh)", self.interval // 3600)

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await self._task

    async def _ran_today(self) -> bool:
        """True if ANY health sweep (daily or manual) was created today, or one is active —
        avoids piling a scheduled daily on top of a manual run the user already triggered."""
        today = datetime.now(timezone.utc).date().isoformat()
        doc = await self.db.lab_runs.find_one({
            "kind": "health_sweep",
            "$or": [
                {"created_at": {"$regex": f"^{today}"}},
                {"status": {"$in": ["QUEUED", "RUNNING"]}},
            ],
        }, {"_id": 1})
        return doc is not None

    async def _loop(self):
        await asyncio.sleep(150)  # let boot + data appender settle
        while not self._stop.is_set():
            try:
                if not await self._ran_today():
                    strategies = await daily_scope_strategies(self.db)
                    await enqueue_health_sweep(self.db, strategies=strategies, period="3m", mode="daily")
                    logger.info("HealthSweepScheduler queued daily sweep (%d strategies)", len(strategies))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception("HealthSweepScheduler error: %s", e)
            with __import__("contextlib").suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
