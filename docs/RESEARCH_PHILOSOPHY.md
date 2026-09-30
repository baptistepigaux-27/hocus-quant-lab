# Quant Lab research philosophy

Status: reference document  
Scope: research design, feature representation and future publication material  
Initial validation date: 2026-04-01

## 1. Purpose

Quant Lab is designed as a reproducible econometric research environment for cross-sectional and time-series experiments over heterogeneous financial entities.

The core idea is simple:

1. each entity has a time series;
2. the history available before a cutoff date is transformed into a vector of descriptive features;
3. all features are expressed on comparable, dimensionless scales;
4. a single cutoff date produces a cross-sectional matrix of entities × features;
5. repeating the same transformation over many cutoff dates creates the historical feature cube used by later models and backtests.

The first objective is therefore not prediction. It is to build a faithful, point-in-time and comparable representation of the state of many market entities at a chosen date.

## 2. Econometric point of view

The primitive object is a one-dimensional time series:

- x-axis: time;
- y-axis: observed value.

For an entity e and a cutoff T, only observations with time <= T may be used.

The feature engine summarizes the trajectory before T. At T it produces:

```
entity e -> [f1(T), f2(T), ..., fn(T)]
```

Repeating this for all entities gives the first cross-sectional slice:

```
entities × features | as_of = T
```

Repeating the same deterministic transformation over T1, T2, ... creates:

```
entity × feature × time
```

This cube is the natural research object. The 2026-04-01 snapshot is only the first golden slice used to validate the representation.

## 3. Invariance principle

A feature intended for comparison between entities must not depend on the nominal unit or price level of the source series.

An 8 EUR stock, an 8,000 point index and a 60,000 USD crypto asset must be representable in the same feature space.

Therefore, raw level-dependent statistics must not leave the feature factory without normalization.

Allowed outputs include:

- ratios;
- percentages;
- log-ratios;
- returns;
- normalized slopes;
- z-scores;
- correlations;
- t-statistics;
- R²;
- ranks / percentiles;
- other explicitly dimensionless quantities.

Raw EUR, USD, index-point or absolute-volume values may be retained for audit but are not canonical model features.

## 4. Base-100 normalization

For a series x observed over a window ending at T, define:

```
x*_t = 100 × x_t / x_T
```

The current value is therefore always 100.

This gives an intuitive common scale. For example:

```
mean_60 = 92
```

means that the 60-session mean was 8% below the current value.

For model features, a zero-centered form is usually preferable:

```
mean_delta_60 = 100 × (mean(x) / x_T - 1)
```

The feature engine may preserve both the base-100 and centered representation, but the canonical model output should favour centered values.

## 5. Normalized trend

For a linear regression over a window:

```
x_t = A t + B + epsilon_t
```

the raw slope A is not cross-asset comparable.

The canonical trend feature is:

```
trend_H_pct = 100 × A × (H - 1) / x_T
```

Interpretation: approximate fitted movement over the window as a percentage of the current value.

The regression family should also retain:

- slope t-statistic;
- R²;
- normalized current residual;
- optional intercept-relative measures.

The trio direction / statistical confidence / linearity is more informative than the raw slope alone.

## 6. Dispersion and volatility normalization

Raw variance and standard deviation depend on the price scale.

Canonical level-dispersion outputs include:

```
std_pct = 100 × std(x) / x_T
var_rel = var(x) / x_T²
```

Returns and log-returns are already dimensionless and should be treated directly.

Range and ATR-like measures must likewise be expressed relative to the current or reference price.

## 7. Multi-scale representation

The same families of features are computed over several horizons.

Initial windows:

- 3 sessions;
- 5 sessions;
- 10 sessions;
- 20 sessions;
- 30 sessions;
- 60 sessions;
- 120 sessions;
- 252 sessions;
- 504 sessions.

These are trading-session windows. They deliberately avoid ambiguous calendar-day semantics.

The maximum 504-session window corresponds approximately to two years of market history.

An entity does not need to have 504 observations to exist in the snapshot. Features whose minimum history is unavailable are marked unavailable with explicit coverage metadata.

## 8. Primitive source series

For securities with OHLCV data, the feature engine initially considers:

- Open;
- High;
- Low;
- Close;
- Volume.

The engine should also derive transformed primitive series where meaningful:

- log(Open), log(High), log(Low), log(Close);
- simple returns;
- log returns;
- log(1 + Volume);
- relative volume.

Volume is optional at the cross-universe level because volume semantics differ across equities, indices, futures, FX and crypto venues.

No artificial volume should be created for an entity that does not possess a meaningful volume series.

## 9. Feature families

### Descriptive distribution

For each eligible primitive or transformed series and horizon:

