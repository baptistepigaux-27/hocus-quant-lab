"""SPEC-004 temporal cube, PIT, replay and incremental build tests."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

import hocus_quant.features.cube as cube
from hocus_quant.features.cube import build_feature_cube, export_feature_panel, resolve_date_grid
from hocus_quant.features.snapshot import build_feature_snapshot

PARIS = ZoneInfo("Europe/Paris")


def _rows(count: int = 45, start_index: int = 0) -> list[dict[str, Any]]:
    records = []
    for index in range(start_index, count):
        close = 100 + index * 0.2
        records.append(
            {
                "session_date": date(2024, 1, 1) + timedelta(days=index),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return records


def _make_data(
    data_dir: Path, *, future_bad: bool = False, second_starts: int | None = None
) -> None:
    data_dir.mkdir(parents=True)
    with duckdb.connect(str(data_dir / "research.duckdb")) as connection:
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
        retrieved = datetime(2026, 9, 1, tzinfo=PARIS)
        series = [("FR0000000001", 0, False)]
        if second_starts is not None:
            series.append(("FR0000000002", second_starts, False))
        for instrument, begins, _bad in series:
            for row in _rows(count=46, start_index=begins):
                values = [
                    instrument,
                    instrument,
                    row["session_date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    datetime.combine(
                        row["session_date"] + timedelta(days=1), datetime.min.time(), PARIS
                    ),
                    retrieved,
                    "fixture-snapshot",
                ]
                if instrument == "FR0000000002" and row["session_date"] == date(2024, 1, 21):
                    values[3] = values[4] * 1.1
                connection.execute(
                    "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values
                )
        if future_bad:
            # Available after the historical slice cutoff and after the series' initial history.
            connection.execute(
                "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    "FR0000000001",
                    "FR0000000001",
                    date(2024, 2, 16),
                    1000.0,
                    110.0,
                    90.0,
                    100.0,
                    1000.0,
                    datetime(2024, 2, 20, tzinfo=PARIS),
                    retrieved,
                    "fixture-snapshot",
                ],
            )
            for row in _rows(count=50, start_index=49):
                connection.execute(
                    "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        "FR0000000001",
                        "FR0000000001",
                        date(2024, 2, 19),
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        datetime(2024, 2, 20, tzinfo=PARIS),
                        retrieved,
                        "fixture-snapshot",
                    ],
                )


def _build(
    data_dir: Path,
    output_dir: Path,
    dates: list[date],
    *,
    resume: bool = False,
    force: bool = False,
    quality_scope: str = "approved",
) -> dict[str, Any]:
    return build_feature_cube(
        output_dir=output_dir,
        data_dir=data_dir,
        dates=dates,
        cadence="explicit",
        quality_scope=quality_scope,
        resume=resume,
        force=force,
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cube_slice_equals_independent_spec003_snapshot(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    as_of = date(2024, 2, 14)
    out = tmp_path / "cube"
    _build(data_dir, out, [as_of])
    oracle_dir = tmp_path / "oracle"
    oracle = build_feature_snapshot(
        as_of_date=as_of,
        output_dir=oracle_dir,
        data_dir=data_dir,
        quality_scope="approved",
    )
    cube_file = out / f"as_of_date={as_of.isoformat()}" / "features.parquet"
    with duckdb.connect() as connection:
        diff = connection.execute(
            """SELECT count(*) FROM (
                 (SELECT entity_id, entity_family, as_of_date, feature_id, feature_value,
                         feature_status, unavailable_reason, "window", source_series,
                         coverage_count, coverage_ratio, formula_version
                  FROM read_parquet(?)
                  EXCEPT ALL
                  SELECT entity_id, entity_family, as_of_date, feature_id, feature_value,
                         feature_status, unavailable_reason, "window", source_series,
                         coverage_count, coverage_ratio, formula_version
                  FROM read_parquet(?))
                 UNION ALL
                 (SELECT entity_id, entity_family, as_of_date, feature_id, feature_value,
                         feature_status, unavailable_reason, "window", source_series,
                         coverage_count, coverage_ratio, formula_version
                  FROM read_parquet(?)
                  EXCEPT ALL
                  SELECT entity_id, entity_family, as_of_date, feature_id, feature_value,
                         feature_status, unavailable_reason, "window", source_series,
                         coverage_count, coverage_ratio, formula_version
                  FROM read_parquet(?))
               )""",
            [
                str(cube_file),
                str(oracle_dir / "features_long.parquet"),
                str(oracle_dir / "features_long.parquet"),
                str(cube_file),
            ],
        ).fetchone()[0]
    assert diff == 0
    manifest = json.loads((cube_file.parent / "manifest.json").read_text())
    assert manifest["entity_count"] == oracle["entity_count"]
    assert manifest["quality_scope"] == "approved"
    assert manifest["pit_grade"] == "reconstructed"


def test_replay_is_deterministic_and_resume_skips_valid_partition(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    output = tmp_path / "cube"
    as_of = date(2024, 2, 14)
    _build(data_dir, output, [as_of])
    partition = output / f"as_of_date={as_of.isoformat()}" / "features.parquet"
    first_hash = _hash(partition)
    replay = _build(data_dir, output, [as_of], resume=True)
    assert replay["reused_slices"]
    assert _hash(partition) == first_hash


def test_future_data_does_not_change_a_past_slice(tmp_path: Path) -> None:
    as_of = date(2024, 1, 20)
    outputs = []
    for name, future in (("without-future", False), ("with-future", True)):
        data_dir = tmp_path / name / "data"
        _make_data(data_dir, future_bad=future)
        output = tmp_path / name / "cube"
        _build(data_dir, output, [as_of])
        outputs.append(_hash(output / f"as_of_date={as_of.isoformat()}" / "features.parquet"))
    assert outputs[0] == outputs[1]


def test_future_quality_anomaly_does_not_retroactively_quarantine(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir, future_bad=True)
    early, late = date(2024, 2, 14), date(2024, 2, 19)
    output = tmp_path / "cube"
    _build(data_dir, output, [early, late])
    early_path = output / f"as_of_date={early}" / "quality_status.parquet"
    late_path = output / f"as_of_date={late}" / "quality_status.parquet"
    early_rows = duckdb.sql(
        f"SELECT quality_status FROM read_parquet('{early_path}') "
        "WHERE entity_id='abc-bourse-manual:equity:FR0000000001'"
    ).fetchall()
    late_rows = duckdb.sql(
        f"SELECT quality_status FROM read_parquet('{late_path}') "
        "WHERE entity_id='abc-bourse-manual:equity:FR0000000001'"
    ).fetchall()
    assert early_rows == [("approved",)]
    assert late_rows == [("quarantined",)]


def test_historical_universe_arrival_and_absent_entity(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir, second_starts=25)
    early, late = date(2024, 1, 10), date(2024, 2, 15)
    output = tmp_path / "cube"
    report = _build(data_dir, output, [early, late])
    assert report["audit"]["cells_by_date"][0]["entity_count"] == 1
    assert report["audit"]["cells_by_date"][1]["entity_count"] == 2
    with duckdb.connect(str(output / "feature_cube.duckdb"), read_only=True) as connection:
        absent = connection.execute(
            "SELECT count(*) FROM features_long WHERE as_of_date=? AND entity_id LIKE '%0002'",
            [early],
        ).fetchone()[0]
    assert absent == 0


def test_missing_features_stay_null_without_imputation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    as_of = date(2024, 1, 3)
    output = tmp_path / "cube"
    _build(data_dir, output, [as_of])
    with duckdb.connect(str(output / "feature_cube.duckdb"), read_only=True) as connection:
        null_count = connection.execute(
            "SELECT count(*) FROM features_long WHERE feature_status='unavailable' "
            "AND feature_value IS NULL"
        ).fetchone()[0]
        zero_unavailable = connection.execute(
            "SELECT count(*) FROM features_long WHERE feature_status='unavailable' "
            "AND feature_value=0"
        ).fetchone()[0]
    assert null_count > 0
    assert zero_unavailable == 0


@pytest.mark.parametrize("contract_piece", ["registry", "quality"])
def test_changed_registry_or_quality_fingerprint_blocks_mixing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contract_piece: str
) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    output = tmp_path / "cube"
    _build(data_dir, output, [date(2024, 2, 14)])
    if contract_piece == "registry":
        original = cube.registry_document
        changed = {**original(), "sha256": "changed-registry"}
        monkeypatch.setattr(cube, "registry_document", lambda: changed)
    else:
        monkeypatch.setattr(cube, "QUALITY_RULES_SHA256", "changed-quality-rules")
    with pytest.raises(ValueError, match="cube contract changed"):
        _build(data_dir, output, [date(2024, 2, 15)], resume=True)


def test_interruption_and_resume_matches_complete_build(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    dates = [date(2024, 2, 14), date(2024, 2, 15)]
    partial = tmp_path / "partial"
    _build(data_dir, partial, dates[:1])
    _build(data_dir, partial, dates, resume=True)
    complete = tmp_path / "complete"
    _build(data_dir, complete, dates)
    for as_of in dates:
        rel = f"as_of_date={as_of.isoformat()}/features.parquet"
        assert _hash(partial / rel) == _hash(complete / rel)


def test_force_rebuild_atomically_replaces_one_partition(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    as_of = date(2024, 2, 14)
    output = tmp_path / "cube"
    _build(data_dir, output, [as_of])
    partition = output / f"as_of_date={as_of.isoformat()}" / "features.parquet"
    expected_hash = _hash(partition)
    partition.write_bytes(b"corrupt")
    _build(data_dir, output, [as_of], force=True)
    assert _hash(partition) == expected_hash


def test_each_partition_has_one_run_and_persists_full_contract(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    as_of = date(2024, 2, 14)
    output = tmp_path / "cube"
    report = _build(data_dir, output, [as_of])
    manifest = json.loads(
        (output / f"as_of_date={as_of.isoformat()}" / "manifest.json").read_text()
    )
    assert manifest["quality_scope"] == "approved"
    assert manifest["quality_rules_fingerprint"]
    assert manifest["feature_registry_fingerprint"]
    assert manifest["pit_grade"] == "reconstructed"
    assert manifest["run_id"]
    with duckdb.connect(str(output / "feature_cube.duckdb"), read_only=True) as connection:
        run_ids = connection.execute(
            "SELECT count(DISTINCT run_id) FROM features_long WHERE as_of_date=?", [as_of]
        ).fetchone()[0]
        assert connection.execute("SELECT count(*) FROM features_wide").fetchone()[0] > 0
    assert run_ids == 1
    assert report["contract"]["strict_pit_claimed"] is False


def test_weekly_grid_uses_last_market_session_per_iso_week(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    dates = resolve_date_grid(
        data_dir=data_dir,
        cadence="weekly",
        start=date(2024, 1, 1),
        end=date(2024, 1, 14),
    )
    assert dates == [date(2024, 1, 7), date(2024, 1, 14)]
    explicit = resolve_date_grid(data_dir=data_dir, cadence="explicit", dates=[date(2024, 1, 8)])
    assert explicit == [date(2024, 1, 8)]


def test_export_wide_panel_filters_and_preserves_missing_values(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    output = tmp_path / "cube"
    _build(data_dir, output, [date(2024, 1, 3), date(2024, 2, 14)])
    target = tmp_path / "panel.parquet"
    frame = export_feature_panel(
        output,
        start=date(2024, 2, 1),
        feature_ids=["close.level.mean_delta.w60.v1"],
        minimum_coverage=0.1,
        output_path=target,
    )
    assert target.is_file()
    assert frame.height > 0
    assert "close.level.mean_delta.w60.v1" in frame.columns
    assert frame["as_of_date"].min() == date(2024, 2, 14)


def test_all_scope_is_rejected_for_research_cube(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _make_data(data_dir)
    with pytest.raises(ValueError, match="require quality_scope='approved'"):
        _build(data_dir, tmp_path / "cube", [date(2024, 2, 14)], quality_scope="all")
