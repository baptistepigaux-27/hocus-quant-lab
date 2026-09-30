# hocus-quant-lab

Reproducible research sandbox for point-in-time scoring experiments on Euronext Paris / SBF 120 equities. V0 establishes data contracts and validation; it does not include a predictive model or a financial scraper.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run mypy src/
```

Copy `.env.example` to `.env` if you want to override local paths. `data/` and MLflow run artifacts are local and ignored by Git.

## Data flow

Gremlin acquires source snapshots and records provenance. Quant Lab consumes those snapshots without fetching external data, stores the source payload unchanged under `data/raw/`, writes parsed records to Parquet bronze, then normalizes them into silver. Silver observations retain `observation_date`, `published_at`, `retrieved_at`, and `valid_from`; `available_at` is the conservative point-in-time boundary used by queries. It is derived as the latest of publication and retrieval timestamps, so data cannot be used before it was actually retrieved. Source-specific semantics and correction policies belong in a later, explicit normalizer.

```text
source → Gremlin snapshot → immutable raw → bronze Parquet → silver Parquet
                                                        → DuckDB research
```

See [architecture](docs/ARCHITECTURE.md), [data sources](docs/DATA_SOURCES.md), [point-in-time rules](docs/POINT_IN_TIME.md), and [Gremlin contract](docs/GREMLIN.md).

## Local fixture walkthrough

```sh
uv run python -m hocus_quant.cli ingest-fixture fixtures/gremlin/amf_snapshot.json
```

The command writes the original fixture payload to raw, its records to bronze and silver Parquet, and creates/updates a DuckDB `observations` view over silver. Replaying the same capture is idempotent. Raw objects are content-addressed by SHA-256 and never overwritten; each distinct capture keeps its own provenance manifest, including when the payload checksum is unchanged.

## AMF short positions

Gremlin acquires and parses the official AMF consolidated file; Quant Lab consumes the saved snapshot offline:

```sh
uv run python -m hocus_quant.cli ingest-amf /path/to/amf-snapshot.json
```

The adapter writes `data/raw/amf/`, `data/bronze/amf_short_positions/`, and `data/silver/amf_short_positions/`, creates the DuckDB view `amf_short_positions`, and writes a JSON audit beside silver. See [AMF field and point-in-time rules](docs/AMF_SHORT_POSITIONS.md). Source payloads and database files remain ignored by Git.

## Manual OHLCV delivery

ABC Bourse files are downloaded manually and then imported locally; neither
repository signs in to the site or automates downloads. Place all delivered
semicolon-delimited `.txt` files in the input folder. Run from `hocus-gremlin`:

```sh
PYTHONPATH=src python3 -m gremlin.cli market-data import-abc-bourse \
  --input-dir /path/to/extracted/SRD \
  --artifact-root ./var/market-data/abc-bourse/raw \
  --output ./var/market-data/abc-bourse/market-data.json
```

Then run from `hocus-quant-lab`:

```sh
uv run python -m hocus_quant.cli ingest-market \
  /path/to/hocus-gremlin/var/market-data/abc-bourse/market-data.json \
  --gremlin-artifact-root /path/to/hocus-gremlin/var/market-data/abc-bourse/raw
```

This writes content-addressed raw files, bronze/silver Parquet, the
`market_daily` and `market_daily_history` DuckDB views, and the data audit.
Adding later deliveries to the input folder and rerunning both commands
refreshes the snapshot. Current ABC Bourse OHLC values are retained as supplied;
the point-in-time safety of its historical split adjustments remains
unverified, so this dataset is not yet cleared for split-sensitive backtests.

### Other delivered ABC Bourse universes

Additional ZIPs can be imported in one offline pass:

```sh
uv run python -m hocus_quant.cli ingest-market-archives "$QUANT_INPUT_DIR"
```

The importer stores each original ZIP once by SHA-256 under
`data/raw/market_archives/`, records every capture separately, validates the
included inventory, and writes universe-partitioned bronze/silver Parquet plus
`market_series_history` and the latest-revision `market_series` DuckDB view.
The supplementary `series` schema keeps the provider identifier when it is not
a valid ISIN; MIC and currency are left null because the delivered files do not
establish them consistently. The full SRD ZIP is routed through the Gremlin
snapshot adapter above; its partial ZIP is retained as raw provenance and not
loaded a second time. See `data/silver/market_series/archive_audit.json` for
the import audit. These manually supplied series remain subject to the same
corporate-action and point-in-time limitations as the SRD data.

### ABC Bourse labels and tickers

Import the accompanying reference workbook separately:

```sh
uv run python -m hocus_quant.cli ingest-instrument-labels \
  "$QUANT_INPUT_DIR/Libelles_codes_perimetre_2022-2026.xlsx"
```

The workbook is preserved as immutable raw with a checksum and capture record.
Its ABC name/ticker variants are retained in
`data/silver/instrument_labels/`; the `instrument_labels_by_code` DuckDB view
groups variants without selecting one as canonical. Use
`market_series_with_labels` and `market_daily_with_labels` for enriched views.
The marimo explorer shows the labels and tickers while keeping the original
provider identifier visible. Codes with no current label remain explicitly
unresolved. The workbook uses the source column heading `ISIN` even for ABC's
synthetic `ABC…` identifiers; Quant Lab stores those as provider identifiers,
not as real ISINs.

See [the full delivery note](docs/ABC_BOURSE_DELIVERY.md) for coverage,
replay commands, audit paths, metadata variants and point-in-time limits.

## Interactive local explorer

Install the notebook extra and open the marimo explorer:

```sh
uv sync --extra notebook
uv run --extra notebook marimo edit notebooks/explorateur.py
```

It reads `data/research.duckdb` in read-only mode and lets you inspect SRD
OHLCV, the supplementary ABC Bourse universes, or AMF positions by identifier
and `as_of` date. To use another local database, set
`HOCUS_QUANT_DB`. The editor binds to localhost by default; keep it local because
the manual OHLCV files are for personal use. The hosted sandbox route below
remains behind the sandbox's existing authentication.

The hosted explorer is available at
[`staging.hocus.works/quant-lab/`](https://staging.hocus.works/quant-lab/) and
[`sandbox.hocus.works/quant-lab/`](https://sandbox.hocus.works/quant-lab/). Both
use the host's existing authentication and read the same local database in
read-only mode. The systemd service runs as the dedicated non-login
`hocus-quant-lab` account; within `/home/ubuntu`, it sees only this project's
virtualenv, data and notebooks, mounted read-only.

## Scope

Initial universe: Euronext Paris / SBF 120. Planned source order: AMF public short positions, selected INSEE series, Banque de France series, then a separately evaluated Euronext OHLCV source. AMF acquisition itself is done in Gremlin after this fixture pipeline and its leakage checks are validated.