- current value in normalized form;
- mean;
- median;
- standard deviation;
- variance;
- minimum;
- maximum;
- selected quantiles;
- current vs mean;
- current vs median;
- normalized range;
- coefficient of variation where mathematically meaningful;
- skewness;
- kurtosis.

### Trend and dependence

- normalized linear slope;
- t-statistic of slope;
- R²;
- normalized residual at T;
- autocorrelation;
- optional higher-order trend diagnostics later.

### OHLC structure

Features using relationships between OHLC fields include:

- High-Low relative range;
- Close-Open return;
- overnight gap;
- close position inside the candle;
- body size;
- upper and lower wick;
- true range;
- ATR relative to price;
- intraday vs interday volatility;
- gap frequency;
- positive / negative session frequency.

### Technical-analysis family

Technical indicators are treated as engineered features, not as assumed trading rules.

Candidate families include:

- RSI;
- MACD;
- stochastic oscillator;
- Williams %R;
- CCI;
- ADX / directional indicators;
- ROC;
- momentum;
- Bollinger position and width;
- normalized ATR;
- OBV;
- MFI;
- Chaikin / accumulation-distribution;
- moving-average ratios;
- EMA/SMA distances and crossovers;
- realized volatility.

Any level-dependent technical indicator must be normalized before becoming canonical.

## 10. Cross-universe representation

The same feature vocabulary should be reusable across every entity for which compatible observations exist.

Target entity families include:

- equities;
- equity indices;
- rates / bond proxies;
- commodities;
- FX;
- crypto;
- other market series added later.

The goal is a common state representation, not forced semantic identity.

A feature unavailable or meaningless for one family must be null / unavailable with explicit provenance rather than synthesized.

## 11. Entity features and context features

An equity can be represented by both:

1. its own features;
2. features of contextual entities such as broad indices, sector indices, volatility indices, commodities, rates, FX and crypto.

Relative features can then be derived, for example:

```
stock_return_30 - market_return_30
stock_trend_60 - market_trend_60
stock_vol_30 / market_vol_30
```

This permits the research layer to distinguish absolute movement from relative strength and market regime.

## 12. Point-in-time discipline

Every snapshot is evaluated as of an explicit cutoff T.

Rules:

- no observation available after T may be read;
- source-specific availability timestamps must be honoured;
- a later correction cannot silently rewrite an earlier as-of state;
- current labels or instrument metadata must not be represented as historical facts unless their historical validity is known;
- historical index membership must not be inferred from present membership.

The 2026-04-01 test snapshot is not a statement that the current SBF 120 membership existed historically.

## 13. First validation slice

The first golden slice is:

```
as_of = 2026-04-01
```

Initial equity eligibility:

- an instrument has market observations at or before the cutoff;
- enough data exists to compute at least one configured feature window;
- all features are computed using only observations available at the cutoff;
- feature availability is explicit.

The snapshot should include every usable equity in the imported price corpus, not only a manually selected list.

The same factory must also be run over the other imported universes where compatible points are available.

## 14. Data model

Recommended long-form canonical output:

```
entity_id
as_of_date
feature_id
feature_value
feature_status
window
source_series
coverage_count
coverage_ratio
formula_version
```

A wide matrix can be materialized for research:

```
entity_id | as_of_date | f1 | f2 | ... | fn
```

Long form is better for lineage and evolution; wide form is convenient for econometrics and ML.

## 15. Reproducibility and feature identity

Every feature must have a deterministic identity based on:

- source series;
- transform;
- statistic / indicator;
- horizon;
- normalization;
- formula version.

Example:

```
close.level.mean_delta.w60.v1
close.log.trend_pct.w60.v1
close.log.trend_tstat.w60.v1
ohlc.atr_pct.w30.v1
```

Changing a formula must create a new version rather than silently changing historical meaning.

## 16. What this stage is not

This stage does not yet define:

- a prediction target;
- a model;
- a trading strategy;
- portfolio construction;
- transaction costs;
- execution assumptions;
- a claim of alpha.

The purpose is to build the measurement system before testing explanatory or predictive relationships.

## 17. Research progression

The intended sequence is:

1. validate one cross-sectional snapshot;
2. inspect coverage, distributions and redundancy;
3. freeze the feature contract;
4. generate the historical feature cube;
5. define targets separately;
6. run econometric and predictive tests;
7. add portfolio and execution layers only after signal validation.

This separation is intentional: data representation, target construction and model evaluation should remain independently auditable.

## 18. Publication / article angles

This document is also intended as source material for later articles.

Possible themes:

- why nominal prices should disappear from cross-asset feature spaces;
- from time series to cross-sectional market state vectors;
- point-in-time data as a prerequisite for honest backtests;
- separating measurement, prediction and trading;
- using slope, t-statistic and R² together to describe trend;
- building a common feature language across equities, indices, commodities and crypto;
- why a single validated market snapshot is a useful precursor to a historical feature cube.
