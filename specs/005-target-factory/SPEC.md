# SPEC-005 — Target Factory

Status: READY FOR IMPLEMENTATION
Primary executor: Codex / Luna
Depends on: SPEC-003/003Q frozen feature contract and SPEC-004 historical cube

## 1. Goal

Implement a deterministic target factory that constructs future outcomes Y(entity,T,H) independently from the feature engine.

Read first:

- `docs/TARGET_RESEARCH_PHILOSOPHY.md`
- `docs/POINT_IN_TIME.md`
- `docs/SPEC_003Q_MARKET_DATA_QUALITY.md`
- `docs/SPEC_004_HISTORICAL_FEATURE_CUBE.md`

Do not modify SPEC-003 feature formulas.

## 2. Core contract

For each eligible entity e, cutoff T and horizon H:

```
X(e,T) uses only information <= T
Y(e,T,H) uses observations strictly after T
```

No target computation may affect the feature cube.

## 3. Horizons

Implement:

```
5, 10, 20, 60, 120
```

These are counts of future observed sessions for the entity, not calendar days.

Persist both requested horizon and actual end observation date.

## 4. Primitive absolute return

For close price P:

```
return_abs_H = P_H / P_0 - 1
```

P_0 is the last eligible close at cutoff T.
P_H is the H-th future eligible close after T.

Do not use adjusted close in V1 unless an explicitly verified contract exists.

## 5. Relative return

Implement:

```
return_rel_H = return_asset_H - return_benchmark_H
```

Relative targets require an explicit benchmark mapping.

Persist:

- `benchmark_id`
- `benchmark_family`
- `benchmark_mapping_version`
- `benchmark_start_date`
- `benchmark_end_date`

V1 benchmark philosophy: broad market benchmark appropriate to the equity universe.

Do not implement sector-relative targets yet.

If no justified benchmark mapping exists, mark relative targets unavailable rather than guessing.

## 6. Benchmark registry

Create a versioned benchmark registry / mapping contract.

Initial intended scope:

- French/SRD equities -> broad French market benchmark available in corpus;
- German equities -> broad German market benchmark available in corpus;
- US equities -> broad US market benchmark available in corpus.

For indices, commodities, crypto, FX/rates and bonds, only define relative targets where an explicit meaningful benchmark is documented.

The implementation must make adding sector benchmarks later straightforward without changing V1 IDs.

## 7. Direction targets

Derive from continuous primitive returns:

```
direction_abs_H =
  +1 if return_abs_H > 0
   0 if return_abs_H == 0
  -1 if return_abs_H < 0
```

```
direction_rel_H = sign(return_rel_H)
```

Persist continuous and direction targets separately.

## 8. Future volatility

Compute realized volatility from future close-to-close log returns over the future window.

Use an explicitly documented formula and annualization convention.

Suggested V1:

```
std(log returns over future H sessions) * sqrt(252)
```

Do not use observations at or before T in the future-volatility calculation.

## 9. Future drawdown / extrema

Implement:

- future max drawdown;
- future maximum upside relative to P_0;
- future maximum downside relative to P_0.

Document formulas precisely.

Suggested definitions:

```
max_upside_H = max(P_t/P_0 - 1), t in future window
max_downside_H = min(P_t/P_0 - 1), t in future window
```

Max drawdown must use rolling future peaks, not simply minimum return from P_0.

## 10. Cross-sectional rank

For valid absolute-return targets at the same T/H, produce:

- percentile rank;
- optional ordinal rank;
- cohort size.

V1 cohort should be explicit and simple, preferably same `entity_family`.

Only entities eligible at T and with valid future target windows enter the cohort.

Persist `cohort_id` / `cohort_definition_version`.

## 11. Quality scope at cutoff

Target rows should be built for entities approved at cutoff T using the same historical point-in-time quality logic as SPEC-004.

Do not project final quality status backward.

Persist the quality rule version/fingerprint used at T.

## 12. Future-window quality

Assess the future target window independently.

A target must carry a status such as:

- `available`
- `insufficient_future_history`
- `benchmark_unavailable`
- `future_quality_review`
- `future_quality_quarantined`
- `undefined`

Do not silently compute through confirmed bad bars.

For review-only future events, choose a conservative documented V1 policy and expose both the raw evidence and target status.

No automatic correction/winsorization/split adjustment.

## 13. PIT grade

Persist:

```
pit_grade = reconstructed
strict_pit_claimed = false
```

Target availability is forward-looking by design, but source-history claims remain reconstructed PIT.

Do not imply contemporaneous historical capture.

## 14. Target IDs

Use stable versioned IDs.

Examples:

```
future.return_abs.h5.v1
future.return_abs.h20.v1
future.return_rel.h20.market.v1
future.direction_abs.h20.v1
future.direction_rel.h20.market.v1
future.volatility.h20.v1
future.max_drawdown.h60.v1
future.max_upside.h60.v1
future.max_downside.h60.v1
future.rank_pct.h20.family.v1
```

