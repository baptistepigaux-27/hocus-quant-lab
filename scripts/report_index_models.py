"""Index performance diagnostics and retrospective SRD-context score exports."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.report import table


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "data/analysis/spec008-index-model-lab"
    (output / "index_report_complete.json").unlink(missing_ok=True)
    run = json.loads((output / "summary.json").read_text())
    dataset = json.loads((output / "dataset_manifest.json").read_text())
    for name, sha in dataset["source_sha256"].items():
        if file_sha(output / name) != sha:
            raise ValueError(f"Frozen dataset changed: {name}")
    for name, sha in run["artifact_sha256"].items():
        if file_sha(output / name) != sha:
            raise ValueError(f"Frozen run changed: {name}")
    for name, sha in run["source_sha256"].items():
        if file_sha(root / name) != sha:
            raise ValueError(f"Model engine changed since the run: {name}")
    registry = pd.DataFrame(json.loads((output / "model_registry.json").read_text()))
    selected = registry[registry.validation_winner_within_feature_set]
    keys = ["model_id", "feature_set", "target", "horizon", "model"]
    winners = selected[keys + ["validation_metric"]].copy()
    metrics = pd.read_parquet(output / "metrics.parquet")
    overview = winners.merge(metrics[metrics.split == "test"], on=keys, validate="one_to_one")
    validation = metrics[metrics.split == "validation"][["model_id", "mean_ic", "roc_auc"]]
    overview = overview.merge(
        validation.rename(
            columns={"mean_ic": "validation_mean_ic", "roc_auc": "validation_roc_auc"}
        ),
        on="model_id",
        validate="one_to_one",
    )
    cutoffs = pd.read_parquet(output / "cutoff_metrics.parquet")
    history = cutoffs[(cutoffs.split == "test") & cutoffs.model_id.isin(winners.model_id)]
    intervals = []
    rng = np.random.default_rng(20261006)
    for mid, part in history.groupby("model_id", sort=True):
        values = part.sort_values("cutoff").ic.dropna().to_numpy()
        for block in [2, 4, 6]:
            if len(values) < 6:
                continue
            starts = rng.integers(0, len(values), size=(10000, math.ceil(len(values) / block)))
            indices = ((starts[..., None] + np.arange(block)) % len(values)).reshape(10000, -1)
            samples = values[indices[:, : len(values)]].mean(axis=1)
            lo, hi = np.quantile(samples, [0.05, 0.95])
            intervals.append(
                {
                    "model_id": mid,
                    "block_cutoffs": block,
                    "ic_lo90": lo,
                    "ic_hi90": hi,
                    "bootstrap_positive_fraction": float((samples > 0).mean()),
                }
            )
    confidence = pd.DataFrame(intervals)
    if len(confidence):
        overview = overview.merge(
            confidence[confidence.block_cutoffs == 4], on="model_id", how="left"
        )
    predictions = pd.read_parquet(output / "predictions.parquet")
    names = pd.read_parquet(output / "source_market.parquet")[
        ["entity_id", "display_name"]
    ].drop_duplicates()
    diagnostics = []
    picks = []
    for (mid, split, cutoff), frame in predictions.groupby(
        ["model_id", "split", "cutoff"], sort=True
    ):
        finite = frame[np.isfinite(frame.score)].sort_values(
            ["score", "entity_id"], ascending=[False, True], kind="stable"
        )
        if not len(finite):
            continue
        n = max(1, math.ceil(len(finite) * 0.03))
        top, bottom = finite.head(n), finite.tail(n)
        a, b, u = top.return_abs.mean(), bottom.return_abs.mean(), finite.return_abs.mean()
        metadata = finite.iloc[0][["target", "horizon", "model", "feature_set"]].to_dict()
        diagnostics.append(
            {
                "model_id": mid,
                "split": split,
                "cutoff": cutoff,
                **metadata,
                "selection_n": n,
                "top_observed_n": int(top.return_abs.notna().sum()),
                "top3_complete": bool(top.return_abs.notna().sum() == n),
                "eligible_n": len(finite),
                "universe_observed_n": int(finite.return_abs.notna().sum()),
                "constant_scores": finite.score.nunique() <= 1,
                "top3_mean_future_return": a,
                "bottom3_mean_future_return": b,
                "universe_mean_future_return": u,
                "universe_mean_on_top_observed_cutoffs": u if np.isfinite(a) else np.nan,
                "top_minus_universe": a - u,
                "top_minus_bottom": a - b,
            }
        )
        if mid in set(winners.model_id) and split == "test":
            for r in top.itertuples():
                picks.append(
                    {
                        "model_id": mid,
                        "cutoff": cutoff,
                        "entity_id": r.entity_id,
                        **metadata,
                        "score": r.score,
                        "future_return": r.return_abs,
                        "target_end": r.target_end,
                        "future_quality": r.future_quality,
                    }
                )
    diagnostic_frame = pd.DataFrame(diagnostics)
    diagnostic_summary = (
        diagnostic_frame.groupby(keys + ["split"])
        .agg(
            top3_mean_future_return=("top3_mean_future_return", "mean"),
            universe_mean_future_return=("universe_mean_future_return", "mean"),
            universe_mean_on_top_observed_cutoffs=("universe_mean_on_top_observed_cutoffs", "mean"),
            top_minus_universe=("top_minus_universe", "mean"),
            top_minus_bottom=("top_minus_bottom", "mean"),
            minimum_selected=("selection_n", "min"),
            maximum_selected=("selection_n", "max"),
            mean_eligible_n=("eligible_n", "mean"),
            diagnostic_cutoff_n=("cutoff", "nunique"),
            top3_observed_cutoffs=("top3_mean_future_return", "count"),
            top3_complete_cutoffs=("top3_complete", "sum"),
            constant_scores=("constant_scores", "all"),
        )
        .reset_index()
    )
    overview = overview.merge(
        diagnostic_summary[diagnostic_summary.split == "test"].drop(columns="split"),
        on=keys,
        validate="one_to_one",
    )
    test_picks = pd.DataFrame(picks).merge(
        names, on="entity_id", how="left", validate="many_to_one"
    )
    # Validation predictions depend on hyperparameters selected using all of S1 2025.
    # Export only nominally out-of-time test scores, with reconstructed availability explicit.
    export = predictions[
        (predictions.split == "test") & predictions.model_id.isin(winners.model_id)
    ]
    export = export[keys + ["cutoff", "entity_id", "score"]].copy()
    export["available_at_modeled"] = (
        (pd.to_datetime(export.cutoff) + pd.Timedelta(days=1))
        .dt.tz_localize("UTC")
        .dt.tz_convert("Europe/Paris")
    )
    export["training_label_end"] = "2025-06-30"
    export["hyperparameter_selection_end"] = "2025-06-30"
    export["pit_grade"] = "reconstructed"
    export["independent_confirmation"] = False
    export["retrospective_protocol"] = True
    export["historical_calendar_harmonized"] = True
    export["ready_for_srd_integration"] = False
    export["feature_stream"] = (
        export.entity_id
        + ":"
        + export.target
        + ":h"
        + export.horizon.astype(str)
        + ":"
        + export.model_id
    )
    if not (pd.to_datetime(export.cutoff) > pd.Timestamp("2025-06-30")).all():
        raise ValueError("Score export includes observations before selection ended")
    features = pd.read_parquet(output / "features.parquet")
    profiles = []
    feature_ids = [
        r["feature_id"]
        for r in json.loads((output / "feature_registry.json").read_text())["definitions"]
    ]
    targets = pd.read_parquet(output / "targets.parquet")
    outcome_panel = targets[targets.split.isin(["train", "validation", "test"])].copy()
    outcome_panel["calendar_days_to_target"] = (
        pd.to_datetime(outcome_panel.target_end) - pd.to_datetime(outcome_panel.cutoff)
    ).dt.days
    label_profiles = []
    for (group, split, horizon), frame in outcome_panel.groupby(["group", "split", "horizon"]):
        observed = frame[frame.return_abs.notna()]
        label_profiles.append(
            {
                "group": group,
                "split": split,
                "horizon": horizon,
                "predicted_rows": len(frame),
                "observed_return_rows": len(observed),
                "boundary_censored_rows": int(frame.purge_reason.str.contains("boundary").sum()),
                "calendar_missing_rows": int(
                    (frame.purge_reason == "future_calendar_quote_missing").sum()
                ),
                "median_calendar_days_observed": observed.calendar_days_to_target.median(),
                "max_calendar_days_observed": observed.calendar_days_to_target.max(),
            }
        )
    label_profile = pd.DataFrame(label_profiles)
    calendar_review = outcome_panel[
        outcome_panel.return_abs.notna()
        & (outcome_panel.calendar_days_to_target > 3 * outcome_panel.horizon)
    ].merge(names, on="entity_id", validate="many_to_one")
    test_picks = test_picks.merge(
        targets[
            [
                "cutoff",
                "entity_id",
                "horizon",
                "purge_reason",
                "reference_quote_date",
                "index_quote_end",
                "calendar_complete",
            ]
        ],
        on=["cutoff", "entity_id", "horizon"],
        validate="many_to_one",
    )
    bounds = targets[targets.horizon == 5][["cutoff", "entity_id", "split"]]
    features = features.merge(bounds, on=["cutoff", "entity_id"], validate="one_to_one")
    for (group, split), frame in features.groupby(["research_group", "split"]):
        if split not in ["train", "validation", "test"]:
            continue
        matrix = frame[feature_ids]
        profiles.append(
            {
                "group": group,
                "split": split,
                "rows": len(frame),
                "min_series": int(frame.groupby("cutoff").entity_id.nunique().min()),
                "max_series": int(frame.groupby("cutoff").entity_id.nunique().max()),
                "registry_ids": len(feature_ids),
                "entirely_missing": int(matrix.isna().all().sum()),
                "constant_nonmissing": int((matrix.nunique() == 1).sum()),
                "mean_missing_fraction": float(matrix.isna().mean().mean()),
                "close_only_rows": int(frame.close_only_at_T.sum()),
            }
        )
    profile = pd.DataFrame(profiles)
    for name, frame in [
        ("index_overview", overview),
        ("index_ic_confidence", confidence),
        ("index_top3_cutoffs", diagnostic_frame),
        ("index_top3_summary", diagnostic_summary),
        ("index_selected_picks", test_picks),
        ("historical_index_score_features", export),
        ("index_feature_profiles", profile),
        ("index_label_profiles", label_profile),
        ("index_calendar_review", calendar_review),
    ]:
        frame.to_parquet(output / f"{name}.parquet", index=False)
        frame.to_csv(output / f"{name}.csv", index=False)
    fig = px.line(
        history,
        x="cutoff",
        y="ic",
        color="target",
        facet_row="feature_set",
        facet_col="horizon",
        markers=True,
        title="IC par cutoff · gagnants de validation",
    )
    fig.write_html(output / "index_ic_history.html", include_plotlyjs=True)
    columns = [
        "feature_set",
        "target",
        "horizon",
        "model",
        "validation_mean_ic",
        "mean_ic",
        "roc_auc",
        "r2",
        "ic_lo90",
        "ic_hi90",
        "top3_mean_future_return",
        "universe_mean_future_return",
        "universe_mean_on_top_observed_cutoffs",
        "top_minus_universe",
        "minimum_selected",
        "maximum_selected",
        "top3_observed_cutoffs",
        "top3_complete_cutoffs",
    ]
    report = root / "docs/SPEC_008_INDICES_RESULTS.md"
    inventory = pd.read_parquet(output / "universe_inventory.parquet")
    rank_reading = overview[overview.target == "rank_pct"].sort_values(["feature_set", "horizon"])
    rank_table = pd.DataFrame(
        {
            "Groupe": rank_reading.feature_set,
            "Horizon": rank_reading.horizon,
            "Modèle": rank_reading.model,
            "IC validation 2025": rank_reading.validation_mean_ic,
            "IC test 2026": rank_reading.mean_ic,
            "Intervalle IC 90 %": rank_reading.apply(
                lambda r: f"[{r.ic_lo90:+.3f} ; {r.ic_hi90:+.3f}]", axis=1
            ),
            "Top3 moyen (%)": 100 * rank_reading.top3_mean_future_return,
            "Groupe mêmes cutoffs (%)": 100 * rank_reading.universe_mean_on_top_observed_cutoffs,
        }
    )
    report.write_text(
        "# Indices — première performance des modèles\n\n"
        "**Développement rétrospectif. Scores destinés à une future recherche de features "
        "de contexte SRD ; aucune intégration au modèle SRD dans ce run.**\n\n"
        "[Contrat fixé avant entraînement](SPEC_008_INDICES_CONTRACT.md). "
        f"{run['model_count']} modèles finaux, {run['tuning_fits']} fits de validation, "
        "deux groupes et six targets H5/H10. Train 2024, validation S1 2025, "
        "retrain 2024 + S1 2025, test S1 2026.\n\n"
        "## Lecture rapide — rang du rendement\n\n"
        + table(rank_table)
        + "\n\nCe résumé reprend les modèles choisis sur validation, sans retenir le "
        "meilleur modèle test après coup. La conservation du signe se lit entre "
        "validation et test ; les intervalles individuels restent "
        "conditionnels au corpus et au protocole. Les paniers top3 représentent deux "
        "indices de marché ou un indice sectoriel par cutoff, sans composition.\n\n"
        "## Périmètre effectif et disponibilité des features\n\n"
        + table(profile)
        + "\n\nLes 1 048 IDs sont conservés ; colonnes constantes/absentes et masques "
        "intraday/volume sont décrits par le contrat. Le nombre de séries varie selon "
        "les dates et la qualité à T. En juin 2026, des trous de cotation dans plusieurs "
        "STOXX sectoriels déclenchent le seuil de fraîcheur à T et réduisent le panel.\n\n"
        "### Durée réelle et couverture des labels\n\n"
        + table(label_profile)
        + "\n\nH5/H10 comptent les séances du calendrier commun CAC40. La quote native "
        "est la dernière connue jusqu'à chaque séance, avec un âge maximal de trois "
        "jours calendaires ; un trou plus long rend le label indisponible. Un label "
        "franchissant la frontière de période reste censuré, alors que son score à T "
        "est conservé. Le panier est choisi avant examen des outcomes et aucun indice "
        "sans résultat exploitable n'est remplacé.\n\n"
        "**Correction avant publication :** la v1 a été retirée après le contrôle "
        "indépendant : une coupe à minuit Paris excluait le close D disponible à "
        "minuit UTC D+1, et quelques horizons propres aux séries traversaient des "
        "trous de six mois. Les données et modèles v2 ont été entièrement recalculés "
        "après correction de l'heure et du calendrier, sans ajustement au résultat "
        "test. La v1 reste archivée pour audit. Les snapshots SRD portent déjà "
        "minuit Paris et sont cohérents avec leur coupe historique ; leurs "
        "artefacts restent conservés. "
        "L'export reste `ready_for_srd_integration=false` : le raccordement as-of, "
        "les scores OOF et une confirmation indépendante restent à construire.\n\n"
        "## Gagnants choisis sur validation — performance test\n\n"
        "La sélection est mécanique : AUC pooled de validation pour la direction, "
        "IC temporel moyen pour les régressions. Aucun seuil de performance minimale "
        "ne force l'abstention. Un meilleur IC encore négatif ne valide donc pas "
        "un pouvoir de classement. L'IC d'une baseline à score constant est indéfini ; "
        "elle reste visible dans les métriques comparatives.\n\n"
        "Les IC sont cross-sectionnels par date, puis moyennés dans le temps. "
        "AUC directions : mesure pooled. Les rendements ci-dessous sont en fractions "
        "(0.01 = 1 %), **moyennes de fenêtres futures par cutoff**, sans composition. "
        "Les paniers ne représentent pas un portefeuille exécuté. Prix en quote native, "
        "sans harmonisation de devises ou des conventions de dividendes.\n\n"
        + table(overview[columns].sort_values(["feature_set", "target", "horizon"]))
        + "\n\nUne baseline à score constant donne un panier choisi par identifiant, "
        "sans pouvoir de classement. Les labels durs ininterprétables sont absents, "
        "sans remplacement d'un titre sélectionné. Les scopes sont classés séparément.\n\n"
        "Les moyennes de paniers utilisent les résultats disponibles parmi les choix "
        "à T ; la couverture par cutoff est conservée. Un cutoff sans aucun label "
        "de panier n'entre pas dans sa moyenne. L'écart au groupe est moyenné sur les "
        "cutoffs où les deux moyennes sont calculables.\n\n"
        "## Incertitude et dépendances\n\n"
        "Intervalles individuels à 90 % par bootstrap circulaire de la moyenne des IC, "
        "10 000 réplications, seed 20261006 ; blocs 2/4/6. Le tableau présente les blocs "
        "de 4. Pas de correction multiple ; petit nombre de dates, facteurs communs entre "
        "indices et chevauchement H10. Aucun seuil de preuve d'alpha n'est attribué.\n\n"
        "## Scores disponibles pour la suite SRD\n\n"
        f"`historical_index_score_features.parquet` contient {len(export)} lignes et "
        f"{export.feature_stream.nunique()} flux de score pour les gagnants figés sur validation. "
        "Uniquement test S1 2026 : dates de disponibilité **modélisées**, date limite "
        "d'apprentissage/sélection 30 juin 2025, grade reconstruit explicite, aucun target "
        "futur dans cet export. Les prédictions de validation ne sont pas des features "
        "historiquement utilisables, car leurs paramètres utilisent la validation complète. "
        "Le raccordement SRD doit produire des scores OOF pour 2024/2025, définir le "
        "mapping des contextes et réaliser une jointure as-of. Il n'est pas exécuté ici.\n\n"
        "## Inventaire des candidats et exclusions\n\n"
        + table(inventory[["code", "name", "research_group", "reason"]].drop_duplicates("code"))
        + "\n\n## Artefacts et reproduction\n\n"
        "Dossier `data/analysis/spec008-index-model-lab/` : snapshots source, manifestes, "
        "modèles, essais, métriques, calibration, déciles et scores. "
        "`index_selected_picks.csv` donne les indices sélectionnés et leurs résultats "
        "futurs. `index_top3_cutoffs.csv` détaille les paniers et leur couverture. "
        "`index_ic_history.html` est un graphique interactif standalone.\n\n"
        "Après les commandes data/run du contrat : `uv run python scripts/report_index_models.py`. "
        "Aucune modification des données SRD ou du protocole SPEC-007.\n"
    )
    receipt = {
        "run_summary_sha256": file_sha(output / "summary.json"),
        "dataset_manifest_sha256": file_sha(output / "dataset_manifest.json"),
        "generator_sha256": file_sha(Path(__file__)),
        "audit_generator_sha256": file_sha(root / "scripts/audit_index_dataset.py"),
        "report_sha256": file_sha(report),
        "artifacts": {p.name: file_sha(p) for p in output.glob("index_*.parquet")},
        "score_export_sha256": file_sha(output / "historical_index_score_features.parquet"),
        "model_engine_sha256": run["source_sha256"],
        "supporting_source_sha256": {
            name: file_sha(root / name)
            for name in [
                "src/hocus_quant/features/factory.py",
                "src/hocus_quant/features/registry.py",
                "src/hocus_quant/validation/market_quality.py",
            ]
        },
    }
    (root / "docs/SPEC_008_INDICES_RESULTS.sources.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    (output / "index_report_ready.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        overview[columns].sort_values(["feature_set", "target", "horizon"]).to_string(index=False)
    )


if __name__ == "__main__":
    main()
