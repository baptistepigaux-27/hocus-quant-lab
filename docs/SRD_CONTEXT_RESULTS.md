# SRD — modèles enrichis par les contextes de marché

**6 octobre 2026 · développement rétrospectif, sans confirmation indépendante.** [Contrat, folds et jointure](SRD_CONTEXT_INTEGRATION_CONTRACT.md).

1 048 features d'action + **356 contextes = 1 404 variables**. K-means SBF120 à sept centres 2023, tables par régime ; prévisions des 27 secteurs et CAC40/SBF120. Les producteurs sont ajustés avant chaque trimestre, seulement avec labels alors matures. La borne du contexte test 2026 reste juillet 2025. Les anciens exports 2026 ne remplissent pas le train.

## Lecture des résultats

**56 modèles SRD, 12 tâches, 116 simulations de portefeuille.** À 25 bp, le gagnant enrichi améliore le rendement net dans **5/12 tâches**. L'écart d'IC apparié a trois intervalles 90 % entièrement positifs dans **0 tâches**. Le gain n'est donc pas automatique et les critères prédictifs et de portefeuille peuvent diverger.

| target | horizon | model_baseline | model_context | IC référence → contexte | Net 25 bp référence → contexte | Net 45 bp référence → contexte |
| --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | rf | xgb | 0.0625 → 0.0404 | +2.30 % → +4.94 % | +0.01 % → +2.55 % |
| direction_abs | 10 | naive | rf | indéfini → 0.0451 | +0.12 % → -0.83 % | -1.34 % → -2.27 % |
| return_abs | 5 | rf | rf | 0.0205 → 0.0281 | +14.05 % → +2.69 % | +11.49 % → +0.39 % |
| return_abs | 10 | rf | xgb | 0.0386 → 0.0454 | +14.74 % → +11.85 % | +13.09 % → +10.24 % |
| direction_rel | 5 | rf | xgb | 0.0110 → 0.0462 | +7.74 % → +3.77 % | +5.32 % → +1.41 % |
| direction_rel | 10 | rf | rf | 0.0520 → 0.0668 | +11.70 % → -0.84 % | +10.06 % → -2.28 % |
| rank_pct | 5 | rf | rf | 0.0440 → 0.0675 | +10.81 % → +16.99 % | +8.32 % → +14.35 % |
| rank_pct | 10 | rf | rf | 0.0594 → 0.0764 | +17.68 % → +25.49 % | +15.95 % → +23.64 % |
| excursion_balance | 5 | xgb | rf | 0.0244 → 0.0771 | +14.49 % → +14.69 % | +11.92 % → +12.11 % |
| excursion_balance | 10 | linear | linear | 0.0035 → 0.0099 | +9.24 % → +7.41 % | +7.67 % → +5.87 % |
| trend_tstat | 5 | xgb | xgb | 0.0661 → 0.0449 | +7.77 % → +1.57 % | +5.31 % → -0.74 % |
| trend_tstat | 10 | xgb | xgb | 0.0915 → 0.0673 | -0.67 % → -0.04 % | -2.12 % → -1.49 % |

Rendements cumulés du portefeuille sur le test S1 2026, non annualisés. Les flèches lisent référence sans contexte → modèle enrichi. Types de modèles choisis sur validation, avant la lecture de ce test.

## Couverture des contextes historiques

| year | dates | streams | missing |
| --- | --- | --- | --- |
| 2024 | 51 | 356 | 0.05023 |
| 2025 | 25 | 356 | 0.03371 |
| 2026 | 24 | 356 | 0.07303 |

Aucune action ni target SRD retirée. Scores disponibles à minuit UTC D+1, jointure as-of avant l'open suivant. Manquants explicites. Les vecteurs sectoriels sont globaux, sans affectation sectorielle des actions.

## Gagnants de validation, avec et sans contexte, mêmes observations test

