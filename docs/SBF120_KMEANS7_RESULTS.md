# SBF 120 — sept régimes K-means

**6 octobre 2026 · développement rétrospectif.** [Contrat, formules et limites](SBF120_KMEANS7_CONTRACT.md).

Centres et prétraitement figés sur 256 dates de 2024, 22 variables historiques, K=7. Aucune information future dans les centres. Même modèle en S1 2025 et S1 2026. Les tables de prévision apprennent seulement les labels purgés de 2024, avec shrinkage 20 et fallback n<10.

Silhouette train : 0.2158. Elle mesure la séparation géométrique, sans preuve prédictive.

## Lecture du résultat

En 2026, AUC direction H5/H10 : 0.453 / 0.482. Les erreurs de direction et rendement ne battent pas leurs références. La volatilité H5 réduit la MSE de 28.4 % face à la volatilité historique H5, mais seulement de 4.3 % face à une moyenne 2024 constante. L'avantage H5 face à la volatilité historique a un intervalle individuel 90 % positif pour les trois tailles de blocs. Ce soutien ne concerne pas le comparateur moyenne constante. L'amélioration H10 face à la volatilité historique ne bat pas la moyenne constante.

58.4 % des jours 2025 et 27.2 % des jours 2026 dépassent le quantile 95 % des distances train. Les centres de 2024 couvrent donc imparfaitement les états ultérieurs.

## Profils des centres, en unités natives

| cluster | momentum_5 | momentum_20 | momentum_60 | volatility_20 | drawdown_60 | rsi_simple_14 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | -0.00789 | -0.00863 | 0.05096 | 0.09328 | -0.02329 | 0.39144 |
| 2 | 0.01001 | 0.02973 | 0.07215 | 0.09443 | -0.00403 | 0.68580 |
| 3 | -0.01221 | -0.00646 | -0.02358 | 0.12947 | -0.05276 | 0.45973 |
| 4 | 0.01697 | 0.01435 | -0.02899 | 0.13969 | -0.04478 | 0.68061 |
| 5 | 0.00410 | -0.00443 | -0.01734 | 0.14112 | -0.04740 | 0.47179 |
| 6 | -0.03093 | -0.05284 | -0.07509 | 0.15863 | -0.09170 | 0.31609 |
| 7 | -0.00660 | -0.04379 | -0.07042 | 0.16634 | -0.08420 | 0.37971 |

Les rendements sont des fractions ; les volatilités sont annualisées. Les numéros suivent la volatilité 20 du centre train, sans sens ordinal prédictif.

## Occupation et distance au support train

| period | cluster | dates | mean_distance | outside_train_support | share |
| --- | --- | --- | --- | --- | --- |
| test | 1 | 12 | 2.93043 | 0.08333 | 0.09600 |
| test | 2 | 36 | 2.57382 | 0.00000 | 0.28800 |
| test | 3 | 11 | 4.41757 | 0.54545 | 0.08800 |
| test | 4 | 28 | 5.16111 | 0.53571 | 0.22400 |
| test | 5 | 12 | 3.98150 | 0.16667 | 0.09600 |
| test | 6 | 10 | 4.65957 | 0.60000 | 0.08000 |
| test | 7 | 16 | 3.94905 | 0.25000 | 0.12800 |
| train | 1 | 46 | 2.50780 | 0.00000 | 0.17969 |
| train | 2 | 65 | 2.34210 | 0.04615 | 0.25391 |
| train | 3 | 39 | 2.92591 | 0.05128 | 0.15234 |
| train | 4 | 27 | 3.14923 | 0.11111 | 0.10547 |
| train | 5 | 40 | 2.79822 | 0.02500 | 0.15625 |
| train | 6 | 13 | 3.43435 | 0.15385 | 0.05078 |
| train | 7 | 26 | 3.23198 | 0.07692 | 0.10156 |
| validation | 1 | 11 | 3.76167 | 0.09091 | 0.08800 |
| validation | 2 | 35 | 3.49914 | 0.17143 | 0.28000 |
| validation | 3 | 17 | 4.43168 | 0.70588 | 0.13600 |
| validation | 4 | 28 | 5.88133 | 0.85714 | 0.22400 |
| validation | 5 | 19 | 4.56455 | 0.84211 | 0.15200 |
| validation | 6 | 6 | 11.17205 | 0.83333 | 0.04800 |
| validation | 7 | 9 | 12.10347 | 1.00000 | 0.07200 |

Support : distance au centre le plus proche supérieure au quantile 95 % des distances train. C'est un indicateur descriptif, aucune date n'est exclue.

## Prévisions par régime, validation et test

