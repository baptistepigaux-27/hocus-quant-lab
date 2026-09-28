# SPEC-002B — Quant Lab market-data ingestion

## Scope and state

Quant Lab consumes the provider-neutral Gremlin `market-data/1.0` manifest. It
verifies each content-addressed raw blob and capture checksum before copying it
to `data/raw/market/`; it persists the input rows to bronze Parquet, validated
rows to silver Parquet, and time-valid instrument mappings and corporate
actions to their own silver datasets. DuckDB exposes `market_daily`,
`instruments`, and `corporate_actions`, with history views retained underneath
for correction-aware queries.

The checked-in market snapshot is a tiny **synthetic offline fixture**. It is
not a provider response and gives no evidence of French market coverage. No API
credential was available, and no provider was selected or queried with a key.

## Point-in-time convention

V0 makes raw OHLCV for session D available at midnight at the start of D+1 in
`Europe/Paris`. A query requires a timezone-aware `as_of` timestamp and filters
bars by `available_at`. When multiple captures exist, it selects the latest
version retrieved by the cutoff. If the dataset is first imported after a
historical cutoff and has no earlier capture, it uses that first imported
version only after the D+1 availability boundary; a subsequent correction
captured later cannot rewrite an earlier as-of result.

This supports an initial historical import, but it cannot prove what the
provider originally published at each past date unless the provider supplies
versioned historical snapshots. Raw values and capture provenance are retained
so subsequent changes remain visible. Provider-adjusted close is returned only
when the snapshot explicitly marks it point-in-time safe and its own
`adjusted_close_available_at` is not later than the cutoff; otherwise it is
null. The provider adjustment basis is preserved without reconstructing a
series in Quant Lab.

`query_market_amf_as_of` joins each bar to the latest AMF observation that was
available by the bar's availability time and avoids multiplying rows when an
issuer has multiple holders.

## Audit outputs

Each ingestion writes a per-snapshot audit JSON, `unresolved_instruments.json`,
`suspicious_observations.json`, and `provider_coverage.json`. They report
requested/resolved/ambiguous/not-found/invalid mappings, row date range,
coverage per instrument/year, missing OHLCV fields, duplicate sessions,
quality issues, currency/MIC distributions, corporate actions and unresolved
mappings. Cross-capture corrections remain visible in versioned Parquet rows
and as-of queries; the report does not yet compute a correction count. A
temporal gap is not called a missing
session without an explicit exchange calendar; weekend/holiday gaps are not
failures by themselves.

Run locally with `ingest_market_snapshot(snapshot_path,
gremlin_artifact_root=..., data_dir=...)`; production `data/` remains outside
Git. The API and correction/as-of behavior are covered by offline tests.
