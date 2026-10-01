"""Evaluate a frozen set of signal pairs on later date windows."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from hocus_quant.analysis.signals import analyze_cutoff


def _read_ids(path: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        baselines = list(csv.DictReader(handle))
    if len(baselines) != 100:
        raise ValueError(f"expected 100 frozen signals, got {len(baselines)}")
    features = sorted({row["feature_id"] for row in baselines})
    targets = sorted({row["target_id"] for row in baselines})
    return baselines, features, targets


def _read_partition(path: Path, ids: list[str], id_column: str, columns: str) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in ids)
    query = f"SELECT {columns} FROM read_parquet(?) WHERE {id_column} IN ({placeholders})"
    return duckdb.execute(query, [str(path), *ids]).df()


def compare_period(
    *,
    baseline_path: Path,
    feature_cube: Path,
    target_set: Path,
    output_dir: Path,
    label: str,
) -> dict[str, Any]:
    baselines, feature_ids, target_ids = _read_ids(baseline_path)
    baseline_by_pair = {
        (row["scope"], row["feature_id"], row["target_id"]): float(row["ic_mean_2024"])
        for row in baselines
    }
    feature_sql = "entity_id, entity_family, as_of_date, feature_id, feature_value, feature_status"
    target_sql = (
        "entity_id, entity_family, as_of_date, target_id, target_family, horizon, "
        "target_value, target_status, research_ready"
    )
    daily_rows: list[dict[str, Any]] = []
    partitions = sorted(feature_cube.glob("as_of_date=*/features.parquet"))
    if not partitions:
        raise FileNotFoundError(f"no feature partitions in {feature_cube}")
    for feature_path in partitions:
        partition = feature_path.parent.name
        date_text = partition.split("=", maxsplit=1)[1]
        target_path = target_set / partition / "targets_research_ready.parquet"
        if not target_path.is_file():
            continue
        features = _read_partition(feature_path, feature_ids, "feature_id", feature_sql)
        targets = _read_partition(target_path, target_ids, "target_id", target_sql)
        pairs, _ = analyze_cutoff(features, targets, minimum_n=30)
        for row in pairs:
            pair = (row["scope"], row["feature_id"], row["target_id"])
            if pair not in baseline_by_pair:
                continue
            daily_rows.append(
                {
                    "period": label,
                    "as_of_date": date_text,
                    "scope": pair[0],
                    "feature_id": pair[1],
                    "target_id": pair[2],
                    "baseline_ic_2024": baseline_by_pair[pair],
                    "spearman_ic": row["spearman_ic"],
                    "n": row["n"],
                    "coverage": row["coverage"],
                }
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_path = output_dir / f"signal_ic_{label}.csv"
    summary_path = output_dir / f"signal_stability_{label}.csv"
    daily_frame = pd.DataFrame(daily_rows)
    daily_frame.to_csv(daily_path, index=False)
    if daily_frame.empty:
        summary_frame = pd.DataFrame()
    else:
        summary_frame = (
            daily_frame.groupby(["scope", "feature_id", "target_id"], sort=True)
            .agg(
                cutoff_count=("spearman_ic", "count"),
                ic_mean=("spearman_ic", "mean"),
                ic_median=("spearman_ic", "median"),
                ic_std=("spearman_ic", "std"),
                positive_cutoff_rate=("spearman_ic", lambda values: float((values > 0).mean())),
                aligned_sign_rate=(
                    "spearman_ic",
                    lambda values: float(
                        (np.sign(values.to_numpy())
                         == np.sign(daily_frame.loc[values.index, "baseline_ic_2024"].iloc[0]))
                        .mean()
                    ),
                ),
                mean_n=("n", "mean"),
                mean_coverage=("coverage", "mean"),
            )
            .reset_index()
        )
        baseline_frame = pd.DataFrame(baselines)[
            [
                "scope",
                "feature_id",
                "target_id",
                "target_family",
                "horizon",
                "ic_mean_2024",
                "fdr_q_2024",
            ]
        ]
        baseline_frame["ic_mean_2024"] = pd.to_numeric(
            baseline_frame["ic_mean_2024"], errors="raise"
        )
        baseline_frame["fdr_q_2024"] = pd.to_numeric(
            baseline_frame["fdr_q_2024"], errors="coerce"
        )
        summary_frame = summary_frame.merge(
            baseline_frame, on=["scope", "feature_id", "target_id"], how="left"
        )
        summary_frame["sign_retained"] = (
            np.sign(summary_frame["ic_mean"])
            == np.sign(summary_frame["ic_mean_2024"])
        )
        summary_frame["ic_delta_vs_2024"] = (
            summary_frame["ic_mean"] - summary_frame["ic_mean_2024"]
        )
        summary_frame["abs_ic_retention"] = np.where(
            summary_frame["ic_mean_2024"].abs() > 1e-12,
            summary_frame["ic_mean"].abs() / summary_frame["ic_mean_2024"].abs(),
            np.nan,
        )
        summary_frame.to_csv(summary_path, index=False)
    same_sign = int(summary_frame["sign_retained"].sum()) if not summary_frame.empty else 0
    report = {
        "period": label,
        "feature_cube": str(feature_cube),
        "target_set": str(target_set),
        "feature_cutoffs": len(partitions),
        "signals_selected": len(baselines),
        "signals_with_outcomes": len(summary_frame),
        "same_sign_count": same_sign,
        "same_sign_rate": same_sign / len(summary_frame) if len(summary_frame) else None,
        "median_absolute_ic_retention": (
            float(summary_frame["abs_ic_retention"].median())
            if not summary_frame.empty
            else None
        ),
        "median_aligned_sign_rate": (
            float(summary_frame["aligned_sign_rate"].median())
            if not summary_frame.empty
            else None
        ),
        "daily_output": str(daily_path),
        "summary_output": str(summary_path),
    }
    (output_dir / f"signal_stability_{label}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--feature-cube", type=Path, required=True)
    parser.add_argument("--target-set", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            compare_period(
                baseline_path=args.baseline,
                feature_cube=args.feature_cube,
                target_set=args.target_set,
                output_dir=args.output,
                label=args.label,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
