# SPEC-006R — Period Stability & Validation Atlas

## Purpose

SPEC-006R separates **discovery** from **validation**. A discovery database
chooses and freezes signal relations. Later date windows are then evaluated
without reranking or replacing those relations. The configured periods must
have distinct IDs and non-overlapping calendar dates; the pipeline rejects an
overlap before it reads validation data.

This remains descriptive univariate research. It does not train a model, choose
a portfolio, run a backtest, or claim a profitable or validated alpha signal.

## Periods and two discovery cohorts

The shipped configuration is
[`configs/experiments/stability_atlas.toml`](../configs/experiments/stability_atlas.toml):

| Role | Configured window | Observed cutoffs |
| --- | --- | ---: |
| Discovery | 2024-04-05–2024-10-04 | 27 |
| Validation | 2025-04-05–2025-10-04 | 27 |
| Validation | 2026-04-05–2026-10-04 | 27, observed through 2026-09-28 |

The validation window persists configured dates, actual first/last cutoff,
theoretical cutoff count, target-mature cutoff count, and maturity ratio at
signal/horizon/scope level. “Mature” means at least the configured 30 usable
research-ready target outcomes for that horizon and evaluation scope. The
feature-target pair still needs the same minimum to produce an IC.

Two separate top-N cohorts are frozen for each supported discovery scope:

- `general`: all target families, currently led by future volatility and
  drawdown relations;
- `return_direction`: only `return_abs`, `return_rel`, `direction_abs`,
  `direction_rel`, and `rank_pct`.

The initial scopes are `equity`, `equity_us`, and `equity_de`. A scope with fewer
than N candidates is recorded with its candidate count and is not silently
padded. The primary comparison and regression baseline use `equity`.

## Frozen selection contract

`freeze_top_signals(discovery_period, target_scope, N)` reads only the discovery
`signal_summary` table. V1 selects eligible rows with `n_total >= 1,000`, at
least 13 discovery cutoffs, and coverage >= 0.60. The stable rule identifier is
`q_abs_ic_coverage_cutoff_v1`; within the chosen general/return cohort it sorts
by:

1. FDR q-value ascending (nulls last);
2. absolute mean cross-sectional Spearman IC descending;
3. coverage descending;
4. discovery cutoff count descending;
5. feature and target IDs ascending.

Each frozen row stores its discovery rank and measurements, rule version,
period, scope, target family/horizon, feature/target definitions, and stable
`signal_id`. Identity includes feature ID, target ID, horizon, selected entity
scope/family, and metric/target definition; the same relation retains its ID in
later periods.

## Metrics and descriptive classes

For each frozen signal and evaluation period the outputs contain mean/median
cross-sectional Spearman IC, t-statistic, hit rate, cutoff count, total aligned
observations, top-minus-bottom decile target spread, decile monotonicity,
descriptive p-value/FDR, and ranking within the frozen cohort. The rank
retention field is discovery absolute-IC rank divided by validation absolute-IC
rank; it is intentionally uncapped.

- **Sign retained:** validation mean IC and discovery mean IC have the same
  sign.
- **Impact retention:** `abs(validation mean IC) / abs(discovery mean IC)`.
- **Signed retention:** `validation mean IC / discovery mean IC`. A negative
  value indicates a direction reversal; values above one indicate amplification.
- **Period consistency:** number of later periods with an evaluable IC and the
  number retaining the discovery sign.
- **Evidence level:** `thin` below four target-mature cutoffs, `partial` from
  four through twelve, and `adequate` from thirteen. This is an information
  quantity label, not a statistical confidence probability.

The stability classes use separate, reviewable thresholds from config:

1. `insufficient_validation` if fewer than four cutoffs have mature targets or
   an IC;
2. `sign_reversed` when an adequately observed period's mean IC changes sign;
3. `unstable` when fewer than 60% of observed cutoff IC signs agree with the
   discovery sign;
4. `stable` when the sign is retained, absolute impact retention is at least
   0.80, and target maturity is at least 0.80;
5. `weakened` when the sign is retained but the stable conditions are not met.

The raw `sign_retained` and observed reversal remain available even when the
class is `insufficient_validation`. This avoids hiding a short-sample sign flip.
FDR values are adjusted within the frozen tested cohort by period, family, and
horizon. They are descriptive; weekly cutoffs and future targets overlap.

## Current reproducibility baseline

On the present local data snapshot, the primary `equity` general top 100
reproduces 100/100 retained signs and median impact retention 95.6% in 2025.
In 2026 all 100 have an observed aligned average sign, median impact retention
93.0%, but the 70 H120 risk/drawdown relations have only two mature cutoffs and
are classified `insufficient_validation`.

The primary return/direction top 100 reproduces 6/100 retained signs in 2025;
mean IC goes from -0.0999 in discovery to +0.0482 in validation and median
absolute-impact retention is 22.9%. In 2026, 69 of 100 relations have an IC
observed on the first two cutoffs, and all 69 reverse the discovery sign; 31
have no evaluable IC. All 100 are below the four-cutoff evidence threshold and
are therefore classified `insufficient_validation`, even where the observed
two-cutoff mean has reversed. H120 target maturity is approximately 4.9% for
`return_abs` and 3.5% for `return_rel`.

These figures are regression baselines for the pipeline, not inferential
claims. Family-specific relations and maturity are visible separately in the
Parquet atlas.

## Outputs and replay

```sh
uv run python -m hocus_quant.cli build-stability-atlas \
  --config configs/experiments/stability_atlas.toml \
  --output data/analysis/spec006r-stability-atlas
```

The builder writes:

- `frozen_top_signals.parquet` — persisted discovery selection and metrics;
- `signal_stability_summary.parquet` — primary scope, signal × period;
- `signal_stability_by_family.parquet` — signal × period × evaluation scope;
- `signal_period_metrics.parquet` — long-form aggregate metrics;
- `signal_period_ic_history.parquet` — cutoff-level IC timeline;
- `signal_period_deciles.parquet` — discovery and validation decile rows;
- `stability_audit.json` and `stability_audit.md` — periods, maturity, counts,
  regression figures, and selection invariant.

All analytical outputs are generated locally under `data/` and are ignored by
Git. Replaying the same config and immutable source contracts yields the same
selection and rows.

## Sandbox and interpretation

The marimo **Stability Atlas** keeps general risk signals separate from return /
direction signals, supports scope/family/horizon/class/maturity/discovery-sign
filters, shows an IC heatmap and risk-vs-return aggregates, and opens a selected
signal's discovery/validation IC timeline, deciles, signed retention, maturity,
family slices, and descriptive method note. Hosted access remains behind the
sandbox's existing authentication. The view uses no “validated alpha”,
profitability, or winning-signal language.

The source market universe is not a historically reconstructed SBF 120. PIT
quality remains `reconstructed`. No conclusion here should be interpreted as a
tradable edge or independent statistical confirmation.
