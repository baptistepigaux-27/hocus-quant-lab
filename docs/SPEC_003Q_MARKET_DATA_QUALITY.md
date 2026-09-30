# SPEC-003Q — Market Data Quality & Quarantine

**Status:** implemented for the reconstructed snapshot dated 2026-04-01.  
**Rules:** `SPEC-003Q/1.0.0`, SHA-256 `047046e2a4eaa68b2bffcbf6b7611949aef94c4fc60eeeb5c54d1bdce4241c62`.  
**Scope:** input-series assessment only. Prices are never corrected, adjusted,
winsorized or removed from raw/bronze/silver storage.

## Contract

Every series included in the technically usable snapshot receives one of three
stable statuses:

- `approved`: no configured hard or review rule fired in observations available
  by the requested cutoff;
- `review`: at least one review-only rule fired; the series remains intact but
  is omitted from `--quality-scope approved`;
- `quarantined`: at least one hard rule fired; the series remains intact but is
  omitted from the research-cleared scope.

Hard rules quarantine a non-finite numeric field, a negative volume, `high < low`,
or an open/close outside the low/high envelope by more than 2% of close. Review
rules flag a close-to-close move of at least 30%, a daily high-low range above
50% of close, or a close ratio within 2% of 0.01, 0.1, 10 or 100. A close and
volume move consistent with a common split factor is labeled probable corporate
action; it is still review-only. No rule repairs a price. Large movement or
volatility alone never means quarantine.

The assessment receives only rows selected by the builder's session-date and
`available_at` cutoff. Both decision evidence and any detected break are
therefore bounded by that as-of horizon. The later-retrieved label workbook is
used only to explain the three index cases below; it does not affect their
automated status or the 2026-04-01 decision.

Rebuild either view with:

```sh
uv run python -m hocus_quant.cli build-feature-snapshot \
  --as-of 2026-04-01 --output data/features/2026-04-01 \
  --quality-scope all

uv run python -m hocus_quant.cli build-feature-snapshot \
  --as-of 2026-04-01 --output data/features/2026-04-01/research-cleared \
  --quality-scope approved
```

The default remains `all` to preserve the SPEC-003R golden contract. Both
machine-readable audits persist the rule version and fingerprint. The raw
snapshot is the compatibility/reconstruction scope; the approved snapshot is
the research-cleared scope.

## 2026-04-01 quality audit

The 2,194 series used by the reconstructed raw snapshot were assessed using
observations available by 2026-04-02 00:00 Europe/Paris:

| Status | Series | Research-cleared treatment |
| --- | ---: | --- |
| Approved | 1,757 | Included |
| Review | 433 | Excluded pending review |
| Quarantined | 4 | Excluded |

| Family | Approved | Review | Quarantined |
| --- | ---: | ---: | ---: |
| bond | 15 | 0 | 0 |
| commodity | 21 | 6 | 0 |
| crypto | 8 | 67 | 0 |
| equity / SRD | 162 | 32 | 3 |
| German equities | 386 | 99 | 1 |
| US equities | 932 | 192 | 0 |
| FX and rates | 120 | 25 | 0 |
| indices | 84 | 11 | 0 |
| sector indices | 29 | 1 | 0 |

The review count is deliberately broad: one very large move or range is enough
to keep a series out of the first research-cleared universe. This is a review
gate, not a claim that all 433 series contain errors. Most have only candidate
events; an event can reflect real volatility, a corporate action or an
unverified price convention.

## Priority investigations

The four OHLC-envelope cases were checked against the original source records.
The raw CSV values exactly match the normalized DuckDB values. This confirms the
bad bar is present in the delivered source file and rules out a numeric parsing
change in Quant Lab. It does not establish why ABC Bourse supplied it.

| Series | Date | OHLC (source values) | Finding / status |
| --- | --- | --- | --- |
| `FR0000051807` (SRD) | 2025-05-26 | 93.32 / 90.40 / 90.42 / 90.30 | Open exceeds high by 2.92 (3.23% of close); high is 0.02 below low. Neighboring 2025-05-23 and 2025-05-27 bars are internally ordered. Exact source row is in `Cotations20250516.txt`; **quarantined**, source inconsistency confirmed, cause unknown. |
| `FR0011466069` (SRD) | 2025-05-26 | 3.81 / 3.99 / 3.93 / 3.975 | Open is 0.12 below low (3.02% of close). Neighboring bars are internally ordered. Exact source row is in `Cotations20250516.txt`; **quarantined**, source inconsistency confirmed, cause unknown. |
| `US2220702037` (SRD daily snapshot) | 2025-06-04 | 4.9775 / 4.25 / 4.2225 / 4.25 | Open exceeds high by 0.7275 (17.12% of close). Neighboring June 3 and 5 bars are valid. Exact source row is in `Cotations20250516.txt`; **quarantined** for this SRD series. |
| `LU2089238112` (German equities) | 2025-03-17 | 30.5875 / 30.5875 / 30.5875 / 28.255 | Close is 2.3325 below low (8.26% of close). Exact raw line in `Cotations20250317.txt` matches DuckDB. It is the first observation; the next available observation is 2025-04-07. **Quarantined**, source inconsistency confirmed, cause unknown. |

