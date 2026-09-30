# SPEC-003R — hardening and audit record

**Scope:** audit and contract hardening of the 2026-04-01 feature snapshot.
No model, target, score, feature selection, correction, winsorization or
backtest was added.

## PIT evidence grade

The snapshot grade is **`reconstructed`**. The ABC Bourse bars used here were
captured in September 2026, after the 2026-04-01 cutoff. The archive lacks
historical vintages and revision timestamps; the engine applies the documented
session-date + one-day availability convention. All 1,674,050 included source
rows were retrieved after the cutoff. Therefore this slice is not strict / observed
PIT, and the run manifest explicitly sets `strict_pit_claimed=false`. Corporate
action and adjustment vintages remain unverified. See
[`POINT_IN_TIME.md`](POINT_IN_TIME.md).

## Golden regression

`tests/fixtures/features/spec003_golden_manifest.json` records the local
2026-04-01 reference slice and a fixed panel spanning all nine entity families.
The small ABC fixture tests formulas in normal CI; when the ignored large local
snapshot is present, an additional regression checks its entity/feature/cell
counts, availability, family composition and fixed panel values.

Reference snapshot:

- 2,194 entities and 1,048 feature IDs (2,299,312 cells);
- 2,208,926 available (96.069%), 90,386 unavailable;
- 9 families: equity/SRD 197, US equity 1,124, German equity 486, index 95,
  sector index 30, commodity 27, crypto 75, FX 145, bond 15;
- the registry fingerprint is frozen in the golden manifest and run metadata.

The count includes one additive, explicitly versioned RSI correction;
`rsi.w14.v1` remains part of the stable historical contract. Technical IDs
number 31, including the additional v2 RSI.

Regenerating these values intentionally requires updating the manifest and
documenting why. A change in formula or meaning requires a new `v2` feature ID;
a technical correction that leaves theoretical output unchanged may remain v1.

## Extreme feature audit

The existing threshold flags **348 feature IDs** for review. The generated
`data/features/2026-04-01/hardening_audit.md` gives
each feature's family, horizon, p01/p50/p99/min/max, up to three low-tail and
three high-tail entities, and their final five source bars. It also provides
the machine-readable `hardening_audit.json`. Categories are triage labels from
the available window, not verified causes. They do not alter the snapshot.

The main review group is discontinuity / possible corporate action. These
observations recur across multiple feature IDs and must not be interpreted as
hundreds of independent data events. The report separates observable OHLC
envelope violations, relative denominator collapse, large return discontinuity,
three-row formula sensitivity and residual family/sample tails. The primary
labels over the 348 feature IDs are 194 discontinuity/corporate-action
candidates, 150 family/sample tails and 4 short-window formula-sensitivity
reviews. These labels are derived from up to six tail entities per feature and
do not count independent events. An absolute
nominal price threshold is deliberately not used because it would violate the
price-scale invariance contract.

One formula/documentation mismatch was demonstrated: RSI `w14.v1` uses 14 close
values and therefore 13 close-to-close changes, while the former docs said 14
changes. The existing ID and output remain untouched. A new
`ohlc.technical.rsi.w15.v2` computes 14 close-to-close changes over 15 close
values. The golden panel covers both. No other formula defect was identified,
and no other v2 is required by this audit. Source-level anomalies remain a
separate blocker below.

## Input quality and readiness gate

The included raw-bar screening checks for (1) open/close outside the OHLC
low/high envelope, (2) intraday high-low range above 50% of close, and
(3) absolute close-to-close move of at least 30%. The audit reports these by
family, including affected entity counts. A large range or move is a review
candidate, not proof of a bad observation: genuine volatility and corporate
actions can produce such values. An OHLC envelope violation is a stronger source
quality issue and must be resolved against source documentation or raw files.

The screening found four OHLC bars outside a 2% envelope tolerance in four
entities (`FR0000051807`, `FR0011466069`, `US2220702037` and
`LU2089238112`), 2,815 bars with range above 50% of close across 172 entities, and
2,295 close jumps above 30% across 406 entities. The largest range/jump counts
are concentrated in imported index histories: `ABC003500476` (831 wide-range
bars; max range/close 11.71), `ABC003500477` (815; 259.86) and
`ABC003500468` (504; 2.04). As a result,
**the existing v1 feature IDs can be frozen (with the RSI v2 additive), but the
snapshot is not certified as clean market data and is not ready to feed
SPEC-004 directly**.
Resolve or explicitly quarantine affected input series in the data contract,
preserving raw inputs and documenting exclusions; rerun the golden snapshot and
review the changes before beginning targets or modeling. Existing v1 feature
values remain unchanged; the snapshot adds the RSI v2 column and retains the
2026-04-01 slice as the regression reference.

## Family distribution review

The separate family tables in the hardening audit cover mean delta, normalized
trend and t-statistic, standard deviation, annualized realized volatility, RSI,
ATR percent and relative volume where present. The current slice differs
materially by family: 20-session realized-volatility medians are about 51% for
crypto, 34–37% for equity families, 19% for indices and 10% for FX; index and
crypto 99th percentiles are much larger and reflect source discontinuities in
part. These are descriptive differences, not reasons to rescale or correct a
feature automatically. Relative volume is absent for many non-equity series,
and remains unavailable rather than set to zero.

The 21 global high-correlation pairs remain in the audit. Each pair is labeled
for expected same-series redundancy, quasi-duplication, technically distinct
near-correlation or sample-level review; qualifying correlations are also
reported by family. No pair or feature was removed.

## Verification

The implementation has invariant tests for independent price scaling, volume
scaling, family-agnostic formula semantics, missing-volume availability and
determinism. The as-of integration test asserts that retrieval after the
cutoff cannot be claimed strict PIT. The local golden regression protects the
2026-04-01 counts and fixed panel when the non-versioned snapshot is present.
