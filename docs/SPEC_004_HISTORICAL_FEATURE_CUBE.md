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

## Local benchmark (2026-09-30)

Measured on the local ABC research database, with 1,048 frozen features and
quality evaluated at each cutoff. The source history spans 2022-09-29 through
2026-09-28. Registry SHA-256 is
`97fc1dc4c34c54cedd41771c5dc30224db24427981639a0d46256a3a7d17f552`; quality
rules are `SPEC-003Q/1.0.0`, SHA-256
`047046e2a4eaa68b2bffcbf6b7611949aef94c4fc60eeeb5c54d1bdce4241c62`. Source
fingerprints are stored in each run's contract manifest. PIT grade is
`reconstructed`.

| Sparse cutoff | Approved entities in output | Cells | Available |
| --- | ---: | ---: | ---: |
| 2022-09-29 | 0 | 0 | n/a — no approved series yet |
| 2023-04-03 | 1,717 | 1,799,416 | 75.63% |
| 2024-04-01 | 1,674 | 1,754,352 | 87.26% |
| 2025-04-01 | 1,645 | 1,723,960 | 96.95% |
| 2026-01-02 | 1,767 | 1,851,816 | 94.56% |
| 2026-04-01 | 1,757 | 1,841,336 | 95.70% |
| 2026-09-28 | 1,687 | 1,767,976 | 96.05% |

Across the seven sparse partitions: 10,738,856 cells, 9,774,497 available
(91.02%; the first partition is empty), 83,717,147 bytes, 0 missing/error
partitions, and 402 quality-status transitions. Entity count was 0 / 1,687
median / 1,767 maximum including the initial empty cutoff. Summed slice time
was 771.7 s across the resumable invocations; non-empty slices took 95.6–151.4
s each. The as-of 2026-04-01 quality counts were 1,757 approved, 433 review,
and 4 quarantined. By 2026-09-28, the decisions were 1,689 approved, 479
review, and 32 quarantined; 1,687 approved entities had at least one output
feature.

The measured weekly tail (2026-09-04, 2026-09-11, 2026-09-18) contained
5,303,928 cells, 5,093,134 available (96.03%), occupied 43,711,195 bytes, and
took 425.2 s total (136.9–145.4 s per slice). The full source range resolves
to 210 weekly cutoffs and 1,314 daily cutoffs. Linear extrapolation from the
weekly tail is about 8.3 hours for the full weekly cube and 52 hours for daily;
these estimates exclude catalog/audit overhead and are not measured full-run
times. The main bottleneck is rebuilding the complete SPEC-003 snapshot and
quality audit at every cutoff.

Independent SPEC-003 runs were compared bidirectionally with the cube on
2023-04-03, 2026-04-01, and 2026-09-28. All three had identical row counts and
zero differences across entity/family, feature ID/value/status, coverage,
window, source-series, and formula-version fields. Collectively, the slices
include equity, index, commodity, crypto, FX, and bond families. A future
quality anomaly test also verifies that a later quarantine does not alter an
earlier slice. These results validate the cube implementation against the
existing reconstructed-PIT inputs; they do not improve the source's PIT grade.

Local output directories `data/feature_cube/spec004-sparse/` and
`data/feature_cube/spec004-weekly-tail/` are ignored by Git. The weekly range
was generated only for a three-week performance sample; the 210-week grid is
resolved and ready to generate, but was not materialized end-to-end.

**Recommendation:** `weekly sufficient for next research stage`. Daily is not
reasonable for routine iteration at the measured cost; the historical weekly
build is possible as an overnight/one-off job, and incremental slices avoid
repeating completed partitions.

## Limitations

- PIT is `reconstructed`, and must not be described as strict historic
  availability.
- Cutoffs use available source dates, not an exchange-session calendar.
- The first builder calls the complete snapshot engine for every date; it is
  correctness-first and may be expensive at 210 weekly or ~1,000 daily dates.
- No targets, models, scores, portfolio construction, or backtests are part of
  this specification.