| target | horizon | feature_set | model | validation_metric | mean_ic | roc_auc | r2 | n | cumulative_return_25bp | cumulative_return_45bp | max_drawdown_45bp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | all | rf | 0.50360 | 0.06254 | 0.53688 | — | 3732 | 0.02296 | 0.00009 | -0.03514 |
| direction_abs | 5 | context | xgb | 0.57215 | 0.04039 | 0.53393 | — | 3732 | 0.04937 | 0.02547 | -0.04500 |
| direction_abs | 10 | all | naive | 0.50000 | — | 0.50000 | — | 3573 | 0.00120 | -0.01340 | -0.11139 |
| direction_abs | 10 | context | rf | 0.58184 | 0.04510 | 0.53103 | — | 3573 | -0.00829 | -0.02273 | -0.05881 |
| direction_rel | 5 | all | rf | 0.55713 | 0.01100 | 0.54949 | — | 3732 | 0.07738 | 0.05324 | -0.03738 |
| direction_rel | 5 | context | xgb | 0.57444 | 0.04620 | 0.57138 | — | 3732 | 0.03767 | 0.01405 | -0.02660 |
| direction_rel | 10 | all | rf | 0.53690 | 0.05204 | 0.55637 | — | 3573 | 0.11702 | 0.10064 | -0.04258 |
| direction_rel | 10 | context | rf | 0.59023 | 0.06678 | 0.58543 | — | 3573 | -0.00838 | -0.02280 | -0.07455 |
| excursion_balance | 5 | all | xgb | 0.03336 | 0.02443 | — | -0.04953 | 3732 | 0.14489 | 0.11917 | -0.05879 |
| excursion_balance | 5 | context | rf | 0.05660 | 0.07713 | — | 0.00127 | 3732 | 0.14688 | 0.12111 | -0.06748 |
| excursion_balance | 10 | all | linear | 0.02615 | 0.00350 | — | -0.26115 | 3573 | 0.09239 | 0.07672 | -0.06931 |
| excursion_balance | 10 | context | linear | 0.03499 | 0.00988 | — | -0.26792 | 3573 | 0.07409 | 0.05869 | -0.08738 |
| rank_pct | 5 | all | rf | 0.07111 | 0.04400 | — | 0.00138 | 3732 | 0.10806 | 0.08320 | -0.05413 |
| rank_pct | 5 | context | rf | 0.07492 | 0.06746 | — | 0.00459 | 3732 | 0.16985 | 0.14354 | -0.06478 |
| rank_pct | 10 | all | rf | 0.06287 | 0.05942 | — | 0.00397 | 3573 | 0.17679 | 0.15954 | -0.04498 |
| rank_pct | 10 | context | rf | 0.06639 | 0.07638 | — | 0.00524 | 3573 | 0.25488 | 0.23642 | -0.06759 |
| return_abs | 5 | all | rf | 0.05388 | 0.02045 | — | -0.02416 | 3732 | 0.14055 | 0.11492 | -0.05574 |
| return_abs | 5 | context | rf | 0.06482 | 0.02809 | — | -0.02540 | 3732 | 0.02687 | 0.00390 | -0.05602 |
| return_abs | 10 | all | rf | 0.03137 | 0.03862 | — | -0.01920 | 3573 | 0.14743 | 0.13088 | -0.08101 |
| return_abs | 10 | context | xgb | 0.04889 | 0.04542 | — | -0.04572 | 3573 | 0.11855 | 0.10245 | -0.06588 |
| trend_tstat | 5 | all | xgb | 0.08187 | 0.06606 | — | 0.00044 | 3732 | 0.07766 | 0.05309 | -0.03398 |
| trend_tstat | 5 | context | xgb | 0.10104 | 0.04492 | — | 0.00980 | 3732 | 0.01570 | -0.00740 | -0.05691 |
| trend_tstat | 10 | all | xgb | 0.03054 | 0.09148 | — | 0.00918 | 3573 | -0.00674 | -0.02121 | -0.05550 |
| trend_tstat | 10 | context | xgb | 0.10687 | 0.06726 | — | -0.01941 | 3573 | -0.00035 | -0.01491 | -0.08959 |

Gagnants fixés séparément sur S1 2025. AUC pour directions, IC moyen pour régressions. Référence = registre complet, top3, modèles et scores précédemment sauvegardés. Les contextes du train sont hors apprentissage de leurs producteurs. Le SRD sélectionne ses paramètres sur validation.

## Écarts contexte moins référence

