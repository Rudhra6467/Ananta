# Research Feature Factory V4

V4 creates the first versioned analytical layer above canonical market bars.

## Feature families

The initial implementation covers price/returns, trend, momentum, volatility, volume, and moving-average state. Future versions will add order-book/microstructure, derivatives, sentiment, cross-asset and macro features.

## Point-in-time contract

`build_feature_snapshot()` filters bars to `timestamp <= as_of` before calculating features. The snapshot records both `as_of` and the source bar key. A feature version identifies the calculation implementation used to produce the value.

## Regimes

The deterministic research classifier currently emits:

- `TREND_UP`
- `TREND_DOWN`
- `RANGE`
- `COMPRESSION`
- `HIGH_VOL`
- `MOMENTUM_UP`
- `MOMENTUM_DOWN`
- `NEUTRAL`
- `INSUFFICIENT_DATA`

These are evidence segmentation labels, not trade instructions. Thresholds are versioned separately from strategy logic so the research team can compare alternative regime definitions without rewriting historical observations.

## Important limitation

`trend_strength_proxy` is intentionally named as a proxy rather than pretending to be Wilder ADX. A later feature version should implement and validate canonical ADX, Bollinger Bands, OBV, VWAP, volatility percentiles, cross-asset context, derivatives and sentiment.

## Next step

Run the factory over the historical bars and persist snapshots. Then build the standardized strategy registry and experiment runner. Do not tune strategies against the same data used to discover features without explicit train/test boundaries.
