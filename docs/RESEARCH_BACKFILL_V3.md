# Research Backfill V3

## What V3 provides

`backend/research_backfill.py` is a repeat-safe exchange backfill runner. It fetches OHLCV in pages, normalizes every row through the research ingestion contract, and idempotently writes to `research_market_bars`.

Example:

```bash
cd backend
python research_backfill.py --symbol BTC/USD --timeframe 1h --days 365
python research_backfill.py --symbol BTC/USD --timeframe 1d --days 1825
```

## Important historical-data limitation

Do not interpret the exchange API backfill as a guaranteed five-year 1-minute archive. Public exchange endpoints commonly impose per-request limits and may retain less history than the research horizon requires. A deep 1m archive should be acquired from a suitable historical-data source and imported through the same `research_ingest` normalization interface.

## No survivorship bias

The research universe must be selected point-in-time. `research_asset_membership` records which assets belonged to `top10_crypto` at each ranking date. Do NOT take today's top ten and replay them over 2021–2026 as though they were known in 2021.

The existing application asset profile is an operational trading universe; it is not the historical research-universe definition.

## Recommended initial backfill order

1. Populate dated top-10 membership snapshots.
2. Backfill 1d and 4h across the full historical period.
3. Backfill 1h across the full historical period.
4. Backfill 15m and 5m for the periods needed by the first strategy experiments.
5. Acquire/import the archival 1m dataset separately; do not pretend a small exchange API sample represents five years.
6. Run data-quality checks: duplicates, timestamp gaps, OHLC violations, abnormal zero volume, and source coverage.
7. Generate versioned feature snapshots only after the raw bar layer passes quality checks.

## Research source separation

Research data can come from a high-quality historical market-data source even when live execution later uses a different venue. Every record stores its source and data version. Venue-specific execution costs and slippage are modeled separately in strategy experiments.
