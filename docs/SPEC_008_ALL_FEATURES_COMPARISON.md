# SPEC-008 — toutes les variables versus Strict/Strong

**Development backtest — not independent confirmation.**

Toutes les 1 048 entrées du registre sont fournies ensemble aux modèles. Aucun classement univarié ni filtre d'outcome ne restreint ce set. Les fenêtres 504, constantes et aliases sont conservés. Les formules restent celles du registre existant.

Même univers, mêmes labels, splits/purges, grilles, seed et frais. Les modèles indiqués sont choisis exclusivement sur S1 2025 dans chaque set. Le set complet est une nouvelle expérience sur des périodes déjà explorées.

## Comparaison des 36 gagnants de validation

| target | horizon | feature_set | model | validation_metric | roc_auc | r2 | mean_ic | median_ic | positive_ic_fraction | top10_lift | return_0bp | return_10bp | return_25bp | return_50bp | turnover | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | all | rf | 0.50360 | 0.53688 | — | 0.06254 | 0.06110 | 0.69565 | 1.10247 | 0.05455 | 0.04253 | 0.02477 | -0.00414 | 22.89352 | -0.02676 |
| direction_abs | 5 | strict | naive | 0.50000 | 0.50000 | — | — | — | — | 1.00000 | 0.03199 | 0.02018 | 0.00272 | -0.02568 | 22.99829 | -0.05251 |
| direction_abs | 5 | strong | linear | 0.51657 | 0.54732 | — | 0.04657 | 0.05636 | 0.69565 | 1.12792 | 0.07044 | 0.05822 | 0.04017 | 0.01079 | 22.89599 | -0.03427 |
| direction_abs | 10 | all | naive | 0.50000 | 0.50000 | — | — | — | — | 1.00000 | 0.02596 | 0.01845 | 0.00729 | -0.01104 | 14.67754 | -0.06039 |
| direction_abs | 10 | strict | linear | 0.52800 | 0.54639 | — | 0.03082 | 0.03211 | 0.68182 | 1.08993 | 0.02140 | 0.01391 | 0.00279 | -0.01547 | 14.68037 | -0.06994 |
| direction_abs | 10 | strong | xgb | 0.51398 | 0.53687 | — | 0.03362 | 0.05050 | 0.72727 | 1.18798 | 0.05841 | 0.05065 | 0.03912 | 0.02021 | 14.68606 | -0.04579 |
| direction_rel | 5 | all | rf | 0.55713 | 0.54949 | — | 0.01100 | 0.01928 | 0.52174 | 1.07045 | 0.03958 | 0.02774 | 0.01024 | -0.01824 | 22.87814 | -0.03910 |
| direction_rel | 5 | strict | rf | 0.53591 | 0.52174 | — | -0.01168 | 0.00495 | 0.52174 | 1.04149 | 0.05096 | 0.03899 | 0.02129 | -0.00752 | 22.88939 | -0.04063 |
| direction_rel | 5 | strong | rf | 0.54571 | 0.52054 | — | -0.01072 | -0.00361 | 0.47826 | 1.05264 | 0.02765 | 0.01595 | -0.00134 | -0.02948 | 22.87079 | -0.04661 |
| direction_rel | 10 | all | rf | 0.53690 | 0.55637 | — | 0.05204 | -0.00352 | 0.50000 | 1.13923 | 0.07993 | 0.07200 | 0.06022 | 0.04089 | 14.68546 | -0.05227 |
| direction_rel | 10 | strict | xgb | 0.50825 | 0.53838 | — | 0.03271 | 0.01329 | 0.54545 | 1.03048 | 0.05739 | 0.04967 | 0.03822 | 0.01941 | 14.60688 | -0.03866 |
| direction_rel | 10 | strong | xgb | 0.52216 | 0.53507 | — | 0.02014 | 0.00813 | 0.50000 | 1.02406 | 0.01968 | 0.01225 | 0.00121 | -0.01690 | 14.59532 | -0.06141 |
| excursion_balance | 5 | all | xgb | 0.03336 | — | -0.04953 | 0.02443 | 0.03818 | 0.56522 | 1.17446 | 0.08369 | 0.07131 | 0.05303 | 0.02326 | 22.89052 | -0.06832 |
| excursion_balance | 5 | strict | rf | 0.03011 | — | -0.02289 | 0.03828 | 0.04643 | 0.69565 | 1.11552 | 0.13193 | 0.11899 | 0.09987 | 0.06874 | 22.92691 | -0.05373 |
| excursion_balance | 5 | strong | linear | 0.03386 | — | -0.07949 | 0.01341 | 0.02029 | 0.56522 | 1.00040 | 0.03156 | 0.01981 | 0.00245 | -0.02580 | 22.86337 | -0.05183 |
| excursion_balance | 10 | all | linear | 0.02615 | — | -0.26115 | 0.00350 | 0.01484 | 0.54545 | 1.13116 | 0.00102 | -0.00626 | -0.01707 | -0.03482 | 14.58292 | -0.05691 |
| excursion_balance | 10 | strict | rf | 0.03098 | — | -0.04225 | 0.02122 | 0.04455 | 0.59091 | 1.15089 | 0.10794 | 0.09984 | 0.08780 | 0.06805 | 14.62416 | -0.04709 |
| excursion_balance | 10 | strong | rf | 0.03527 | — | -0.04573 | 0.04858 | 0.03464 | 0.68182 | 1.13582 | 0.06423 | 0.05646 | 0.04491 | 0.02596 | 14.60987 | -0.06833 |
| rank_pct | 5 | all | rf | 0.07111 | — | 0.00138 | 0.04400 | 0.06169 | 0.73913 | 1.00000 | 0.09488 | 0.08238 | 0.06391 | 0.03385 | 22.89889 | -0.02610 |
| rank_pct | 5 | strict | linear | 0.04141 | — | -0.01909 | 0.04126 | 0.05430 | 0.73913 | 1.00000 | 0.07522 | 0.06295 | 0.04483 | 0.01533 | 22.88620 | -0.03061 |
| rank_pct | 5 | strong | linear | 0.06652 | — | -0.02943 | 0.04798 | 0.03994 | 0.60870 | 1.00000 | 0.07188 | 0.05964 | 0.04156 | 0.01214 | 22.88625 | -0.03156 |
| rank_pct | 10 | all | rf | 0.06287 | — | 0.00397 | 0.05942 | 0.04657 | 0.68182 | 1.00000 | 0.08242 | 0.07450 | 0.06274 | 0.04343 | 14.64694 | -0.03046 |
| rank_pct | 10 | strict | rf | 0.01284 | — | 0.00288 | 0.05251 | 0.02150 | 0.59091 | 1.00000 | 0.10352 | 0.09546 | 0.08348 | 0.06382 | 14.61665 | -0.02959 |
| rank_pct | 10 | strong | rf | 0.01106 | — | 0.00347 | 0.04686 | 0.03119 | 0.59091 | 1.00000 | 0.12319 | 0.11498 | 0.10278 | 0.08276 | 14.62491 | -0.03427 |
| return_abs | 5 | all | rf | 0.05388 | — | -0.02416 | 0.02045 | 0.00195 | 0.56522 | 1.11109 | 0.01154 | 0.00002 | -0.01700 | -0.04470 | 22.85111 | -0.05632 |
| return_abs | 5 | strict | rf | 0.03118 | — | -0.02219 | 0.04772 | 0.06177 | 0.60870 | 1.20733 | 0.13219 | 0.11925 | 0.10012 | 0.06899 | 22.93292 | -0.04575 |
| return_abs | 5 | strong | linear | 0.03946 | — | -0.07576 | 0.01554 | 0.03208 | 0.65217 | 1.07606 | 0.06834 | 0.05616 | 0.03815 | 0.00885 | 22.88096 | -0.04617 |
| return_abs | 10 | all | rf | 0.03137 | — | -0.01920 | 0.03862 | 0.04120 | 0.68182 | 1.24448 | 0.07439 | 0.06654 | 0.05488 | 0.03574 | 14.60204 | -0.06753 |
| return_abs | 10 | strict | rf | 0.02289 | — | -0.02308 | 0.05125 | 0.01753 | 0.59091 | 1.22538 | 0.14317 | 0.13480 | 0.12236 | 0.10194 | 14.63316 | -0.04465 |
| return_abs | 10 | strong | rf | 0.02751 | — | -0.02281 | 0.05847 | 0.01270 | 0.59091 | 1.18554 | 0.06846 | 0.06066 | 0.04906 | 0.03004 | 14.61109 | -0.06635 |
| trend_tstat | 5 | all | xgb | 0.08187 | — | 0.00044 | 0.06606 | 0.08483 | 0.69565 | 1.11722 | 0.05102 | 0.03898 | 0.02119 | -0.00776 | 23.00480 | -0.03869 |
| trend_tstat | 5 | strict | linear | 0.03316 | — | -0.00120 | 0.03220 | 0.03585 | 0.60870 | 1.12598 | 0.08227 | 0.06986 | 0.05152 | 0.02167 | 23.02160 | -0.02607 |
| trend_tstat | 5 | strong | linear | 0.03618 | — | 0.00020 | 0.02972 | 0.05356 | 0.69565 | 1.07097 | 0.07208 | 0.05978 | 0.04160 | 0.01203 | 23.01740 | -0.02822 |
| trend_tstat | 10 | all | xgb | 0.03054 | — | 0.00918 | 0.09148 | 0.12005 | 0.63636 | 1.07182 | 0.03761 | 0.03001 | 0.01871 | 0.00017 | 14.67602 | -0.04277 |
| trend_tstat | 10 | strict | rf | 0.03517 | — | -0.00516 | 0.02383 | 0.05921 | 0.54545 | 1.00553 | -0.00176 | -0.00906 | -0.01990 | -0.03770 | 14.66470 | -0.05641 |
| trend_tstat | 10 | strong | rf | 0.03800 | — | -0.00092 | 0.02298 | 0.03571 | 0.54545 | 0.97305 | 0.02225 | 0.01477 | 0.00365 | -0.01459 | 14.66980 | -0.05051 |
## Écart au meilleur baseline Strict/Strong choisi en validation

