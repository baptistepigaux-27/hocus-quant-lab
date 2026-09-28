from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hocus_quant.ingestion.amf import ingest_amf_snapshot, query_amf_as_of

FIXTURE = Path(__file__).parent / "fixtures/amf/amf_net_short_positions_snapshot.json"


def test_real_amf_fixture_imports_raw_bronze_silver_duckdb_and_audit(tmp_path: Path) -> None:
    paths = ingest_amf_snapshot(FIXTURE, tmp_path / "data")

    assert all(path.exists() for path in paths.values())
    with duckdb.connect(str(paths["duckdb"]), read_only=True) as connection:
        assert connection.execute("SELECT count(*) FROM amf_short_positions").fetchone()[0] == 4
        assert connection.execute(
            "SELECT net_short_position_pct FROM amf_short_positions "
            "WHERE isin = 'FR0000054470' ORDER BY position_date DESC LIMIT 1"
        ).fetchone()[0] == 0.35
    audit = json.loads(paths["audit"].read_text(encoding="utf-8"))
    assert audit["row_count"] == 4
    assert audit["unique_isin_count"] == 1
    assert audit["missing_isin_rate"] == 0
    assert paths["raw"].parent.parent.name == "amf"


def test_amf_as_of_fence_hides_publication_day_and_includes_next_day(tmp_path: Path) -> None:
    paths = ingest_amf_snapshot(FIXTURE, tmp_path / "data")

    before = query_amf_as_of(paths["duckdb"], datetime(2015, 10, 6, 23, 59, tzinfo=UTC))
    after = query_amf_as_of(paths["duckdb"], datetime(2015, 10, 7, 0, 0, tzinfo=UTC))
    position_day_midday = query_amf_as_of(
        paths["duckdb"], datetime(2015, 10, 7, 10, 0, tzinfo=UTC)
    )
    following_day = query_amf_as_of(paths["duckdb"], datetime(2015, 10, 8, 0, 0, tzinfo=UTC))

    assert before == []
    assert len(after) == 3
    assert len(position_day_midday) == 3
    assert len(following_day) == 4
    assert all(row["available_at"] <= datetime(2015, 10, 8, tzinfo=UTC) for row in following_day)


def test_checksum_is_verified_before_quantlab_ingestion(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["payload"] += "\n"
    damaged = tmp_path / "damaged.json"
    damaged.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        ingest_amf_snapshot(damaged, tmp_path / "data")


def test_bad_isin_is_rejected_during_normalization(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["records"][0]["isin"] = "FR0000054471"
    changed_payload = payload["payload"]
    payload["checksum"] = "sha256:" + hashlib.sha256(changed_payload.encode()).hexdigest()
    damaged = tmp_path / "bad-isin.json"
    damaged.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid ISIN"):
        ingest_amf_snapshot(damaged, tmp_path / "data")
