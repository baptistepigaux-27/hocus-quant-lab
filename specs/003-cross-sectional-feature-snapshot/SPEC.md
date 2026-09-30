# SPEC-003 — Cross-sectional feature snapshot

Status: READY FOR IMPLEMENTATION  
Primary executor: Codex / Luna  
Reference date: 2026-04-01  
Depends on: SPEC-001 AMF ingestion, SPEC-002B market-data ingestion

## 1. Goal

Implement a deterministic multi-scale feature factory that converts all eligible market series available as of 2026-04-01 into one cross-sectional, dimensionless entity × feature snapshot.

This spec validates the feature language and computation contract. It does not build a model or backtest.

Read first:

- `docs/RESEARCH_PHILOSOPHY.md`
- `docs/POINT_IN_TIME.md`
- `docs/ABC_BOURSE_DELIVERY.md`
- existing market-data schemas and as-of query helpers.

## 2. Inputs

Use only data available in Quant Lab / imported local datasets.

The factory must operate from normalized silver / DuckDB research views, not directly from ad hoc source files.

Initial entity families:

- equities;
- indices;
- commodities;
- crypto;
- any other imported market series with compatible price observations.

Do not invent missing series.

## 3. Cutoff

Canonical golden cutoff:

```
2026-04-01
```

Every query must be point-in-time safe and must reject / exclude observations not available by the cutoff.

The implementation must expose the cutoff as a parameter even though acceptance tests focus on 2026-04-01.

## 4. Windows

Use trading-observation counts:

```
3, 5, 10, 20, 30, 60, 120, 252, 504
```

Do not reinterpret them as calendar days.

A feature may be unavailable if the source entity has insufficient observations. Preserve the entity and record feature status / coverage.

## 5. Normalization invariant

No canonical output feature may retain the nominal unit or price scale of the entity.

For level series x ending at T:

```
base100_t = 100 * x_t / x_T
centered_t = 100 * (x_t / x_T - 1)
```

For linear regression x_t = A t + B:

```
trend_pct = 100 * A * (H - 1) / x_T
```

For level dispersion:

```
std_pct = 100 * std(x) / x_T
var_rel = var(x) / x_T^2
```

Returns, t-statistics, R², correlations and similar dimensionless quantities remain on their natural scale.

Raw level values may exist for audit only and must not be exposed as canonical model features.

## 6. Primitive series

For standard OHLCV instruments:

- open;
- high;
- low;
- close;
- volume.

Derived primitive series:

- log open/high/low/close;
- simple close returns;
- log close returns;
- log(1 + volume) when volume exists;
- relative volume.

Volume is optional. Do not fabricate it for indices or other assets with no meaningful volume field.

## 7. Required feature families

### 7.1 Distribution features

For each applicable primitive / transformed series and each eligible window:

- mean delta vs current;
- median delta vs current;
- std normalized;
- variance normalized;
- min delta vs current;
- max delta vs current;
- q10 / q25 / q75 / q90 delta vs current where window size is sufficient;
- normalized range;
- skewness where sample size is sufficient;
- kurtosis where sample size is sufficient.

### 7.2 Trend features

For each applicable price-like series and window:

- normalized linear slope `trend_pct`;
- slope t-statistic;
- R²;
- normalized residual at cutoff;
- lag-1 autocorrelation where sample size permits.

Regression time index must be deterministic: 0..H-1 over the selected observations.

### 7.3 OHLC relational features

Implement normalized versions of:

- high-low range;
- close-open return;
- overnight gap;
- candle body size;
- upper wick;
- lower wick;
- close location value;
- true range;
- ATR;
- positive-session share;
- negative-session share;
- gap frequency.

Compute rolling summary statistics over configured windows where meaningful.

### 7.4 Technical indicators

Implement a first deterministic set using library-free or pinned-library formulas:

- RSI;
- MACD components expressed on normalized / percentage scale;
- stochastic oscillator;
- Williams %R;
- CCI;
- ADX / +DI / -DI;
- ROC;
- momentum as percent return;
- Bollinger position;
- Bollinger bandwidth;
- ATR percent;
- OBV-derived normalized change features when volume exists;
- MFI when volume exists;
- accumulation/distribution derived normalized change when volume exists;
- EMA/SMA distance ratios;
- realized volatility.

