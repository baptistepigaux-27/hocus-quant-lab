# SPEC-008 — résultats reproductibles

**Development backtest — not independent confirmation.**

Calculs : 56 modèles finaux, 80 fits de découverte/validation, 56 retrains. XGBoost CPU est la référence principale.

Lock `7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f` ; registry additif `906d8281f40614e2c91d069866018894a215e0ac52de50e0358ab427b8a91044`.

Feature sets : `{'all': 1048}`. Le set `all`, lorsqu'il est présent, conserve toutes les entrées du registre, sans sélection fondée sur leurs outcomes. L'univers et les labels sont identiques au benchmark initial.

**Contamination de sélection :** strict/strong ont été choisis avec des outcomes de 2025 **et 2026**. L'absence de tuning sur 2026 dans ce code ne supprime pas cette connaissance préalable. Aucun chiffre ci-dessous n'est une confirmation indépendante.

## 1. Splits exacts et effectifs

| horizon | split | first_cutoff | last_cutoff | last_usable_label_end | cutoff_n | eligible_rows | usable_labels | feature_missing_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | train | 2024-01-05 | 2024-12-20 | 2024-12-31 | 50 | 9068 | 9067 | 0.08952 |
| 5 | validation | 2025-01-03 | 2025-06-20 | 2025-06-27 | 24 | 4187 | 4185 | 0.00974 |
| 5 | test | 2026-01-02 | 2026-06-19 | 2026-06-26 | 23 | 3732 | 3732 | 0.00723 |
| 10 | train | 2024-01-05 | 2024-12-13 | 2024-12-31 | 49 | 8890 | 8889 | 0.09110 |
| 10 | validation | 2025-01-03 | 2025-06-13 | 2025-06-27 | 23 | 4017 | 4013 | 0.00981 |
| 10 | test | 2026-01-02 | 2026-06-12 | 2026-06-26 | 22 | 3573 | 3573 | 0.00727 |

Les effectifs sont des couples entité/cutoff répétés, pas des observations indépendantes. Les lignes dont la target traverse une frontière restent dans la matrice/prédictions ; leur label est nul. Le purge/embargo calendaire est appliqué à toutes les entités d'un cutoff.

## 2. Modèle retenu exclusivement sur validation, puis lu en S1 2026

| target | horizon | model | feature_set | validation_metric | roc_auc | r2 | mean_ic | median_ic | positive_ic_fraction | top10_lift | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | rf | all | 0.50360 | 0.53688 | — | 0.06254 | 0.06110 | 0.69565 | 1.10247 | 3732 |
| direction_abs | 10 | naive | all | 0.50000 | 0.50000 | — | — | — | — | 1.00000 | 3573 |
| return_abs | 5 | rf | all | 0.05388 | — | -0.02416 | 0.02045 | 0.00195 | 0.56522 | 1.11109 | 3732 |
| return_abs | 10 | rf | all | 0.03137 | — | -0.01920 | 0.03862 | 0.04120 | 0.68182 | 1.24448 | 3573 |
| direction_rel | 5 | rf | all | 0.55713 | 0.54949 | — | 0.01100 | 0.01928 | 0.52174 | 1.07045 | 3732 |
| direction_rel | 10 | rf | all | 0.53690 | 0.55637 | — | 0.05204 | -0.00352 | 0.50000 | 1.13923 | 3573 |
| rank_pct | 5 | rf | all | 0.07111 | — | 0.00138 | 0.04400 | 0.06169 | 0.73913 | 1.00000 | 3732 |
| rank_pct | 10 | rf | all | 0.06287 | — | 0.00397 | 0.05942 | 0.04657 | 0.68182 | 1.00000 | 3573 |
| excursion_balance | 5 | xgb | all | 0.03336 | — | -0.04953 | 0.02443 | 0.03818 | 0.56522 | 1.17446 | 3732 |
| excursion_balance | 10 | linear | all | 0.02615 | — | -0.26115 | 0.00350 | 0.01484 | 0.54545 | 1.13116 | 3573 |
| trend_tstat | 5 | xgb | all | 0.08187 | — | 0.00044 | 0.06606 | 0.08483 | 0.69565 | 1.11722 | 3732 |
| trend_tstat | 10 | xgb | all | 0.03054 | — | 0.00918 | 0.09148 | 0.12005 | 0.63636 | 1.07182 | 3573 |

Pour les directions : ROC AUC validation. Pour les régressions : IC Spearman moyen par cutoff validation. Les modèles/feature sets ne sont pas rechoisis selon leur test. AUC pooled et R² pooled sont des diagnostics ; le ranking principal utilise les IC par date.

## 3. RF/XGB, baselines, strict/strong, H5/H10

