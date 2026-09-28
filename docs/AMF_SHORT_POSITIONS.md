# AMF net short positions — SPEC-001

## Source and contract

Gremlin reads the AMF-produced consolidated history through the stable data.gouv.fr resource URL:

`https://www.data.gouv.fr/datasets/r/c2539d1c-8531-4937-9cba-3bd8e9786cc5`

The response redirects to a date-stamped AMF CSV on data.gouv.fr's official object service. Gremlin stores the response as a SHA-256 content-addressed artifact, records a separate capture event per retrieval, and emits a canonical snapshot containing exact UTF-8 payload bytes and parsed rows. Quant Lab has no network access in this flow.

The adapter keeps the raw source fields and maps issuer, ISIN, holder, position start, publication start/end, ratio, retrieval time, publication availability fence, and source provenance into bronze/silver. `Ratio` is already in percentage points (`0.35` is 0.35%); it is not multiplied by 100. Non-empty ISINs failing the ISO 6166 check digit are marked invalid, excluded from canonical `isin`, preserved in `source_fields`, and counted in the audit.

AMF publishes only a date, not a timestamp. `published_at` stays null. `available_at` is 00:00 UTC on the day following `publication_date`, or `retrieved_at` when that date is unavailable. `position_date` is never used as availability.

## Import and query

```sh
uv run python -m hocus_quant.cli ingest-amf /path/to/amf-snapshot.json
```

The result is in `data/raw/amf/`, `data/bronze/amf_short_positions/`, and `data/silver/amf_short_positions/`. DuckDB exposes the `amf_short_positions` view:

```sql
SELECT *
FROM amf_short_positions
WHERE available_at <= TIMESTAMPTZ '2026-09-26 10:00:00+00';
```

Each import writes a JSON audit beside its silver Parquet. It reports date coverage, entity counts, missing/invalid identifiers, duplicates, calendar gaps, ratio quantiles, and the observed source-header signature. Calendar gap counts include weekends and holidays.

## First acquired dataset

Captured on 2026-09-28 at 12:21:46 UTC; raw checksum `sha256:c268b91e29e7d1bb424569134d0c7832287a2313d5c16f8ba9663809b39f7640`.

| Measure | Value |
| --- | ---: |
| Rows | 40,819 |
| Position date range | 2012-10-17 – 2026-09-24 |
| Publication date range | 2012-11-02 – 2026-09-25 |
| Unique valid ISINs | 271 |
| Unique issuers | 246 |
| Unique holders | 380 |
| Missing ISIN | 0 (0.00%) |
| Invalid ISIN check digits | 7 rows; all raw values retained and flagged |
| Missing ratio | 0 (0.00%) |
| Exact duplicate rows | 0 |
| Publication calendar days without rows | 1,292, including weekends and holidays |
| Ratio percentiles (min / p25 / median / p75 / max) | 0.00 / 0.56 / 0.75 / 1.13 / 89.17 |

The seven invalid check digits refer to source value `FR001400D512` for `VERGNET SA`; the source rows remain available but the identifier is not used as canonical ISIN. This is a source-data quality exception, not a parse failure. The current export exposes one header signature. Because it is a consolidated current file rather than an archive of prior file versions, historical header changes cannot be inferred from this capture; new captures retain their signatures for prospective detection.
