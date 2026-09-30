# SPEC-004 — Historical feature cube

Status: PLANNED AFTER SPEC-003  
Primary executor: Codex / Luna  
Depends on: validated and frozen SPEC-003 feature contract

## 1. Goal

Apply the exact SPEC-003 feature factory over a sequence of historical cutoff dates to construct the point-in-time feature cube:

```
entity × feature × time
```

SPEC-004 must not change feature semantics. Its purpose is temporal expansion, reproducibility and efficient research access.

## 2. Core invariant

For any entity e, feature f and cutoff T:

```
cube[e, f, T] == SPEC003_feature_factory(e, f, as_of=T)
```

A feature computed historically must be identical to the same feature computed as an isolated snapshot for that date.

## 3. Date grid

Start with trading dates supported by the available market corpus.

The implementation must make the date grid configurable.

Initial development may use a sparse cadence such as weekly cutoffs for fast validation, followed by daily trading-date materialization.

Document the exact chosen grid in every run manifest.

## 4. PIT rules

Each slice must obey all source-level availability constraints.

No later:

- market observation;
- AMF publication;
- metadata correction;
- instrument mapping;
- source correction

may leak into an earlier slice unless explicitly valid at that earlier date.

## 5. Storage

Persist a partitioned long-form dataset with efficient predicates on:

- as_of_date;
- entity_id;
- feature_id.

Recommended shape:

```
as_of_date
entity_id
entity_family
feature_id
feature_value
feature_status
coverage_count
coverage_ratio
formula_version
run_id
```

Provide DuckDB views for common wide research matrices.

Do not require one physically wide file containing all features.

## 6. Incremental build

The cube builder must support:

- building a date range;
- rebuilding one date;
- resuming an interrupted run;
- idempotent replay;
- detecting formula-version changes;
- avoiding recomputation of unchanged slices when safe.

Each build writes a manifest containing source snapshots / checksums, code version, feature registry version and cutoff range.

## 7. Validation

Tests must prove:

- historical slices equal isolated SPEC-003 snapshots;
- repeated builds are deterministic;
- later data does not alter earlier slices;
- correction-aware source semantics are honoured;
- unavailable history remains unavailable rather than backfilled from the future;
- feature version changes create distinguishable outputs.

## 8. Research exports

Provide helpers to materialize panels such as:

```
rows = entity_id × as_of_date
columns = feature_id
```

with configurable:

- entity families;
- date range;
- feature subsets;
- minimum coverage;
- missing-value policy.

Missing-value policy must be explicit and must not silently impute by default.

## 9. Non-goals

Do not implement:

- prediction targets;
- train/test splits;
- models;
- alpha scoring;
- portfolio simulation.

Those belong to later specs after the cube is validated.

## 10. Definition of done

SPEC-004 is complete when a configured historical range can be reproduced as a point-in-time feature cube whose individual slices are provably identical to SPEC-003 snapshot calculations.
