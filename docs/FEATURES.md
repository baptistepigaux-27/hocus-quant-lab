# SPEC-003 feature contract

## Snapshot and lineage

`build-feature-snapshot --as-of D` uses the instant 00:00 Europe/Paris on D+1
as its cutoff and includes session dates through D when their stored
`available_at` is at or before that instant. The builder reads only `market_daily_history`
and `market_series_history`; it does not read source ZIPs, labels, adjusted
closes or the current composition of an index. Entities use provider and
universe qualified identifiers to prevent accidental joins between unrelated
codes.

The imported ABC Bourse history was retrieved in September 2026 and carries a
source-contract availability time of session date + one day. The snapshot
therefore reports how many included rows were retrieved after its cutoff. ABC
does not provide historical vintages or a corporate-action stream in this
delivery. The date-based availability rule is an explicit backfill assumption,
not proof that every delivered value was unchanged from what a researcher
could have downloaded on that historical date. Adjusted closes are excluded.

## IDs and normalization

Feature IDs follow
`<source>.<transform>.<metric>[.w<horizon>].v<formula_version>`. Formula
changes that alter meaning require a new version. Horizons are counts of
observed rows, not calendar days. Unavailable values are written as Parquet
nulls and carry status `unavailable`, a reason, observed coverage count and
coverage ratio.

For positive level series, `base100 = 100*x_T/x_T`, and level deltas compare a
statistic with `x_T`. `std_pct = 100*sample_std(x)/x_T`; `var_rel` uses the
sample variance divided by `x_T²`. For log-price trend, the slope feature is
`100*slope(log(x))*(H-1)`, which is invariant to changing the unit of x and
represents an approximate log-return. Trend t-statistic and R² use ordinary
least squares on index 0..H-1. The current residual is
`100*(exp(residual_T)-1)`. Returns and log-returns remain in natural decimal
units; percentage OHLC and technical outputs multiply those returns by 100.

The registry includes four OHLC level series, two close-return series,
rolling OHLC relationship summaries, relative volume and realized volatility
for horizons 3, 5, 10, 20, 30, 60, 120, 252 and 504. Every level output is
normalized; no raw price, currency, index-point or absolute-volume value is a
canonical feature. `log1p(volume)` is constructed as a primitive but is not
published as a canonical feature because its value changes with the unit used
for volume. Volume outputs use ratios or volume-weighted fractions instead.

## Technical formula choices v1

All formulas are implemented locally with NumPy; no technical-analysis
package is used.

| Feature | v1 formula / lookback |
| --- | --- |
| RSI | Simple mean gain/loss RSI, 14 close differences |
| MACD | Recursive EMA seeded at first close; EMA(12)-EMA(26), signal EMA(9); components as % of close; 34 observations |
| Stochastic K / D | 14-row high-low position; D is mean of last three K values; 14 / 16 observations |
| Williams %R | 14-row high-low range |
| CCI | 20-row typical price and mean absolute deviation, constant 0.015 |
| +DI / -DI / ADX | 14-row simple smoothed true range and directional movement; ADX is mean of last 14 DX values |
| ROC / momentum | Close change over 12 / 20 observed intervals, expressed in percent |
| Bollinger | 20-row population standard deviation, bands at ±2σ; position within bands and bandwidth / mean |
| ATR % | 14-row mean true range divided by current close |
| OBV change fraction | Signed volume over 20 intervals divided by total volume |
| MFI | 14 typical-price money-flow intervals |
| Accumulation/distribution fraction | 20-row close-location weighted volume divided by total volume |
| EMA / SMA distance | Current close relative to recursive EMA(20) / mean close(20), in percent |
| Realized volatility | Sample standard deviation of log returns × √252 × 100 for each configured horizon |

These are descriptive measurements, not trading rules. Zero denominators,
non-finite inputs and insufficient history produce unavailable values; no
missing value is silently replaced with zero. OHLC gap frequency is the share
of observed gaps whose absolute size exceeds 0.1%. Positive/negative session
shares compare close with the preceding observed close.

## Outputs and audit

`features_long.parquet` is the canonical source of truth. `features_wide.parquet`
is a convenience matrix keyed by entity and cutoff. `features.duckdb` exposes
both as `features_long` and `features_wide`. `audit.json` and `audit.md` report
family counts, cells, availability, horizon coverage, distributions, constant
and extreme features, near-duplicate IDs, pairwise high correlations and low
coverage entities. Correlation checks use up to 2,000 sorted entities and the
100 features with greatest coverage; missing values are handled pairwise.
Pairs with absolute correlation at least 0.95 are reported. Entities with
fewer than 15% of registry features available are labeled low coverage.
An entity with no available feature is reported as an ineligible candidate and
omitted from the output. An entity is not excluded merely for lacking the
504-row horizon. A feature is flagged extreme when its minimum is below
`p01 - 20 * max(abs(p01), 1)` or its maximum is above
`p99 + 20 * max(abs(p99), 1)`. This is a review flag only; values are retained.

The small real-data golden fixture is copied from the manually supplied ABC
Bourse snapshot and contains 504 OHLCV rows each for one SRD equity, one market
index and one crypto series, ending on or before 2026-04-01. It validates
formula reproducibility on those exact observations, not the vendor's
historical adjustment policy.
