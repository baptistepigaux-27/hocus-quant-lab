"""Pointwise block-bootstrap intervals for frozen H5 mean ICs in 2025/2026."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt
import pandas as pd

from hocus_quant.features.registry import WINDOWS

ROOT = Path(__file__).resolve().parents[1]


def _draw_means(
    values: npt.NDArray[np.float64], *, block_length: int, replicates: int, seed: int
) -> npt.NDArray[np.float64]:
    """Circular blocks, shared date draws across all columns/features."""
    n = len(values)
    if not 1 <= block_length < n or not np.isfinite(values).all():
        raise ValueError("expected finite IC panel and a block length smaller than sample")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replicates, (n + block_length - 1) // block_length))
    indices = ((starts[:, :, None] + np.arange(block_length)) % n).reshape(replicates, -1)
    indices = indices[:, :n]
    # Counts give the same mean as materializing a B x T x feature array.
    counts = np.zeros((replicates, n), dtype=np.float64)
    np.add.at(counts, (np.arange(replicates)[:, None], indices), 1)
    return np.asarray((counts / n) @ values, dtype=np.float64)


def run(
    *,
    comparison_dir: Path,
    history_2025: Path,
    output: Path,
    replicates: int,
    seed: int,
    block_lengths: list[int],
) -> None:
    if replicates < 1000 or not block_lengths or len(set(block_lengths)) != len(block_lengths):
        raise ValueError("use at least 1000 replicates and distinct block lengths")
    source = comparison_dir / "signal_comparison.parquet"
    selected = pd.read_parquet(source).sort_values(["feature_window", "rank_within_window"])
    if not (
        (selected.target_id == "future.direction_abs.h5.v1") & (selected.scope == "equity")
    ).all():
        raise ValueError("expected frozen equity direction H5 cohort")
    if selected.duplicated("feature_id").any():
        raise ValueError("duplicate selected feature identities")
    with duckdb.connect() as db:
        db.register("selected", selected[["feature_id", "target_id", "scope"]])
        h25 = db.execute(
            """SELECT h.feature_id,h.as_of_date,h.spearman_ic
               FROM read_parquet(?) h JOIN selected USING(feature_id,target_id,scope)""",
            [str(history_2025)],
        ).fetchdf()
    h26 = pd.read_parquet(comparison_dir / "ic_history_2026.parquet")
    panels = {
        year: history.pivot(index="as_of_date", columns="feature_id", values="spearman_ic")
        .sort_index()
        .reindex(columns=selected.feature_id)
        for year, history in ((2025, h25), (2026, h26))
    }
    for year, panel in panels.items():
        if panel.isna().any().any():
            raise ValueError(
                f"incomplete weekly IC panel in {year}; missingness needs explicit handling"
            )
        if not np.allclose(
            panel.mean().to_numpy(), selected[f"ic_{year}"].to_numpy(), rtol=1e-10, atol=1e-12
        ):
            raise ValueError(f"weekly IC means differ from reference in {year}")
    output.mkdir(parents=True, exist_ok=True)
    intervals: list[pd.DataFrame] = []
    comparisons: list[pd.DataFrame] = []
    for block in block_lengths:
        draws: dict[int, npt.NDArray[np.float64]] = {}
        pair = selected[
            [
                "feature_id",
                "target_id",
                "feature_window",
                "rank_within_window",
                "ic_2024",
                "ic_2025",
                "ic_2026",
            ]
        ].copy()
        pair["block_length"] = block
        for year, panel in panels.items():
            values = panel.to_numpy(dtype=np.float64)
            draws[year] = _draw_means(
                values, block_length=block, replicates=replicates, seed=seed + year * 100 + block
            )
            mean = values.mean(axis=0)
            sign = np.sign(mean)
            quantiles = np.quantile(draws[year], [0.025, 0.05, 0.10, 0.90, 0.95, 0.975], axis=0)
            confidence = selected[
                ["feature_id", "target_id", "feature_window", "rank_within_window"]
            ].copy()
            confidence["year"] = year
            confidence["block_length"] = block
            confidence["cutoffs"] = len(panel)
            confidence["ic_mean"] = mean
            confidence["ci90_lower"] = quantiles[1]
            confidence["ci90_upper"] = quantiles[4]
            confidence["ci95_lower"] = quantiles[0]
            confidence["ci95_upper"] = quantiles[5]
            confidence["one_sided90_observed_sign_bound"] = np.where(
                sign > 0, quantiles[2], quantiles[3]
            )
            confidence["bootstrap_observed_sign_support"] = (draws[year] * sign > 0).mean(axis=0)
            confidence["observed_sign_support_gt90"] = (
                confidence.bootstrap_observed_sign_support > 0.90
            )
            confidence["ci90_excludes_zero"] = (quantiles[1] > 0) | (quantiles[4] < 0)
            confidence["ci95_excludes_zero"] = (quantiles[0] > 0) | (quantiles[5] < 0)
            confidence["bootstrap_2024_sign_support"] = (
                draws[year] * np.sign(selected.ic_2024.to_numpy()) > 0
            ).mean(axis=0)
            intervals.append(confidence)
            for name in (
                "bootstrap_observed_sign_support",
                "observed_sign_support_gt90",
                "ci90_excludes_zero",
                "ci95_excludes_zero",
                "ci90_lower",
                "ci90_upper",
                "ci95_lower",
                "ci95_upper",
            ):
                pair[f"{name}_{year}"] = confidence[name].to_numpy()
        pair["same_observed_sign_2025_2026"] = pair.ic_2025 * pair.ic_2026 > 0
        pair["bootstrap_same_sign_support_2025_2026"] = (draws[2025] * draws[2026] > 0).mean(axis=0)
        pair["bootstrap_2025_sign_support_in_2026"] = (
            draws[2026] * np.sign(pair.ic_2025.to_numpy()) > 0
        ).mean(axis=0)
        pair["same_sign_supported_gt90_each_year"] = (
            pair.same_observed_sign_2025_2026
            & pair.observed_sign_support_gt90_2025
            & pair.observed_sign_support_gt90_2026
        )
        pair["same_sign_ci90_excludes_zero_both_years"] = (
            pair.same_observed_sign_2025_2026
            & pair.ci90_excludes_zero_2025
            & pair.ci90_excludes_zero_2026
        )
        comparisons.append(pair)
        print(f"Completed blocks={block}, B={replicates}", flush=True)
    interval_frame = pd.concat(intervals, ignore_index=True)
    pairs_frame = pd.concat(comparisons, ignore_index=True)
    robust = pairs_frame.groupby("feature_id").agg(
        support_gt90_each_year_all_block_lengths=("same_sign_supported_gt90_each_year", "all"),
        ci90_excludes_zero_both_years_all_block_lengths=(
            "same_sign_ci90_excludes_zero_both_years",
            "all",
        ),
        joint_same_sign_support_gt90_all_block_lengths=(
            "bootstrap_same_sign_support_2025_2026",
            lambda s: bool((s > 0.90).all()),
        ),
        min_joint_same_sign_support=("bootstrap_same_sign_support_2025_2026", "min"),
        min_observed_sign_support_2025=("bootstrap_observed_sign_support_2025", "min"),
        min_observed_sign_support_2026=("bootstrap_observed_sign_support_2026", "min"),
    )
    pairs_frame = pairs_frame.merge(robust, on="feature_id", validate="many_to_one")
    reference_block = 4 if 4 in block_lengths else block_lengths[0]
    candidates = pairs_frame.loc[
        (pairs_frame.block_length == reference_block)
        & pairs_frame.joint_same_sign_support_gt90_all_block_lengths
    ].sort_values(["min_joint_same_sign_support", "feature_id"], ascending=[False, True])
    candidates.to_csv(output / "candidates_joint_sign_support_gt90.csv", index=False)
    summary: list[dict[str, Any]] = []
    for (block, window), group in pairs_frame.groupby(["block_length", "feature_window"]):
        summary.append(
            {
                "block_length": int(block),
                "feature_window": int(window),
                "standard_window": window in WINDOWS,
                "relations": len(group),
                "sign_gt90_2025": int(group.observed_sign_support_gt90_2025.sum()),
                "sign_gt90_2026": int(group.observed_sign_support_gt90_2026.sum()),
                "same_sign_supported_gt90_each_year": int(
                    group.same_sign_supported_gt90_each_year.sum()
                ),
                "joint_same_sign_support_gt90": int(
                    (group.bootstrap_same_sign_support_2025_2026 > 0.90).sum()
                ),
                "ci90_excludes_zero_2025": int(group.ci90_excludes_zero_2025.sum()),
                "ci90_excludes_zero_2026": int(group.ci90_excludes_zero_2026.sum()),
                "same_sign_ci90_excludes_zero_both_years": int(
                    group.same_sign_ci90_excludes_zero_both_years.sum()
                ),
                "support_gt90_each_year_all_block_lengths": int(
                    group.support_gt90_each_year_all_block_lengths.sum()
                ),
                "ci90_excludes_zero_both_years_all_block_lengths": int(
                    group.ci90_excludes_zero_both_years_all_block_lengths.sum()
                ),
                "joint_same_sign_support_gt90_all_block_lengths": int(
                    group.joint_same_sign_support_gt90_all_block_lengths.sum()
                ),
            }
        )
    for filename, frame in (
        ("ic_intervals", interval_frame),
        ("sign_comparison", pairs_frame),
        ("window_summary", pd.DataFrame(summary)),
    ):
        frame.to_parquet(output / f"{filename}.parquet", index=False)
        frame.to_csv(output / f"{filename}.csv", index=False)
    audit = {
        "cohort_size": len(selected),
        "selection_year": 2024,
        "target": "future.direction_abs.h5.v1",
        "scope": "equity",
        "method": "circular_block_bootstrap_percentile_pointwise",
        "replicates": replicates,
        "seed": seed,
        "block_lengths_cutoffs": block_lengths,
        "source_comparison": str(source),
        "source_checksum": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_history_2025": str(history_2025),
        "source_history_2026": str(comparison_dir / "ic_history_2026.parquet"),
        "periods": {
            str(year): {
                "cutoffs": len(panel),
                "first": str(panel.index.min()),
                "last": str(panel.index.max()),
            }
            for year, panel in panels.items()
        },
        "windows": summary,
        "notes": [
            "Bootstrap sign support is a resampling frequency, not a posterior probability.",
            "90% two-sided intervals use the 5th and 95th percentiles; "
            "sign support >90% is weaker.",
            "All features share date draws within a year; year draws are generated independently.",
            "Intervals are pointwise, not adjusted for 815 comparisons or feature selection.",
            "Joint sign support and each-year support thresholds are distinct criteria.",
            "Block lengths 2/4/6 are sensitivity choices, not an estimated optimum.",
            "Approximate short-series intervals assume reasonably stationary "
            "IC behavior within each year.",
            "The observed universe and existing research-ready filters remain fixed; "
            "sampling bias is not corrected.",
        ],
        "method_references": [
            "https://arch.readthedocs.io/en/stable/bootstrap/timeseries-bootstraps.html",
            "https://arch.readthedocs.io/en/latest/bootstrap/confidence-intervals.html",
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
        "--comparison-dir",
        type=Path,
        default=ROOT / "data/analysis/spec006r-h5-top100-by-window-2025-2026",
    )
    parser.add_argument(
        "--history-2025",
        type=Path,
        default=ROOT / "data/analysis/spec006-2025-equity-scan/signal_ic_history.parquet",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/analysis/spec006r-h5-ic-confidence"
    )
    parser.add_argument("--replicates", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--block-lengths", type=int, nargs="+", default=[2, 4, 6])
    args = parser.parse_args()
    run(
        comparison_dir=args.comparison_dir,
        history_2025=args.history_2025,
        output=args.output,
        replicates=args.replicates,
        seed=args.seed,
        block_lengths=args.block_lengths,
    )


if __name__ == "__main__":
    main()