| split | target | horizon | n | roc_auc | temporal_spearman | rmse | reference_rmse | skill | train_mean_reference_rmse | skill_vs_train_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation | direction | 5 | 120 | 0.41319 | -0.15110 | — | — | -0.02634 | — | — |
| test | direction | 5 | 120 | 0.45272 | -0.08304 | — | — | -0.02382 | — | — |
| validation | return | 5 | 120 | — | -0.12029 | 0.02852 | 0.02818 | -0.02437 | 0.02820 | -0.02296 |
| test | return | 5 | 120 | — | -0.07308 | 0.02222 | 0.02171 | -0.04758 | 0.02172 | -0.04611 |
| validation | volatility | 5 | 120 | — | 0.05986 | 0.10604 | 0.11485 | 0.14743 | 0.10715 | 0.02053 |
| test | volatility | 5 | 120 | — | 0.38554 | 0.07456 | 0.08813 | 0.28417 | 0.07622 | 0.04308 |
| validation | direction | 10 | 115 | 0.54002 | 0.07079 | — | — | -0.03783 | — | — |
| test | direction | 10 | 115 | 0.48194 | -0.03179 | — | — | -0.04501 | — | — |
| validation | return | 10 | 115 | — | -0.03284 | 0.04261 | 0.04225 | -0.01715 | 0.04230 | -0.01514 |
| test | return | 10 | 115 | — | -0.15216 | 0.03194 | 0.03118 | -0.04933 | 0.03121 | -0.04739 |
| validation | volatility | 10 | 115 | — | 0.04885 | 0.10353 | 0.12994 | 0.36524 | 0.10351 | -0.00034 |
| test | volatility | 10 | 115 | — | 0.16449 | 0.06777 | 0.07254 | 0.12724 | 0.06583 | -0.05984 |

Skill direction sur log-loss ; régressions sur MSE. Références : prior 2024, rendement zéro, volatilité historique H. Le comparateur complémentaire `train_mean` mesure l'apport des régimes face à une simple moyenne 2024 pour les deux régressions. Les modèles supervisés précédents utilisent un retrain jusqu'à juin 2025 : budgets d'information différents.

## Résultats futurs par groupe en 2026

| period | cluster | target | horizon | dates | labels | outcome_mean | outcome_median |
| --- | --- | --- | --- | --- | --- | --- | --- |
| test | 1 | direction | 5 | 12 | 12 | 0.75000 | 1.00000 |
| test | 2 | direction | 5 | 36 | 32 | 0.53125 | 1.00000 |
| test | 3 | direction | 5 | 11 | 11 | 0.54545 | 1.00000 |
| test | 4 | direction | 5 | 28 | 28 | 0.53571 | 1.00000 |
| test | 5 | direction | 5 | 12 | 11 | 0.63636 | 1.00000 |
| test | 6 | direction | 5 | 10 | 10 | 0.30000 | 0.00000 |
| test | 7 | direction | 5 | 16 | 16 | 0.56250 | 1.00000 |
| test | 1 | return | 5 | 12 | 12 | 0.00366 | 0.00642 |
| test | 2 | return | 5 | 36 | 32 | -0.00498 | 0.00435 |
| test | 3 | return | 5 | 11 | 11 | 0.00238 | 0.00266 |
| test | 4 | return | 5 | 28 | 28 | 0.00106 | 0.00063 |
| test | 5 | return | 5 | 12 | 11 | 0.00872 | 0.00393 |
| test | 6 | return | 5 | 10 | 10 | -0.00681 | -0.00602 |
| test | 7 | return | 5 | 16 | 16 | 0.00942 | 0.01405 |
| test | 1 | volatility | 5 | 12 | 12 | 0.09941 | 0.07943 |
| test | 2 | volatility | 5 | 36 | 32 | 0.11567 | 0.09911 |
| test | 3 | volatility | 5 | 11 | 11 | 0.16461 | 0.16498 |
| test | 4 | volatility | 5 | 28 | 28 | 0.13968 | 0.11775 |
| test | 5 | volatility | 5 | 12 | 11 | 0.16166 | 0.13867 |
| test | 6 | volatility | 5 | 10 | 10 | 0.18345 | 0.18196 |
| test | 7 | volatility | 5 | 16 | 16 | 0.18945 | 0.17650 |
| test | 1 | direction | 10 | 12 | 11 | 0.90909 | 1.00000 |
| test | 2 | direction | 10 | 36 | 29 | 0.34483 | 0.00000 |
| test | 3 | direction | 10 | 11 | 11 | 0.63636 | 1.00000 |
| test | 4 | direction | 10 | 28 | 27 | 0.40741 | 0.00000 |
| test | 5 | direction | 10 | 12 | 11 | 0.72727 | 1.00000 |
| test | 6 | direction | 10 | 10 | 10 | 0.40000 | 0.00000 |
| test | 7 | direction | 10 | 16 | 16 | 0.68750 | 1.00000 |
| test | 1 | return | 10 | 12 | 11 | 0.01479 | 0.02235 |
| test | 2 | return | 10 | 36 | 29 | -0.01649 | -0.02025 |
| test | 3 | return | 10 | 11 | 11 | 0.00410 | 0.00557 |
| test | 4 | return | 10 | 28 | 27 | 0.00111 | -0.00357 |
| test | 5 | return | 10 | 12 | 11 | 0.01006 | 0.01419 |
| test | 6 | return | 10 | 10 | 10 | -0.00159 | -0.01990 |
| test | 7 | return | 10 | 16 | 16 | 0.02081 | 0.02327 |
| test | 1 | volatility | 10 | 12 | 11 | 0.09169 | 0.08744 |
| test | 2 | volatility | 10 | 36 | 29 | 0.14352 | 0.11983 |
| test | 3 | volatility | 10 | 11 | 11 | 0.18067 | 0.20612 |
| test | 4 | volatility | 10 | 28 | 27 | 0.13819 | 0.13297 |
| test | 5 | volatility | 10 | 12 | 11 | 0.14402 | 0.12226 |
| test | 6 | volatility | 10 | 10 | 10 | 0.18019 | 0.17260 |
| test | 7 | volatility | 10 | 16 | 16 | 0.19763 | 0.18624 |

