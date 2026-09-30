from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from hocus_quant.analysis.signals import (
    _materialize_pooled_panels,
    _pooled_spearman_rows,
    _summarize_files,
    _summary_rows,
    analyze_cutoff,
)


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    n = 40
    x = np.arange(n, dtype=float)
    features = pd.DataFrame(
        {
            "entity_id": [f"e{i}" for i in range(n)] * 2,
            "entity_family": ["equity"] * n + ["crypto"] * n,
            "as_of_date": [pd.Timestamp("2025-01-03").date()] * (n * 2),
            "feature_id": ["x.linear"] * n + ["x.linear"] * n,
            "feature_value": np.r_[x, x],
            "feature_status": ["available"] * (n * 2),
        }
    )
    targets = pd.DataFrame(
        {
            "entity_id": [f"e{i}" for i in range(n)] * 2,
            "entity_family": ["equity"] * n + ["crypto"] * n,
            "as_of_date": [pd.Timestamp("2025-01-03").date()] * (n * 2),
            "target_id": ["y.forward"] * (n * 2),
            "target_family": ["return_rel"] * (n * 2),
            "horizon": [20] * (n * 2),
            "target_value": np.r_[x, x[::-1]],
            "target_status": ["available"] * (n * 2),
            "research_ready": [True] * (n * 2),
        }
    )
    # Prefix IDs by family so the two synthetic universes remain disjoint.
    features["entity_id"] = [
        f"{family}:{entity}"
        for family, entity in zip(features.entity_family, features.entity_id, strict=True)
    ]
    targets["entity_id"] = [
        f"{family}:{entity}"
        for family, entity in zip(targets.entity_family, targets.entity_id, strict=True)
    ]
    return features, targets


def test_alignment_cross_sectional_metrics_and_family_scopes() -> None:
    features, targets = _fixture()
    pairs, deciles = analyze_cutoff(features, targets, minimum_n=20)
    global_row = next(row for row in pairs if row["scope"] == "global")
    equity_row = next(row for row in pairs if row["scope"] == "equity")
    assert global_row["n"] == 80
    assert equity_row["n"] == 40
    assert np.isclose(equity_row["pearson_ic"], 1.0)
    assert np.isclose(equity_row["spearman_ic"], 1.0)
    equity_deciles = [row for row in deciles if row["scope"] == "equity"]
    assert len(equity_deciles) == 10
    assert [row["decile"] for row in equity_deciles] == list(range(1, 11))


def test_unavailable_target_rows_are_excluded_and_fdr_is_repeatable() -> None:
    features, targets = _fixture()
    targets.loc[0, "research_ready"] = False
    features.loc[1, "feature_status"] = "unavailable"
    pairs, deciles = analyze_cutoff(features, targets, minimum_n=20)
    assert next(row for row in pairs if row["scope"] == "equity")["n"] == 38
    first, _, _, _ = _summary_rows(pairs * 13, deciles * 13, minimum_cutoffs=1, fdr_alpha=0.25)
    second, _, _, _ = _summary_rows(pairs * 13, deciles * 13, minimum_cutoffs=1, fdr_alpha=0.25)
    first_q = [(row["feature_id"], row["scope"], row["fdr_q_value"]) for row in first]
    second_q = [(row["feature_id"], row["scope"], row["fdr_q_value"]) for row in second]
    assert first_q == second_q


def test_alignment_does_not_join_a_future_cutoff() -> None:
    features, targets = _fixture()
    targets["as_of_date"] = pd.Timestamp("2025-01-10").date()
    pairs, deciles = analyze_cutoff(features, targets, minimum_n=3)
    assert pairs == []
    assert deciles == []


