# SPEC-008 — résultats reproductibles

**Development backtest — not independent confirmation.**

Calculs : 112 modèles finaux, 160 fits de découverte/validation, 112 retrains. XGBoost CPU est la référence principale.

Lock `7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f` ; registry additif `906d8281f40614e2c91d069866018894a215e0ac52de50e0358ab427b8a91044`.

**Contamination de sélection :** strict/strong ont été choisis avec des outcomes de 2025 **et 2026**. L'absence de tuning sur 2026 dans ce code ne supprime pas cette connaissance préalable. Aucun chiffre ci-dessous n'est une confirmation indépendante.

## 1. Splits exacts et effectifs

| horizon | split | first_cutoff | last_cutoff | last_usable_label_end | cutoff_n | eligible_rows | usable_labels | feature_missing_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | train | 2024-01-05 | 2024-12-20 | 2024-12-31 | 50 | 9068 | 9067 | 0.00173 |
| 5 | validation | 2025-01-03 | 2025-06-20 | 2025-06-27 | 24 | 4187 | 4185 | 0.00011 |
| 5 | test | 2026-01-02 | 2026-06-19 | 2026-06-26 | 23 | 3732 | 3732 | 0.00000 |
| 10 | train | 2024-01-05 | 2024-12-13 | 2024-12-31 | 49 | 8890 | 8889 | 0.00176 |
| 10 | validation | 2025-01-03 | 2025-06-13 | 2025-06-27 | 23 | 4017 | 4013 | 0.00011 |
| 10 | test | 2026-01-02 | 2026-06-12 | 2026-06-26 | 22 | 3573 | 3573 | 0.00000 |

Les effectifs sont des couples entité/cutoff répétés, pas des observations indépendantes. Les lignes dont la target traverse une frontière restent dans la matrice/prédictions ; leur label est nul. Le purge/embargo calendaire est appliqué à toutes les entités d'un cutoff.

## 2. Modèle retenu exclusivement sur validation, puis lu en S1 2026

| target | horizon | model | feature_set | validation_metric | roc_auc | r2 | mean_ic | median_ic | positive_ic_fraction | top10_lift | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | linear | strong | 0.51657 | 0.54732 | — | 0.04657 | 0.05636 | 0.69565 | 1.12792 | 3732 |
| direction_abs | 10 | linear | strict | 0.52800 | 0.54639 | — | 0.03082 | 0.03211 | 0.68182 | 1.08993 | 3573 |
| return_abs | 5 | linear | strong | 0.03946 | — | -0.07576 | 0.01554 | 0.03208 | 0.65217 | 1.07606 | 3732 |
| return_abs | 10 | rf | strong | 0.02751 | — | -0.02281 | 0.05847 | 0.01270 | 0.59091 | 1.18554 | 3573 |
| direction_rel | 5 | rf | strong | 0.54571 | 0.52054 | — | -0.01072 | -0.00361 | 0.47826 | 1.05264 | 3732 |
| direction_rel | 10 | xgb | strong | 0.52216 | 0.53507 | — | 0.02014 | 0.00813 | 0.50000 | 1.02406 | 3573 |
| rank_pct | 5 | linear | strong | 0.06652 | — | -0.02943 | 0.04798 | 0.03994 | 0.60870 | 1.00000 | 3732 |
| rank_pct | 10 | rf | strict | 0.01284 | — | 0.00288 | 0.05251 | 0.02150 | 0.59091 | 1.00000 | 3573 |
| excursion_balance | 5 | linear | strong | 0.03386 | — | -0.07949 | 0.01341 | 0.02029 | 0.56522 | 1.00040 | 3732 |
| excursion_balance | 10 | rf | strong | 0.03527 | — | -0.04573 | 0.04858 | 0.03464 | 0.68182 | 1.13582 | 3573 |
| trend_tstat | 5 | linear | strong | 0.03618 | — | 0.00020 | 0.02972 | 0.05356 | 0.69565 | 1.07097 | 3732 |
| trend_tstat | 10 | rf | strong | 0.03800 | — | -0.00092 | 0.02298 | 0.03571 | 0.54545 | 0.97305 | 3573 |

Pour les directions : ROC AUC validation. Pour les régressions : IC Spearman moyen par cutoff validation. Les modèles/feature sets ne sont pas rechoisis selon leur test. AUC pooled et R² pooled sont des diagnostics ; le ranking principal utilise les IC par date.

## 3. RF/XGB, baselines, strict/strong, H5/H10

| model | feature_set | horizon | mean_ic | median_r2 | mean_auc | tasks |
| --- | --- | --- | --- | --- | --- | --- |
| linear | strict | 5 | 0.02234 | -0.03181 | 0.53132 | 6 |
| linear | strict | 10 | 0.02901 | -0.02033 | 0.53939 | 6 |
| linear | strong | 5 | 0.02681 | -0.05259 | 0.53644 | 6 |
| linear | strong | 10 | 0.03248 | -0.03360 | 0.53927 | 6 |
| naive | strict | 5 | — | — | 0.50000 | 2 |
| naive | strict | 10 | — | — | 0.50000 | 2 |
| naive | strong | 5 | — | — | 0.50000 | 2 |
| naive | strong | 10 | — | — | 0.50000 | 2 |
| naive_mean | strict | 5 | — | -0.00149 | — | 4 |
| naive_mean | strict | 10 | — | -0.00166 | — | 4 |
| naive_mean | strong | 5 | — | -0.00149 | — | 4 |
| naive_mean | strong | 10 | — | -0.00166 | — | 4 |
| naive_median | strict | 5 | — | -0.00106 | — | 4 |
| naive_median | strict | 10 | — | -0.00049 | — | 4 |
| naive_median | strong | 5 | — | -0.00106 | — | 4 |
| naive_median | strong | 10 | — | -0.00049 | — | 4 |
| rf | strict | 5 | 0.01817 | -0.01186 | 0.51888 | 6 |
| rf | strict | 10 | 0.03945 | -0.01412 | 0.53828 | 6 |
| rf | strong | 5 | 0.01632 | -0.01342 | 0.51874 | 6 |
| rf | strong | 10 | 0.03994 | -0.01187 | 0.53580 | 6 |
| xgb | strict | 5 | 0.01790 | -0.01836 | 0.51991 | 6 |
| xgb | strict | 10 | 0.03520 | -0.01060 | 0.54052 | 6 |
| xgb | strong | 5 | 0.02262 | -0.02160 | 0.52749 | 6 |
| xgb | strong | 10 | 0.03227 | -0.02179 | 0.53597 | 6 |