If an indicator has a conventional minimum lookback, preserve it and mark unavailable where insufficient.

## 8. Feature naming

Every feature must have a stable deterministic identifier.

Recommended grammar:

```
<series>.<transform>.<metric>.w<window>.v<formula_version>
```

Examples:

```
close.level.mean_delta.w60.v1
close.log.trend_pct.w60.v1
close.log.trend_tstat.w60.v1
close.return.std.w30.v1
ohlc.atr_pct.w30.v1
volume.log1p.trend_tstat.w60.v1
```

The exact grammar may be refined, but it must be documented and tested.

## 9. Output

Persist a canonical long-form snapshot with at least:

```
entity_id
entity_family
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

Also materialize a wide research view/table:

```
entity_id | as_of_date | feature_1 | ... | feature_n
```

The wide form is a derived convenience object, not the source of truth.

## 10. Eligibility

An entity is eligible if:

- it has at least one market observation available by the cutoff;
- at least one configured feature can be computed.

Do not require 504 observations globally.

Feature coverage must be explicit so that young / sparse entities can coexist with long-history entities.

## 11. Cross-universe requirement

Run the exact same feature engine over every imported market universe with compatible observations.

Do not create separate hand-written feature implementations for equities, indices, commodities or crypto unless source semantics genuinely require an adapter.

The feature formula for a given feature_id must have the same meaning everywhere.

## 12. Quality report

Produce a machine-readable and human-readable audit containing:

- entity count by family;
- feature count;
- total cells;
- available / unavailable cell counts;
- coverage distribution by window;
- NaN / inf count;
- constant features;
- features with extreme values;
- duplicate feature IDs;
- per-feature min / p01 / median / p99 / max;
- top feature correlations / redundant pairs;
- entities with unusually low coverage.

Do not automatically drop correlated features in this spec. Report redundancy only.

## 13. Golden tests

Include deterministic synthetic fixtures that prove:

1. base-100 current value is exactly 100;
2. mean_delta is invariant to multiplying the source series by a constant;
3. trend_pct is invariant to multiplying the source series by a constant;
4. slope t-statistic and R² are invariant to source scale;
5. normalized std / variance are invariant to source scale;
6. no observation after cutoff influences a feature;
7. insufficient history yields explicit unavailable status, not silent zero;
8. replay is deterministic;
9. volume-only features remain unavailable when volume is absent;
10. no canonical feature has EUR/USD/raw-level units.

Add one golden real-data snapshot test for a small fixed set of entities at 2026-04-01, storing expected values with tolerances.

## 14. CLI

Provide a command similar to:

```
uv run python -m hocus_quant.cli build-feature-snapshot \
  --as-of 2026-04-01 \
  --output data/features/2026-04-01
```

A dry-run / audit-only mode is desirable.

## 15. Performance

The first implementation should comfortably process the currently imported corpus on the existing research machine.

Prefer vectorized Polars / DuckDB operations where practical.

Correctness and auditability take precedence over premature optimization.

## 16. Non-goals

Do not implement in SPEC-003:

- prediction targets;
- feature selection by model performance;
- ML models;
- trading signals;
- portfolio construction;
- transaction costs;
- automated live ingestion;
- claims of predictive power.

## 17. Deliverables

- feature formulas module(s);
- feature registry / naming contract;
- cross-sectional snapshot builder;
- long-form persisted output;
- wide research view;
- quality / coverage report;
- unit and golden tests;
- documentation of formulas and minimum history;
- CLI;
- updated README status.

## 18. Definition of done

SPEC-003 is complete when:

- the 2026-04-01 snapshot is reproducibly generated from local imported data;
- all canonical features satisfy the dimensionless invariant;
- outputs span every compatible imported universe;
- PIT tests prove no future leakage;
- quality report is persisted;
- pytest, Ruff and MyPy pass;
- the implementation does not depend on network access.
