"""Compare SPEC-006R return/direction IC signs across 2024 and 2025.

Run after building the 2025 equity-only signal summary and the 2024 discovery
summary. Local results are written to the ignored data/analysis directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import polars as pl
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
PERIOD_2024 = ROOT / "data/analysis/spec006-weekly-demo"
PERIOD_2025 = ROOT / "data/analysis/spec006-2025-equity-scan"
ATLAS = ROOT / "data/analysis/spec006r-stability-atlas-top500"
OUTPUT = ROOT / "data/analysis/spec006r-reversal-audit"
FAMILIES = ["direction_abs", "direction_rel", "rank_pct", "return_abs", "return_rel"]
KEYS = ["feature_id", "target_id"]


def _eligible() -> pl.Expr:
    return (
        (pl.col("scope") == "equity")
        & pl.col("target_family").is_in(FAMILIES)
        & (pl.col("status") == "eligible")
        & (pl.col("n_total") >= 1000)
        & (pl.col("cutoff_count") >= 13)
        & (pl.col("coverage") >= 0.60)
        & pl.col("spearman_ic_mean").is_not_null()
    )


def _sign_summary(frame: pl.DataFrame, earlier: str, later: str) -> dict[str, Any]:
    x = frame[earlier].to_numpy().astype(float)
    y = frame[later].to_numpy().astype(float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    same = (np.sign(x) == np.sign(y)) & (x != 0) & (y != 0)
    reversed_sign = (np.sign(x) != np.sign(y)) & (x != 0) & (y != 0)
    zero_either = (x == 0) | (y == 0)
    return {
        "n": int(len(x)),
        "same_sign": int(same.sum()),
        "reversed_sign": int(reversed_sign.sum()),
        "reversed_sign_pct": float(reversed_sign.mean() * 100) if len(x) else None,
        "zero_either": int(zero_either.sum()),
        "negative_2024": int((x < 0).sum()),
        "positive_2024": int((x > 0).sum()),
        "negative_2025": int((y < 0).sum()),
        "positive_2025": int((y > 0).sum()),
        "mean_ic_2024": float(x.mean()) if len(x) else None,
        "mean_ic_2025": float(y.mean()) if len(y) else None,
        "median_ic_2024": float(np.median(x)) if len(x) else None,
        "median_ic_2025": float(np.median(y)) if len(y) else None,
        "spearman_across_relations": (float(spearmanr(x, y).statistic) if len(x) > 1 else None),
    }


def _weekly_top500() -> pl.DataFrame:
    frozen = ATLAS / "frozen_top_signals.parquet"
    queries: list[pl.DataFrame] = []
    for year, history in (
        ("2024", PERIOD_2024 / "signal_ic_history.parquet"),
        ("2025", PERIOD_2025 / "signal_ic_history.parquet"),
    ):
        sql = f"""
            WITH selected AS (
                SELECT feature_id, target_id
                FROM read_parquet('{frozen}')
                WHERE scope='equity' AND selection_bucket='return_direction'
            ), history AS (
                SELECT h.as_of_date, h.spearman_ic
                FROM read_parquet('{history}') h
                JOIN selected USING (feature_id, target_id)
                WHERE h.scope='equity'
            )
            SELECT '{year}' AS period, as_of_date, count(*) AS relations,
                   avg(spearman_ic) AS mean_ic, median(spearman_ic) AS median_ic,
                   100.0 * count_if(spearman_ic < 0) / count(*) AS negative_pct
            FROM history GROUP BY as_of_date ORDER BY as_of_date
        """
        queries.append(duckdb.sql(sql).pl())
    return pl.concat(queries)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    s24 = pl.read_parquet(PERIOD_2024 / "signal_summary.parquet")
    s25 = pl.read_parquet(PERIOD_2025 / "signal_summary.parquet")
    cols = KEYS + ["target_family", "spearman_ic_mean"]
    c24 = (
        s24.filter(_eligible())
        .select(cols)
        .rename({"target_family": "target_family_2024", "spearman_ic_mean": "ic_2024"})
    )
    c25 = (
        s25.filter(_eligible())
        .select(cols)
        .rename({"target_family": "target_family_2025", "spearman_ic_mean": "ic_2025"})
    )
    common = c24.join(c25, on=KEYS, how="inner")
    result: dict[str, Any] = {
        "eligible_2024": c24.height,
        "eligible_2025": c25.height,
        "common_relation_pairs": _sign_summary(common, "ic_2024", "ic_2025"),
        "common_by_target_family": {},
    }
    for family in FAMILIES:
        selected = common.filter(pl.col("target_family_2024") == family)
        result["common_by_target_family"][family] = _sign_summary(selected, "ic_2024", "ic_2025")

    frozen = pl.read_parquet(ATLAS / "frozen_top_signals.parquet").filter(
        (pl.col("scope") == "equity")
        & (pl.col("selection_bucket") == "return_direction")
        & pl.col("target_family").is_in(FAMILIES)
    )
    current_2025 = s25.filter(pl.col("scope") == "equity").select(
        KEYS + [pl.col("spearman_ic_mean").alias("ic_2025")]
    )
    selected_2024 = (
        frozen.join(current_2025, on=KEYS, how="left")
        .select(KEYS + [pl.col("discovery_ic_mean").alias("ic_2024"), "ic_2025"])
        .filter(pl.col("ic_2025").is_not_null())
    )
    result["frozen_2024_top500"] = _sign_summary(selected_2024, "ic_2024", "ic_2025")

    placebo = (
        s25.filter(_eligible())
        .with_columns(pl.col("spearman_ic_mean").abs().alias("abs_ic"))
        .sort(
            ["fdr_q_value", "abs_ic", "coverage", "cutoff_count", "feature_id", "target_id"],
            descending=[False, True, True, True, False, False],
            nulls_last=True,
        )
        .head(frozen.height)
        .select(
            KEYS
            + [
                "target_family",
                "horizon",
                pl.col("spearman_ic_mean").alias("ic_2025"),
            ]
        )
    )
    earlier_2024 = s24.filter(pl.col("scope") == "equity").select(
        KEYS + [pl.col("spearman_ic_mean").alias("ic_2024")]
    )
    placebo_paired = placebo.join(earlier_2024, on=KEYS, how="left").filter(
        pl.col("ic_2024").is_not_null()
    )
    result["placebo_2025_top500"] = _sign_summary(placebo_paired, "ic_2024", "ic_2025")
    result["placebo_2025_composition"] = (
        placebo.group_by(["target_family", "horizon"])
        .len()
        .sort(["target_family", "horizon"])
        .to_dicts()
    )

    weekly = _weekly_top500()
    weekly.write_csv(OUTPUT / "top500_weekly_ic_by_year.csv")
    common.write_csv(OUTPUT / "common_eligible_relation_pairs.csv")
    placebo_paired.write_csv(OUTPUT / "placebo_2025_top500.csv")
    (OUTPUT / "population_comparison.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"\nDetailed local outputs: {OUTPUT}")


if __name__ == "__main__":
    main()
