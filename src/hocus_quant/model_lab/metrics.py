"""Pooled diagnostics and primary date-local ranking metrics, with explicit ties."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, rankdata, spearmanr
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)


def correlation(x: Any, y: Any, rank: bool = True) -> float | None:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    if good.sum() < 3 or np.ptp(x[good]) == 0 or np.ptp(y[good]) == 0:
        return None
    return float((spearmanr if rank else pearsonr)(x[good], y[good]).statistic)


def evaluate(
    frame: pd.DataFrame, classification: bool, minimum_n: int = 30, threshold: float = 0.5
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    valid = frame[np.isfinite(frame.target_value) & np.isfinite(frame.score)].copy()
    summary: dict[str, Any] = {
        "n": len(valid),
        "prediction_n": len(frame),
        "coverage": len(valid) / max(1, len(frame)),
        "neutral_n": int((valid.target_value == 0).sum()) if classification else 0,
    }
    cutoffs: list[dict[str, Any]] = []
    deciles: list[dict[str, Any]] = []
    calibration: list[dict[str, Any]] = []
    for day, part in valid.groupby("cutoff", sort=True):
        x, y = part.score.to_numpy(), part.target_value.to_numpy()
        ic = correlation(x, y) if len(part) >= minimum_n else None
        ranks = rankdata(x, method="average")
        labels = np.clip(np.ceil(ranks * 10 / len(part)).astype(int), 1, 10)
        avg: list[float] = []
        for q in range(1, 11):
            inside = part.iloc[np.where(labels == q)[0]]
            mean = float(inside.target_value.mean()) if len(inside) else None
            if mean is not None:
                avg.append(mean)
            deciles.append(
                {
                    "cutoff": day,
                    "decile": q,
                    "n": len(inside),
                    "mean_target": mean,
                    "median_target": float(inside.target_value.median()) if len(inside) else None,
                    "positive_rate": float((inside.target_value > 0).mean())
                    if len(inside)
                    else None,
                    "mean_return_abs": float(inside.return_abs.mean()) if len(inside) else None,
                    "mean_score": float(inside.score.mean()) if len(inside) else None,
                }
            )
        means = {r["decile"]: r["mean_target"] for r in deciles if r["cutoff"] == day}
        top, bottom = means.get(10), means.get(1)
        spread = top - bottom if top is not None and bottom is not None else None
        monotonicity = correlation(np.arange(len(avg)), avg) if len(avg) >= 3 else None
        row = {
            "cutoff": day,
            "n": len(part),
            "ic": ic,
            "spread": spread,
            "monotonicity": monotonicity,
            "mean_target": float(np.mean(y)),
            "positive_rate": float(np.mean(y > 0)),
        }
        for label, level, upper in [
            ("top10", 0.9, True),
            ("top20", 0.8, True),
            ("bottom10", 0.1, False),
        ]:
            threshold_score = np.quantile(x, level)
            chosen = y[x >= threshold_score] if upper else y[x <= threshold_score]
            rate = float(np.mean(chosen > 0))
            base = float(np.mean(y > 0))
            row[f"{label}_positive_rate"] = rate
            row[f"{label}_lift"] = rate / base if base > 0 else None
            row[f"{label}_mean_target"] = float(np.mean(chosen))
            row[f"{label}_n"] = len(chosen)
        cutoffs.append(row)
    observed = [r["ic"] for r in cutoffs if r["ic"] is not None]
    summary.update(
        {
            "mean_ic": float(np.mean(observed)) if observed else None,
            "median_ic": float(np.median(observed)) if observed else None,
            "positive_ic_fraction": float(np.mean(np.array(observed) > 0)) if observed else None,
            "std_ic": float(np.std(observed, ddof=1)) if len(observed) > 1 else None,
            "cutoff_n": len(cutoffs),
            "ic_cutoff_n": len(observed),
            "spearman": correlation(valid.score, valid.target_value),
            "pearson": correlation(valid.score, valid.target_value, False),
        }
    )
    for name in ["spread", "monotonicity", "top10_lift", "top20_lift", "bottom10_lift"]:
        values = [r[name] for r in cutoffs if r[name] is not None]
        summary[name] = float(np.mean(values)) if values else None
    if not len(valid):
        return summary, cutoffs, deciles, calibration
    if classification:
        binary = valid[valid.target_value != 0]
        y = (binary.target_value.to_numpy() > 0).astype(int)
        p = np.clip(binary.score.to_numpy(), 1e-7, 1 - 1e-7)
        prediction = (p > threshold).astype(int)
        summary["binary_n"] = len(y)
        if len(y):
            summary.update(
                {
                    "accuracy": float(accuracy_score(y, prediction)),
                    "balanced_accuracy": float(balanced_accuracy_score(y, prediction))
                    if len(np.unique(y)) == 2
                    else None,
                    "roc_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
                    "pr_auc": float(average_precision_score(y, p))
                    if len(np.unique(y)) == 2
                    else None,
                    "log_loss": float(log_loss(y, p, labels=[0, 1])),
                    "brier": float(brier_score_loss(y, p)),
                    "positive_rate": float(y.mean()),
                    "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
                }
            )
            bins = np.clip((p * 10).astype(int), 0, 9)
            for q in range(10):
                keep = bins == q
                calibration.append(
                    {
                        "bin": q,
                        "n": int(keep.sum()),
                        "mean_probability": float(p[keep].mean()) if keep.any() else None,
                        "positive_rate": float(y[keep].mean()) if keep.any() else None,
                    }
                )
            summary["calibration_ece"] = float(
                sum(
                    r["n"] / len(y) * abs(r["mean_probability"] - r["positive_rate"])
                    for r in calibration
                    if r["n"]
                )
            )
    else:
        y, p = valid.target_value.to_numpy(), valid.score.to_numpy()
        summary.update(
            {
                "rmse": float(np.sqrt(mean_squared_error(y, p))),
                "mae": float(mean_absolute_error(y, p)),
                "r2": float(r2_score(y, p)) if len(y) > 1 else None,
            }
        )
    return summary, cutoffs, deciles, calibration


def validation_metric(
    frame: pd.DataFrame, scores: Any, classification: bool, minimum_n: int = 30
) -> float | None:
    """Only the frozen selection metric, for full-feature permutation diagnostics."""
    good = np.isfinite(frame.target_value.to_numpy()) & np.isfinite(scores)
    if classification:
        good &= frame.target_value.to_numpy() != 0
        y = (frame.target_value.to_numpy()[good] > 0).astype(int)
        return float(roc_auc_score(y, np.asarray(scores)[good])) if len(np.unique(y)) == 2 else None
    panel = frame.loc[good, ["cutoff", "target_value"]].copy()
    panel["score"] = np.asarray(scores)[good]
    values = [
        correlation(p.score, p.target_value)
        for _, p in panel.groupby("cutoff")
        if len(p) >= minimum_n
    ]
    finite = [v for v in values if v is not None]
    return float(np.mean(finite)) if finite else None
