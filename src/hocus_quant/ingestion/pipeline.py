"""Replayable Gremlin snapshot ingestion into raw, bronze, silver, and DuckDB."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from hocus_quant.schemas.observation import ObservationSchema, normalize_record
from hocus_quant.schemas.snapshot import GremlinSnapshot


def ingest_snapshot(snapshot_path: Path, data_dir: Path) -> dict[str, Path]:
    """Validate and ingest a snapshot without contacting the source."""
    raw_json = snapshot_path.read_text(encoding="utf-8")
    raw_data = json.loads(raw_json)
    snapshot = GremlinSnapshot.model_validate(raw_data)
    provenance = {key: value for key, value in raw_data.items() if key != "payload"}
    canonical_provenance = json.dumps(
        provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    snapshot_id = hashlib.sha256(canonical_provenance.encode("utf-8")).hexdigest()
    payload_document = json.loads(snapshot.payload)
    records = snapshot.records or (
        payload_document.get("records") if isinstance(payload_document, dict) else None
    )
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("fixture payload must be a JSON object containing a records array")
    source_dir = data_dir / "raw" / snapshot.source_id
    raw_dir = source_dir / snapshot.checksum.split(":", maxsplit=1)[1]
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "payload"
    if raw_path.exists() and raw_path.read_text(encoding="utf-8") != snapshot.payload:
        raise ValueError("content-addressed raw object exists with different bytes")
    raw_path.write_text(snapshot.payload, encoding="utf-8")
    snapshot_dir = source_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = snapshot_dir / f"{snapshot_id}.json"
    metadata_json = json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not metadata_path.exists():
        metadata_path.write_text(metadata_json, encoding="utf-8")
    elif metadata_path.read_text(encoding="utf-8") != metadata_json:
        raise ValueError("snapshot identifier exists with different provenance")

    bronze_rows = [
        {
            **record,
            "source_id": snapshot.source_id,
            "source_checksum": snapshot.checksum,
            "snapshot_id": snapshot_id,
            "source_url": snapshot.source_url,
            "retrieved_at": snapshot.retrieved_at,
        }
        for record in records
    ]
    bronze = pl.DataFrame(bronze_rows, infer_schema_length=None)
    bronze_dir = data_dir / "bronze" / f"source_id={snapshot.source_id}"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_dir / f"{snapshot_id}.parquet"
    if not bronze_path.exists():
        bronze.write_parquet(bronze_path)

    silver_rows = [
        normalize_record(
            source_id=snapshot.source_id,
            source_checksum=snapshot.checksum,
            snapshot_id=snapshot_id,
            source_url=snapshot.source_url,
            retrieved_at=snapshot.retrieved_at,
            record=record,
        )
        for record in records
    ]
    silver = pl.DataFrame(silver_rows, infer_schema_length=None)
    for column, dtype in (
        ("observation_date", pl.Date),
        ("published_at", pl.Datetime(time_zone="UTC")),
        ("retrieved_at", pl.Datetime(time_zone="UTC")),
        ("valid_from", pl.Datetime(time_zone="UTC")),
        ("available_at", pl.Datetime(time_zone="UTC")),
    ):
        silver = silver.with_columns(pl.col(column).cast(dtype))
    silver = ObservationSchema.validate(silver)
    silver_dir = data_dir / "silver" / f"source_id={snapshot.source_id}"
    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_path = silver_dir / f"{snapshot_id}.parquet"
    if not silver_path.exists():
        silver.write_parquet(silver_path)

    db_path = data_dir / "research.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as connection:
        pattern = (data_dir / "silver" / "**" / "*.parquet").as_posix()
        escaped_pattern = pattern.replace("'", "''")
        connection.execute(
            "CREATE OR REPLACE VIEW observations AS "
            f"SELECT * FROM read_parquet('{escaped_pattern}', union_by_name=true)"
        )
    return {
        "raw": raw_path,
        "bronze": bronze_path,
        "silver": silver_path,
        "duckdb": db_path,
    }


def query_as_of(db_path: Path, as_of: datetime) -> list[dict[str, Any]]:
    """Return observations available no later than the timezone-aware cutoff."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    with duckdb.connect(str(db_path), read_only=True) as connection:
        cursor = connection.execute(
            "SELECT * FROM observations WHERE available_at <= ? ORDER BY available_at",
            [as_of],
        )
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
