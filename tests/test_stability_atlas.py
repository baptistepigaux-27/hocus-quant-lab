from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from hocus_quant.analysis.stability import (
    build_stability_atlas,
    calculate_maturity_ratio,
    calculate_retention,
    classify_stability,
    freeze_top_signals,
    signal_identity_id,
)


def _discovery_db(path: Path) -> Path:
    with duckdb.connect(str(path)) as db:
        db.execute(
            """CREATE TABLE signal_summary (
                feature_id VARCHAR, target_id VARCHAR, target_family VARCHAR,
                horizon INTEGER, scope VARCHAR, n_total INTEGER, cutoff_count INTEGER,
                spearman_ic_mean DOUBLE, ic_median DOUBLE, hit_rate DOUBLE,
                coverage DOUBLE, fdr_q_value DOUBLE, top_bottom_spread DOUBLE,
                monotonicity_spearman DOUBLE, feature_family VARCHAR,
                feature_source_series VARCHAR, feature_metric VARCHAR,
                feature_window INTEGER, target_formula VARCHAR, target_scale VARCHAR,
                status VARCHAR
            )"""
        )
        db.executemany(
            "INSERT INTO signal_summary VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "feature.a",
                    "target.return",
                    "return_abs",
                    20,
                    "equity",
                    1200,
                    20,
                    -0.2,
                    -0.18,
                    0.2,
                    0.9,
                    0.01,
                    -0.3,
                    -0.5,
                    "price",
                    "close",
                    "momentum",
                    20,
                    "future return",
                    "percent",
                    "eligible",
                ),
                (
                    "feature.b",
                    "target.return",
                    "return_abs",
                    20,
                    "equity",
                    1300,
                    22,
                    0.1,
                    0.09,
                    0.7,
                    0.95,
                    0.02,
                    0.15,
                    0.2,
                    "price",
                    "close",
                    "range",
                    30,
                    "future return",
                    "percent",
                    "eligible",
                ),
                (
                    "feature.c",
                    "target.risk",
                    "volatility",
                    60,
                    "equity_us",
                    1500,
                    27,
                    0.7,
                    0.69,
                    1.0,
                    0.99,
                    0.001,
                    0.8,
                    0.9,
                    "price",
                    "close",
                    "volatility",
                    60,
                    "future volatility",
                    "percent",
                    "eligible",
                ),
            ],
        )
    return path


def test_signal_identity_includes_relation_dimensions() -> None:
    identity = {
        "feature_id": "feature.a",
        "target_id": "target.a",
        "horizon": 20,
        "scope": "equity",
        "metric_definition": "spearman/v1",
    }
    signal_id = signal_identity_id(identity)
    assert signal_identity_id(dict(identity)) == signal_id
    for field, value in (
        ("feature_id", "feature.b"),
        ("target_id", "target.b"),
        ("horizon", 60),
        ("scope", "equity_us"),
        ("metric_definition", "pearson/v1"),
    ):
        assert signal_identity_id({**identity, field: value}) != signal_id


def test_signal_id_is_period_invariant() -> None:
    identity = {
        "feature_id": "feature.a",
        "target_id": "target.a",
        "horizon": 20,
        "scope": "equity",
        "metric_definition": "spearman/v1",
    }
    assert signal_identity_id({**identity, "period": "2024"}) == signal_identity_id(
        {**identity, "period": "2026"}
    )


def test_freeze_top_signals_uses_discovery_scope_and_rule(tmp_path: Path) -> None:
    database = _discovery_db(tmp_path / "signals.duckdb")
    frozen = freeze_top_signals(
        {"id": "2024", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        "equity",
        2,
        analysis_database=database,
        selection_rule_version="test/v1",
        return_target_families={"return_abs"},
    )
    assert [row["feature_id"] for row in frozen] == ["feature.a", "feature.b"]
    assert [row["discovery_rank"] for row in frozen] == [1, 2]
    assert all(row["selection_rule_version"] == "test/v1" for row in frozen)
    assert all(row["discovery_period_id"] == "2024" for row in frozen)
    replay = freeze_top_signals(
        {"id": "2024", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        "equity",
        2,
        analysis_database=database,
        selection_rule_version="test/v1",
        return_target_families={"return_abs"},
    )
    assert replay == frozen


def test_builder_rejects_discovery_validation_overlap_before_reading_data(tmp_path: Path) -> None:
    config_path = tmp_path / "periods.toml"
    config_path.write_text(
        """[discovery_period]
id = "discovery"
start_date = "2024-01-01"
end_date = "2024-12-31"
analysis_database = "missing.duckdb"

[[validation_periods]]
id = "validation"
start_date = "2024-12-01"
end_date = "2025-12-31"
feature_cube = "missing-features"
target_set = "missing-targets"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-overlapping"):
        build_stability_atlas(
            config_path=config_path,
            repo_root=tmp_path,
            output_dir=tmp_path / "output",
        )


def test_general_and_return_discovery_sets_remain_separate(tmp_path: Path) -> None:
    database = _discovery_db(tmp_path / "signals.duckdb")
    frozen = freeze_top_signals(
        {"id": "2024", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        "equity_us",
        1,
        analysis_database=database,
        selection_rule_version="test/v1",
    )
    assert len(frozen) == 1
    assert frozen[0]["feature_id"] == "feature.c"
    assert frozen[0]["selection_bucket"] == "general"


@pytest.mark.parametrize(
    ("discovery", "validation", "expected"),
    [
        (-0.2, -0.1, (True, 0.5, 0.5)),
        (-0.2, -0.4, (True, 2.0, 2.0)),
        (-0.2, 0.1, (False, -0.5, 0.5)),
    ],
)
def test_signed_and_absolute_retention(
    discovery: float, validation: float, expected: tuple[bool, float, float]
) -> None:
    assert calculate_retention(discovery, validation) == expected


def test_zero_discovery_ic_has_undefined_retention() -> None:
    assert calculate_retention(0.0, 0.3) == (None, None, None)


@pytest.mark.parametrize(
    ("mature", "theoretical", "expected"),
    [(2, 8, 0.25), (0, 8, 0.0), (0, 0, None)],
)
def test_target_maturity_ratio(mature: int, theoretical: int, expected: float | None) -> None:
    assert calculate_maturity_ratio(mature, theoretical) == expected


def test_maturity_ratio_rejects_impossible_cutoff_counts() -> None:
    with pytest.raises(ValueError):
        calculate_maturity_ratio(5, 4)


def test_unmature_signal_is_insufficient_even_if_sign_agrees() -> None:
    status = classify_stability(
        evaluated_cutoffs=2,
        mature_cutoffs=2,
        sign_retained=True,
        aligned_sign_rate=1.0,
        impact_retention=0.95,
        maturity_ratio=2 / 27,
    )
    assert status == "insufficient_validation"


def test_stability_classes_use_documented_independent_thresholds() -> None:
    common = {
        "evaluated_cutoffs": 20,
        "mature_cutoffs": 20,
        "aligned_sign_rate": 1.0,
        "maturity_ratio": 1.0,
    }
    assert classify_stability(**common, sign_retained=True, impact_retention=0.95) == "stable"
    assert classify_stability(**common, sign_retained=True, impact_retention=0.65) == "weakened"
    assert (
        classify_stability(**common, sign_retained=False, impact_retention=0.65) == "sign_reversed"
    )
    assert (
        classify_stability(
            **{**common, "aligned_sign_rate": 0.4},
            sign_retained=True,
            impact_retention=0.95,
        )
        == "unstable"
    )