| model | feature_set | horizon | mean_ic | median_r2 | mean_auc | tasks |
| --- | --- | --- | --- | --- | --- | --- |
| linear | all | 5 | 0.00046 | -0.15917 | 0.51818 | 6 |
| linear | all | 10 | 0.02046 | -0.14086 | 0.52572 | 6 |
| naive | all | 5 | — | — | 0.50000 | 2 |
| naive | all | 10 | — | — | 0.50000 | 2 |
| naive_mean | all | 5 | — | -0.00149 | — | 4 |
| naive_mean | all | 10 | — | -0.00166 | — | 4 |
| naive_median | all | 5 | — | -0.00106 | — | 4 |
| naive_median | all | 10 | — | -0.00049 | — | 4 |
| rf | all | 5 | 0.03911 | -0.01139 | 0.54319 | 6 |
| rf | all | 10 | 0.04939 | -0.00761 | 0.55312 | 6 |
| xgb | all | 5 | 0.03914 | -0.01532 | 0.54714 | 6 |
| xgb | all | 10 | 0.05779 | -0.01071 | 0.55951 | 6 |

Les moyennes regroupant des targets différentes résument les expériences, sans test de significativité ni classement scientifique universel. Voir les 56 lignes de métriques test pour les comparaisons tâche par tâche.

## 4. Backtests des mêmes gagnants de validation

