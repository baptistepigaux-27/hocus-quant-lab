"""Paired development results of SRD with and without historical index context."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_data import normal_dates
from hocus_quant.model_lab.models import predict_score
from hocus_quant.model_lab.report import table, validation_winners
from hocus_quant.model_lab.targets import FAMILIES


def reconcile_producers(output: Path, config: dict[str, Any]) -> dict[str, Any]:
    context = output / "context"
    registry = json.loads((context / "model_registry.json").read_text())
    scores = normal_dates(pd.read_parquet(context / "scores.parquet"), ["cutoff"])
    major = normal_dates(
        pd.read_parquet(output / "context_inputs/major_features.parquet"), ["cutoff"]
    )
    sector = normal_dates(
        pd.read_parquet(output / "context_inputs/sector_features.parquet"), ["cutoff"]
    )
    folds = {r["id"]: r for r in config["folds"]}
    differences = []
    replayed = 0
    for entry in registry:
        if entry["status"] != "fitted":
            continue
        path = context / "models" / f"{entry['producer_id']}.joblib"
        assert file_sha(path) == entry["model_sha256"]
        saved = joblib.load(path)
        part = scores[scores.producer_id == entry["producer_id"]]
        dates = part.cutoff.unique()
        target, h = entry["target"], int(re.search(r"-h(\d+)-", entry["producer_id"])[1])
        if entry["producer_id"].startswith("sector-"):
            matrix = sector[sector.cutoff.isin(dates)].sort_values(["cutoff", "entity_id"])
            ids = (
                "ctx.sector." + matrix.entity_id.str.rsplit(":", n=1).str[-1] + f".{target}.h{h}.v1"
            )
        else:
            code = entry["index_codes"][0]
            matrix = major[
                (major.index_code == code) & major.cutoff.isin(dates) & major.eligible_at_T
            ]
            ids = pd.Series(f"ctx.major.{code}.{target}.h{h}.v1", index=matrix.index)
        values = predict_score(
            saved["estimator"],
            matrix[entry["feature_ids"]].to_numpy(dtype=float),
            entry["classification"],
        )
        if target == "volatility":
            values = np.maximum(values, 0)
        replay = pd.DataFrame(
            {"cutoff": matrix.cutoff.to_numpy(), "feature_id": ids.to_numpy(), "replay": values}
        )
        paired = replay.merge(
            part[["cutoff", "feature_id", "value"]],
            on=["cutoff", "feature_id"],
            validate="one_to_one",
        )
        differences.extend(np.abs(paired.replay - paired.value))
        replayed += 1
        if replayed % 24 == 0:
            print(f"CONTEXT MODEL REPLAY {replayed}", flush=True)
        bound = pd.Timestamp(folds[entry["fold"]]["fit_before"], tz="UTC")
        assert (part.max_training_label_available_at < bound).all()
        assert (part.fit_information_available_at <= part.source_available_at).all()
    assert differences and max(differences) < 1e-12
    anchor = joblib.load(context / "models/kmeans-anchor-2023.joblib")
    sbf = major[
        (major.index_code == "FR0003999481")
        & major.eligible_at_T
        & major.cutoff.isin(scores.cutoff.unique())
    ]
    matrix = anchor["preprocessing"].transform(sbf[anchor["feature_ids"]])
    clusters = anchor["remap"][anchor["clusterer"].predict(matrix)]
    distances = anchor["clusterer"].transform(matrix)[:, np.argsort(anchor["remap"])]
    states = dict(zip(sbf.cutoff, clusters, strict=True))
    regime_rows = []
    for position, day in enumerate(sbf.cutoff):
        for c in range(1, 8):
            for metric, value in [
                ("cluster", float(clusters[position] == c)),
                ("distance", float(distances[position, c - 1])),
            ]:
                regime_rows.append(
                    {"cutoff": day, "feature_id": f"ctx.sbf120.{metric}_c{c}.v1", "replay": value}
                )
    lookup_replays = 0
    for entry in registry:
        if entry["status"] != "lookup_fitted":
            continue
        path = context / "models" / f"{entry['producer_id']}.json"
        assert file_sha(path) == entry["model_sha256"]
        mapping = {row["cluster"]: row["score"] for row in json.loads(path.read_text())}
        part = scores[scores.producer_id == entry["producer_id"]]
        for row in part[part.value.notna()].itertuples():
            regime_rows.append(
                {
                    "cutoff": row.cutoff,
                    "feature_id": row.feature_id,
                    "replay": mapping[int(states[row.cutoff])],
                }
            )
        assert (part.max_training_label_available_at < part.fit_information_available_at).all()
        lookup_replays += 1
    regime_paired = pd.DataFrame(regime_rows).merge(
        scores[["cutoff", "feature_id", "value"]],
        on=["cutoff", "feature_id"],
        validate="one_to_one",
    )
    regime_error = float(np.abs(regime_paired.replay - regime_paired.value).max())
    assert regime_error < 1e-12
    receipt = {
        "upstream_model_replays": replayed,
        "replayed_score_rows": len(differences),
        "max_prediction_difference": float(max(differences)),
        "all_training_labels_mature_before_fold": True,
        "regime_anchor_replayed": True,
        "regime_lookup_replays": lookup_replays,
        "regime_score_rows": len(regime_paired),
        "max_regime_prediction_difference": regime_error,
        "regime_anchor_sha256": file_sha(context / "models/kmeans-anchor-2023.joblib"),
        "producer_registry_sha256": file_sha(context / "model_registry.json"),
    }
    (output / "context/replay_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def publish(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    marker = output / "context_report_complete.json"
    marker.unlink(missing_ok=True)
    summary = json.loads((output / "summary.json").read_text())
    for name, sha in summary["artifact_sha256"].items():
        assert file_sha(output / name) == sha, name
    upstream_audit = reconcile_producers(output, config)
    parent = root / config["baseline_path"]
    registry = json.loads((output / "model_registry.json").read_text())
    features = normal_dates(pd.read_parquet(output / "features.parquet"), ["cutoff"])
    test_predictions = normal_dates(pd.read_parquet(output / "predictions.parquet"), ["cutoff"])
    max_error = 0.0
    for number, entry in enumerate(registry, start=1):
        saved = output / "models" / f"{entry['model_id']}.joblib"
        assert file_sha(saved) == entry["model_sha256"]
        artifact = joblib.load(saved)
        part = test_predictions[
            (test_predictions.model_id == entry["model_id"]) & (test_predictions.split == "test")
        ]
        matrix = part[["cutoff", "entity_id"]].merge(
            features, on=["cutoff", "entity_id"], validate="one_to_one"
        )
        replay = predict_score(
            artifact["estimator"],
            matrix[entry["feature_ids"]].to_numpy(dtype=float),
            artifact["classification"],
        )
        max_error = max(max_error, float(np.max(np.abs(replay - part.score.to_numpy()))))
        if number % 14 == 0:
            print(f"SRD MODEL REPLAY {number}/{len(registry)}", flush=True)
    assert max_error < 1e-12
    winners = validation_winners(output)
    baseline_winners = validation_winners(parent)
    metrics = pd.read_parquet(output / "metrics.parquet")
    base_metrics = pd.read_parquet(parent / "metrics.parquet")
    backtests = pd.read_parquet(output / "backtest_summary.parquet")
    base_backtests = pd.concat(
        [
            pd.read_parquet(parent / "portfolio-top03/backtest_summary.parquet"),
            pd.read_parquet(parent / "portfolio-top03/costs-25-45/backtest_summary.parquet"),
        ],
        ignore_index=True,
    )
    groups = []
    for chosen, measured, bt in [
        (winners, metrics, backtests),
        (baseline_winners, base_metrics, base_backtests),
    ]:
        result = chosen.merge(
            measured[measured.split == "test"],
            on=["model_id", "target", "horizon", "model", "feature_set"],
            validate="one_to_one",
        )
        for cost in [25, 45]:
            cost_rows = bt[(bt.cost_bp == cost) & (bt.model != "universe")][
                ["model_id", "cumulative_return", "max_drawdown", "fees"]
            ]
            cost_rows = cost_rows.rename(
                columns={k: f"{k}_{cost}bp" for k in ["cumulative_return", "max_drawdown", "fees"]}
            )
            result = result.merge(cost_rows, on="model_id", validate="one_to_one")
        groups.append(result)
    overview = pd.concat(groups, ignore_index=True).sort_values(
        ["target", "horizon", "feature_set"]
    )
    key_columns = [
        "model_id",
        "model",
        "validation_metric",
        "mean_ic",
        "roc_auc",
        "r2",
        "log_loss",
        "n",
        "cumulative_return_25bp",
        "cumulative_return_45bp",
        "max_drawdown_25bp",
        "max_drawdown_45bp",
    ]
    comparison = groups[0][["target", "horizon", *key_columns]].merge(
        groups[1][["target", "horizon", *key_columns]],
        on=["target", "horizon"],
        suffixes=("_context", "_baseline"),
        validate="one_to_one",
    )
    for name in [
        "mean_ic",
        "roc_auc",
        "r2",
        "log_loss",
        "cumulative_return_25bp",
        "cumulative_return_45bp",
    ]:
        comparison[f"delta_{name}"] = comparison[f"{name}_context"] - comparison[f"{name}_baseline"]
    assert (comparison.n_context == comparison.n_baseline).all()
    matched = metrics[metrics.split == "test"].merge(
        base_metrics[base_metrics.split == "test"],
        on=["target", "horizon", "model"],
        suffixes=("_context", "_baseline"),
        validate="one_to_one",
    )
    for name in ["mean_ic", "roc_auc", "r2", "log_loss"]:
        matched[f"delta_{name}"] = matched[f"{name}_context"] - matched[f"{name}_baseline"]
    cutoff = pd.read_parquet(output / "cutoff_metrics.parquet")
    base_cutoff = pd.read_parquet(parent / "cutoff_metrics.parquet")
    confidence, paired_rows = [], []
    rng = np.random.default_rng(config["seed"])
    for row in comparison.itertuples():
        a = cutoff[(cutoff.model_id == row.model_id_context) & (cutoff.split == "test")][
            ["cutoff", "ic"]
        ]
        b = base_cutoff[
            (base_cutoff.model_id == row.model_id_baseline) & (base_cutoff.split == "test")
        ][["cutoff", "ic"]]
        paired = a.merge(
            b, on="cutoff", suffixes=("_context", "_baseline"), validate="one_to_one"
        ).sort_values("cutoff")
        paired["target"], paired["horizon"] = row.target, row.horizon
        paired["delta_ic"] = paired.ic_context - paired.ic_baseline
        paired_rows.append(paired)
        good = paired.ic_context.notna() & paired.ic_baseline.notna()
        mask = (comparison.target == row.target) & (comparison.horizon == row.horizon)
        comparison.loc[mask, "paired_ic_cutoffs"] = int(good.sum())
        comparison.loc[mask, "paired_delta_ic"] = (
            float(paired.loc[good, "delta_ic"].mean()) if good.any() else np.nan
        )
        values = paired.delta_ic.to_numpy(dtype=float)
        if not np.isfinite(values).any():
            continue
        for block in config[f"bootstrap_blocks_h{row.horizon}"]:
            starts = rng.integers(
                0,
                len(values),
                size=(config["bootstrap_replicates"], math.ceil(len(values) / block)),
            )
            indices = ((starts[..., None] + np.arange(block)) % len(values)).reshape(
                config["bootstrap_replicates"], -1
            )[:, : len(values)]
            sampled = values[indices]
            counts = np.isfinite(sampled).sum(axis=1)
            means = np.divide(
                np.nansum(sampled, axis=1),
                counts,
                out=np.full(len(counts), np.nan),
                where=counts > 0,
            )
            finite_means = means[np.isfinite(means)]
            confidence.append(
                {
                    "target": row.target,
                    "horizon": row.horizon,
                    "block_cutoffs": block,
                    "paired_cutoffs": int(np.isfinite(values).sum()),
                    "usable_bootstrap_replicates": len(finite_means),
                    "delta_ic": float(np.nanmean(values)),
                    "delta_ic_lo90": float(np.nanquantile(means, 0.05)),
                    "delta_ic_hi90": float(np.nanquantile(means, 0.95)),
                    "bootstrap_positive_fraction": float((finite_means > 0).mean()),
                }
            )
    importance = pd.read_parquet(output / "feature_importances.parquet")
    importance["block"] = np.select(
        [
            importance.feature_id.str.startswith("ctx.sector."),
            importance.feature_id.str.startswith("ctx.major."),
            importance.feature_id.str.startswith("ctx.sbf120."),
        ],
        ["sector_predictions", "major_predictions", "sbf120_regimes"],
        default="stock_features",
    )
    shares = (
        importance.groupby(["model_id", "target", "horizon", "model", "block"])
        .gain_or_impurity.sum()
        .reset_index()
    )
    shares["importance_share"] = shares.gain_or_impurity / shares.groupby(
        "model_id"
    ).gain_or_impurity.transform("sum")
    selected_shares = shares[shares.model_id.isin(winners.model_id)]
    targets = pd.read_parquet(output / "targets.parquet")
    bounds = []
    for family in FAMILIES:
        valid = targets[
            targets[family].notna() & targets.split.isin(["train", "validation", "test"])
        ]
        if family.startswith("direction"):
            valid = valid[valid[family] != 0]
        for (h, split), part in valid.groupby(["horizon", "split"]):
            bounds.append(
                {
                    "target": family,
                    "horizon": h,
                    "split": split,
                    "last_usable_label_end": str(part.target_end.max()),
                }
            )
    coverage = pd.read_parquet(output / "coverage.parquet").rename(
        columns={"last_outcome": "last_observed_path_end"}
    )
    coverage = coverage.merge(
        pd.DataFrame(bounds), on=["target", "horizon", "split"], validate="many_to_one"
    )
    frames = {
        "comparison_validation_winners": overview,
        "comparison_baseline": comparison,
        "comparison_matched_models": matched,
        "comparison_paired_cutoffs": pd.concat(paired_rows),
        "comparison_confidence": pd.DataFrame(confidence),
        "context_importance_shares": shares,
        "label_coverage": coverage,
    }
    for name, df in frames.items():
        df.to_parquet(output / f"{name}.parquet", index=False)
        df.to_csv(output / f"{name}.csv", index=False)
    scores = pd.read_parquet(output / "context/scores.parquet")
    profile = (
        scores.assign(year=pd.to_datetime(scores.cutoff).dt.year)
        .groupby("year")
        .agg(
            dates=("cutoff", "nunique"),
            streams=("feature_id", "nunique"),
            missing=("value", lambda x: float(x.isna().mean())),
        )
        .reset_index()
    )
    profile.to_parquet(output / "context_coverage.parquet", index=False)
    (output / "comparison_replay_audit.json").write_text(
        json.dumps(
            {
                **upstream_audit,
                "srd_model_replays": len(registry),
                "max_srd_prediction_difference": max_error,
                "same_outcome_counts_as_baseline": True,
            },
            indent=2,
        )
        + "\n"
    )
    report = root / "docs/SRD_CONTEXT_RESULTS.md"
    compact = comparison[["target", "horizon", "model_baseline", "model_context"]].copy()
    for name, label in [
        ("mean_ic", "IC"),
        ("cumulative_return_25bp", "Net 25 bp"),
        ("cumulative_return_45bp", "Net 45 bp"),
    ]:

        def display(v: float, metric: str = name) -> str:
            if pd.isna(v):
                return "indéfini"
            return f"{v:.4f}" if metric == "mean_ic" else f"{100 * v:+.2f} %"

        compact[label + " référence → contexte"] = [
            display(a) + " → " + display(b)
            for a, b in zip(
                comparison[name + "_baseline"], comparison[name + "_context"], strict=True
            )
        ]
    net_better = int((comparison.delta_cumulative_return_25bp > 0).sum())
    ci = pd.DataFrame(confidence)
    robust_ci = ci.groupby(["target", "horizon"]).delta_ic_lo90.min()
    positive_ci = int((robust_ci > 0).sum())
    report.write_text(
        "# SRD — modèles enrichis par les contextes de marché\n\n"
        "**6 octobre 2026 · développement rétrospectif, sans confirmation indépendante.** "
        "[Contrat, folds et jointure](SRD_CONTEXT_INTEGRATION_CONTRACT.md).\n\n"
        "1 048 features d'action + **356 contextes = 1 404 variables**. "
        "K-means SBF120 à sept centres 2023, tables par régime ; prévisions des "
        "27 secteurs et CAC40/SBF120. Les producteurs sont ajustés avant chaque "
        "trimestre, seulement avec labels alors matures. La borne du contexte "
        "test 2026 reste juillet 2025. Les anciens exports 2026 ne remplissent pas le train.\n\n"
        "## Lecture des résultats\n\n"
        f"**56 modèles SRD, 12 tâches, 116 simulations de portefeuille.** "
        f"À 25 bp, le gagnant enrichi améliore le rendement net dans **{net_better}/12 tâches**. "
        f"L'écart d'IC apparié a trois intervalles 90 % entièrement positifs dans "
        f"**{positive_ci} tâches**. Le gain n'est donc pas automatique et les critères "
        "prédictifs et de portefeuille peuvent diverger.\n\n"
        + table(compact)
        + "\n\nRendements cumulés du portefeuille sur le test S1 2026, non annualisés. "
        "Les flèches lisent référence sans contexte → modèle enrichi. "
        "Types de modèles choisis sur validation, avant la lecture de ce test.\n\n"
        "## Couverture des contextes historiques\n\n"
        + table(profile)
        + "\n\nAucune action ni target SRD retirée. Scores disponibles à minuit UTC D+1, "
        "jointure as-of avant l'open suivant. Manquants explicites. Les vecteurs "
        "sectoriels sont globaux, sans affectation sectorielle des actions.\n\n"
        "## Gagnants de validation, avec et sans contexte, mêmes observations test\n\n"
        + table(
            overview[
                [
                    "target",
                    "horizon",
                    "feature_set",
                    "model",
                    "validation_metric",
                    "mean_ic",
                    "roc_auc",
                    "r2",
                    "n",
                    "cumulative_return_25bp",
                    "cumulative_return_45bp",
                    "max_drawdown_45bp",
                ]
            ]
        )
        + "\n\nGagnants fixés séparément sur S1 2025. AUC pour directions, IC moyen "
        "pour régressions. Référence = registre complet, top3, modèles et scores "
        "précédemment sauvegardés. Les contextes du train sont hors apprentissage "
        "de leurs producteurs. Le SRD sélectionne ses paramètres sur validation.\n\n"
        "## Écarts contexte moins référence\n\n"
        + table(
            comparison[
                [
                    "target",
                    "horizon",
                    "model_context",
                    "model_baseline",
                    "delta_mean_ic",
                    "paired_ic_cutoffs",
                    "paired_delta_ic",
                    "delta_roc_auc",
                    "delta_r2",
                    "delta_cumulative_return_25bp",
                    "delta_cumulative_return_45bp",
                ]
            ]
        )
        + "\n\nLes deux sélections peuvent choisir des types ou hyperparamètres différents. "
        "L'écart des IC moyens utilise les cutoffs définis de chaque modèle ; "
        "`paired_delta_ic` et ses intervalles utilisent seulement les cutoffs "
        "où les deux IC sont définis, comptés par `paired_ic_cutoffs`. "
        "Le CSV `comparison_matched_models.csv` compare également chaque type "
        "de modèle au même type de référence. Aucun choix sur les performances test.\n\n"
        "## Incertitude de l'écart d'IC\n\n"
        + table(pd.DataFrame(confidence))
        + "\n\nBootstrap apparié de cutoffs, 5 000 tirages, blocs 2/4/6. "
        "Intervalles individuels 90 %, conditionnels aux modèles choisis, sans "
        "correction multiple. Un naïf constant n'a pas d'IC défini. Les rendements "
        "de portefeuille n'ont pas d'intervalle dans cette publication.\n\n"
        "## Parts d'importance des blocs pour les gagnants RF/XGB\n\n"
        + table(selected_shares.drop(columns="model_id"))
        + "\n\nImpurity/gain du fit train 2024 seulement ; descriptif, sensible aux "
        "corrélations, sans interprétation causale. Aucune permutation marginale "
        "de milliers de colonnes ni nouvelle sélection au test.\n\n"
        "## Replays et artefacts\n\n"
        f"{upstream_audit['upstream_model_replays']} modèles de contexte "
        f"et {len(registry)} modèles SRD "
        "sauvegardés reproduisent les scores à la précision numérique. "
        f"L'ancrage K-means et {upstream_audit['regime_lookup_replays']} "
        "tables par régime sont également rejoués. "
        "Cohorte, labels et 1 048 valeurs d'action identiques à la référence. "
        "Portefeuilles top3, 25/45 bp forfaitaires, ledgers complets. "
        "Pas de fiscalité titre par titre, minimum par ordre "
        "ou certification de corporate actions.\n\n"
        "Dossier : `data/analysis/srd-context-v1/`. Config contextuelle et "
        "`srd_benchmark.toml` effectif figés. Contextes, disponibilité, folds, "
        "modèles, métriques, paniers et courbes sont conservés. "
        "Sources locales ignorées par Git.\n\n"
        "Reproduction : `uv run python scripts/srd_context.py inputs`, puis "
        "`context`, `data`, `run`, `publish`. Les périodes ont déjà été lues ; "
        "l'expérience n'apporte pas de confirmation indépendante.\n"
    )
    receipt = {
        "status": "development_context_integration_complete",
        "report_sha256": file_sha(report),
        "generator_sha256": file_sha(Path(__file__)),
        "summary_sha256": file_sha(output / "summary.json"),
        "integration_audit_sha256": file_sha(output / "integration_audit.json"),
        "replay_audit_sha256": file_sha(output / "comparison_replay_audit.json"),
        "context_sources_sha256": file_sha(output / "context/complete.json"),
        "baseline_manifest_sha256": file_sha(parent / "dataset_manifest.json"),
        "context_config_sha256": file_sha(output / "context_config.json"),
        "benchmark_config_sha256": file_sha(output / "srd_benchmark.toml"),
        "model_registry_sha256": file_sha(output / "model_registry.json"),
        "artifacts": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    report.with_suffix(".sources.json").write_text(json.dumps(receipt, indent=2) + "\n")
    marker.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
