"""Replay fixed all-feature test scores with a top 3% portfolio; never fit a model."""

from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.report import table, validation_winners
from hocus_quant.model_lab.run import code_identity, run_backtests


def main() -> None:
    started = time.monotonic()
    root = Path(__file__).resolve().parents[1]
    source = root / "data/analysis/spec008-model-lab-all-features"
    output = source / "portfolio-top03"
    source_summary = json.loads((source / "summary.json").read_text())
    dataset = json.loads((source / "dataset_manifest.json").read_text())
    names = [
        "predictions.parquet",
        "model_registry.json",
        "experiment_config.json",
        "summary.json",
        "backtest_summary.parquet",
        "source_market.parquet",
        "source_benchmark.parquet",
    ]
    inputs = {name: file_sha(source / name) for name in names}
    for name in ["predictions.parquet", "backtest_summary.parquet"]:
        if inputs[name] != source_summary["artifact_sha256"][name]:
            raise ValueError(f"Source artifact changed: {name}")
    for name in ["source_market.parquet", "source_benchmark.parquet"]:
        if inputs[name] != dataset["source_sha256"][name]:
            raise ValueError(f"Source market changed: {name}")
    config = json.loads((source / "experiment_config.json").read_text())
    if config["portfolio_top_fraction"] != 0.1:
        raise ValueError("Expected top 10% reference")
    config["portfolio_top_fraction"] = 0.03
    output.mkdir(exist_ok=True)
    manifest_path = output / "summary.json"
    if manifest_path.exists():
        raise ValueError("Completed replay already exists; preserve the recorded experiment")
    for name in ["source_market.parquet", "source_benchmark.parquet"]:
        shutil.copyfile(source / name, output / name)
    (output / "experiment_config.json").write_text(json.dumps(config, indent=2) + "\n")
    predictions = pd.read_parquet(source / "predictions.parquet")
    predictions = predictions[predictions.split == "test"].copy()
    predictions["cutoff"] = pd.to_datetime(predictions.cutoff).dt.date
    selection = []
    for (mid, cutoff), part in predictions.groupby(["model_id", "cutoff"], sort=True):
        finite = part[np.isfinite(part.score)].sort_values(
            ["score", "entity_id"], ascending=[False, True], kind="stable"
        )
        n = max(1, math.ceil(len(finite) * 0.03))
        selected = finite.head(n)
        selection.append(
            {
                "model_id": mid,
                "cutoff": cutoff,
                "eligible_n": len(finite),
                "selected_n": len(selected),
                "selected_ids": selected.entity_id.tolist(),
                "constant_scores": finite.score.nunique() <= 1,
                "boundary_tie_n": int((finite.score == selected.score.iloc[-1]).sum())
                if len(selected)
                else 0,
            }
        )
    selection_frame = pd.DataFrame(selection)
    selection_frame.to_parquet(output / "selection_audit.parquet", index=False)
    print(f"REPLAY {predictions.model_id.nunique()} fixed models; top 3%; no fits", flush=True)
    results = run_backtests(output, predictions, config)
    replay = pd.read_parquet(output / "backtest_summary.parquet")
    original = pd.read_parquet(source / "backtest_summary.parquet")
    keys = ["model_id", "cost_bp", "target", "model", "feature_set", "horizon"]
    compared = replay.merge(original, on=keys, suffixes=("_top3", "_top10"), validate="one_to_one")
    for metric in ["cumulative_return", "max_drawdown", "turnover", "hit_rate"]:
        compared[f"delta_{metric}"] = compared[f"{metric}_top3"] - compared[f"{metric}_top10"]
    compared.to_parquet(output / "comparison_all_models.parquet", index=False)
    winners = validation_winners(source)
    selected_comparison = winners.merge(
        compared, on=[k for k in keys if k != "cost_bp"], validate="one_to_many"
    )
    selected_comparison.to_parquet(output / "comparison_winners.parquet", index=False)
    selected_comparison.to_csv(output / "comparison_winners.csv", index=False)
    metrics = pd.read_parquet(source / "metrics.parquet")
    presentation = winners.merge(
        metrics[metrics.split == "test"][["model_id", "mean_ic", "roc_auc"]],
        on="model_id",
        validate="one_to_one",
    )
    for cost in [0, 10, 25, 50]:
        part = selected_comparison[selected_comparison.cost_bp == cost]
        presentation = presentation.merge(
            part[["model_id", "cumulative_return_top3"]].rename(
                columns={"cumulative_return_top3": f"top3_return_{cost}bp"}
            ),
            on="model_id",
            validate="one_to_one",
        )
    part = selected_comparison[selected_comparison.cost_bp == 25]
    presentation = presentation.merge(
        part[
            [
                "model_id",
                "cumulative_return_top10",
                "delta_cumulative_return",
                "max_drawdown_top3",
                "turnover_top3",
            ]
        ],
        on="model_id",
        validate="one_to_one",
    ).sort_values(["target", "horizon"])
    report = root / "docs/SPEC_008_TOP3_RESULTS.md"
    columns = [
        "target",
        "horizon",
        "model",
        "mean_ic",
        "roc_auc",
        "top3_return_0bp",
        "top3_return_10bp",
        "top3_return_25bp",
        "top3_return_50bp",
        "cumulative_return_top10",
        "delta_cumulative_return",
        "max_drawdown_top3",
        "turnover_top3",
    ]
    report.write_text(
        "# SPEC-008 — simulations du top 3 %\n\n"
        "**Development backtest — not independent confirmation.**\n\n"
        "## Protocole\n\n"
        "Les mêmes 56 modèles utilisant les 1 048 variables, et leurs scores test S1 2026, "
        "sont réutilisés. Aucun entraînement, nouveau choix d'hyperparamètre ou changement "
        "de target. Les 12 gagnants ci-dessous restent ceux choisis sur validation S1 2025. "
        "Seule la fraction du portefeuille passe de 10 % à 3 %.\n\n"
        "À chaque cutoff : `max(1, ceil(0.03 × nombre de scores finis))` titres, triés "
        "par score décroissant puis ISIN croissant pour départager les ex æquo. Cela "
        f"donne {selection_frame.selected_n.min()} à {selection_frame.selected_n.max()} titres "
        "par nouveau compartiment, équipondérés. Deux compartiments H5 / trois H10 ; "
        "long-only, sans levier, entrée au prochain open commun et sortie au H-ième close "
        "commun. Frais aller-retour 0/10/25/50 bp, moitié par jambe. L'univers "
        "équipondéré reste entier et inchangé.\n\n"
        "Les IC/AUC restent ceux des scores sur l'univers complet ; ils ne sont pas "
        "recalculés sur les seuls titres sélectionnés. Le portefeuille est plus concentré ; "
        "les coûts restent proportionnels aux montants, sans modèle supplémentaire "
        "d'impact de marché ou de liquidité.\n\n"
        "## Gagnants choisis en validation : top 3 % versus top 10 %\n\n"
        "Rendements cumulés sur S1 2026 en fractions (0.05 = 5 %). "
        "`cumulative_return_top10` et les écarts sont à 25 bp.\n\n"
        + table(presentation[columns])
        + "\n\nLes scores de la baseline naïve sont constants : sa sélection par ISIN "
        "est arbitraire, sans classement prédictif. C'est notamment le gagnant "
        "direction absolue H10 ; son rendement n'est pas une preuve de discrimination.\n\n"
        "## Limites et reproduction\n\n"
        "Cette sensibilité de portefeuille intervient après examen de 2026 ; elle reste "
        "du développement. Prix raw/corporate actions, univers survivant et PIT reconstruit "
        "ont les mêmes limites que le benchmark initial. SPEC-007 demeure gelé.\n\n"
        "Commande : `uv run python scripts/replay_model_lab_top3.py`. Les scores, "
        "sources et résultats top 10 % sont vérifiés par checksums et restent inchangés. "
        "La commande refuse d'écraser un replay terminé.\n\n"
        "Livrables locaux : `data/analysis/spec008-model-lab-all-features/portfolio-top03/` "
        "(ledger, courbes, 232 backtests, audit des sélections, comparaison des 56 modèles "
        "et des 12 gagnants). Le [Model Lab](https://sandbox.hocus.works/quant-model-lab/) "
        "propose les deux tailles de portefeuille.\n"
    )
    if any(file_sha(source / name) != sha for name, sha in inputs.items()):
        raise ValueError("Source experiment mutated during replay")
    manifest = {
        "version": "SPEC-008-ALL-TOP03/1.0.0",
        "status": "development_complete",
        "development_only": True,
        "source": str(source.relative_to(root)),
        "portfolio_top_fraction": 0.03,
        "reference_top_fraction": 0.1,
        "model_count": predictions.model_id.nunique(),
        "backtest_count": len(results),
        "training_fits": 0,
        "scores_unchanged": True,
        "winners_unchanged": True,
        "input_sha256": inputs,
        "elapsed_seconds": time.monotonic() - started,
        "artifact_sha256": {p.name: file_sha(p) for p in sorted(output.glob("*.parquet"))},
        **code_identity(root),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "docs/SPEC_008_TOP3_RESULTS.sources.json").write_text(
        json.dumps(
            {
                "report_sha256": file_sha(report),
                "manifest": manifest,
                "generator_sha256": file_sha(Path(__file__)),
            },
            indent=2,
        )
        + "\n"
    )
    print(presentation[columns].to_string(index=False), flush=True)
    print(json.dumps({"backtests": len(results), "elapsed_seconds": manifest["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
