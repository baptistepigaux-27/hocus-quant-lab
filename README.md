# hocus-quant-lab

Reproducible research sandbox for point-in-time scoring experiments. Data ingestion and exploration are underway; there is not yet an end-to-end predictive experiment (features, target, model and backtest).

## Current state (2026-09-30)

- **AMF short positions:** Gremlin acquisition and the Quant Lab offline adapter are implemented; see [AMF rules](docs/AMF_SHORT_POSITIONS.md).
- **Market prices:** real ABC Bourse files supplied manually have been imported. The full SRD archive has 199,416 observations across 197 provider identifiers; eight additional universes have 1,745,030 observations. Coverage is 2022-09-29 to 2026-09-28. These files are local and ignored by Git.
- **Instrument reference:** the companion workbook has been ingested: 2,135 codes, including 2,067 with labels and 68 unresolved. Labels are a current snapshot, not historical point-in-time names.
- **Cross-sectional measurements:** SPEC-003 v1 is implemented with an additive RSI `v2` contract. The local 2026-04-01 slice has 2,194 entities × 1,048 features (2,299,312 cells; about 96.1% available). Its long/wide Parquet and audit files are local under `data/features/2026-04-01/` and are ignored by Git. The ABC history is reconstructed PIT; SPEC-004 evaluates quality at each historical cutoff and preserves that PIT grade.
- **Historical feature cube:** SPEC-004 adds sparse, weekly and daily grids over the frozen SPEC-003 engine. Its research scope is `approved`; this does not make the source strict observed-PIT or turn the delivered SRD sample into a historical SBF 120 universe. See [the cube guide](docs/SPEC_004_HISTORICAL_FEATURE_CUBE.md).
- **Research still to build:** construct a historically valid universe, then define targets and walk-forward evaluation. Do not describe the SRD sample as a historical SBF 120 universe.

ABC Bourse ingestion is manual and intended for this personal sandbox. The 2026-04-01 historical slice uses the source contract's session-date + one day `available_at` rule even though the archive was retrieved in September 2026; the audit reports this backfill. Historical vintages and split/corporate-action adjustment history are unverified, so this is not proof of fully versioned point-in-time prices and is not cleared for split-sensitive backtests. See [the feature formulas and caveats](docs/FEATURES.md) and [the ABC Bourse delivery note](docs/ABC_BOURSE_DELIVERY.md).

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

Gremlin acquires source snapshots and records provenance. Quant Lab consumes those snapshots without fetching external data, stores the source payload unchanged under `data/raw/`, writes parsed records to Parquet bronze, then normalizes them into silver. Silver observations retain `observation_date`, `published_at`, `retrieved_at`, and `valid_from`; `available_at` follows the source-specific availability contract. For AMF it uses publication/retrieval rules; for ABC daily bars it is modeled as session date + 1 day. The ABC archive was retrieved after the historical cutoff and has no dated source vintages, so this session-date rule is an explicit backfill assumption rather than proof of historically captured values.

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

## SPEC-003 feature snapshot

Build the local cross-sectional feature slice from the imported research DuckDB:

```sh
uv run python -m hocus_quant.cli build-feature-snapshot \
  --as-of 2026-04-01 \
  --output data/features/2026-04-01
```

The long-form Parquet is canonical; a wide Parquet and local DuckDB catalog are
derived conveniences. `--dry-run` computes and prints the audit without
writing snapshot files. Formula IDs, definitions, normalization and the
historical availability assumption are documented in [FEATURES.md](docs/FEATURES.md).

## SPEC-004 historical feature cube

Build point-in-time SPEC-003 snapshots over an explicit or generated grid:

```sh
uv run python -m hocus_quant.cli build-feature-cube \
  --start 2022-09-29 --end 2026-09-28 --cadence weekly \
  --quality-scope approved --output data/feature_cube/weekly
```

Use `--dry-run` to inspect the resolved cutoffs, `--resume` to reuse valid
partitions, and `--force` to rebuild them. The output is partitioned long-form
Parquet with a DuckDB catalog and temporal audit. For a filtered wide research
panel, run `export-feature-panel`; to refresh/check coverage and historical
quality transitions, run `audit-feature-cube`. The grid convention,
reconstructed-PIT limitation, contract fingerprints, and performance notes are
in [the SPEC-004 guide](docs/SPEC_004_HISTORICAL_FEATURE_CUBE.md).

