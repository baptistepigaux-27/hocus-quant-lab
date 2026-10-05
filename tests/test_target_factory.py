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
from hocus_quant.targets.hardening import _classify_extremes, _is_research_ready
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
EXTENDED_DATES: list[date] = []
_cursor = FUTURE_DATES[-1]
while len(EXTENDED_DATES) < 125:
    _cursor += timedelta(days=1)
    if _cursor.weekday() < 5:
        EXTENDED_DATES.append(_cursor)
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
    extra_dates = EXTENDED_DATES
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
        # Keep these entities present at the terminal cutoff without filling the
        # intervening history, so the same fixture exercises local gaps too.
        for day in (extra_dates[-1],):
            close = float(closes[-1])
            daily.append(
                (
                    isin,
                    isin,
                    day,
                    close,
                    close * 1.01,
                    close * 0.99,
                    close,
                    1_000.0,
                    datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS),
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
    growth_dates = [AS_OF, *FUTURE_DATES, *extra_dates]
    growth_closes = [100.0 * (1.2 ** min(index, 5)) for index in range(len(growth_dates))]
    for day, close in zip(growth_dates, growth_closes, strict=True):
        daily.append(
            (
                "FR0000000005",
                "FR0000000005",
                day,
                close,
                close * 1.01,
                close * 0.99,
                close,
                1_000.0,
                datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS),
                retrieved,
                "fixture-growth-snapshot",
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
    benchmark_last = benchmark_values[-1]
    for index, day in enumerate(extra_dates, start=1):
        close = benchmark_last * (1.001**index)
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
    german_values = [100, 101, 102, 103, 104, 105]
    for day, close in zip(all_dates, german_values, strict=True):
        series.append(
            (
                "german_equities",
                "german_equities:DE0000000001",
                "DE0000000001",
                None,
                day,
                close,
                close * 1.01,
                close * 0.99,
                close,
                1_000.0,
                datetime.combine(day + timedelta(days=1), datetime.min.time(), PARIS),
                retrieved,
                "fixture-german-checksum",
                "fixture-german-members",
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
    assert manifest["target_row_count"] == 8 * 45
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
    assert short == ("insufficient_future_history", None, 6)
    relative = _rows(
        output_dir,
        """SELECT target_status, unavailable_reason FROM read_parquet(?)
           WHERE entity_id='abc-bourse-manual:commodities:commodities:fixture-oil'
             AND target_family='return_rel' AND horizon=5""",
        [],
    )[0]
    assert relative == ("benchmark_not_defined", "no_defensible_v1_mapping_for_entity_family")
    german_relative = _rows(
        output_dir,
        """SELECT target_status, unavailable_reason FROM read_parquet(?)
           WHERE entity_id='abc-bourse-manual:german_equities:german_equities:DE0000000001'
             AND target_family='return_rel' AND horizon=5""",
        [],
    )[0]
    assert german_relative == (
        "benchmark_defined_but_unavailable",
        "mapped_benchmark_missing_at_cutoff",
    )


def test_terminal_cutoff_is_right_censored_and_kept_out_of_research_ready(
    panel: tuple[Path, Path], tmp_path: Path
) -> None:
    data_dir, _output_dir = panel
    output_dir = tmp_path / "terminal"
    build_target_snapshot(as_of_date=EXTENDED_DATES[-1], output_dir=output_dir, data_dir=data_dir)
    raw = _rows(
        output_dir,
        """SELECT target_status, is_end_of_sample_censored FROM read_parquet(?)
           WHERE entity_id='abc-bourse-manual:equity:FR0000000002'
             AND target_family='return_abs' AND horizon=20""",
        [],
    )[0]
    assert raw == ("right_censored_end_of_sample", True)
    with duckdb.connect(str(output_dir / "target_catalog.duckdb"), read_only=True) as connection:
        ready_count = connection.execute("SELECT count(*) FROM targets_research_ready").fetchone()[
            0
        ]
    assert ready_count == 0
    assert (output_dir / "targets.parquet").is_file()
    assert (output_dir / "targets_research_ready.parquet").is_file()


def test_extreme_rows_deduplicate_and_plausible_move_stays_research_ready(
    panel: tuple[Path, Path],
) -> None:
    _data_dir, output_dir = panel
    entity_id = "abc-bourse-manual:equity:FR0000000005"
    extreme_rows = _rows(
        output_dir,
        """SELECT horizon,target_value,candidate_value,research_ready,event_id,
                  extreme_classification FROM read_parquet(?)
           WHERE entity_id=? AND target_family='return_abs'
             AND candidate_value IS NOT NULL AND abs(candidate_value)>=0.9
           ORDER BY horizon""",
        [entity_id],
    )
    assert len(extreme_rows) == 5
    assert all(row[1] == pytest.approx(1.48832) for row in extreme_rows)
    assert all(row[3] is True for row in extreme_rows)
    assert len({row[4] for row in extreme_rows}) == 1
    assert {row[5] for row in extreme_rows} == {"plausible_market_move"}
    audit = json.loads((output_dir / "target_hardening_audit.json").read_text())
    assert audit["extreme_target_rows"] >= 10  # abs and relative labels share one price event
    assert audit["unique_events"] == 1
    assert audit["entities_with_extreme_targets"] == 1
    assert audit["events_classified_plausible"] == 1
    assert audit["research_ready_rules"]["winsorization"] is False


def test_split_like_event_is_diagnostic_and_excluded_from_research_ready() -> None:
    entity_id = "abc-bourse-manual:equity:FR0000000009"
    end_date = FUTURE_DATES[-1]
    target = {
        "entity_id": entity_id,
        "entity_family": "equity",
        "as_of_date": AS_OF,
        "target_id": "return_abs_h5",
        "target_family": "return_abs",
        "horizon": 5,
        "candidate_value": -0.9,
        "target_status": "available",
        "start_date": AS_OF,
        "target_end_date": end_date,
        "start_price": 100.0,
        "end_price": 10.0,
        "benchmark_id": None,
        "benchmark_start_date": None,
        "benchmark_end_date": None,
        "quality_status_at_cutoff": "approved",
        "future_quality_reason": None,
    }
    path = [
        {
            "session_date": day,
            "close": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": volume,
            "available_at": None,
            "retrieved_at": None,
        }
        for day, close, volume in zip(
            [AS_OF, *FUTURE_DATES],
            [100.0, 10.0, 10.1, 10.2, 10.3, 10.4],
            [100.0, 1_000.0, 100.0, 100.0, 100.0, 100.0],
            strict=True,
        )
    ]
    events, _links = _classify_extremes(
        [target], {(entity_id, AS_OF, end_date): path}
    )
    flags = set(events[0]["flags"])
    assert "likely_split_or_reverse_split" in flags
    assert not _is_research_ready("available", flags)
    assert not _is_research_ready("right_censored_end_of_sample", set())


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
    assert review[1] == pytest.approx(0.44)  # SPEC-006T retains review candidates.
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
    flags = _rows(
        output_dir,
        """SELECT entity_id, eligible_at_cutoff, target_observable,
                  future_quality_status, target_interpretable
           FROM read_parquet(?) WHERE target_family='direction_abs' AND horizon=5
           AND entity_id IN (?,?) ORDER BY entity_id""",
        ["abc-bourse-manual:equity:FR0000000003", "abc-bourse-manual:equity:FR0000000004"],
    )
    assert flags[0][1:] == (True, True, "review", True)
    assert flags[1][1:] == (True, True, "quarantined", False)
    rank_status = _rows(
        output_dir,
        """SELECT target_status, cohort_size FROM read_parquet(?)
           WHERE entity_id=? AND target_family='rank_pct' AND horizon=5""",
        ["abc-bourse-manual:equity:FR0000000003"],
    )[0]
    assert rank_status == ("future_quality_review", 3)
    good_cohort = _rows(
        output_dir,
        """SELECT DISTINCT cohort_size FROM read_parquet(?)
           WHERE entity_family='equity' AND target_family='rank_pct' AND horizon=5
             AND target_status='available'""",
        [],
    )
    assert good_cohort == [(3,)]


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
    cube_dir.mkdir()
    cutoff_dates = [AS_OF, EXTENDED_DATES[-6]]
    (cube_dir / "contract.json").write_text(
        json.dumps(
            {
                "contract_fingerprint": "fixture-cube-contract",
                "contract": {"quality_scope": "approved"},
            }
        )
    )
    entity_id = "abc-bourse-manual:equity:FR0000000005"
    for cutoff_date in cutoff_dates:
        partition = cube_dir / f"as_of_date={cutoff_date.isoformat()}"
        partition.mkdir()
        (partition / "manifest.json").write_text(
            json.dumps(
                {
                    "as_of_date": cutoff_date.isoformat(),
                    "run_id": f"fixture-cube-{cutoff_date.isoformat()}",
                    "contract_fingerprint": "fixture-cube-contract",
                }
            )
        )
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
    assert result["dates"] == [item.isoformat() for item in cutoff_dates]
    assert result["target_row_count"] == 90
    relative = _rows(
        target_set_dir / f"as_of_date={AS_OF.isoformat()}",
        """SELECT target_status, target_value, benchmark_id FROM read_parquet(?)
           WHERE target_family='return_rel' AND horizon=5""",
        [],
    )[0]
    assert relative[0] == "available"
    assert relative[1] is not None
    assert relative[2] == CAC_ID
    hardening = json.loads((target_set_dir / "target_hardening_audit.json").read_text())
    cohorts = {item["horizon"]: item for item in hardening["usable_cutoff_cohorts_by_horizon"]}
    assert cohorts[5]["last_usable_cutoff"] == cutoff_dates[-1].isoformat()
    assert cohorts[120]["last_usable_cutoff"] == AS_OF.isoformat()
    limits = {
        item["horizon"]: item["last_possible_weekly_cutoff"]
        for item in hardening["last_possible_weekly_cutoff_by_horizon"]
    }
    assert limits[5] > limits[120]
