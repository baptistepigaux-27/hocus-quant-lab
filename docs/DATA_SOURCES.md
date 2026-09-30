# Data sources

The initial research universe is Euronext Paris / SBF 120. Source acquisition is performed by Gremlin and reviewed independently from this repository.

| Planned connector | Initial scope | Quant Lab role |
| --- | --- | --- |
| GREMLIN-FIN-001 AMF | Public net short positions and history | Normalize publication, position, holder, issuer, ISIN, and percentage |
| GREMLIN-FIN-002 INSEE | Inflation, industrial production, business climate, consumer confidence, unemployment | Preserve original series codes and publication/revision history |
| GREMLIN-FIN-003 Banque de France | OAT/yields, yield curve, credit conditions, corporate rates, credit aggregates | Normalize observations while retaining vintages and release times |
| GREMLIN-FIN-004 Euronext prices | ABC Bourse manually downloaded SRD history (current pilot) | Import local files through Gremlin; no automatic site access; adjustment history still needs PIT review |

V0 fixture ingestion itself does not contact external sources. SPEC-001 adds a source-specific Gremlin acquisition/parser and a Quant Lab offline adapter for AMF; the Quant Lab adapter never performs network requests.

ABC Bourse's export contains ISIN, date, OHLC and share volume. The current
input is an SRD-listing sample, not a complete or survivorship-free SBF 120
universe. ABC Bourse's page states that history is readjusted when nominal
divisions occur; the supplied history has no matching corporate-action stream,
so split-sensitive point-in-time use remains gated on a separate audit.

The 2026-09-29 manual delivery also included crypto, FX/rates, market and sector
indices, commodities, bonds, German equities, US equities, and a full SRD ZIP.
The eight supplemental universes contain 1,745,030 rows from 2022-09-29 through
2026-09-28. Non-ISIN source codes remain source identifiers; the parser does not
infer MIC, currency, or an ISIN from the archive's display category. The FX
inventory has 3,984 repeated series/date rows with identical values; DuckDB's
latest-observation view collapses identical keys. The bond inventory omits two
zero-row monthly files, both called out in the audit. The partial SRD delivery
duplicates its overlapping monthly files and is preserved only as raw; full
SRD is ingested through Gremlin with 199,416 rows and 197 ISINs.

`Libelles_codes_perimetre_2022-2026.xlsx` is the companion ABC Bourse reference
workbook (download source recorded in the workbook as
`https://www.abcbourse.com/download/libelles`). It has 2,135 distinct codes:
2,067 codes with current labels and 68 without; 55 codes have multiple name or
ticker variants. All 2,122 labeled rows and all 68 unresolved codes are
preserved. These labels are current reference metadata, not point-in-time
historical names: use the original identifier for joins, and do not treat a
current ticker or issuer name as valid throughout 2022–2026 without a dated
reference history.