| target | horizon | model_all | model_baseline | feature_set_baseline | delta_roc_auc | delta_r2 | delta_mean_ic | delta_return_25bp | delta_return_50bp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | rf | linear | strong | -0.01044 | — | 0.01597 | -0.01540 | -0.01493 |
| direction_abs | 10 | naive | linear | strict | -0.04639 | — | — | 0.00450 | 0.00443 |
| direction_rel | 5 | rf | rf | strong | 0.02895 | — | 0.02171 | 0.01158 | 0.01124 |
| direction_rel | 10 | rf | xgb | strong | 0.02130 | — | 0.03190 | 0.05900 | 0.05778 |
| excursion_balance | 5 | xgb | linear | strong | — | 0.02996 | 0.01103 | 0.05057 | 0.04906 |
| excursion_balance | 10 | linear | rf | strong | — | -0.21542 | -0.04508 | -0.06198 | -0.06078 |
| rank_pct | 5 | rf | linear | strong | — | 0.03081 | -0.00398 | 0.02235 | 0.02171 |
| rank_pct | 10 | rf | rf | strict | — | 0.00109 | 0.00691 | -0.02074 | -0.02039 |
| return_abs | 5 | rf | linear | strong | — | 0.05160 | 0.00491 | -0.05515 | -0.05355 |
| return_abs | 10 | rf | rf | strong | — | 0.00361 | -0.01985 | 0.00581 | 0.00570 |
| trend_tstat | 5 | xgb | linear | strong | — | 0.00024 | 0.03633 | -0.02041 | -0.01979 |
| trend_tstat | 10 | xgb | rf | strong | — | 0.01010 | 0.06849 | 0.01505 | 0.01475 |
Les écarts sont all moins baseline. Ils ne sont pas des tests de significativité. Le fichier `comparison_matched_models.parquet` compare aussi chaque type de modèle avec le même type Strict et Strong.

## Disponibilité du registre complet

| horizon | split | features | entirely_missing | mean_missing_fraction |
| --- | --- | --- | --- | --- |
| 5 | test | 1048 | 6 | 0.00723 |
| 5 | train | 1048 | 6 | 0.08952 |
| 5 | validation | 1048 | 6 | 0.00974 |
| 10 | test | 1048 | 6 | 0.00727 |
| 10 | train | 1048 | 6 | 0.09110 |
| 10 | validation | 1048 | 6 | 0.00981 |
Une colonne entièrement absente de train reste dans les IDs. L'imputer conserve cette colonne avec une valeur constante (0, comportement explicite de keep_empty_features) ; les indicateurs d'absence sont appris à train. Les valeurs réellement observées en aval ne servent jamais à estimer une médiane train. XGBoost conserve les NaN natifs. Les constantes et redondances peuvent pénaliser l'ajout du registre complet.

## Livrables

[Résultats du set complet](SPEC_008_ALL_FEATURES_RESULTS.md) · [Résultats initiaux](SPEC_008_RESULTS.md) · [Contrat de l'extension](SPEC_008_ALL_FEATURES.md).

