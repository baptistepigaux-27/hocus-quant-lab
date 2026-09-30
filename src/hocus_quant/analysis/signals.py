"""SPEC-006 univariate signal measurements.

This module deliberately produces descriptive associations, not strategy scores.
Every date is analyzed cross-sectionally before time-series statistics are formed.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import pearsonr, rankdata, spearmanr
from scipy.stats import t as student_t
from statsmodels.stats.multitest import multipletests

from hocus_quant.features.registry import FEATURE_REGISTRY, registry_document
from hocus_quant.targets.registry import target_registry, target_registry_document

_SUMMARY_TABLES = (
    "signal_summary",
    "signal_deciles",
    "signal_ic_history",
    "signal_period_stability",
    "signal_by_family",
    "signal_top_candidates",
    "signal_pooled_spearman",
)

_CUTOFF_ANALYSIS_VERSION = "cross-sectional-deciles/1.0"
_POOLED_SPEARMAN_VERSION = "pairwise-complete-average-ranks/1.0"


def _connect_spillable_duckdb(db_path: Path, output_dir: Path) -> duckdb.DuckDBPyConnection:
    scratch_dir = output_dir / ".duckdb_tmp"
    shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(db_path))
    db.execute("SET threads=1")
    db.execute("SET memory_limit='2GB'")
    db.execute("SET preserve_insertion_order=false")
    scratch_path = scratch_dir.resolve().as_posix().replace("'", "''")
    db.execute(f"SET temp_directory='{scratch_path}'")
    return db


def _finite_pair(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def _correlations(x: np.ndarray, y: np.ndarray) -> tuple[float | None, float | None, int]:
    x, y = _finite_pair(x, y)
    n = int(x.size)
    if n < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None, None, n
    return float(pearsonr(x, y).statistic), float(spearmanr(x, y).statistic), n


def _decile_rows(
    x: np.ndarray,
    y: np.ndarray,
    *,
    feature_id: str,
    target_id: str,
    scope: str,
    as_of_date: str,
    target_family: str,
) -> list[dict[str, Any]]:
    x, y = _finite_pair(x, y)
    if x.size < 10 or np.ptp(x) == 0:
        return []
    # Average ranks avoid order-dependent ties. Rank bucketing keeps groups balanced.
    ranks = rankdata(x, method="average")
    bins = np.minimum(10, np.ceil(ranks * 10 / x.size).astype(np.int16))
    population_positive = (
        float(np.mean(y > 0)) if target_family in {"direction_abs", "direction_rel"} else None
    )
    rows: list[dict[str, Any]] = []
    for decile in range(1, 11):
        values = y[bins == decile]
        if not values.size:
            continue
        positive_rate = float(np.mean(values > 0)) if population_positive is not None else None
        rows.append(
            {
                "feature_id": feature_id,
                "target_id": target_id,
                "scope": scope,
                "as_of_date": as_of_date,
                "decile": decile,
                "mean_target": float(np.mean(values)),
                "median_target": float(np.median(values)),
                "count": int(values.size),
                "dispersion": float(np.std(values, ddof=1)) if values.size > 1 else None,
                "positive_rate": positive_rate,
                "positive_lift": (
                    positive_rate - population_positive
                    if positive_rate is not None and population_positive is not None
                    else None
                ),
            }
        )
    return rows


def analyze_cutoff(
    feature_rows: pd.DataFrame,
    target_rows: pd.DataFrame,
    *,
    minimum_n: int = 30,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Measure all available feature/target pairs at one cutoff.

    Inputs are long-form SPEC-004 features and SPEC-005R research-ready targets.
    Alignment is an inner join on entity_id and as_of_date, and unavailable
    features/non-finite values are removed pairwise.
    """
    features = feature_rows.loc[
        (feature_rows["feature_status"] == "available")
        & np.isfinite(pd.to_numeric(feature_rows["feature_value"], errors="coerce"))
    ].copy()
    targets = target_rows.loc[
        target_rows["research_ready"].fillna(False)
        & (target_rows["target_status"] == "available")
        & np.isfinite(pd.to_numeric(target_rows["target_value"], errors="coerce"))
    ].copy()
    if features.empty or targets.empty:
        return [], []
    targets = targets.drop_duplicates(["entity_id", "as_of_date", "target_id"])
    features = features.drop_duplicates(["entity_id", "as_of_date", "feature_id"])
    matched_entities = (
        features[["entity_id", "entity_family", "as_of_date"]]
        .drop_duplicates()
        .merge(
            targets[["entity_id", "entity_family", "as_of_date"]].drop_duplicates(),
            on=["entity_id", "entity_family", "as_of_date"],
            how="inner",
        )
    )
    if matched_entities.empty:
        return [], []
    cutoff = str(pd.Timestamp(matched_entities["as_of_date"].iloc[0]).date())
    pair_rows: list[dict[str, Any]] = []
    decile_rows: list[dict[str, Any]] = []
    families = ["global", *sorted(matched_entities["entity_family"].unique().tolist())]
    for scope in families:
        scope_entities = (
            matched_entities
            if scope == "global"
            else matched_entities.loc[matched_entities["entity_family"] == scope]
        )
        entity_ids = scope_entities["entity_id"].tolist()
        feature_scope = features.loc[features["entity_id"].isin(entity_ids)]
        target_scope = targets.loc[targets["entity_id"].isin(entity_ids)]
        feature_matrix_frame = feature_scope.pivot(
            index="entity_id", columns="feature_id", values="feature_value"
        ).reindex(entity_ids)
        feature_ids = feature_matrix_frame.columns.astype(str).tolist()
        x_all = feature_matrix_frame.to_numpy(dtype=float)
        target_matrix = target_scope.pivot(
            index="entity_id", columns="target_id", values="target_value"
        ).reindex(entity_ids)
        target_meta = target_scope.drop_duplicates("target_id").set_index("target_id")
        for target_id in target_matrix.columns:
            y = target_matrix[target_id].to_numpy(dtype=float)
            y_valid = np.isfinite(y)
            if int(y_valid.sum()) < minimum_n:
                continue
            valid = np.isfinite(x_all) & y_valid[:, None]
            n = valid.sum(axis=0).astype(np.int64)
            target_family = str(target_meta.loc[target_id, "target_family"])
            horizon = int(target_meta.loc[target_id, "horizon"])
            keep = n >= minimum_n
            if not keep.any():
                continue
            # Pairwise-complete Pearson, vectorized across all features for this target.
            x = np.where(valid, x_all, 0.0)
            y_matrix = np.where(valid, y[:, None], 0.0)
            sx, sy = x.sum(axis=0), y_matrix.sum(axis=0)
            sxx, syy = np.square(x).sum(axis=0), np.square(y_matrix).sum(axis=0)
            sxy = (x * y_matrix).sum(axis=0)
            cov = sxy - sx * sy / np.maximum(n, 1)
            var_x = sxx - np.square(sx) / np.maximum(n, 1)
            var_y = syy - np.square(sy) / np.maximum(n, 1)
            pearson_values = np.divide(
                cov,
                np.sqrt(np.maximum(var_x, 0) * np.maximum(var_y, 0)),
                out=np.full(len(feature_ids), np.nan),
                where=(var_x > 0) & (var_y > 0),
            )
            # Re-rank each feature and the outcome on the pair-specific complete rows.
            # This is exact Spearman with ties handled by average ranks.
            from scipy.stats import rankdata

            ranked_x = rankdata(
                np.where(valid, x_all, np.nan), axis=0, method="average", nan_policy="omit"
            )
            ranked_y = rankdata(
                np.where(valid, y[:, None], np.nan), axis=0, method="average", nan_policy="omit"
            )
            rx = np.where(valid, ranked_x, 0.0)
            ry = np.where(valid, ranked_y, 0.0)
            rsx, rsy = rx.sum(axis=0), ry.sum(axis=0)
            rsxx, rsyy = np.square(rx).sum(axis=0), np.square(ry).sum(axis=0)
            rsxy = (rx * ry).sum(axis=0)
            rcov = rsxy - rsx * rsy / np.maximum(n, 1)
            rvar_x = rsxx - np.square(rsx) / np.maximum(n, 1)
            rvar_y = rsyy - np.square(rsy) / np.maximum(n, 1)
            spearman_values = np.divide(
                rcov,
                np.sqrt(np.maximum(rvar_x, 0) * np.maximum(rvar_y, 0)),
                out=np.full(len(feature_ids), np.nan),
                where=(rvar_x > 0) & (rvar_y > 0),
            )
            base_positive_rate = (
                float(np.mean(y[y_valid] > 0))
                if target_family in {"direction_abs", "direction_rel"}
                else None
            )
            for idx in np.flatnonzero(keep):
                pearson, spearman = pearson_values[idx], spearman_values[idx]
                if not (np.isfinite(pearson) and np.isfinite(spearman)):
                    continue
                feature_id = feature_ids[idx]
                pair_rows.append(
                    {
                        "feature_id": feature_id,
                        "target_id": str(target_id),
                        "target_family": target_family,
                        "horizon": horizon,
                        "scope": scope,
                        "as_of_date": cutoff,
                        "n": int(n[idx]),
                        "pearson_ic": float(pearson),
                        "spearman_ic": float(spearman),
                        "coverage": float(n[idx] / max(1, int(y_valid.sum()))),
                        "sum_x": float(sx[idx]),
                        "sum_y": float(sy[idx]),
                        "sum_x2": float(sxx[idx]),
                        "sum_y2": float(syy[idx]),
                        "sum_xy": float(sxy[idx]),
                    }
                )
            # Decile assignment is date-local. Summaries are vectorized by feature.
            ranked_x_deciles = ranked_x
            bins = np.minimum(
                10,
                np.ceil(
                    np.where(valid, ranked_x_deciles, 0)
                    * 10
                    / np.maximum(n[None, :], 1)
                ),
            ).astype(np.int8)
            bins[~valid] = 0
            for decile in range(1, 11):
                members = valid & (bins == decile)
                counts = members.sum(axis=0)
                sums = (members * y[:, None]).sum(axis=0)
                squares = (members * np.square(y[:, None])).sum(axis=0)
                positive = (members & (y[:, None] > 0)).sum(axis=0)
                medians = np.full(len(feature_ids), np.nan)
                nonempty = np.flatnonzero(counts > 0)
                if nonempty.size:
                    medians[nonempty] = np.nanmedian(
                        np.where(
                            members[:, nonempty], y[:, None], np.nan
                        ),
                        axis=0,
                    )
                for idx in np.flatnonzero(keep & (counts > 0)):
                    count = int(counts[idx])
                    mean_value = float(sums[idx] / count)
                    variance = max(0.0, float(squares[idx] / count - mean_value**2))
                    decile_rows.append(
                        {
                            "feature_id": feature_ids[idx],
                            "target_id": str(target_id),
                            "scope": scope,
                            "as_of_date": cutoff,
                            "decile": decile,
                            "mean_target": mean_value,
                            "median_target": float(medians[idx]),
                            "count": count,
                            "dispersion": float(np.sqrt(variance)),
                            "positive_rate": float(positive[idx] / count)
                            if base_positive_rate is not None
                            else None,
                            "positive_lift": float(positive[idx] / count - base_positive_rate)
                            if base_positive_rate is not None
                            else None,
                        }
                    )
    return pair_rows, decile_rows


