"""Generate research tables directly from persisted artefacts, with validation-only winners."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from hocus_quant.analysis.confirmation_protocol import file_sha


def table(df: pd.DataFrame) -> str:
    def cell(v: Any) -> str:
        if isinstance(v, float):
            return "—" if pd.isna(v) else f"{v:.5f}"
        return str(v).replace("|", "/")

    columns = list(df.columns)
    return (
        "| "
        + " | ".join(columns)
        + " |\n| "
        + " | ".join("---" for _ in columns)
        + " |\n"
        + "\n".join(
            "| " + " | ".join(cell(v) for v in row) + " |"
            for row in df.itertuples(index=False, name=None)
        )
    )


def validation_winners(output: Path) -> pd.DataFrame:
    registry = json.loads((output / "model_registry.json").read_text())
    winners = []
    for target in [
        "direction_abs",
        "return_abs",
        "direction_rel",
        "rank_pct",
        "excursion_balance",
        "trend_tstat",
    ]:
        for h in [5, 10]:
            entries = [
                r
                for r in registry
                if r["target"] == target
                and r["horizon"] == h
                and r["validation_metric"] is not None
            ]
            best = max(entries, key=lambda r: r["validation_metric"])
            winners.append(
                {
                    k: best[k]
                    for k in [
                        "model_id",
                        "target",
                        "horizon",
                        "model",
                        "feature_set",
                        "validation_metric",
                    ]
                }
            )
    return pd.DataFrame(winners)


def render_report(root: Path, output: Path) -> dict[str, Any]:
    summary = json.loads((output / "summary.json").read_text())
    metrics = pd.read_parquet(output / "metrics.parquet")
    registry_path = output / "model_registry.json"
    registry = json.loads(registry_path.read_text())
    metric_records = pl.read_parquet(output / "metrics.parquet").to_dicts()
    for entry in registry:
        entry["metrics"] = {
            r["split"]: r for r in metric_records if r["model_id"] == entry["model_id"]
        }
        entry["metrics_sha256"] = file_sha(output / "metrics.parquet")
    registry_path.write_text(json.dumps(registry, indent=2, allow_nan=False) + "\n")
    backtest = pd.read_parquet(output / "backtest_summary.parquet")
    coverage = pd.read_parquet(output / "coverage.parquet")
    trajectory = pd.read_parquet(output / "trajectory_diagnostics.parquet")
    importance = pd.read_parquet(output / "feature_importances.parquet")
    extra = additional_diagnostics(output, importance)
    label_bounds = extra["label_bounds"]
    coverage = coverage.rename(columns={"last_outcome": "last_observed_path_end"}).merge(
        label_bounds, on=["target", "horizon", "split"], validate="many_to_one"
    )
    coverage.to_parquet(output / "label_coverage.parquet", index=False)
    winners = validation_winners(output)
    test = metrics[metrics.split == "test"]
    selected = winners.merge(
        test, on=["model_id", "target", "horizon", "model", "feature_set"], validate="one_to_one"
    )
    backselected = winners.merge(
        backtest,
        on=["model_id", "target", "horizon", "model", "feature_set"],
        validate="one_to_many",
    )
    overview = selected[
        [
            "target",
            "horizon",
            "model",
            "feature_set",
            "validation_metric",
            "roc_auc",
            "r2",
            "mean_ic",
            "median_ic",
            "positive_ic_fraction",
            "top10_lift",
            "n",
        ]
    ]
    first_set = "strict" if "strict" in set(coverage.feature_set) else coverage.feature_set.iloc[0]
    split_table = coverage[(coverage.feature_set == first_set) & (coverage.target == "return_abs")][
        [
            "horizon",
            "split",
            "first_cutoff",
            "last_cutoff",
            "last_usable_label_end",
            "cutoff_n",
            "eligible_rows",
            "usable_labels",
            "feature_missing_fraction",
        ]
    ]
    backcols = [
        "target",
        "horizon",
        "cost_bp",
        "cumulative_return",
        "excess_return",
        "max_drawdown",
        "turnover",
        "positions",
        "average_exposure",
        "flagged_closed_positions",
        "missing_entries",
        "unresolved_exits",
    ]
    diagnosis = selected.merge(
        trajectory, on=["model_id", "task", "target", "horizon", "model", "feature_set"]
    )
    ix = diagnosis[diagnosis.target.isin(["excursion_balance", "trend_tstat"])][
        [
            "target",
            "horizon",
            "score_vs_return_abs",
            "score_vs_excursion_balance",
            "score_vs_trend_tstat",
            "score_vs_volatility",
            "score_vs_max_upside",
            "score_vs_max_downside",
            "truth_vs_return_abs",
            "truth_vs_volatility",
        ]
    ]
    top = (
        importance[importance.model_id.isin(winners.model_id)]
        .sort_values("validation_permutation_drop", ascending=False)
        .head(20)
    )
    # Report every comparator, not the model which happened to win on test.
    comparison = (
        test.groupby(["model", "feature_set", "horizon"], dropna=False)
        .agg(
            mean_ic=("mean_ic", "mean"),
            median_r2=("r2", "median"),
            mean_auc=("roc_auc", "mean"),
            tasks=("model_id", "count"),
        )
        .reset_index()
    )
    selected_reg = selected[selected.model.isin(["rf", "xgb"])]
    positive = int((selected_reg.mean_ic > 0).sum())
    net = backselected[backselected.cost_bp == 50]
    beating_ew = []
    for _, r in net.iterrows():
        ew = backtest[
            (backtest.model == "universe")
            & (backtest.horizon == r.horizon)
            & (backtest.cost_bp == 50)
        ].iloc[0]
        beating_ew.append(float(r.cumulative_return - ew.cumulative_return))
    go = (
        len(selected_reg) > 0
        and positive >= len(selected_reg) * 0.75
        and sum(x > 0 for x in beating_ew) >= len(beating_ew) * 0.75
    )
    verdict = "GO exploratoire" if go else "NO-GO pour un second cycle de tuning en l'état"
    sections = [
        "# SPEC-008 — résultats reproductibles\n\n**Development backtest — not "
        "independent confirmation.**\n",
        f"Calculs : {summary['model_count']} modèles finaux, {summary['tuning_fits']} fits "
        f"de découverte/validation, {summary['final_retrain_fits']} retrains. "
        "XGBoost CPU est la référence principale.\n",
        f"Lock `{summary['lock_sha256']}` ; "
        f"registry additif `{summary['target_registry_sha256']}`.\n",
        f"Feature sets : `{summary.get('feature_sets', {'strict': 85, 'strong': 138})}`. "
        "Le set `all`, lorsqu'il est présent, conserve toutes les entrées du registre, "
        "sans sélection fondée sur leurs outcomes. L'univers et les labels sont "
        "identiques au benchmark initial.\n",
        "**Contamination de sélection :** strict/strong ont été choisis avec des "
        "outcomes de 2025 **et 2026**. L'absence de tuning sur 2026 dans ce code ne"
        " supprime pas cette connaissance préalable. Aucun chiffre ci-dessous n'est"
        " une confirmation indépendante.\n",
        "## 1. Splits exacts et effectifs\n",
        table(split_table),
        "\nLes effectifs sont des couples entité/cutoff répétés, pas des "
        "observations indépendantes. Les lignes dont la target traverse une "
        "frontière restent dans la matrice/prédictions ; leur label est nul. Le "
        "purge/embargo calendaire est appliqué à toutes les entités d'un cutoff.\n",
        "## 2. Modèle retenu exclusivement sur validation, puis lu en S1 2026\n",
        table(overview),
        "\nPour les directions : ROC AUC validation. Pour les régressions : IC "
        "Spearman moyen par cutoff validation. Les modèles/feature sets ne sont pas"
        " rechoisis selon leur test. AUC pooled et R² pooled sont des diagnostics ;"
        " le ranking principal utilise les IC par date.\n",
        "## 3. RF/XGB, baselines, strict/strong, H5/H10\n",
        table(comparison),
        "\nLes moyennes regroupant des targets différentes résument les expériences,"
        " sans test de significativité ni classement scientifique universel. Voir "
        f"les {len(test)} lignes de métriques test pour les comparaisons tâche par tâche.\n",
        "## 4. Backtests des mêmes gagnants de validation\n",
        table(backselected[backcols]),
        "\nFrais all-in **aller-retour**, moitié à l'entrée et moitié à la sortie. "
        "Portefeuilles sans levier, cash non rémunéré, compartiments de capital "
        "fixes (2 en H5 / 3 en H10), top 10 %, entrée next_open, sortie close du "
        "H-ième jour commun. Le turnover est la somme des achats + ventes rapportés"
        " à la NAV précédente.\n",
        "### Baselines de portefeuille\n",
        table(
            backtest[backtest.model == "universe"][
                [
                    "horizon",
                    "cost_bp",
                    "cumulative_return",
                    "benchmark_return",
                    "max_drawdown",
                    "turnover",
                    "average_exposure",
                ]
            ]
        ),
        "\nEqual-weight universe suit exactement les mêmes "
        "compartiments/cutoffs/frais. CAC AllShares est un buy-and-hold next_open →"
        " dernier close sur la même fenêtre ; son exposition est différente. Aucun "
        "dividende ni ajustement certifié. L'annualisation du rendement n'est "
        "publiée qu'à partir de 126 séances. Les Sharpe descriptifs sur S1 restent "
        "fragiles.\n",
        "## 5. Excursion balance et trend t-stat\n",
        table(ix),
        "\nLes corrélations pooled ci-dessus diagnostiquent les trajectoires et leur"
        " lien à la volatilité ; elles ne prouvent aucune causalité. "
        "`excursion_balance` est max+min des rendements close futurs sans ancrage "
        "artificiel à zéro. Le t-stat futur est calculé sur exactement H closes "
        "normalisés base 100 ; les trajectoires parfaitement linéaires atteignent "
        "le plafond numérique ±1e6, les plates valent 0.\n",
        "## 6. Features : gain/impurity et permutation sur validation uniquement\n",
        table(
            top[
                [
                    "target",
                    "horizon",
                    "feature_set",
                    "model",
                    "feature_id",
                    "importance_type",
                    "gain_or_impurity",
                    "validation_permutation_drop",
                ]
            ]
        ),
        "### Stabilité des importances\n",
        table(extra["importance_summary"]),
        "\nPermutation de chaque feature verrouillée, une réplication à seed fixe, "
        "estimateur entraîné sur 2024 uniquement. Cette importance marginale est "
        "instable et diluée par la redondance ; elle ne sert pas à retirer des "
        "variables. RF expose impurity ; XGB gain. SHAP n'est pas requis et n'est "
        "pas ajouté au premier benchmark.\n",
        "## 7. Stabilité par cutoff et extrêmes\n",
        "### Exemples de trajectoires observées, choisis à titre illustratif\n",
        table(extra["trajectory_examples"]),
        "Les colonnes median IC / fraction IC>0 de la table 2 et les courbes Model "
        "Lab montrent la stabilité. `cutoff_metrics.parquet` et "
        "`decile_metrics.parquet` conservent tous les cutoffs, spreads D10−D1 et "
        "monotonicités. Les lifts top10/top20/bottom10 sont les moyennes des taux "
        "positifs relatifs à la population de chaque date ; les ex æquo peuvent "
        "agrandir ces groupes. Le portefeuille utilise, lui, exactement ceil(10 "
        "%×N), avec départage stable par ID. Pour `rank_pct`, le lift de taux "
        "positif vaut mécaniquement 1 : tous les percentiles sont positifs. "
        "Il faut lire l'IC, les écarts de percentile et les rendements du portefeuille.\n",
        "## 8. Incohérences, leakage et conclusion\n",
        f"**{verdict}.** Lecture descriptive : {positive}/{len(selected_reg)} gagnants RF/XGB "
        f"ont un IC test positif ; {sum(x > 0 for x in beating_ew)}/{len(beating_ew)} "
        "gagnants de validation dépassent l'equal-weight comparable à 50 bp. "
        "Cette règle de lecture ne crée ni p-value ni preuve d'alpha.\n",
        "Avant un cycle plus réaliste : prix/corporate actions certifiés, univers "
        "daté, période réellement neuve, calendrier/latence et coûts de liquidité. "
        "Aucun résultat de SPEC-007 n'est utilisé. Les nouvelles targets et views "
        "sont isolées : le registre historique gelé, le lock et les fichiers "
        "SPEC-007 sont byte-identiques.\n",
        "## 9. Artefacts, reproductibilité et rapport intégral\n",
        f"SHA de base du run : `{summary['code_sha']}` ; "
        f"dirty lors du run : `{summary['working_tree_dirty']}`. "
        "Les empreintes exactes des fichiers scientifiques utilisés sont dans summary/model "
        "registry, et celles des datasets dans dataset_manifest. "
        "Le SHA Git final est indiqué au compte rendu.\n",
        "Tables locales sous `data/analysis/spec008-model-lab` (hors Git), modèles "
        "joblib, registre JSON, métriques, prédictions, déciles, calibration, "
        "importances, trajectoires, trades, equity et résumé. `uv run python "
        "scripts/model_lab_spec008.py report` régénère ce Markdown à partir des "
        "artefacts.\n",
        "### Toutes les métriques test\n",
        table(
            test[
                [
                    "target",
                    "horizon",
                    "feature_set",
                    "model",
                    "roc_auc",
                    "pr_auc",
                    "balanced_accuracy",
                    "accuracy",
                    "log_loss",
                    "brier",
                    "calibration_ece",
                    "r2",
                    "rmse",
                    "mae",
                    "mean_ic",
                    "median_ic",
                    "positive_ic_fraction",
                    "top10_lift",
                    "n",
                ]
            ]
        ),
        "### Couverture par tâche\n",
        table(
            coverage[
                [
                    "target",
                    "horizon",
                    "feature_set",
                    "split",
                    "eligible_rows",
                    "usable_labels",
                    "neutral_n",
                    "future_warning_n",
                    "uninterpretable_n",
                    "feature_missing_fraction",
                ]
            ]
        ),
    ]
    report_stem = summary.get("report_stem", "SPEC_008_RESULTS")
    if not report_stem.replace("_", "").isalnum():
        raise ValueError("invalid report stem")
    report = root / "docs" / f"{report_stem}.md"
    report.write_text("\n".join(sections) + "\n")
    receipt = {
        "report_sha256": file_sha(report),
        "inputs": {
            p.name: file_sha(p)
            for p in sorted(output.iterdir())
            if p.is_file() and p.suffix in {".parquet", ".json"}
        },
        "report_generator_sha256": file_sha(Path(__file__)),
        "summary_sha256": file_sha(output / "summary.json"),
        "verdict": verdict,
    }
    (root / "docs" / f"{report_stem}.sources.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def additional_diagnostics(output: Path, importances: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Descriptive artefacts only; never change model selection or fitted predictions."""
    importance_groups = []
    for mid, part in importances.groupby("model_id", sort=True):
        row = part.iloc[0]
        names = set(
            part.sort_values("validation_permutation_drop", ascending=False).head(20).feature_id
        )
        importance_groups.append(
            {
                "model_id": mid,
                "model": row.model,
                "feature_set": row.feature_set,
                "target": row.target,
                "horizon": int(row.horizon),
                "features": names,
            }
        )
    stability = []
    for a, b in combinations(importance_groups, 2):
        if a["model"] != b["model"] or a["feature_set"] != b["feature_set"]:
            continue
        kind = (
            "horizon"
            if a["target"] == b["target"]
            else "target"
            if a["horizon"] == b["horizon"]
            else "target_and_horizon"
        )
        overlap = len(a["features"] & b["features"])
        stability.append(
            {
                "model_id_a": a["model_id"],
                "model_id_b": b["model_id"],
                "model": a["model"],
                "feature_set": a["feature_set"],
                "comparison": kind,
                "top20_overlap": overlap,
                "jaccard": overlap / len(a["features"] | b["features"]),
            }
        )
    stab = pd.DataFrame(stability)
    stab.to_parquet(output / "importance_stability.parquet", index=False)
    compact = stab.groupby(["model", "feature_set", "comparison"], as_index=False).agg(
        mean_overlap=("top20_overlap", "mean"),
        median_jaccard=("jaccard", "median"),
        pairs=("jaccard", "count"),
    )
    targets = pd.read_parquet(output / "targets.parquet")
    features = pd.read_parquet(output / "features.parquet")
    merged = features.merge(
        targets[["cutoff", "entity_id", "horizon", "split"]], on=["cutoff", "entity_id"]
    )
    sets = json.loads((output / "feature_sets.json").read_text())["ids"]
    bounds = []
    for family in [
        "direction_abs",
        "return_abs",
        "direction_rel",
        "rank_pct",
        "excursion_balance",
        "trend_tstat",
    ]:
        usable = targets[
            targets[family].notna() & targets.split.isin(["train", "validation", "test"])
        ]
        if family.startswith("direction"):
            usable = usable[usable[family] != 0]
        for (h, split), part in usable.groupby(["horizon", "split"]):
            bounds.append(
                {
                    "target": family,
                    "horizon": int(h),
                    "split": split,
                    "last_usable_label_end": str(part.target_end.max()),
                }
            )
    missing = []
    for (h, split), part in merged[merged.split.isin(["train", "validation", "test"])].groupby(
        ["horizon", "split"]
    ):
        for tier, ids in sets.items():
            for feature in ids:
                missing.append(
                    {
                        "horizon": int(h),
                        "split": split,
                        "feature_set": tier,
                        "feature_id": feature,
                        "missing_n": int(part[feature].isna().sum()),
                        "n": len(part),
                        "missing_fraction": float(part[feature].isna().mean()),
                    }
                )
    pd.DataFrame(missing).to_parquet(output / "feature_missingness.parquet", index=False)
    examples = []
    for h in [5, 10]:
        rows = targets[
            (targets.horizon == h)
            & (targets.split == "test")
            & (targets.future_quality == "approved")
            & (targets.trend_tstat.notna())
        ].copy()
        lower = rows[rows.return_abs.abs() <= rows.return_abs.abs().median()]
        regular = lower.iloc[lower.trend_tstat.abs().argmax()]
        upper = rows[rows.return_abs.abs() >= rows.return_abs.abs().quantile(0.9)]
        irregular = upper.iloc[upper.trend_tstat.abs().argmin()]
        for label, row in [
            ("rendement modeste / trajectoire régulière", regular),
            ("grand mouvement / t-stat faible", irregular),
        ]:
            examples.append(
                {
                    "case": label,
                    "entity_id": row.entity_id,
                    "cutoff": str(row.cutoff),
                    "horizon": h,
                    "return_abs": float(row.return_abs),
                    "trend_tstat": float(row.trend_tstat),
                    "excursion_balance": float(row.excursion_balance),
                    "volatility": float(row.volatility),
                }
            )
    ex = pd.DataFrame(examples)
    ex.to_parquet(output / "trajectory_examples.parquet", index=False)
    eq = pd.read_parquet(output / "backtest_equity.parquet")
    valid_cutoffs = set(targets[targets.split == "test"].cutoff.unique())
    eq[eq.session_date.isin(valid_cutoffs)].to_parquet(
        output / "backtest_cutoff_equity.parquet", index=False
    )
    return {
        "importance_summary": compact,
        "trajectory_examples": ex,
        "label_bounds": pd.DataFrame(bounds),
    }