def test_pooled_spearman_ranks_all_pairwise_complete_entity_cutoffs(tmp_path) -> None:
    x_path = tmp_path / "x.parquet"
    y_path = tmp_path / "y.parquet"
    x = pd.DataFrame(
        {
            "entity_id": ["a", "b", "c", "a", "b", "c"],
            "entity_family": ["equity"] * 6,
            "as_of_date": ["2025-01-03"] * 3 + ["2025-01-10"] * 3,
            "x.linear": [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        }
    )
    y = x[["entity_id", "entity_family", "as_of_date"]].copy()
    y["y.forward"] = [1.0, 2.0, 3.0, 3.0, 2.0, 1.0]
    x.to_parquet(x_path, index=False)
    y.to_parquet(y_path, index=False)
    rows = _pooled_spearman_rows([x_path], [y_path], minimum_n=3)
    global_row = next(row for row in rows if row["scope"] == "global")
    assert global_row["n"] == 6
    assert np.isclose(global_row["spearman_pooled"], 1.0)


def test_pooled_panels_keep_empty_cutoffs_queryable(tmp_path) -> None:
    cube_dir = tmp_path / "cube"
    target_dir = tmp_path / "targets"
    partition = "as_of_date=2025-01-03"
    feature_path = cube_dir / partition / "features.parquet"
    target_path = target_dir / partition / "targets_research_ready.parquet"
    feature_path.parent.mkdir(parents=True)
    target_path.parent.mkdir(parents=True)
    pq.write_table(
        pa.Table.from_pylist(
            [],
            schema=pa.schema(
                [
                    ("entity_id", pa.string()),
                    ("entity_family", pa.string()),
                    ("as_of_date", pa.string()),
                    ("feature_id", pa.string()),
                    ("feature_value", pa.float64()),
                    ("feature_status", pa.string()),
                ]
            ),
        ),
        feature_path,
    )
    pq.write_table(
        pa.Table.from_pylist(
            [],
            schema=pa.schema(
                [
                    ("entity_id", pa.string()),
                    ("entity_family", pa.string()),
                    ("as_of_date", pa.string()),
                    ("target_id", pa.string()),
                    ("target_value", pa.float64()),
                    ("research_ready", pa.bool_()),
                    ("target_status", pa.string()),
                ]
            ),
        ),
        target_path,
    )
    x_files, y_files = _materialize_pooled_panels(
        feature_cube_dir=cube_dir,
        target_set_dir=target_dir,
        panel_dir=tmp_path / "panels",
    )
    assert len(x_files) == len(y_files) == 1
    assert pd.read_parquet(x_files[0]).columns.tolist() == [
        "entity_id",
        "entity_family",
        "as_of_date",
    ]
    assert pd.read_parquet(y_files[0]).columns.tolist() == [
        "entity_id",
        "entity_family",
        "as_of_date",
    ]


def test_disk_aggregation_builds_pooled_pearson_history_and_periods(tmp_path) -> None:
    features, targets = _fixture()
    pair_files = []
    decile_files = []
    x_files = []
    y_files = []
    baseline_feature_values = features["feature_value"].copy()
    for week in range(3):
        features["as_of_date"] = pd.Timestamp(f"2025-01-{3 + week * 7:02d}").date()
        targets["as_of_date"] = features["as_of_date"].iloc[0]
        if week == 1:
            equity_rows = features["entity_family"] == "equity"
            features.loc[equity_rows, "feature_value"] = features.loc[
                equity_rows, "feature_value"
            ].to_numpy()[::-1]
        pairs, deciles = analyze_cutoff(features, targets, minimum_n=20)
        pair_path = tmp_path / f"pairs-{week}.parquet"
        decile_path = tmp_path / f"deciles-{week}.parquet"
        pq.write_table(pa.Table.from_pylist(pairs), pair_path)
        pq.write_table(pa.Table.from_pylist(deciles), decile_path)
        pair_files.append(pair_path)
        decile_files.append(decile_path)
        features["feature_value"] = baseline_feature_values
        keys = ["entity_id", "entity_family", "as_of_date"]
        x_panel = features.pivot(
            index=keys, columns="feature_id", values="feature_value"
        ).reset_index()
        y_panel = targets.pivot(
            index=keys, columns="target_id", values="target_value"
        ).reset_index()
        x_path, y_path = tmp_path / f"x-{week}.parquet", tmp_path / f"y-{week}.parquet"
        x_panel.to_parquet(x_path, index=False)
        y_panel.to_parquet(y_path, index=False)
        x_files.append(x_path)
        y_files.append(y_path)
    output_dir = tmp_path / "result"
    output_dir.mkdir()
    pooled_path = output_dir / "signal_pooled_spearman.parquet"
    pq.write_table(
        pa.Table.from_pylist(_pooled_spearman_rows(x_files, y_files, minimum_n=20)),
        pooled_path,
    )
    counts = _summarize_files(
        pair_files,
        decile_files,
        output_dir=output_dir,
        minimum_cutoffs=3,
        fdr_alpha=0.25,
        pooled_spearman_path=pooled_path,
    )
    assert counts["history_rows"] == len(pq.read_table(pair_files[0])) * 3
    summary = pq.read_table(tmp_path / "result" / "signal_summary.parquet").to_pylist()
    equity = next(row for row in summary if row["scope"] == "equity")
    global_row = next(row for row in summary if row["scope"] == "global")
    assert equity["pearson_pooled"] < 1.0
    assert np.isclose(equity["spearman_pooled"], 1.0)
    assert np.isclose(equity["coverage"], 1.0)
    assert equity["cutoff_count"] == 3
    assert np.isfinite(equity["p_value_descriptive"])
    assert np.isfinite(equity["fdr_q_value"])
    assert np.isfinite(global_row["fdr_q_value"])
    periods = pq.read_table(tmp_path / "result" / "signal_period_stability.parquet").to_pylist()
    assert any(
        row["scope"] == "equity" and row["status"] == "insufficient_period_n" for row in periods
    )


def test_empty_scan_still_exposes_queryable_duckdb_views(tmp_path) -> None:
    import duckdb

    _summarize_files([], [], output_dir=tmp_path, minimum_cutoffs=13, fdr_alpha=0.25)
    with duckdb.connect(str(tmp_path / "signals.duckdb"), read_only=True) as db:
        result = db.execute(
            "SELECT count(*), count(DISTINCT target_family), count(feature_family) "
            "FROM signal_summary"
        ).fetchone()
    assert result == (0, 0, 0)