| target | horizon | cost_bp | cumulative_return | excess_return | max_drawdown | turnover | positions | average_exposure | flagged_closed_positions | missing_entries | unresolved_exits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | 0 | 0.05455 | 0.06932 | -0.02320 | 22.91499 | 384 | 0.36957 | 0 | 2 | 0 |
| direction_abs | 5 | 10 | 0.04253 | 0.05730 | -0.02463 | 22.90640 | 384 | 0.36948 | 0 | 2 | 0 |
| direction_abs | 5 | 25 | 0.02477 | 0.03953 | -0.02676 | 22.89352 | 384 | 0.36934 | 0 | 2 | 0 |
| direction_abs | 5 | 50 | -0.00414 | 0.01063 | -0.03029 | 22.87209 | 384 | 0.36911 | 0 | 2 | 0 |
| direction_abs | 10 | 0 | 0.02596 | 0.04073 | -0.05807 | 14.68709 | 370 | 0.53381 | 2 | 0 | 0 |
| direction_abs | 10 | 10 | 0.01845 | 0.03322 | -0.05900 | 14.68326 | 370 | 0.53372 | 2 | 0 | 0 |
| direction_abs | 10 | 25 | 0.00729 | 0.02205 | -0.06039 | 14.67754 | 370 | 0.53358 | 2 | 0 | 0 |
| direction_abs | 10 | 50 | -0.01104 | 0.00373 | -0.06507 | 14.66801 | 370 | 0.53335 | 2 | 0 | 0 |
| return_abs | 5 | 0 | 0.01154 | 0.02630 | -0.05282 | 22.87251 | 384 | 0.37148 | 3 | 2 | 0 |
| return_abs | 5 | 10 | 0.00002 | 0.01478 | -0.05422 | 22.86394 | 384 | 0.37139 | 3 | 2 | 0 |
| return_abs | 5 | 25 | -0.01700 | -0.00224 | -0.05632 | 22.85111 | 384 | 0.37125 | 3 | 2 | 0 |
| return_abs | 5 | 50 | -0.04470 | -0.02994 | -0.05980 | 22.82975 | 384 | 0.37102 | 3 | 2 | 0 |
| return_abs | 10 | 0 | 0.07439 | 0.08915 | -0.06561 | 14.61153 | 368 | 0.53321 | 6 | 2 | 0 |
| return_abs | 10 | 10 | 0.06654 | 0.08131 | -0.06638 | 14.60773 | 368 | 0.53312 | 6 | 2 | 0 |
| return_abs | 10 | 25 | 0.05488 | 0.06964 | -0.06753 | 14.60204 | 368 | 0.53298 | 6 | 2 | 0 |
| return_abs | 10 | 50 | 0.03574 | 0.05051 | -0.06944 | 14.59257 | 368 | 0.53275 | 6 | 2 | 0 |
| direction_rel | 5 | 0 | 0.03958 | 0.05435 | -0.03144 | 22.89960 | 384 | 0.36988 | 0 | 2 | 0 |
| direction_rel | 5 | 10 | 0.02774 | 0.04251 | -0.03451 | 22.89101 | 384 | 0.36979 | 0 | 2 | 0 |
| direction_rel | 5 | 25 | 0.01024 | 0.02501 | -0.03910 | 22.87814 | 384 | 0.36965 | 0 | 2 | 0 |
| direction_rel | 5 | 50 | -0.01824 | -0.00347 | -0.04969 | 22.85673 | 384 | 0.36942 | 0 | 2 | 0 |
| direction_rel | 10 | 0 | 0.07993 | 0.09469 | -0.04993 | 14.69498 | 370 | 0.53482 | 0 | 0 | 0 |
| direction_rel | 10 | 10 | 0.07200 | 0.08676 | -0.05086 | 14.69117 | 370 | 0.53473 | 0 | 0 | 0 |
| direction_rel | 10 | 25 | 0.06022 | 0.07498 | -0.05227 | 14.68546 | 370 | 0.53459 | 0 | 0 | 0 |
| direction_rel | 10 | 50 | 0.04089 | 0.05565 | -0.05460 | 14.67596 | 370 | 0.53436 | 0 | 0 | 0 |
| rank_pct | 5 | 0 | 0.09488 | 0.10965 | -0.02490 | 22.92034 | 384 | 0.37022 | 1 | 2 | 0 |
| rank_pct | 5 | 10 | 0.08238 | 0.09714 | -0.02538 | 22.91176 | 384 | 0.37012 | 1 | 2 | 0 |
| rank_pct | 5 | 25 | 0.06391 | 0.07867 | -0.02610 | 22.89889 | 384 | 0.36998 | 1 | 2 | 0 |
| rank_pct | 5 | 50 | 0.03385 | 0.04861 | -0.02730 | 22.87748 | 384 | 0.36975 | 1 | 2 | 0 |
| rank_pct | 10 | 0 | 0.08242 | 0.09718 | -0.02891 | 14.65646 | 369 | 0.53255 | 1 | 1 | 0 |
| rank_pct | 10 | 10 | 0.07450 | 0.08927 | -0.02953 | 14.65265 | 369 | 0.53246 | 1 | 1 | 0 |
| rank_pct | 10 | 25 | 0.06274 | 0.07750 | -0.03046 | 14.64694 | 369 | 0.53232 | 1 | 1 | 0 |
| rank_pct | 10 | 50 | 0.04343 | 0.05820 | -0.03200 | 14.63744 | 369 | 0.53209 | 1 | 1 | 0 |
| excursion_balance | 5 | 0 | 0.08369 | 0.09846 | -0.06313 | 22.91192 | 384 | 0.37183 | 2 | 2 | 0 |
| excursion_balance | 5 | 10 | 0.07131 | 0.08608 | -0.06521 | 22.90336 | 384 | 0.37173 | 2 | 2 | 0 |
| excursion_balance | 5 | 25 | 0.05303 | 0.06779 | -0.06832 | 22.89052 | 384 | 0.37160 | 2 | 2 | 0 |
| excursion_balance | 5 | 50 | 0.02326 | 0.03803 | -0.07348 | 22.86915 | 384 | 0.37137 | 2 | 2 | 0 |
| excursion_balance | 10 | 0 | 0.00102 | 0.01578 | -0.05424 | 14.59248 | 368 | 0.53032 | 2 | 2 | 0 |
| excursion_balance | 10 | 10 | -0.00626 | 0.00851 | -0.05531 | 14.58865 | 368 | 0.53023 | 2 | 2 | 0 |
| excursion_balance | 10 | 25 | -0.01707 | -0.00231 | -0.05691 | 14.58292 | 368 | 0.53009 | 2 | 2 | 0 |
| excursion_balance | 10 | 50 | -0.03482 | -0.02005 | -0.05956 | 14.57339 | 368 | 0.52986 | 2 | 2 | 0 |
| trend_tstat | 5 | 0 | 0.05102 | 0.06578 | -0.03237 | 23.02634 | 386 | 0.37156 | 0 | 0 | 0 |
| trend_tstat | 5 | 10 | 0.03898 | 0.05375 | -0.03477 | 23.01772 | 386 | 0.37147 | 0 | 0 | 0 |
| trend_tstat | 5 | 25 | 0.02119 | 0.03595 | -0.03869 | 23.00480 | 386 | 0.37133 | 0 | 0 | 0 |
| trend_tstat | 5 | 50 | -0.00776 | 0.00701 | -0.04523 | 22.98330 | 386 | 0.37110 | 0 | 0 | 0 |
| trend_tstat | 10 | 0 | 0.03761 | 0.05238 | -0.04040 | 14.68557 | 370 | 0.53413 | 0 | 0 | 0 |
| trend_tstat | 10 | 10 | 0.03001 | 0.04477 | -0.04135 | 14.68175 | 370 | 0.53404 | 0 | 0 | 0 |
| trend_tstat | 10 | 25 | 0.01871 | 0.03347 | -0.04277 | 14.67602 | 370 | 0.53390 | 0 | 0 | 0 |
| trend_tstat | 10 | 50 | 0.00017 | 0.01493 | -0.04514 | 14.66650 | 370 | 0.53367 | 0 | 0 | 0 |

