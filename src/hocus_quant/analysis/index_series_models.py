"""Independent daily time-series forecasters, one fitted index per model."""

from __future__ import annotations

import json
import math
import tomllib
from bisect import bisect_right
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.data import split_assignment
from hocus_quant.model_lab.models import fit_model, make_model, predict_score
from hocus_quant.model_lab.report import table


def features(close: pd.Series[Any]) -> pd.DataFrame:
    """All operations are backward-looking on the reference-session grid."""
    r = close.pct_change(fill_method=None)
    lr = np.log(close).diff()
    values = {f"return_lag_{lag}": r.shift(lag) for lag in [0, 1, 2]}
    for w in [3, 5, 10, 20, 60, 120]:
        full = close.rolling(w + 1).count() == w + 1
        values[f"momentum_{w}"] = (close / close.shift(w) - 1).where(full)
    for w in [5, 10, 20, 60]:
        values[f"volatility_{w}"] = lr.rolling(w).std(ddof=1) * math.sqrt(252)
    for w in [5, 20, 60, 120]:
        values[f"ma_distance_{w}"] = close / close.rolling(w).mean() - 1
    for w in [20, 60]:
        lo, hi = close.rolling(w).min(), close.rolling(w).max()
        values[f"drawdown_{w}"] = close / hi - 1
        values[f"range_position_{w}"] = ((close - lo) / (hi - lo)).where(hi != lo, 0.5)
    gain, loss = r.clip(lower=0).rolling(14).mean(), (-r).clip(lower=0).rolling(14).mean()
    values["rsi_simple_14"] = (gain / (gain + loss)).where(gain + loss != 0, 0.5)
    frame = pd.DataFrame(values)
    assert len(frame.columns) == 22
    return frame.replace([np.inf, -np.inf], np.nan)


def settings(root: Path, path: Path) -> tuple[dict[str, Any], Path]:
    config = tomllib.loads(path.read_text())
    return config, root / config["output_path"]


