"""Tests for the Research Lab queue runner + PDF report (offline)."""
import asyncio
import math
import os
import tempfile

import pytest

import lab.data_store as ds
from lab import runner
from lab.lab_report import build_lab_report


@pytest.fixture()
def seeded_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(ds, "DB_PATH", path)
    ds.init_db()
    n = 500
    start = 1_600_000_000_000
    bars4 = []
    for i in range(n):
        c = max(1.0, 100 + math.sin(i / 10.0) * 3 + (-12 if i % 50 < 2 else 0) + i * 0.03)
        bars4.append([start + i * ds.TF_MS["4h"], c - 0.4, c + 1.4, c - 1.4, c, 1000 + (i % 5) * 60])
    ds.upsert_candles("BTC/USD", "4h", bars4)
    ds.upsert_candles("BTC/USD", "1d", [bars4[i] for i in range(0, n, 6)])
    yield path
    for p in (path, path + "-wal", path + "-shm"):
        if os.path.exists(p):
            os.remove(p)


def test_resolve_window_period(seeded_db):
    start, end = runner.resolve_window(["BTC/USD"], "1m", None, None)
    assert start and end and end > start
    assert (end - start) == 1 * 30 * 86_400_000
    # custom passes through
    assert runner.resolve_window(["BTC/USD"], "custom", 111, 222) == (111, 222)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return self._docs


class _FakeRuns:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(doc)


class _FakeDB:
    def __init__(self):
        self.lab_runs = _FakeRuns()


def test_create_run_validation():
    db = _FakeDB()
    # missing grid for walk_forward -> ValueError
    with pytest.raises(ValueError):
        asyncio.run(runner.create_run(db, {"kind": "walk_forward", "symbols": ["BTC/USD"]}))
    # invalid kind
    with pytest.raises(ValueError):
        asyncio.run(runner.create_run(db, {"kind": "bogus", "symbols": ["BTC/USD"]}))
    # valid grid_search
    doc = asyncio.run(runner.create_run(db, {
        "kind": "grid_search", "symbols": ["BTC/USD"], "period": "custom",
        "start_ms": 1, "end_ms": 2, "grid": {"set:stop_loss_pct": [8, 12]}}))
    assert doc["status"] == "QUEUED" and doc["git_hash"] and doc["id"]


def test_run_job_dispatch_backtest(seeded_db):
    bars = ds.load_candles("BTC/USD", "4h")
    run = {"kind": "backtest", "symbols": ["BTC/USD"],
           "start_ms": bars[210][0], "end_ms": bars[-1][0]}
    seen = []
    res = runner._run_job(run, seen.append)
    assert "per_symbol" in res and "BTC/USD" in res["per_symbol"]
    assert seen and seen[-1] == 1.0  # progress reached 100%


def test_run_job_dispatch_sensitivity(seeded_db):
    bars = ds.load_candles("BTC/USD", "4h")
    run = {"kind": "sensitivity", "symbols": ["BTC/USD"], "start_ms": bars[210][0],
           "end_ms": bars[-1][0], "target": "prof:hunter:trail_atr_mult",
           "values": [1.8, 2.0, 2.2], "metric": "total_return_pct", "min_trades": 1}
    res = runner._run_job(run, lambda p: None)
    assert res["target"] == "prof:hunter:trail_atr_mult" and len(res["curve"]) == 3


@pytest.mark.parametrize("kind,result", [
    ("backtest", {"per_symbol": {"BTC/USD": {"total_return_pct": 5.1, "trades": 20, "win_rate_pct": 55.0,
                                             "max_drawdown_pct": 4.2, "avg_mfe_pct": 6.0, "avg_mae_pct": -2.0,
                                             "avg_trade_quality": 60.0,
                                             "exit_module_breakdown": {"A": {"n": 5, "win_pct": 20.0, "net_pnl": -3.0}},
                                             "regime_breakdown": {"TREND_UP": {"n": 10, "win_pct": 60.0, "net_pnl": 8.0}}}}}),
    ("sensitivity", {"target": "prof:hunter:trail_atr_mult", "metric": "total_return_pct",
                     "coeff_variation": 0.1, "verdict": "ROBUST (flat plateau)",
                     "curve": [{"value": 2.0, "metric": 3.1, "trades": 12, "total_return_pct": 3.1}]}),
    ("walk_forward", {"metric": "return_over_dd", "avg_is_metric": 1.2, "avg_oos_metric": 0.8,
                      "wfa_efficiency": 0.67, "oos_positive_folds": "3/4", "verdict": "ROBUST — edge holds out-of-sample",
                      "fold_reports": [{"fold": 1, "is_window": [1, 2], "oos_window": [2, 3],
                                        "best_params": {"prof:hunter:profit_arm_pct": 5.0},
                                        "is_metric": 1.2, "oos_metric": 0.8, "oos_trades": 9, "oos_return_pct": 4.0}]}),
])
def test_build_lab_report_all_kinds(kind, result):
    run = {"id": "abc12345", "kind": kind, "symbols": ["BTC/USD"], "period": "3m",
           "start_ms": 1_700_000_000_000, "end_ms": 1_710_000_000_000, "metric": "return_over_dd",
           "git_hash": "deadbee", "created_at": "2026-06-28T00:00:00+00:00",
           "status": "DONE", "result": result}
    pdf = build_lab_report(run)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000