## SPEC-005 future targets

Build future outcome labels separately from features for one cutoff or every
cutoff in an existing feature cube:

```sh
uv run python -m hocus_quant.cli build-target-snapshot \
  --as-of 2026-04-01 --quality-scope approved \
  --output data/targets/as_of_date=2026-04-01

uv run python -m hocus_quant.cli build-target-set \
  --feature-cube data/feature_cube/weekly \
  --output data/targets/weekly --resume
```

SPEC-005 V1 emits nine target families for 5/10/20/60/120 future observed
sessions. It builds continuous absolute and mapped broad-market relative returns,
their direction labels, future volatility/drawdown/extrema, and same-family
percentile ranks. It uses daily prices for labels even when feature cutoffs are
weekly. Future quality events make labels unavailable and retain a separate
candidate value for review. The output is reconstructed PIT and is not a
predictive model or backtest. See the [target contract](docs/SPEC_005_TARGET_FACTORY.md).

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

### SPEC-006 — Univariate Signal Atlas

The first research pass compares each approved feature with research-ready
future targets at the same entity and cutoff. Build the weekly feature cube,
matching targets, then the signal analysis:

```sh
uv run python -m hocus_quant.cli build-feature-cube \
  --start 2024-04-05 --end 2026-04-03 --cadence weekly \
  --quality-scope approved --output data/feature_cube/spec006-weekly-demo --resume

uv run python -m hocus_quant.cli build-target-set \
  --feature-cube data/feature_cube/spec006-weekly-demo \
  --output data/targets/spec006-weekly-demo --resume

uv run python -m hocus_quant.cli analyze-signals \
  --feature-cube data/feature_cube/spec006-weekly-demo \
  --target-set data/targets/spec006-weekly-demo \
  --output data/analysis/spec006-weekly-demo
```

The analysis is incremental and resumes complete cutoff partitions. It writes
Parquet and read-only DuckDB research views for summary metrics, date-local
deciles, IC history, annual stability, family slices and mechanically filtered
research candidates. The marimo explorer adds the Signal Atlas and detail view;
set `HOCUS_QUANT_SIGNALS_DB` to choose another analysis database. Methodology,
thresholds and limitations are documented in
[`docs/SPEC_006_SIGNAL_ANALYSIS.md`](docs/SPEC_006_SIGNAL_ANALYSIS.md). The
coverage and first real run statistics are in
[`docs/SPEC_006_DATA_REPORT.md`](docs/SPEC_006_DATA_REPORT.md).

### SPEC-006R — Period Stability & Validation Atlas

Freeze two discovery cohorts (all targets and return/direction only) on the
configured discovery period, then evaluate those exact relations over separate
validation windows. No validation-period rows participate in selection. Build
or replay the local Parquet atlas with:

```sh
uv run python -m hocus_quant.cli build-stability-atlas \
  --config configs/experiments/stability_atlas.toml \
  --output data/analysis/spec006r-stability-atlas-top500
```

The outputs include frozen selections, signal × period and signal × period ×
family tables, cutoff-level IC and decile histories, and a coverage/maturity
audit. In the current sandbox, the Stability Atlas separates risk-oriented
signals from return/direction signals and shows discovery/validation detail.
The 2026 validation window is incomplete; horizon maturity and missing ICs
remain visible in the tables. This is descriptive univariate analysis, not
alpha validation or a strategy. Periods, target families, ranking contract and
classification thresholds are configurable in the TOML file; see the
[SPEC-006R methodology and current report](docs/SPEC_006R_PERIOD_STABILITY.md).

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
read-only mode. Staging and sandbox run as separate systemd services and use
separate Nginx upstreams so a sandbox release does not replace the staging UI.
Each service runs as the dedicated non-login
`hocus-quant-lab` account; within `/home/ubuntu`, it sees only this project's
virtualenv, data and notebooks, mounted read-only. The service split and
maintenance commands are in [the hosted deployment note](docs/SANDBOX_DEPLOYMENT.md).

## Scope

The intended equity research scope is Euronext Paris, eventually with a historically correct point-in-time universe. **No SBF 120 membership history is currently ingested.** AMF and ABC Bourse SRD price data are available through the workflows above; selected INSEE and Banque de France series remain planned. Quant Lab does not scrape financial sites or acquire ABC Bourse files automatically.