| target | horizon | model_context | model_baseline | delta_mean_ic | paired_ic_cutoffs | paired_delta_ic | delta_roc_auc | delta_r2 | delta_cumulative_return_25bp | delta_cumulative_return_45bp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | xgb | rf | -0.02215 | 23.00000 | -0.02215 | -0.00295 | — | 0.02641 | 0.02538 |
| direction_abs | 10 | rf | naive | — | 0.00000 | — | 0.03103 | — | -0.00949 | -0.00933 |
| return_abs | 5 | rf | rf | 0.00764 | 23.00000 | 0.00764 | — | -0.00123 | -0.11368 | -0.11102 |
| return_abs | 10 | xgb | rf | 0.00680 | 22.00000 | 0.00680 | — | -0.02652 | -0.02888 | -0.02843 |
| direction_rel | 5 | xgb | rf | 0.03521 | 23.00000 | 0.03521 | 0.02188 | — | -0.03970 | -0.03918 |
| direction_rel | 10 | rf | rf | 0.01474 | 22.00000 | 0.01474 | 0.02906 | — | -0.12540 | -0.12344 |
| rank_pct | 5 | rf | rf | 0.02346 | 23.00000 | 0.02346 | — | 0.00321 | 0.06179 | 0.06034 |
| rank_pct | 10 | rf | rf | 0.01696 | 22.00000 | 0.01696 | — | 0.00126 | 0.07809 | 0.07689 |
| excursion_balance | 5 | rf | xgb | 0.05270 | 23.00000 | 0.05270 | — | 0.05080 | 0.00199 | 0.00194 |
| excursion_balance | 10 | linear | linear | 0.00638 | 22.00000 | 0.00638 | — | -0.00677 | -0.01830 | -0.01803 |
| trend_tstat | 5 | xgb | xgb | -0.02114 | 23.00000 | -0.02114 | — | 0.00936 | -0.06197 | -0.06049 |
| trend_tstat | 10 | xgb | xgb | -0.02422 | 22.00000 | -0.02422 | — | -0.02859 | 0.00639 | 0.00630 |

Les deux sélections peuvent choisir des types ou hyperparamètres différents. L'écart des IC moyens utilise les cutoffs définis de chaque modèle ; `paired_delta_ic` et ses intervalles utilisent seulement les cutoffs où les deux IC sont définis, comptés par `paired_ic_cutoffs`. Le CSV `comparison_matched_models.csv` compare également chaque type de modèle au même type de référence. Aucun choix sur les performances test.

## Incertitude de l'écart d'IC