Frais all-in **aller-retour**, moitié à l'entrée et moitié à la sortie. Portefeuilles sans levier, cash non rémunéré, compartiments de capital fixes (2 en H5 / 3 en H10), top 10 %, entrée next_open, sortie close du H-ième jour commun. Le turnover est la somme des achats + ventes rapportés à la NAV précédente.

### Baselines de portefeuille

| horizon | cost_bp | cumulative_return | benchmark_return | max_drawdown | turnover | average_exposure |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 0 | 0.01651 | -0.01477 | -0.03170 | 22.99108 | 0.37132 |
| 5 | 10 | 0.00488 | -0.01477 | -0.03290 | 22.98246 | 0.37123 |
| 5 | 25 | -0.01229 | -0.01477 | -0.03468 | 22.96956 | 0.37109 |
| 5 | 50 | -0.04024 | -0.01477 | -0.04650 | 22.94808 | 0.37086 |
| 10 | 0 | 0.00499 | -0.01477 | -0.05244 | 14.66386 | 0.53329 |
| 10 | 10 | -0.00236 | -0.01477 | -0.05353 | 14.66004 | 0.53320 |
| 10 | 25 | -0.01328 | -0.01477 | -0.05517 | 14.65431 | 0.53306 |
| 10 | 50 | -0.03119 | -0.01477 | -0.05815 | 14.64478 | 0.53283 |

Equal-weight universe suit exactement les mêmes compartiments/cutoffs/frais. CAC AllShares est un buy-and-hold next_open → dernier close sur la même fenêtre ; son exposition est différente. Aucun dividende ni ajustement certifié. L'annualisation du rendement n'est publiée qu'à partir de 126 séances. Les Sharpe descriptifs sur S1 restent fragiles.

## 5. Excursion balance et trend t-stat

| target | horizon | score_vs_return_abs | score_vs_excursion_balance | score_vs_trend_tstat | score_vs_volatility | score_vs_max_upside | score_vs_max_downside | truth_vs_return_abs | truth_vs_volatility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| excursion_balance | 5 | 0.04865 | 0.04777 | 0.03785 | 0.08997 | 0.06862 | 0.01583 | 0.91622 | -0.01865 |
| excursion_balance | 10 | 0.01709 | 0.03421 | 0.00660 | 0.02395 | 0.04119 | 0.02610 | 0.90587 | -0.01840 |
| trend_tstat | 5 | 0.03802 | 0.04142 | 0.05580 | -0.17885 | -0.01151 | 0.09391 | 0.81975 | -0.03803 |
| trend_tstat | 10 | 0.09444 | 0.09981 | 0.09568 | -0.23301 | 0.03351 | 0.16355 | 0.87384 | -0.04612 |

Les corrélations pooled ci-dessus diagnostiquent les trajectoires et leur lien à la volatilité ; elles ne prouvent aucune causalité. `excursion_balance` est max+min des rendements close futurs sans ancrage artificiel à zéro. Le t-stat futur est calculé sur exactement H closes normalisés base 100 ; les trajectoires parfaitement linéaires atteignent le plafond numérique ±1e6, les plates valent 0.

## 6. Features : gain/impurity et permutation sur validation uniquement

| target | horizon | feature_set | model | feature_id | importance_type | gain_or_impurity | validation_permutation_drop |
| --- | --- | --- | --- | --- | --- | --- | --- |
| excursion_balance | 5 | all | xgb | volume.relative.current_vs_mean.w504.v1 | gain | 0.00701 | 0.01642 |
| return_abs | 5 | all | rf | open.level.range_pct.w504.v1 | impurity | 0.00816 | 0.01593 |
| return_abs | 5 | all | rf | close.return.q75.w20.v1 | impurity | 0.00745 | 0.01244 |
| return_abs | 5 | all | rf | ohlc.relation.candle_body.w30.v1 | impurity | 0.00970 | 0.01178 |
| return_abs | 10 | all | rf | low.level.kurtosis.w504.v1 | impurity | 0.00464 | 0.01122 |
| return_abs | 10 | all | rf | ohlc.relation.upper_wick.w504.v1 | impurity | 0.01149 | 0.01071 |
| excursion_balance | 5 | all | xgb | open.level.range_pct.w10.v1 | gain | 0.00571 | 0.00902 |
| direction_abs | 5 | all | rf | ohlc.relation.candle_body.w120.v1 | impurity | 0.02328 | 0.00850 |
| trend_tstat | 10 | all | xgb | ohlc.relation.candle_body.w30.v1 | gain | 0.00918 | 0.00845 |
| return_abs | 5 | all | rf | low.level.range_pct.w504.v1 | impurity | 0.00521 | 0.00826 |
| return_abs | 5 | all | rf | high.log.trend_pct.w504.v1 | impurity | 0.00187 | 0.00766 |
| direction_rel | 10 | all | rf | close.log.residual_pct.w5.v1 | impurity | 0.03231 | 0.00746 |
| return_abs | 5 | all | rf | open.level.range_pct.w10.v1 | impurity | 0.00718 | 0.00742 |
| excursion_balance | 5 | all | xgb | ohlc.relation.overnight_gap.w5.v1 | gain | 0.00521 | 0.00718 |
| return_abs | 5 | all | rf | ohlc.relation.upper_wick.w5.v1 | impurity | 0.01042 | 0.00714 |
| return_abs | 5 | all | rf | close.log_return.median.w20.v1 | impurity | 0.00917 | 0.00701 |
| return_abs | 5 | all | rf | ohlc.relation.upper_wick.w20.v1 | impurity | 0.00784 | 0.00694 |
| return_abs | 5 | all | rf | ohlc.relation.candle_body.w20.v1 | impurity | 0.01814 | 0.00690 |
| return_abs | 10 | all | rf | ohlc.relation.close_location.w504.v1 | impurity | 0.00864 | 0.00651 |
| return_abs | 5 | all | rf | close.return.mean.w20.v1 | impurity | 0.00951 | 0.00651 |
### Stabilité des importances

