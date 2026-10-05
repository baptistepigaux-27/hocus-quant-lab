"""Compare 2025/2026 H5 IC signs for the 2024 top features per lookback window."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from hocus_quant.analysis.signals import analyze_cutoff
from hocus_quant.features.registry import WINDOWS

ROOT = Path(__file__).resolve().parents[1]
TARGET = "future.direction_abs.h5.v1"


def compare(
    *, frozen_comparison: Path, feature_root: Path, target_root: Path, output: Path
) -> None:
    frozen = pd.read_parquet(frozen_comparison)
    if frozen.empty or frozen.duplicated(["feature_id", "target_id", "scope"]).any():
        raise ValueError("empty or duplicate frozen selection")
    if not (
        (frozen.target_id == TARGET) & (frozen.scope == "equity") & (frozen.horizon_2024 == 5)
    ).all():
        raise ValueError("expected frozen equity direction H5 relations")
    output.mkdir(parents=True, exist_ok=True)
    frozen.to_parquet(output / "frozen_2024_selection.parquet", index=False)
    feature_ids = frozen[["feature_id"]].drop_duplicates()
    history: list[dict[str, Any]] = []
    partition_dates: list[str] = []
    with duckdb.connect() as db:
        db.register("selected_features", feature_ids)
        for feature_path in sorted(feature_root.glob("as_of_date=*/features.parquet")):
            day = feature_path.parent.name.removeprefix("as_of_date=")
            if not date(2026, 4, 5) <= date.fromisoformat(day) <= date(2026, 10, 4):
                continue
            target_path = target_root / feature_path.parent.name / "targets_research_ready.parquet"
            if not target_path.is_file():
                raise FileNotFoundError(target_path)
            partition_dates.append(day)
            features = db.execute(
                """SELECT entity_id, entity_family, as_of_date, feature_id,
                          feature_value, feature_status
                   FROM read_parquet(?) WHERE entity_family='equity'
                     AND feature_id IN (SELECT feature_id FROM selected_features)""",
                [str(feature_path)],
            ).fetchdf()
            targets = db.execute(
                """SELECT entity_id, entity_family, as_of_date, target_id, target_family,
                          horizon, target_value, target_status, research_ready
                   FROM read_parquet(?) WHERE entity_family='equity' AND target_id=?""",
                [str(target_path), TARGET],
            ).fetchdf()
            pairs, _ = analyze_cutoff(features, targets, minimum_n=30)
            kept = [row for row in pairs if row["scope"] == "equity"]
            history.extend(kept)
            print(f"2026 {day}: {len(kept)} relations evaluated", flush=True)
    if not history:
        raise ValueError("no evaluable 2026 ICs")
    history_frame = pd.DataFrame(history)
    if history_frame.duplicated(["feature_id", "target_id", "scope", "as_of_date"]).any():
        raise ValueError("duplicate 2026 cutoff measurements")
    history_frame.to_parquet(output / "ic_history_2026.parquet", index=False)
    annual = history_frame.groupby(["feature_id", "target_id", "scope"], as_index=False).agg(
        ic_2026=("spearman_ic", "mean"),
        cutoffs_2026=("spearman_ic", "size"),
        first_cutoff_2026=("as_of_date", "min"),
        last_cutoff_2026=("as_of_date", "max"),
        observations_2026=("n", "sum"),
    )
    compared = frozen.merge(
        annual, on=["feature_id", "target_id", "scope"], how="left", validate="one_to_one"
    )
    usable = (
        np.isfinite(compared.ic_2025)
        & np.isfinite(compared.ic_2026)
        & (compared.cutoff_count_2025 >= 4)
        & (compared.cutoffs_2026 >= 4)
    )
    nonzero = (compared.ic_2025.abs() > 1e-12) & (compared.ic_2026.abs() > 1e-12)
    compared["sign_status_2025_2026"] = np.select(
        [~usable, ~nonzero, compared.ic_2025 * compared.ic_2026 < 0],
        ["not_evaluable", "zero_or_negligible", "inverted"],
        default="retained",
    )
    compared.to_parquet(output / "signal_comparison.parquet", index=False)
    compared.to_csv(output / "signal_comparison.csv", index=False)
    summary: list[dict[str, Any]] = []
    for window in sorted(set(WINDOWS) | set(frozen.feature_window.tolist())):
        rows = compared.loc[compared.feature_window == window]
        valid = rows.loc[rows.sign_status_2025_2026.isin(["inverted", "retained"])]
        inverted = int((valid.sign_status_2025_2026 == "inverted").sum())
        summary.append(
            {
                "feature_window": int(window),
                "standard_window": window in WINDOWS,
                "selected_2024": len(rows),
                "evaluable": len(valid),
                "inverted": inverted,
                "retained": len(valid) - inverted,
                "inverted_pct": 100 * inverted / len(valid) if len(valid) else None,
                "not_evaluable": int((rows.sign_status_2025_2026 == "not_evaluable").sum()),
                "zero_or_negligible": int(
                    (rows.sign_status_2025_2026 == "zero_or_negligible").sum()
                ),
                "median_cutoffs_2025": float(rows.cutoff_count_2025.median())
                if len(rows)
                else None,
                "median_cutoffs_2026": float(rows.cutoffs_2026.median()) if len(rows) else None,
                "median_abs_ic_2025": float(rows.ic_2025.abs().median()) if len(rows) else None,
                "median_abs_ic_2026": float(rows.ic_2026.abs().median()) if len(rows) else None,
            }
        )
    pd.DataFrame(summary).to_csv(output / "window_summary.csv", index=False)
    audit = {
        "target_id": TARGET,
        "scope": "equity",
        "selection_year": 2024,
        "comparison_years": [2025, 2026],
        "reselected": False,
        "source_frozen_comparison": str(frozen_comparison),
        "source_checksum": hashlib.sha256(frozen_comparison.read_bytes()).hexdigest(),
        "feature_cube_2026": str(feature_root),
        "target_set_2026": str(target_root),
        "configured_period_2026": ["2026-04-05", "2026-10-04"],
        "available_partitions_2026": partition_dates,
        "evaluated_start_2026": str(history_frame.as_of_date.min()),
        "evaluated_end_2026": str(history_frame.as_of_date.max()),
        "validation_minimum_n": 30,
        "validation_minimum_cutoffs": 4,
        "windows": summary,
        "notes": [
            "Historical feature windows vary; the future direction target remains H5.",
            "2025 ICs use the existing full-period scan; 2026 uses already mature targets only.",
            "Research-ready filters are retained, including the future quality filter.",
            "Inversion compares signs of mean cutoff ICs, not signs of individual asset returns.",
            "Correlated features, weak ICs and reconstructed universes remain limitations.",
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
        "--frozen-comparison",
        type=Path,
        default=ROOT / "data/analysis/spec006r-h5-top100-by-window/signal_comparison.parquet",
    )
    parser.add_argument(
        "--feature-root", type=Path, default=ROOT / "data/feature_cube/spec006-2026-matched"
    )
    parser.add_argument(
        "--target-root", type=Path, default=ROOT / "data/targets/spec006-2026-matched"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/analysis/spec006r-h5-top100-by-window-2025-2026"
    )
    args = parser.parse_args()
    compare(
        frozen_comparison=args.frozen_comparison,
        feature_root=args.feature_root,
        target_root=args.target_root,
        output=args.output,
    )


if __name__ == "__main__":
    main()