| target | horizon | block_cutoffs | paired_cutoffs | usable_bootstrap_replicates | delta_ic | delta_ic_lo90 | delta_ic_hi90 | bootstrap_positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | 2 | 23 | 5000 | -0.02215 | -0.05630 | 0.00867 | 0.12340 |
| direction_abs | 5 | 4 | 23 | 5000 | -0.02215 | -0.05142 | 0.00528 | 0.09120 |
| direction_abs | 5 | 6 | 23 | 5000 | -0.02215 | -0.04601 | 0.00205 | 0.06560 |
| return_abs | 5 | 2 | 23 | 5000 | 0.00764 | -0.04084 | 0.05282 | 0.60260 |
| return_abs | 5 | 4 | 23 | 5000 | 0.00764 | -0.03058 | 0.04907 | 0.60620 |
| return_abs | 5 | 6 | 23 | 5000 | 0.00764 | -0.02073 | 0.03710 | 0.66000 |
| return_abs | 10 | 2 | 22 | 5000 | 0.00680 | -0.02647 | 0.03895 | 0.63060 |
| return_abs | 10 | 4 | 22 | 5000 | 0.00680 | -0.02262 | 0.03879 | 0.61820 |
| return_abs | 10 | 6 | 22 | 5000 | 0.00680 | -0.02155 | 0.03627 | 0.63780 |
| direction_rel | 5 | 2 | 23 | 5000 | 0.03521 | -0.00264 | 0.07300 | 0.93780 |
| direction_rel | 5 | 4 | 23 | 5000 | 0.03521 | 0.00274 | 0.06492 | 0.96060 |
| direction_rel | 5 | 6 | 23 | 5000 | 0.03521 | 0.00821 | 0.06027 | 0.98180 |
| direction_rel | 10 | 2 | 22 | 5000 | 0.01474 | -0.02770 | 0.05819 | 0.70140 |
| direction_rel | 10 | 4 | 22 | 5000 | 0.01474 | -0.03223 | 0.05892 | 0.69140 |
| direction_rel | 10 | 6 | 22 | 5000 | 0.01474 | -0.03618 | 0.06329 | 0.68140 |
| rank_pct | 5 | 2 | 23 | 5000 | 0.02346 | -0.01258 | 0.06704 | 0.82580 |
| rank_pct | 5 | 4 | 23 | 5000 | 0.02346 | -0.01703 | 0.07341 | 0.80400 |
| rank_pct | 5 | 6 | 23 | 5000 | 0.02346 | -0.01624 | 0.07085 | 0.79700 |
| rank_pct | 10 | 2 | 22 | 5000 | 0.01696 | -0.01032 | 0.04912 | 0.81900 |
| rank_pct | 10 | 4 | 22 | 5000 | 0.01696 | -0.01264 | 0.05058 | 0.81240 |
| rank_pct | 10 | 6 | 22 | 5000 | 0.01696 | -0.01680 | 0.05036 | 0.78740 |
| excursion_balance | 5 | 2 | 23 | 5000 | 0.05270 | -0.00822 | 0.11756 | 0.92460 |
| excursion_balance | 5 | 4 | 23 | 5000 | 0.05270 | -0.01993 | 0.12841 | 0.87660 |
| excursion_balance | 5 | 6 | 23 | 5000 | 0.05270 | -0.02757 | 0.13984 | 0.83620 |
| excursion_balance | 10 | 2 | 22 | 5000 | 0.00638 | -0.00932 | 0.02260 | 0.73280 |
| excursion_balance | 10 | 4 | 22 | 5000 | 0.00638 | -0.01033 | 0.02233 | 0.73660 |
| excursion_balance | 10 | 6 | 22 | 5000 | 0.00638 | -0.00895 | 0.02140 | 0.73800 |
| trend_tstat | 5 | 2 | 23 | 5000 | -0.02114 | -0.04685 | 0.00567 | 0.09540 |
| trend_tstat | 5 | 4 | 23 | 5000 | -0.02114 | -0.04706 | 0.00392 | 0.08520 |
| trend_tstat | 5 | 6 | 23 | 5000 | -0.02114 | -0.04521 | 0.00126 | 0.06280 |
| trend_tstat | 10 | 2 | 22 | 5000 | -0.02422 | -0.06689 | 0.01272 | 0.15960 |
| trend_tstat | 10 | 4 | 22 | 5000 | -0.02422 | -0.06890 | 0.01375 | 0.16560 |
| trend_tstat | 10 | 6 | 22 | 5000 | -0.02422 | -0.06464 | 0.01255 | 0.16060 |

Bootstrap apparié de cutoffs, 5 000 tirages, blocs 2/4/6. Intervalles individuels 90 %, conditionnels aux modèles choisis, sans correction multiple. Un naïf constant n'a pas d'IC défini. Les rendements de portefeuille n'ont pas d'intervalle dans cette publication.

## Parts d'importance des blocs pour les gagnants RF/XGB

