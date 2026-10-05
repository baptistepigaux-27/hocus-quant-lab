"""Fixed univariate and collective confirmation statistics; no selection or fitted weights."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import polars as pl
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from hocus_quant.analysis.confirmation_protocol import verdict
from hocus_quant.analysis.ex_ante import draw_means
from hocus_quant.features.registry import FEATURE_REGISTRY

META = {r.feature_id: r for r in FEATURE_REGISTRY}
TIERS = ("broad_candidates", "strong_sign_candidates", "strict_candidates")


def finite_float(value: Any) -> float | None:
    return float(value) if value is not None and math.isfinite(float(value)) else None


def oriented_scores(
    features: pl.DataFrame, lock: dict[str, Any], minimum_fraction: float = 0.5
) -> pl.DataFrame:
    """Two fixed strict aggregates, formed from the frozen cross-section at T."""
    strict = [r for r in lock["candidates"] if r["strict_candidates"]]
    matrix = features.pivot(on="feature_id", index="entity_id", values="feature_value")
    matrix = matrix.sort("entity_id")
    percentiles = np.full((matrix.height, len(strict)), np.nan)
    for j, row in enumerate(strict):
        x = matrix[row["canonical_feature"]].to_numpy().astype(float)
        mask = np.isfinite(x)
        percentiles[mask, j] = (
            rankdata(x[mask] * row["locked_direction"], method="average") - 0.5
        ) / max(int(mask.sum()), 1)
    count = np.isfinite(percentiles).sum(axis=1)
    valid = count >= math.ceil(len(strict) * minimum_fraction)
    ranks = np.divide(
        np.nansum(percentiles, axis=1), count, out=np.full(matrix.height, np.nan), where=count > 0
    )
    consensus = np.divide(
        (percentiles > 0.5).sum(axis=1), count, out=np.full(matrix.height, np.nan), where=count > 0
    )
    return pl.DataFrame(
        {
            "entity_id": matrix["entity_id"],
            "strict_features_available": count,
            "equal_weight_oriented_rank": [
                finite_float(v) if ok else None for v, ok in zip(ranks, valid, strict=True)
            ],
            "strict_consensus": [
                finite_float(v) if ok else None for v, ok in zip(consensus, valid, strict=True)
            ],
        },
        schema_overrides={"equal_weight_oriented_rank": pl.Float64, "strict_consensus": pl.Float64},
    )


def statistics(
    x: np.ndarray[Any, Any],
    y: np.ndarray[Any, Any],
    *,
    eligible: int,
    minimum_n: int,
    decile_minimum_n: int,
) -> dict[str, Any]:
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(y)
    ic = (
        finite_float(spearmanr(x, y).statistic)
        if n >= minimum_n and np.ptp(x) > 0 and np.ptp(y) > 0
        else None
    )
    spread = None
    if n >= decile_minimum_n and np.ptp(x) > 0:
        bins = np.ceil(rankdata(x, method="average") * 10 / n).astype(int)
        if (bins == 1).any() and (bins == 10).any():
            spread = float(y[bins == 10].mean() - y[bins == 1].mean())
    return {
        "spearman_ic": ic,
        "n": n,
        "coverage": n / eligible if eligible else 0.0,
        "mean_target": float(y.mean()) if n else None,
        "positive_target_rate": float((y > 0).mean()) if n else None,
        "decile_spread": spread,
        "ic_status": "available" if ic is not None else "insufficient_or_constant",
    }


def cutoff_metrics(
    features: pl.DataFrame,
    outcomes: pl.DataFrame,
    lock: dict[str, Any],
    protocol: dict[str, Any],
    cutoff: str,
) -> pl.DataFrame:
    settings = protocol["settings"]
    eligible = outcomes.filter(pl.col("eligible_at_cutoff")).height
    rows = []
    for policy in ["ex_ante", "clean_future"]:
        valid = outcomes.filter(
            pl.col("eligible_at_cutoff")
            & pl.col("target_observable")
            & pl.col("target_interpretable")
        )
        if policy == "clean_future":
            valid = valid.filter(pl.col("future_quality_status") == "clean")
        for candidate in lock["candidates"]:
            feature = candidate["canonical_feature"]
            joined = features.filter(pl.col("feature_id") == feature).join(
                valid.select("entity_id", "target_value"),
                on="entity_id",
                how="inner",
                validate="1:1",
            )
            stats = statistics(
                joined["feature_value"].to_numpy().astype(float),
                joined["target_value"].to_numpy().astype(float),
                eligible=eligible,
                minimum_n=settings["minimum_pairs"],
                decile_minimum_n=settings["decile_minimum_pairs"],
            )
            expected = candidate["locked_direction"]
            rows.append(
                {
                    "cutoff": cutoff,
                    "policy": policy,
                    "feature_id": feature,
                    "expected_sign": expected,
                    "oriented_ic": stats["spearman_ic"] * expected
                    if stats["spearman_ic"] is not None
                    else None,
                    "rank_signature": candidate["rank_signature"],
                    "correlation_group": protocol["known_groups"]["correlation_group"][feature],
                    "feature_family": META[feature].family,
                    "historical_window": META[feature].window,
                    **{tier: candidate[tier] for tier in TIERS},
                    **stats,
                }
            )
    return pl.DataFrame(
        rows,
        schema_overrides={
            "spearman_ic": pl.Float64,
            "oriented_ic": pl.Float64,
            "mean_target": pl.Float64,
            "positive_target_rate": pl.Float64,
            "decile_spread": pl.Float64,
        },
    )


def prediction_metrics(
    scores: pl.DataFrame, outcomes: pl.DataFrame, past_majority: int, cutoff: str
) -> pl.DataFrame:
    rows = []
    for policy in ["ex_ante", "clean_future"]:
        valid = outcomes.filter(
            pl.col("eligible_at_cutoff")
            & pl.col("target_observable")
            & pl.col("target_interpretable")
        )
        if policy == "clean_future":
            valid = valid.filter(pl.col("future_quality_status") == "clean")
        y_all = valid["target_value"].to_numpy().astype(float)
        binary = y_all[y_all != 0] > 0
        rows.append(
            {
                "cutoff": cutoff,
                "policy": policy,
                "method": "baseline_population",
                "n": len(y_all),
                "spearman_ic": None,
                "auc": None,
                "accuracy": float(binary.mean()) if len(binary) else None,
                "balanced_accuracy": 0.5 if np.unique(binary).size == 2 else None,
                "positive_target_rate": float(binary.mean()) if len(binary) else None,
                "majority_at_T_accuracy": float((binary == (past_majority > 0)).mean())
                if len(binary)
                else None,
                "top_quintile_lift": None,
                "top_quintile_n": 0,
                "neutral_target_count": int((y_all == 0).sum()),
            }
        )
        aligned = scores.join(valid.select("entity_id", "target_value"), on="entity_id")
        for method in ["equal_weight_oriented_rank", "strict_consensus"]:
            part = aligned.filter(pl.col(method).is_not_null())
            x, y = part[method].to_numpy(), part["target_value"].to_numpy()
            nonzero = y != 0
            xb, yb = x[nonzero], y[nonzero] > 0
            both = np.unique(yb).size == 2
            top = xb >= np.quantile(xb, 0.8) if len(xb) else np.zeros(0, dtype=bool)
            positive = float(yb.mean()) if len(yb) else None
            rows.append(
                {
                    "cutoff": cutoff,
                    "policy": policy,
                    "method": method,
                    "n": len(y),
                    "spearman_ic": finite_float(spearmanr(x, y).statistic)
                    if len(y) >= 30 and np.ptp(x) > 0 and np.ptp(y) > 0
                    else None,
                    "auc": float(roc_auc_score(yb, xb)) if both else None,
                    "accuracy": float(((xb > 0.5) == yb).mean()) if len(yb) else None,
                    "balanced_accuracy": float(balanced_accuracy_score(yb, xb > 0.5))
                    if both
                    else None,
                    "positive_target_rate": positive,
                    "majority_at_T_accuracy": None,
                    "top_quintile_lift": float(yb[top].mean() / positive)
                    if positive and top.any()
                    else None,
                    "top_quintile_n": int(top.sum()),
                    "neutral_target_count": int((y == 0).sum()),
                }
            )
    return pl.DataFrame(
        rows,
        schema_overrides={
            k: pl.Float64
            for k in [
                "spearman_ic",
                "auc",
                "accuracy",
                "balanced_accuracy",
                "positive_target_rate",
                "majority_at_T_accuracy",
                "top_quintile_lift",
            ]
        },
    )


def individual_intervals(prefix: pl.DataFrame, settings: dict[str, Any], step: int) -> pl.DataFrame:
    """Pointwise candidate intervals with the same temporal draws, never candidate resampling."""
    rows = []
    for policy in ["ex_ante", "clean_future"]:
        panel = (
            prefix.filter(pl.col("policy") == policy)
            .pivot(on="feature_id", index="cutoff", values="oriented_ic")
            .sort("cutoff")
        )
        ids = [c for c in panel.columns if c != "cutoff"]
        values = panel.select(ids).to_numpy().astype(float)
        complete = np.isfinite(values).all(axis=0)
        selected = [f for f, ok in zip(ids, complete, strict=True) if ok]
        if not selected:
            continue
        bounds = []
        supports = []
        for block in settings["bootstrap_blocks"]:
            draws = draw_means(
                values[:, complete],
                block=block,
                replicates=settings["bootstrap_replicates"],
                seed=settings["bootstrap_seed"] + step + block,
            )
            bounds.append(np.quantile(draws, [0.05, 0.95], axis=0))
            supports.append((draws > 0).mean(axis=0))
        lower = np.min(np.asarray(bounds)[:, 0, :], axis=0)
        upper = np.max(np.asarray(bounds)[:, 1, :], axis=0)
        support = np.min(np.asarray(supports), axis=0)
        for i, feature_id in enumerate(selected):
            rows.append(
                {
                    "policy": policy,
                    "feature_id": feature_id,
                    "oriented_ci90_lower": float(lower[i]),
                    "oriented_ci90_upper": float(upper[i]),
                    "expected_sign_bootstrap_support": float(support[i]),
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "policy": pl.String,
            "feature_id": pl.String,
            "oriented_ci90_lower": pl.Float64,
            "oriented_ci90_upper": pl.Float64,
            "expected_sign_bootstrap_support": pl.Float64,
        },
    )


def cumulative_tables(
    history: pl.DataFrame, protocol: dict[str, Any]
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """All prefixes and all candidates stay in the projections; no performance sorting."""
    candidates, cohorts, groups, intervals = [], [], [], []
    settings = protocol["settings"]
    dates = sorted(history["cutoff"].unique().to_list())
    for step, cutoff in enumerate(dates, start=1):
        prefix = history.filter(pl.col("cutoff") <= cutoff)
        candidate = (
            prefix.group_by(["policy", "feature_id"], maintain_order=True)
            .agg(
                pl.col("expected_sign").first(),
                pl.col("rank_signature").first(),
                pl.col("correlation_group").first(),
                pl.col("feature_family").first(),
                pl.col("historical_window").first(),
                *[pl.col(t).first() for t in TIERS],
                pl.col("spearman_ic").count().alias("observed_ic_cutoffs"),
                pl.col("spearman_ic").mean().alias("mean_ic"),
                pl.col("spearman_ic").median().alias("median_ic"),
                pl.col("spearman_ic").std().alias("std_ic"),
                pl.col("oriented_ic").mean().alias("mean_oriented_ic"),
                (pl.col("oriented_ic") > 0).sum().alias("sign_agreement_count"),
                pl.col("oriented_ic")
                .tail(settings["rolling_cutoffs"])
                .mean()
                .alias("rolling_mean"),
                pl.col("decile_spread").mean().alias("mean_decile_spread"),
                pl.col("coverage").mean().alias("mean_coverage"),
            )
            .with_columns(
                pl.lit(step).alias("mature_cutoffs"),
                pl.lit(cutoff).alias("cutoff"),
                (pl.col("sign_agreement_count") / pl.col("observed_ic_cutoffs"))
                .fill_nan(None)
                .alias("cumulative_sign_agreement"),
            )
            .sort(["policy", "feature_id"])
        )
        if step in settings["checkpoints"]:
            bounds = individual_intervals(prefix, settings, step)
            candidate = candidate.join(bounds, on=["policy", "feature_id"], how="left")
        else:
            candidate = candidate.with_columns(
                *[
                    pl.lit(None, dtype=pl.Float64).alias(c)
                    for c in [
                        "oriented_ci90_lower",
                        "oriented_ci90_upper",
                        "expected_sign_bootstrap_support",
                    ]
                ]
            )
        candidates.append(candidate)
        for policy in ["ex_ante", "clean_future"]:
            for tier in TIERS:
                part = candidate.filter((pl.col("policy") == policy) & pl.col(tier))
                values = part["mean_oriented_ic"].drop_nulls().to_numpy()
                positive = int((values > 0).sum())
                mean = float(values.mean()) if len(values) else None
                median = float(np.median(values)) if len(values) else None
                quantiles = np.quantile(values, [0.25, 0.75]) if len(values) else [None, None]
                row = {
                    "cutoff": cutoff,
                    "mature_cutoffs": step,
                    "policy": policy,
                    "tier": tier,
                    "candidate_count": part.height,
                    "observed_candidates": len(values),
                    "unknown_candidates": part.height - len(values),
                    "sign_conforming": positive,
                    "positive_fraction": positive / part.height,
                    "mean_oriented_ic": mean,
                    "median_oriented_ic": median,
                    "q25": quantiles[0],
                    "q75": quantiles[1],
                    "strongly_inverted": int((values <= -settings["strong_inversion_ic"]).sum()),
                    "checkpoint": step in settings["checkpoints"],
                    "verdict": verdict(step, mean, median, positive / part.height),
                    "ci90_lower": None,
                    "ci90_upper": None,
                    "inference_status": "descriptive_only" if step < 8 else "between_checkpoints",
                }
                tier_history = prefix.filter((pl.col("policy") == policy) & pl.col(tier))
                time = (
                    tier_history.group_by("cutoff")
                    .agg(
                        pl.col("oriented_ic").mean().alias("ic"),
                        pl.col("oriented_ic").count().alias("n"),
                    )
                    .sort("cutoff")
                )
                complete = (
                    time["n"]
                    >= math.ceil(part.height * settings["cohort_minimum_candidate_fraction"])
                ).all() and time["ic"].null_count() == 0
                if step in settings["checkpoints"] and complete:
                    lows, highs = [], []
                    for block in settings["bootstrap_blocks"]:
                        draws = draw_means(
                            time["ic"].to_numpy(),
                            block=block,
                            replicates=settings["bootstrap_replicates"],
                            seed=settings["bootstrap_seed"] + step + block,
                        )
                        low, high = np.quantile(draws, [0.05, 0.95])
                        lows.append(float(low))
                        highs.append(float(high))
                        intervals.append(
                            {
                                "cutoff": cutoff,
                                "mature_cutoffs": step,
                                "policy": policy,
                                "tier": tier,
                                "block": block,
                                "ci90_lower": float(low),
                                "ci90_upper": float(high),
                            }
                        )
                    row.update(
                        ci90_lower=min(lows),
                        ci90_upper=max(highs),
                        inference_status="pointwise_block_bootstrap_no_sequential_control",
                    )
                elif step in settings["checkpoints"]:
                    row.update(
                        inference_status="insufficient_complete_temporal_panel",
                        verdict="insufficient_data",
                    )
                cohorts.append(row)
                for key in [
                    "rank_signature",
                    "correlation_group",
                    "feature_family",
                    "historical_window",
                ]:
                    grouped = part.group_by(key).agg(
                        pl.col("mean_oriented_ic").mean().alias("oriented_ic"),
                        pl.len().alias("candidates"),
                    )
                    row[f"equal_group_mean_{key}"] = grouped["oriented_ic"].mean()
                    for group in grouped.to_dicts():
                        groups.append(
                            {
                                "cutoff": cutoff,
                                "mature_cutoffs": step,
                                "policy": policy,
                                "tier": tier,
                                "group_type": key,
                                "group_id": str(group[key]),
                                "mean_oriented_ic": group["oriented_ic"],
                                "candidates": group["candidates"],
                            }
                        )
    return (
        pl.concat(candidates),
        pl.DataFrame(
            cohorts,
            schema_overrides={
                "mean_oriented_ic": pl.Float64,
                "median_oriented_ic": pl.Float64,
                "q25": pl.Float64,
                "q75": pl.Float64,
                "ci90_lower": pl.Float64,
                "ci90_upper": pl.Float64,
            },
        ),
        pl.DataFrame(groups, schema_overrides={"mean_oriented_ic": pl.Float64}),
        pl.DataFrame(
            intervals,
            schema={
                "cutoff": pl.String,
                "mature_cutoffs": pl.Int64,
                "policy": pl.String,
                "tier": pl.String,
                "block": pl.Int64,
                "ci90_lower": pl.Float64,
                "ci90_upper": pl.Float64,
            },
        ),
    )