| model | feature_set | comparison | mean_overlap | median_jaccard | pairs |
| --- | --- | --- | --- | --- | --- |
| rf | all | horizon | 1.50000 | 0.02564 | 6 |
| rf | all | target | 1.50000 | 0.02564 | 30 |
| rf | all | target_and_horizon | 0.76667 | 0.00000 | 30 |
| xgb | all | horizon | 3.33333 | 0.08108 | 6 |
| xgb | all | target | 2.13333 | 0.05263 | 30 |
| xgb | all | target_and_horizon | 1.33333 | 0.02564 | 30 |

Permutation de chaque feature verrouillée, une réplication à seed fixe, estimateur entraîné sur 2024 uniquement. Cette importance marginale est instable et diluée par la redondance ; elle ne sert pas à retirer des variables. RF expose impurity ; XGB gain. SHAP n'est pas requis et n'est pas ajouté au premier benchmark.

## 7. Stabilité par cutoff et extrêmes

### Exemples de trajectoires observées, choisis à titre illustratif

| case | entity_id | cutoff | horizon | return_abs | trend_tstat | excursion_balance | volatility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rendement modeste / trajectoire régulière | abc-bourse-manual:equity:FR0014000MR3 | 2026-02-20 | 5 | 0.00918 | 58.36113 | -0.00888 | 0.01011 |
| grand mouvement / t-stat faible | abc-bourse-manual:equity:FR001400Q9V2 | 2026-02-06 | 5 | 0.08238 | 0.12573 | 0.10153 | 0.56768 |
| rendement modeste / trajectoire régulière | abc-bourse-manual:equity:FR0000060303 | 2026-06-12 | 10 | -0.01747 | -12.02102 | -0.00873 | 0.06013 |
| grand mouvement / t-stat faible | abc-bourse-manual:equity:NL0000226223 | 2026-05-29 | 10 | 0.14928 | 0.05045 | 0.16777 | 1.01100 |
Les colonnes median IC / fraction IC>0 de la table 2 et les courbes Model Lab montrent la stabilité. `cutoff_metrics.parquet` et `decile_metrics.parquet` conservent tous les cutoffs, spreads D10−D1 et monotonicités. Les lifts top10/top20/bottom10 sont les moyennes des taux positifs relatifs à la population de chaque date ; les ex æquo peuvent agrandir ces groupes. Le portefeuille utilise, lui, exactement ceil(10 %×N), avec départage stable par ID. Pour `rank_pct`, le lift de taux positif vaut mécaniquement 1 : tous les percentiles sont positifs. Il faut lire l'IC, les écarts de percentile et les rendements du portefeuille.

## 8. Incohérences, leakage et conclusion

**GO exploratoire.** Lecture descriptive : 10/10 gagnants RF/XGB ont un IC test positif ; 10/12 gagnants de validation dépassent l'equal-weight comparable à 50 bp. Cette règle de lecture ne crée ni p-value ni preuve d'alpha.

Avant un cycle plus réaliste : prix/corporate actions certifiés, univers daté, période réellement neuve, calendrier/latence et coûts de liquidité. Aucun résultat de SPEC-007 n'est utilisé. Les nouvelles targets et views sont isolées : le registre historique gelé, le lock et les fichiers SPEC-007 sont byte-identiques.

## 9. Artefacts, reproductibilité et rapport intégral

SHA de base du run : `c61fd520ccb0ba2655c1927cf4cc1eb1f6423d8f` ; dirty lors du run : `True`. Les empreintes exactes des fichiers scientifiques utilisés sont dans summary/model registry, et celles des datasets dans dataset_manifest. Le SHA Git final est indiqué au compte rendu.