def _aggregate_deciles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    group_cols = ["feature_id", "target_id", "scope", "decile"]
    output: list[dict[str, Any]] = []
    for keys, group in frame.groupby(group_cols, sort=True):
        weights = group["count"].to_numpy(dtype=float)
        means = group["mean_target"].to_numpy(dtype=float)
        row = dict(zip(group_cols, keys, strict=True))
        row.update(
            {
                "mean_target": float(np.average(means, weights=weights)),
                "median_target": float(np.average(group["median_target"], weights=weights)),
                "count": int(weights.sum()),
                "dispersion": float(
                    np.sqrt(np.average(group["dispersion"].fillna(0) ** 2, weights=weights))
                ),
                "positive_rate": (
                    float(
                        np.average(
                            group["positive_rate"].dropna(),
                            weights=weights[~group["positive_rate"].isna()],
                        )
                    )
                    if group["positive_rate"].notna().any()
                    else None
                ),
                "positive_lift": (
                    float(
                        np.average(
                            group["positive_lift"].dropna(),
                            weights=weights[~group["positive_lift"].isna()],
                        )
                    )
                    if group["positive_lift"].notna().any()
                    else None
                ),
                "cutoff_count": int(group["as_of_date"].nunique()),
            }
        )
        output.append(row)
    return output


