# Point-in-time data rules

## Availability timestamps

Every source record keeps the following concepts separate:

- `observation_date`: the date or period described by the source;
- `published_at`: when the source actually published the value, if known;
- `retrieved_at`: when Gremlin or an operator captured that version;
- `valid_from`: when the source says the value/version became valid, if known;
- `available_at`: the earliest defensible instant this stored version may be used.

The generic rule is **source-aware**. When an actual publication timestamp is
known, availability cannot precede publication or capture of that version. If
publication time is unavailable, capture time is the lower bound unless a
source-specific contract provides an explicitly documented historical
availability convention. A source-specific convention does not prove vintage
integrity. Revisions remain separate versions; `valid_from` is not a substitute
for publication or capture time.

## PIT evidence grades

Each run or dataset carries one of these stable grades:

- `strict`: the value/version was captured or verifiably published no later
  than the decision cutoff, with revision/vintage lineage sufficient to show
  which value was then knowable;
- `reconstructed`: historical availability is inferred from a documented
  source convention, while the exact historical vintage is not proven;
- `unknown`: neither strict evidence nor a sufficiently defensible historical
  availability convention is available.

Grades describe evidence, not data quality or economic usefulness. A snapshot
combining sources must retain a grade per source; its overall grade cannot be
stronger than its weakest included source. Do not call a reconstructed snapshot
strict PIT.

## AMF short positions

The consolidated AMF file provides a publication **date**, not an intraday
publication timestamp. Quant Lab preserves that date, leaves `published_at`
unknown, and makes a row available from 00:00 UTC on the following calendar
day (`publication_date + 1 day`). If publication date is missing, `retrieved_at`
is required. `position_date` never determines availability. This is a
conservative publication-date convention; source revisions and historical file
vintages must remain separately captured to support strict PIT claims.

## ABC Bourse market history

The manually supplied ABC Bourse archive was retrieved in September 2026. The
current ingestion contract models a session as available at 00:00 Europe/Paris
on the following calendar date. The archive contains no historical download
vintages or revision timestamps. For the 2026-04-01 snapshot, the bars dated
through that session are therefore **backfilled data**, not bars retrieved in
April 2026. Their grade is `reconstructed`, not `strict`.

This convention lets the research code build a historically ordered feature
slice, but cannot prove that values in the September archive equal the values
known on each past date. Corporate-action and adjusted-price history are also
not verified; adjusted closes are excluded. Runs report late-retrieved rows and
carry `pit_grade`, per-source grades, and the registry fingerprint in run
metadata. No timing inference is made from `session_date` alone.

## Query rule

All as-of reads filter `available_at <= as_of`. For a strict PIT study, also
require strict source grade and vintage evidence appropriate to the source.
Tests must demonstrate that an old observation captured after the cutoff is
not presented as strict PIT merely because its observation date is old.
