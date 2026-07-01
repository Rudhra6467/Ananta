"""Offline tests for the historical seeders (no network)."""
import os
import tempfile

import pytest

import lab.data_store as ds
from lab.seed_history import _norm_ts, _parse_klines, seed_from_csv


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


def test_norm_ts_units():
    assert _norm_ts(1_700_000_000_000) == 1_700_000_000_000       # ms stays ms
    assert _norm_ts(1_700_000_000_000_000) == 1_700_000_000_000    # micro -> ms
    assert _norm_ts(1_700_000_000) == 1_700_000_000_000            # sec -> ms


def test_parse_klines_skips_header_and_parses():
    text = (
        "open_time,open,high,low,close,volume,close_time\n"      # header -> skipped
        "1700000000000,100,110,90,105,1000,1700014399999\n"
        "1700014400000,105,120,100,118,1500,1700028799999\n"
    )
    rows = _parse_klines(text)
    assert len(rows) == 2
    assert rows[0] == [1700000000000, 100.0, 110.0, 90.0, 105.0, 1000.0]


def test_seed_from_csv_cryptodatadownload_format(temp_db):
    # CDD files: a comment/URL line, then header with unix (seconds) + date columns
    csv_text = (
        "https://www.cryptodatadownload.com\n"
        "unix,date,symbol,open,high,low,close,Volume BTC,Volume USDT,tradecount\n"
        "1700000000,2023-11-14 00:00:00,BTC/USDT,35000,35500,34800,35400,10,350000,500\n"
        "1700014400,2023-11-14 04:00:00,BTC/USDT,35400,36000,35300,35900,12,430000,620\n"
    )
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(csv_text)
    try:
        res = seed_from_csv(path, "BTC/USD", "4h")
        assert res["parsed"] == 2 and res["inserted"] == 2
        loaded = ds.load_candles("BTC/USD", "4h")
        assert loaded[0][0] == 1700000000000  # seconds normalised to ms
        assert loaded[0][4] == 35400.0
    finally:
        os.remove(path)
