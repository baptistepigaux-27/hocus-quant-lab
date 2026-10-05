"""Compare the full registry with the unchanged Strict/Strong development benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.report import table


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    original = root / "data/analysis/spec008-model-lab"
    expanded = root / "data/analysis/spec008-model-lab-all-features"
    paths = [original, expanded]
    registries = pd.concat(
        [pd.DataFrame(json.loads((p / "model_registry.json").read_text())) for p in paths],
        ignore_index=True,
    )
    metrics = pd.concat([pd.read_parquet(p / "metrics.parquet") for p in paths], ignore_index=True)
    backtests = pd.concat(
        [pd.read_parquet(p / "backtest_summary.parquet") for p in paths], ignore_index=True
    )
    # Both runs contain the same named universe baselines; only model portfolios join here.
    backtests = backtests[backtests.model != "universe"]
    winners = (
        registries.sort_values("validation_metric", ascending=False, kind="stable")
        .groupby(["target", "horizon", "feature_set"], sort=True)
        .head(1)
    )
    wanted = ["model_id", "target", "horizon", "feature_set", "model", "validation_metric"]
    columns = [
        *wanted,
        "roc_auc",
        "r2",
        "mean_ic",
        "median_ic",
        "positive_ic_fraction",
        "top10_lift",
    ]
    compared = winners[wanted].merge(
        metrics[metrics.split == "test"],
        on=["model_id", "target", "horizon", "feature_set", "model"],
        validate="one_to_one",
    )[columns]
    for cost in [0, 10, 25, 50]:
        costs = backtests[backtests.cost_bp == cost][["model_id", "cumulative_return"]].rename(
            columns={"cumulative_return": f"return_{cost}bp"}
        )
        compared = compared.merge(costs, on="model_id", validate="one_to_one")
    compared = compared.merge(
        backtests[backtests.cost_bp == 25][["model_id", "turnover", "max_drawdown"]],
        on="model_id",
        validate="one_to_one",
    ).sort_values(["target", "horizon", "feature_set"])
    compared.to_parquet(expanded / "comparison_validation_winners.parquet", index=False)
    compared.to_csv(expanded / "comparison_validation_winners.csv", index=False)
    # A separate matched-model comparison avoids conflating feature count and model choice.
    tested = metrics[metrics.split == "test"]
    broad = tested[tested.feature_set == "all"]
    narrow = tested[tested.feature_set != "all"]
    matched = broad.merge(narrow, on=["target", "horizon", "model"], suffixes=("_all", "_locked"))
    matched["delta_ic"] = matched.mean_ic_all - matched.mean_ic_locked
    matched["delta_auc"] = matched.roc_auc_all - matched.roc_auc_locked
    matched["delta_r2"] = matched.r2_all - matched.r2_locked
    matched.to_parquet(expanded / "comparison_matched_models.parquet", index=False)
    baseline = (
        compared[compared.feature_set != "all"]
        .sort_values("validation_metric", ascending=False, kind="stable")
        .groupby(["target", "horizon"], sort=True)
        .head(1)
    )
    delta = compared[compared.feature_set == "all"].merge(
        baseline, on=["target", "horizon"], suffixes=("_all", "_baseline"), validate="one_to_one"
    )
    for metric in ["mean_ic", "roc_auc", "r2", "return_25bp", "return_50bp"]:
        delta[f"delta_{metric}"] = delta[f"{metric}_all"] - delta[f"{metric}_baseline"]
    delta.to_parquet(expanded / "comparison_best_baseline.parquet", index=False)
    profile = pd.read_parquet(expanded / "feature_missingness.parquet")
    profiles = []
    for (h, split), part in profile.groupby(["horizon", "split"]):
        profiles.append(
            {
                "horizon": h,
                "split": split,
                "features": len(part),
                "entirely_missing": int((part.missing_fraction == 1).sum()),
                "mean_missing_fraction": part.missing_fraction.mean(),
            }
        )
    body = [
        "# SPEC-008 — toutes les variables versus Strict/Strong\n",
        "**Development backtest — not independent confirmation.**\n",
        "Toutes les 1 048 entrées du registre sont fournies ensemble aux modèles. "
        "Aucun classement univarié ni filtre d'outcome ne restreint ce set. "
        "Les fenêtres 504, constantes et aliases sont conservés. "
        "Les formules restent celles du registre existant.\n",
        "Même univers, mêmes labels, splits/purges, grilles, seed et frais. "
        "Les modèles indiqués sont choisis exclusivement sur S1 2025 dans chaque set. "
        "Le set complet est une nouvelle expérience sur des périodes déjà explorées.\n",
        "## Comparaison des 36 gagnants de validation\n",
        table(compared.drop(columns="model_id")),
        "## Écart au meilleur baseline Strict/Strong choisi en validation\n",
        table(
            delta[
                [
                    "target",
                    "horizon",
                    "model_all",
                    "model_baseline",
                    "feature_set_baseline",
                    "delta_roc_auc",
                    "delta_r2",
                    "delta_mean_ic",
                    "delta_return_25bp",
                    "delta_return_50bp",
                ]
            ]
        ),
        "Les écarts sont all moins baseline. Ils ne sont pas des tests de significativité. "
        "Le fichier `comparison_matched_models.parquet` compare aussi chaque type de modèle "
        "avec le même type Strict et Strong.\n",
        "## Disponibilité du registre complet\n",
        table(pd.DataFrame(profiles)),
        "Une colonne entièrement absente de train reste dans les IDs. "
        "L'imputer conserve cette colonne avec une valeur constante (0, comportement "
        "explicite de keep_empty_features) ; les indicateurs d'absence sont appris à train. "
        "Les valeurs réellement observées en aval ne servent jamais à estimer une médiane train. "
        "XGBoost conserve les NaN natifs. Les constantes et redondances peuvent pénaliser "
        "l'ajout du registre complet.\n",
        "## Livrables\n",
        "[Résultats du set complet](SPEC_008_ALL_FEATURES_RESULTS.md) · "
        "[Résultats initiaux](SPEC_008_RESULTS.md) · "
        "[Contrat de l'extension](SPEC_008_ALL_FEATURES.md).\n",
    ]
    report = root / "docs/SPEC_008_ALL_FEATURES_COMPARISON.md"
    report.write_text("\n".join(body) + "\n")
    receipt = {
        "report_sha256": file_sha(report),
        "generator_sha256": file_sha(Path(__file__)),
        "inputs": {
            str(p.relative_to(root)): file_sha(p)
            for folder in paths
            for p in sorted(folder.glob("*"))
            if p.is_file() and p.suffix in {".parquet", ".json"}
        },
    }
    report.with_suffix(".sources.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(delta[["target", "horizon", "delta_mean_ic", "delta_return_25bp"]].to_string(index=False))


if __name__ == "__main__":
    main()