`outcome_mean` de direction = fréquence de hausse, hors zéros. Une cellule sans label reste vide ; les n ne sont pas indépendants.

## Incertitude test, intervalles individuels 90 %

| target | horizon | block_sessions | primary_metric | primary_lo90 | primary_hi90 | loss_advantage_lo90 | loss_advantage_hi90 | bootstrap_better_than_reference_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction | 5 | 5 | roc_auc | 0.33143 | 0.57493 | -0.04224 | 0.00959 | 0.15080 |
| direction | 5 | 10 | roc_auc | 0.33043 | 0.57336 | -0.04405 | 0.01117 | 0.15940 |
| direction | 5 | 20 | roc_auc | 0.37831 | 0.53227 | -0.03494 | 0.00248 | 0.08160 |
| direction | 10 | 10 | roc_auc | 0.29933 | 0.66962 | -0.09654 | 0.02780 | 0.19600 |
| direction | 10 | 20 | roc_auc | 0.31652 | 0.67908 | -0.09309 | 0.02643 | 0.19220 |
| direction | 10 | 40 | roc_auc | 0.31035 | 0.66951 | -0.09417 | 0.01787 | 0.15460 |
| return | 5 | 5 | temporal_spearman | -0.29270 | 0.16057 | -0.00005 | 0.00000 | 0.07060 |
| return | 5 | 10 | temporal_spearman | -0.28548 | 0.17804 | -0.00005 | 0.00000 | 0.07740 |
| return | 5 | 20 | temporal_spearman | -0.24110 | 0.17704 | -0.00004 | -0.00000 | 0.03960 |
| return | 10 | 10 | temporal_spearman | -0.45473 | 0.23072 | -0.00012 | 0.00003 | 0.15020 |
| return | 10 | 20 | temporal_spearman | -0.43870 | 0.27596 | -0.00012 | 0.00002 | 0.13440 |
| return | 10 | 40 | temporal_spearman | -0.40904 | 0.22958 | -0.00011 | 0.00002 | 0.10940 |
| volatility | 5 | 5 | temporal_spearman | 0.15211 | 0.56708 | 0.00012 | 0.00441 | 0.95840 |
| volatility | 5 | 10 | temporal_spearman | 0.13058 | 0.57303 | 0.00023 | 0.00430 | 0.96560 |
| volatility | 5 | 20 | temporal_spearman | 0.14925 | 0.52488 | 0.00033 | 0.00445 | 0.97760 |
| volatility | 10 | 10 | temporal_spearman | -0.15175 | 0.45936 | -0.00113 | 0.00229 | 0.75880 |
| volatility | 10 | 20 | temporal_spearman | -0.11316 | 0.46399 | -0.00087 | 0.00199 | 0.79500 |
| volatility | 10 | 40 | temporal_spearman | -0.15852 | 0.46796 | -0.00042 | 0.00178 | 0.83580 |

5 000 tirages circulaires, blocs H/2H/4H, modèles figés. Pas de correction multiple ni d'incertitude de réapprentissage des centres.

## Artefacts et utilisation

`data/analysis/sbf120-kmeans7-v1/` : 250 dates exportées, 20 flux (7 indicatrices, 7 distances, 6 prévisions), sans résultat futur. Les assignations 2024 servent à lire le fit, pas à une évaluation hors période. Scores 2025/2026 disponibles après D, fit déclaré au 01/01/2025 UTC. Jointure SRD et confirmation indépendante restent à faire.

Reproduction : `uv run python scripts/sbf120_kmeans.py`. Onglet **SBF 120 · régimes** du [Model Lab](https://sandbox.hocus.works/quant-model-lab/).