The same `US2220702037` ISIN also exists as a separate supplementary US-equity
series. Its 2025-06-04 bar is a valid 4.99 / 5.05 / 4.96 / 4.98 with volume
5,365,300, so that separate series remains approved. This is not a repair or a
merge: the two source series remain independently traceable.

| ABC series | Source label available in current reference workbook | Evidence by 2026-04-01 | Status / interpretation |
| --- | --- | --- | --- |
| `ABC003500476` | NYSE Declining Stocks (`NSHD`) | 831 daily ranges above 50% of close; maximum range/close 11.71; 512 close moves at least 30%. Raw opening record has OHLC 17 / 2855 / 17 / 2694 and zero volume. | `review`; extreme OHLC magnitudes and moves are present verbatim in the raw archive. Label suggests market breadth counts rather than a conventional price index, but that interpretation is not proven. No parsing defect confirmed. |
| `ABC003500477` | NYSE Advancing Stocks (`NSHU`) | 815 daily ranges above 50%; maximum range/close 259.86; 491 close moves at least 30%. Raw opening record has OHLC 2 / 574 / 2 / 549 and zero volume. | `review`; ratio detector also finds possible scale changes. Raw values match the source. Breadth-series semantics are plausible, but these OHLC levels are not approved as price data. |
| `ABC003500468` | DJIA Volatility (`VXD`) | 504 daily ranges above 50%; maximum range/close 2.04; 25 close moves at least 30%. | `review`; volatility index values can move heavily. Source semantics explain volatility but do not establish that its extreme OHLC observations are erroneous. No parsing defect confirmed. |

The current label workbook was downloaded after the snapshot's as-of date, so
labels above are post-hoc diagnostic context only. Automated snapshot statuses
use OHLC/close/volume observations bounded by the as-of cutoff, not the future
labels. For all seven priority entries, no corporate action or scale correction
was applied. The three index-series findings are not proven source errors; they
are excluded by their review status.

## Snapshot impact

| Measure | Raw / reconstructed | Research-cleared | Difference |
| --- | ---: | ---: | ---: |
| Entities | 2,194 | 1,757 | -437 (-19.92%) |
| Feature IDs per entity | 1,048 | 1,048 | 0 |
| Feature cells | 2,299,312 | 1,841,336 | -457,976 |
| Available cells | 2,208,926 (96.069%) | 1,762,215 (95.703%) | -446,711 |
| Unavailable cells | 90,386 | 79,121 | -11,265 |
| Extreme feature IDs flagged by snapshot audit | 348 | 11 | -337 |
| High-correlation pairs (absolute r ≥ 0.95) | 21 | 21 | count unchanged |

The extreme-feature count is a screening statistic, not an objective to
minimize. Of the raw 348 flags, 341 no longer trigger the snapshot's extreme
threshold after excluded entities are removed; 7 remain, and 4 other features
cross the threshold in the smaller sample. Ten of the 21 raw correlation pairs
drop out and ten pairs enter; 11 are shared. Correlation membership is
sample-dependent, and no feature is selected or removed.

The cell availability rate decreases by 0.366 percentage points because the
removed series tend to have longer, more complete histories. Feature IDs and
formulas are unchanged. Raw/bronze/silver data and the raw/reconstructed golden
snapshot are unchanged in meaning and remain rebuildable with `--quality-scope
all`.

Examples of distribution changes from exclusion alone:

| Feature | Raw min / p50 / p99 / max | Approved min / p50 / p99 / max |
| --- | --- | --- |
| `open.level.var_rel.w30.v1` | ~0 / 0.00237 / 0.06228 / 893,111.79 | ~0 / 0.00194 / 0.03109 / 0.15029 |
| `close.level.max_delta.w3.v1` | 0 / 0 / 9.85880 / 246.23 | 0 / 0 / 6.45598 / 19.88 |
| `close.level.max_delta.w60.v1` | 0 / 15.63515 / 142.65129 / 214,025 | 0 / 13.76527 / 87.14465 / 194.70 |

## Readiness and limits

**GO for SPEC-004 only on the 1,757-series research-cleared universe**, with
`--quality-scope approved` explicit in every build. The four confirmed OHLC
inconsistencies are quarantined and the three prioritized index series remain
excluded for review; their source semantics are not fully resolved. The other
430 review series also remain out until reviewed or the screening policy is
revised with evidence.

This GO does not upgrade the OHLCV history to strict point-in-time data. The
2026-04-01 slice is still graded `reconstructed`: the source was retrieved in
September 2026, historical revisions and adjusted-price corporate-action
vintages are missing, and current universe membership is unavailable. A future
target/model study must preserve that limitation and use the approved scope.

## Artifacts and verification

- `data/features/2026-04-01/market_quality_audit.json` and `.md`: all 2,194
  per-series decisions, evidence, rule version/fingerprint and family counts.
- `data/features/2026-04-01/`: raw/reconstructed feature Parquet, DuckDB and
  feature audit.
- `data/features/2026-04-01/research-cleared/`: approved-only Parquet, DuckDB,
  feature audit and its matching quality audit. These generated data files are
  ignored by Git.

The synthetic tests cover normal, impossible OHLC, large moves, scale breaks,
deterministic replay, source immutability, as-of evidence, both snapshot scopes,
rule fingerprint persistence and invalid scope rejection.
