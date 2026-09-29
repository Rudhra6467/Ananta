from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from research_database import asset_membership
from research_features import build_feature_snapshot
from research_ingest import normalize_ohlcv_row, utc_datetime


def _bar(ts, close, volume=10.0):
    return {
        "key": f"BTC/USD|1h|{ts.isoformat()}",
        "symbol": "BTC/USD",
        "timeframe": "1h",
        "timestamp": ts,
        "ohlcv": {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": volume},
    }


def test_timestamp_normalizes_to_utc():
    dt = utc_datetime("2026-01-01T12:00:00-05:00")
    assert dt == datetime(2026, 1, 1, 17, 0, tzinfo=UTC)


def test_invalid_ohlc_is_rejected():
    with pytest.raises(ValueError):
        normalize_ohlcv_row(
            symbol="BTC/USD", timeframe="1h", timestamp=0,
            open=100, high=90, low=80, close=95, volume=1, source="test"
        )


def test_feature_snapshot_never_uses_future_bars():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_bar(t0 + timedelta(hours=i), 100 + i) for i in range(55)]
    snapshot = build_feature_snapshot(bars=bars, as_of=t0 + timedelta(hours=40))
    assert snapshot["timestamp"] == t0 + timedelta(hours=40)
    assert snapshot["features"]["close"] == 140.0
    assert snapshot["source_bar_key"].endswith((t0 + timedelta(hours=40)).isoformat())


def test_feature_version_changes_snapshot_identity():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [_bar(t0 + timedelta(hours=i), 100 + i) for i in range(55)]
    a = build_feature_snapshot(bars=bars, as_of=t0 + timedelta(hours=50), feature_version="v1")
    b = build_feature_snapshot(bars=bars, as_of=t0 + timedelta(hours=50), feature_version="v2")
    assert a["feature_version"] != b["feature_version"]


def test_asset_membership_is_point_in_time():
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    row = asset_membership(symbol="btc/usd", as_of=as_of, rank=1, market_cap=1_000_000, source="test")
    assert row["symbol"] == "BTC/USD"
    assert row["rank"] == 1
    assert row["universe"] == "top10_crypto"
    assert row["as_of"] == as_of