def prepare(root: Path, config_path: Path) -> dict[str, Any]:
    config, output = settings(root, config_path)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "dataset_manifest.json").exists():
        raise ValueError("Frozen dataset exists; use a new experiment version")
    source = root / config["source_path"]
    parent = json.loads((source.parent / "dataset_manifest.json").read_text())
    assert file_sha(source) == parent["source_sha256"][source.name]
    bars = pd.read_parquet(source)
    bars = bars[bars.provider_instrument_id.isin(config["codes"])].copy()
    assert set(bars.provider_instrument_id) == set(config["codes"])
    assert not bars.duplicated(["provider_instrument_id", "session_date"]).any()
    expected = (pd.to_datetime(bars.session_date) + pd.Timedelta(days=1)).dt.tz_localize("UTC")
    assert (pd.to_datetime(bars.available_at) == expected).all()
    bars.to_parquet(output / "source_selected.parquet", index=False)
    calendar = sorted(bars[bars.provider_instrument_id == "FR0003500008"].session_date.unique())
    (output / "calendar.json").write_text(json.dumps(list(map(str, calendar))) + "\n")
    indices, matrices, targets = [], [], []
    for code in config["codes"]:
        part = bars[bars.provider_instrument_id == code].sort_values("session_date")
        name = str(part.display_name.iloc[0])
        indices.append({"index_code": code, "index_name": name})
        native_dates, native_close = part.session_date.tolist(), part.close.tolist()
        aligned, quote_dates, ages = [], [], []
        for day in calendar:
            pos = bisect_right(native_dates, day) - 1
            quote_day = native_dates[pos] if pos >= 0 else None
            age = (day - quote_day).days if quote_day is not None else None
            value = native_close[pos] if pos >= 0 else np.nan
            valid = (
                age is not None
                and age <= config["maximum_quote_age_days"]
                and np.isfinite(value)
                and value > 0
            )
            aligned.append(value if valid else np.nan)
            quote_dates.append(quote_day)
            ages.append(age)
        close = pd.Series(aligned, dtype=float)
        matrix = features(close)
        for i, day in enumerate(calendar):
            declared = any(
                date.fromisoformat(config[f"{split}_start"])
                <= day
                <= date.fromisoformat(config[f"{split}_end"])
                for split in ["train", "validation", "test"]
            )
            if not declared:
                continue
            meta = {
                "index_code": code,
                "index_name": name,
                "cutoff": day,
                "reference_quote_date": quote_dates[i],
                "quote_age_days": ages[i],
                "reference_close": close.iloc[i],
                "eligible_at_T": bool(np.isfinite(close.iloc[i])),
                "past_jump_review": bool(abs(matrix.return_lag_0.iloc[i]) >= 0.3),
            }
            matrices.append({**meta, **matrix.iloc[i].to_dict()})
            for h in config["horizons"]:
                path = close.iloc[i : i + h + 1].to_numpy()
                complete = len(path) == h + 1 and np.isfinite(path).all() and (path > 0).all()
                end = calendar[i + h] if i + h < len(calendar) else None
                split, reason = split_assignment(day, end, h, calendar, config)
                ret = float(path[-1] / path[0] - 1) if complete else np.nan
                vol = (
                    float(np.std(np.diff(np.log(path)), ddof=1) * math.sqrt(252))
                    if complete
                    else np.nan
                )
                admitted = complete and reason == "accepted"
                targets.append(
                    {
                        "index_code": code,
                        "cutoff": day,
                        "horizon": h,
                        "split": split,
                        "target_end": end,
                        "index_quote_end": quote_dates[i + h] if end else None,
                        "calendar_complete": bool(complete),
                        "purge_reason": reason,
                        "label_status": "observed"
                        if admitted
                        else reason
                        if reason != "accepted"
                        else "future_quote_missing",
                        "return": ret if admitted else np.nan,
                        "direction": float(np.sign(ret)) if admitted else np.nan,
                        "volatility": vol if admitted else np.nan,
                    }
                )
    pd.DataFrame(matrices).to_parquet(output / "features.parquet", index=False)
    pd.DataFrame(targets).to_parquet(output / "targets.parquet", index=False)
    ids = list(features(pd.Series([1.0, 2.0, 3.0])).columns)
    (output / "feature_registry.json").write_text(
        json.dumps(
            {
                "version": config["version"],
                "ids": ids,
                "definition": "22 backward-only close features on reference sessions; see contract",
            },
            indent=2,
        )
        + "\n"
    )
    (output / "experiment_config.json").write_text(json.dumps(config, indent=2) + "\n")
    manifest = {
        "version": config["version"],
        "config_sha256": fingerprint(config),
        "parent_source_sha256": file_sha(source),
        "parent_dataset": str(source.parent),
        "indices": indices,
        "feature_ids": ids,
        "pooling": False,
        "pit_grade": "reconstructed",
        "independent_confirmation": False,
        "source_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
        "feature_generator_sha256": file_sha(Path(__file__)),
    }
    (output / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    audit_dataset(output, config)
    return manifest


def audit_dataset(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    for name, sha in manifest["source_sha256"].items():
        assert file_sha(output / name) == sha, name
    bars = pd.read_parquet(output / "source_selected.parquet")
    matrix = pd.read_parquet(output / "features.parquet")
    targets = pd.read_parquet(output / "targets.parquet")
    joined = targets.merge(matrix, on=["index_code", "cutoff"], validate="many_to_one")
    calendar = [date.fromisoformat(d) for d in json.loads((output / "calendar.json").read_text())]
    errors, vol_errors = [], []
    for code, part in bars.groupby("provider_instrument_id"):
        source = part.sort_values("session_date")
        days, closes = source.session_date.tolist(), source.close.tolist()
        for row in joined[(joined.index_code == code) & joined["return"].notna()].itertuples():
            # 'return' is a Python keyword, so use the source frame for the label below.
            start = bisect_right(days, row.cutoff) - 1
            assert days[start] == row.reference_quote_date <= row.cutoff
            assert closes[start] == row.reference_close
            pos = calendar.index(row.cutoff)
            path_days = calendar[pos : pos + row.horizon + 1]
            assert path_days[-1] == row.target_end
            positions = [bisect_right(days, d) - 1 for d in path_days]
            assert all(
                d - days[i] <= timedelta(days=3) for d, i in zip(path_days, positions, strict=True)
            )
            path = np.array([closes[i] for i in positions])
            label = joined.loc[row.Index, "return"]
            errors.append(abs(path[-1] / path[0] - 1 - label))
            vol_errors.append(
                abs(np.std(np.diff(np.log(path)), ddof=1) * math.sqrt(252) - row.volatility)
            )
    assert errors and max(errors) < 1e-12 and max(vol_errors) < 1e-12
    for split in ["train", "validation", "test"]:
        good = joined[(joined.split == split) & joined["return"].notna()]
        assert (pd.to_datetime(good.target_end) <= pd.Timestamp(config[f"{split}_end"])).all()
    # Prefix recalculation: later prices cannot alter any feature already emitted.
    calendar_index = pd.Index(calendar)
    differences = []
    for code, source in bars.groupby("provider_instrument_id"):
        source = source.sort_values("session_date")
        days, prices = source.session_date.tolist(), source.close.tolist()
        aligned = []
        for day in calendar:
            i = bisect_right(days, day) - 1
            aligned.append(prices[i] if i >= 0 and (day - days[i]).days <= 3 else np.nan)
        for row in (
            matrix[matrix.index_code == code].sample(10, random_state=config["seed"]).itertuples()
        ):
            i = calendar_index.get_loc(row.cutoff)
            prefix = features(pd.Series(aligned[: i + 1])).iloc[-1]
            saved = matrix.loc[row.Index, manifest["feature_ids"]].to_numpy(dtype=float)
            assert np.array_equal(np.isnan(prefix.to_numpy()), np.isnan(saved))
            differences.extend(
                np.abs(prefix.to_numpy()[np.isfinite(saved)] - saved[np.isfinite(saved)])
            )
    assert not differences or max(differences) < 1e-12
    receipt = {
        "status": "dataset_reconciled",
        "return_checks": len(errors),
        "max_return_difference": float(max(errors)),
        "max_volatility_difference": float(max(vol_errors)),
        "feature_prefix_checks": len(config["codes"]) * 10,
        "max_feature_prefix_difference": float(max(differences)),
    }
    (output / "dataset_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def labels(frame: pd.DataFrame, target: str) -> tuple[Any, Any]:
    y = frame[target].to_numpy(dtype=float)
    keep = np.isfinite(y) & ((y != 0) if target == "direction" else True)
    return keep, (y[keep] > 0).astype(int) if target == "direction" else y[keep]


def reference(frame: pd.DataFrame, target: str, h: int, y_train: Any) -> Any:
    if target == "direction":
        return np.full(len(frame), float(np.mean(y_train)))
    if target == "return":
        return np.zeros(len(frame))
    return frame[f"volatility_{h}"].fillna(float(np.mean(y_train))).to_numpy(dtype=float)


def score(
    model: Any, kind: str, frame: pd.DataFrame, ids: list[str], target: str, h: int, fallback: float
) -> Any:
    if kind == "zero":
        value = np.zeros(len(frame))
    elif kind == "historical_vol":
        value = frame[f"volatility_{h}"].fillna(fallback).to_numpy(dtype=float)
    else:
        value = predict_score(model, frame[ids].to_numpy(dtype=float), target == "direction")
    return np.maximum(value, 0) if target == "volatility" else value


def metric(frame: pd.DataFrame, target: str) -> dict[str, Any]:
    good, y = labels(frame, target)
    p, base = (
        frame.score.to_numpy(dtype=float)[good],
        frame.reference_score.to_numpy(dtype=float)[good],
    )
    if not len(y):
        raise ValueError("No observed labels")
    corr = float(spearmanr(p, y).statistic) if np.ptp(p) > 0 and np.ptp(y) > 0 else None
    result = {
        "n": len(y),
        "prediction_n": len(frame),
        "coverage": len(y) / len(frame),
        "temporal_spearman": corr,
    }
    if target == "direction":
        p, base = np.clip(p, 1e-7, 1 - 1e-7), np.clip(base, 1e-7, 1 - 1e-7)
        loss = float(log_loss(y, p, labels=[0, 1]))
        baseline = float(log_loss(y, base, labels=[0, 1]))
        result.update(
            roc_auc=float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
            log_loss=loss,
            reference_loss=baseline,
            skill=1 - loss / baseline,
            brier=float(brier_score_loss(y, p)),
            accuracy=float(accuracy_score(y, p > 0.5)),
            balanced_accuracy=float(balanced_accuracy_score(y, p > 0.5)),
            positive_rate=float(np.mean(y)),
        )
    else:
        mse, baseline = float(mean_squared_error(y, p)), float(mean_squared_error(y, base))
        result.update(
            rmse=math.sqrt(mse),
            mae=float(mean_absolute_error(y, p)),
            r2=float(r2_score(y, p)),
            reference_loss=baseline,
            reference_rmse=math.sqrt(baseline),
            skill=1 - mse / baseline if baseline else None,
        )
    return result


def candidate_grid(config: dict[str, Any], target: str) -> dict[str, list[dict[str, Any]]]:
    baselines: dict[str, list[dict[str, Any]]] = (
        {"naive": [{}]}
        if target == "direction"
        else {
            "zero" if target == "return" else "historical_vol": [{}],
            "naive_mean": [{}],
        }
    )
    params = (
        [{"C": c} for c in config["linear_classification_C"]]
        if target == "direction"
        else [{"alpha": a} for a in config["linear_regression_alpha"]]
    )
    return {**baselines, "linear": params, "rf": config["rf_grid"], "xgb": config["xgb_grid"]}


def estimator(kind: str, params: dict[str, Any], target: str, config: dict[str, Any]) -> Any:
    if kind in {"zero", "historical_vol"}:
        return None
    obj = make_model(
        kind,
        {} if kind == "linear" else params,
        target == "direction",
        config["seed"],
        config["threads"],
    )
    if kind == "linear":
        obj.named_steps["model"].set_params(**params)
    return obj


def run(root: Path, config_path: Path) -> dict[str, Any]:
    config, output = settings(root, config_path)
    if (output / "summary.json").exists():
        raise ValueError("Completed benchmark exists; preserve it")
    audit_dataset(output, config)
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    assert fingerprint(config) == manifest["config_sha256"]
    ids = manifest["feature_ids"]
    matrix = pd.read_parquet(output / "features.parquet")
    targets = pd.read_parquet(output / "targets.parquet")
    data = matrix.merge(targets, on=["index_code", "cutoff"], validate="one_to_many")
    data = data[data.eligible_at_T]
    registry, trials, metrics, forecasts = [], [], [], []
    fitting_count = 0
    (output / "models").mkdir(exist_ok=True)
    for code in config["codes"]:
        for h in config["horizons"]:
            for target in config["targets"]:
                print(f"START {code} H{h} {target}", flush=True)
                panel = data[(data.index_code == code) & (data.horizon == h)].sort_values("cutoff")
                split_frames = {
                    s: panel[panel.split == s].copy() for s in ["train", "validation", "test"]
                }
                train, val, test = (split_frames[s] for s in ["train", "validation", "test"])
                keep, y_train = labels(train, target)
                vk, _ = labels(val, target)
                assert (
                    keep.sum() >= config["minimum_training_labels"]
                    and vk.sum() >= config["minimum_validation_labels"]
                )
                retrain = pd.concat([train, val], ignore_index=True)
                final_keep, y_final = labels(retrain, target)
                task_entries = []
                for kind, grid in candidate_grid(config, target).items():
                    candidates = []
                    for trial_i, params in enumerate(grid):
                        obj = estimator(kind, params, target, config)
                        if obj is not None:
                            obj = fit_model(
                                obj,
                                train.loc[keep, ids].to_numpy(dtype=float),
                                y_train,
                                target == "direction",
                            )
                            fitting_count += 1
                        prediction = val.copy()
                        prediction["score"] = score(
                            obj, kind, val, ids, target, h, float(np.mean(y_train))
                        )
                        prediction["reference_score"] = reference(val, target, h, y_train)
                        measured = metric(prediction, target)
                        loss = measured["log_loss" if target == "direction" else "rmse"]
                        candidates.append((loss, trial_i, params, prediction, measured))
                        trials.append(
                            {
                                "index_code": code,
                                "target": target,
                                "horizon": h,
                                "model": kind,
                                "trial": trial_i,
                                "params": json.dumps(params),
                                "validation_selection_loss": loss,
                                **measured,
                            }
                        )
                    _, _, params, validation_prediction, vm = min(
                        candidates, key=lambda x: (x[0], x[1])
                    )
                    mid = (
                        f"{code}-{target}-h{h}-{kind}-"
                        + fingerprint({"config": manifest["config_sha256"], "params": params})[:12]
                    )
                    final = estimator(kind, params, target, config)
                    if final is not None:
                        final = fit_model(
                            final,
                            retrain.loc[final_keep, ids].to_numpy(dtype=float),
                            y_final,
                            target == "direction",
                        )
                    artifact = output / "models" / f"{mid}.joblib"
                    joblib.dump(
                        {
                            "estimator": final,
                            "index_code": code,
                            "feature_ids": ids,
                            "target": target,
                            "horizon": h,
                            "kind": kind,
                            "fallback": float(np.mean(y_final)),
                        },
                        artifact,
                        compress=3,
                    )
                    test_prediction = test.copy()
                    test_prediction["score"] = score(
                        final, kind, test, ids, target, h, float(np.mean(y_final))
                    )
                    test_prediction["reference_score"] = reference(test, target, h, y_final)
                    base = {
                        "model_id": mid,
                        "index_code": code,
                        "index_name": str(train.index_name.iloc[0]),
                        "target": target,
                        "horizon": h,
                        "model": kind,
                    }
                    for split, prediction in [
                        ("validation", validation_prediction),
                        ("test", test_prediction),
                    ]:
                        measured = metric(prediction, target)
                        metrics.append({**base, "split": split, **measured})
                        prediction = prediction[
                            [
                                "cutoff",
                                "reference_quote_date",
                                "reference_close",
                                "target_end",
                                "index_quote_end",
                                "label_status",
                                target,
                                "score",
                                "reference_score",
                            ]
                        ].rename(columns={target: "target_value"})
                        for key, value in {**base, "split": split}.items():
                            prediction[key] = value
                        forecasts.append(prediction)
                    entry = {
                        **base,
                        "params": params,
                        "validation_selection_loss": vm[
                            "log_loss" if target == "direction" else "rmse"
                        ],
                        "training_indices": sorted(train.index_code.unique().tolist()),
                        "training_labels": int(keep.sum()),
                        "final_training_labels": int(final_keep.sum()),
                        "training_start": str(train.cutoff.min()),
                        "training_end": str(train.cutoff.max()),
                        "final_information_available_at_modeled": "2025-07-01T00:00:00+00:00",
                        "supervised_estimator": final is not None,
                        "model_sha256": file_sha(artifact),
                        "feature_ids": ids,
                        "pooling": False,
                    }
                    registry.append(entry)
                    task_entries.append(entry)
                selected = min(task_entries, key=lambda e: e["validation_selection_loss"])
                for entry in task_entries:
                    entry["validation_winner"] = entry["model_id"] == selected["model_id"]
                pd.DataFrame(metrics).to_parquet(output / "metrics.parquet", index=False)
                print(f"DONE {code} H{h} {target}; winner={selected['model']}", flush=True)
    pd.DataFrame(trials).to_parquet(output / "trials.parquet", index=False)
    pd.concat(forecasts, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    (output / "model_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    summary = {
        "version": config["version"],
        "status": "development_complete",
        "pooling": False,
        "model_count": len(registry),
        "supervised_final_fits": sum(r["supervised_estimator"] for r in registry),
        "validation_fits": fitting_count,
        "validation_evaluations": len(trials),
        "task_count": len(config["codes"]) * 6,
        "source_sha256": {
            str(p.relative_to(root)): file_sha(p)
            for p in [
                Path(__file__),
                root / "src/hocus_quant/model_lab/models.py",
                root / "src/hocus_quant/model_lab/data.py",
            ]
        },
        "artifact_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
        "config_sha256": manifest["config_sha256"],
        "pit_grade": "reconstructed",
        "independent_confirmation": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def bootstrap(
    part: pd.DataFrame, target: str, h: int, config: dict[str, Any], rng: Any
) -> list[dict[str, Any]]:
    ordered = part.sort_values("cutoff")
    truth = ordered.target_value.to_numpy(dtype=float)
    if target == "direction":
        truth = np.where(np.isfinite(truth) & (truth != 0), (truth > 0).astype(float), np.nan)
    score_values, ref = (
        ordered.score.to_numpy(dtype=float),
        ordered.reference_score.to_numpy(dtype=float),
    )
    results = []
    for block in config[f"bootstrap_blocks_h{h}"]:
        n, count = len(truth), config["bootstrap_replicates"]
        starts = rng.integers(0, n, size=(count, math.ceil(n / block)))
        ix = ((starts[..., None] + np.arange(block)) % n).reshape(count, -1)[:, :n]
        y, p, b = truth[ix], score_values[ix], ref[ix]
        good = np.isfinite(y)
        if target == "direction":
            p, b = np.clip(p, 1e-7, 1 - 1e-7), np.clip(b, 1e-7, 1 - 1e-7)
            losses = -(y * np.log(p) + (1 - y) * np.log1p(-p))
            references = -(y * np.log(b) + (1 - y) * np.log1p(-b))
            ranks = rankdata(np.where(good, p, np.nan), axis=1, nan_policy="omit")
            positive, negative = np.sum(y == 1, axis=1), np.sum(y == 0, axis=1)
            denominator = positive * negative
            auc = np.divide(
                np.nansum(np.where(y == 1, ranks, np.nan), axis=1) - positive * (positive + 1) / 2,
                denominator,
                out=np.full(count, np.nan),
                where=denominator > 0,
            )
            primary = auc
            name = "roc_auc"
        else:
            losses, references = (y - p) ** 2, (y - b) ** 2
            yr = rankdata(y, axis=1, nan_policy="omit")
            pr = rankdata(np.where(good, p, np.nan), axis=1, nan_policy="omit")
            yc, pc = yr - np.nanmean(yr, axis=1)[:, None], pr - np.nanmean(pr, axis=1)[:, None]
            denom = np.sqrt(np.nansum(yc**2, axis=1) * np.nansum(pc**2, axis=1))
            primary = np.divide(
                np.nansum(yc * pc, axis=1), denom, out=np.full(count, np.nan), where=denom > 0
            )
            name = "temporal_spearman"
        gain = np.nanmean(references - losses, axis=1)
        finite = primary[np.isfinite(primary)]
        results.append(
            {
                "block_sessions": block,
                "primary_metric": name,
                "primary_lo90": float(np.quantile(finite, 0.05)) if len(finite) else None,
                "primary_hi90": float(np.quantile(finite, 0.95)) if len(finite) else None,
                "loss_advantage_lo90": float(np.quantile(gain, 0.05)),
                "loss_advantage_hi90": float(np.quantile(gain, 0.95)),
                "bootstrap_better_than_reference_fraction": float((gain > 0).mean()),
            }
        )
    return results


def publish(root: Path, config_path: Path) -> dict[str, Any]:
    config, output = settings(root, config_path)
    (output / "report_complete.json").unlink(missing_ok=True)
    audit_dataset(output, config)
    summary = json.loads((output / "summary.json").read_text())
    for name, sha in summary["artifact_sha256"].items():
        assert file_sha(output / name) == sha, name
    for name, sha in summary["source_sha256"].items():
        assert file_sha(root / name) == sha, name
    registry = pd.DataFrame(json.loads((output / "model_registry.json").read_text()))
    for row in registry.itertuples():
        assert row.training_indices == [row.index_code] and not row.pooling
        assert file_sha(output / "models" / f"{row.model_id}.joblib") == row.model_sha256
    selected = registry[registry.validation_winner]
    metrics = pd.read_parquet(output / "metrics.parquet")
    test = metrics[metrics.split == "test"]
    overview = selected[["model_id", "validation_selection_loss"]].merge(
        test, on="model_id", validate="one_to_one"
    )
    predictions = pd.read_parquet(output / "predictions.parquet")
    chosen = predictions[
        (predictions.split == "test") & predictions.model_id.isin(selected.model_id)
    ]
    intervals = []
    rng = np.random.default_rng(config["seed"])
    for mid, part in chosen.groupby("model_id", sort=True):
        for result in bootstrap(
            part, str(part.target.iloc[0]), int(part.horizon.iloc[0]), config, rng
        ):
            intervals.append({"model_id": mid, **result})
    confidence = pd.DataFrame(intervals)
    primary = confidence.merge(selected[["model_id", "horizon"]], on="model_id")
    primary = primary[primary.block_sessions == 2 * primary.horizon].drop(columns="horizon")
    overview = overview.merge(primary, on="model_id", validate="one_to_one")
    export = chosen[
        ["model_id", "index_code", "index_name", "target", "horizon", "cutoff", "score"]
    ].copy()
    export["available_at_modeled"] = (
        (pd.to_datetime(export.cutoff) + pd.Timedelta(days=1))
        .dt.tz_localize("UTC")
        .dt.tz_convert("Europe/Paris")
    )
    export["fit_information_available_at_modeled"] = pd.Timestamp("2025-07-01", tz="UTC")
    export["feature_stream"] = (
        export.index_code
        + "."
        + export.target
        + ".h"
        + export.horizon.astype(str)
        + ".index-series-v1"
    )
    export["pit_grade"], export["independent_confirmation"], export["ready_for_srd_integration"] = (
        "reconstructed",
        False,
        False,
    )
    assert (export.available_at_modeled > export.fit_information_available_at_modeled).all()
    for name, frame in [
        ("overview", overview),
        ("confidence", confidence),
        ("context_score_features", export),
    ]:
        frame.to_parquet(output / f"{name}.parquet", index=False)
        frame.to_csv(output / f"{name}.csv", index=False)
    columns = [
        "index_name",
        "target",
        "horizon",
        "model",
        "n",
        "roc_auc",
        "temporal_spearman",
        "rmse",
        "reference_rmse",
        "skill",
        "primary_lo90",
        "primary_hi90",
        "loss_advantage_lo90",
        "loss_advantage_hi90",
    ]
    report = root / "docs/INDEX_SERIES_MODELS_RESULTS.md"
    report.write_text(
        "# Grands marchés — modèles temporels par indice\n\n"
        "**Développement rétrospectif, 6 octobre 2026.** "
        "[Contrat et formules](INDEX_SERIES_MODELS_CONTRACT.md).\n\n"
        f"{summary['model_count']} artefacts de modèles/références, "
        f"{summary['supervised_final_fits']} fits finaux, "
        f"{summary['validation_fits']} fits de validation. "
        "Cinq séries, trois targets, H5/H10 : 30 tâches. "
        "Chaque estimateur apprend sur **un seul indice**. "
        "22 features de close, grille quotidienne CAC40, "
        "disponibilité source à minuit UTC D+1. Train 2024, validation S1 2025, "
        "retrain 2024+S1 2025, test S1 2026.\n\n"
        "## Gagnants de validation — résultats test\n\n"
        "Direction : sélection par log-loss ; régressions par RMSE. "
        "Une référence simple peut gagner. "
        "AUC et corrélation temporelle sont calculées **sur les dates de chaque indice**. "
        "Le skill compare la perte test au prior historique (direction), à zéro (rendement) "
        "ou à la volatilité historique H. Skill ≤0 : aucune amélioration avec ce critère. "
        "Rendements/volatilités sont en fractions.\n\n"
        + table(overview[columns].sort_values(["target", "index_name", "horizon"]))
        + "\n\nIntervalles individuels 90 %, bootstrap temporel de 5 000 réplications, "
        "blocs principaux 2×H ; variantes H et 4×H conservées. L'avantage de perte est "
        "perte référence − perte modèle, positif si meilleur. Une corrélation positive "
        "peut coexister avec une erreur plus grande. Les intervalles sont conditionnels "
        "aux modèles et aux données, sans correction multiple ni preuve d'alpha. "
        "Les fenêtres futures quotidiennes se chevauchent fortement.\n\n"
        "## Données et contrôles\n\n"
        f"{json.loads((output / 'dataset_audit.json').read_text())['return_checks']} rendements et "
        "volatilités futurs recalculés depuis les quotes natives ; contrôle de 50 préfixes "
        "historiques pour les features ; contrôle des timestamps et frontières de split. "
        "Aucun poids ou prétraitement partagé entre indices. Labels absents conservés, "
        "sans remplacement ni filtre selon le rendement futur. Les résultats précédents "
        "restent conservés.\n\n"
        "## Artefacts et futur contexte SRD\n\n"
        f"`context_score_features.parquet` : {len(export)} scores "
        f"sur {export.feature_stream.nunique()} "
        "flux, seulement test 2026, sans résultat futur. OOF roulant et jointure as-of "
        "nécessaires pour une intégration historique au SRD. Grade reconstruit, "
        "confirmation indépendante et intégration SRD encore ouvertes.\n\n"
        "Dossier local `data/analysis/index-series-models-v1/` : source figée, features, "
        "targets, audit, grilles, métriques par modèle, prédictions validation/test, "
        "modèles joblib, intervalles et scores. Onglet **Grands marchés** dans le "
        "[Model Lab](https://sandbox.hocus.works/quant-model-lab/).\n\n"
        "Reproduction : `uv run python scripts/index_series_models.py prepare`, "
        "puis `run`, puis `publish`. Configuration `configs/experiments/index_series_v1.toml`.\n"
    )
    receipt = {
        "summary_sha256": file_sha(output / "summary.json"),
        "report_sha256": file_sha(report),
        "generator_sha256": file_sha(Path(__file__)),
        "single_index_fits_verified": True,
        "artifacts": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    (root / "docs/INDEX_SERIES_MODELS_RESULTS.sources.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    (output / "report_complete.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