Les moyennes regroupant des targets différentes résument les expériences, sans test de significativité ni classement scientifique universel. Voir les 112 lignes de métriques test pour les comparaisons tâche par tâche.

## 4. Backtests des mêmes gagnants de validation

| target | horizon | cost_bp | cumulative_return | excess_return | max_drawdown | turnover | positions | average_exposure | flagged_closed_positions | missing_entries | unresolved_exits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | 0 | 0.07044 | 0.08521 | -0.03249 | 22.91741 | 384 | 0.37160 | 2 | 2 | 0 |
| direction_abs | 5 | 10 | 0.05822 | 0.07299 | -0.03320 | 22.90883 | 384 | 0.37151 | 2 | 2 | 0 |
| direction_abs | 5 | 25 | 0.04017 | 0.05493 | -0.03427 | 22.89599 | 384 | 0.37137 | 2 | 2 | 0 |
| direction_abs | 5 | 50 | 0.01079 | 0.02555 | -0.04476 | 22.87461 | 384 | 0.37114 | 2 | 2 | 0 |
| direction_abs | 10 | 0 | 0.02140 | 0.03616 | -0.06335 | 14.68989 | 370 | 0.53521 | 2 | 0 | 0 |
| direction_abs | 10 | 10 | 0.01391 | 0.02868 | -0.06599 | 14.68608 | 370 | 0.53512 | 2 | 0 | 0 |
| direction_abs | 10 | 25 | 0.00279 | 0.01755 | -0.06994 | 14.68037 | 370 | 0.53498 | 2 | 0 | 0 |
| direction_abs | 10 | 50 | -0.01547 | -0.00070 | -0.07647 | 14.67088 | 370 | 0.53475 | 2 | 0 | 0 |
| return_abs | 5 | 0 | 0.06834 | 0.08311 | -0.04083 | 22.90241 | 384 | 0.37035 | 1 | 2 | 0 |
| return_abs | 5 | 10 | 0.05616 | 0.07092 | -0.04297 | 22.89383 | 384 | 0.37025 | 1 | 2 | 0 |
| return_abs | 5 | 25 | 0.03815 | 0.05292 | -0.04617 | 22.88096 | 384 | 0.37011 | 1 | 2 | 0 |
| return_abs | 5 | 50 | 0.00885 | 0.02362 | -0.05147 | 22.85956 | 384 | 0.36988 | 1 | 2 | 0 |
| return_abs | 10 | 0 | 0.06846 | 0.08323 | -0.06023 | 14.62059 | 368 | 0.53319 | 5 | 2 | 0 |
| return_abs | 10 | 10 | 0.06066 | 0.07542 | -0.06268 | 14.61679 | 368 | 0.53310 | 5 | 2 | 0 |
| return_abs | 10 | 25 | 0.04906 | 0.06383 | -0.06635 | 14.61109 | 368 | 0.53296 | 5 | 2 | 0 |
| return_abs | 10 | 50 | 0.03004 | 0.04480 | -0.07242 | 14.60160 | 368 | 0.53274 | 5 | 2 | 0 |
| direction_rel | 5 | 0 | 0.02765 | 0.04242 | -0.03707 | 22.89225 | 384 | 0.36979 | 0 | 2 | 0 |
| direction_rel | 5 | 10 | 0.01595 | 0.03072 | -0.04090 | 22.88366 | 384 | 0.36970 | 0 | 2 | 0 |
| direction_rel | 5 | 25 | -0.00134 | 0.01343 | -0.04661 | 22.87079 | 384 | 0.36956 | 0 | 2 | 0 |
| direction_rel | 5 | 50 | -0.02948 | -0.01471 | -0.05658 | 22.84937 | 384 | 0.36933 | 0 | 2 | 0 |
| direction_rel | 10 | 0 | 0.01968 | 0.03444 | -0.05367 | 14.60487 | 368 | 0.53106 | 0 | 2 | 0 |
| direction_rel | 10 | 10 | 0.01225 | 0.02701 | -0.05677 | 14.60104 | 368 | 0.53097 | 0 | 2 | 0 |
| direction_rel | 10 | 25 | 0.00121 | 0.01598 | -0.06141 | 14.59532 | 368 | 0.53083 | 0 | 2 | 0 |
| direction_rel | 10 | 50 | -0.01690 | -0.00213 | -0.06907 | 14.58579 | 368 | 0.53060 | 0 | 2 | 0 |
| rank_pct | 5 | 0 | 0.07188 | 0.08664 | -0.02883 | 22.90766 | 384 | 0.37185 | 2 | 2 | 0 |
| rank_pct | 5 | 10 | 0.05964 | 0.07441 | -0.02979 | 22.89909 | 384 | 0.37176 | 2 | 2 | 0 |
| rank_pct | 5 | 25 | 0.04156 | 0.05632 | -0.03156 | 22.88625 | 384 | 0.37162 | 2 | 2 | 0 |
| rank_pct | 5 | 50 | 0.01214 | 0.02690 | -0.03454 | 22.86488 | 384 | 0.37139 | 2 | 2 | 0 |
| rank_pct | 10 | 0 | 0.10352 | 0.11829 | -0.02794 | 14.62615 | 368 | 0.53233 | 2 | 2 | 0 |
| rank_pct | 10 | 10 | 0.09546 | 0.11023 | -0.02818 | 14.62235 | 368 | 0.53224 | 2 | 2 | 0 |
| rank_pct | 10 | 25 | 0.08348 | 0.09825 | -0.02959 | 14.61665 | 368 | 0.53210 | 2 | 2 | 0 |
| rank_pct | 10 | 50 | 0.06382 | 0.07858 | -0.03195 | 14.60717 | 368 | 0.53187 | 2 | 2 | 0 |
| excursion_balance | 5 | 0 | 0.03156 | 0.04633 | -0.04687 | 22.88482 | 384 | 0.37001 | 1 | 2 | 0 |
| excursion_balance | 5 | 10 | 0.01981 | 0.03458 | -0.04876 | 22.87623 | 384 | 0.36992 | 1 | 2 | 0 |
| excursion_balance | 5 | 25 | 0.00245 | 0.01722 | -0.05183 | 22.86337 | 384 | 0.36978 | 1 | 2 | 0 |
| excursion_balance | 5 | 50 | -0.02580 | -0.01103 | -0.05710 | 22.84197 | 384 | 0.36955 | 1 | 2 | 0 |
| excursion_balance | 10 | 0 | 0.06423 | 0.07900 | -0.06589 | 14.61937 | 368 | 0.53339 | 6 | 2 | 0 |
| excursion_balance | 10 | 10 | 0.05646 | 0.07123 | -0.06672 | 14.61557 | 368 | 0.53330 | 6 | 2 | 0 |
| excursion_balance | 10 | 25 | 0.04491 | 0.05968 | -0.06833 | 14.60987 | 368 | 0.53316 | 6 | 2 | 0 |
| excursion_balance | 10 | 50 | 0.02596 | 0.04072 | -0.07102 | 14.60040 | 368 | 0.53293 | 6 | 2 | 0 |
| trend_tstat | 5 | 0 | 0.07208 | 0.08685 | -0.02489 | 23.03889 | 386 | 0.37338 | 1 | 0 | 0 |
| trend_tstat | 5 | 10 | 0.05978 | 0.07454 | -0.02612 | 23.03029 | 386 | 0.37328 | 1 | 0 | 0 |
| trend_tstat | 5 | 25 | 0.04160 | 0.05637 | -0.02822 | 23.01740 | 386 | 0.37315 | 1 | 0 | 0 |
| trend_tstat | 5 | 50 | 0.01203 | 0.02679 | -0.04087 | 22.99594 | 386 | 0.37292 | 1 | 0 | 0 |
| trend_tstat | 10 | 0 | 0.02225 | 0.03702 | -0.04817 | 14.67935 | 370 | 0.53317 | 0 | 0 | 0 |
| trend_tstat | 10 | 10 | 0.01477 | 0.02954 | -0.04911 | 14.67553 | 370 | 0.53308 | 0 | 0 | 0 |
| trend_tstat | 10 | 25 | 0.00365 | 0.01842 | -0.05051 | 14.66980 | 370 | 0.53294 | 0 | 0 | 0 |
| trend_tstat | 10 | 50 | -0.01459 | 0.00018 | -0.05367 | 14.66027 | 370 | 0.53271 | 0 | 0 | 0 |

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
| excursion_balance | 5 | 0.02888 | 0.05321 | 0.01725 | 0.04258 | 0.06181 | 0.03991 | 0.91622 | -0.01865 |
| excursion_balance | 10 | 0.04353 | 0.05313 | 0.01184 | 0.12004 | 0.08016 | 0.01661 | 0.90587 | -0.01840 |
| trend_tstat | 5 | 0.08328 | 0.07934 | 0.07544 | -0.10125 | 0.04156 | 0.11051 | 0.81975 | -0.03803 |
| trend_tstat | 10 | 0.03750 | 0.03089 | 0.02665 | -0.19637 | -0.02430 | 0.08545 | 0.87384 | -0.04612 |