def _summary_rows(
    pair_rows: list[dict[str, Any]],
    deciles: list[dict[str, Any]],
    *,
    minimum_cutoffs: int,
    fdr_alpha: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if not pair_rows:
        return [], [], [], []
    frame = pd.DataFrame(pair_rows)
    history: list[dict[str, Any]] = []
    aggregated_deciles = _aggregate_deciles(deciles)
    decile_frame = pd.DataFrame(aggregated_deciles) if aggregated_deciles else pd.DataFrame()
    summaries: list[dict[str, Any]] = []
    group_cols = ["feature_id", "target_id", "target_family", "horizon", "scope"]
    for keys, group in frame.groupby(group_cols, sort=True):
        group = group.sort_values("as_of_date")
        row: dict[str, Any] = dict(zip(group_cols, keys, strict=True))
        spearman = group["spearman_ic"].dropna().to_numpy(dtype=float)
        pearson_values = group["pearson_ic"].dropna().to_numpy(dtype=float)
        n_cutoffs = int(group["as_of_date"].nunique())
        mean_ic = float(np.mean(spearman)) if spearman.size else None
        t_stat = (
            float(np.mean(spearman) / (np.std(spearman, ddof=1) / math.sqrt(spearman.size)))
            if spearman.size > 1 and np.std(spearman, ddof=1) > 0
            else None
        )
        p_value = (
            float(2 * student_t.sf(abs(t_stat), df=spearman.size - 1))
            if t_stat is not None
            else None
        )
        curve = (
            decile_frame.loc[
                (decile_frame["feature_id"] == row["feature_id"])
                & (decile_frame["target_id"] == row["target_id"])
                & (decile_frame["scope"] == row["scope"])
            ].sort_values("decile")
            if not decile_frame.empty
            else pd.DataFrame()
        )
        means = curve["mean_target"].to_numpy(dtype=float) if not curve.empty else np.array([])
        monotonicity, violations, slope, spread = None, None, None, None
        if means.size >= 3:
            monotonicity = float(spearmanr(np.arange(1, means.size + 1), means).statistic)
            violations = int(
                np.sum(np.diff(means) < 0) if monotonicity >= 0 else np.sum(np.diff(means) > 0)
            )
            slope = float(np.polyfit(np.arange(1, means.size + 1), means, 1)[0])
            spread = float(means[-1] - means[0])
        all_n = int(group["n"].sum())
        pooled_cov = float(group["sum_xy"].sum()) - float(group["sum_x"].sum()) * float(
            group["sum_y"].sum()
        ) / max(all_n, 1)
        pooled_var_x = float(group["sum_x2"].sum()) - float(group["sum_x"].sum()) ** 2 / max(
            all_n, 1
        )
        pooled_var_y = float(group["sum_y2"].sum()) - float(group["sum_y"].sum()) ** 2 / max(
            all_n, 1
        )
        summary = {
            **row,
            "n_total": all_n,
            "cutoff_count": n_cutoffs,
            "pearson_pooled": (
                pooled_cov / math.sqrt(pooled_var_x * pooled_var_y)
                if pooled_var_x > 0 and pooled_var_y > 0
                else None
            ),
            "spearman_pooled": None,
            "pearson_ic_mean": float(np.mean(pearson_values)) if pearson_values.size else None,
            "spearman_ic_mean": mean_ic,
            "ic_median": float(np.median(spearman)) if spearman.size else None,
            "ic_std": float(np.std(spearman, ddof=1)) if spearman.size > 1 else None,
            "ic_t_stat": t_stat,
            "hit_rate": float(np.mean(spearman > 0)) if spearman.size else None,
            "p_value_descriptive": p_value,
            "coverage": float(np.average(group["coverage"], weights=group["n"])),
            "monotonicity_spearman": monotonicity,
            "monotone_violations_directional": violations,
            "decile_slope": slope,
            "top_bottom_spread": spread,
            "strength_axis": abs(mean_ic) if mean_ic is not None else None,
            "stability_axis": float(np.mean(spearman > 0)) if spearman.size else None,
            "monotonicity_axis": abs(monotonicity) if monotonicity is not None else None,
            "coverage_axis": float(np.average(group["coverage"], weights=group["n"])),
            "significance_axis": p_value,
            "family_consistency_axis": None,
            "fdr_q_value": None,
            "fdr_rank": None,
            "status": "eligible" if n_cutoffs >= minimum_cutoffs else "insufficient_cutoffs",
        }
        summaries.append(summary)
        dates = pd.to_datetime(group["as_of_date"])
        vals = group["spearman_ic"].to_numpy(dtype=float)
        rolling = pd.Series(vals).rolling(13, min_periods=1).mean().to_numpy()
        for idx, (_, point) in enumerate(group.iterrows()):
            history.append(
                {
                    "feature_id": row["feature_id"],
                    "target_id": row["target_id"],
                    "scope": row["scope"],
                    "as_of_date": str(dates.iloc[idx].date()),
                    "n": int(point["n"]),
                    "pearson_ic": point["pearson_ic"],
                    "spearman_ic": point["spearman_ic"],
                    "rolling_spearman_ic_13": float(rolling[idx]),
                }
            )
    # BH is independent per scope x target family x horizon; descriptive p values.
    scopes = {(r["scope"], r["target_family"], r["horizon"]) for r in summaries}
    for scope, target_family, horizon in scopes:
        selected = [
            r
            for r in summaries
            if (r["scope"], r["target_family"], r["horizon"]) == (scope, target_family, horizon)
            and r["status"] == "eligible"
            and r["p_value_descriptive"] is not None
        ]
        if selected:
            q_values = multipletests(
                [r["p_value_descriptive"] for r in selected], alpha=fdr_alpha, method="fdr_bh"
            )[1]
            for rank, (item, q_value) in enumerate(
                sorted(
                    zip(selected, q_values, strict=True),
                    key=lambda pair: (pair[1], pair[0]["feature_id"]),
                ),
                start=1,
            ):
                item["fdr_q_value"] = float(q_value)
                item["fdr_rank"] = rank
    family_ics: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for item in summaries:
        if item["scope"] != "global" and item["status"] == "eligible":
            family_ics[(item["feature_id"], item["target_id"], item["horizon"])].append(
                float(item["spearman_ic_mean"])
            )
    for item in summaries:
        values = family_ics.get((item["feature_id"], item["target_id"], item["horizon"]), [])
        if item["scope"] == "global" and values and item["spearman_ic_mean"]:
            sign = math.copysign(1.0, item["spearman_ic_mean"])
            item["family_consistency_axis"] = float(
                np.mean([math.copysign(1.0, value) == sign for value in values])
            )
    period_rows: list[dict[str, Any]] = []
    history_frame = pd.DataFrame(history)
    if not history_frame.empty:
        history_frame["year"] = pd.to_datetime(history_frame["as_of_date"]).dt.year
        for keys, group in history_frame.groupby(
            ["feature_id", "target_id", "scope", "year"], sort=True
        ):
            feature_id, target_id, scope, year = keys
            values = group["spearman_ic"].dropna().to_numpy(dtype=float)
            period_rows.append(
                {
                    "feature_id": feature_id,
                    "target_id": target_id,
                    "scope": scope,
                    "year": int(year),
                    "cutoff_count": int(group["as_of_date"].nunique()),
                    "spearman_ic_mean": float(np.mean(values)) if values.size else None,
                    "spearman_ic_median": float(np.median(values)) if values.size else None,
                    "positive_ratio": float(np.mean(values > 0)) if values.size else None,
                    "status": "eligible" if values.size >= 4 else "insufficient_period_n",
                }
            )
    return summaries, aggregated_deciles, history, period_rows


def _summarize_files(
    pair_files: list[Path],
    decile_files: list[Path],
    *,
    output_dir: Path,
    minimum_cutoffs: int,
    fdr_alpha: float,
    pooled_spearman_path: Path | None = None,
) -> dict[str, int]:
    """Aggregate cutoff partitions with DuckDB so the full history stays disk-backed."""
    if not pair_files or not decile_files:
        _write_empty_outputs(output_dir)
        return {"summary_rows": 0, "decile_rows": 0, "history_rows": 0, "period_rows": 0}
    output_dir.mkdir(parents=True, exist_ok=True)
    pooled_output_path = output_dir / "signal_pooled_spearman.parquet"
    if (
        pooled_spearman_path is None
        or pooled_spearman_path.resolve() != pooled_output_path.resolve()
    ):
        if not pooled_output_path.exists():
            _write_parquet(pooled_output_path, [])

    def parquet_list(paths: list[Path]) -> str:
        values = ["'" + path.resolve().as_posix().replace("'", "''") + "'" for path in paths]
        return "[" + ",".join(values) + "]"

    pairs_sql = parquet_list(pair_files)
    deciles_sql = parquet_list(decile_files)
    db_path = output_dir / "signals.duckdb"
    history_path = (
        (output_dir / "signal_ic_history.parquet").resolve().as_posix().replace("'", "''")
    )
    decile_path = (output_dir / "signal_deciles.parquet").resolve().as_posix().replace("'", "''")
    with _connect_spillable_duckdb(db_path, output_dir) as db:
        db.execute(
            f"""COPY (
              SELECT *, avg(spearman_ic) OVER (
                PARTITION BY feature_id, target_id, scope ORDER BY as_of_date
                ROWS BETWEEN 12 PRECEDING AND CURRENT ROW
              ) AS rolling_spearman_ic_13
              FROM read_parquet({pairs_sql}, union_by_name=true)
            ) TO '{history_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        db.execute(
            f"""COPY (
              SELECT feature_id, target_id, scope, decile,
                     sum(mean_target * count) / sum(count) AS mean_target,
                     median(median_target) AS median_target,
                     sum(count)::BIGINT AS count,
                     sqrt(greatest(
                       0,
                       sum((dispersion * dispersion + mean_target * mean_target) * count)
                         / sum(count)
                       - pow(sum(mean_target * count) / sum(count), 2)
                     )) AS dispersion,
                     sum(positive_rate * count) / sum(count) AS positive_rate,
                     sum(positive_lift * count) / sum(count) AS positive_lift,
                     count(DISTINCT as_of_date)::INTEGER AS cutoff_count
              FROM read_parquet({deciles_sql}, union_by_name=true)
              GROUP BY feature_id, target_id, scope, decile
            ) TO '{decile_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
    with _connect_spillable_duckdb(db_path, output_dir) as db:
        summary = db.execute(
            f"""WITH agg AS (
              SELECT feature_id, target_id, target_family, horizon, scope,
                     sum(n)::BIGINT AS n_total,
                     count(DISTINCT as_of_date)::INTEGER AS cutoff_count,
                     sum(sum_x) AS sum_x, sum(sum_y) AS sum_y,
                     sum(sum_x2) AS sum_x2, sum(sum_y2) AS sum_y2,
                     sum(sum_xy) AS sum_xy,
                     avg(pearson_ic) AS pearson_ic_mean,
                     avg(spearman_ic) AS spearman_ic_mean,
                     median(spearman_ic) AS ic_median,
                     stddev_samp(spearman_ic) AS ic_std,
                     avg((spearman_ic > 0)::INTEGER) AS hit_rate,
                     sum(n) / sum(n / NULLIF(coverage, 0)) AS coverage,
                     stddev_samp(spearman_ic) / sqrt(count(spearman_ic)) AS standard_error
              FROM read_parquet({pairs_sql}, union_by_name=true)
              GROUP BY feature_id, target_id, target_family, horizon, scope
            ), decile AS (
              SELECT feature_id, target_id, scope,
                     max(mean_target) FILTER (WHERE decile=1) AS d1,
                     max(mean_target) FILTER (WHERE decile=2) AS d2,
                     max(mean_target) FILTER (WHERE decile=3) AS d3,
                     max(mean_target) FILTER (WHERE decile=4) AS d4,
                     max(mean_target) FILTER (WHERE decile=5) AS d5,
                     max(mean_target) FILTER (WHERE decile=6) AS d6,
                     max(mean_target) FILTER (WHERE decile=7) AS d7,
                     max(mean_target) FILTER (WHERE decile=8) AS d8,
                     max(mean_target) FILTER (WHERE decile=9) AS d9,
                     max(mean_target) FILTER (WHERE decile=10) AS d10,
                     regr_slope(mean_target, decile::DOUBLE) AS decile_slope
              FROM read_parquet('{decile_path}') GROUP BY feature_id, target_id, scope
            )
            SELECT agg.*, decile.d1, decile.d2, decile.d3, decile.d4, decile.d5,
                   decile.d6, decile.d7, decile.d8, decile.d9, decile.d10,
                   decile.decile_slope, decile.d10-decile.d1 AS top_bottom_spread,
                   CASE WHEN agg.ic_std > 0 AND agg.cutoff_count > 1
                     THEN agg.spearman_ic_mean / (agg.ic_std / sqrt(agg.cutoff_count))
                     ELSE NULL END AS ic_t_stat
            FROM agg LEFT JOIN decile USING (feature_id, target_id, scope)"""
    ).df()
    if summary.empty:
        _write_empty_outputs(output_dir)
        return {"summary_rows": 0, "decile_rows": 0, "history_rows": 0, "period_rows": 0}
    summary["pearson_pooled"] = (
        summary["sum_xy"] - summary["sum_x"] * summary["sum_y"] / summary["n_total"]
    ) / np.sqrt(
        (summary["sum_x2"] - summary["sum_x"] ** 2 / summary["n_total"]).clip(lower=0)
        * (summary["sum_y2"] - summary["sum_y"] ** 2 / summary["n_total"]).clip(lower=0)
    )
    summary = summary.drop(columns=["sum_x", "sum_y", "sum_x2", "sum_y2", "sum_xy"])
    decile_columns = [f"d{index}" for index in range(1, 11)]
    decile_values = summary[decile_columns].to_numpy(dtype=float)
    complete_deciles = np.isfinite(decile_values).all(axis=1)
    if complete_deciles.any():
        ranked_deciles = rankdata(
            decile_values[complete_deciles], axis=1, method="average", nan_policy="omit"
        )
        centered_index = np.arange(1, 11, dtype=float) - 5.5
        centered_rank = ranked_deciles - ranked_deciles.mean(axis=1, keepdims=True)
        denominator = np.linalg.norm(centered_rank, axis=1) * np.linalg.norm(centered_index)
        monotonicity = np.divide(
            centered_rank @ centered_index,
            denominator,
            out=np.full(len(centered_rank), np.nan),
            where=denominator > 0,
        )
        summary.loc[complete_deciles, "monotonicity_spearman"] = monotonicity
        differences = np.diff(decile_values[complete_deciles], axis=1)
        directions = np.where(monotonicity[:, None] >= 0, differences < 0, differences > 0)
        summary.loc[complete_deciles, "monotone_violations_directional"] = directions.sum(axis=1)
    else:
        summary["monotonicity_spearman"] = np.nan
        summary["monotone_violations_directional"] = np.nan
    summary = summary.drop(columns=decile_columns)
    summary["p_value_descriptive"] = np.nan
    summary["fdr_q_value"] = np.nan
    summary["fdr_rank"] = np.nan
    summary["status"] = np.where(
        summary["cutoff_count"] >= minimum_cutoffs, "eligible", "insufficient_cutoffs"
    )
    summary["significance_axis"] = np.nan
    summary["strength_axis"] = summary["spearman_ic_mean"].abs()
    summary["stability_axis"] = summary["hit_rate"]
    summary["monotonicity_axis"] = summary["monotonicity_spearman"].abs()
    summary["coverage_axis"] = summary["coverage"]
    summary["family_consistency_axis"] = np.nan
    eligible = summary.loc[
        (summary["status"] == "eligible") & np.isfinite(summary["ic_t_stat"])
    ]
    if not eligible.empty:
        p_values = 2 * student_t.sf(
            np.abs(eligible["ic_t_stat"]), df=eligible["cutoff_count"] - 1
        )
        finite_p = np.isfinite(p_values)
        summary.loc[eligible.index[finite_p], "p_value_descriptive"] = p_values[finite_p]
        fdr_groups = ["scope", "target_family", "horizon"]
        # Re-select after assigning p-values: `eligible` is a copy and still
        # contains the original NaNs from the initialized summary columns.
        eligible_with_p = summary.loc[
            (summary["status"] == "eligible")
            & np.isfinite(summary["p_value_descriptive"])
        ]
        for _keys, group in eligible_with_p.groupby(fdr_groups, sort=True):
            q_values = multipletests(
                group["p_value_descriptive"].to_numpy(dtype=float), alpha=fdr_alpha, method="fdr_bh"
            )[1]
            ranked = group.assign(_q=q_values).sort_values(["_q", "feature_id"], kind="stable")
            summary.loc[ranked.index, "fdr_q_value"] = ranked["_q"].to_numpy()
            summary.loc[ranked.index, "fdr_rank"] = np.arange(1, len(ranked) + 1)
    summary["spearman_pooled"] = np.nan
    summary["spearman_pooled_status"] = "unavailable"
    if pooled_spearman_path is not None and pooled_spearman_path.is_file():
        pooled = pq.read_table(pooled_spearman_path).to_pandas()
        if not pooled.empty:
            summary = summary.drop(columns=["spearman_pooled"], errors="ignore").merge(
                pooled.rename(columns={"spearman_pooled": "spearman_pooled_value"}),
                on=["feature_id", "target_id", "scope"],
                how="left",
            )
            summary["spearman_pooled"] = summary.pop("spearman_pooled_value")
            summary["spearman_pooled_status"] = np.where(
                summary["spearman_pooled"].notna(),
                "pairwise_complete_global_ranks",
                "insufficient_n",
            )
    feature_family = {item.feature_id: item.family for item in FEATURE_REGISTRY}
    summary["feature_family"] = summary["feature_id"].map(feature_family)
    feature_series = {item.feature_id: item.source_series for item in FEATURE_REGISTRY}
    feature_metric = {item.feature_id: item.metric for item in FEATURE_REGISTRY}
    feature_window = {item.feature_id: item.window for item in FEATURE_REGISTRY}
    summary["feature_source_series"] = summary["feature_id"].map(feature_series)
    summary["feature_metric"] = summary["feature_id"].map(feature_metric)
    summary["feature_window"] = summary["feature_id"].map(feature_window)
    targets_by_id = {item.target_id: item for item in target_registry()}
    summary["target_formula"] = summary["target_id"].map(
        {key: item.formula for key, item in targets_by_id.items()}
    )
    summary["target_scale"] = summary["target_id"].map(
        {key: item.scale for key, item in targets_by_id.items()}
    )
    global_rows = summary.loc[summary["scope"] == "global"]
    family_consistency = (
        summary.loc[summary["scope"] != "global"]
        .groupby(["feature_id", "target_id", "horizon"])["spearman_ic_mean"]
        .apply(list)
    )
    for idx, row in global_rows.iterrows():
        values = family_consistency.get((row["feature_id"], row["target_id"], row["horizon"]), [])
        if values and pd.notna(row["spearman_ic_mean"]) and row["spearman_ic_mean"] != 0:
            sign = np.sign(row["spearman_ic_mean"])
            summary.loc[idx, "family_consistency_axis"] = float(np.mean(np.sign(values) == sign))
    summary_records = summary.to_dict("records")
    for row in summary_records:
        for column, value in row.items():
            if isinstance(value, (float, np.floating)) and not np.isfinite(value):
                row[column] = None
    _write_parquet(output_dir / "signal_summary.parquet", summary_records)
    with _connect_spillable_duckdb(db_path, output_dir) as db:
        summary_path = (
            (output_dir / "signal_summary.parquet").resolve().as_posix().replace("'", "''")
        )
        period_path = (
            (output_dir / "signal_period_stability.parquet").resolve().as_posix().replace("'", "''")
        )
        db.execute(
            f"""COPY (
              SELECT feature_id, target_id, scope,
                     year(CAST(as_of_date AS DATE)) AS year,
                     count(*)::INTEGER AS cutoff_count,
                     min(CAST(as_of_date AS DATE)) AS date_min,
                     max(CAST(as_of_date AS DATE)) AS date_max,
                     avg(spearman_ic) AS spearman_ic_mean,
                     median(spearman_ic) AS spearman_ic_median,
                     avg((spearman_ic > 0)::INTEGER) AS positive_ratio,
                     CASE WHEN count(*) < 4 THEN 'insufficient_period_n'
                          WHEN min(CAST(as_of_date AS DATE)) > make_date(
                                 year(CAST(as_of_date AS DATE)), 1, 1)
                            OR max(CAST(as_of_date AS DATE)) < make_date(
                                 year(CAST(as_of_date AS DATE)), 12, 31)
                          THEN 'partial_calendar_year'
                          ELSE 'eligible' END AS status
              FROM read_parquet('{history_path}')
              GROUP BY feature_id, target_id, scope, year
            ) TO '{period_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        family_path = (
            (output_dir / "signal_by_family.parquet").resolve().as_posix().replace("'", "''")
        )
        top_path = (
            (output_dir / "signal_top_candidates.parquet").resolve().as_posix().replace("'", "''")
        )
        db.execute(
            f"COPY (SELECT * FROM read_parquet('{summary_path}') WHERE scope<>'global') "
            f"TO '{family_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        db.execute(
            f"""COPY (
              SELECT * FROM read_parquet('{summary_path}') WHERE scope='global'
                AND status='eligible' AND n_total>=1000 AND cutoff_count>={minimum_cutoffs}
                AND coverage>=0.60 AND fdr_q_value<={fdr_alpha}
            ) TO '{top_path}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
    with duckdb.connect(str(db_path)) as db:
        for name in _SUMMARY_TABLES:
            path = (output_dir / f"{name}.parquet").resolve().as_posix().replace("'", "''")
            db.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
        db.execute("CHECKPOINT")
    decile_count = duckdb.sql(f"SELECT count(*) FROM read_parquet('{decile_path}')").fetchone()
    history_count = duckdb.sql(f"SELECT count(*) FROM read_parquet('{history_path}')").fetchone()
    period_count = duckdb.sql(f"SELECT count(*) FROM read_parquet('{period_path}')").fetchone()
    if decile_count is None or history_count is None or period_count is None:
        raise RuntimeError("DuckDB did not return aggregate output counts")
    shutil.rmtree(output_dir / ".duckdb_tmp", ignore_errors=True)
    return {
        "summary_rows": len(summary),
        "decile_rows": int(decile_count[0]),
        "history_rows": int(history_count[0]),
        "period_rows": int(period_count[0]),
    }


def _materialize_pooled_panels(
    *,
    feature_cube_dir: Path,
    target_set_dir: Path,
    panel_dir: Path,
) -> tuple[list[Path], list[Path]]:
    x_dir, y_dir = panel_dir / "x", panel_dir / "y"
    x_dir.mkdir(parents=True, exist_ok=True)
    y_dir.mkdir(parents=True, exist_ok=True)
    x_files: list[Path] = []
    y_files: list[Path] = []
    for feature_path in sorted(feature_cube_dir.glob("as_of_date=*/features.parquet")):
        partition = feature_path.parent.name
        date_text = partition.split("=", maxsplit=1)[1]
        target_path = target_set_dir / partition / "targets_research_ready.parquet"
        if not target_path.is_file():
            continue
        x_path = x_dir / f"{date_text}.parquet"
        y_path = y_dir / f"{date_text}.parquet"
        if not x_path.exists():
            feature_rows = duckdb.sql(
                "SELECT entity_id, entity_family, as_of_date, feature_id, feature_value "
                "FROM read_parquet(?) WHERE feature_status='available'",
                params=[str(feature_path)],
            ).df()
            keys = ["entity_id", "entity_family", "as_of_date"]
            x_wide = (
                feature_rows.pivot(
                    index=keys,
                    columns="feature_id",
                    values="feature_value",
                ).reset_index()
                if not feature_rows.empty
                else pd.DataFrame(columns=keys)
            )
            x_wide.to_parquet(x_path, compression="zstd", index=False)
        if not y_path.exists():
            target_rows = duckdb.sql(
                "SELECT entity_id, entity_family, as_of_date, target_id, target_value "
                "FROM read_parquet(?) WHERE research_ready=true AND target_status='available'",
                params=[str(target_path)],
            ).df()
            y_wide = (
                target_rows.pivot(
                    index=keys,
                    columns="target_id",
                    values="target_value",
                ).reset_index()
                if not target_rows.empty
                else pd.DataFrame(columns=keys)
            )
            y_wide.to_parquet(y_path, compression="zstd", index=False)
        x_files.append(x_path)
        y_files.append(y_path)
    return x_files, y_files


def _pooled_spearman_rows(
    x_files: list[Path],
    y_files: list[Path],
    *,
    minimum_n: int,
) -> list[dict[str, Any]]:
    if not x_files or not y_files:
        return []
    x_panel = pd.concat([pd.read_parquet(path) for path in x_files], ignore_index=True)
    y_panel = pd.concat([pd.read_parquet(path) for path in y_files], ignore_index=True)
    keys = ["entity_id", "entity_family", "as_of_date"]
    feature_ids = [column for column in x_panel.columns if column not in keys]
    target_ids = [column for column in y_panel.columns if column not in keys]
    joined = x_panel.merge(y_panel, on=keys, how="inner", validate="one_to_one")
    output: list[dict[str, Any]] = []
    scopes = ["global", *sorted(joined["entity_family"].dropna().unique().tolist())]
    for scope in scopes:
        selected = joined if scope == "global" else joined.loc[joined["entity_family"] == scope]
        x_all = selected[feature_ids].to_numpy(dtype=float)
        y_all = selected[target_ids].to_numpy(dtype=float)
        for target_index, target_id in enumerate(target_ids):
            y = y_all[:, target_index]
            y_valid = np.isfinite(y)
            valid = np.isfinite(x_all) & y_valid[:, None]
            n = valid.sum(axis=0)
            keep = n >= minimum_n
            if not keep.any():
                continue
            # Reranking on each feature/target pair's complete pooled rows gives
            # ordinary pooled Spearman rather than a correlation of date-local ICs.
            ranked_x = rankdata(
                np.where(valid, x_all, np.nan), axis=0, method="average", nan_policy="omit"
            )
            ranked_y = rankdata(
                np.where(valid, y[:, None], np.nan), axis=0, method="average", nan_policy="omit"
            )
            rx = np.where(valid, ranked_x, 0.0)
            ry = np.where(valid, ranked_y, 0.0)
            sx, sy = rx.sum(axis=0), ry.sum(axis=0)
            sxx, syy = np.square(rx).sum(axis=0), np.square(ry).sum(axis=0)
            sxy = (rx * ry).sum(axis=0)
            cov = sxy - sx * sy / np.maximum(n, 1)
            var_x = sxx - np.square(sx) / np.maximum(n, 1)
            var_y = syy - np.square(sy) / np.maximum(n, 1)
            correlations = np.divide(
                cov,
                np.sqrt(np.maximum(var_x, 0) * np.maximum(var_y, 0)),
                out=np.full(len(feature_ids), np.nan),
                where=(var_x > 0) & (var_y > 0),
            )
            output.extend(
                {
                    "feature_id": feature_ids[index],
                    "target_id": target_id,
                    "scope": scope,
                    "n": int(n[index]),
                    "spearman_pooled": float(correlations[index]),
                }
                for index in np.flatnonzero(keep & np.isfinite(correlations))
            )
    return output


def build_signal_analysis(
    *,
    feature_cube_dir: Path,
    target_set_dir: Path,
    output_dir: Path,
    minimum_n: int = 30,
    minimum_cutoffs: int = 13,
    fdr_alpha: float = 0.25,
    resume: bool = True,
) -> dict[str, Any]:
    """Build resumable SPEC-006 outputs from SPEC-004/005R partitions."""
    if minimum_n < 3:
        raise ValueError("minimum_n must be at least 3 for correlation analysis")
    if minimum_cutoffs < 1:
        raise ValueError("minimum_cutoffs must be positive")
    if not 0 < fdr_alpha <= 1:
        raise ValueError("fdr_alpha must be in (0, 1]")
    started = time.perf_counter()
    cube_contract_path = feature_cube_dir / "contract.json"
    target_contract_path = target_set_dir / "contract.json"
    if not cube_contract_path.is_file() or not target_contract_path.is_file():
        raise FileNotFoundError("feature cube and target set must each contain contract.json")
    cube_contract = json.loads(cube_contract_path.read_text(encoding="utf-8"))
    target_contract = json.loads(target_contract_path.read_text(encoding="utf-8"))
    cube_details = cube_contract.get("contract", cube_contract)
    target_details = target_contract.get("contract", target_contract)
    if cube_details.get("quality_scope") != "approved":
        raise ValueError("SPEC-006 requires a feature cube with quality_scope=approved")
    if target_details.get("quality_scope") != "approved":
        raise ValueError("SPEC-006 requires targets from the approved quality scope")
    if (
        target_details.get("feature_cube_contract_fingerprint")
        != cube_contract.get("contract_fingerprint")
    ):
        raise ValueError("target set was not built from the supplied feature cube contract")
    if cube_details.get("feature_registry_fingerprint") != registry_document().get("sha256"):
        raise ValueError("feature cube registry fingerprint does not match this code version")
    if (
        target_details.get("target_registry_fingerprint")
        != target_registry_document().get("sha256")
    ):
        raise ValueError("target set registry fingerprint does not match this code version")
    cutoff_dirs = sorted(feature_cube_dir.glob("as_of_date=*/features.parquet"))
    if not cutoff_dirs:
        raise FileNotFoundError(f"no feature partitions found in {feature_cube_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    per_cut_dir = output_dir / "cutoffs"
    per_cut_dir.mkdir(exist_ok=True)
    cutoff_contract = {
        "version": _CUTOFF_ANALYSIS_VERSION,
        "feature_cube_contract_fingerprint": cube_contract.get("contract_fingerprint"),
        "target_set_contract_fingerprint": target_contract.get("contract_fingerprint"),
        "minimum_n": minimum_n,
    }
    cutoff_contract_path = output_dir / "cutoff_analysis_contract.json"
    existing_cutoffs = list(per_cut_dir.glob("*.parquet"))
    if cutoff_contract_path.is_file():
        if json.loads(cutoff_contract_path.read_text(encoding="utf-8")) != cutoff_contract:
            raise ValueError("existing cutoff partitions use a different analysis contract")
    elif existing_cutoffs:
        raise ValueError(
            "existing cutoff partitions lack a contract; choose a new output "
            "or restore its contract"
        )
    else:
        cutoff_contract_path.write_text(
            json.dumps(cutoff_contract, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    completed = 0
    errors: list[str] = []
    for feature_path in cutoff_dirs:
        partition = feature_path.parent.name
        date_text = partition.split("=", maxsplit=1)[1]
        out_path = per_cut_dir / f"{date_text}.parquet"
        dec_path = per_cut_dir / f"{date_text}.deciles.parquet"
        if resume and out_path.exists() and dec_path.exists():
            completed += 1
            continue
        target_path = target_set_dir / partition / "targets_research_ready.parquet"
        if not target_path.is_file():
            errors.append(f"{date_text}: missing research-ready targets")
            continue
        feature_rows = duckdb.sql(
            "SELECT entity_id, entity_family, as_of_date, feature_id, feature_value, "
            "feature_status "
            f"FROM read_parquet('{feature_path.resolve()}')"
            ).df()
        target_rows = duckdb.sql(
            "SELECT entity_id, entity_family, as_of_date, target_id, target_family, horizon, "
            "target_value, target_status, research_ready "
            f"FROM read_parquet('{target_path.resolve()}')"
        ).df()
        pairs, deciles = analyze_cutoff(feature_rows, target_rows, minimum_n=minimum_n)
        _write_cutoff_rows(out_path, pairs, kind="pairs")
        _write_cutoff_rows(dec_path, deciles, kind="deciles")
        completed += 1
    pair_files = sorted(per_cut_dir.glob("*.parquet"))
    pair_files = [p for p in pair_files if not p.name.endswith(".deciles.parquet")]
    decile_files = sorted(per_cut_dir.glob("*.deciles.parquet"))
    pooled_panel_dir = output_dir / "pooled_panels"
    x_panel_files, y_panel_files = _materialize_pooled_panels(
        feature_cube_dir=feature_cube_dir,
        target_set_dir=target_set_dir,
        panel_dir=pooled_panel_dir,
    )
    pooled_spearman_path = output_dir / "signal_pooled_spearman.parquet"
    pooled_contract = {
        "version": _POOLED_SPEARMAN_VERSION,
        "feature_cube_contract_fingerprint": cube_contract.get("contract_fingerprint"),
        "target_set_contract_fingerprint": target_contract.get("contract_fingerprint"),
        "minimum_n": minimum_n,
    }
    pooled_contract_path = output_dir / "pooled_spearman_contract.json"
    if (
        resume
        and pooled_spearman_path.is_file()
        and pooled_contract_path.is_file()
        and json.loads(pooled_contract_path.read_text(encoding="utf-8")) == pooled_contract
    ):
        pooled_spearman = pq.read_table(pooled_spearman_path).to_pylist()
    else:
        pooled_spearman = _pooled_spearman_rows(
            x_panel_files, y_panel_files, minimum_n=minimum_n
        )
        _write_parquet(pooled_spearman_path, pooled_spearman)
        pooled_contract_path.write_text(
            json.dumps(pooled_contract, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    aggregate_counts = _summarize_files(
        pair_files,
        decile_files,
        output_dir=output_dir,
        minimum_cutoffs=minimum_cutoffs,
        fdr_alpha=fdr_alpha,
        pooled_spearman_path=pooled_spearman_path,
    )
    with duckdb.connect(str(output_dir / "signals.duckdb"), read_only=True) as db:
        all_relation_count = db.execute("SELECT count(*) FROM signal_summary").fetchone()
        candidate_count = db.execute("SELECT count(*) FROM signal_top_candidates").fetchone()
        summary_stats = db.execute(
            """SELECT count(*) AS rows,
                      count(DISTINCT feature_id) AS features,
                      count(DISTINCT target_id) AS targets,
                      sum(n_total) AS aligned_x_y_observations,
                      count(*) FILTER (WHERE fdr_q_value<=0.05) AS q05,
                      count(*) FILTER (WHERE fdr_q_value<=0.10) AS q10,
                      count(*) FILTER (WHERE fdr_q_value<=0.25) AS q25,
                      min(spearman_ic_mean), quantile_cont(spearman_ic_mean, .01),
                      quantile_cont(spearman_ic_mean, .25),
                      quantile_cont(spearman_ic_mean, .5),
                      quantile_cont(spearman_ic_mean, .75),
                      quantile_cont(spearman_ic_mean, .99), max(spearman_ic_mean),
                      count(*) FILTER (WHERE coverage<0.60) AS low_coverage
               FROM signal_summary WHERE scope='global'"""
        ).fetchone()
        cutoff_stats = db.execute(
            "SELECT count(DISTINCT as_of_date), min(as_of_date), max(as_of_date) "
            "FROM signal_ic_history WHERE scope='global'"
        ).fetchone()
    if summary_stats is None or cutoff_stats is None:
        raise RuntimeError("Signal output audit query returned no row")
    if all_relation_count is None or candidate_count is None:
        raise RuntimeError("Signal relation count query returned no row")
    cube_audit_path = feature_cube_dir / "cube_audit.json"
    hardening_audit_path = target_set_dir / "target_hardening_audit.json"
    cube_audit = (
        json.loads(cube_audit_path.read_text(encoding="utf-8"))
        if cube_audit_path.is_file()
        else {}
    )
    hardening_audit = (
        json.loads(hardening_audit_path.read_text(encoding="utf-8"))
        if hardening_audit_path.is_file()
        else {}
    )
    output_bytes = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
    code_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    run_identity = {
        "feature_cube_contract_fingerprint": cube_contract.get("contract_fingerprint"),
        "target_set_contract_fingerprint": target_contract.get("contract_fingerprint"),
        "data_quality": {
            "feature_cube": {
                key: cube_audit.get(key)
                for key in (
                    "availability_rate",
                    "available_cells",
                    "total_cells",
                    "entity_count_min",
                    "entity_count_median",
                    "entity_count_max",
                    "error_count",
                )
            },
            "target_set": {
                key: hardening_audit.get(key)
                for key in (
                    "raw_target_rows",
                    "research_ready_target_rows",
                    "target_rows_excluded_from_research_ready",
                    "extreme_target_rows",
                    "unresolved_event_count",
                    "pit_grade",
                    "strict_pit_claimed",
                    "relative_benchmark_coverage_by_horizon",
                )
            },
        },
        "analysis_code_sha256": code_sha256,
        "minimum_n": minimum_n,
        "minimum_cutoffs": minimum_cutoffs,
        "fdr_alpha": fdr_alpha,
        "cutoff_count": cutoff_stats[0],
        "start": str(cutoff_stats[1]),
        "end": str(cutoff_stats[2]),
    }
    run_id = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    manifest = {
        "schema_version": "SPEC-006/1.0",
        "run_id": run_id,
        "status": "complete" if not errors else "incomplete",
        "feature_cube": str(feature_cube_dir),
        "target_set": str(target_set_dir),
        "cutoff_count": len(pair_files),
        "input_cutoff_count": len(cutoff_dirs),
        "completed_cutoff_count": completed,
        "errors": errors,
        "minimum_n": minimum_n,
        "minimum_cutoffs": minimum_cutoffs,
        "fdr_alpha": fdr_alpha,
        "pit_grade": "reconstructed",
        "quality_scope": "approved",
        "target_scope": "research_ready only",
        "feature_registry_sha256": registry_document()["sha256"],
        "target_registry_sha256": target_registry_document()["sha256"],
        **aggregate_counts,
        "analysis_code_sha256": code_sha256,
        "feature_cube_contract_fingerprint": cube_contract.get("contract_fingerprint"),
        "target_set_contract_fingerprint": target_contract.get("contract_fingerprint"),
        "analyzed_date_min": str(cutoff_stats[1]) if cutoff_stats[1] is not None else None,
        "analyzed_date_max": str(cutoff_stats[2]) if cutoff_stats[2] is not None else None,
        "distinct_features_global": int(summary_stats[1] or 0),
        "distinct_targets_global": int(summary_stats[2] or 0),
        "global_feature_target_pairs_tested": int(summary_stats[0] or 0),
        "all_scope_relation_rows": int(all_relation_count[0] or 0),
        "mechanical_candidate_rows": int(candidate_count[0] or 0),
        "aligned_x_y_observations_global": int(summary_stats[3] or 0),
        "fdr_global_counts": {
            "q_le_0_05": int(summary_stats[4] or 0),
            "q_le_0_10": int(summary_stats[5] or 0),
            "q_le_0_25": int(summary_stats[6] or 0),
        },
        "spearman_ic_global_quantiles": {
            "min": summary_stats[7],
            "p01": summary_stats[8],
            "p25": summary_stats[9],
            "median": summary_stats[10],
            "p75": summary_stats[11],
            "p99": summary_stats[12],
            "max": summary_stats[13],
        },
        "global_low_coverage_rows": int(summary_stats[14] or 0),
        "pooled_spearman_rows": len(pooled_spearman),
        "output_bytes": output_bytes,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
    else:
        if path.name == "signal_pooled_spearman.parquet":
            pq.write_table(
                pa.Table.from_pylist(
                    [],
                    schema=pa.schema(
                        [
                            ("feature_id", pa.string()),
                            ("target_id", pa.string()),
                            ("scope", pa.string()),
                            ("n", pa.int64()),
                            ("spearman_pooled", pa.float64()),
                        ]
                    ),
                ),
                path,
                compression="zstd",
            )
            return
        pq.write_table(
            pa.table({"empty": pa.array([], type=pa.string())}), path, compression="zstd"
        )


def _write_cutoff_rows(path: Path, rows: list[dict[str, Any]], *, kind: str) -> None:
    if rows:
        _write_parquet(path, rows)
        return
    if kind == "pairs":
        schema = pa.schema(
            [
                ("feature_id", pa.string()),
                ("feature_family", pa.string()),
                ("target_id", pa.string()),
                ("target_family", pa.string()),
                ("horizon", pa.int16()),
                ("scope", pa.string()),
                ("as_of_date", pa.string()),
                ("n", pa.int64()),
                ("pearson_ic", pa.float64()),
                ("spearman_ic", pa.float64()),
                ("coverage", pa.float64()),
                ("sum_x", pa.float64()),
                ("sum_y", pa.float64()),
                ("sum_x2", pa.float64()),
                ("sum_y2", pa.float64()),
                ("sum_xy", pa.float64()),
            ]
        )
    else:
        schema = pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("scope", pa.string()),
                ("as_of_date", pa.string()),
                ("decile", pa.int64()),
                ("mean_target", pa.float64()),
                ("median_target", pa.float64()),
                ("count", pa.int64()),
                ("dispersion", pa.float64()),
                ("positive_rate", pa.float64()),
                ("positive_lift", pa.float64()),
            ]
        )
    pq.write_table(pa.Table.from_pylist([], schema=schema), path, compression="zstd")


def _write_empty_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas: dict[str, pa.Schema] = {
        "signal_summary": pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("target_family", pa.string()),
                ("feature_family", pa.string()),
                ("feature_source_series", pa.string()),
                ("feature_metric", pa.string()),
                ("feature_window", pa.int16()),
                ("target_formula", pa.string()),
                ("target_scale", pa.string()),
                ("horizon", pa.int16()),
                ("scope", pa.string()),
                ("n_total", pa.int64()),
                ("cutoff_count", pa.int32()),
                ("pearson_pooled", pa.float64()),
                ("spearman_pooled", pa.float64()),
                ("spearman_pooled_status", pa.string()),
                ("spearman_ic_mean", pa.float64()),
                ("pearson_ic_mean", pa.float64()),
                ("ic_median", pa.float64()),
                ("ic_std", pa.float64()),
                ("ic_t_stat", pa.float64()),
                ("p_value_descriptive", pa.float64()),
                ("hit_rate", pa.float64()),
                ("top_bottom_spread", pa.float64()),
                ("monotonicity_spearman", pa.float64()),
                ("fdr_q_value", pa.float64()),
                ("coverage", pa.float64()),
                ("fdr_rank", pa.int64()),
                ("monotone_violations_directional", pa.float64()),
                ("decile_slope", pa.float64()),
                ("strength_axis", pa.float64()),
                ("stability_axis", pa.float64()),
                ("significance_axis", pa.float64()),
                ("monotonicity_axis", pa.float64()),
                ("coverage_axis", pa.float64()),
                ("family_consistency_axis", pa.float64()),
                ("status", pa.string()),
            ]
        ),
        "signal_deciles": pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("scope", pa.string()),
                ("decile", pa.int16()),
                ("mean_target", pa.float64()),
                ("median_target", pa.float64()),
                ("count", pa.int64()),
                ("dispersion", pa.float64()),
                ("positive_rate", pa.float64()),
                ("positive_lift", pa.float64()),
            ]
        ),
        "signal_ic_history": pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("scope", pa.string()),
                ("as_of_date", pa.string()),
                ("n", pa.int64()),
                ("pearson_ic", pa.float64()),
                ("spearman_ic", pa.float64()),
                ("rolling_spearman_ic_13", pa.float64()),
            ]
        ),
        "signal_period_stability": pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("scope", pa.string()),
                ("year", pa.int32()),
                ("cutoff_count", pa.int32()),
                ("date_min", pa.date32()),
                ("date_max", pa.date32()),
                ("spearman_ic_mean", pa.float64()),
                ("spearman_ic_median", pa.float64()),
                ("positive_ratio", pa.float64()),
                ("status", pa.string()),
            ]
        ),
        "signal_pooled_spearman": pa.schema(
            [
                ("feature_id", pa.string()),
                ("target_id", pa.string()),
                ("scope", pa.string()),
                ("n", pa.int64()),
                ("spearman_pooled", pa.float64()),
            ]
        ),
    }
    for name in (
        "signal_summary",
        "signal_deciles",
        "signal_ic_history",
        "signal_period_stability",
    ):
        path = output_dir / f"{name}.parquet"
        pq.write_table(pa.Table.from_pylist([], schema=schemas[name]), path, compression="zstd")
    for name in ("signal_by_family", "signal_top_candidates"):
        path = output_dir / f"{name}.parquet"
        pq.write_table(
            pa.Table.from_pylist([], schema=schemas["signal_summary"]),
            path,
            compression="zstd",
        )
    pooled_path = output_dir / "signal_pooled_spearman.parquet"
    pq.write_table(
        pa.Table.from_pylist([], schema=schemas["signal_pooled_spearman"]),
        pooled_path,
        compression="zstd",
    )
    db_path = output_dir / "signals.duckdb"
    with duckdb.connect(str(db_path)) as db:
        for name in _SUMMARY_TABLES:
            sql_path = (output_dir / f"{name}.parquet").resolve().as_posix().replace("'", "''")
            db.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{sql_path}')")
