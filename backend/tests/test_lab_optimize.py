"""Tests for the optimizer (grid search, sensitivity, walk-forward) on a temp DB."""
import math
import os
import tempfile

import pytest

import lab.data_store as ds
from lab import optimize


@pytest.fixture()
def seeded_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(ds, "DB_PATH", path)
    ds.init_db()
    # deterministic wavy series with periodic dips (enough structure + trades)
    n = 1600
    start = 1_600_000_000_000
    bars4 = []
    for i in range(n):
        drift = math.sin(i / 10.0) * 3.0
        dip = -14.0 if (i % 60) in (0, 1, 2) else 0.0
        c = max(1.0, 100 + drift + dip + i * 0.03)
        bars4.append([start + i * ds.TF_MS["1h"], c - 0.4, c + 1.4, c - 1.4, c,
                      1000 + (i % 5) * 60 + (350 if dip else 0)])
    daily = [bars4[i][:1] + bars4[i][1:] for i in range(0, n, 24)]
    ds.upsert_candles("BTC/USD", "1h", bars4)
    ds.upsert_candles("BTC/USD", "1d", daily)
    yield path
    for p in (path, path + "-wal", path + "-shm"):
        if os.path.exists(p):
            os.remove(p)


def test_split_overrides_prefixes():
    so, po = optimize._split_overrides({
        "set:stop_loss_pct": 8, "prof:squeeze:trail_atr_mult": 2.0,
        "prof:hunter:profit_arm_pct": 4.0,
    })
    assert so == {"stop_loss_pct": 8}
    assert po == {"squeeze": {"trail_atr_mult": 2.0}, "hunter": {"profit_arm_pct": 4.0}}


def test_expand_grid_cartesian():
    combos = optimize._expand({"a": [1, 2], "b": [9, 8]})
    assert len(combos) == 4 and {"a": 1, "b": 9} in combos


def test_grid_search_structure(seeded_db):
    bars = ds.load_candles("BTC/USD", "1h")
    start, end = bars[210][0], bars[-1][0]
    grid = {"prof:hunter:profit_arm_pct": [4.0, 5.0], "set:stop_loss_pct": [8.0, 12.0]}
    res = optimize.grid_search("BTC/USD", start, end, grid, metric="total_return_pct", min_trades=1)
    assert res["combos_tested"] == 4
    assert res["best"] is not None
    assert len(res["ranked"]) == 4
    # ranked descending by metric
    ms = [r["metric"] for r in res["ranked"] if r["metric"] is not None]
    assert ms == sorted(ms, reverse=True)


def test_sensitivity_verdict(seeded_db):
    bars = ds.load_candles("BTC/USD", "1h")
    start, end = bars[210][0], bars[-1][0]
    res = optimize.sensitivity("BTC/USD", start, end, "prof:hunter:trail_atr_mult",
                               [1.6, 1.8, 2.0, 2.2, 2.4], metric="total_return_pct", min_trades=1)
    assert res["target"] == "prof:hunter:trail_atr_mult"
    assert len(res["curve"]) == 5
    assert res["verdict"] in ("ROBUST (flat plateau)",
                              "FRAGILE (sharp cliff — likely curve-fit)", "INSUFFICIENT_DATA")
    # curve sorted ascending by value
    vals = [c["value"] for c in res["curve"]]
    assert vals == sorted(vals)


def test_walk_forward_folds(seeded_db):
    grid = {"prof:hunter:profit_arm_pct": [4.0, 5.0, 6.0]}
    res = optimize.walk_forward("BTC/USD", grid, folds=3, metric="total_return_pct", min_trades=1)
    assert "error" not in res, res
    assert res["folds"] == 3
    assert len(res["fold_reports"]) == 3
    # each executed fold has an IS window and (usually) an OOS metric slot
    executed = [f for f in res["fold_reports"] if "is_window" in f]
    assert executed, res
    assert "wfa_efficiency" in res and "verdict" in res
