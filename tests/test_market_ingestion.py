"""Offline tests for provider-neutral market snapshot ingestion and PIT queries."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from hocus_quant.ingestion.market import (
    ingest_market_snapshot,
    query_market_amf_as_of,
    query_market_as_of,
)

FIXTURE = Path(__file__).parent / "fixtures" / "market" / "market_data_snapshot.json"
ARTIFACTS = FIXTURE.parent / "gremlin-artifacts"


def test_market_snapshot_ingests_raw_bronze_silver_and_duckdb(tmp_path: Path) -> None:
    outputs = ingest_market_snapshot(
        FIXTURE, gremlin_artifact_root=ARTIFACTS, data_dir=tmp_path / "data"
    )

    assert outputs["raw"].read_bytes().startswith(b"Date,Open")
    assert outputs["bronze"].exists()
    assert outputs["silver"].exists()
    assert outputs["instruments"].exists()
    assert outputs["corporate_actions"].exists()
    audit = json.loads(outputs["audit"].read_text())
    assert audit["requested_isin_count"] == 271
    assert audit["resolved_isin_count"] == 1
    assert audit["not_found_isin_count"] == 1
    assert audit["mapping_response_complete"] is False
    assert audit["session_date_min"] == "2020-01-02"
    assert audit["session_date_max"] == "2020-01-03"
    assert audit["missing_ohlc_count"] == 0
    assert audit["missing_volume_count"] == 0
    assert outputs["unresolved"].exists()
    assert outputs["suspicious"].exists()
    with duckdb.connect(str(outputs["duckdb"]), read_only=True) as connection:
        assert connection.execute("select count(*) from market_daily").fetchone()[0] == 2
        assert connection.execute("select count(*) from instruments").fetchone()[0] == 2
        assert connection.execute("select count(*) from corporate_actions").fetchone()[0] == 1
        assert (
            connection.execute("select count(*) from market_daily where mic='XPAR'").fetchone()[0]
            == 2
        )


def test_d1_bar_is_not_visible_before_d_plus_1_and_adjusted_is_not_pit_safe(tmp_path: Path) -> None:
    outputs = ingest_market_snapshot(
        FIXTURE, gremlin_artifact_root=ARTIFACTS, data_dir=tmp_path / "data"
    )

    before_d_plus_1 = query_market_as_of(outputs["duckdb"], datetime(2020, 1, 3, 12, tzinfo=UTC))
    assert len(before_d_plus_1) == 1
    assert before_d_plus_1[0]["session_date"].isoformat() == "2020-01-02"
    after_d_plus_1 = query_market_as_of(outputs["duckdb"], datetime(2020, 1, 4, 12, tzinfo=UTC))
    assert len(after_d_plus_1) == 2
    assert all(row["adjusted_close"] is None for row in after_d_plus_1)


def test_as_of_selects_only_revisions_known_at_the_cutoff(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    outputs = ingest_market_snapshot(FIXTURE, gremlin_artifact_root=ARTIFACTS, data_dir=data_dir)
    corrected_manifest = json.loads(FIXTURE.read_text())
    corrected_manifest["snapshot_id"] = "fixture-market-correction-20200201"
    corrected_manifest["retrieved_at"] = "2020-02-01T12:00:00+00:00"
    corrected_manifest["raw_snapshots"][0]["capture_id"] = "capture-fixture-market-correction"
    new_payload = (
        ARTIFACTS / f"{corrected_manifest['raw_snapshots'][0]['artifact_id']}.bin"
    ).read_bytes()
    corrected_payload = new_payload.replace(
        b"2020-01-03,101,105,100,104,1200",
        b"2020-01-03,101,106,100,105,1200",
    )
    new_digest = hashlib.sha256(corrected_payload).hexdigest()
    artifact_dir = tmp_path / "gremlin-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / f"raw-{new_digest}.bin").write_bytes(corrected_payload)
    raw_ref = corrected_manifest["raw_snapshots"][0]
    raw_ref.update(
        {
            "artifact_id": f"raw-{new_digest}",
            "checksum": f"sha256:{new_digest}",
            "size_bytes": len(corrected_payload),
            "retrieved_at": corrected_manifest["retrieved_at"],
        }
    )
    corrected_manifest["market_daily"][1]["close"] = 105.0
    corrected_manifest["market_daily"][1]["high"] = 106.0
    for row in corrected_manifest["market_daily"]:
        row["snapshot_checksum"] = f"sha256:{new_digest}"
        row["retrieved_at"] = corrected_manifest["retrieved_at"]
        row["adjusted_close_available_at"] = corrected_manifest["retrieved_at"]
    corrected_manifest["corporate_actions"][0]["snapshot_checksum"] = f"sha256:{new_digest}"
    corrected_manifest["corporate_actions"][0]["retrieved_at"] = corrected_manifest["retrieved_at"]
    corrected_manifest["corporate_actions"][0]["available_at"] = corrected_manifest["retrieved_at"]
    correction_path = tmp_path / "correction.json"
    correction_path.write_text(json.dumps(corrected_manifest))
    corrected = ingest_market_snapshot(
        correction_path,
        gremlin_artifact_root=artifact_dir,
        data_dir=data_dir,
    )

    known_before_correction = query_market_as_of(
        outputs["duckdb"], datetime(2020, 1, 10, tzinfo=UTC)
    )
    known_after_correction = query_market_as_of(
        corrected["duckdb"], datetime(2020, 2, 2, tzinfo=UTC)
    )
    assert len(list((data_dir / "silver" / "market_daily").glob("*.parquet"))) == 2
    assert (
        next(
            row["close"]
            for row in known_before_correction
            if row["session_date"].isoformat() == "2020-01-03"
        )
        == 104.0
    )
    assert (
        next(
            row["close"]
            for row in known_after_correction
            if row["session_date"].isoformat() == "2020-01-03"
        )
        == 105.0
    )


def test_asof_amf_join_returns_latest_known_holder_row_once(tmp_path: Path) -> None:
    outputs = ingest_market_snapshot(
        FIXTURE, gremlin_artifact_root=ARTIFACTS, data_dir=tmp_path / "data"
    )
    with duckdb.connect(str(outputs["duckdb"])) as connection:
        connection.execute("""
            CREATE TABLE amf_short_positions (
                isin VARCHAR, holder VARCHAR, net_short_position_pct DOUBLE,
                available_at TIMESTAMPTZ, publication_date DATE, retrieved_at TIMESTAMPTZ
            )
        """)
        connection.execute("""
            INSERT INTO amf_short_positions VALUES
            ('FR0000120073', 'Holder A', 0.65,
             '2020-01-03 22:00:00+00', '2020-01-03', '2020-01-04 08:00:00+00'),
            ('FR0000120073', 'Holder A', 0.70,
             '2020-01-05 08:00:00+00', '2020-01-05', '2020-01-05 09:00:00+00')
        """)

    rows = query_market_amf_as_of(outputs["duckdb"], datetime(2020, 1, 4, 12, tzinfo=UTC))
    jan3_rows = [row for row in rows if row["session_date"].isoformat() == "2020-01-03"]
    assert len(jan3_rows) == 1
    assert jan3_rows[0]["holder"] == "Holder A"
    assert jan3_rows[0]["net_short_position_pct"] == 0.65


def test_invalid_raw_checksum_is_rejected(tmp_path: Path) -> None:
    bad_root = tmp_path / "bad-artifacts"
    bad_root.mkdir()
    shutil.copyfile(next(ARTIFACTS.glob("*.bin")), bad_root / next(ARTIFACTS.glob("*.bin")).name)
    (bad_root / next(ARTIFACTS.glob("*.bin")).name).write_bytes(b"wrong")

    with pytest.raises(ValueError, match="checksum/size"):
        ingest_market_snapshot(FIXTURE, gremlin_artifact_root=bad_root, data_dir=tmp_path / "data")
