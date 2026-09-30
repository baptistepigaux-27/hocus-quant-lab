"""SPEC-005 target construction contracts on a small daily-resolution panel."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hocus_quant.targets.factory import build_target_set, build_target_snapshot
from hocus_quant.targets.registry import (
    BENCHMARK_MAPPINGS,
    HORIZONS,
    benchmark_registry_document,
    target_registry_document,
)

PARIS = ZoneInfo("Europe/Paris")
AS_OF = date(2024, 1, 5)
FUTURE_DATES = [
    date(2024, 1, 8),
    date(2024, 1, 11),
    date(2024, 1, 15),
    date(2024, 1, 22),
    date(2024, 1, 30),
]
CAC_ID = BENCHMARK_MAPPINGS[0]["benchmark_id"]


def _make_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    daily: list[tuple[object, ...]] = []
    series: list[tuple[object, ...]] = []
    retrieved = datetime(2026, 9, 1, tzinfo=PARIS)
    paths = {
        "FR0000000001": [100, 110, 120, 90, 95, 80],
        "FR0000000002": [100, 100, 101, 102, 103, 104],
        "FR0000000003": [100, 140, 141, 142, 143, 144],  # future review event
        "FR0000000004": [100, 101, 102, 103, 104, 105],  # future hard-quality event
    }
    all_dates = [AS_OF, *FUTURE_DATES]
    for isin, closes in paths.items():
        for day, close in zip(all_dates, closes, strict=True):
            high, low = close * 1.01, close * 0.99
            if isin == "FR0000000004" and day == FUTURE_DATES[-1]:
                high, low = close * 0.98, close * 1.02
            available = datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS)
            daily.append(
                (
                    isin,
                    isin,
                    day,
                    close,
                    high,
                    low,
                    close,
                    1_000.0,
                    available,
                    retrieved,
                    "fixture-daily-snapshot",
                )
            )
    # Later captured correction to P0 must not enter the historical cutoff.
    daily.append(
        (
            "FR0000000001",
            "FR0000000001",
            AS_OF,
            500.0,
            505.0,
            495.0,
            500.0,
            1_000.0,
            datetime(2024, 1, 8, tzinfo=PARIS),
            retrieved + timedelta(days=1),
            "late-correction",
        )
    )

    benchmark_values = [200, 201, 202, 204, 206, 208]
    for day, close in zip(all_dates, benchmark_values, strict=True):
        series.append(
            (
                "market_indices",
                "market_indices:QS0010989141",
                "QS0010989141",
                None,
                day,
                close,
                close * 1.01,
                close * 0.99,
                close,
                10_000.0,
                datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS),
                retrieved,
                "fixture-index-checksum",
                "fixture-index-members",
            )
        )
    commodity_values = [50, 51, 52, 53, 54, 55]
    for day, close in zip(all_dates, commodity_values, strict=True):
        series.append(
            (
                "commodities",
                "commodities:fixture-oil",
                "fixture-oil",
                None,
                day,
                close,
                close * 1.01,
                close * 0.99,
                close,
                500.0,
                datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS),
                retrieved,
                "fixture-commodity-checksum",
                "fixture-commodity-members",
            )
        )

    with duckdb.connect(str(data_dir / "research.duckdb")) as connection:
        connection.execute(
            """CREATE TABLE daily_rows (
              instrument_id VARCHAR, isin VARCHAR, session_date DATE,
              open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
              available_at TIMESTAMPTZ, retrieved_at TIMESTAMPTZ, snapshot_id VARCHAR
            )"""
        )
        connection.execute("CREATE VIEW market_daily_history AS SELECT * FROM daily_rows")
        connection.executemany(
            "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", daily
        )
        connection.execute(
            """CREATE TABLE series_rows (
              universe_id VARCHAR, series_id VARCHAR, provider_instrument_id VARCHAR,
              isin VARCHAR, session_date DATE, open DOUBLE, high DOUBLE, low DOUBLE,
              close DOUBLE, volume DOUBLE, available_at TIMESTAMPTZ, retrieved_at TIMESTAMPTZ,
              snapshot_checksum VARCHAR, member_checksum VARCHAR
            )"""
        )
        connection.execute("CREATE VIEW market_series_history AS SELECT * FROM series_rows")
        connection.executemany(
            "INSERT INTO series_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            series,
        )


def _rows(output_dir: Path, query: str, parameters: list[object]) -> list[tuple[object, ...]]:
    with duckdb.connect() as connection:
        return connection.execute(
            query,
            [str(output_dir / "targets.parquet"), *parameters],
        ).fetchall()


@pytest.fixture
def panel(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "targets"
    _make_data(data_dir)
    build_target_snapshot(as_of_date=AS_OF, output_dir=output_dir, data_dir=data_dir)
    return data_dir, output_dir


def test_target_grid_contains_nine_metrics_for_each_observed_session_horizon(
    panel: tuple[Path, Path],
) -> None:
    _data_dir, output_dir = panel
    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest["target_row_count"] == 6 * 45
    assert [item["horizon"] for item in manifest["target_registry"]["targets"][:9]] == [5] * 9
    assert HORIZONS == (5, 10, 20, 60, 120)


def test_absolute_relative_direction_and_future_only_risk_formulas(
    panel: tuple[Path, Path],
) -> None:
    _data_dir, output_dir = panel
    values = _rows(
        output_dir,
        """SELECT target_family, target_value, target_end_date, benchmark_start_date,
                  benchmark_end_date, benchmark_future_observation_count
           FROM read_parquet(?) WHERE entity_id=? AND horizon=5
             AND target_family IN ('return_abs','return_rel','direction_abs','direction_rel',
                                   'volatility','max_drawdown','max_upside','max_downside')
           ORDER BY target_family""",
        ["abc-bourse-manual:equity:FR0000000001"],
    )
    result = {row[0]: row[1:] for row in values}
    assert result["return_abs"][0] == pytest.approx(-0.2)
    assert result["return_abs"][1] == FUTURE_DATES[-1]
    assert result["return_rel"][0] == pytest.approx(-0.24)
    assert result["direction_abs"][0] == -1
    assert result["direction_rel"][0] == -1
    expected_vol = np.std(np.diff(np.log([110, 120, 90, 95, 80])), ddof=1) * np.sqrt(252)
    assert result["volatility"][0] == pytest.approx(expected_vol)
    assert result["max_drawdown"][0] == pytest.approx(80 / 120 - 1)
    assert result["max_upside"][0] == pytest.approx(0.2)
    assert result["max_downside"][0] == pytest.approx(-0.2)
    assert result["return_rel"][2] == AS_OF
    assert result["return_rel"][3] == FUTURE_DATES[-1]
    assert result["return_rel"][4] == 5


def test_insufficient_horizon_not_shortened_and_missing_mapping_is_unavailable(
    panel: tuple[Path, Path],
) -> None:
    _data_dir, output_dir = panel
    short = _rows(
        output_dir,
        """SELECT target_status, target_value, future_observation_count
           FROM read_parquet(?) WHERE entity_id=? AND target_family='return_abs' AND horizon=10""",
        ["abc-bourse-manual:equity:FR0000000001"],
    )[0]
    assert short == ("insufficient_future_history", None, 5)
    relative = _rows(
        output_dir,
        """SELECT target_status, unavailable_reason FROM read_parquet(?)
           WHERE entity_id='abc-bourse-manual:commodities:commodities:fixture-oil'
             AND target_family='return_rel' AND horizon=5""",
        [],
    )[0]
    assert relative == ("benchmark_unavailable", "no_defensible_v1_mapping_for_entity_family")


def test_future_quality_is_not_projected_back_and_bad_targets_are_not_consumed(
    panel: tuple[Path, Path],
) -> None:
    _data_dir, output_dir = panel
    review = _rows(
        output_dir,
        """SELECT target_status, target_value, candidate_value, future_quality_event_count
           FROM read_parquet(?) WHERE entity_id=? AND target_family='return_abs' AND horizon=5""",
        ["abc-bourse-manual:equity:FR0000000003"],
    )[0]
    assert review[0] == "future_quality_review"
    assert review[1] is None
    assert review[2] == pytest.approx(0.44)
    assert review[3] > 0
    quarantined = _rows(
        output_dir,
        """SELECT target_status, target_value, candidate_value
           FROM read_parquet(?) WHERE entity_id=? AND target_family='return_abs' AND horizon=5""",
        ["abc-bourse-manual:equity:FR0000000004"],
    )[0]
    assert quarantined[0] == "future_quality_quarantined"
    assert quarantined[1] is None
    assert quarantined[2] == pytest.approx(0.05)
    rank_status = _rows(
        output_dir,
        """SELECT target_status, cohort_size FROM read_parquet(?)
           WHERE entity_id=? AND target_family='rank_pct' AND horizon=5""",
        ["abc-bourse-manual:equity:FR0000000003"],
    )[0]
    assert rank_status == ("future_quality_review", 2)
    good_cohort = _rows(
        output_dir,
        """SELECT DISTINCT cohort_size FROM read_parquet(?)
           WHERE entity_family='equity' AND target_family='rank_pct' AND horizon=5
             AND target_status='available'""",
        [],
    )
    assert good_cohort == [(2,)]


def test_registries_are_fingerprinted_and_parquet_replay_is_deterministic(
    panel: tuple[Path, Path], tmp_path: Path
) -> None:
    data_dir, output_dir = panel
    manifest = json.loads((output_dir / "manifest.json").read_text())
    assert manifest["target_registry_fingerprint"] == target_registry_document()["sha256"]
    assert manifest["benchmark_registry_fingerprint"] == benchmark_registry_document()["sha256"]
    assert (
        json.loads(Path("src/hocus_quant/targets/target_registry.json").read_text())["sha256"]
        == target_registry_document()["sha256"]
    )
    assert (
        json.loads(Path("src/hocus_quant/targets/benchmark_registry.json").read_text())["sha256"]
        == benchmark_registry_document()["sha256"]
    )
    assert manifest["pit_grade"] == "reconstructed"
    assert manifest["strict_pit_claimed"] is False
    first_hash = hashlib.sha256((output_dir / "targets.parquet").read_bytes()).hexdigest()
    replay_dir = tmp_path / "replay"
    build_target_snapshot(as_of_date=AS_OF, output_dir=replay_dir, data_dir=data_dir)
    replay_hash = hashlib.sha256((replay_dir / "targets.parquet").read_bytes()).hexdigest()
    assert first_hash == replay_hash


def test_target_set_uses_cube_grid_and_keeps_benchmark_outside_cube_universe(
    panel: tuple[Path, Path], tmp_path: Path
) -> None:
    data_dir, _output_dir = panel
    cube_dir = tmp_path / "cube"
    partition = cube_dir / f"as_of_date={AS_OF.isoformat()}"
    partition.mkdir(parents=True)
    (cube_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_fingerprint": "fixture-cube-contract",
                "contract": {"quality_scope": "approved"},
            }
        )
    )
    (partition / "manifest.json").write_text(
        json.dumps(
            {
                "as_of_date": AS_OF.isoformat(),
                "run_id": "fixture-cube-run",
                "contract_fingerprint": "fixture-cube-contract",
            }
        )
    )
    entity_id = "abc-bourse-manual:equity:FR0000000001"
    pq.write_table(pa.table({"entity_id": [entity_id]}), partition / "features.parquet")
    pq.write_table(
        pa.table({"entity_id": [entity_id], "quality_status": ["approved"]}),
        partition / "quality_status.parquet",
    )

    target_set_dir = tmp_path / "target_set"
    result = build_target_set(
        feature_cube_dir=cube_dir,
        output_dir=target_set_dir,
        data_dir=data_dir,
    )
    assert result["dates"] == [AS_OF.isoformat()]
    assert result["target_row_count"] == 45
    relative = _rows(
        target_set_dir / f"as_of_date={AS_OF.isoformat()}",
        """SELECT target_status, target_value, benchmark_id FROM read_parquet(?)
           WHERE target_family='return_rel' AND horizon=5""",
        [],
    )[0]
    assert relative[0] == "available"
    assert relative[1] is not None
    assert relative[2] == CAC_ID
