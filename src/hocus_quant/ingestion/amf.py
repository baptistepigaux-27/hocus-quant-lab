"""AMF snapshot adapter from Gremlin's parsed snapshot into Parquet and DuckDB."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandera.polars as pa
import polars as pl

from hocus_quant.schemas.snapshot import GremlinSnapshot

AMF_SOURCE_ID = "amf_net_short_positions"

AMFSilverSchema = pa.DataFrameSchema(
    {
        "observation_id": pa.Column(str, nullable=False, unique=True),
        "snapshot_id": pa.Column(str, nullable=False),
        "source_id": pa.Column(str, nullable=False),
        "source_checksum": pa.Column(str, nullable=False),
        "source_url": pa.Column(str, nullable=False),
        "issuer": pa.Column(str, nullable=True),
        "isin": pa.Column(str, nullable=True),
        "holder": pa.Column(str, nullable=True),
        "holder_lei": pa.Column(str, nullable=True),
        "position_date": pa.Column(pl.Date, nullable=True),
        "publication_date": pa.Column(pl.Date, nullable=True),
        "publication_end_date": pa.Column(pl.Date, nullable=True),
        "net_short_position_pct": pa.Column(float, nullable=True),
        "published_at": pa.Column(pl.Datetime("us", "UTC"), nullable=True),
        "retrieved_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "available_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "record": pa.Column(pl.Struct, nullable=False),
    },
    strict=True,
)


def ingest_amf_snapshot(snapshot_path: Path, data_dir: Path) -> dict[str, Path]:
    """Verify a Gremlin AMF snapshot and write raw, bronze, silver, DuckDB, audit."""
    raw_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot = GremlinSnapshot.model_validate(raw_snapshot)
    if (
        snapshot.source_id != AMF_SOURCE_ID
        or snapshot.schema_version != "amf-net-short-positions/1.0"
    ):
        raise ValueError("snapshot is not a supported Gremlin AMF short-position snapshot")
    if not snapshot.records:
        raise ValueError("AMF snapshot has no parsed records")
    payload = snapshot.payload.encode("utf-8")
    checksum = "sha256:" + hashlib.sha256(payload).hexdigest()
    if checksum != snapshot.checksum:
        raise ValueError("Gremlin snapshot raw payload checksum does not match")
    retrieved_at = _parse_datetime(snapshot.retrieved_at)
    provenance = {
        "source_id": snapshot.source_id,
        "source_url": snapshot.source_url,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "checksum": snapshot.checksum,
        "content_type": snapshot.content_type,
        "metadata": snapshot.metadata,
    }
    snapshot_id = hashlib.sha256(
        json.dumps(provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    raw_dir = data_dir / "raw" / "amf" / checksum.split(":", maxsplit=1)[1]
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "payload"
    if raw_path.exists() and raw_path.read_bytes() != payload:
        raise ValueError("content-addressed AMF raw payload already exists with different bytes")
    if not raw_path.exists():
        raw_path.write_bytes(payload)
    capture_dir = data_dir / "raw" / "amf" / "captures"
    capture_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = capture_dir / f"{snapshot_id}.json"
    manifest_json = json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != manifest_json:
        raise ValueError("AMF capture manifest ID collides with different provenance")
    if not manifest_path.exists():
        manifest_path.write_text(manifest_json, encoding="utf-8")

    bronze_rows = snapshot.records
    bronze_dir = data_dir / "bronze" / "amf_short_positions"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_dir / f"{snapshot_id}.parquet"
    if not bronze_path.exists():
        pl.DataFrame(bronze_rows, infer_schema_length=None).write_parquet(bronze_path)

    silver_rows: list[dict[str, Any]] = []
    for index, row in enumerate(snapshot.records):
        _validate_amf_record(row, retrieved_at, index)
        published_raw = row.get("published_at")
        published_at = _parse_datetime(published_raw) if published_raw else None
        available_at = _parse_datetime(row["available_at"])
        silver_rows.append(
            {
                "observation_id": f"{snapshot_id}:{index}",
                "snapshot_id": snapshot_id,
                "source_id": AMF_SOURCE_ID,
                "source_checksum": snapshot.checksum,
                "source_url": row["source_url"],
                "issuer": row.get("issuer"),
                "isin": row.get("isin"),
                "holder": row.get("holder"),
                "holder_lei": row.get("holder_lei"),
                "position_date": _parse_date(row.get("position_date")),
                "publication_date": _parse_date(row.get("publication_date")),
                "publication_end_date": _parse_date(row.get("publication_end_date")),
                "net_short_position_pct": row.get("net_short_position_pct"),
                "published_at": published_at,
                "retrieved_at": _parse_datetime(row["retrieved_at"]),
                "available_at": available_at,
                "record": row,
            }
        )
    silver = pl.DataFrame(silver_rows, infer_schema_length=None)
    for column, dtype in (
        ("position_date", pl.Date),
        ("publication_date", pl.Date),
        ("publication_end_date", pl.Date),
        ("published_at", pl.Datetime(time_zone="UTC")),
        ("retrieved_at", pl.Datetime(time_zone="UTC")),
        ("available_at", pl.Datetime(time_zone="UTC")),
    ):
        silver = silver.with_columns(pl.col(column).cast(dtype))
    silver = AMFSilverSchema.validate(silver)
    silver_dir = data_dir / "silver" / "amf_short_positions"
    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_path = silver_dir / f"{snapshot_id}.parquet"
    if not silver_path.exists():
        silver.write_parquet(silver_path)

    audit = audit_amf_records(snapshot.records, snapshot.metadata)
    audit_path = silver_dir / f"audit-{snapshot_id}.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    db_path = data_dir / "research.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_pattern = (silver_dir / "*.parquet").as_posix()
    escaped_pattern = parquet_pattern.replace("'", "''")
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            "CREATE OR REPLACE VIEW amf_short_positions AS "
            f"SELECT * FROM read_parquet('{escaped_pattern}', union_by_name=true)"
        )
    return {
        "raw": raw_path,
        "manifest": manifest_path,
        "bronze": bronze_path,
        "silver": silver_path,
        "audit": audit_path,
        "duckdb": db_path,
    }


def query_amf_as_of(db_path: Path, as_of: datetime) -> list[dict[str, Any]]:
    """Query AMF rows whose conservative availability time is at or before cutoff."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    with duckdb.connect(str(db_path), read_only=True) as connection:
        cursor = connection.execute(
            "SELECT * FROM amf_short_positions WHERE available_at <= ? ORDER BY available_at",
            [as_of.astimezone(UTC)],
        )
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def audit_amf_records(records: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    """Produce a deterministic coverage/quality report for one imported history."""
    if not records:
        raise ValueError("cannot audit an empty AMF dataset")
    positions = sorted(row["position_date"] for row in records if row.get("position_date"))
    publications = sorted(row["publication_date"] for row in records if row.get("publication_date"))
    pub_days = set(publications)
    if publications:
        days = (date.fromisoformat(publications[-1]) - date.fromisoformat(publications[0])).days + 1
        missing_days = days - len(pub_days)
    else:
        missing_days = None
    duplicate_keys = [
        (row.get("isin"), row.get("holder"), row.get("position_date"),
         row.get("publication_date"), row.get("publication_end_date"),
         row.get("net_short_position_pct"))
        for row in records
    ]
    ratios = sorted(
        float(row["net_short_position_pct"])
        for row in records
        if row.get("net_short_position_pct") is not None
    )
    header_signature = metadata.get("header_signature")
    formats = [{
        "parser_version": metadata.get("parser_version"),
        "header_signature": header_signature,
        "headers": metadata.get("source_headers", []),
        "record_count": len(records),
    }]
    return {
        "source_id": AMF_SOURCE_ID,
        "row_count": len(records),
        "position_date_min": positions[0] if positions else None,
        "position_date_max": positions[-1] if positions else None,
        "publication_date_min": publications[0] if publications else None,
        "publication_date_max": publications[-1] if publications else None,
        "unique_publication_days": len(pub_days),
        "missing_calendar_days_in_publication_range": missing_days,
        "unique_isin_count": len({row["isin"] for row in records if row.get("isin")}),
        "unique_issuer_count": len({row["issuer"] for row in records if row.get("issuer")}),
        "unique_holder_count": len({row["holder"] for row in records if row.get("holder")}),
        "missing_isin_count": sum(row.get("isin_validation") == "missing" for row in records),
        "missing_isin_rate": (
            sum(row.get("isin_validation") == "missing" for row in records) / len(records)
        ),
        "invalid_isin_count": sum(row.get("isin_validation") == "invalid" for row in records),
        "invalid_isin_examples": [
            {
                "source_line": row.get("source_line"),
                "source_fields": row.get("source_fields"),
            }
            for row in records
            if row.get("isin_validation") == "invalid"
        ][:10],
        "missing_ratio_count": sum(row.get("net_short_position_pct") is None for row in records),
        "missing_ratio_rate": (
            sum(row.get("net_short_position_pct") is None for row in records) / len(records)
        ),
        "exact_duplicate_count": len(records) - len(set(duplicate_keys)),
        "net_short_position_pct_distribution": _distribution(ratios),
        "source_format_variants_seen": formats,
        "historical_format_limit": (
            "Only this export's current header is observable; older formats are unverified."
        ),
    }


def _validate_amf_record(row: dict[str, Any], snapshot_retrieved_at: datetime, index: int) -> None:
    isin = row.get("isin")
    if isin and not _valid_isin(isin):
        raise ValueError(f"invalid ISIN in Gremlin AMF record {index}")
    if row.get("isin_validation") == "invalid" and isin is not None:
        raise ValueError(f"invalid source ISIN was not quarantined in Gremlin AMF record {index}")
    ratio = row.get("net_short_position_pct")
    if ratio is not None and (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not 0 <= ratio <= 100
    ):
        raise ValueError(f"invalid normalized ratio in Gremlin AMF record {index}")
    record_retrieved = _parse_datetime(row.get("retrieved_at"))
    available_at = _parse_datetime(row.get("available_at"))
    if record_retrieved != snapshot_retrieved_at:
        raise ValueError(f"retrieved_at mismatch in Gremlin AMF record {index}")
    publication_date = _parse_date(row.get("publication_date"))
    published_raw = row.get("published_at")
    published_at = _parse_datetime(published_raw) if published_raw else None
    if publication_date is not None:
        minimum = datetime.combine(publication_date + timedelta(days=1), time.min, tzinfo=UTC)
        if available_at < minimum:
            raise ValueError(f"AMF record {index} is available before publication-date fence")
    elif published_at is not None:
        if available_at < published_at:
            raise ValueError(f"AMF record {index} is available before published_at")
    elif available_at < record_retrieved:
        raise ValueError(f"AMF record {index} is available before retrieval")
    if row.get("source_id") != AMF_SOURCE_ID:
        raise ValueError(f"unexpected source_id in Gremlin AMF record {index}")


def _valid_isin(value: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        return False
    expanded = "".join(str(int(char, 36)) if char.isalpha() else char for char in value)
    total = 0
    for index, char in enumerate(reversed(expanded)):
        digit = int(char)
        if index % 2:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return total % 10 == 0


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("snapshot timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value)[:10])


def _distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("min", "p25", "median", "p75", "max")}
    return {
        "min": values[0],
        "p25": values[round((len(values) - 1) * 0.25)],
        "median": values[round((len(values) - 1) * 0.5)],
        "p75": values[round((len(values) - 1) * 0.75)],
        "max": values[-1],
    }
