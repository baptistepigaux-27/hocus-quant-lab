# SPEC-004 — Historical Feature Cube

## Purpose and boundaries

The cube applies the frozen SPEC-003 snapshot builder independently at each
cutoff. Its canonical output is long-form Parquet, partitioned by
`as_of_date=YYYY-MM-DD/`. Feature definitions and calculations remain owned by
SPEC-003. Research cubes require `quality_scope=approved`; the source layers
retain `review` and `quarantined` rows. The source is reconstructed-PIT, not
strict observed-PIT: ABC history is assigned availability at session date +
one day and has no historical vintages or corporate-action lineage.

## Date grid

`explicit` resolves each requested cutoff to the latest observed session on or
before that date. `weekly` keeps the final distinct source session in each ISO
week. `daily` keeps every distinct date present in either market history view.
Range endpoints are inclusive. These are source-observation dates rather than
an exchange calendar; a date is never fabricated when the corpus has no row.

Example:

```bash
uv run python -m hocus_quant.cli build-feature-cube \
  --start 2026-09-01 --end 2026-09-30 --cadence weekly \
  --quality-scope approved --output data/feature_cube/weekly-tail
```

Use `--dry-run` to inspect the resolved dates and contract. `--resume` reuses
valid partitions and repairs invalid ones; `--force` rebuilds requested
partitions. A different registry, quality rules, source fingerprint, or code
contract requires a new output directory. Each slice is independently
reproducible with `build-feature-snapshot --as-of DATE --quality-scope
approved`.

## Layout and manifests

Each date directory contains `features.parquet`, `quality_status.parquet`, and
`manifest.json`. The root has `contract.json`, a run manifest in `manifests/`,
`cube_audit.json`/`.md`, and `feature_cube.duckdb` views for `features_long`,
`features_wide`, and `quality_status`. Run manifests record code SHA and dirty
state, source/registry/quality fingerprints, PIT grade, cadence, resolved
dates, per-slice entities/cells/coverage/hash/duration, reused and failed
slices. Partition hashes make replay checks deterministic. Data directories
are local artifacts and must not be committed.

The research export helper and `export-feature-panel` CLI pivot a selected
long-form subset to rows `(entity_id, as_of_date)` and columns `feature_id`.
It supports time, family, feature, entity, and minimum-coverage filters. It
does not impute; missing values remain null.

## Temporal audit

`audit-feature-cube CUBE_DIR` reports coverage and availability per date and
horizon, entity arrivals/disappearances, quality-status transitions,
distribution summaries, missing partitions, and errors. Quality decisions are
recomputed by the existing SPEC-003 path at each historical cutoff; the final
quality state is not projected backward.

## Performance procedure

Start with representative sparse dates, then benchmark a short weekly range.
Estimate a full-grid runtime from observed median/mean slice duration and
compare it with the research iteration budget. The initial implementation
deliberately favors exact SPEC-003 equivalence and independent partitions over
rolling-cache optimizations. Daily materialization is optional until weekly
runtime, storage, and iteration needs justify it.

## Limitations

- PIT is `reconstructed`, and must not be described as strict historic
  availability.
- Cutoffs use available source dates, not an exchange-session calendar.
- The first builder calls the complete snapshot engine for every date; it is
  correctness-first and may be expensive at 210 weekly or ~1,000 daily dates.
- No targets, models, scores, portfolio construction, or backtests are part of
  this specification.
