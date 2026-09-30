# SPEC-005 — Target Factory V1

The target factory builds future outcomes `Y(entity, T, H)` independently from SPEC-003/004 features. A cutoff uses only observations available through 00:00 Europe/Paris on `T+1`; targets use daily observations whose session dates are strictly greater than `T`. Horizons are counts of observed sessions, never calendar offsets.

## V1 contracts

- `P0` is the final eligible close included by the SPEC-003 PIT loader at `T`. Adjusted close is not used.
- `PH` is the Hth future observed close. Incomplete windows stay unavailable and retain their observed count; they are never shortened.
- Realized future volatility is the sample standard deviation (`ddof=1`) of the `H-1` log returns between future closes `T+1` through `T+H`, annualized by `sqrt(252)`. No return involving `P0` enters this measure.
- Maximum drawdown is the minimum future-window peak-to-trough drawdown, `min(Pi / max(P1..Pi) - 1)`. Maximum upside/downside are extrema relative to `P0`.
- Future windows are screened by the frozen SPEC-003Q quality rules. Review or quarantine makes a target unavailable; a computable raw value is retained only as `candidate_value`, separate from `target_value`. There is no repair, winsorization, or split adjustment.
- Rank targets use valid absolute returns from cutoff-approved entities in the same `entity_family` at the same cutoff/horizon. Ties use average ascending rank divided by cohort size, matching percentile rank with average ties. Unavailable future outcomes do not join the cohort.
- Benchmark returns use the mapped series' own Hth observed close after the same cutoff; no calendar-date interpolation is performed. The method is recorded as `independent_hth_observed_close_per_entity`.
- Only French/SRD equity, German equity and US equity mappings are registered in V1. Other families have unavailable relative targets. No sector-relative target is implemented.
- Registry IDs, definitions, mappings and fingerprints are materialized in `src/hocus_quant/targets/*_registry.json` and each output manifest.
- PIT status remains `reconstructed`; `strict_pit_claimed` is always false. Source histories do not prove contemporaneous historical capture.

Future relative-window correlation (for example `future_corr(asset, benchmark, H)` over daily returns `T+1..T+H`), beta, covariance, tracking error, sector/country benchmarks and style-relative outcomes are V2 concepts only.

## CLI

```bash
uv run python -m hocus_quant.cli build-target-snapshot \
  --as-of 2026-04-01 --quality-scope approved \
  --output data/targets/2026-04-01

uv run python -m hocus_quant.cli build-target-set \
  --feature-cube data/feature_cube/weekly \
  --output data/targets/weekly --resume
```

The set builder takes the exact date grid from dated feature-cube manifests, intersects each slice's feature entities with its approved quality rows, and still loads mapped benchmark series independently. Targets use daily source histories even if feature cutoffs are weekly.

Each cutoff produces `targets.parquet`, a JSON/Markdown audit and a manifest. The set additionally produces a catalog DuckDB view named `targets`, a root manifest under `manifests/`, and an aggregate audit. Audits expose status and coverage counts, distributions, direction balances, cohort sizes, mapping coverage, incomplete horizons and extreme raw return candidates for review. Extreme values are reported, never altered.

## Output semantics

`target_value` is populated only when `target_status='available'`. `candidate_value` can hold a computed value for a future window later marked review/quarantined. `target_end_date` is populated only for a complete H-window; `last_future_observation_date` and `future_observation_count` describe truncated samples. Relative rows preserve benchmark ID, mapping version, start/end dates, observation count and matching method. All rows carry target and quality registry fingerprints.
