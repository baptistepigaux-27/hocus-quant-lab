"""SPEC-003Q quality status, deterministic scope and as-of invariants."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

from hocus_quant.features.snapshot import build_feature_snapshot
from hocus_quant.validation.market_quality import (
    QUALITY_RULE_VERSION,
    assess_series,
)

PARIS = ZoneInfo("Europe/Paris")


def _entity(rows: list[dict[str, Any]], entity_id: str = "test:equity:normal") -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "entity_family": "equity",
        "observations": rows,
    }


def _rows(count: int = 40) -> list[dict[str, Any]]:
    rows = []
    for index in range(count):
        close = 100 + index * 0.2
        rows.append(
            {
                "session_date": date(2026, 1, 1) + timedelta(days=index),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return rows


def test_normal_series_is_approved_and_replay_is_deterministic() -> None:
    entity = _entity(_rows())
    first = assess_series(entity)
    second = assess_series(entity)
    assert first == second
    assert first["quality_status"] == "approved"
    assert first["diagnostic_types"] == ["no_issue_found"]
    assert first["review_rule_version"] == QUALITY_RULE_VERSION


def test_impossible_ohlc_is_quarantined_with_exact_gap() -> None:
    rows = _rows()
    rows[20]["open"] = rows[20]["high"] * 1.1
    result = assess_series(_entity(rows))
    assert result["quality_status"] == "quarantined"
    issue = next(
        item
        for item in result["quality_evidence"]
        if item["rule"] == "ohlc_envelope_exceeded_2pct"
    )
    assert issue["date"] == rows[20]["session_date"].isoformat()
    assert issue["gaps"]["open_above_high"] > issue["tolerance"]


def test_large_coherent_move_is_review_not_quarantine() -> None:
    rows = _rows()
    # A 40% gap can be a real market event; its OHLC remains internally consistent.
    for row in rows[20:]:
        for field in ("open", "high", "low", "close"):
            row[field] *= 1.4
    result = assess_series(_entity(rows))
    assert result["quality_status"] == "review"
    assert "large_move_plausible" in result["diagnostic_types"]
    assert "ohlc_inconsistent" not in result["diagnostic_types"]


def test_scale_break_emits_review_only_and_volume_co_movement_evidence() -> None:
    rows = _rows()
    for row in rows[20:]:
        for field in ("open", "high", "low", "close"):
            row[field] /= 100
        row["volume"] *= 100
    result = assess_series(_entity(rows))
    assert result["quality_status"] == "review"
    assert "probable_scale_change" in result["diagnostic_types"]
    assert any(item["rule"] == "possible_scale_change" for item in result["quality_evidence"])


def test_raw_rows_are_not_modified_by_quality_assessment() -> None:
    rows = _rows()
    before = [dict(row) for row in rows]
    assess_series(_entity(rows))
    assert rows == before


def test_quality_assessment_never_reads_after_as_of_observation() -> None:
    rows = _rows(42)
    first = assess_series(_entity(rows[:30]))
    rows[30]["open"] = rows[30]["high"] * 50
    rows[30]["session_date"] = date(2026, 12, 31)
    as_of = assess_series(_entity(rows[:30]))
    assert first == as_of
    assert as_of["observations_as_of"] == rows[29]["session_date"].isoformat()


def _create_quality_db(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    db_path = data_dir / "research.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """CREATE TABLE daily_rows (
                instrument_id VARCHAR, isin VARCHAR, session_date DATE,
                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
                available_at TIMESTAMPTZ, retrieved_at TIMESTAMPTZ, snapshot_id VARCHAR
            )"""
        )
        connection.execute("CREATE VIEW market_daily_history AS SELECT * FROM daily_rows")
        connection.execute(
            """CREATE VIEW market_series_history AS SELECT * FROM (
              VALUES (NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
                NULL::DATE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE,
                NULL::DOUBLE, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ, NULL::VARCHAR,
                NULL::VARCHAR)) AS v(universe_id, series_id, provider_instrument_id,
                isin, session_date, open, high, low, close, volume, available_at,
                retrieved_at, snapshot_checksum, member_checksum) WHERE 1=0"""
        )
        retrieved = datetime(2026, 4, 3, tzinfo=PARIS)
        for identifier, bad in (("FR0000000001", False), ("FR0000000002", True)):
            for row in _rows():
                session = row["session_date"]
                values = [
                    identifier,
                    identifier,
                    session,
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    datetime.combine(session + timedelta(days=1), datetime.min.time(), PARIS),
                    retrieved,
                    "fixture",
                ]
                if bad and session == date(2026, 1, 20):
                    values[3] = values[4] * 1.1
                connection.execute(
                    "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
        # The bar date is within the requested horizon, but its availability is after
        # the 2026-03-02 cutoff. Its impossible OHLC must not affect that snapshot.
        connection.execute(
            "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "FR0000000001",
                "FR0000000001",
                date(2026, 3, 1),
                1000.0,
                101.0,
                99.0,
                100.0,
                5000.0,
                datetime(2026, 3, 3, tzinfo=PARIS),
                retrieved,
                "late-unavailable",
            ],
        )


def test_snapshot_all_keeps_quarantined_and_approved_excludes_it(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _create_quality_db(data_dir)
    source_before = (data_dir / "research.duckdb").read_bytes()
    all_audit = build_feature_snapshot(
        as_of_date=date(2026, 3, 1),
        output_dir=tmp_path / "all",
        data_dir=data_dir,
        quality_scope="all",
    )
    approved_audit = build_feature_snapshot(
        as_of_date=date(2026, 3, 1),
        output_dir=tmp_path / "approved",
        data_dir=data_dir,
        quality_scope="approved",
    )
    assert all_audit["candidate_entity_count"] == 2
    assert all_audit["entity_count"] == 2
    assert all_audit["quality_excluded_entity_count"] == 0
    assert all_audit["quality_status_counts_before_scope"] == {
        "approved": 1,
        "review": 0,
        "quarantined": 1,
    }
    assert approved_audit["candidate_entity_count"] == 2
    assert approved_audit["entity_count"] == 1
    assert approved_audit["quality_excluded_entity_count"] == 1
    assert approved_audit["quality_rule_sha256"] == all_audit["quality_rule_sha256"]
    with duckdb.connect(str(tmp_path / "all/features.duckdb"), read_only=True) as connection:
        count = connection.execute(
            "select count(distinct entity_id) from features_long"
        ).fetchone()[0]
        assert count == 2
    with duckdb.connect(str(tmp_path / "approved/features.duckdb"), read_only=True) as connection:
        count = connection.execute(
            "select count(distinct entity_id) from features_long"
        ).fetchone()[0]
        assert count == 1
    assert (data_dir / "research.duckdb").read_bytes() == source_before


def test_quality_scope_rejects_unknown_value(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _create_quality_db(data_dir)
    with pytest.raises(ValueError):
        build_feature_snapshot(
            as_of_date=date(2026, 3, 1),
            output_dir=tmp_path / "bad",
            data_dir=data_dir,
            quality_scope="raw",  # type: ignore[arg-type]
        )


def test_non_finite_values_are_not_silently_approved() -> None:
    rows = _rows()
    rows[12]["high"] = math.nan
    assert assess_series(_entity(rows))["quality_status"] == "quarantined"
