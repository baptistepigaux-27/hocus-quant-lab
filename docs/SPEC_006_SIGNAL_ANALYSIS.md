# SPEC-006 — Univariate Signal Analysis

SPEC-006 measures historical associations between a SPEC-004 feature known at a
cutoff and a SPEC-005R research-ready future outcome. It is an exploratory
signal atlas. It does not train a model, select a portfolio, estimate costs, or
claim a tradable return.

## Input contract

- Feature cube: `quality_scope=approved`, point-in-time grade `reconstructed`.
- Target set: only rows with `research_ready=true` and `target_status=available`.
- Join: exact `entity_id`, `entity_family`, and `as_of_date` equality.
- Feature values must be marked `available` and finite.
- Cutoffs are analyzed only when both feature and target partitions exist.
- Scope `global` is accompanied by separate scopes for each present asset family.
  Family results are never averaged into the global result.

## Statistical definitions

At each cutoff and scope, Pearson and Spearman correlations are calculated
cross-sectionally across entities using pairwise complete observations. Spearman
uses average ranks for ties. This time series of cross-sectional correlations is
the primary Information Coefficient (IC).

- `pearson_ic_mean`, `spearman_ic_mean`: arithmetic mean across cutoff ICs.
- `ic_median`, `ic_std`, `hit_rate`: median, sample standard deviation, and
  proportion of cutoff Spearman ICs greater than zero.
- `ic_t_stat`: mean Spearman IC divided by its standard error across cutoffs.
- `p_value_descriptive`: two-sided Student t reference probability with
  `cutoff_count - 1` degrees of freedom. It is descriptive, not a causal or
  out-of-sample test. Weekly observations overlap, especially for long targets;
  this t reference does not correct the resulting serial dependence, so neither
  p-values nor FDR q-values are formal significance claims.
- `fdr_q_value`, `fdr_rank`: Benjamini-Hochberg correction separately within
  `(scope, target family, horizon)` among rows meeting the minimum cutoff count.
- `pearson_pooled`: Pearson correlation across all aligned entity-cutoff rows,
  computed from pairwise sufficient statistics.
- `spearman_pooled`: Spearman correlation after ranking each feature and target
  over their pairwise complete entity-cutoff observations. It is reported by
  scope and uses ordinary average ranks; it is sensitive to missingness and
  changing universe composition. The cross-sectional Spearman IC remains the
  primary rank association.
- `coverage`: N divided by research-ready target observations at each cutoff,
  weighted by N across cutoffs.

Decile membership is ranked independently at every cutoff, after pairwise
availability filtering. D1 is the lowest feature bucket and D10 the highest.
The reported mean and dispersion pool the per-cutoff bucket moments weighted by
bucket count; the median is the median of cutoff-level bucket medians.
`top_bottom_spread` retains its observed sign. Direction targets also report
positive rate and lift over the same cutoff's population positive rate.

The period table reports a mean and median IC for each calendar year and keeps
its first and last cutoff. Incomplete calendar years are labeled
`partial_calendar_year`; a period with fewer than four cutoffs is retained with
`status=insufficient_period_n`.
FDR and the independent descriptive axes do not create a composite score.
Each summary row carries the compact feature family/source series/metric/window
metadata and the target formula/scale copied from the frozen registries. The
full registry documents remain the authoritative definitions.

## Build and replay

```sh
uv run python -m hocus_quant.cli build-feature-cube \
  --start 2024-04-05 --end 2026-04-03 --cadence weekly \
  --quality-scope approved --output data/feature_cube/spec006-weekly-demo --resume

uv run python -m hocus_quant.cli build-target-set \
  --feature-cube data/feature_cube/spec006-weekly-demo \
  --output data/targets/spec006-weekly-demo --resume

uv run python -m hocus_quant.cli analyze-signals \
  --feature-cube data/feature_cube/spec006-weekly-demo \
  --target-set data/targets/spec006-weekly-demo \
  --output data/analysis/spec006-weekly-demo
```

Analysis writes resumable per-cutoff Parquet under `cutoffs/`, final Parquet
datasets, aligned wide X/Y panels under `pooled_panels/`, and `signals.duckdb`.
DuckDB exposes `signal_summary`, `signal_deciles`,
`signal_ic_history`, `signal_period_stability`, `signal_pooled_spearman`,
`signal_by_family`, and `signal_top_candidates`. The candidate view applies only mechanical defaults:
global scope, at least 1,000 aligned rows, at least the configured cutoff
minimum, coverage at least 0.60, and FDR q at most 0.25. It is not a scientific
selection.

The analysis database is opened read-only by the marimo explorer. Set
`HOCUS_QUANT_SIGNALS_DB` to point the UI to another local analysis output.
Hosted UI remains behind the existing sandbox authentication.
