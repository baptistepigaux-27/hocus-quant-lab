from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hocus_quant.ingestion.pipeline import ingest_snapshot, query_as_of


def write_fixture(path: Path) -> None:
    record = {
        "publication_date": "2024-02-01T09:00:00Z",
        "position_date": "2024-01-31",
        "holder": "Fixture Capital",
        "issuer": "Example SA",
        "isin": "FR0000000001",
        "net_short_position_pct": 0.52,
    }
    payload = json.dumps({"records": [record]}, ensure_ascii=False, separators=(",", ":"))
    checksum = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    snapshot = {
        "source_id": "amf_short_positions",
        "retrieved_at": "2024-02-01T12:00:00Z",
        "source_url": "https://fixture.invalid/amf.csv",
        "content_type": "application/json",
        "checksum": checksum,
        "payload": payload,
        "metadata": {"fixture": True},
    }
    path.write_text(json.dumps(snapshot), encoding="utf-8")


def test_fixture_flows_raw_bronze_silver_and_duckdb(tmp_path: Path) -> None:
    fixture = tmp_path / "snapshot.json"
    write_fixture(fixture)
    paths = ingest_snapshot(fixture, tmp_path / "data")

    assert all(path.exists() for path in paths.values())
    with duckdb.connect(str(paths["duckdb"]), read_only=True) as connection:
        columns = {row[0] for row in connection.execute("DESCRIBE observations").fetchall()}
        expected_temporal = {
            "observation_date", "published_at", "retrieved_at", "valid_from", "available_at"
        }
        assert expected_temporal <= columns


def test_as_of_query_excludes_unavailable_observations(tmp_path: Path) -> None:
    fixture = tmp_path / "snapshot.json"
    write_fixture(fixture)
    paths = ingest_snapshot(fixture, tmp_path / "data")

    before_retrieval = query_as_of(
        paths["duckdb"], datetime(2024, 2, 1, 11, 59, tzinfo=UTC)
    )
    at_availability = query_as_of(
        paths["duckdb"], datetime(2024, 2, 1, 12, 0, tzinfo=UTC)
    )

    assert before_retrieval == []
    assert len(at_availability) == 1
    assert at_availability[0]["observation_date"].isoformat() == "2024-01-31"


def test_replay_is_idempotent(tmp_path: Path) -> None:
    fixture = tmp_path / "snapshot.json"
    write_fixture(fixture)
    data_dir = tmp_path / "data"

    first = ingest_snapshot(fixture, data_dir)
    second = ingest_snapshot(fixture, data_dir)

    assert first == second


def test_same_payload_with_later_retrieval_keeps_new_availability(tmp_path: Path) -> None:
    fixture = tmp_path / "snapshot.json"
    write_fixture(fixture)
    data_dir = tmp_path / "data"
    first = ingest_snapshot(fixture, data_dir)

    snapshot = json.loads(fixture.read_text(encoding="utf-8"))
    snapshot["retrieved_at"] = "2024-02-02T12:00:00Z"
    later_fixture = tmp_path / "later_snapshot.json"
    later_fixture.write_text(json.dumps(snapshot), encoding="utf-8")
    second = ingest_snapshot(later_fixture, data_dir)

    assert first["raw"] == second["raw"]
    assert first["silver"] != second["silver"]
    assert len(
        query_as_of(first["duckdb"], datetime(2024, 2, 1, 12, 0, tzinfo=UTC))
    ) == 1
    assert len(
        query_as_of(first["duckdb"], datetime(2024, 2, 2, 12, 0, tzinfo=UTC))
    ) == 2


def test_as_of_requires_timezone(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone"):
        query_as_of(tmp_path / "missing.duckdb", datetime(2024, 1, 1))
