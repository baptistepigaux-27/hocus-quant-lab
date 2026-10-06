"""Fixed training-period clusters of the SBF120's historical market states."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.analysis.index_series_models import bootstrap, labels, metric, reference
from hocus_quant.model_lab.report import table


def run(root: Path, config_path: Path) -> dict[str, Any]:
    config = tomllib.loads((root / config_path).read_text())
    assert config["clusters"] == 7
    parent, output = root / config["source_path"], root / config["output_path"]
    if output.exists():
        raise ValueError("Experiment directory exists; use a new version")
    parent_manifest = json.loads((parent / "dataset_manifest.json").read_text())
    for name in ["features.parquet", "targets.parquet"]:
        assert file_sha(parent / name) == parent_manifest["source_sha256"][name], name
    ids = parent_manifest["feature_ids"]
    frame = pd.read_parquet(parent / "features.parquet")
    frame = frame[(frame.index_code == config["index_code"]) & frame.eligible_at_T].copy()
    frame = frame.sort_values("cutoff").reset_index(drop=True)
    assert not frame.duplicated("cutoff").any()
    days = pd.to_datetime(frame.cutoff)
    fit_mask = days.between(config["fit_start"], config["fit_end"])
    train = frame.loc[fit_mask, ids]
    assert len(train) >= config["clusters"] * config["minimum_cluster_labels"]
    assert train.notna().any().all()
    assert not np.isinf(frame[ids].to_numpy(dtype=float)).any()
    preprocessing = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    x_train = preprocessing.fit_transform(train)
    clusterer = KMeans(
        n_clusters=config["clusters"],
        init="k-means++",
        n_init=config["n_init"],
        max_iter=config["max_iter"],
        algorithm=config["algorithm"],
        random_state=config["seed"],
    ).fit(x_train)
    raw_centers = preprocessing.named_steps["scale"].inverse_transform(clusterer.cluster_centers_)
    order = sorted(
        range(config["clusters"]),
        key=lambda i: (
            raw_centers[i, ids.index("volatility_20")],
            raw_centers[i, ids.index("momentum_20")],
            i,
        ),
    )
    remap = np.empty(config["clusters"], dtype=int)
    remap[order] = np.arange(1, config["clusters"] + 1)
    x = preprocessing.transform(frame[ids])
    raw_labels = clusterer.predict(x)
    frame["cluster"] = remap[raw_labels]
    distance = clusterer.transform(x)[:, order]
    for i in range(config["clusters"]):
        frame[f"distance_c{i + 1}"] = distance[:, i]
    frame["nearest_distance"] = distance.min(axis=1)
    assert frame.loc[fit_mask, "cluster"].nunique() == config["clusters"]
    train_distance = frame.loc[fit_mask, "nearest_distance"]
    # Descriptive support indicator; it never removes a date or future outcome.
    support_q95 = float(train_distance.quantile(0.95))
    frame["outside_train_distance_q95"] = frame.nearest_distance > support_q95
    frame["period"] = np.select(
        [days.dt.year == 2024, days.dt.year == 2025, days.dt.year == 2026],
        ["train", "validation", "test"],
        default="undeclared",
    )
    assert not (frame.period == "undeclared").any()
    frame["missing_feature_count"] = frame[ids].isna().sum(axis=1)
    centers = pd.DataFrame(raw_centers[order], columns=ids)
    centers.insert(0, "cluster", np.arange(1, config["clusters"] + 1))
    targets = pd.read_parquet(parent / "targets.parquet")
    targets = targets[targets.index_code == config["index_code"]]
    joined = frame.merge(targets, on=["index_code", "cutoff"], validate="one_to_many")
    lookup, forecasts, measures, profiles = [], [], [], []
    for h in sorted(targets.horizon.unique()):
        panel = joined[joined.horizon == h].sort_values("cutoff")
        fit = panel[panel.split == "train"]
        for target in ["direction", "return", "volatility"]:
            _, y_train = labels(fit, target)
            prior = float(y_train.mean())
            mapped: dict[int, float] = {}
            for c in range(1, config["clusters"] + 1):
                _, y = labels(fit[fit.cluster == c], target)
                fallback = len(y) < config["minimum_cluster_labels"]
                pred = (
                    prior
                    if fallback
                    else float(
                        (y.sum() + config["shrinkage_labels"] * prior)
                        / (len(y) + config["shrinkage_labels"])
                    )
                )
                mapped[c] = pred
                lookup.append(
                    {
                        "cluster": c,
                        "target": target,
                        "horizon": int(h),
                        "training_labels": len(y),
                        "prior": prior,
                        "score": pred,
                        "fallback": fallback,
                    }
                )
            for period in ["train", "validation", "test"]:
                pred = panel[panel.period == period].copy()
                pred["score"] = pred.cluster.map(mapped)
                pred["reference_score"] = reference(pred, target, int(h), y_train)
                base = {
                    "model": "kmeans7_train2024",
                    "target": target,
                    "horizon": int(h),
                    "split": period,
                    "index_code": config["index_code"],
                }
                measured = metric(pred, target)
                if target != "direction":
                    _, actual = labels(pred, target)
                    mean_loss = float(np.mean((actual - prior) ** 2))
                    measured["train_mean_reference_rmse"] = float(np.sqrt(mean_loss))
                    measured["skill_vs_train_mean"] = 1 - measured["rmse"] ** 2 / mean_loss
                measures.append({**base, **measured})
                ledger = pred[
                    [
                        "cutoff",
                        "cluster",
                        "reference_quote_date",
                        "reference_close",
                        "target_end",
                        "label_status",
                        "nearest_distance",
                        "score",
                        "reference_score",
                        target,
                    ]
                ].rename(columns={target: "target_value"})
                for key, value in base.items():
                    ledger[key] = value
                forecasts.append(ledger)
            for period in ["train", "validation", "test"]:
                for c in range(1, config["clusters"] + 1):
                    part = panel[(panel.period == period) & (panel.cluster == c)]
                    _, y = labels(part, target)
                    profiles.append(
                        {
                            "period": period,
                            "cluster": c,
                            "target": target,
                            "horizon": int(h),
                            "dates": len(part),
                            "labels": len(y),
                            "outcome_mean": float(y.mean()) if len(y) else None,
                            "outcome_median": float(np.median(y)) if len(y) else None,
                        }
                    )
    predictions = pd.concat(forecasts, ignore_index=True)
    confidence_rows = []
    rng = np.random.default_rng(config["seed"])
    for (target, h), part in predictions[predictions.split == "test"].groupby(
        ["target", "horizon"]
    ):
        for measured in bootstrap(part, str(target), int(h), config, rng):
            confidence_rows.append({"target": target, "horizon": int(h), **measured})
    confidence = pd.DataFrame(confidence_rows)
    occupancy = (
        frame.groupby(["period", "cluster"])
        .agg(
            dates=("cutoff", "size"),
            mean_distance=("nearest_distance", "mean"),
            outside_train_support=("outside_train_distance_q95", "mean"),
        )
        .reset_index()
    )
    occupancy["share"] = occupancy.dates / occupancy.groupby("period").dates.transform("sum")
    transitions = []
    calendar = json.loads((parent / "calendar.json").read_text())
    positions = {d: i for i, d in enumerate(calendar)}
    for period, part in frame.groupby("period"):
        rows = list(part.itertuples())
        for a, b in zip(rows, rows[1:], strict=False):
            if positions[str(b.cutoff)] - positions[str(a.cutoff)] == 1:
                transitions.append(
                    {"period": period, "from_cluster": a.cluster, "to_cluster": b.cluster}
                )
    transition_counts = (
        pd.DataFrame(transitions)
        .groupby(["period", "from_cluster", "to_cluster"])
        .size()
        .reset_index(name="count")
    )
    transition_counts["probability"] = transition_counts["count"] / transition_counts.groupby(
        ["period", "from_cluster"]
    )["count"].transform("sum")
    feature_profiles = frame.groupby(["period", "cluster"])[ids].mean().reset_index()
    export = frame[frame.period != "train"][["cutoff", "index_code", "cluster"]].copy()
    export["available_at_modeled"] = (
        pd.to_datetime(export.cutoff) + pd.Timedelta(days=1)
    ).dt.tz_localize("UTC")
    export["fit_information_available_at_modeled"] = pd.Timestamp("2025-01-01", tz="UTC")
    for i in range(1, config["clusters"] + 1):
        export[f"cluster_c{i}"] = (export.cluster == i).astype(int)
        export[f"distance_c{i}"] = frame.loc[export.index, f"distance_c{i}"]
    lookup_df = pd.DataFrame(lookup)
    for (target, h), part in lookup_df.groupby(["target", "horizon"]):
        export[f"forecast_{target}_h{h}"] = export.cluster.map(part.set_index("cluster").score)
    export["pit_grade"] = "reconstructed"
    export["ready_for_srd_integration"] = False
    assert (export.available_at_modeled >= export.fit_information_available_at_modeled).all()
    assert not {"target_value", "target_end", "label_status"}.intersection(export.columns)
    output.mkdir(parents=True)
    artifact = output / "model.joblib"
    joblib.dump(
        {
            "preprocessing": preprocessing,
            "clusterer": clusterer,
            "remap": remap,
            "feature_ids": ids,
            "lookup": lookup,
            "config": config,
        },
        artifact,
        compress=3,
    )
    loaded = joblib.load(artifact)
    replay_x = loaded["preprocessing"].transform(frame[ids])
    replay_clusters = loaded["remap"][loaded["clusterer"].predict(replay_x)]
    assert np.array_equal(replay_clusters, frame.cluster.to_numpy())
    differences = []
    for (target, h), part in predictions.groupby(["target", "horizon"]):
        look = pd.DataFrame(loaded["lookup"])
        look = look[(look.target == target) & (look.horizon == h)].set_index("cluster").score
        differences.extend(np.abs(part.cluster.map(look).to_numpy() - part.score.to_numpy()))
    assert max(differences) < 1e-12
    assert (fit.target_end.dropna() <= pd.Timestamp(config["fit_end"]).date()).all()
    assert (export[[f"cluster_c{i}" for i in range(1, 8)]].sum(axis=1) == 1).all()
    audit = {
        "assignment_replays": len(frame),
        "forecast_replays": len(predictions),
        "max_forecast_difference": float(max(differences)),
        "train_only_preprocessing_and_centers": True,
        "one_hot_export_reconciled": True,
        "no_future_outcomes_in_export": True,
    }
    (output / "replay_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    frames = {
        "assignments": frame,
        "centers": centers,
        "lookup": lookup_df,
        "predictions": predictions,
        "metrics": pd.DataFrame(measures),
        "confidence": confidence,
        "occupancy": occupancy,
        "outcome_profiles": pd.DataFrame(profiles),
        "transitions": transition_counts,
        "feature_profiles": feature_profiles,
        "context_features": export,
    }
    for name, df in frames.items():
        df.to_parquet(output / f"{name}.parquet", index=False)
        df.to_csv(output / f"{name}.csv", index=False)
    summary = {
        "version": config["version"],
        "index_code": config["index_code"],
        "clusters": 7,
        "feature_count": len(ids),
        "fit_dates": int(fit_mask.sum()),
        "fit_start": str(frame.loc[fit_mask, "cutoff"].min()),
        "fit_end": str(frame.loc[fit_mask, "cutoff"].max()),
        "prediction_dates": frame.groupby("period").size().to_dict(),
        "inertia": float(clusterer.inertia_),
        "iterations": int(clusterer.n_iter_),
        "train_silhouette": float(silhouette_score(x_train, clusterer.labels_)),
        "train_distance_q95": support_q95,
        "outside_support_by_period": frame.groupby("period")
        .outside_train_distance_q95.mean()
        .to_dict(),
        "context_rows": len(export),
        "context_streams": 20,
        "refit_on_validation_or_test": False,
        "pit_grade": "reconstructed",
        "independent_confirmation": False,
        "ready_for_srd_integration": False,
        "training_missing_values": int(train.isna().sum().sum()),
        "source_sha256": {
            name: file_sha(parent / name) for name in ["features.parquet", "targets.parquet"]
        },
        "generator_sha256": file_sha(Path(__file__)),
        "config_sha256": file_sha(root / config_path),
        "model_sha256": file_sha(artifact),
        "artifact_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    result = pd.DataFrame(measures)
    test_metrics = result[result.split == "test"].set_index(["target", "horizon"])
    report = root / "docs/SBF120_KMEANS7_RESULTS.md"
    report.write_text(
        "# SBF 120 — sept régimes K-means\n\n"
        "**6 octobre 2026 · développement rétrospectif.** "
        "[Contrat, formules et limites](SBF120_KMEANS7_CONTRACT.md).\n\n"
        f"Centres et prétraitement figés sur {summary['fit_dates']} dates de 2024, "
        "22 variables historiques, K=7. Aucune information future dans les centres. "
        "Même modèle en S1 2025 et S1 2026. Les tables de prévision apprennent "
        "seulement les labels purgés de 2024, avec shrinkage 20 et fallback n<10.\n\n"
        f"Silhouette train : {summary['train_silhouette']:.4f}. "
        "Elle mesure la séparation géométrique, sans preuve prédictive.\n\n"
        "## Lecture du résultat\n\n"
        f"En 2026, AUC direction H5/H10 : {test_metrics.loc[('direction', 5), 'roc_auc']:.3f} / "
        f"{test_metrics.loc[('direction', 10), 'roc_auc']:.3f}. "
        "Les erreurs de direction et rendement ne battent pas leurs références. "
        "La volatilité H5 réduit la MSE de "
        f"{100 * test_metrics.loc[('volatility', 5), 'skill']:.1f} % "
        "face à la volatilité historique H5, mais seulement de "
        f"{100 * test_metrics.loc[('volatility', 5), 'skill_vs_train_mean']:.1f} % face "
        "à une moyenne 2024 constante. L'avantage H5 face à la volatilité historique "
        "a un intervalle individuel 90 % positif pour les trois tailles de blocs. "
        "Ce soutien ne concerne pas le comparateur moyenne constante. "
        "L'amélioration H10 face à la volatilité historique ne bat pas la moyenne constante.\n\n"
        f"{100 * summary['outside_support_by_period']['validation']:.1f} % des jours 2025 et "
        f"{100 * summary['outside_support_by_period']['test']:.1f} % des jours 2026 "
        "dépassent le quantile 95 % des distances train. "
        "Les centres de 2024 couvrent donc imparfaitement les états ultérieurs.\n\n"
        "## Profils des centres, en unités natives\n\n"
        + table(
            centers[
                [
                    "cluster",
                    "momentum_5",
                    "momentum_20",
                    "momentum_60",
                    "volatility_20",
                    "drawdown_60",
                    "rsi_simple_14",
                ]
            ]
        )
        + "\n\nLes rendements sont des fractions ; les volatilités sont annualisées. "
        "Les numéros suivent la volatilité 20 du centre train, sans sens ordinal prédictif.\n\n"
        "## Occupation et distance au support train\n\n"
        + table(occupancy)
        + "\n\nSupport : distance au centre le plus proche supérieure au quantile 95 % "
        "des distances train. C'est un indicateur descriptif, aucune date n'est exclue.\n\n"
        "## Prévisions par régime, validation et test\n\n"
        + table(
            result[result.split != "train"][
                [
                    "split",
                    "target",
                    "horizon",
                    "n",
                    "roc_auc",
                    "temporal_spearman",
                    "rmse",
                    "reference_rmse",
                    "skill",
                    "train_mean_reference_rmse",
                    "skill_vs_train_mean",
                ]
            ]
        )
        + "\n\nSkill direction sur log-loss ; régressions sur MSE. Références : "
        "prior 2024, rendement zéro, volatilité historique H. Le comparateur complémentaire "
        "`train_mean` mesure l'apport des régimes face à une simple moyenne 2024 pour "
        "les deux régressions. Les modèles supervisés "
        "précédents utilisent un retrain jusqu'à juin 2025 : budgets d'information différents.\n\n"
        "## Résultats futurs par groupe en 2026\n\n"
        + table(pd.DataFrame(profiles).query("period == 'test'"))
        + "\n\n`outcome_mean` de direction = fréquence de hausse, hors zéros. "
        "Une cellule sans label reste vide ; les n ne sont pas indépendants.\n\n"
        "## Incertitude test, intervalles individuels 90 %\n\n"
        + table(confidence)
        + "\n\n5 000 tirages circulaires, blocs H/2H/4H, modèles figés. "
        "Pas de correction multiple ni d'incertitude de réapprentissage des centres.\n\n"
        "## Artefacts et utilisation\n\n"
        f"`data/analysis/sbf120-kmeans7-v1/` : {len(export)} dates exportées, "
        "20 flux (7 indicatrices, 7 distances, 6 prévisions), sans résultat futur. "
        "Les assignations 2024 servent à lire le fit, pas à une évaluation hors période. "
        "Scores 2025/2026 disponibles après D, fit déclaré au 01/01/2025 UTC. "
        "Jointure SRD et confirmation indépendante restent à faire.\n\n"
        "Reproduction : `uv run python scripts/sbf120_kmeans.py`. "
        "Onglet **SBF 120 · régimes** du [Model Lab](https://sandbox.hocus.works/quant-model-lab/).\n"
    )
    receipt = {
        "summary_sha256": file_sha(output / "summary.json"),
        "report_sha256": file_sha(report),
        "artifact_sha256": summary["artifact_sha256"],
        "model_sha256": summary["model_sha256"],
        "source_sha256": summary["source_sha256"],
    }
    (root / "docs/SBF120_KMEANS7_RESULTS.sources.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    (output / "report_complete.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return summary
