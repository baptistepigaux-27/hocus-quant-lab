# SPEC-008 — simulations du top 3 %

**Development backtest — not independent confirmation.**

## Protocole

Les mêmes 56 modèles utilisant les 1 048 variables, et leurs scores test S1 2026, sont réutilisés. Aucun entraînement, nouveau choix d'hyperparamètre ou changement de target. Les 12 gagnants ci-dessous restent ceux choisis sur validation S1 2025. Seule la fraction du portefeuille passe de 10 % à 3 %.

À chaque cutoff : `max(1, ceil(0.03 × nombre de scores finis))` titres, triés par score décroissant puis ISIN croissant pour départager les ex æquo. Cela donne 5 à 5 titres par nouveau compartiment, équipondérés. Deux compartiments H5 / trois H10 ; long-only, sans levier, entrée au prochain open commun et sortie au H-ième close commun. Frais aller-retour 0/10/25/50 bp, moitié par jambe. L'univers équipondéré reste entier et inchangé.

Les IC/AUC restent ceux des scores sur l'univers complet ; ils ne sont pas recalculés sur les seuls titres sélectionnés. Le portefeuille est plus concentré ; les coûts restent proportionnels aux montants, sans modèle supplémentaire d'impact de marché ou de liquidité.

## Gagnants choisis en validation : top 3 % versus top 10 %

Rendements cumulés sur S1 2026 en fractions (0.05 = 5 %). `cumulative_return_top10` et les écarts sont à 25 bp.

| target | horizon | model | mean_ic | roc_auc | top3_return_0bp | top3_return_10bp | top3_return_25bp | top3_return_50bp | cumulative_return_top10 | delta_cumulative_return | max_drawdown_top3 | turnover_top3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | rf | 0.06254 | 0.53688 | 0.05232 | 0.04047 | 0.02296 | -0.00554 | 0.02477 | -0.00181 | -0.03112 | 22.61489 |
| direction_abs | 10 | naive | — | 0.50000 | 0.01977 | 0.01230 | 0.00120 | -0.01702 | 0.00729 | -0.00609 | -0.10729 | 14.67332 |
| direction_rel | 5 | rf | 0.01100 | 0.54949 | 0.10836 | 0.09586 | 0.07738 | 0.04729 | 0.01024 | 0.06713 | -0.03326 | 22.61933 |
| direction_rel | 10 | rf | 0.05204 | 0.55637 | 0.13785 | 0.12947 | 0.11702 | 0.09658 | 0.06022 | 0.05680 | -0.04100 | 14.71224 |
| excursion_balance | 5 | xgb | 0.02443 | — | 0.17792 | 0.16459 | 0.14489 | 0.11283 | 0.05303 | 0.09187 | -0.05648 | 22.64733 |
| excursion_balance | 10 | linear | 0.00350 | — | 0.11231 | 0.10430 | 0.09239 | 0.07284 | -0.01707 | 0.10946 | -0.06654 | 14.44197 |
| rank_pct | 5 | rf | 0.04400 | — | 0.13998 | 0.12710 | 0.10806 | 0.07708 | 0.06391 | 0.04416 | -0.05174 | 22.62240 |
| rank_pct | 10 | rf | 0.05942 | — | 0.19874 | 0.18991 | 0.17679 | 0.15526 | 0.06274 | 0.11405 | -0.04437 | 14.71311 |
| return_abs | 5 | rf | 0.02045 | — | 0.17345 | 0.16017 | 0.14055 | 0.10861 | -0.01700 | 0.15755 | -0.05482 | 22.65331 |
| return_abs | 10 | rf | 0.03862 | — | 0.16847 | 0.16000 | 0.14743 | 0.12678 | 0.05488 | 0.09255 | -0.07797 | 14.45082 |
| trend_tstat | 5 | xgb | 0.06606 | — | 0.10922 | 0.09648 | 0.07766 | 0.04704 | 0.02119 | 0.05647 | -0.03231 | 23.04430 |
| trend_tstat | 10 | xgb | 0.09148 | — | 0.01165 | 0.00425 | -0.00674 | -0.02479 | 0.01871 | -0.02545 | -0.05364 | 14.66314 |

Les scores de la baseline naïve sont constants : sa sélection par ISIN est arbitraire, sans classement prédictif. C'est notamment le gagnant direction absolue H10 ; son rendement n'est pas une preuve de discrimination.

## Limites et reproduction

Cette sensibilité de portefeuille intervient après examen de 2026 ; elle reste du développement. Prix raw/corporate actions, univers survivant et PIT reconstruit ont les mêmes limites que le benchmark initial. SPEC-007 demeure gelé.

Commande : `uv run python scripts/replay_model_lab_top3.py`. Les scores, sources et résultats top 10 % sont vérifiés par checksums et restent inchangés. La commande refuse d'écraser un replay terminé.

Livrables locaux : `data/analysis/spec008-model-lab-all-features/portfolio-top03/` (ledger, courbes, 232 backtests, audit des sélections, comparaison des 56 modèles et des 12 gagnants). Le [Model Lab](https://sandbox.hocus.works/quant-model-lab/) propose les deux tailles de portefeuille.