Les corrélations pooled ci-dessus diagnostiquent les trajectoires et leur lien à la volatilité ; elles ne prouvent aucune causalité. `excursion_balance` est max+min des rendements close futurs sans ancrage artificiel à zéro. Le t-stat futur est calculé sur exactement H closes normalisés base 100 ; les trajectoires parfaitement linéaires atteignent le plafond numérique ±1e6, les plates valent 0.

## 6. Features : gain/impurity et permutation sur validation uniquement

| target | horizon | feature_set | model | feature_id | importance_type | gain_or_impurity | validation_permutation_drop |
| --- | --- | --- | --- | --- | --- | --- | --- |
| direction_rel | 10 | strong | xgb | close.level.q10_delta.w10.v1 | gain | 0.01132 | 0.01718 |
| direction_rel | 5 | strong | rf | low.level.median_delta.w3.v1 | impurity | 0.10213 | 0.01340 |
| excursion_balance | 10 | strong | rf | ohlc.technical.roc_pct.w13.v1 | impurity | 0.00701 | 0.01299 |
| excursion_balance | 10 | strong | rf | close.level.q75_delta.w20.v1 | impurity | 0.03159 | 0.01280 |
| direction_rel | 5 | strong | rf | close.level.q10_delta.w10.v1 | impurity | 0.06957 | 0.01234 |
| excursion_balance | 10 | strong | rf | low.level.q75_delta.w10.v1 | impurity | 0.00898 | 0.00969 |
| trend_tstat | 10 | strong | rf | high.level.range_pct.w60.v1 | impurity | 0.02273 | 0.00910 |
| excursion_balance | 10 | strong | rf | low.level.q25_delta.w20.v1 | impurity | 0.00769 | 0.00909 |
| return_abs | 10 | strong | rf | close.level.range_pct.w60.v1 | impurity | 0.01575 | 0.00851 |
| direction_rel | 10 | strong | xgb | close.level.median_delta.w30.v1 | gain | 0.01108 | 0.00781 |
| rank_pct | 10 | strict | rf | close.level.q90_delta.w60.v1 | impurity | 0.01555 | 0.00692 |
| return_abs | 10 | strong | rf | open.level.max_delta.w30.v1 | impurity | 0.00766 | 0.00684 |
| excursion_balance | 10 | strong | rf | low.level.mean_delta.w5.v1 | impurity | 0.01637 | 0.00671 |
| trend_tstat | 10 | strong | rf | open.level.range_pct.w60.v1 | impurity | 0.01249 | 0.00640 |
| excursion_balance | 10 | strong | rf | high.log.trend_tstat.w5.v1 | impurity | 0.01201 | 0.00613 |
| excursion_balance | 10 | strong | rf | low.level.q90_delta.w10.v1 | impurity | 0.00197 | 0.00597 |
| return_abs | 10 | strong | rf | ohlc.technical.roc_pct.w13.v1 | impurity | 0.00649 | 0.00556 |
| trend_tstat | 10 | strong | rf | close.log.residual_pct.w252.v1 | impurity | 0.04024 | 0.00547 |
| return_abs | 10 | strong | rf | low.level.range_pct.w60.v1 | impurity | 0.00949 | 0.00543 |
| rank_pct | 10 | strict | rf | close.level.median_delta.w30.v1 | impurity | 0.02334 | 0.00499 |
### Stabilité des importances

