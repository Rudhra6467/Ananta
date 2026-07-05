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
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone

from lab import backtest, data_store, optimize

logger = logging.getLogger("ananta.lab.runner")

VALID_KINDS = {"backtest", "grid_search", "sensitivity", "walk_forward"}
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
    """Map a period dropdown to a [start_ms, end_ms] window off the latest seeded candle."""
    if period == "custom" and start_ms and end_ms:
        return int(start_ms), int(end_ms)
    maxes = [data_store.coverage(s, "1h")["max_ts"] for s in symbols]
    maxes = [m for m in maxes if m]
    if not maxes:
        return None, None
    end = min(maxes)
    months = _PERIOD_MONTHS.get(period, 3)
    start = end - months * 30 * 86_400_000
    return start, end


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
        "compare_timeframes": bool(spec.get("compare_timeframes", False)),
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

    def __init__(self, db, poll_seconds: int = 3):
        self.db = db
        self.poll = poll_seconds
        self._task: asyncio.Task | None = None
        self._pool = ProcessPoolExecutor(max_workers=1)
        self._stop = asyncio.Event()

    def _reset_pool(self):
        """Recycle the process pool (used after a timeout to kill a runaway worker)."""
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._pool = ProcessPoolExecutor(max_workers=1)

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
            else:
                result = await self._run_optimize(run)
            await self.db.lab_runs.update_one({"id": rid}, {"$set": {
                "status": "DONE", "progress_pct": 100.0, "result": result, "finished_at": _now()}})
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
                         strategies=run.get("strategies"))
        timeframes = ["1h"] + (COMPARE_TIMEFRAMES if run.get("compare_timeframes") else [])
        loop = asyncio.get_event_loop()

        out, multi_tf = {}, {}
        tf_results: dict[str, dict] = {}
        total = (len(symbols) or 1) * len(timeframes)
        step = 0
        for sym in symbols:
            for tf in timeframes:
                kwargs = {"symbol": sym, "start_ms": start, "end_ms": end, "timeframe": tf, **overrides}
                try:
                    r = await asyncio.wait_for(
                        loop.run_in_executor(self._pool, _run_backtest_one, kwargs),
                        timeout=self.BACKTEST_BUDGET_S)
                except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
                    r = {"error": "timed_out" if isinstance(e, asyncio.TimeoutError) else str(e), "symbol": sym}
                    if isinstance(e, asyncio.TimeoutError):
                        self._reset_pool()
                        loop = asyncio.get_event_loop()
                tf_results[f"{sym}|{tf}"] = r
                if tf == "1h":
                    out[sym] = r
                step += 1
                await self._set_progress(rid, step / total * 100)
            tf_metrics = {tf: _tf_metrics(tf_results.get(f"{sym}|{tf}")) for tf in timeframes}
            multi_tf[sym] = {"by_tf": tf_metrics, "verdict": _tf_verdict(tf_metrics)}
        return {"per_symbol": out, "multi_timeframe": multi_tf}

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
