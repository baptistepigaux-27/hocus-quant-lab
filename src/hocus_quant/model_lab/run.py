"""Reproducible SPEC-008 benchmark: validation selection, locked retrain, one test pass."""

from __future__ import annotations

import json
import subprocess
import time
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.backtest import simulate
from hocus_quant.model_lab.data import build_dataset
from hocus_quant.model_lab.metrics import correlation, evaluate, validation_metric
from hocus_quant.model_lab.models import (
    choose_trial,
    fit_model,
    gain_importance,
    grid,
    is_classifier,
    make_model,
    predict_score,
    prepare_labels,
)
from hocus_quant.model_lab.targets import FAMILIES, HORIZONS, target_id


def write_table(path: Path, rows: Any) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    # A typed empty sentinel is readable by DuckDB / the monitor.
    if not len(frame.columns):
        frame = pd.DataFrame({"status": pd.Series(dtype=str)})
    frame.to_parquet(path, index=False)


def code_identity(root: Path) -> dict[str, Any]:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return {
        "code_sha": sha,
        "working_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        ),
        "source_sha256": {
            str(p.relative_to(root)): file_sha(p)
            for p in sorted((root / "src/hocus_quant/model_lab").glob("*.py"))
        },
    }


def run_benchmark(
    root: Path, config_path: Path, output: Path, *, build: bool = False
) -> dict[str, Any]:
    started = time.monotonic()
    config = tomllib.loads(config_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    if build or not (output / "features.parquet").exists():
        build_dataset(root, output, config)
    dataset = json.loads((output / "dataset_manifest.json").read_text())
    for name, checksum in dataset["source_sha256"].items():
        if file_sha(output / name) != checksum:
            raise ValueError("dataset changed after manifest")
    config_sha = fingerprint(config)
    saved = output / "experiment_config.json"
    if saved.exists() and json.loads(saved.read_text()) != config:
        raise ValueError("config changed; use a new output/version")
    saved.write_text(json.dumps(config, indent=2) + "\n")
    fs = json.loads((output / "feature_sets.json").read_text())
    sets = fs["ids"]
    features = pd.read_parquet(output / "features.parquet").sort_values(["cutoff", "entity_id"])
    targets = pd.read_parquet(output / "targets.parquet")
    for frame in [features, targets]:
        frame["cutoff"] = pd.to_datetime(frame.cutoff).dt.date
    registry: list[dict[str, Any]] = []
    trials: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    cutoff_rows: list[dict[str, Any]] = []
    decile_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    (output / "models").mkdir(exist_ok=True)
    metadata = code_identity(root)
    all_task_ids = []
    for horizon in HORIZONS:
        joined = features.merge(
            targets[targets.horizon == horizon], on=["cutoff", "entity_id"], validate="one_to_one"
        )
        for family in FAMILIES:
            classification = is_classifier(family)
            for tier, ids in sets.items():
                task = f"{family}-h{horizon}-{tier}"
                all_task_ids.append(task)
                print(f"START {task}", flush=True)
                data = {
                    split: joined[joined.split == split].sort_values(["cutoff", "entity_id"]).copy()
                    for split in ["train", "validation", "test"]
                }
                for split, df in data.items():
                    df["target_value"] = df[family]
                    keep, y = prepare_labels(df.target_value, classification)
                    coverage_rows.append(
                        {
                            "task": task,
                            "target": family,
                            "target_id": target_id(family, horizon),
                            "horizon": horizon,
                            "feature_set": tier,
                            "split": split,
                            "eligible_rows": len(df),
                            "usable_labels": int(keep.sum()),
                            "neutral_n": int((df.target_value == 0).sum()) if classification else 0,
                            "future_warning_n": int((df.future_quality == "review").sum()),
                            "uninterpretable_n": int((~df.interpretable).sum()),
                            "first_cutoff": str(df.cutoff.min()),
                            "last_cutoff": str(df.cutoff.max()),
                            "last_outcome": str(df.target_end.max()),
                            "cutoff_n": df.cutoff.nunique(),
                            "feature_missing_fraction": float(df[ids].isna().mean().mean()),
                        }
                    )
                train, val, test = data["train"], data["validation"], data["test"]
                train_keep, y_train = prepare_labels(train.target_value, classification)
                x_train = train.loc[train_keep, ids].to_numpy(dtype=float)
                x_val = val[ids].to_numpy(dtype=float)
                selected_models = []
                for kind, parameters in grid(config, classification).items():
                    attempted = []
                    fitted: dict[int, Any] = {}
                    for number, params in enumerate(parameters):
                        model = fit_model(
                            make_model(
                                kind, params, classification, config["seed"], config["threads"]
                            ),
                            x_train,
                            y_train,
                            classification,
                        )
                        vp = val.copy()
                        vp["score"] = predict_score(model, x_val, classification)
                        vm, _, _, _ = evaluate(
                            vp,
                            classification,
                            config["minimum_ic_pairs"],
                            config["classification_threshold"],
                        )
                        row = {
                            "task": task,
                            "kind": kind,
                            "trial": number,
                            "params": json.dumps(params, sort_keys=True),
                            "split": "validation",
                            **vm,
                        }
                        attempted.append(row)
                        trials.append(row)
                        fitted[number] = model
                    best = choose_trial(attempted, classification)
                    params = parameters[best["trial"]]
                    model = fitted[best["trial"]]
                    identity = {
                        "task": task,
                        "kind": kind,
                        "params": params,
                        "config_sha256": config_sha,
                        "dataset": dataset["source_sha256"],
                    }
                    model_id = f"{task}-{kind}-{fingerprint(identity)[:12]}"
                    base = {
                        "model_id": model_id,
                        "task": task,
                        "model": kind,
                        "feature_set": tier,
                        "target": family,
                        "target_id": target_id(family, horizon),
                        "horizon": horizon,
                    }
                    val_prediction = val.copy()
                    val_prediction["score"] = predict_score(model, x_val, classification)
                    if kind in {"rf", "xgb"}:
                        gain = gain_importance(model, len(ids))
                        key = "roc_auc" if classification else "mean_ic"
                        baseline = best.get(key)
                        rng = np.random.default_rng(config["seed"])
                        permutations = []
                        for feature_i in range(len(ids)):
                            changed = x_val.copy()
                            changed[:, feature_i] = changed[
                                rng.permutation(len(changed)), feature_i
                            ]
                            value = validation_metric(
                                val,
                                predict_score(model, changed, classification),
                                classification,
                                config["minimum_ic_pairs"],
                            )
                            permutations.append(
                                baseline - value
                                if baseline is not None and value is not None
                                else None
                            )
                            if len(ids) > 138 and (feature_i + 1) % 256 == 0:
                                print(
                                    f"PERMUTATION {task} {kind}: {feature_i + 1}/{len(ids)}",
                                    flush=True,
                                )
                        for name, g, p in zip(ids, gain, permutations, strict=True):
                            importance_rows.append(
                                {
                                    **base,
                                    "feature_id": name,
                                    "gain_or_impurity": float(g),
                                    "importance_type": "gain" if kind == "xgb" else "impurity",
                                    "validation_permutation_drop": p,
                                    "permutation_metric": key,
                                    "permutation_repeats": 1,
                                    "importance_fit": "2024_train_only",
                                }
                            )
                    selected_models.append(
                        {
                            **base,
                            "validation_selection_metric": best.get(
                                "roc_auc" if classification else "mean_ic"
                            ),
                            "params": params,
                        }
                    )
                    # Fresh preprocessing on declared 2024+S1 2025 final training only.
                    retrain = pd.concat([train, val], ignore_index=True)
                    final_keep, y_final = prepare_labels(retrain.target_value, classification)
                    final = fit_model(
                        make_model(kind, params, classification, config["seed"], config["threads"]),
                        retrain.loc[final_keep, ids].to_numpy(dtype=float),
                        y_final,
                        classification,
                    )
                    model_path = output / "models" / f"{model_id}.joblib"
                    joblib.dump(
                        {
                            "estimator": final,
                            "feature_ids": ids,
                            "classification": classification,
                            "metadata": base,
                        },
                        model_path,
                        compress=3,
                    )
                    predicted = test.copy()
                    predicted["score"] = predict_score(
                        final, test[ids].to_numpy(dtype=float), classification
                    )
                    for split, df in [("validation", val_prediction), ("test", predicted)]:
                        result, cs, ds, cal = evaluate(
                            df,
                            classification,
                            config["minimum_ic_pairs"],
                            config["classification_threshold"],
                        )
                        metric_rows.append({**base, "split": split, **result})
                        cutoff_rows.extend({**base, "split": split, **r} for r in cs)
                        decile_rows.extend({**base, "split": split, **r} for r in ds)
                        calibration_rows.extend({**base, "split": split, **r} for r in cal)
                        pred = df[
                            [
                                "cutoff",
                                "entity_id",
                                "target_value",
                                "score",
                                "return_abs",
                                "excursion_balance",
                                "trend_tstat",
                                "volatility",
                                "max_upside",
                                "max_downside",
                                "future_quality",
                                "target_end",
                            ]
                        ].copy()
                        for k, v in {**base, "split": split}.items():
                            pred[k] = v
                        prediction_frames.append(pred)
                    registry.append(
                        {
                            **base,
                            "seed": config["seed"],
                            "hyperparameters": params,
                            "training_dates": sorted(map(str, train.cutoff.unique())),
                            "validation_dates": sorted(map(str, val.cutoff.unique())),
                            "final_training_dates": sorted(map(str, retrain.cutoff.unique())),
                            "test_dates": sorted(map(str, test.cutoff.unique())),
                            "feature_ids": ids,
                            "lock_sha256": fs["lock_sha256"],
                            "feature_registry_sha256": fs.get("feature_registry_sha256"),
                            "data_fingerprints": dataset["source_sha256"],
                            "config_sha256": config_sha,
                            "model_sha256": file_sha(model_path),
                            "validation_metric": best.get(
                                "roc_auc" if classification else "mean_ic"
                            ),
                            **metadata,
                        }
                    )
                    print(f"DONE {task} {kind}", flush=True)
                # Chosen BEFORE any comparison of test metrics, based on validation only.
                finite = [
                    r for r in selected_models if r["validation_selection_metric"] is not None
                ]
                winner = (
                    max(finite, key=lambda r: r["validation_selection_metric"])
                    if finite
                    else selected_models[0]
                )
                for entry in registry:
                    if entry["task"] == task:
                        entry["validation_winner_within_feature_set"] = (
                            entry["model_id"] == winner["model_id"]
                        )
                # Progress is inspectable; an interrupted run is never marked complete.
                write_table(output / "hyperparameter_results.parquet", trials)
                write_table(output / "metrics.parquet", metric_rows)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    for name, rows in [
        ("predictions", predictions),
        ("cutoff_metrics", cutoff_rows),
        ("decile_metrics", decile_rows),
        ("calibration", calibration_rows),
        ("feature_importances", importance_rows),
        ("coverage", coverage_rows),
    ]:
        write_table(output / f"{name}.parquet", rows)
    (output / "model_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    test_preds = predictions[predictions.split == "test"]
    # Diagnose overlap and trajectories using scores already fixed.
    trajectory = []
    for model_id, df in test_preds.groupby("model_id", sort=True):
        meta = df.iloc[0][["task", "model", "feature_set", "target", "horizon"]].to_dict()
        previous: set[str] = set()
        turnover = []
        for _, part in df.groupby("cutoff", sort=True):
            top = set(
                part.sort_values(["score", "entity_id"], ascending=[False, True])
                .head(max(1, int(np.ceil(len(part) * 0.1))))
                .entity_id
            )
            if previous:
                turnover.append(1 - len(previous & top) / max(len(previous), len(top)))
            previous = top
        row = {
            "model_id": model_id,
            **meta,
            "potential_top10_replacement": float(np.mean(turnover)) if turnover else None,
        }
        for col in [
            "return_abs",
            "excursion_balance",
            "trend_tstat",
            "volatility",
            "max_upside",
            "max_downside",
        ]:
            row[f"score_vs_{col}"] = correlation(df.score, df[col])
            row[f"truth_vs_{col}"] = correlation(df.target_value, df[col])
        trajectory.append(row)
    write_table(output / "trajectory_diagnostics.parquet", trajectory)
    backtests = run_backtests(output, test_preds, config)
    summary = {
        "version": config["version"],
        "status": "development_complete",
        "development_only": True,
        "config_sha256": config_sha,
        "lock_sha256": fs["lock_sha256"],
        "target_registry_sha256": dataset["target_registry_sha256"],
        "tasks": len(all_task_ids),
        "target_horizon_tasks": 12,
        "feature_sets": {name: len(ids) for name, ids in sets.items()},
        "report_stem": config.get("report_stem", "SPEC_008_RESULTS"),
        "model_count": len(registry),
        "tuning_fits": len(trials),
        "final_retrain_fits": len(registry),
        "package_versions": {
            n: version(n) for n in ["xgboost", "scikit-learn", "numpy", "pandas", "polars"]
        },
        "data_fingerprints": dataset["source_sha256"],
        "backtest_count": len(backtests),
        "elapsed_seconds": time.monotonic() - started,
        "pit_grade": "reconstructed",
        "strict_pit_claimed": False,
        "independent_confirmation": False,
        "selection_contamination": dataset["selection_contamination"],
        **metadata,
    }
    summary["artifact_sha256"] = {p.name: file_sha(p) for p in sorted(output.glob("*.parquet"))}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_backtests(
    output: Path, predictions: pd.DataFrame, config: dict[str, Any]
) -> list[dict[str, Any]]:
    market = pd.read_parquet(output / "source_market.parquet")
    bench = pd.read_parquet(output / "source_benchmark.parquet")
    for df in [market, bench]:
        df["session_date"] = pd.to_datetime(df.session_date).dt.date
    from datetime import date

    lo, hi = date.fromisoformat(config["test_start"]), date.fromisoformat(config["test_end"])
    market = market[(market.session_date >= lo) & (market.session_date <= hi)]
    bench = bench[(bench.session_date >= lo) & (bench.session_date <= hi)]
    equities = []
    trades = []
    results = []
    jobs = [(str(mid), part, False) for mid, part in predictions.groupby("model_id", sort=True)]
    for h in HORIZONS:
        ref = next(part for _, part in predictions[predictions.horizon == h].groupby("model_id"))
        jobs.append((f"equal_weight_universe-h{h}", ref, True))
    for mid, part, universe in jobs:
        h = int(part.horizon.iloc[0])
        for cost in config["costs_round_trip_bp"]:
            eq, tr, stats = simulate(
                part,
                market,
                bench,
                h,
                cost,
                config[f"portfolio_sleeves_h{h}"],
                universe=universe,
                fraction=config["portfolio_top_fraction"],
                end=hi,
            )
            info = {
                "model_id": mid,
                "cost_bp": cost,
                "target": "universe" if universe else part.target.iloc[0],
                "model": "universe" if universe else part.model.iloc[0],
                "feature_set": "all" if universe else part.feature_set.iloc[0],
                "horizon": h,
            }
            for df in [eq, tr]:
                for k, v in info.items():
                    df[k] = v
            equities.append(eq)
            trades.append(tr)
            results.append({**info, **stats})
        print(f"BACKTEST {mid}", flush=True)
    write_table(output / "backtest_equity.parquet", pd.concat(equities, ignore_index=True))
    write_table(output / "backtest_trades.parquet", pd.concat(trades, ignore_index=True))
    write_table(output / "backtest_summary.parquet", results)
    return results
