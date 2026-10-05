"""Freeze 2024 top features per lookback window and compare H5 IC signs in 2025."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from hocus_quant.features.registry import WINDOWS

ROOT = Path(__file__).resolve().parents[1]
TARGET = "future.direction_abs.h5.v1"
SCOPE = "equity"
SORT_COLUMNS = ["fdr_q_value", "abs_ic", "coverage", "cutoff_count", "feature_id", "target_id"]


def _read_summary(path: Path) -> pd.DataFrame:
    with duckdb.connect(str(path), read_only=True) as db:
        return db.execute(
            """SELECT feature_id, target_id, horizon, scope, target_family,
                      feature_window, feature_metric, feature_family, feature_source_series,
                      target_formula, target_scale, status, n_total, cutoff_count,
                      coverage, fdr_q_value, spearman_ic_mean
               FROM signal_summary WHERE scope=? AND target_id=? AND horizon=5""",
            [SCOPE, TARGET],
        ).fetchdf()


def _history_dates(path: Path) -> dict[str, Any]:
    with duckdb.connect(str(path), read_only=True) as db:
        row = db.execute(
            """SELECT min(as_of_date), max(as_of_date), count(DISTINCT as_of_date)
               FROM signal_ic_history WHERE scope=? AND target_id=?""",
            [SCOPE, TARGET],
        ).fetchone()
    if row is None or row[0] is None:
        raise ValueError(f"no H5 IC history in {path}")
    return {"first_cutoff": str(row[0]), "last_cutoff": str(row[1]), "cutoffs": int(row[2])}


def compare(*, discovery_db: Path, validation_db: Path, output: Path, top_n: int) -> None:
    if top_n < 1:
        raise ValueError("top_n must be positive")
    dates_2024 = _history_dates(discovery_db)
    dates_2025 = _history_dates(validation_db)
    if dates_2024["last_cutoff"] >= dates_2025["first_cutoff"]:
        raise ValueError("discovery and validation dates overlap")
    discovery = _read_summary(discovery_db)
    candidates = discovery.loc[
        (discovery.status == "eligible")
        & (discovery.n_total >= 1000)
        & (discovery.cutoff_count >= 13)
        & (discovery.coverage >= 0.60)
        & discovery.feature_window.notna()
        & np.isfinite(discovery.spearman_ic_mean)
    ].copy()
    candidates["feature_window"] = candidates.feature_window.astype(int)
    if candidates.duplicated(["feature_id", "target_id", "scope"]).any():
        raise ValueError("duplicate discovery identities")
    candidates["abs_ic"] = candidates.spearman_ic_mean.abs()
    ranked = candidates.sort_values(
        SORT_COLUMNS,
        ascending=[True, False, False, False, True, True],
        na_position="last",
        kind="mergesort",
    )
    frozen = ranked.groupby("feature_window", sort=True).head(top_n).copy()
    frozen["rank_within_window"] = frozen.groupby("feature_window").cumcount() + 1
    frozen = frozen.sort_values(["feature_window", "rank_within_window"])
    # Persist the complete selection before reading any validation metrics.
    output.mkdir(parents=True, exist_ok=True)
    frozen.to_parquet(output / "frozen_top100_by_feature_window.parquet", index=False)
    validation = _read_summary(validation_db)
    compared = frozen.merge(
        validation,
        on=["feature_id", "target_id", "scope"],
        how="left",
        suffixes=("_2024", "_2025"),
        validate="one_to_one",
    )
    for field in (
        "horizon",
        "target_family",
        "feature_window",
        "feature_metric",
        "feature_family",
        "feature_source_series",
        "target_formula",
        "target_scale",
    ):
        present = compared.spearman_ic_mean_2025.notna()
        if not compared.loc[present, f"{field}_2024"].equals(
            compared.loc[present, f"{field}_2025"]
        ):
            # Merged missing rows can promote integer columns to float; compare values.
            if (
                compared.loc[present, f"{field}_2024"].to_numpy()
                != compared.loc[present, f"{field}_2025"].to_numpy()
            ).any():
                raise ValueError(f"relation definition changed: {field}")
    compared = compared.rename(
        columns={
            "spearman_ic_mean_2024": "ic_2024",
            "spearman_ic_mean_2025": "ic_2025",
            "feature_window_2024": "feature_window",
        }
    )
    valid = np.isfinite(compared.ic_2025) & (compared.cutoff_count_2025 >= 4)
    nonzero = (compared.ic_2024.abs() > 1e-12) & (compared.ic_2025.abs() > 1e-12)
    compared["sign_status"] = np.select(
        [~valid, ~nonzero, compared.ic_2024 * compared.ic_2025 < 0],
        ["not_evaluable", "zero_or_negligible", "inverted"],
        default="retained",
    )
    compared["impact_retention"] = np.where(
        valid & nonzero,
        np.abs(compared.ic_2025 / compared.ic_2024),
        np.nan,
    )
    compared.to_parquet(output / "signal_comparison.parquet", index=False)
    compared.to_csv(output / "signal_comparison.csv", index=False)
    summary: list[dict[str, Any]] = []
    windows = sorted(set(WINDOWS) | set(candidates.feature_window.tolist()))
    for window in windows:
        rows = compared.loc[compared.feature_window == window]
        usable = rows.loc[rows.sign_status.isin(["inverted", "retained"])]
        reversed_n = int((usable.sign_status == "inverted").sum())
        summary.append(
            {
                "feature_window": window,
                "standard_window": window in WINDOWS,
                "eligible_2024": int((candidates.feature_window == window).sum()),
                "selected": len(rows),
                "sign_evaluable": len(usable),
                "inverted": reversed_n,
                "retained": len(usable) - reversed_n,
                "inverted_pct": 100 * reversed_n / len(usable) if len(usable) else None,
                "not_evaluable": int((rows.sign_status == "not_evaluable").sum()),
                "zero_or_negligible": int((rows.sign_status == "zero_or_negligible").sum()),
                "mean_ic_2024": float(rows.ic_2024.mean()) if len(rows) else None,
                "mean_ic_2025": float(rows.ic_2025.mean()) if len(rows) else None,
                "median_abs_ic_2024": float(rows.ic_2024.abs().median()) if len(rows) else None,
                "median_abs_ic_2025": float(rows.ic_2025.abs().median()) if len(rows) else None,
            }
        )
    pd.DataFrame(summary).to_csv(output / "window_summary.csv", index=False)
    audit = {
        "target_id": TARGET,
        "target_horizon": 5,
        "scope": SCOPE,
        "top_n_per_feature_window": top_n,
        "selection_rule": "q_abs_ic_coverage_cutoff_v1",
        "discovery_criteria": {"minimum_n": 1000, "minimum_cutoffs": 13, "coverage": 0.6},
        "validation_minimum_cutoffs": 4,
        "discovery_database": str(discovery_db),
        "validation_database": str(validation_db),
        "discovery_dates": dates_2024,
        "validation_dates": dates_2025,
        "frozen_before_validation_metrics_read": True,
        "windows": summary,
        "notes": [
            "Windows describe historical feature lookbacks, not the future H5 target.",
            "Selection uses all eligible 2024 features, not the previous top 500 subset.",
            "Validation never reselects the cohort. Existing research-ready filters are retained.",
            "Fewer than top_n candidates means all candidates, without filling from other windows.",
            "Inversion means opposite signs of the mean cutoff Spearman IC, not asset returns.",
            "Tiny ICs, correlated features and descriptive q-values remain limitations.",
        ],
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o755)
    for path in output.iterdir():
        if path.is_file():
            path.chmod(0o644)
    print(pd.DataFrame(summary).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--discovery-db",
        type=Path,
        default=ROOT / "data/analysis/spec006-weekly-demo/signals.duckdb",
    )
    parser.add_argument(
        "--validation-db",
        type=Path,
        default=ROOT / "data/analysis/spec006-2025-equity-scan/signals.duckdb",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/analysis/spec006r-h5-top100-by-window"
    )
    parser.add_argument("--top-n", type=int, default=100)
    args = parser.parse_args()
    compare(
        discovery_db=args.discovery_db,
        validation_db=args.validation_db,
        output=args.output,
        top_n=args.top_n,
    )


if __name__ == "__main__":
    main()