Formula changes require a new version.

## 15. Canonical output

Create long-form canonical output with at least:

```
entity_id
entity_family
as_of_date
target_id
target_value
target_status
horizon
target_end_date
benchmark_id
benchmark_mapping_version
cohort_id
future_observation_count
quality_rules_fingerprint
target_registry_fingerprint
pit_grade
formula_version
```

A wide research export may be derived later/concurrently.

## 16. Target registry

Create a versioned target registry describing:

- target_id;
- family;
- formula;
- horizon;
- minimum future observations;
- scale;
- benchmark requirement;
- cohort requirement;
- formula_version.

Persist a deterministic registry fingerprint.

## 17. Storage

Suggested layout:

```
data/targets/
  as_of_date=YYYY-MM-DD/
    targets.parquet
    manifest.json
  manifests/
  target_catalog.duckdb
  target_audit.json
  target_audit.md
```

Do not commit generated market data artifacts.

## 18. Alignment with weekly feature cube

The next research stage uses weekly feature cutoffs.

SPEC-005 must therefore be able to generate targets for arbitrary explicit cutoff dates and especially the weekly SPEC-004 date grid.

Targets themselves use daily source observations to resolve future horizons.

Do not reduce the target calculation to weekly prices.

## 19. End-of-sample handling

Near the end of the dataset, future horizons may be incomplete.

Do not shorten horizons silently.

Example: if only 17 future sessions exist for H=20, target is unavailable with `insufficient_future_history`.

Persist observed future count.

## 20. Determinism

Same:

- source data;
- cutoff;
- horizon;
- target registry;
- benchmark registry;
- quality rules

must produce identical target output/fingerprint.

## 21. Tests

Add deterministic tests proving:

1. H counts future observed sessions, not calendar days;
2. P_0 comes from cutoff, future observations begin strictly after T;
3. return_abs is correct;
4. return_rel uses the mapped benchmark and same requested horizon logic;
5. direction_abs matches return_abs sign;
6. direction_rel matches return_rel sign;
7. future volatility reads no pre-cutoff return;
8. max drawdown uses future rolling peaks;
9. insufficient future history never shortens H;
10. absent benchmark makes relative target unavailable;
11. future quarantined bad bar is not silently consumed;
12. future review behavior follows documented policy;
13. quality status at T is point-in-time, not projected backward;
14. rank cohort excludes invalid/unavailable future targets;
15. replay is deterministic;
16. target registry and benchmark registry fingerprints are persisted;
17. reconstructed PIT metadata is preserved.

Include a small real-data golden panel across several entity families where possible.

## 22. CLI

Provide commands similar to:

```
uv run python -m hocus_quant.cli build-target-snapshot \
  --as-of 2026-04-01 \
  --quality-scope approved \
  --output data/targets/2026-04-01
```

and preferably:

```
uv run python -m hocus_quant.cli build-target-set \
  --feature-cube data/feature_cube/... \
  --output data/targets/weekly
```

The latter should reuse the exact cutoff grid from an existing feature-cube manifest where possible.

## 23. Audit

Produce audit metrics including:

- target rows/cells by horizon;
- availability by target/horizon/family;
- benchmark mapping coverage;
- unavailable reasons;
- future-window quality exclusions;
- distributions of absolute/relative returns;
- direction balance;
- rank coverage;
- end-of-sample attrition;
- extreme target values for review.

Do not winsorize.

## 24. Planned V2 extensions — document only

Architecture must anticipate, but V1 must not implement:

- sector-relative returns;
- country-relative alternatives;
- beta-adjusted excess return;
- future asset/benchmark correlation;
- future beta;
- future covariance;
- future tracking error;
- other multi-series relational outcomes.

In particular document the future concept:

```
future_corr(asset, benchmark, H)
```

computed on future daily returns over T+1..T+H.

## 25. Non-goals

Do not implement:

- feature selection;
- signal scan;
- train/test split;
- ML;
- predictive score;
- trading strategy;
- portfolio;
- transaction costs;
- backtest.

## 26. Definition of done

SPEC-005 is complete when:

- primitive and derived V1 targets are reproducible;
- absolute and relative direction exist;
- benchmark mappings are explicit/versioned;
- weekly feature cutoffs can receive daily-resolution future targets;
- future quality/anomaly handling is explicit;
- no horizon is silently shortened;
- target registry is frozen/fingerprinted;
- audit is produced;
- pytest, Ruff and MyPy pass.

## 27. Final report expected

Report:

- cutoffs tested;
- target IDs/count;
- coverage by horizon;
- benchmark mapping coverage;
- absolute/relative direction balance;
- end-of-sample attrition;
- future quality exclusions;
- anomalous target values;
- target registry fingerprint;
- benchmark registry fingerprint;
- tests passed;
- files changed;
- final SHA.

Conclude whether the target contract is ready for SPEC-006 univariate signal analysis.