| model | feature_set | comparison | mean_overlap | median_jaccard | pairs |
| --- | --- | --- | --- | --- | --- |
| rf | strict | horizon | 6.00000 | 0.19430 | 6 |
| rf | strict | target | 6.20000 | 0.17647 | 30 |
| rf | strict | target_and_horizon | 5.83333 | 0.17647 | 30 |
| rf | strong | horizon | 3.83333 | 0.11111 | 6 |
| rf | strong | target | 4.23333 | 0.12698 | 30 |
| rf | strong | target_and_horizon | 3.13333 | 0.08108 | 30 |
| xgb | strict | horizon | 6.00000 | 0.17749 | 6 |
| xgb | strict | target | 6.96667 | 0.23106 | 30 |
| xgb | strict | target_and_horizon | 5.56667 | 0.17647 | 30 |
| xgb | strong | horizon | 4.33333 | 0.14286 | 6 |
| xgb | strong | target | 4.36667 | 0.11111 | 30 |
| xgb | strong | target_and_horizon | 3.66667 | 0.09610 | 30 |

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

**GO exploratoire.** Lecture descriptive : 5/6 gagnants RF/XGB ont un IC test positif ; 12/12 gagnants de validation dépassent l'equal-weight comparable à 50 bp. Cette règle de lecture ne crée ni p-value ni preuve d'alpha.

Avant un cycle plus réaliste : prix/corporate actions certifiés, univers daté, période réellement neuve, calendrier/latence et coûts de liquidité. Aucun résultat de SPEC-007 n'est utilisé. Les nouvelles targets et views sont isolées : le registre historique gelé, le lock et les fichiers SPEC-007 sont byte-identiques.

## 9. Artefacts, reproductibilité et rapport intégral

SHA de base du run : `429f12e984debdd8a1587771a3418bcb51ca43f3` ; dirty lors du run : `True`. Les empreintes exactes des fichiers scientifiques utilisés sont dans summary/model registry, et celles des datasets dans dataset_manifest. Le SHA Git final est indiqué au compte rendu.

Tables locales sous `data/analysis/spec008-model-lab` (hors Git), modèles joblib, registre JSON, métriques, prédictions, déciles, calibration, importances, trajectoires, trades, equity et résumé. `uv run python scripts/model_lab_spec008.py report` régénère ce Markdown à partir des artefacts.

### Toutes les métriques test

