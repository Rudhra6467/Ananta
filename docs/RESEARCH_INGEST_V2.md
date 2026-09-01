# Research Ingestion V2

V2 establishes the canonical market-data path for the Ananta research warehouse.

## Contract

Every market bar is normalized to:

- UTC timestamp
- symbol
- timeframe (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`)
- OHLCV
- optional trade count
- source
- data version
- deterministic key

The same normalization contract must be used for historical backfills and live/replay ingestion.

## Point-in-time rule

For a decision at time `t`, feature generation may use only observations whose timestamp is `<= t`.
Future bars, revised future sentiment, or labels derived from future returns must never enter the feature snapshot.
Outcome labels belong to the observation after its evaluation horizon closes.

## Initial deterministic features

V2 provides a deliberately small, auditable baseline:

- 1/5/20-period returns
- SMA-20 / SMA-50
- distance from SMA-20 / SMA-50
- 20-period realized volatility
- 20-period volume ratio
- current bar range percentage

This is not intended to be the final feature library. It establishes a reproducible pipeline on which RSI, MACD, ATR, Bollinger, ADX, OBV, funding, order-book, sentiment, correlation and regime features can be added as versioned feature families.

## Ingestion behavior

`ingest_ohlcv()` validates rows and performs idempotent upserts into `research_market_bars`.
A repeated download therefore does not create duplicate observations.

## Next step

Connect exchange/source adapters to this neutral interface, backfill the selected universe, then build versioned feature families and point-in-time regime/context snapshots before strategy sweeps begin.
