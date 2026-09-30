# Target research philosophy

Status: reference document
Scope: outcome construction for future-return and future-risk research

## 1. Purpose

The feature system describes what is known at cutoff T. The target system describes what happens after T.

The two layers must remain conceptually and technically separate:

```
X(entity, T) = information available up to T
Y(entity, T, H) = outcome observed after T over horizon H
```

The target factory must never feed future information back into feature construction.

## 2. Primitive targets first

Targets should be built from continuous primitive outcomes before deriving classes.

Primary primitive:

```
return_abs_H = P(T+H) / P(T) - 1
```

where H is counted in future observed market sessions for the entity.

Derived labels such as up/down or top/bottom quantiles must be built from these primitives rather than replacing them.

## 3. Absolute versus relative outcomes

Absolute return measures the asset's own future performance.

Relative return measures future performance against an explicit benchmark:

```
return_rel_H = return_asset_H - return_benchmark_H
```

A relative target is meaningless without benchmark identity and method. Every relative target must therefore preserve:

- benchmark_id;
- benchmark_family;
- benchmark_mapping_version;
- matching method;
- horizon;
- target formula version.

The initial V1 benchmark should be a broad market benchmark appropriate to the asset's universe. Sector-relative outcomes are deliberately deferred to a later phase.

## 4. Direction targets

Direction exists in two distinct forms:

```
direction_abs_H = sign(return_abs_H)
direction_rel_H = sign(return_rel_H)
```

Interpretation:

- absolute direction: future rise/fall;
- relative direction: future over/under-performance versus benchmark.

The continuous return remains the source of truth.

## 5. Initial horizons

Initial target horizons:

- 5 sessions;
- 10 sessions;
- 20 sessions;
- 60 sessions;
- 120 sessions.

Targets use future source observations rather than calendar-day offsets.

## 6. Initial V1 target families

For each eligible entity/cutoff/horizon:

- absolute future return;
- relative future return;
- absolute direction;
- relative direction;
- future realized volatility;
- future maximum drawdown;
- future maximum upside;
- future maximum downside;
- future cross-sectional return percentile/rank where a valid comparison cohort exists.

## 7. Benchmark philosophy

V1 uses broad-market references, not sector references.

Examples of intended mapping logic:

- French / SRD equity -> broad French equity benchmark when available;
- German equity -> broad German equity benchmark;
- US equity -> broad US equity benchmark;
- other asset families require an explicit documented benchmark or no relative target.

Do not invent a benchmark when the dataset cannot justify one.

Benchmark mappings must be data contracts, not hard-coded assumptions hidden in formulas.

Future extensions may add:

- sector-relative return;
- country-relative return;
- beta-adjusted excess return;
- style-factor-relative return.

## 8. Cross-sectional rank targets

At a given cutoff T and horizon H, a rank target describes where an entity's future return sits within an eligible comparison cohort.

The cohort definition must be explicit and point-in-time safe.

Possible V1 cohort:

- same entity family;
- valid absolute return;
- approved quality at T;
- sufficient future observations.

Ranks must never include an entity merely because it survives until the end of the dataset.

## 9. Future risk targets

Future realized volatility is measured only from observations strictly after T over the target horizon.

Future drawdown is the worst peak-to-trough decline inside the future window.

Future max upside/downside describe extrema relative to the starting price at T.

These are outcomes, not input features.

## 10. Quality and corporate-action caveat

Current ABC histories are reconstructed PIT and corporate-action vintages are not fully verified.

The target factory must not silently transform suspicious jumps into returns.

Future windows affected by:

- quarantined source bars;
- quality review events;
- likely scale changes;
- unverified corporate-action discontinuities

must carry an explicit target quality/status field.

The system should prefer unavailable/review status over a misleading numerical target.

No automatic split adjustment belongs in V1.

## 11. Target identity and versioning

Every target requires a stable ID.

Suggested grammar:

```
<target_family>.<metric>.h<horizon>[.<benchmark_scope>].v<version>
```

Examples:

```
future.return_abs.h20.v1
future.return_rel.h20.market.v1
future.direction_abs.h20.v1
future.direction_rel.h20.market.v1
future.volatility.h20.v1
future.max_drawdown.h60.v1
future.rank_pct.h20.family.v1
```

A semantic change requires a new version.

## 12. Relation targets are a planned extension

V1 targets are primarily scalar outcomes for one entity.

Later versions may include future relationships between series, for example:

- future correlation between an equity and its benchmark;
- future beta;
- future covariance;
- future relative volatility;
- future tracking error;
- future regime-change indicators.

Example concept:

```
future_corr(asset, benchmark, H)
```

computed from daily returns over T+1..T+H.

These targets are explicitly anticipated by the architecture but are out of scope for SPEC-005 V1.

## 13. Separation from modeling

The target factory does not decide whether an outcome is predictable.

It only constructs auditable future outcomes.

Feature selection, signal tests, econometric relationships, machine learning, portfolio construction and backtesting belong to later stages.

## 14. Research sequence

The intended sequence is:

1. feature measurement;
2. historical feature cube;
3. target construction;
4. univariate relationship testing;
5. multivariate models;
6. portfolio/execution analysis.

This preserves the distinction between measuring the past, defining the future outcome, and evaluating whether the former predicts the latter.
