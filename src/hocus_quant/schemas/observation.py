"""Normalized, point-in-time observation contract."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import pandera.polars as pa
import polars as pl

ObservationSchema = pa.DataFrameSchema(
    {
        "observation_id": pa.Column(str, unique=True, nullable=False),
        "snapshot_id": pa.Column(str, nullable=False),
        "source_id": pa.Column(str, nullable=False),
        "source_checksum": pa.Column(str, nullable=False),
        "observation_date": pa.Column(pl.Date, nullable=True),
        "published_at": pa.Column(pl.Datetime("us", "UTC"), nullable=True),
        "retrieved_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "valid_from": pa.Column(pl.Datetime("us", "UTC"), nullable=True),
        "available_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "source_url": pa.Column(str, nullable=False),
        "record": pa.Column(pl.Struct, nullable=False),
    },
    strict=True,
)


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_record(
    *, source_id: str, source_checksum: str, snapshot_id: str, source_url: str,
    retrieved_at: datetime, record: dict[str, Any],
) -> dict[str, Any]:
    published_at = parse_datetime(record.get("published_at") or record.get("publication_date"))
    retrieved = parse_datetime(retrieved_at)
    assert retrieved is not None
    valid_from = parse_datetime(record.get("valid_from"))
    available_at = max(retrieved, published_at) if published_at is not None else retrieved
    observation_date = parse_date(record.get("observation_date") or record.get("position_date"))
    canonical_record = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    record_hash = hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()
    return {
        "observation_id": f"{snapshot_id}:{record_hash}",
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "source_checksum": source_checksum,
        "observation_date": observation_date,
        "published_at": published_at,
        "retrieved_at": retrieved,
        "valid_from": valid_from,
        "available_at": available_at,
        "source_url": source_url,
        "record": record,
    }
