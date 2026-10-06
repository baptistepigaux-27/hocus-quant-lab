# Top 3 % — scénarios de coûts 25 et 45 bp

Même corpus, mêmes 1 048 variables, modèles et scores figés, test S1 2026. Gagnants choisis sur validation 2025, sans nouveau réglage.

- **Optimiste : 25 bp aller-retour**, 12,5 bp à l'achat et à la vente ; résultats existants.
- **Mixte : 45 bp aller-retour**, 22,5 bp à l'achat et à la vente ; nouveau replay du ledger.

Le scénario mixte est un forfait global : il représente une hypothèse de coûts moyens comprenant potentiellement courtage, fiscalité et exécution. Il ne calcule pas une TTF de 0,4 % sur chaque titre et n'ajoute pas une taxe par-dessus les 45 bp. Les minimums par ordre ne sont pas modélisés.

Les frais changent le cash, les quantités et les allocations suivantes ; le résultat à 45 bp est simulé directement, sans interpolation du rendement.

## Rang du rendement — Random Forest

Rendements cumulés en fractions : 0.10 = 10 %. Frais en fraction du capital initial.

| target | horizon | model | cumulative_return_25bp | cumulative_return_45bp | delta_net_return | max_drawdown_25bp | max_drawdown_45bp | fees_25bp | fees_45bp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 5 | rf | 0.10806 | 0.08320 | -0.02486 | -0.05174 | -0.05413 | 0.02986 | 0.05310 |
| rank_pct | 10 | rf | 0.17679 | 0.15954 | -0.01726 | -0.04437 | -0.04498 | 0.01975 | 0.03527 |

## Toutes les tâches — mêmes gagnants de validation

| target | horizon | model | cumulative_return_25bp | cumulative_return_45bp | delta_net_return | max_drawdown_25bp | max_drawdown_45bp | fees_25bp | fees_45bp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | rf | 0.02296 | 0.00009 | -0.02287 | -0.03112 | -0.03514 | 0.02848 | 0.05066 |
| direction_abs | 10 | naive | 0.00120 | -0.01340 | -0.01460 | -0.10729 | -0.11139 | 0.01809 | 0.03232 |
| direction_rel | 5 | rf | 0.07738 | 0.05324 | -0.02414 | -0.03326 | -0.03738 | 0.02992 | 0.05321 |
| direction_rel | 10 | rf | 0.11702 | 0.10064 | -0.01638 | -0.04100 | -0.04258 | 0.01928 | 0.03443 |
| excursion_balance | 5 | xgb | 0.14489 | 0.11917 | -0.02573 | -0.05648 | -0.05879 | 0.03108 | 0.05528 |
| excursion_balance | 10 | linear | 0.09239 | 0.07672 | -0.01567 | -0.06654 | -0.06931 | 0.01819 | 0.03250 |
| rank_pct | 5 | rf | 0.10806 | 0.08320 | -0.02486 | -0.05174 | -0.05413 | 0.02986 | 0.05310 |
| rank_pct | 10 | rf | 0.17679 | 0.15954 | -0.01726 | -0.04437 | -0.04498 | 0.01975 | 0.03527 |
| return_abs | 5 | rf | 0.14055 | 0.11492 | -0.02563 | -0.05482 | -0.05574 | 0.03034 | 0.05395 |
| return_abs | 10 | rf | 0.14743 | 0.13088 | -0.01655 | -0.07797 | -0.08101 | 0.01876 | 0.03351 |
| trend_tstat | 5 | xgb | 0.07766 | 0.05309 | -0.02457 | -0.03231 | -0.03398 | 0.02942 | 0.05233 |
| trend_tstat | 10 | xgb | -0.00674 | -0.02121 | -0.01447 | -0.05364 | -0.05550 | 0.01830 | 0.03270 |

## Reproduction

`uv run python scripts/replay_model_lab_costs.py`

Les 56 modèles et deux références équipondérées sont rejoués à 45 bp, sans entraînement. Les ledgers et courbes sont dans `data/analysis/spec008-model-lab-all-features/portfolio-top03/costs-25-45/`. Les artefacts originaux à 25 bp restent inchangés.

Résultats de développement ; mêmes limites sur prix raw, corporate actions et univers reconstruit. Le [Model Lab](https://sandbox.hocus.works/quant-model-lab/) propose 45 bp pour le registre complet en top 3 %.