| target | horizon | feature_set | model | roc_auc | pr_auc | balanced_accuracy | accuracy | log_loss | brier | calibration_ece | r2 | rmse | mae | mean_ic | median_ic | positive_ic_fraction | top10_lift | n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | strict | naive | 0.50000 | 0.48842 | 0.50000 | 0.48842 | 0.69417 | 0.25051 | 0.02544 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_abs | 5 | strict | linear | 0.53323 | 0.52133 | 0.51989 | 0.51784 | 0.69300 | 0.24987 | 0.02801 | — | — | — | 0.03952 | 0.05677 | 0.69565 | 1.17361 | 3732 |
| direction_abs | 5 | strict | rf | 0.51601 | 0.50255 | 0.51383 | 0.50804 | 0.69378 | 0.25031 | 0.02442 | — | — | — | 0.01130 | 0.01302 | 0.60870 | 1.03717 | 3732 |
| direction_abs | 5 | strict | xgb | 0.51695 | 0.50636 | 0.50934 | 0.50531 | 0.69384 | 0.25035 | 0.02381 | — | — | — | 0.02023 | 0.03742 | 0.60870 | 1.13296 | 3732 |
| direction_abs | 5 | strong | naive | 0.50000 | 0.48842 | 0.50000 | 0.48842 | 0.69417 | 0.25051 | 0.02544 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_abs | 5 | strong | linear | 0.54732 | 0.52905 | 0.54385 | 0.54127 | 0.69327 | 0.24994 | 0.03093 | — | — | — | 0.04657 | 0.05636 | 0.69565 | 1.12792 | 3732 |
| direction_abs | 5 | strong | rf | 0.51693 | 0.50281 | 0.51271 | 0.50776 | 0.69425 | 0.25055 | 0.02633 | — | — | — | 0.02580 | 0.02640 | 0.65217 | 1.04455 | 3732 |
| direction_abs | 5 | strong | xgb | 0.52920 | 0.51729 | 0.51349 | 0.50831 | 0.69299 | 0.24992 | 0.02674 | — | — | — | 0.03995 | 0.03592 | 0.73913 | 1.14560 | 3732 |
| return_abs | 5 | strict | naive_mean | — | — | — | — | — | — | — | -0.00290 | 0.05451 | 0.03792 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | strict | naive_median | — | — | — | — | — | — | — | -0.00244 | 0.05450 | 0.03791 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | strict | linear | — | — | — | — | — | — | — | -0.04453 | 0.05563 | 0.03859 | 0.00383 | 0.00836 | 0.56522 | 1.02470 | 3732 |
| return_abs | 5 | strict | rf | — | — | — | — | — | — | — | -0.02219 | 0.05503 | 0.03799 | 0.04772 | 0.06177 | 0.60870 | 1.20733 | 3732 |
| return_abs | 5 | strict | xgb | — | — | — | — | — | — | — | -0.03449 | 0.05536 | 0.03805 | 0.03226 | 0.03911 | 0.65217 | 1.20457 | 3732 |
| return_abs | 5 | strong | naive_mean | — | — | — | — | — | — | — | -0.00290 | 0.05451 | 0.03792 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | strong | naive_median | — | — | — | — | — | — | — | -0.00244 | 0.05450 | 0.03791 | — | — | — | 1.00000 | 3732 |
| return_abs | 5 | strong | linear | — | — | — | — | — | — | — | -0.07576 | 0.05646 | 0.03891 | 0.01554 | 0.03208 | 0.65217 | 1.07606 | 3732 |
| return_abs | 5 | strong | rf | — | — | — | — | — | — | — | -0.02622 | 0.05514 | 0.03802 | 0.03698 | 0.05185 | 0.65217 | 1.24848 | 3732 |
| return_abs | 5 | strong | xgb | — | — | — | — | — | — | — | -0.04153 | 0.05555 | 0.03811 | 0.03006 | 0.04257 | 0.56522 | 1.17054 | 3732 |
| direction_rel | 5 | strict | naive | 0.50000 | 0.51983 | 0.50000 | 0.48017 | 0.69323 | 0.25004 | 0.02088 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_rel | 5 | strict | linear | 0.52941 | 0.55740 | 0.51873 | 0.51768 | 0.69466 | 0.25069 | 0.02897 | — | — | — | 0.00636 | -0.00852 | 0.47826 | 1.10247 | 3732 |
| direction_rel | 5 | strict | rf | 0.52174 | 0.54715 | 0.51591 | 0.51099 | 0.69262 | 0.24973 | 0.02067 | — | — | — | -0.01168 | 0.00495 | 0.52174 | 1.04149 | 3732 |
| direction_rel | 5 | strict | xgb | 0.52286 | 0.55201 | 0.52456 | 0.52224 | 0.69215 | 0.24951 | 0.01955 | — | — | — | -0.01413 | -0.00254 | 0.47826 | 1.04917 | 3732 |
| direction_rel | 5 | strong | naive | 0.50000 | 0.51983 | 0.50000 | 0.48017 | 0.69323 | 0.25004 | 0.02088 | — | — | — | — | — | — | 1.00000 | 3732 |
| direction_rel | 5 | strong | linear | 0.52557 | 0.54825 | 0.51517 | 0.51608 | 0.69669 | 0.25166 | 0.03876 | — | — | — | 0.00764 | -0.01121 | 0.47826 | 1.00426 | 3732 |
| direction_rel | 5 | strong | rf | 0.52054 | 0.54386 | 0.50807 | 0.50723 | 0.69375 | 0.25028 | 0.02867 | — | — | — | -0.01072 | -0.00361 | 0.47826 | 1.05264 | 3732 |
| direction_rel | 5 | strong | xgb | 0.52577 | 0.54906 | 0.52350 | 0.52224 | 0.69290 | 0.24987 | 0.02052 | — | — | — | -0.01042 | 0.01239 | 0.52174 | 1.03471 | 3732 |
| rank_pct | 5 | strict | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | strict | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | strict | linear | — | — | — | — | — | — | — | -0.01909 | 0.29141 | 0.24994 | 0.04126 | 0.05430 | 0.73913 | 1.00000 | 3732 |
| rank_pct | 5 | strict | rf | — | — | — | — | — | — | — | -0.00153 | 0.28889 | 0.25012 | 0.00535 | 0.01493 | 0.56522 | 1.00000 | 3732 |
| rank_pct | 5 | strict | xgb | — | — | — | — | — | — | — | -0.00224 | 0.28899 | 0.25012 | 0.01691 | 0.04737 | 0.56522 | 1.00000 | 3732 |
| rank_pct | 5 | strong | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | strong | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3732 |
| rank_pct | 5 | strong | linear | — | — | — | — | — | — | — | -0.02943 | 0.29289 | 0.25045 | 0.04798 | 0.03994 | 0.60870 | 1.00000 | 3732 |
| rank_pct | 5 | strong | rf | — | — | — | — | — | — | — | -0.00062 | 0.28876 | 0.24999 | 0.01041 | 0.05618 | 0.65217 | 1.00000 | 3732 |
| rank_pct | 5 | strong | xgb | — | — | — | — | — | — | — | -0.00166 | 0.28891 | 0.25012 | 0.01559 | 0.04040 | 0.56522 | 1.00000 | 3732 |
| excursion_balance | 5 | strict | naive_mean | — | — | — | — | — | — | — | -0.00271 | 0.07270 | 0.04988 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | strict | naive_median | — | — | — | — | — | — | — | -0.00211 | 0.07267 | 0.04986 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | strict | linear | — | — | — | — | — | — | — | -0.04663 | 0.07427 | 0.05100 | 0.01089 | -0.00086 | 0.47826 | 0.95825 | 3732 |
| excursion_balance | 5 | strict | rf | — | — | — | — | — | — | — | -0.02289 | 0.07342 | 0.04993 | 0.03828 | 0.04643 | 0.69565 | 1.11552 | 3732 |
| excursion_balance | 5 | strict | xgb | — | — | — | — | — | — | — | -0.06584 | 0.07495 | 0.05014 | 0.03189 | 0.03894 | 0.60870 | 1.05192 | 3732 |
| excursion_balance | 5 | strong | naive_mean | — | — | — | — | — | — | — | -0.00271 | 0.07270 | 0.04988 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | strong | naive_median | — | — | — | — | — | — | — | -0.00211 | 0.07267 | 0.04986 | — | — | — | 1.00000 | 3732 |
| excursion_balance | 5 | strong | linear | — | — | — | — | — | — | — | -0.07949 | 0.07543 | 0.05118 | 0.01341 | 0.02029 | 0.56522 | 1.00040 | 3732 |
| excursion_balance | 5 | strong | rf | — | — | — | — | — | — | — | -0.04310 | 0.07415 | 0.05011 | 0.01991 | -0.00691 | 0.47826 | 1.11347 | 3732 |
| excursion_balance | 5 | strong | xgb | — | — | — | — | — | — | — | -0.07189 | 0.07516 | 0.05018 | 0.04097 | 0.03183 | 0.56522 | 1.18567 | 3732 |
| trend_tstat | 5 | strict | naive_mean | — | — | — | — | — | — | — | -0.00027 | 4.10197 | 2.63975 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | strict | naive_median | — | — | — | — | — | — | — | -0.00000 | 4.10141 | 2.63981 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | strict | linear | — | — | — | — | — | — | — | -0.00120 | 4.10388 | 2.64806 | 0.03220 | 0.03585 | 0.60870 | 1.12598 | 3732 |
| trend_tstat | 5 | strict | rf | — | — | — | — | — | — | — | 0.00099 | 4.09939 | 2.63822 | 0.01807 | 0.01358 | 0.52174 | 1.00975 | 3732 |
| trend_tstat | 5 | strict | xgb | — | — | — | — | — | — | — | 0.00157 | 4.09819 | 2.63959 | 0.02026 | 0.03563 | 0.56522 | 1.01847 | 3732 |
| trend_tstat | 5 | strong | naive_mean | — | — | — | — | — | — | — | -0.00027 | 4.10197 | 2.63975 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | strong | naive_median | — | — | — | — | — | — | — | -0.00000 | 4.10141 | 2.63981 | — | — | — | 1.00000 | 3732 |
| trend_tstat | 5 | strong | linear | — | — | — | — | — | — | — | 0.00020 | 4.10101 | 2.64288 | 0.02972 | 0.05356 | 0.69565 | 1.07097 | 3732 |
| trend_tstat | 5 | strong | rf | — | — | — | — | — | — | — | 0.00066 | 4.10006 | 2.63913 | 0.01556 | -0.02358 | 0.43478 | 1.05128 | 3732 |
| trend_tstat | 5 | strong | xgb | — | — | — | — | — | — | — | 0.00138 | 4.09858 | 2.63720 | 0.01954 | 0.02416 | 0.52174 | 1.08546 | 3732 |
| direction_abs | 10 | strict | naive | 0.50000 | 0.47743 | 0.50000 | 0.47743 | 0.69383 | 0.25034 | 0.02918 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_abs | 10 | strict | linear | 0.54639 | 0.51982 | 0.53706 | 0.53471 | 0.69502 | 0.24971 | 0.03591 | — | — | — | 0.03082 | 0.03211 | 0.68182 | 1.08993 | 3573 |
| direction_abs | 10 | strict | rf | 0.53828 | 0.51592 | 0.52381 | 0.52144 | 0.69229 | 0.24955 | 0.03457 | — | — | — | 0.05187 | 0.09983 | 0.68182 | 1.14858 | 3573 |
| direction_abs | 10 | strict | xgb | 0.54266 | 0.52298 | 0.53032 | 0.52737 | 0.69090 | 0.24888 | 0.02975 | — | — | — | 0.05534 | 0.07092 | 0.72727 | 1.17765 | 3573 |
| direction_abs | 10 | strong | naive | 0.50000 | 0.47743 | 0.50000 | 0.47743 | 0.69383 | 0.25034 | 0.02918 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_abs | 10 | strong | linear | 0.55206 | 0.52680 | 0.53790 | 0.53471 | 0.69462 | 0.25014 | 0.04488 | — | — | — | 0.03328 | 0.02945 | 0.63636 | 1.08296 | 3573 |
| direction_abs | 10 | strong | rf | 0.53714 | 0.51856 | 0.52153 | 0.51834 | 0.69145 | 0.24915 | 0.03067 | — | — | — | 0.04204 | 0.06659 | 0.68182 | 1.16947 | 3573 |
| direction_abs | 10 | strong | xgb | 0.53687 | 0.52375 | 0.51682 | 0.51270 | 0.69142 | 0.24914 | 0.03134 | — | — | — | 0.03362 | 0.05050 | 0.72727 | 1.18798 | 3573 |
| return_abs | 10 | strict | naive_mean | — | — | — | — | — | — | — | -0.00321 | 0.07782 | 0.05576 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | strict | naive_median | — | — | — | — | — | — | — | -0.00176 | 0.07776 | 0.05568 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | strict | linear | — | — | — | — | — | — | — | -0.02653 | 0.07871 | 0.05626 | 0.01769 | 0.02063 | 0.72727 | 1.07735 | 3573 |
| return_abs | 10 | strict | rf | — | — | — | — | — | — | — | -0.02308 | 0.07858 | 0.05584 | 0.05125 | 0.01753 | 0.59091 | 1.22538 | 3573 |
| return_abs | 10 | strict | xgb | — | — | — | — | — | — | — | -0.01785 | 0.07838 | 0.05574 | 0.04590 | 0.02654 | 0.63636 | 1.23178 | 3573 |
| return_abs | 10 | strong | naive_mean | — | — | — | — | — | — | — | -0.00321 | 0.07782 | 0.05576 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | strong | naive_median | — | — | — | — | — | — | — | -0.00176 | 0.07776 | 0.05568 | — | — | — | 1.00000 | 3573 |
| return_abs | 10 | strong | linear | — | — | — | — | — | — | — | -0.06078 | 0.08002 | 0.05654 | 0.01991 | 0.00435 | 0.50000 | 1.05885 | 3573 |
| return_abs | 10 | strong | rf | — | — | — | — | — | — | — | -0.02281 | 0.07857 | 0.05583 | 0.05847 | 0.01270 | 0.59091 | 1.18554 | 3573 |
| return_abs | 10 | strong | xgb | — | — | — | — | — | — | — | -0.04116 | 0.07927 | 0.05596 | 0.04460 | 0.02954 | 0.72727 | 1.11788 | 3573 |
| direction_rel | 10 | strict | naive | 0.50000 | 0.51469 | 0.50000 | 0.48531 | 0.69321 | 0.25003 | 0.01578 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_rel | 10 | strict | linear | 0.53238 | 0.55304 | 0.52717 | 0.52673 | 0.69686 | 0.24992 | 0.01801 | — | — | — | 0.03255 | 0.03898 | 0.63636 | 1.05760 | 3573 |
| direction_rel | 10 | strict | rf | 0.53827 | 0.56067 | 0.52291 | 0.51945 | 0.68978 | 0.24834 | 0.01613 | — | — | — | 0.03601 | 0.05800 | 0.59091 | 1.04220 | 3573 |
| direction_rel | 10 | strict | xgb | 0.53838 | 0.56315 | 0.52874 | 0.52645 | 0.68970 | 0.24830 | 0.01547 | — | — | — | 0.03271 | 0.01329 | 0.54545 | 1.03048 | 3573 |
| direction_rel | 10 | strong | naive | 0.50000 | 0.51469 | 0.50000 | 0.48531 | 0.69321 | 0.25003 | 0.01578 | — | — | — | — | — | — | 1.00000 | 3573 |
| direction_rel | 10 | strong | linear | 0.52647 | 0.54328 | 0.51645 | 0.51693 | 0.70025 | 0.25150 | 0.03485 | — | — | — | 0.02837 | 0.01682 | 0.54545 | 1.06578 | 3573 |
| direction_rel | 10 | strong | rf | 0.53445 | 0.55648 | 0.52478 | 0.52029 | 0.69034 | 0.24861 | 0.01721 | — | — | — | 0.02071 | 0.03776 | 0.54545 | 1.03056 | 3573 |
| direction_rel | 10 | strong | xgb | 0.53507 | 0.56260 | 0.52064 | 0.51833 | 0.68960 | 0.24826 | 0.01547 | — | — | — | 0.02014 | 0.00813 | 0.50000 | 1.02406 | 3573 |
| rank_pct | 10 | strict | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | strict | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | strict | linear | — | — | — | — | — | — | — | -0.00172 | 0.28892 | 0.24954 | 0.04701 | 0.05547 | 0.72727 | 1.00000 | 3573 |
| rank_pct | 10 | strict | rf | — | — | — | — | — | — | — | 0.00288 | 0.28825 | 0.24946 | 0.05251 | 0.02150 | 0.59091 | 1.00000 | 3573 |
| rank_pct | 10 | strict | xgb | — | — | — | — | — | — | — | 0.00337 | 0.28818 | 0.24938 | 0.04999 | 0.04480 | 0.63636 | 1.00000 | 3573 |
| rank_pct | 10 | strong | naive_mean | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | strong | naive_median | — | — | — | — | — | — | — | -0.00000 | 0.28867 | 0.25000 | — | — | — | 1.00000 | 3573 |
| rank_pct | 10 | strong | linear | — | — | — | — | — | — | — | -0.00642 | 0.28959 | 0.24966 | 0.06008 | 0.05830 | 0.77273 | 1.00000 | 3573 |
| rank_pct | 10 | strong | rf | — | — | — | — | — | — | — | 0.00347 | 0.28817 | 0.24947 | 0.04686 | 0.03119 | 0.59091 | 1.00000 | 3573 |
| rank_pct | 10 | strong | xgb | — | — | — | — | — | — | — | 0.00395 | 0.28810 | 0.24944 | 0.04384 | 0.06854 | 0.63636 | 1.00000 | 3573 |
| excursion_balance | 10 | strict | naive_mean | — | — | — | — | — | — | — | -0.00151 | 0.09546 | 0.06820 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | strict | naive_median | — | — | — | — | — | — | — | -0.00012 | 0.09539 | 0.06814 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | strict | linear | — | — | — | — | — | — | — | -0.05396 | 0.09792 | 0.06922 | 0.01503 | 0.01897 | 0.63636 | 1.07940 | 3573 |
| excursion_balance | 10 | strict | rf | — | — | — | — | — | — | — | -0.04225 | 0.09738 | 0.06859 | 0.02122 | 0.04455 | 0.59091 | 1.15089 | 3573 |
| excursion_balance | 10 | strict | xgb | — | — | — | — | — | — | — | -0.06938 | 0.09864 | 0.06870 | -0.00050 | -0.02517 | 0.45455 | 1.03667 | 3573 |
| excursion_balance | 10 | strong | naive_mean | — | — | — | — | — | — | — | -0.00151 | 0.09546 | 0.06820 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | strong | naive_median | — | — | — | — | — | — | — | -0.00012 | 0.09539 | 0.06814 | — | — | — | 1.00000 | 3573 |
| excursion_balance | 10 | strong | linear | — | — | — | — | — | — | — | -0.10127 | 0.10010 | 0.06976 | 0.01438 | 0.00425 | 0.54545 | 1.03693 | 3573 |
| excursion_balance | 10 | strong | rf | — | — | — | — | — | — | — | -0.04573 | 0.09754 | 0.06855 | 0.04858 | 0.03464 | 0.68182 | 1.13582 | 3573 |
| excursion_balance | 10 | strong | xgb | — | — | — | — | — | — | — | -0.08375 | 0.09930 | 0.06880 | 0.02333 | 0.01073 | 0.59091 | 1.02356 | 3573 |
| trend_tstat | 10 | strict | naive_mean | — | — | — | — | — | — | — | -0.00181 | 4.38574 | 3.35749 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | strict | naive_median | — | — | — | — | — | — | — | -0.00086 | 4.38365 | 3.35520 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | strict | linear | — | — | — | — | — | — | — | -0.01413 | 4.41261 | 3.36962 | 0.03094 | 0.04674 | 0.68182 | 1.05321 | 3573 |
| trend_tstat | 10 | strict | rf | — | — | — | — | — | — | — | -0.00516 | 4.39307 | 3.36793 | 0.02383 | 0.05921 | 0.54545 | 1.00553 | 3573 |
| trend_tstat | 10 | strict | xgb | — | — | — | — | — | — | — | -0.00336 | 4.38912 | 3.36380 | 0.02776 | 0.03678 | 0.54545 | 1.07850 | 3573 |
| trend_tstat | 10 | strong | naive_mean | — | — | — | — | — | — | — | -0.00181 | 4.38574 | 3.35749 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | strong | naive_median | — | — | — | — | — | — | — | -0.00086 | 4.38365 | 3.35520 | — | — | — | 1.00000 | 3573 |
| trend_tstat | 10 | strong | linear | — | — | — | — | — | — | — | -0.00410 | 4.39074 | 3.37112 | 0.03888 | 0.05652 | 0.63636 | 1.02240 | 3573 |
| trend_tstat | 10 | strong | rf | — | — | — | — | — | — | — | -0.00092 | 4.38379 | 3.36117 | 0.02298 | 0.03571 | 0.54545 | 0.97305 | 3573 |
| trend_tstat | 10 | strong | xgb | — | — | — | — | — | — | — | -0.00243 | 4.38708 | 3.36297 | 0.02809 | 0.00910 | 0.50000 | 1.04115 | 3573 |
### Couverture par tâche

