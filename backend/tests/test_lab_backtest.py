"""Tests for the Research Lab foundation: data store, injectable clock, replay parity."""
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

import lab.data_store as ds
from exit_engine import evaluate_exit_engine
from models import Position, RiskSettings


@pytest.fixture()
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(ds, "DB_PATH", path)
    ds.init_db()
    yield path
    for p in (path, path + "-wal", path + "-shm"):
        if os.path.exists(p):
            os.remove(p)


# ---------- data store ----------
def test_data_store_roundtrip_idempotent(temp_db):
    bars = [[1000 + i * ds.TF_MS["4h"], 10 + i, 11 + i, 9 + i, 10.5 + i, 100 + i] for i in range(5)]
    ins1 = ds.upsert_candles("BTC/USD", "4h", bars)
    ins2 = ds.upsert_candles("BTC/USD", "4h", bars)  # duplicate -> ignored
    assert ins1 == 5 and ins2 == 0
    loaded = ds.load_candles("BTC/USD", "4h")
    assert len(loaded) == 5 and loaded[0][0] == 1000
    cov = ds.coverage("BTC/USD", "4h")
    assert cov["count"] == 5 and cov["min_ts"] == 1000


def test_load_candles_window(temp_db):
    base = 1_600_000_000_000
    bars = [[base + i * ds.TF_MS["4h"], 1, 2, 0.5, 1.5, 10] for i in range(10)]
    ds.upsert_candles("ETH/USD", "4h", bars)
    win = ds.load_candles("ETH/USD", "4h", start_ms=base + 2 * ds.TF_MS["4h"],
                          end_ms=base + 5 * ds.TF_MS["4h"])
    assert len(win) == 4  # indices 2,3,4,5 inclusive


# ---------- injectable clock (the critical backtest-parity fix) ----------
def _pos(entry_hours_ago_from, avg=100.0):
    return Position(symbol="BTC/USD", quantity=1.0, avg_cost=avg, peak_price=avg,
                    trough_price=avg, entry_timestamp=entry_hours_ago_from)


def test_injected_clock_prevents_false_time_exit():
    """A trade opened 'now' in sim time must NOT instantly hit Module E, even if the
    real wall clock is years ahead of the historical entry timestamp."""
    s = RiskSettings()
    sim_now = datetime(2025, 1, 15, tzinfo=timezone.utc)
    entry_iso = (sim_now - timedelta(hours=2)).isoformat()  # 2h old in sim time
    pos = _pos(entry_iso)
    d = evaluate_exit_engine(pos, last_price=100.05, bars_4h=None, settings=s, now=sim_now)
    assert d.action == "NONE"  # 2h old, flat -> no exit


def test_injected_clock_allows_real_time_exit_when_stagnant():
    s = RiskSettings()
    sim_now = datetime(2025, 1, 15, tzinfo=timezone.utc)
    entry_iso = (sim_now - timedelta(hours=50)).isoformat()  # >48h in sim time
    pos = _pos(entry_iso)
    d = evaluate_exit_engine(pos, last_price=100.05, bars_4h=None, settings=s, now=sim_now)
    assert d.action == "EXIT_FULL" and d.module == "E"


def test_default_clock_backward_compatible():
    """Omitting `now` must behave as before (real wall clock)."""
    s = RiskSettings()
    fresh = _pos(datetime.now(timezone.utc).isoformat())
    d = evaluate_exit_engine(fresh, last_price=100.05, bars_4h=None, settings=s)
    assert d.action == "NONE"


# ---------- replay engine parity + structure ----------
def _synth_series(n=320, start_ms=1_600_000_000_000, seed_price=100.0):
    """Deterministic wavy series with a dip (to trigger Hunter) then recovery."""
    bars = []
    p = seed_price
    for i in range(n):
        # gentle oscillation + a pronounced dip around the middle
        drift = math.sin(i / 12.0) * 2.0
        dip = -18.0 if 150 <= i <= 160 else 0.0
        c = max(1.0, seed_price + drift + dip + (i * 0.02))
        o = c - 0.3
        h = c + 1.2
        low = c - 1.2
        v = 1000 + (i % 7) * 50 + (400 if 150 <= i <= 160 else 0)
        bars.append([start_ms + i * ds.TF_MS["1h"], o, h, low, c, v])
    return bars


def test_backtest_runs_and_reports(temp_db):
    from lab import backtest
    bars4 = _synth_series(340)
    # daily bars (coarse) so compute_levels has structure
    daily = [[bars4[i][0], bars4[i][1], bars4[i][2], bars4[i][3], bars4[i][4], bars4[i][5]]
             for i in range(0, len(bars4), 24)]
    ds.upsert_candles("BTC/USD", "1h", bars4)
    ds.upsert_candles("BTC/USD", "1d", daily)
    start = bars4[210][0]
    end = bars4[-1][0]
    res = backtest.run_backtest("BTC/USD", start, end)
    assert "error" not in res, res
    # structural assertions on the report contract
    for k in ("total_return_pct", "win_rate_pct", "max_drawdown_pct",
              "exit_module_breakdown", "regime_breakdown", "trade_log"):
        assert k in res
    assert res["starting_capital"] == 1200.0
    assert isinstance(res["trades"], int)
