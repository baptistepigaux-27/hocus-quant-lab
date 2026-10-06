"""Expanding historical context predictions, never fitted on their scored block."""

from __future__ import annotations

import json
from bisect import bisect_right
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_data import normal_dates, utc_available
from hocus_quant.model_lab.models import (
    fit_model,
    is_classifier,
    make_model,
    predict_score,
    prepare_labels,
)


def produce_context(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    destination = output / "context"
    if (destination / "complete.json").exists():
        receipt = json.loads((destination / "complete.json").read_text())
        for name, sha in receipt["artifacts"].items():
            assert file_sha(destination / name) == sha
        return receipt
    destination.mkdir(parents=True, exist_ok=True)
    models = destination / "models"
    models.mkdir(exist_ok=True)
    inputs = output / "context_inputs"
    manifest = json.loads((inputs / "complete.json").read_text())
    sectors = normal_dates(pd.read_parquet(inputs / "sector_features.parquet"), ["cutoff"])
    sector_targets = normal_dates(
        pd.read_parquet(inputs / "sector_targets.parquet"), ["cutoff", "target_end"]
    )
    major = normal_dates(
        pd.read_parquet(inputs / "major_features.parquet"), ["cutoff", "reference_quote_date"]
    )
    major_targets = normal_dates(
        pd.read_parquet(inputs / "major_targets.parquet"), ["cutoff", "target_end"]
    )
    baseline = root / config["baseline_path"]
    requested = sorted(
        normal_dates(pd.read_parquet(baseline / "features.parquet"), ["cutoff"]).cutoff.unique()
    )
    codes, sector_ids, major_ids = (
        manifest[k] for k in ["sector_codes", "sector_feature_ids", "major_feature_ids"]
    )
    sector_source = normal_dates(
        pd.read_parquet(root / config["indices_path"] / "source_market.parquet"), ["session_date"]
    )
    native_days = {
        code: sorted(part.session_date.unique())
        for code, part in sector_source.groupby("provider_instrument_id")
        if code in codes
    }
    sector_panel = sectors.merge(sector_targets, on=["cutoff", "entity_id"], validate="one_to_many")
    major_panel = major.merge(major_targets, on=["cutoff", "index_code"], validate="one_to_many")
    sbf = major[(major.index_code == "FR0003999481") & major.eligible_at_T].copy()
    anchor = sbf[sbf.cutoff <= date.fromisoformat(config["cluster_fit_end"])]
    assert len(anchor) > config["clusters"] * 10
    preprocess = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        ]
    )
    anchor_x = preprocess.fit_transform(anchor[major_ids])
    clusterer = KMeans(
        n_clusters=7,
        n_init=config["kmeans_n_init"],
        max_iter=500,
        random_state=config["seed"],
        algorithm="lloyd",
    ).fit(anchor_x)
    native_centers = preprocess.named_steps["scale"].inverse_transform(clusterer.cluster_centers_)
    order = sorted(
        range(7),
        key=lambda i: (
            native_centers[i, major_ids.index("volatility_20")],
            native_centers[i, major_ids.index("momentum_20")],
            i,
        ),
    )
    remap = np.empty(7, dtype=int)
    remap[order] = np.arange(1, 8)
    transformed = preprocess.transform(sbf[major_ids])
    sbf["cluster"] = remap[clusterer.predict(transformed)]
    distances = clusterer.transform(transformed)[:, order]
    for i in range(7):
        sbf[f"distance_c{i + 1}"] = distances[:, i]
    anchor_path = models / "kmeans-anchor-2023.joblib"
    joblib.dump(
        {
            "preprocessing": preprocess,
            "clusterer": clusterer,
            "remap": remap,
            "feature_ids": major_ids,
            "fit_end": config["cluster_fit_end"],
        },
        anchor_path,
        compress=3,
    )
    pd.DataFrame(native_centers[order], columns=major_ids).assign(
        cluster=np.arange(1, 8)
    ).to_parquet(destination / "cluster_centers.parquet", index=False)
    sbf_panel = major_panel[major_panel.index_code == "FR0003999481"].merge(
        sbf[["cutoff", "cluster"]], on="cutoff", validate="many_to_one"
    )
    rows: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    rf_params = {
        "n_estimators": config["context_rf_estimators"],
        "max_depth": config["context_rf_max_depth"],
        "min_samples_leaf": config["context_rf_min_samples_leaf"],
        "max_features": config["context_rf_max_features"],
    }

    def add(
        day: date,
        stream: str,
        value: float,
        fold: dict[str, Any],
        producer: str,
        last_feature: Any,
        last_label: Any,
        quote_day: Any = None,
    ) -> None:
        rows.append(
            {
                "cutoff": day,
                "feature_id": stream,
                "value": float(value),
                "source_available_at": utc_available(day),
                "fit_information_available_at": pd.Timestamp(fold["fit_before"], tz="UTC"),
                "max_training_feature_available_at": utc_available(last_feature)
                if last_feature
                else pd.NaT,
                "max_training_label_available_at": utc_available(last_label)
                if last_label
                else pd.NaT,
                "source_quote_date": quote_day,
                "quote_age_days": (day - quote_day).days if quote_day is not None else None,
                "fold": fold["id"],
                "producer_id": producer,
                "status": "observed_context" if np.isfinite(value) else "context_unavailable",
            }
        )

    def mature(panel: pd.DataFrame, fold: dict[str, Any]) -> pd.DataFrame:
        bound = pd.Timestamp(fold["fit_before"], tz="UTC")
        keep = panel.target_end.notna() & panel.cutoff.notna()
        valid = panel.loc[keep].copy()
        valid = valid[valid.target_end.map(utc_available) < bound]
        assert (valid.cutoff.map(utc_available) < bound).all()
        return valid

    def fit_forecaster(
        fit: pd.DataFrame,
        scored: pd.DataFrame,
        ids: list[str],
        target: str,
        classification: bool,
        fold: dict[str, Any],
        producer_name: str,
    ) -> tuple[Any, str, Any, Any]:
        keep, y = prepare_labels(fit[target], classification)
        training = fit.loc[keep]
        identity = fingerprint(
            {
                "fold": fold,
                "name": producer_name,
                "config": config,
                "input_receipt": file_sha(inputs / "complete.json"),
            }
        )[:14]
        producer = producer_name + "-" + identity
        path = models / f"{producer}.joblib"
        if len(y) < config["minimum_labels"]:
            registry.append(
                {
                    "producer_id": producer,
                    "fold": fold["id"],
                    "target": target,
                    "status": "insufficient_labels",
                    "n": len(y),
                }
            )
            return np.full(len(scored), np.nan), producer, None, None
        model = fit_model(
            make_model("rf", rf_params, classification, config["seed"], config["threads"]),
            training[ids].to_numpy(dtype=float),
            y,
            classification,
        )
        prediction = predict_score(model, scored[ids].to_numpy(dtype=float), classification)
        if target == "volatility":
            prediction = np.maximum(prediction, 0)
        metadata = {
            "producer_id": producer,
            "fold": fold["id"],
            "target": target,
            "fit_information_available_at": fold["fit_before"],
            "training_max_feature_cutoff": str(training.cutoff.max()),
            "training_max_label_end": str(training.target_end.max()),
            "training_rows": len(training),
            "feature_ids": ids,
            "classification": classification,
            "params": rf_params,
            "index_codes": sorted(
                training.index_code.unique().tolist()
                if "index_code" in training
                else [e.rsplit(":", 1)[-1] for e in training.entity_id.unique()]
            ),
            "status": "fitted",
        }
        joblib.dump({"estimator": model, "metadata": metadata}, path, compress=3)
        metadata["model_sha256"] = file_sha(path)
        registry.append(metadata)
        return prediction, producer, training.cutoff.max(), training.target_end.max()

    for fold in config["folds"]:
        dates = [
            d
            for d in requested
            if date.fromisoformat(fold["start"]) <= d <= date.fromisoformat(fold["end"])
        ]
        if not dates:
            continue
        print(f"CONTEXT FIT {fold['id']}: {len(dates)} decision dates", flush=True)
        sector_scored = sectors[sectors.cutoff.isin(dates)].sort_values(["cutoff", "entity_id"])
        for h in config["horizons"]:
            fit = mature(sector_panel[sector_panel.horizon == h], fold)
            for target in config["sector_targets"]:
                predicted, producer, last_feature, last_label = fit_forecaster(
                    fit,
                    sector_scored,
                    sector_ids,
                    target,
                    is_classifier(target),
                    fold,
                    f"sector-{target}-h{h}",
                )
                values = {}
                for row, prediction in zip(sector_scored.itertuples(), predicted, strict=True):
                    code = row.entity_id.rsplit(":", 1)[-1]
                    days = native_days[code]
                    position = bisect_right(days, row.cutoff) - 1
                    quote = days[position] if position >= 0 else None
                    values[(row.cutoff, code)] = (float(prediction), quote)
                for day in dates:
                    for code in codes:
                        value, quote = values.get((day, code), (np.nan, None))
                        add(
                            day,
                            f"ctx.sector.{code}.{target}.h{h}.v1",
                            value,
                            fold,
                            producer,
                            last_feature,
                            last_label,
                            quote,
                        )
                print(f"CONTEXT {fold['id']} sector {target} H{h}", flush=True)
        for code in config["major_codes"]:
            scored = major[
                (major.index_code == code) & major.cutoff.isin(dates) & major.eligible_at_T
            ]
            for h in config["horizons"]:
                fit = mature(
                    major_panel[(major_panel.index_code == code) & (major_panel.horizon == h)], fold
                )
                fit = fit[fit.eligible_at_T]
                for target in config["major_targets"]:
                    predicted, producer, last_feature, last_label = fit_forecaster(
                        fit,
                        scored,
                        major_ids,
                        target,
                        target == "direction",
                        fold,
                        f"major-{code}-{target}-h{h}",
                    )
                    values = {
                        r.cutoff: (float(p), r.reference_quote_date)
                        for r, p in zip(scored.itertuples(), predicted, strict=True)
                    }
                    for day in dates:
                        value, quote = values.get(day, (np.nan, None))
                        add(
                            day,
                            f"ctx.major.{code}.{target}.h{h}.v1",
                            value,
                            fold,
                            producer,
                            last_feature,
                            last_label,
                            quote,
                        )
        state_dates = sbf[sbf.cutoff.isin(dates)].set_index("cutoff")
        for day in dates:
            state = state_dates.loc[day] if day in state_dates.index else None
            for i in range(1, 8):
                add(
                    day,
                    f"ctx.sbf120.cluster_c{i}.v1",
                    float(state.cluster == i) if state is not None else np.nan,
                    fold,
                    "kmeans-anchor-2023",
                    anchor.cutoff.max(),
                    None,
                    state.reference_quote_date if state is not None else None,
                )
                add(
                    day,
                    f"ctx.sbf120.distance_c{i}.v1",
                    float(state[f"distance_c{i}"]) if state is not None else np.nan,
                    fold,
                    "kmeans-anchor-2023",
                    anchor.cutoff.max(),
                    None,
                    state.reference_quote_date if state is not None else None,
                )
        for h in config["horizons"]:
            fit = mature(sbf_panel[sbf_panel.horizon == h], fold)
            for target in config["major_targets"]:
                keep, y = prepare_labels(fit[target], target == "direction")
                training = fit.loc[keep]
                prior = float(y.mean())
                mapping, lookup = {}, []
                for c in range(1, 8):
                    _, yc = prepare_labels(
                        training[training.cluster == c][target], target == "direction"
                    )
                    prediction = (
                        prior
                        if len(yc) < config["cluster_minimum_labels"]
                        else float(
                            (yc.sum() + config["cluster_shrinkage_labels"] * prior)
                            / (len(yc) + config["cluster_shrinkage_labels"])
                        )
                    )
                    mapping[c] = prediction
                    lookup.append({"cluster": c, "n": len(yc), "score": prediction})
                producer = f"regime-{target}-h{h}-{fold['id']}"
                table_path = models / f"{producer}.json"
                table_path.write_text(json.dumps(lookup, indent=2) + "\n")
                registry.append(
                    {
                        "producer_id": producer,
                        "fold": fold["id"],
                        "target": target,
                        "n": len(training),
                        "model_sha256": file_sha(table_path),
                        "status": "lookup_fitted",
                    }
                )
                for day in dates:
                    state = state_dates.loc[day] if day in state_dates.index else None
                    add(
                        day,
                        f"ctx.sbf120.regime_forecast.{target}.h{h}.v1",
                        mapping[int(state.cluster)] if state is not None else np.nan,
                        fold,
                        producer,
                        training.cutoff.max(),
                        training.target_end.max(),
                        state.reference_quote_date if state is not None else None,
                    )
        pd.DataFrame(rows).to_parquet(destination / "scores_progress.parquet", index=False)
    scores = pd.DataFrame(rows)
    assert not scores.duplicated(["cutoff", "feature_id"]).any()
    assert scores.feature_id.nunique() == 356
    assert scores.cutoff.nunique() == len(requested)
    assert (scores.fit_information_available_at <= scores.source_available_at).all()
    known = scores.max_training_label_available_at.notna()
    assert (
        scores.loc[known, "max_training_label_available_at"]
        < scores.loc[known, "fit_information_available_at"]
    ).all()
    scores["pit_grade"] = "reconstructed"
    scores.to_parquet(destination / "scores.parquet", index=False)
    wide = scores.pivot(index="cutoff", columns="feature_id", values="value").reset_index()
    wide.columns.name = None
    wide.to_parquet(destination / "features.parquet", index=False)
    (destination / "model_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    receipt = {
        "context_features": scores.feature_id.nunique(),
        "context_dates": len(requested),
        "context_score_rows": len(scores),
        "context_models": len(registry),
        "cluster_anchor_dates": len(anchor),
        "cluster_anchor_end": str(anchor.cutoff.max()),
        "no_label_later_than_fit": True,
        "source_and_fit_available_at_each_decision": True,
        "missing_fraction": float(scores.value.isna().mean()),
        "generator_sha256": file_sha(Path(__file__)),
        "artifacts": {p.name: file_sha(p) for p in destination.glob("*.parquet")},
    }
    (destination / "complete.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
