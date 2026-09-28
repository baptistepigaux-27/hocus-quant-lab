# Gremlin snapshot contract

Gremlin receives a source definition and emits a raw snapshot. Its generic envelope contains `source_id`, `retrieved_at`, `source_url`, `content_type`, `checksum`, `payload`, and `metadata`. Quant Lab verifies the payload checksum and stores the exact payload bytes before parsing records. Ingestion is idempotent by checksum and safe to replay.

The AMF connector is responsible for retrieving and parsing the official public source. Its canonical snapshot contains the raw CSV payload plus parsed records with `publication_date`, `position_date`, `holder`, `issuer`, `isin`, and `net_short_position_pct`; source URL, retrieval time, checksum, capture ID and parser/header signature remain attached as provenance. Quant Lab verifies the raw payload checksum and each record's temporal and identifier constraints, then retains the original source fields in bronze.

No HTTP client, source URL discovery, scraping, or AMF business interpretation is implemented here.
