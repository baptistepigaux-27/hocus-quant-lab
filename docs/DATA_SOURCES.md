# Data sources

The initial research universe is Euronext Paris / SBF 120. Source acquisition is performed by Gremlin and reviewed independently from this repository.

| Planned connector | Initial scope | Quant Lab role |
| --- | --- | --- |
| GREMLIN-FIN-001 AMF | Public net short positions and history | Normalize publication, position, holder, issuer, ISIN, and percentage |
| GREMLIN-FIN-002 INSEE | Inflation, industrial production, business climate, consumer confidence, unemployment | Preserve original series codes and publication/revision history |
| GREMLIN-FIN-003 Banque de France | OAT/yields, yield curve, credit conditions, corporate rates, credit aggregates | Normalize observations while retaining vintages and release times |
| GREMLIN-FIN-004 Euronext prices | Historical OHLCV source to be assessed separately | Consume an approved source; no fragile or legally ambiguous third-party scrape |

V0 fixture ingestion itself does not contact external sources. SPEC-001 adds a source-specific Gremlin acquisition/parser and a Quant Lab offline adapter for AMF; the Quant Lab adapter never performs network requests.