Tables locales sous `data/analysis/spec008-model-lab` (hors Git), modèles joblib, registre JSON, métriques, prédictions, déciles, calibration, importances, trajectoires, trades, equity et résumé. `uv run python scripts/model_lab_spec008.py report` régénère ce Markdown à partir des artefacts.

### Toutes les métriques test

| target | horizon | feature_set | model | roc_auc | pr_auc | balanced_accuracy | accuracy | log_loss | brier | calibration_ece | r2 | rmse | mae | mean_ic | median_ic | positive_ic_fraction | top10_lift | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | all | naive | 0.50000 | 0.48842 | 0.50000 | 0.48842 | 0.69417 | 0.25051 | 0.02544 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_abs | 5 | all | linear | 0.51674 | 0.50470 | 0.50315 | 0.50095 | 0.74803 | 0.27179 | 0.12845 | — | — | — | 0.01180 | 0.01009 | 0.56522 | 1.04504 | 3732 |
| direction_abs | 5 | all | rf | 0.53688 | 0.52018 | 0.52315 | 0.52029 | 0.69218 | 0.24951 | 0.02547 | — | — | — | 0.06254 | 0.06110 | 0.69565 | 1.10247 | 3732 |
| direction_abs | 5 | all | xgb | 0.54199 | 0.52899 | 0.52083 | 0.51784 | 0.69169 | 0.24927 | 0.02826 | — | — | — | 0.06213 | 0.04685 | 0.78261 | 1.07508 | 3732 |
| return_abs | 5 | all | naive_mean | — | — | — | — | — | — | — | -0.00290 | 0.05451 | 0.03792 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | all | naive_median | — | — | — | — | — | — | — | -0.00244 | 0.05450 | 0.03791 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | all | linear | — | — | — | — | — | — | — | -0.21796 | 0.06007 | 0.04198 | -0.00108 | 0.01159 | 0.60870 | 0.99761 | 3732 |
| return_abs | 5 | all | rf | — | — | — | — | — | — | — | -0.02416 | 0.05509 | 0.03798 | 0.02045 | 0.00195 | 0.56522 | 1.11109 | 3732 |
| return_abs | 5 | all | xgb | — | — | — | — | — | — | — | -0.03109 | 0.05527 | 0.03806 | 0.00923 | 0.00577 | 0.52174 | 1.19710 | 3732 |
| direction_rel | 5 | all | naive | 0.50000 | 0.51983 | 0.50000 | 0.48017 | 0.69323 | 0.25004 | 0.02088 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_rel | 5 | all | linear | 0.51963 | 0.52872 | 0.51218 | 0.51501 | 0.73519 | 0.26588 | 0.10269 | — | — | — | -0.00768 | -0.01213 | 0.47826 | 0.97314 | 3732 |
| direction_rel | 5 | all | rf | 0.54949 | 0.56337 | 0.53929 | 0.53671 | 0.68933 | 0.24811 | 0.02377 | — | — | — | 0.01100 | 0.01928 | 0.52174 | 1.07045 | 3732 |
| direction_rel | 5 | all | xgb | 0.55230 | 0.56260 | 0.53776 | 0.53725 | 0.68947 | 0.24815 | 0.02284 | — | — | — | 0.01802 | 0.01107 | 0.69565 | 1.08784 | 3732 |
| rank_pct | 5 | all | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | all | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | all | linear | — | — | — | — | — | — | — | -0.10219 | 0.30306 | 0.25647 | 0.00064 | -0.00309 | 0.47826 | 1.00000 | 3732 |
| rank_pct | 5 | all | rf | — | — | — | — | — | — | — | 0.00138 | 0.28847 | 0.24972 | 0.04400 | 0.06169 | 0.73913 | 1.00000 | 3732 |
| rank_pct | 5 | all | xgb | — | — | — | — | — | — | — | 0.00126 | 0.28849 | 0.24947 | 0.05500 | 0.07650 | 0.69565 | 1.00000 | 3732 |
| excursion_balance | 5 | all | naive_mean | — | — | — | — | — | — | — | -0.00271 | 0.07270 | 0.04988 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | all | naive_median | — | — | — | — | — | — | — | -0.00211 | 0.07267 | 0.04986 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | all | linear | — | — | — | — | — | — | — | -0.21615 | 0.08006 | 0.05564 | -0.00050 | 0.00586 | 0.65217 | 1.07948 | 3732 |
| excursion_balance | 5 | all | rf | — | — | — | — | — | — | — | -0.03521 | 0.07386 | 0.04994 | 0.02863 | 0.02306 | 0.69565 | 1.12135 | 3732 |
| excursion_balance | 5 | all | xgb | — | — | — | — | — | — | — | -0.04953 | 0.07437 | 0.05005 | 0.02443 | 0.03818 | 0.56522 | 1.17446 | 3732 |
| trend_tstat | 5 | all | naive_mean | — | — | — | — | — | — | — | -0.00027 | 4.10197 | 2.63975 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | all | naive_median | — | — | — | — | — | — | — | -0.00000 | 4.10141 | 2.63981 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | all | linear | — | — | — | — | — | — | — | -0.06770 | 4.23797 | 2.78866 | -0.00039 | -0.01674 | 0.47826 | 0.95188 | 3732 |
| trend_tstat | 5 | all | rf | — | — | — | — | — | — | — | 0.00196 | 4.09740 | 2.63770 | 0.06807 | 0.09005 | 0.69565 | 1.12148 | 3732 |
| trend_tstat | 5 | all | xgb | — | — | — | — | — | — | — | 0.00044 | 4.10051 | 2.63906 | 0.06606 | 0.08483 | 0.69565 | 1.11722 | 3732 |
| direction_abs | 10 | all | naive | 0.50000 | 0.47743 | 0.50000 | 0.47743 | 0.69383 | 0.25034 | 0.02918 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_abs | 10 | all | linear | 0.53170 | 0.50443 | 0.52303 | 0.51975 | 0.75506 | 0.27306 | 0.12252 | — | — | — | 0.02917 | 0.04197 | 0.63636 | 1.01915 | 3573 |
| direction_abs | 10 | all | rf | 0.54987 | 0.52693 | 0.53258 | 0.53047 | 0.69015 | 0.24850 | 0.03219 | — | — | — | 0.05701 | 0.04771 | 0.63636 | 1.15725 | 3573 |
| direction_abs | 10 | all | xgb | 0.55600 | 0.53610 | 0.53620 | 0.53386 | 0.68874 | 0.24782 | 0.03284 | — | — | — | 0.06105 | 0.05852 | 0.77273 | 1.15851 | 3573 |
| return_abs | 10 | all | naive_mean | — | — | — | — | — | — | — | -0.00321 | 0.07782 | 0.05576 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | all | naive_median | — | — | — | — | — | — | — | -0.00176 | 0.07776 | 0.05568 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | all | linear | — | — | — | — | — | — | — | -0.19430 | 0.08490 | 0.06080 | 0.00699 | 0.00574 | 0.50000 | 1.13384 | 3573 |
| return_abs | 10 | all | rf | — | — | — | — | — | — | — | -0.01920 | 0.07843 | 0.05569 | 0.03862 | 0.04120 | 0.68182 | 1.24448 | 3573 |
| return_abs | 10 | all | xgb | — | — | — | — | — | — | — | -0.02864 | 0.07880 | 0.05589 | 0.02090 | 0.00939 | 0.54545 | 1.20445 | 3573 |
| direction_rel | 10 | all | naive | 0.50000 | 0.51469 | 0.50000 | 0.48531 | 0.69321 | 0.25003 | 0.01578 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_rel | 10 | all | linear | 0.51975 | 0.53143 | 0.50885 | 0.51273 | 0.75106 | 0.27057 | 0.12150 | — | — | — | 0.02036 | 0.02343 | 0.63636 | 0.96798 | 3573 |
| direction_rel | 10 | all | rf | 0.55637 | 0.57768 | 0.53185 | 0.53093 | 0.68691 | 0.24692 | 0.01114 | — | — | — | 0.05204 | -0.00352 | 0.50000 | 1.13923 | 3573 |
| direction_rel | 10 | all | xgb | 0.56302 | 0.58495 | 0.54622 | 0.54632 | 0.68566 | 0.24632 | 0.01461 | — | — | — | 0.06506 | 0.05836 | 0.63636 | 1.16355 | 3573 |
| rank_pct | 10 | all | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | all | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | all | linear | — | — | — | — | — | — | — | -0.08742 | 0.30102 | 0.25616 | 0.02846 | 0.02433 | 0.59091 | 1.00000 | 3573 |
| rank_pct | 10 | all | rf | — | — | — | — | — | — | — | 0.00397 | 0.28810 | 0.24909 | 0.05942 | 0.04657 | 0.68182 | 1.00000 | 3573 |
| rank_pct | 10 | all | xgb | — | — | — | — | — | — | — | 0.00723 | 0.28762 | 0.24872 | 0.09151 | 0.06914 | 0.72727 | 1.00000 | 3573 |
| excursion_balance | 10 | all | naive_mean | — | — | — | — | — | — | — | -0.00151 | 0.09546 | 0.06820 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | all | naive_median | — | — | — | — | — | — | — | -0.00012 | 0.09539 | 0.06814 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | all | linear | — | — | — | — | — | — | — | -0.26115 | 0.10712 | 0.07563 | 0.00350 | 0.01484 | 0.54545 | 1.13116 | 3573 |
| excursion_balance | 10 | all | rf | — | — | — | — | — | — | — | -0.02032 | 0.09635 | 0.06815 | 0.01308 | 0.01949 | 0.63636 | 1.19549 | 3573 |
| excursion_balance | 10 | all | xgb | — | — | — | — | — | — | — | -0.04508 | 0.09751 | 0.06858 | 0.01674 | 0.03005 | 0.63636 | 1.09636 | 3573 |
| trend_tstat | 10 | all | naive_mean | — | — | — | — | — | — | — | -0.00181 | 4.38574 | 3.35749 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | all | naive_median | — | — | — | — | — | — | — | -0.00086 | 4.38365 | 3.35520 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | all | linear | — | — | — | — | — | — | — | -0.06374 | 4.51926 | 3.49873 | 0.03426 | 0.03619 | 0.54545 | 1.00979 | 3573 |
| trend_tstat | 10 | all | rf | — | — | — | — | — | — | — | 0.00472 | 4.37140 | 3.35527 | 0.07616 | 0.10053 | 0.63636 | 1.11925 | 3573 |
| trend_tstat | 10 | all | xgb | — | — | — | — | — | — | — | 0.00918 | 4.36161 | 3.34899 | 0.09148 | 0.12005 | 0.63636 | 1.07182 | 3573 |
### Couverture par tâche

