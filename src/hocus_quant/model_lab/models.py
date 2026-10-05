"""Small validation-only search, train-only transformations, deterministic CPU estimators."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier, XGBRegressor


def is_classifier(family: str) -> bool:
    return family in {"direction_abs", "direction_rel"}


def prepare_labels(y: Any, classification: bool) -> tuple[Any, Any]:
    y = np.asarray(y, dtype=float)
    keep = np.isfinite(y) & ((y != 0) if classification else True)
    return keep, (y[keep] > 0).astype(int) if classification else y[keep]


def grid(config: dict[str, Any], classification: bool) -> dict[str, list[dict[str, Any]]]:
    naive: dict[str, list[dict[str, Any]]] = (
        {"naive": [{}]} if classification else {"naive_mean": [{}], "naive_median": [{}]}
    )
    return {**naive, "linear": [{}], "rf": config["rf_grid"], "xgb": config["xgb_grid"]}


def make_model(
    kind: str, params: dict[str, Any], classification: bool, seed: int, threads: int = 4
) -> Any:
    if kind.startswith("naive"):
        estimator = (
            DummyClassifier(strategy="prior")
            if classification
            else DummyRegressor(strategy="median" if kind == "naive_median" else "mean")
        )
    elif kind == "linear":
        estimator = (
            LogisticRegression(C=1.0, max_iter=2000, random_state=seed)
            if classification
            else Ridge(alpha=10.0)
        )
    elif kind == "rf":
        ctor = RandomForestClassifier if classification else RandomForestRegressor
        estimator = ctor(**params, random_state=seed, n_jobs=threads)
    elif kind == "xgb":
        ctor = XGBClassifier if classification else XGBRegressor
        return ctor(
            **params,
            random_state=seed,
            n_jobs=threads,
            tree_method="hist",
            objective="binary:logistic" if classification else "reg:squarederror",
            eval_metric="logloss" if classification else "rmse",
            importance_type="gain",
        )
    else:
        raise ValueError(kind)
    steps: list[tuple[str, Any]] = [
        (
            "preprocess",
            FeatureUnion(
                [
                    ("values", SimpleImputer(strategy="median", keep_empty_features=True)),
                    ("missing", MissingIndicator(features="all")),
                ]
            ),
        )
    ]
    if kind == "linear":
        steps.append(("scaler", StandardScaler()))
    steps.append(("model", estimator))
    return Pipeline(steps)


def fit_model(model: Any, x: Any, y: Any, classification: bool) -> Any:
    if classification and len(np.unique(y)) < 2:
        # Explicit fallback for degenerate training; never fake an AUC on a single class.
        model = make_model("naive", {}, True, 0)
    model.fit(x, y)
    return model


def predict_score(model: Any, x: Any, classification: bool) -> Any:
    if len(x) == 0:
        return np.asarray([], dtype=float)
    if not classification:
        return np.asarray(model.predict(x), dtype=float)
    probabilities = model.predict_proba(x)
    classes = list(model.classes_)
    return np.asarray(
        probabilities[:, classes.index(1)] if 1 in classes else np.zeros(len(x)), dtype=float
    )


def choose_trial(rows: list[dict[str, Any]], classification: bool) -> dict[str, Any]:
    """Accept validation results only; absence of a usable metric never consults test."""
    if any(r.get("split") != "validation" for r in rows):
        raise ValueError("hyperparameters require validation-only metrics")
    metric = "roc_auc" if classification else "mean_ic"
    return max(
        rows, key=lambda r: (r.get(metric) if r.get(metric) is not None else -np.inf, -r["trial"])
    )


def gain_importance(model: Any, n: int) -> Any:
    estimator = model.named_steps["model"] if isinstance(model, Pipeline) else model
    values = np.asarray(getattr(estimator, "feature_importances_", np.zeros(n)), dtype=float)
    if len(values) == 2 * n:
        return values[:n] + values[n:]
    return values[:n]
