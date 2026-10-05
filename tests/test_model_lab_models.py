from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
import pytest

from hocus_quant.model_lab.metrics import evaluate
from hocus_quant.model_lab.models import (
    choose_trial,
    fit_model,
    make_model,
    predict_score,
    prepare_labels,
)


@pytest.mark.parametrize("classification", [True, False])
@pytest.mark.parametrize("kind", ["rf", "xgb", "linear", "naive"])
def test_models_deterministic_missing_reload(tmp_path, classification, kind):
    rng = np.random.default_rng(88)
    x = rng.normal(size=(70, 5))
    x[::7, 0] = np.nan
    x[:, 4] = np.nan
    y = (np.nan_to_num(x[:, 0]) + x[:, 1] > 0).astype(int) if classification else x[:, 1] * 2
    params = {"n_estimators": 6, "max_depth": 2} if kind in {"rf", "xgb"} else {}
    models = [
        fit_model(make_model(kind, params, classification, 12, 1), x, y, classification)
        for _ in range(2)
    ]
    expected = predict_score(models[0], x, classification)
    assert np.isfinite(expected).all()
    np.testing.assert_allclose(expected, predict_score(models[1], x, classification))
    path = tmp_path / "model.joblib"
    joblib.dump(models[0], path)
    np.testing.assert_array_equal(expected, predict_score(joblib.load(path), x, classification))
    assert predict_score(models[0], x[:0], classification).size == 0
    np.testing.assert_allclose(expected[::-1], predict_score(models[0], x[::-1], classification))


def test_preprocessing_train_only():
    x = np.array([[1.0, np.nan], [3.0, 4.0], [5.0, 6.0]])
    model = fit_model(make_model("linear", {}, False, 10), x, np.array([1.0, 2.0, 3.0]), False)
    preprocess = model.named_steps["preprocess"]
    imputer = dict(preprocess.transformer_list)["values"]
    np.testing.assert_allclose(imputer.statistics_, [3.0, 5.0])
    scale_mean = model.named_steps["scaler"].mean_.copy()
    _ = predict_score(model, np.array([[1e9, np.nan], [np.nan, 1e10]]), False)
    np.testing.assert_array_equal(imputer.statistics_, [3.0, 5.0])
    np.testing.assert_array_equal(scale_mean, model.named_steps["scaler"].mean_)


def test_selection_requires_validation_and_excludes_zero():
    with pytest.raises(ValueError, match="validation"):
        choose_trial([{"split": "test", "trial": 0, "roc_auc": 0.99}], True)
    assert (
        choose_trial(
            [
                {"split": "validation", "trial": 0, "roc_auc": 0.51},
                {"split": "validation", "trial": 1, "roc_auc": 0.52},
            ],
            True,
        )["trial"]
        == 1
    )
    keep, y = prepare_labels([-1, 0, 1, np.nan], True)
    assert keep.tolist() == [True, False, True, False]
    assert y.tolist() == [0, 1]


def test_empty_single_class_and_constant_quantiles():
    df = pd.DataFrame(
        {
            "cutoff": ["2026-01-02"] * 35,
            "target_value": [1.0] * 35,
            "score": [0.8] * 35,
            "return_abs": [0.01] * 35,
        }
    )
    metrics, cs, ds, cal = evaluate(df, True)
    assert metrics["roc_auc"] is None and metrics["mean_ic"] is None
    assert cs[0]["ic"] is None
    assert sum(r["n"] for r in ds) == 35
    assert sum(r["n"] > 0 for r in ds) == 1
    assert sum(r["n"] for r in cal) == 35
    assert evaluate(df.iloc[:0], True)[0]["n"] == 0
    model = fit_model(make_model("xgb", {}, True, 1), np.ones((5, 2)), np.ones(5, dtype=int), True)
    assert predict_score(model, np.ones((2, 2)), True).tolist() == [1.0, 1.0]