| target | horizon | feature_set | split | eligible_rows | usable_labels | neutral_n | future_warning_n | uninterpretable_n | feature_missing_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | all | train | 9068 | 8940 | 127 | 6 | 0 | 0.08952 |
| direction_abs | 5 | all | validation | 4187 | 4120 | 65 | 6 | 2 | 0.00974 |
| direction_abs | 5 | all | test | 3732 | 3671 | 61 | 7 | 0 | 0.00723 |
| return_abs | 5 | all | train | 9068 | 9067 | 0 | 6 | 0 | 0.08952 |
| return_abs | 5 | all | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00974 |
| return_abs | 5 | all | test | 3732 | 3732 | 0 | 7 | 0 | 0.00723 |
| direction_rel | 5 | all | train | 9068 | 9067 | 0 | 6 | 0 | 0.08952 |
| direction_rel | 5 | all | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00974 |
| direction_rel | 5 | all | test | 3732 | 3732 | 0 | 7 | 0 | 0.00723 |
| rank_pct | 5 | all | train | 9068 | 9067 | 0 | 6 | 0 | 0.08952 |
| rank_pct | 5 | all | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00974 |
| rank_pct | 5 | all | test | 3732 | 3732 | 0 | 7 | 0 | 0.00723 |
| excursion_balance | 5 | all | train | 9068 | 9067 | 0 | 6 | 0 | 0.08952 |
| excursion_balance | 5 | all | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00974 |
| excursion_balance | 5 | all | test | 3732 | 3732 | 0 | 7 | 0 | 0.00723 |
| trend_tstat | 5 | all | train | 9068 | 9067 | 0 | 6 | 0 | 0.08952 |
| trend_tstat | 5 | all | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00974 |
| trend_tstat | 5 | all | test | 3732 | 3732 | 0 | 7 | 0 | 0.00723 |
| direction_abs | 10 | all | train | 8890 | 8811 | 78 | 12 | 0 | 0.09110 |
| direction_abs | 10 | all | validation | 4017 | 3974 | 39 | 12 | 4 | 0.00981 |
| direction_abs | 10 | all | test | 3573 | 3544 | 29 | 11 | 0 | 0.00727 |
| return_abs | 10 | all | train | 8890 | 8889 | 0 | 12 | 0 | 0.09110 |
| return_abs | 10 | all | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00981 |
| return_abs | 10 | all | test | 3573 | 3573 | 0 | 11 | 0 | 0.00727 |
| direction_rel | 10 | all | train | 8890 | 8889 | 0 | 12 | 0 | 0.09110 |
| direction_rel | 10 | all | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00981 |
| direction_rel | 10 | all | test | 3573 | 3573 | 0 | 11 | 0 | 0.00727 |
| rank_pct | 10 | all | train | 8890 | 8889 | 0 | 12 | 0 | 0.09110 |
| rank_pct | 10 | all | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00981 |
| rank_pct | 10 | all | test | 3573 | 3573 | 0 | 11 | 0 | 0.00727 |
| excursion_balance | 10 | all | train | 8890 | 8889 | 0 | 12 | 0 | 0.09110 |
| excursion_balance | 10 | all | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00981 |
| excursion_balance | 10 | all | test | 3573 | 3573 | 0 | 11 | 0 | 0.00727 |
| trend_tstat | 10 | all | train | 8890 | 8889 | 0 | 12 | 0 | 0.09110 |
| trend_tstat | 10 | all | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00981 |
| trend_tstat | 10 | all | test | 3573 | 3573 | 0 | 11 | 0 | 0.00727 |