| target | horizon | feature_set | split | eligible_rows | usable_labels | neutral_n | future_warning_n | uninterpretable_n | feature_missing_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | strict | train | 9068 | 8940 | 127 | 6 | 0 | 0.00173 |
| direction_abs | 5 | strict | validation | 4187 | 4120 | 65 | 6 | 2 | 0.00011 |
| direction_abs | 5 | strict | test | 3732 | 3671 | 61 | 7 | 0 | 0.00000 |
| direction_abs | 5 | strong | train | 9068 | 8940 | 127 | 6 | 0 | 0.00183 |
| direction_abs | 5 | strong | validation | 4187 | 4120 | 65 | 6 | 2 | 0.00029 |
| direction_abs | 5 | strong | test | 3732 | 3671 | 61 | 7 | 0 | 0.00005 |
| return_abs | 5 | strict | train | 9068 | 9067 | 0 | 6 | 0 | 0.00173 |
| return_abs | 5 | strict | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00011 |
| return_abs | 5 | strict | test | 3732 | 3732 | 0 | 7 | 0 | 0.00000 |
| return_abs | 5 | strong | train | 9068 | 9067 | 0 | 6 | 0 | 0.00183 |
| return_abs | 5 | strong | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00029 |
| return_abs | 5 | strong | test | 3732 | 3732 | 0 | 7 | 0 | 0.00005 |
| direction_rel | 5 | strict | train | 9068 | 9067 | 0 | 6 | 0 | 0.00173 |
| direction_rel | 5 | strict | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00011 |
| direction_rel | 5 | strict | test | 3732 | 3732 | 0 | 7 | 0 | 0.00000 |
| direction_rel | 5 | strong | train | 9068 | 9067 | 0 | 6 | 0 | 0.00183 |
| direction_rel | 5 | strong | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00029 |
| direction_rel | 5 | strong | test | 3732 | 3732 | 0 | 7 | 0 | 0.00005 |
| rank_pct | 5 | strict | train | 9068 | 9067 | 0 | 6 | 0 | 0.00173 |
| rank_pct | 5 | strict | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00011 |
| rank_pct | 5 | strict | test | 3732 | 3732 | 0 | 7 | 0 | 0.00000 |
| rank_pct | 5 | strong | train | 9068 | 9067 | 0 | 6 | 0 | 0.00183 |
| rank_pct | 5 | strong | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00029 |
| rank_pct | 5 | strong | test | 3732 | 3732 | 0 | 7 | 0 | 0.00005 |
| excursion_balance | 5 | strict | train | 9068 | 9067 | 0 | 6 | 0 | 0.00173 |
| excursion_balance | 5 | strict | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00011 |
| excursion_balance | 5 | strict | test | 3732 | 3732 | 0 | 7 | 0 | 0.00000 |
| excursion_balance | 5 | strong | train | 9068 | 9067 | 0 | 6 | 0 | 0.00183 |
| excursion_balance | 5 | strong | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00029 |
| excursion_balance | 5 | strong | test | 3732 | 3732 | 0 | 7 | 0 | 0.00005 |
| trend_tstat | 5 | strict | train | 9068 | 9067 | 0 | 6 | 0 | 0.00173 |
| trend_tstat | 5 | strict | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00011 |
| trend_tstat | 5 | strict | test | 3732 | 3732 | 0 | 7 | 0 | 0.00000 |
| trend_tstat | 5 | strong | train | 9068 | 9067 | 0 | 6 | 0 | 0.00183 |
| trend_tstat | 5 | strong | validation | 4187 | 4185 | 0 | 6 | 2 | 0.00029 |
| trend_tstat | 5 | strong | test | 3732 | 3732 | 0 | 7 | 0 | 0.00005 |
| direction_abs | 10 | strict | train | 8890 | 8811 | 78 | 12 | 0 | 0.00176 |
| direction_abs | 10 | strict | validation | 4017 | 3974 | 39 | 12 | 4 | 0.00011 |
| direction_abs | 10 | strict | test | 3573 | 3544 | 29 | 11 | 0 | 0.00000 |
| direction_abs | 10 | strong | train | 8890 | 8811 | 78 | 12 | 0 | 0.00185 |
| direction_abs | 10 | strong | validation | 4017 | 3974 | 39 | 12 | 4 | 0.00030 |
| direction_abs | 10 | strong | test | 3573 | 3544 | 29 | 11 | 0 | 0.00005 |
| return_abs | 10 | strict | train | 8890 | 8889 | 0 | 12 | 0 | 0.00176 |
| return_abs | 10 | strict | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00011 |
| return_abs | 10 | strict | test | 3573 | 3573 | 0 | 11 | 0 | 0.00000 |
| return_abs | 10 | strong | train | 8890 | 8889 | 0 | 12 | 0 | 0.00185 |
| return_abs | 10 | strong | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00030 |
| return_abs | 10 | strong | test | 3573 | 3573 | 0 | 11 | 0 | 0.00005 |
| direction_rel | 10 | strict | train | 8890 | 8889 | 0 | 12 | 0 | 0.00176 |
| direction_rel | 10 | strict | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00011 |
| direction_rel | 10 | strict | test | 3573 | 3573 | 0 | 11 | 0 | 0.00000 |
| direction_rel | 10 | strong | train | 8890 | 8889 | 0 | 12 | 0 | 0.00185 |
| direction_rel | 10 | strong | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00030 |
| direction_rel | 10 | strong | test | 3573 | 3573 | 0 | 11 | 0 | 0.00005 |
| rank_pct | 10 | strict | train | 8890 | 8889 | 0 | 12 | 0 | 0.00176 |
| rank_pct | 10 | strict | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00011 |
| rank_pct | 10 | strict | test | 3573 | 3573 | 0 | 11 | 0 | 0.00000 |
| rank_pct | 10 | strong | train | 8890 | 8889 | 0 | 12 | 0 | 0.00185 |
| rank_pct | 10 | strong | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00030 |
| rank_pct | 10 | strong | test | 3573 | 3573 | 0 | 11 | 0 | 0.00005 |
| excursion_balance | 10 | strict | train | 8890 | 8889 | 0 | 12 | 0 | 0.00176 |
| excursion_balance | 10 | strict | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00011 |
| excursion_balance | 10 | strict | test | 3573 | 3573 | 0 | 11 | 0 | 0.00000 |
| excursion_balance | 10 | strong | train | 8890 | 8889 | 0 | 12 | 0 | 0.00185 |
| excursion_balance | 10 | strong | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00030 |
| excursion_balance | 10 | strong | test | 3573 | 3573 | 0 | 11 | 0 | 0.00005 |
| trend_tstat | 10 | strict | train | 8890 | 8889 | 0 | 12 | 0 | 0.00176 |
| trend_tstat | 10 | strict | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00011 |
| trend_tstat | 10 | strict | test | 3573 | 3573 | 0 | 11 | 0 | 0.00000 |
| trend_tstat | 10 | strong | train | 8890 | 8889 | 0 | 12 | 0 | 0.00185 |
| trend_tstat | 10 | strong | validation | 4017 | 4013 | 0 | 12 | 4 | 0.00030 |
| trend_tstat | 10 | strong | test | 3573 | 3573 | 0 | 11 | 0 | 0.00005 |
