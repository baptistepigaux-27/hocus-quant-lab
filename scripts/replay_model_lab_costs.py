"""Fixed top3 scores: retain 25 bp and replay the mixed 45 bp flat-cost scenario."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.report import table, validation_winners
from hocus_quant.model_lab.run import code_identity, run_backtests


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "data/analysis/spec008-model-lab-all-features"
    reference = source / "portfolio-top03"
    output = reference / "costs-25-45"
    if (output / "summary.json").exists():
        raise ValueError("Completed cost replay exists; preserve it")
    output.mkdir(exist_ok=True)
    original_summary = json.loads((source / "summary.json").read_text())
    reference_summary = json.loads((reference / "summary.json").read_text())
    inputs = {
        str(p.relative_to(root)): file_sha(p)
        for p in [
            source / "predictions.parquet",
            source / "model_registry.json",
            reference / "experiment_config.json",
            reference / "backtest_summary.parquet",
            reference / "source_market.parquet",
            reference / "source_benchmark.parquet",
        ]
    }
    assert (
        file_sha(source / "predictions.parquet")
        == original_summary["artifact_sha256"]["predictions.parquet"]
    )
    for name in ["backtest_summary.parquet", "source_market.parquet", "source_benchmark.parquet"]:
        assert file_sha(reference / name) == reference_summary["artifact_sha256"][name]
    config = json.loads((reference / "experiment_config.json").read_text())
    assert config["portfolio_top_fraction"] == 0.03
    config["costs_round_trip_bp"] = [45]
    (output / "experiment_config.json").write_text(json.dumps(config, indent=2) + "\n")
    for name in ["source_market.parquet", "source_benchmark.parquet"]:
        shutil.copyfile(reference / name, output / name)
    predictions = pd.read_parquet(source / "predictions.parquet")
    predictions = predictions[predictions.split == "test"].copy()
    predictions["cutoff"] = pd.to_datetime(predictions.cutoff).dt.date
    results = run_backtests(output, predictions, config)
    mixed = pd.read_parquet(output / "backtest_summary.parquet")
    optimistic = pd.read_parquet(reference / "backtest_summary.parquet")
    optimistic = optimistic[optimistic.cost_bp == 25]
    keys = ["model_id", "target", "horizon", "model", "feature_set"]
    comparison = mixed.merge(
        optimistic, on=keys, suffixes=("_45bp", "_25bp"), validate="one_to_one"
    )
    comparison["delta_net_return"] = (
        comparison.cumulative_return_45bp - comparison.cumulative_return_25bp
    )
    comparison.to_parquet(output / "comparison_all_models.parquet", index=False)
    winners = validation_winners(source)
    selected = winners.merge(comparison, on=keys, validate="one_to_one").sort_values(
        ["target", "horizon"]
    )
    selected.to_parquet(output / "comparison_winners.parquet", index=False)
    selected.to_csv(output / "comparison_winners.csv", index=False)
    columns = [
        "target",
        "horizon",
        "model",
        "cumulative_return_25bp",
        "cumulative_return_45bp",
        "delta_net_return",
        "max_drawdown_25bp",
        "max_drawdown_45bp",
        "fees_25bp",
        "fees_45bp",
    ]
    for h in [5, 10]:
        rank = selected[(selected.target == "rank_pct") & (selected.horizon == h)].iloc[0]
        print(
            f"RANK H{h}: {rank.cumulative_return_25bp:.8%} -> {rank.cumulative_return_45bp:.8%}",
            flush=True,
        )
    report = root / "docs/SPEC_008_COST_SCENARIOS_25_45.md"
    report.write_text(
        "# Top 3 % — scénarios de coûts 25 et 45 bp\n\n"
        "Même corpus, mêmes 1 048 variables, modèles et scores figés, test S1 2026. "
        "Gagnants choisis sur validation 2025, sans nouveau réglage.\n\n"
        "- **Optimiste : 25 bp aller-retour**, 12,5 bp à l'achat et à la vente ; "
        "résultats existants.\n"
        "- **Mixte : 45 bp aller-retour**, 22,5 bp à l'achat et à la vente ; "
        "nouveau replay du ledger.\n\n"
        "Le scénario mixte est un forfait global : il représente une hypothèse de coûts "
        "moyens comprenant potentiellement courtage, fiscalité et exécution. Il ne "
        "calcule pas une TTF de 0,4 % sur chaque titre et n'ajoute pas une taxe par-dessus "
        "les 45 bp. Les minimums par ordre ne sont pas modélisés.\n\n"
        "Les frais changent le cash, les quantités et les allocations suivantes ; "
        "le résultat à 45 bp est simulé directement, sans interpolation du rendement.\n\n"
        "## Rang du rendement — Random Forest\n\n"
        "Rendements cumulés en fractions : 0.10 = 10 %. Frais en fraction du capital initial.\n\n"
        + table(selected[selected.target == "rank_pct"][columns])
        + "\n\n## Toutes les tâches — mêmes gagnants de validation\n\n"
        + table(selected[columns])
        + "\n\n## Reproduction\n\n"
        "`uv run python scripts/replay_model_lab_costs.py`\n\n"
        "Les 56 modèles et deux références équipondérées sont rejoués à 45 bp, sans "
        "entraînement. Les ledgers et courbes sont dans "
        "`data/analysis/spec008-model-lab-all-features/portfolio-top03/costs-25-45/`. "
        "Les artefacts originaux à 25 bp restent inchangés.\n\n"
        "Résultats de développement ; mêmes limites sur prix raw, corporate actions "
        "et univers reconstruit. Le [Model Lab](https://sandbox.hocus.works/quant-model-lab/) "
        "propose 45 bp pour le registre complet en top 3 %.\n"
    )
    assert all(file_sha(root / name) == sha for name, sha in inputs.items())
    manifest = {
        "status": "development_complete",
        "development_only": True,
        "version": "SPEC-008-TOP03-COSTS-25-45/1.0.0",
        "costs_round_trip_bp": [25, 45],
        "new_replay_cost_bp": 45,
        "portfolio_top_fraction": 0.03,
        "backtest_count": len(results),
        "refits": 0,
        "input_sha256": inputs,
        "artifact_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
        **code_identity(root),
    }
    (output / "summary.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "docs/SPEC_008_COST_SCENARIOS_25_45.sources.json").write_text(
        json.dumps(
            {
                "manifest": manifest,
                "generator_sha256": file_sha(Path(__file__)),
                "report_sha256": file_sha(report),
            },
            indent=2,
        )
        + "\n"
    )
    print(selected[columns].to_string(index=False))


if __name__ == "__main__":
    main()
