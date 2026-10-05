"""Checks of the completed development run; never used to select parameters."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from hocus_quant.model_lab.models import predict_score

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/analysis/spec008-model-lab"


@pytest.fixture
def completed():
    if not (OUTPUT / "summary.json").exists():
        pytest.skip("local SPEC-008 development artefacts are not versioned")
    return json.loads((OUTPUT / "model_registry.json").read_text())


def test_actual_split_and_selection_boundaries(completed):
    registry = completed
    summary = json.loads((OUTPUT / "summary.json").read_text())
    assert summary["model_count"] == 112 and summary["tuning_fits"] == 160
    for model in registry:
        assert len(model["feature_ids"]) == (85 if model["feature_set"] == "strict" else 138)
        assert {day[:4] for day in model["training_dates"]} == {"2024"}
        assert {day[:4] for day in model["validation_dates"]} == {"2025"}
        assert {day[:4] for day in model["final_training_dates"]} == {"2024", "2025"}
        assert {day[:4] for day in model["test_dates"]} == {"2026"}
    trials = pd.read_parquet(OUTPUT / "hyperparameter_results.parquet")
    assert set(trials.split) == {"validation"}
    targets = pd.read_parquet(OUTPUT / "targets.parquet")
    bounds = {"train": "2024-12-31", "validation": "2025-06-30", "test": "2026-06-30"}
    for family in [
        "direction_abs",
        "return_abs",
        "direction_rel",
        "rank_pct",
        "excursion_balance",
        "trend_tstat",
    ]:
        for split, hi in bounds.items():
            used = targets[(targets.split == split) & targets[family].notna()]
            assert pd.to_datetime(used.target_end).max() <= pd.Timestamp(hi)
    censored = targets[targets.purge_reason.str.contains("crosses_boundary")]
    assert len(censored) > 0 and censored.return_abs.isna().all()
    features = pd.read_parquet(OUTPUT / "features.parquet")
    assert len(censored.merge(features, on=["cutoff", "entity_id"])) == len(censored)


def test_actual_model_reload_and_test_prediction_ledger(completed):
    predictions = pd.read_parquet(OUTPUT / "predictions.parquet")
    features = pd.read_parquet(OUTPUT / "features.parquet")
    targets = pd.read_parquet(OUTPUT / "targets.parquet")
    for kind in ["naive", "linear", "rf", "xgb"]:
        r = next(
            m
            for m in completed
            if m["target"] == "direction_abs"
            and m["horizon"] == 5
            and m["feature_set"] == "strict"
            and m["model"] == kind
        )
        stored = joblib.load(OUTPUT / "models" / f"{r['model_id']}.joblib")
        chosen = predictions[
            (predictions.model_id == r["model_id"]) & (predictions.split == "test")
        ]
        # Predictions include all test decision rows, independent of later label validity.
        decision = targets[(targets.horizon == 5) & (targets.split == "test")]
        assert len(chosen) == len(decision)
        sample = chosen.head(40).merge(features, on=["cutoff", "entity_id"], validate="one_to_one")
        replay = predict_score(
            stored["estimator"], sample[stored["feature_ids"]].to_numpy(dtype=float), True
        )
        np.testing.assert_allclose(replay, sample.score.to_numpy(), atol=1e-12)


def test_actual_portfolio_ledger(completed):
    trades = pd.read_parquet(OUTPUT / "backtest_trades.parquet")
    summary = pd.read_parquet(OUTPUT / "backtest_summary.parquet")
    closed = trades[trades.status.isin(["closed", "delayed_missing_exit"])]
    assert (pd.to_datetime(closed.entry_date) > pd.to_datetime(closed.cutoff)).all()
    expected = (closed.exit_price / closed.entry_price) * (1 - closed.cost_bp / 20000) / (
        1 + closed.cost_bp / 20000
    ) - 1
    np.testing.assert_allclose(expected, closed.return_net, atol=1e-12)
    assert (summary.unresolved_exits == 0).all()
    assert set(summary.cost_bp) == {0, 10, 25, 50}
