"""Measure the main sample-selection and dependence issues in SPEC-006R.

The script compares the frozen 2024 equity return/direction top 500 in four
configurations: the published research-ready targets, all retained target
candidates, and both variants on the entities present at every 2024/2025
cutoff. Outputs are local and ignored by Git.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data/analysis/spec006r-stability-atlas-top500/frozen_top_signals.parquet"
ATLAS_HISTORY = (
    ROOT / "data/analysis/spec006r-stability-atlas-top500/signal_period_ic_history.parquet"
)
OUTPUT = ROOT / "data/analysis/spec006r-root-cause-audit"
PERIODS = {
    2024: (
        ROOT / "data/feature_cube/spec006-weekly-demo",
        ROOT / "data/targets/spec006-weekly-demo",
    ),
    2025: (
        ROOT / "data/feature_cube/spec006-2025-matched",
        ROOT / "data/targets/spec006-2025-matched",
    ),
}


def _selected_signals() -> pd.DataFrame:
    return (
        pl.read_parquet(FROZEN)
        .filter(
            (pl.col("scope") == "equity")
            & (pl.col("selection_bucket") == "return_direction")
        )
        .select(
            [
                "signal_id",
                "feature_id",
                "target_id",
                "target_family",
                "horizon",
                "discovery_rank",
            ]
        )
        .sort("discovery_rank")
        .to_pandas()
    )


def _common_entities() -> set[str]:
    populations: list[set[str]] = []
    for feature_root, _target_root in PERIODS.values():
        for path in sorted(feature_root.glob("as_of_date=*/features.parquet")):
            entities = (
                pl.read_parquet(path, columns=["entity_id", "entity_family"])
                .filter(pl.col("entity_family") == "equity")
                .get_column("entity_id")
                .to_list()
            )
            populations.append(set(entities))
    return set.intersection(*populations)


def _target_candidates(targets: pd.DataFrame) -> pd.DataFrame:
    """Use absolute-return candidates for unavailable percentile targets."""
    absolute = targets[targets.target_id.str.startswith("future.return_abs.")].copy()
    absolute["horizon_text"] = absolute.target_id.str.extract(r"h(\d+)")[0]
    values = absolute.set_index(["entity_id", "horizon_text"]).candidate_value
    is_rank = targets.target_id.str.startswith("future.rank_pct.")
    horizons = targets.loc[is_rank, "target_id"].str.extract(r"h(\d+)")[0]
    targets.loc[is_rank, "candidate_value"] = [
        values.get((entity, horizon), np.nan)
        for entity, horizon in zip(targets.loc[is_rank, "entity_id"], horizons, strict=True)
    ]
    return targets


def _cutoff_ics(
    *,
    year: int,
    feature_root: Path,
    target_root: Path,
    signals: pd.DataFrame,
    common_entities: set[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    records: list[tuple[int, str, str, str, float, int]] = []
    exclusions: list[dict[str, Any]] = []
    feature_ids = signals.feature_id.unique().tolist()
    target_ids = signals.target_id.unique().tolist()
    target_ids.extend(["future.return_abs.h60.v1", "future.return_abs.h120.v1"])

    for target_path in sorted(target_root.glob("as_of_date=*/targets.parquet")):
        partition = target_path.parent.name
        day = partition.split("=", maxsplit=1)[1]
        feature_path = feature_root / partition / "features.parquet"
        features = (
            pl.read_parquet(feature_path)
            .filter(
                (pl.col("entity_family") == "equity")
                & (pl.col("feature_status") == "available")
                & pl.col("feature_value").is_not_null()
                & pl.col("feature_id").is_in(feature_ids)
            )
            .select(["entity_id", "feature_id", "feature_value"])
            .to_pandas()
        )
        targets = (
            pl.read_parquet(target_path)
            .filter(
                (pl.col("entity_family") == "equity") & pl.col("target_id").is_in(target_ids)
            )
            .select(
                [
                    "entity_id",
                    "target_id",
                    "target_value",
                    "candidate_value",
                    "target_status",
                ]
            )
            .to_pandas()
        )
        targets = _target_candidates(targets)
        panel = signals.merge(features, on="feature_id").merge(
            targets, on=["entity_id", "target_id"]
        )
        modes = (
            ("current", "target_value", False),
            ("candidate", "candidate_value", False),
            ("current_stable", "target_value", True),
            ("candidate_stable", "candidate_value", True),
        )
        for mode, target_column, stable_only in modes:
            selected = panel[
                np.isfinite(panel.feature_value) & np.isfinite(panel[target_column])
            ]
            if stable_only:
                selected = selected[selected.entity_id.isin(common_entities)]
            for signal_id, group in selected.groupby("signal_id", sort=False):
                if (
                    len(group) >= 30
                    and group.feature_value.nunique() > 1
                    and group[target_column].nunique() > 1
                ):
                    ic = float(spearmanr(group.feature_value, group[target_column]).statistic)
                    records.append((year, day, mode, signal_id, ic, len(group)))

        h120 = targets[targets.target_id == "future.return_abs.h120.v1"]
        exclusions.append(
            {
                "year": year,
                "as_of_date": day,
                "available": int((h120.target_status == "available").sum()),
                "review": int((h120.target_status == "future_quality_review").sum()),
                "quarantined": int(
                    (h120.target_status == "future_quality_quarantined").sum()
                ),
            }
        )
    columns = ["year", "as_of_date", "mode", "signal_id", "ic", "n"]
    return pd.DataFrame(records, columns=columns), exclusions


def _annual_comparison(metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    annual = (
        metrics.groupby(["year", "mode", "signal_id"], as_index=False)
        .agg(ic_mean=("ic", "mean"), cutoffs=("ic", "size"), n_total=("n", "sum"))
    )
    comparison = (
        annual.pivot(index=["mode", "signal_id"], columns="year", values="ic_mean")
        .reset_index()
        .dropna()
    )
    comparison["reversal"] = np.sign(comparison[2024]) != np.sign(comparison[2025])
    comparison["magnitude_ratio"] = comparison[2025].abs() / comparison[2024].abs()
    rows: list[dict[str, Any]] = []
    for mode, group in comparison.groupby("mode"):
        rows.append(
            {
                "mode": mode,
                "relations": len(group),
                "reversals": int(group.reversal.sum()),
                "reversal_pct": float(100 * group.reversal.mean()),
                "mean_ic_2024": float(group[2024].mean()),
                "mean_ic_2025": float(group[2025].mean()),
                "median_ic_2024": float(group[2024].median()),
                "median_ic_2025": float(group[2025].median()),
                "cross_year_rank_correlation": float(
                    group[2024].corr(group[2025], method="spearman")
                ),
                "median_magnitude_ratio": float(group.magnitude_ratio.median()),
            }
        )
    return annual, pd.DataFrame(rows)


def _rank_signature_count(signals: pd.DataFrame) -> dict[str, int]:
    feature_ids = signals.feature_id.unique().tolist()
    chunks: list[pd.DataFrame] = []
    feature_root = PERIODS[2024][0]
    for path in sorted(feature_root.glob("as_of_date=*/features.parquet")):
        frame = (
            pl.read_parquet(path)
            .filter(
                (pl.col("entity_family") == "equity")
                & pl.col("feature_id").is_in(feature_ids)
                & pl.col("feature_value").is_not_null()
            )
            .select(["as_of_date", "entity_id", "feature_id", "feature_value"])
            .to_pandas()
        )
        frame["rank"] = frame.groupby("feature_id").feature_value.rank(
            method="average", pct=True
        )
        chunks.append(frame[["as_of_date", "entity_id", "feature_id", "rank"]])
    values = pd.concat(chunks).sort_values(["feature_id", "as_of_date", "entity_id"])
    signatures: list[str] = []
    for _feature_id, group in values.groupby("feature_id"):
        payload = "|".join(
            f"{day}:{entity}:{rank:.12g}"
            for day, entity, rank in zip(
                group.as_of_date, group.entity_id, group["rank"], strict=True
            )
        )
        signatures.append(hashlib.sha256(payload.encode()).hexdigest())
    counts = pd.Series(signatures).value_counts()
    return {
        "feature_ids": len(feature_ids),
        "exact_rank_signatures": int(len(counts)),
        "features_in_duplicate_signature_groups": int(counts[counts > 1].sum()),
    }


def _serial_dependence() -> dict[str, Any]:
    history = (
        pl.read_parquet(ATLAS_HISTORY)
        .filter(
            (pl.col("selection_scope") == "equity")
            & (pl.col("selection_bucket") == "return_direction")
            & (pl.col("evaluation_scope") == "equity")
            & pl.col("period_id").is_in(["2024_discovery", "2025_validation"])
        )
        .select(["period_id", "signal_id", "as_of_date", "spearman_ic"])
        .to_pandas()
        .sort_values(["period_id", "signal_id", "as_of_date"])
    )
    output: dict[str, Any] = {}
    for period, frame in history.groupby("period_id"):
        correlations = frame.groupby("signal_id").spearman_ic.apply(lambda x: x.autocorr(1))
        output[str(period)] = {
            "signals": int(correlations.notna().sum()),
            "median_lag1_autocorrelation": float(correlations.median()),
            "mean_lag1_autocorrelation": float(correlations.mean()),
        }
    return output


def main() -> None:
    signals = _selected_signals()
    common_entities = _common_entities()
    metrics: list[pd.DataFrame] = []
    exclusions: list[dict[str, Any]] = []
    for year, (feature_root, target_root) in PERIODS.items():
        period_metrics, period_exclusions = _cutoff_ics(
            year=year,
            feature_root=feature_root,
            target_root=target_root,
            signals=signals,
            common_entities=common_entities,
        )
        metrics.append(period_metrics)
        exclusions.extend(period_exclusions)

    cutoff_metrics = pd.concat(metrics, ignore_index=True)
    annual, comparison = _annual_comparison(cutoff_metrics)
    current = comparison[comparison["mode"] == "current"].iloc[0]
    audit = {
        "common_entities_all_54_cutoffs": len(common_entities),
        "top500_rows": len(signals),
        "top500_unique_features": int(signals.feature_id.nunique()),
        "rank_signatures": _rank_signature_count(signals),
        "serial_dependence": _serial_dependence(),
        "current_median_absolute_ic": {
            "2024": float(
                annual[(annual.year == 2024) & (annual["mode"] == "current")].ic_mean.abs().median()
            ),
            "2025": float(
                annual[(annual.year == 2025) & (annual["mode"] == "current")].ic_mean.abs().median()
            ),
        },
        "current_relations_abs_ic_at_least_0_10": {
            "2024": int(
                (
                    annual[(annual.year == 2024) & (annual["mode"] == "current")].ic_mean.abs()
                    >= 0.10
                ).sum()
            ),
            "2025": int(
                (
                    annual[(annual.year == 2025) & (annual["mode"] == "current")].ic_mean.abs()
                    >= 0.10
                ).sum()
            ),
        },
        "current_reversal_pct": float(current.reversal_pct),
        "mode_comparison": comparison.to_dict(orient="records"),
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    OUTPUT.chmod(0o755)
    output_paths = [
        OUTPUT / "top500_ic_by_cutoff_and_mode.csv",
        OUTPUT / "top500_ic_current_vs_candidate.csv",
        OUTPUT / "top500_reversal_current_vs_candidate.csv",
        OUTPUT / "h120_exclusions_by_cutoff.csv",
    ]
    cutoff_metrics.to_csv(output_paths[0], index=False)
    annual.to_csv(output_paths[1], index=False)
    comparison.to_csv(output_paths[2], index=False)
    pd.DataFrame(exclusions).to_csv(output_paths[3], index=False)
    audit_path = OUTPUT / "root_cause_audit.json"
    audit_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for output_path in [*output_paths, audit_path]:
        output_path.chmod(0o644)
    print(json.dumps(audit, indent=2, sort_keys=True))
    print(f"\nDetailed local outputs: {OUTPUT}")


if __name__ == "__main__":
    main()
