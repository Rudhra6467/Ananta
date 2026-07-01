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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial

from lab import backtest, data_store, optimize

logger = logging.getLogger("ananta.lab.runner")

VALID_KINDS = {"backtest", "grid_search", "sensitivity", "walk_forward"}
_PERIOD_MONTHS = {"1m": 1, "2m": 2, "3m": 3, "quarter": 3, "6m": 6, "1y": 12, "2y": 24}


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
    maxes = [data_store.coverage(s, "4h")["max_ts"] for s in symbols]
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
        "status": "QUEUED", "progress_pct": 0.0, "git_hash": git_hash(),
        "created_at": _now(), "started_at": None, "finished_at": None,
        "result": None, "error": None,
    }
    await db.lab_runs.insert_one(doc)
    doc.pop("_id", None)
    return doc


def _run_job(run: dict, cb) -> dict:
    """SYNC job body (executed in a worker thread). Reuses the live-parity replay engine."""
    kind = run["kind"]
    symbols = run["symbols"]
    metric = run.get("metric", "return_over_dd")
    min_trades = run.get("min_trades", 8)
    start, end = run.get("start_ms"), run.get("end_ms")

    if kind == "backtest":
        out = {}
        n = len(symbols) or 1
        for i, sym in enumerate(symbols):
            out[sym] = backtest.run_backtest(
                sym, start, end,
                setting_overrides=run.get("setting_overrides"),
                profile_overrides=run.get("profile_overrides"),
            )
            cb((i + 1) / n)
        return {"per_symbol": out}
    if kind == "grid_search":
        return optimize.grid_search(symbols, start, end, run["grid"], metric, min_trades, progress_cb=cb)
    if kind == "sensitivity":
        return optimize.sensitivity(symbols, start, end, run["target"], run["values"],
                                    metric, min_trades, progress_cb=cb)
    if kind == "walk_forward":
        return optimize.walk_forward(symbols, run["grid"], run.get("folds", 5),
                                     metric, min_trades, progress_cb=cb)
    raise ValueError(f"unknown kind {kind}")


class LabWorker:
    """Polls lab_runs for QUEUED jobs and executes them one at a time."""

    def __init__(self, db, poll_seconds: int = 3):
        self.db = db
        self.poll = poll_seconds
        self._task: asyncio.Task | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lab")
        self._stop = asyncio.Event()

    def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("LabWorker started (poll=%ss)", self.poll)

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

    async def _execute(self, run: dict):
        rid = run["id"]
        progress = {"pct": 0.0}

        def cb(p: float):
            progress["pct"] = max(progress["pct"], min(1.0, float(p)))

        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(self._pool, partial(_run_job, run, cb))
        try:
            while not fut.done():
                await self.db.lab_runs.update_one(
                    {"id": rid}, {"$set": {"progress_pct": round(progress["pct"] * 100, 1)}})
                await asyncio.sleep(2)
            result = await fut
            await self.db.lab_runs.update_one({"id": rid}, {"$set": {
                "status": "DONE", "progress_pct": 100.0, "result": result, "finished_at": _now()}})
            logger.info("LabWorker DONE run=%s kind=%s", rid, run["kind"])
        except Exception as e:
            logger.exception("LabWorker run %s failed: %s", rid, e)
            await self.db.lab_runs.update_one({"id": rid}, {"$set": {
                "status": "FAILED", "error": str(e), "finished_at": _now()}})