| target | horizon | model | block | gain_or_impurity | importance_share |
| --- | --- | --- | --- | --- | --- |
| direction_abs | 10 | rf | major_predictions | 0.05624 | 0.05624 |
| direction_abs | 10 | rf | sbf120_regimes | 0.00349 | 0.00349 |
| direction_abs | 10 | rf | sector_predictions | 0.80074 | 0.80074 |
| direction_abs | 10 | rf | stock_features | 0.13954 | 0.13954 |
| direction_abs | 5 | xgb | major_predictions | 0.02720 | 0.02720 |
| direction_abs | 5 | xgb | sbf120_regimes | 0.01871 | 0.01871 |
| direction_abs | 5 | xgb | sector_predictions | 0.80104 | 0.80104 |
| direction_abs | 5 | xgb | stock_features | 0.15305 | 0.15305 |
| direction_rel | 10 | rf | major_predictions | 0.00959 | 0.00959 |
| direction_rel | 10 | rf | sbf120_regimes | 0.01228 | 0.01228 |
| direction_rel | 10 | rf | sector_predictions | 0.66841 | 0.66841 |
| direction_rel | 10 | rf | stock_features | 0.30971 | 0.30971 |
| direction_rel | 5 | xgb | major_predictions | 0.00280 | 0.00280 |
| direction_rel | 5 | xgb | sbf120_regimes | 0.03743 | 0.03743 |
| direction_rel | 5 | xgb | sector_predictions | 0.64506 | 0.64506 |
| direction_rel | 5 | xgb | stock_features | 0.31471 | 0.31471 |
| excursion_balance | 5 | rf | major_predictions | 0.05354 | 0.05354 |
| excursion_balance | 5 | rf | sbf120_regimes | 0.00159 | 0.00159 |
| excursion_balance | 5 | rf | sector_predictions | 0.59548 | 0.59548 |
| excursion_balance | 5 | rf | stock_features | 0.34939 | 0.34939 |
| rank_pct | 10 | rf | major_predictions | 0.00511 | 0.00511 |
| rank_pct | 10 | rf | sbf120_regimes | 0.00210 | 0.00210 |
| rank_pct | 10 | rf | sector_predictions | 0.19554 | 0.19554 |
| rank_pct | 10 | rf | stock_features | 0.79724 | 0.79724 |
| rank_pct | 5 | rf | major_predictions | 0.00332 | 0.00332 |
| rank_pct | 5 | rf | sbf120_regimes | 0.00390 | 0.00390 |
| rank_pct | 5 | rf | sector_predictions | 0.18816 | 0.18816 |
| rank_pct | 5 | rf | stock_features | 0.80461 | 0.80461 |
| return_abs | 10 | xgb | major_predictions | 0.02793 | 0.02793 |
| return_abs | 10 | xgb | sbf120_regimes | 0.00883 | 0.00883 |
| return_abs | 10 | xgb | sector_predictions | 0.40778 | 0.40778 |
| return_abs | 10 | xgb | stock_features | 0.55546 | 0.55546 |
| return_abs | 5 | rf | major_predictions | 0.06904 | 0.06904 |
| return_abs | 5 | rf | sbf120_regimes | 0.00294 | 0.00294 |
| return_abs | 5 | rf | sector_predictions | 0.59456 | 0.59456 |
| return_abs | 5 | rf | stock_features | 0.33346 | 0.33346 |
| trend_tstat | 10 | xgb | major_predictions | 0.04409 | 0.04409 |
| trend_tstat | 10 | xgb | sbf120_regimes | 0.01537 | 0.01537 |
| trend_tstat | 10 | xgb | sector_predictions | 0.76420 | 0.76420 |
| trend_tstat | 10 | xgb | stock_features | 0.17633 | 0.17633 |
| trend_tstat | 5 | xgb | major_predictions | 0.06139 | 0.06139 |
| trend_tstat | 5 | xgb | sbf120_regimes | 0.07687 | 0.07687 |
| trend_tstat | 5 | xgb | sector_predictions | 0.69282 | 0.69282 |
| trend_tstat | 5 | xgb | stock_features | 0.16893 | 0.16893 |

Impurity/gain du fit train 2024 seulement ; descriptif, sensible aux corrélations, sans interprétation causale. Aucune permutation marginale de milliers de colonnes ni nouvelle sélection au test.

## Replays et artefacts

168 modèles de contexte et 56 modèles SRD sauvegardés reproduisent les scores à la précision numérique. L'ancrage K-means et 42 tables par régime sont également rejoués. Cohorte, labels et 1 048 valeurs d'action identiques à la référence. Portefeuilles top3, 25/45 bp forfaitaires, ledgers complets. Pas de fiscalité titre par titre, minimum par ordre ou certification de corporate actions.

Dossier : `data/analysis/srd-context-v1/`. Config contextuelle et `srd_benchmark.toml` effectif figés. Contextes, disponibilité, folds, modèles, métriques, paniers et courbes sont conservés. Sources locales ignorées par Git.

Reproduction : `uv run python scripts/srd_context.py inputs`, puis `context`, `data`, `run`, `publish`. Les périodes ont déjà été lues ; l'expérience n'apporte pas de confirmation indépendante.
