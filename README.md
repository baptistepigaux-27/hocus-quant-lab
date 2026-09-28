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

## Scope

Initial universe: Euronext Paris / SBF 120. Planned source order: AMF public short positions, selected INSEE series, Banque de France series, then a separately evaluated Euronext OHLCV source. AMF acquisition itself is done in Gremlin after this fixture pipeline and its leakage checks are validated.
