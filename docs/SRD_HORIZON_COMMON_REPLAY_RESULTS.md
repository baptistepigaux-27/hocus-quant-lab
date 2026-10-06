# SRD — replay commun H1/H2/H3/H5/H10

**6 octobre 2026 · version 1 · replay de développement.**

## A. Question et résultat de lecture

Comparer les scores appris et les détentions en neutralisant dates, cohortes, coûts et budget. Aucun refit, tuning, changement de score ou exclusion d'événement futur. Les résultats 2026 restent du développement ; ils ne prolongent pas SPEC-007.

**22 dates**, **10 modèles**, **360 replays de stratégies** et **15 références univers**. Analyse B commune principale ; analyse A native complète. Le top 3 % est principal et le top 10 % un diagnostic.

## B. Contrat et périmètre

Le [contrat de replay](SRD_HORIZON_COMPARISON_CONTRACT.md) est complété par la consigne utilisateur : **deux compartiments**, sorties 1/2/3/5/10 avec sortie ≥ horizon appris. Le capital initial vaut 1, le budget d'entrée est min(cash, NAV précédente / 2), réparti entre ceil(top × N) titres. Actions fractionnaires, aucun arrondi de lots, pas de levier ni de VAD. Cash rémunéré à zéro.

Les cutoffs vont du **2026-01-02 au 2026-06-12**. Ils sont identiques à l'inventaire déjà figé ; décisions suivies jusqu'au 31 juillet 2026, avec cash après les liquidations. Leur liste est scellée dans la [configuration](../configs/experiments/srd_horizon_common_replay_v1.json).

## C. Cohortes

L'admission utilise les registres `eligible_at_T` et les features, sans demander un label futur disponible. Les registres et features sont byte-identiques entre expériences. Les 22 dates donnent **159 à 164 titres**, **3 573 lignes par modèle**. Univers natif = univers commun à chaque cutoff ; perte de couverture **0 %**, aucun titre exclu par l'intersection. Les deux analyses produisent ainsi les mêmes résultats.

| cutoff | native_n | common_n | coverage_loss |
| --- | --- | --- | --- |
| 2026-01-02 | 164 | 164 | 0.00000 |
| 2026-01-09 | 164 | 164 | 0.00000 |
| 2026-01-16 | 164 | 164 | 0.00000 |
| 2026-01-23 | 164 | 164 | 0.00000 |
| 2026-01-30 | 164 | 164 | 0.00000 |
| 2026-02-06 | 164 | 164 | 0.00000 |
| 2026-02-13 | 164 | 164 | 0.00000 |
| 2026-02-20 | 164 | 164 | 0.00000 |
| 2026-02-27 | 164 | 164 | 0.00000 |
| 2026-03-06 | 163 | 163 | 0.00000 |
| 2026-03-13 | 163 | 163 | 0.00000 |
| 2026-03-20 | 163 | 163 | 0.00000 |
| 2026-03-27 | 162 | 162 | 0.00000 |
| 2026-04-10 | 162 | 162 | 0.00000 |
| 2026-04-17 | 162 | 162 | 0.00000 |
| 2026-04-24 | 162 | 162 | 0.00000 |
| 2026-05-08 | 162 | 162 | 0.00000 |
| 2026-05-15 | 161 | 161 | 0.00000 |
| 2026-05-22 | 160 | 160 | 0.00000 |
| 2026-05-29 | 159 | 159 | 0.00000 |
| 2026-06-05 | 159 | 159 | 0.00000 |
| 2026-06-12 | 159 | 159 | 0.00000 |

## D. Modèles et scores préservés

| target | horizon | model | model_id | validation_metric |
| --- | --- | --- | --- | --- |
| rank_pct | 1 | rf | rank_pct-h1-all-rf-0df3b166dc71 | 0.04474 |
| rank_pct | 2 | rf | rank_pct-h2-all-rf-90eeb04f8762 | 0.01209 |
| rank_pct | 3 | rf | rank_pct-h3-all-rf-6ef7625d42fd | 0.03557 |
| rank_pct | 5 | rf | rank_pct-h5-all-rf-3c5fa028d3f4 | 0.07111 |
| rank_pct | 10 | rf | rank_pct-h10-all-rf-bedd78069821 | 0.06287 |
| return_abs | 1 | xgb | return_abs-h1-all-xgb-2cb02f543be3 | -0.00180 |
| return_abs | 2 | rf | return_abs-h2-all-rf-06dc2b7ed8ec | 0.01601 |
| return_abs | 3 | xgb | return_abs-h3-all-xgb-d139323e99e0 | 0.01441 |
| return_abs | 5 | rf | return_abs-h5-all-rf-1273ae260f86 | 0.05388 |
| return_abs | 10 | rf | return_abs-h10-all-rf-1bbd2af1ad50 | 0.03137 |

Les **35 730 scores** originaux sont conservés à l'identique. Les dix artefacts sauvegardés sont chargés et leurs prédictions rapprochées des exports (tolérance 1e-12). Aucun score supplémentaire n'a été nécessaire. Les SHAs des modèles, features, sources, registries, scores et code sont conservés. Les directions constantes H1/H2/H3 sont exclues de cette comparaison des deux targets prédictives.

## E. Exécution et suspensions

Achat à l'open de la première séance de la grille commune strictement après T ; si le titre n'a pas d'open, aucune entrée ultérieure ni substitution par un close. Sortie au H-ième close, **entrée incluse** : H1 = intraday. Un close absent retarde la sortie jusqu'au premier close source réellement disponible. Les prix indicatifs de suspension ne sont pas des fills. Nacon reste une perte et immobilise du capital.

La grille observée des actions est rapprochée des dates CAC AllShares du snapshot ([] dates actions seules). Elle n'est pas présentée comme un calendrier de place certifié indépendant. Les features actions conservent leur borne historique ; le replay est exécuté après 00:00 UTC le lendemain de T. Les targets relatives et prévisions d'indices ne sont pas utilisées ici.

## F. Frais

0/25/45 bp **aller-retour**, moitié sur le nominal d'achat et moitié sur le nominal de vente. Shares = allocation / (open × (1 + cost/20000)). Les coûts modifient donc cash et tailles, et ne sont pas simplement soustraits de la performance finale. Les 45 bp sont un forfait de scénario ; fiscalité par titre, minimums, spread et impact ne sont pas calculés séparément.

## G. Horizons natifs — net 45 bp

Rendement, DD, capital actif, hit rate et parts de contribution en pourcentage ; turnover en multiples de NAV. Les contributions peuvent dépasser 100 % du gain net lorsque d'autres trades le compensent.

| target | score_horizon | model | cumulative_return | max_drawdown | average_active_session_capital | turnover | hit_rate | top_5_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | rf | 0.65983 | -1.83773 | 7.46619 | 22.00708 | 46.36364 | 664.53035 |
| rank_pct | 2 | rf | 0.75814 | -3.48164 | 14.64655 | 21.58692 | 48.14815 | 741.44369 |
| rank_pct | 3 | rf | 4.19170 | -5.84188 | 22.38718 | 22.04809 | 51.81818 | 145.69239 |
| rank_pct | 5 | rf | 12.85319 | -3.37065 | 36.50061 | 21.62491 | 52.77778 | 79.56053 |
| rank_pct | 10 | rf | 24.35005 | -6.69513 | 73.57786 | 21.91115 | 56.36364 | 60.62835 |
| return_abs | 1 | xgb | 3.31212 | -3.44208 | 7.33045 | 21.63351 | 48.14815 | 126.97489 |
| return_abs | 2 | rf | 3.19669 | -4.70701 | 14.64660 | 21.61092 | 50.92593 | 267.71235 |
| return_abs | 3 | xgb | 19.76561 | -2.18972 | 21.93796 | 21.72787 | 60.18519 | 76.14578 |
| return_abs | 5 | rf | 16.32051 | -3.84927 | 36.49220 | 21.65656 | 56.48148 | 70.42517 |
| return_abs | 10 | rf | 18.85868 | -11.96394 | 72.41469 | 21.38027 | 55.55556 | 80.52521 |

## H. Matrice score × détention — tous les coûts

Rendements cumulés (%) sur univers commun top 3 %. Aucune cellule sous la diagonale n'est testée ; les cellules au-dessus sont toutes calculées.

| target | score_horizon | exit_horizon | gross | net25 | net45 |
| --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 1 | 5.77524 | 2.90066 | 0.65983 |
| rank_pct | 1 | 2 | 6.41277 | 3.52019 | 1.26535 |
| rank_pct | 1 | 3 | 10.98744 | 7.96494 | 5.60891 |
| rank_pct | 1 | 5 | 10.63566 | 7.62339 | 5.27533 |
| rank_pct | 1 | 10 | 29.11623 | 25.63549 | 22.91861 |
| rank_pct | 2 | 2 | 5.78390 | 2.96023 | 0.75814 |
| rank_pct | 2 | 3 | 13.98337 | 10.93053 | 8.54991 |
| rank_pct | 2 | 5 | 12.09238 | 9.09271 | 6.75351 |
| rank_pct | 2 | 10 | 23.80782 | 20.52618 | 17.96418 |
| rank_pct | 3 | 3 | 9.49467 | 6.51464 | 4.19170 |
| rank_pct | 3 | 5 | 13.96080 | 10.85385 | 8.43207 |
| rank_pct | 3 | 10 | 12.10588 | 9.07835 | 6.71530 |
| rank_pct | 5 | 5 | 18.51313 | 15.33298 | 12.85319 |
| rank_pct | 5 | 10 | 36.13516 | 32.52259 | 29.70193 |
| rank_pct | 10 | 10 | 30.64338 | 27.10876 | 24.35005 |
| return_abs | 1 | 1 | 8.47142 | 5.57269 | 3.31212 |
| return_abs | 1 | 2 | 14.70099 | 11.62814 | 9.23193 |
| return_abs | 1 | 3 | 30.69536 | 27.17332 | 24.42721 |
| return_abs | 1 | 5 | 14.70283 | 11.62330 | 9.22198 |
| return_abs | 1 | 10 | -1.38226 | -3.99314 | -6.03194 |
| return_abs | 2 | 2 | 8.34974 | 5.45452 | 3.19669 |
| return_abs | 2 | 3 | 20.21234 | 16.98450 | 14.46756 |
| return_abs | 2 | 5 | 10.04044 | 7.09794 | 4.80327 |
| return_abs | 2 | 10 | 15.99354 | 12.92319 | 10.52573 |
| return_abs | 3 | 3 | 25.78860 | 22.40437 | 19.76561 |
| return_abs | 3 | 5 | 18.44123 | 15.25655 | 12.77333 |
| return_abs | 3 | 10 | 28.41336 | 25.00815 | 22.34915 |
| return_abs | 5 | 5 | 22.16280 | 18.88015 | 16.32051 |
| return_abs | 5 | 10 | 42.30325 | 38.53386 | 35.59044 |
| return_abs | 10 | 10 | 24.73976 | 21.43742 | 18.85868 |

Les matrices complètes return/DD/capital actif/turnover/hit rate pour chaque coût sont dans les [matrices complètes](SRD_HORIZON_COMMON_REPLAY_MATRICES.md), `all_matrices.md` et **Horizon Comparison** du sandbox. Les tables machine `metrics.parquet` et `horizon_matrix.parquet` contiennent les deux univers et les deux concentrations.

## I. Exposition et cash

Exposition EOD = valeur des positions / NAV au close. Capital actif = somme des nominaux d'entrée des positions actives dans la séance / NAV précédente, entrée et sortie incluses. C'est une mesure du budget mobilisé et pas une moyenne horaire du notionnel. H1 a une exposition EOD nulle et un capital actif positif. `return_per_average_exposure` utilise ce capital actif ; le ratio EOD est séparé et indéfini en H1. Aucun de ces ratios n'est une performance annualisée.

| target | score_horizon | exit_horizon | average_exposure | median_exposure | max_exposure | average_active_session_capital | average_cash_fraction | average_holding_sessions | max_simultaneous_positions | turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 1 | 0.00000 | 0.00000 | 0.00000 | 0.07466 | 1.00000 | 1.00000 | 5 | 22.00708 |
| rank_pct | 1 | 2 | 0.07494 | 0.00000 | 0.50714 | 0.14922 | 0.92506 | 2.00000 | 5 | 21.99804 |
| rank_pct | 1 | 3 | 0.14989 | 0.00000 | 0.51668 | 0.22376 | 0.85011 | 3.00000 | 5 | 22.03630 |
| rank_pct | 1 | 5 | 0.29995 | 0.49660 | 0.51668 | 0.37268 | 0.70005 | 5.00000 | 5 | 22.02916 |
| rank_pct | 1 | 10 | 0.66939 | 0.97890 | 1.00000 | 0.73531 | 0.33061 | 10.00000 | 10 | 21.91807 |
| rank_pct | 2 | 2 | 0.07363 | 0.00000 | 0.50709 | 0.14647 | 0.92637 | 2.00000 | 5 | 21.58692 |
| rank_pct | 2 | 3 | 0.14722 | 0.00000 | 0.50799 | 0.21967 | 0.85278 | 3.00000 | 5 | 21.66851 |
| rank_pct | 2 | 5 | 0.29481 | 0.49416 | 0.51974 | 0.36567 | 0.70519 | 5.00000 | 5 | 21.62409 |
| rank_pct | 2 | 10 | 0.65799 | 0.79865 | 1.00000 | 0.72313 | 0.34201 | 10.00000 | 10 | 21.49778 |
| rank_pct | 3 | 3 | 0.14977 | 0.00000 | 0.51023 | 0.22387 | 0.85023 | 3.00000 | 5 | 22.04809 |
| rank_pct | 3 | 5 | 0.30000 | 0.49480 | 0.51799 | 0.37263 | 0.70000 | 5.00000 | 5 | 22.02678 |
| rank_pct | 3 | 10 | 0.67084 | 0.97748 | 1.00000 | 0.73834 | 0.32916 | 10.00000 | 10 | 21.82674 |
| rank_pct | 5 | 5 | 0.29556 | 0.49598 | 0.52770 | 0.36501 | 0.70444 | 5.00000 | 5 | 21.62491 |
| rank_pct | 5 | 10 | 0.65933 | 0.81120 | 1.00000 | 0.72032 | 0.34067 | 10.00000 | 10 | 21.47612 |
| rank_pct | 10 | 10 | 0.67209 | 0.98206 | 1.00000 | 0.73578 | 0.32791 | 10.00000 | 10 | 21.91115 |
| return_abs | 1 | 1 | 0.00000 | 0.00000 | 0.00000 | 0.07330 | 1.00000 | 1.00000 | 5 | 21.63351 |
| return_abs | 1 | 2 | 0.07367 | 0.00000 | 0.51125 | 0.14643 | 0.92633 | 2.00000 | 5 | 21.66221 |
| return_abs | 1 | 3 | 0.14752 | 0.00000 | 0.51950 | 0.21937 | 0.85248 | 3.00000 | 5 | 21.76534 |
| return_abs | 1 | 5 | 0.29975 | 0.49159 | 0.53076 | 0.37064 | 0.70025 | 5.07407 | 5 | 21.63588 |
| return_abs | 1 | 10 | 0.66183 | 0.89930 | 1.00000 | 0.72837 | 0.33817 | 10.10185 | 10 | 21.22723 |
| return_abs | 2 | 2 | 0.07363 | 0.00000 | 0.51064 | 0.14647 | 0.92637 | 2.00000 | 5 | 21.61092 |
| return_abs | 2 | 3 | 0.14729 | 0.00000 | 0.51845 | 0.21960 | 0.85271 | 3.00000 | 5 | 21.70902 |
| return_abs | 2 | 5 | 0.29497 | 0.49193 | 0.51860 | 0.36556 | 0.70503 | 5.00000 | 5 | 21.62146 |
| return_abs | 2 | 10 | 0.65733 | 0.81184 | 1.00000 | 0.72359 | 0.34267 | 10.00000 | 10 | 21.47189 |
| return_abs | 3 | 3 | 0.14749 | 0.00000 | 0.51615 | 0.21938 | 0.85251 | 3.00000 | 5 | 21.72787 |
| return_abs | 3 | 5 | 0.29967 | 0.49656 | 0.52391 | 0.37029 | 0.70033 | 5.07407 | 5 | 21.63485 |
| return_abs | 3 | 10 | 0.66204 | 0.88949 | 1.00000 | 0.72367 | 0.33796 | 10.10185 | 10 | 21.35785 |
| return_abs | 5 | 5 | 0.29566 | 0.49326 | 0.52534 | 0.36492 | 0.70434 | 5.00000 | 5 | 21.65656 |
| return_abs | 5 | 10 | 0.66011 | 0.81926 | 1.00000 | 0.72053 | 0.33989 | 10.07407 | 10 | 21.40971 |
| return_abs | 10 | 10 | 0.65971 | 0.79750 | 1.00000 | 0.72415 | 0.34029 | 10.07407 | 10 | 21.38027 |

Volatilité et Sharpe sont indicatifs, issus des rendements quotidiens de NAV avec facteur √252, cash compris, sans taux sans risque. Les fenêtres de détention et événements communs rendent les observations dépendantes.

## J. Concentration, trades et cutoffs

| target | score_horizon | exit_horizon | top1_contribution | top3_contribution | top5_contribution | top10_contribution | negative_top5_contribution | top_5_share | absolute_contribution_hhi | best_cutoff | best_cutoff_pnl | worst_cutoff | worst_cutoff_pnl | positive_cutoff_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 1 | 0.01492 | 0.03091 | 0.04385 | 0.06494 | -0.02720 | 6.64530 | 0.01820 | 2026-01-23 | 0.01316 | 2026-01-09 | -0.01301 | 0.59091 |
| rank_pct | 1 | 2 | 0.01410 | 0.03865 | 0.06015 | 0.09822 | -0.04089 | 4.75380 | 0.01584 | 2026-03-06 | 0.03270 | 2026-06-05 | -0.01867 | 0.54545 |
| rank_pct | 1 | 3 | 0.01551 | 0.04394 | 0.06943 | 0.11564 | -0.05315 | 1.23785 | 0.01679 | 2026-03-06 | 0.02620 | 2026-06-05 | -0.03066 | 0.63636 |
| rank_pct | 1 | 5 | 0.01749 | 0.04912 | 0.07633 | 0.13470 | -0.07081 | 1.44697 | 0.01532 | 2026-03-27 | 0.03972 | 2026-02-06 | -0.02480 | 0.40909 |
| rank_pct | 1 | 10 | 0.04293 | 0.10193 | 0.15649 | 0.25504 | -0.10861 | 0.68281 | 0.01556 | 2026-05-15 | 0.09477 | 2026-06-12 | -0.07548 | 0.63636 |
| rank_pct | 2 | 2 | 0.01269 | 0.03657 | 0.05621 | 0.08519 | -0.04254 | 7.41444 | 0.01844 | 2026-02-20 | 0.01628 | 2026-03-20 | -0.02045 | 0.54545 |
| rank_pct | 2 | 3 | 0.05243 | 0.07757 | 0.09713 | 0.13603 | -0.04633 | 1.13609 | 0.02999 | 2026-05-22 | 0.04239 | 2026-03-20 | -0.02470 | 0.50000 |
| rank_pct | 2 | 5 | 0.03545 | 0.06593 | 0.09286 | 0.14566 | -0.06274 | 1.37500 | 0.01893 | 2026-03-27 | 0.04069 | 2026-03-20 | -0.03502 | 0.45455 |
| rank_pct | 2 | 10 | 0.03987 | 0.09848 | 0.14254 | 0.21651 | -0.09766 | 0.79349 | 0.01816 | 2026-05-15 | 0.09064 | 2026-06-12 | -0.05131 | 0.54545 |
| rank_pct | 3 | 3 | 0.01321 | 0.03842 | 0.06107 | 0.10107 | -0.04636 | 1.45692 | 0.01656 | 2026-03-27 | 0.03016 | 2026-06-12 | -0.02613 | 0.54545 |
| rank_pct | 3 | 5 | 0.01802 | 0.05178 | 0.07925 | 0.13717 | -0.06671 | 0.93990 | 0.01780 | 2026-03-27 | 0.03381 | 2026-06-12 | -0.03753 | 0.68182 |
| rank_pct | 3 | 10 | 0.03819 | 0.09053 | 0.12389 | 0.19445 | -0.09432 | 1.84487 | 0.01701 | 2026-05-15 | 0.06348 | 2026-06-12 | -0.07633 | 0.54545 |
| rank_pct | 5 | 5 | 0.03655 | 0.07170 | 0.10226 | 0.15801 | -0.06269 | 0.79561 | 0.02128 | 2026-05-22 | 0.04371 | 2026-01-23 | -0.01643 | 0.72727 |
| rank_pct | 5 | 10 | 0.04280 | 0.10709 | 0.15870 | 0.24736 | -0.10263 | 0.53431 | 0.01901 | 2026-05-15 | 0.09441 | 2026-06-12 | -0.06446 | 0.77273 |
| rank_pct | 10 | 10 | 0.04154 | 0.09795 | 0.14763 | 0.23355 | -0.10504 | 0.60628 | 0.01832 | 2026-05-15 | 0.08601 | 2026-06-12 | -0.05804 | 0.77273 |
| return_abs | 1 | 1 | 0.00860 | 0.02553 | 0.04206 | 0.07440 | -0.03391 | 1.26975 | 0.01489 | 2026-03-06 | 0.02133 | 2026-02-13 | -0.01136 | 0.50000 |
| return_abs | 1 | 2 | 0.02998 | 0.05889 | 0.08392 | 0.13983 | -0.05874 | 0.90904 | 0.01697 | 2026-03-06 | 0.03993 | 2026-03-20 | -0.01956 | 0.59091 |
| return_abs | 1 | 3 | 0.05705 | 0.11670 | 0.15965 | 0.23026 | -0.08808 | 0.65357 | 0.02191 | 2026-05-22 | 0.07435 | 2026-02-13 | -0.03254 | 0.63636 |
| return_abs | 1 | 5 | 0.03548 | 0.08409 | 0.12300 | 0.20497 | -0.18663 | 1.33377 | 0.02238 | 2026-05-22 | 0.05247 | 2026-02-13 | -0.09564 | 0.72727 |
| return_abs | 1 | 10 | 0.04570 | 0.11262 | 0.16142 | 0.26423 | -0.24460 | -2.67601 | 0.01981 | 2026-03-27 | 0.04248 | 2026-02-06 | -0.09383 | 0.63636 |
| return_abs | 2 | 2 | 0.02886 | 0.06026 | 0.08558 | 0.13662 | -0.06060 | 2.67712 | 0.01758 | 2026-03-06 | 0.03677 | 2026-05-15 | -0.02342 | 0.40909 |
| return_abs | 2 | 3 | 0.02733 | 0.07678 | 0.10810 | 0.16890 | -0.07894 | 0.74720 | 0.01726 | 2026-04-10 | 0.04060 | 2026-01-16 | -0.01807 | 0.54545 |
| return_abs | 2 | 5 | 0.02709 | 0.06676 | 0.10070 | 0.16207 | -0.14249 | 2.09648 | 0.02096 | 2026-04-10 | 0.04371 | 2026-05-15 | -0.04855 | 0.59091 |
| return_abs | 2 | 10 | 0.04296 | 0.10968 | 0.15162 | 0.24116 | -0.17627 | 1.44045 | 0.01783 | 2026-04-10 | 0.04623 | 2026-03-13 | -0.05808 | 0.63636 |
| return_abs | 3 | 3 | 0.05478 | 0.11011 | 0.15051 | 0.20591 | -0.08380 | 0.76146 | 0.02425 | 2026-05-22 | 0.05439 | 2026-04-24 | -0.01439 | 0.63636 |
| return_abs | 3 | 5 | 0.03578 | 0.08425 | 0.12195 | 0.19766 | -0.14157 | 0.95473 | 0.02165 | 2026-05-22 | 0.03331 | 2026-02-13 | -0.05330 | 0.63636 |
| return_abs | 3 | 10 | 0.04448 | 0.10495 | 0.15550 | 0.25536 | -0.18155 | 0.69577 | 0.01978 | 2026-03-27 | 0.05665 | 2026-02-06 | -0.04148 | 0.72727 |
| return_abs | 5 | 5 | 0.03719 | 0.07799 | 0.11494 | 0.19406 | -0.08910 | 0.70425 | 0.01625 | 2026-05-22 | 0.04156 | 2026-01-30 | -0.02029 | 0.59091 |
| return_abs | 5 | 10 | 0.04458 | 0.12281 | 0.17951 | 0.29573 | -0.14855 | 0.50438 | 0.01646 | 2026-05-15 | 0.10518 | 2026-06-12 | -0.05212 | 0.72727 |
| return_abs | 10 | 10 | 0.03782 | 0.10202 | 0.15186 | 0.25236 | -0.15073 | 0.80525 | 0.01663 | 2026-05-15 | 0.09201 | 2026-02-06 | -0.06946 | 0.68182 |

Les contributions valent des fractions du capital initial (×100 pour des points). HHI absolu = somme des carrés des contributions absolues normalisées ; HHI positif calculé séparément. Les meilleurs trades ne sont jamais retirés d'un replay. Les vues `trades`, `portfolio_cutoff` et `event_concentration` conservent prix, dates, volumes, warnings, audit réutilisé, retards et catégories >10/20/30 %.

L'[audit prix précédent](SRD_PRICE_AUDIT.md) est réutilisé après contrôle du SHA source. Les entrées non exécutées Nacon des 23 février et 2 mars conservent également leur preuve primaire (`entry_not_traded_in_primary_table`) : rapprochement par entité/date d'entrée dans l'étape de publication, sans modifier les champs financiers ou les sélections (`annotation_audit.json`). Les nouveaux cas restent dans `new_price_audit_cases.parquet` avec statut pending. Le registre contient 729 couples instrument/entrée/sortie distincts (y compris des références univers) ; il conserve pour chaque cas l'attribution la plus matérielle et le nombre de variantes concernées, par priorité absolue. Tous les résultats portent `volume_definition_not_certified=true`. Aucun volume n'a été substitué et les features n'ont pas été recalculées.

## K. Similarité et diagnostic top 10 %

Jaccard des paniers et corrélations cross-sectionnelles de scores/rangs sont calculés par cutoff puis moyennés. `overlap.parquet` conserve les 22 observations par paire. `winner_overlap.parquet` compare les cinq contributions les plus élevées, avec identité trade = action + cutoff, à détention H10 commune et coût 45 bp.

| model_a | model_b | jaccard | overlap_fraction | score_correlation | rank_correlation |
| --- | --- | --- | --- | --- | --- |
| rank_pct-h1-all-rf-0df3b166dc71 | rank_pct-h10-all-rf-bedd78069821 | 0.13817 | 0.22727 | 0.23766 | 0.20285 |
| rank_pct-h1-all-rf-0df3b166dc71 | rank_pct-h2-all-rf-90eeb04f8762 | 0.20166 | 0.31818 | 0.60969 | 0.56167 |
| rank_pct-h1-all-rf-0df3b166dc71 | rank_pct-h3-all-rf-6ef7625d42fd | 0.16270 | 0.26364 | 0.36952 | 0.32005 |
| rank_pct-h1-all-rf-0df3b166dc71 | rank_pct-h5-all-rf-3c5fa028d3f4 | 0.16901 | 0.27273 | 0.34204 | 0.27976 |
| rank_pct-h1-all-rf-0df3b166dc71 | return_abs-h1-all-xgb-2cb02f543be3 | 0.20292 | 0.31818 | 0.24051 | 0.25614 |
| rank_pct-h1-all-rf-0df3b166dc71 | return_abs-h10-all-rf-1bbd2af1ad50 | 0.20924 | 0.32727 | 0.16504 | -0.09357 |
| rank_pct-h1-all-rf-0df3b166dc71 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.20292 | 0.31818 | 0.29874 | 0.30928 |
| rank_pct-h1-all-rf-0df3b166dc71 | return_abs-h3-all-xgb-d139323e99e0 | 0.13690 | 0.22727 | 0.11579 | 0.06070 |
| rank_pct-h1-all-rf-0df3b166dc71 | return_abs-h5-all-rf-1273ae260f86 | 0.21735 | 0.33636 | 0.15155 | -0.09916 |
| rank_pct-h10-all-rf-bedd78069821 | rank_pct-h2-all-rf-90eeb04f8762 | 0.22439 | 0.32727 | 0.46099 | 0.46899 |
| rank_pct-h10-all-rf-bedd78069821 | rank_pct-h3-all-rf-6ef7625d42fd | 0.27471 | 0.40909 | 0.57361 | 0.61782 |
| rank_pct-h10-all-rf-bedd78069821 | rank_pct-h5-all-rf-3c5fa028d3f4 | 0.32017 | 0.45455 | 0.83270 | 0.84292 |
| rank_pct-h10-all-rf-bedd78069821 | return_abs-h1-all-xgb-2cb02f543be3 | 0.13059 | 0.21818 | 0.06187 | 0.08098 |
| rank_pct-h10-all-rf-bedd78069821 | return_abs-h10-all-rf-1bbd2af1ad50 | 0.19787 | 0.30909 | 0.30533 | -0.05343 |
| rank_pct-h10-all-rf-bedd78069821 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.14448 | 0.23636 | 0.10687 | 0.12702 |
| rank_pct-h10-all-rf-bedd78069821 | return_abs-h3-all-xgb-d139323e99e0 | 0.10732 | 0.18182 | 0.08174 | 0.15832 |
| rank_pct-h10-all-rf-bedd78069821 | return_abs-h5-all-rf-1273ae260f86 | 0.21555 | 0.33636 | 0.26077 | 0.02601 |
| rank_pct-h2-all-rf-90eeb04f8762 | rank_pct-h3-all-rf-6ef7625d42fd | 0.31403 | 0.45455 | 0.60781 | 0.57901 |
| rank_pct-h2-all-rf-90eeb04f8762 | rank_pct-h5-all-rf-3c5fa028d3f4 | 0.25920 | 0.36364 | 0.53719 | 0.52037 |
| rank_pct-h2-all-rf-90eeb04f8762 | return_abs-h1-all-xgb-2cb02f543be3 | 0.17767 | 0.26364 | 0.19140 | 0.19499 |
| rank_pct-h2-all-rf-90eeb04f8762 | return_abs-h10-all-rf-1bbd2af1ad50 | 0.22078 | 0.31818 | 0.19064 | -0.05881 |
| rank_pct-h2-all-rf-90eeb04f8762 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.19805 | 0.29091 | 0.30670 | 0.30145 |
| rank_pct-h2-all-rf-90eeb04f8762 | return_abs-h3-all-xgb-d139323e99e0 | 0.13799 | 0.21818 | 0.15289 | 0.13722 |
| rank_pct-h2-all-rf-90eeb04f8762 | return_abs-h5-all-rf-1273ae260f86 | 0.24910 | 0.34545 | 0.19344 | -0.02922 |
| rank_pct-h3-all-rf-6ef7625d42fd | rank_pct-h5-all-rf-3c5fa028d3f4 | 0.20869 | 0.31818 | 0.64955 | 0.69384 |
| rank_pct-h3-all-rf-6ef7625d42fd | return_abs-h1-all-xgb-2cb02f543be3 | 0.14502 | 0.23636 | 0.15923 | 0.08900 |
| rank_pct-h3-all-rf-6ef7625d42fd | return_abs-h10-all-rf-1bbd2af1ad50 | 0.12229 | 0.20000 | 0.07844 | -0.06220 |
| rank_pct-h3-all-rf-6ef7625d42fd | return_abs-h2-all-rf-06dc2b7ed8ec | 0.14899 | 0.23636 | 0.14049 | 0.21848 |
| rank_pct-h3-all-rf-6ef7625d42fd | return_abs-h3-all-xgb-d139323e99e0 | 0.08766 | 0.14545 | 0.03191 | 0.24686 |
| rank_pct-h3-all-rf-6ef7625d42fd | return_abs-h5-all-rf-1273ae260f86 | 0.14574 | 0.22727 | 0.06903 | -0.03433 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | return_abs-h1-all-xgb-2cb02f543be3 | 0.16071 | 0.25455 | 0.08364 | 0.06448 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | return_abs-h10-all-rf-1bbd2af1ad50 | 0.26858 | 0.37273 | 0.25490 | -0.07195 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.20346 | 0.30000 | 0.18321 | 0.18359 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | return_abs-h3-all-xgb-d139323e99e0 | 0.14628 | 0.23636 | 0.10080 | 0.17631 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | return_abs-h5-all-rf-1273ae260f86 | 0.27994 | 0.39091 | 0.23726 | -0.02103 |
| return_abs-h1-all-xgb-2cb02f543be3 | return_abs-h10-all-rf-1bbd2af1ad50 | 0.32666 | 0.47273 | 0.36099 | 0.17587 |
| return_abs-h1-all-xgb-2cb02f543be3 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.39881 | 0.55455 | 0.54990 | 0.32176 |
| return_abs-h1-all-xgb-2cb02f543be3 | return_abs-h3-all-xgb-d139323e99e0 | 0.31259 | 0.44545 | 0.34311 | 0.19394 |
| return_abs-h1-all-xgb-2cb02f543be3 | return_abs-h5-all-rf-1273ae260f86 | 0.32937 | 0.47273 | 0.33220 | 0.16884 |
| return_abs-h10-all-rf-1bbd2af1ad50 | return_abs-h2-all-rf-06dc2b7ed8ec | 0.46447 | 0.60909 | 0.62081 | 0.18219 |
| return_abs-h10-all-rf-1bbd2af1ad50 | return_abs-h3-all-xgb-d139323e99e0 | 0.44300 | 0.59091 | 0.63604 | 0.19937 |
| return_abs-h10-all-rf-1bbd2af1ad50 | return_abs-h5-all-rf-1273ae260f86 | 0.72294 | 0.81818 | 0.91142 | 0.45351 |
| return_abs-h2-all-rf-06dc2b7ed8ec | return_abs-h3-all-xgb-d139323e99e0 | 0.34470 | 0.49091 | 0.56027 | 0.25599 |
| return_abs-h2-all-rf-06dc2b7ed8ec | return_abs-h5-all-rf-1273ae260f86 | 0.49784 | 0.63636 | 0.64203 | 0.22122 |
| return_abs-h3-all-xgb-d139323e99e0 | return_abs-h5-all-rf-1273ae260f86 | 0.43128 | 0.58182 | 0.67400 | 0.23975 |

Sensibilité à 45 bp : même score et détention, top 3 % vs top 10 %. Le percentile n'a pas été retuné.

| target | score_horizon | exit_horizon | cumulative_return_top3 | cumulative_return_top10 | return_difference | max_drawdown_top3 | max_drawdown_top10 | top_5_share_top3 | top_5_share_top10 | turnover_top3 | turnover_top10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 1 | 0.00660 | -0.00734 | 0.01394 | -0.01838 | -0.02181 | 6.64530 | -1.93820 | 22.00708 | 21.99290 |
| rank_pct | 1 | 2 | 0.01265 | -0.00403 | 0.01669 | -0.03043 | -0.03416 | 4.75380 | -4.94615 | 21.99804 | 21.98785 |
| rank_pct | 1 | 3 | 0.05609 | 0.02106 | 0.03503 | -0.03858 | -0.03787 | 1.23785 | 1.09860 | 22.03630 | 22.01080 |
| rank_pct | 1 | 5 | 0.05275 | -0.01214 | 0.06489 | -0.06488 | -0.07533 | 1.44697 | -2.10274 | 22.02916 | 21.98108 |
| rank_pct | 1 | 10 | 0.22919 | 0.01552 | 0.21366 | -0.10522 | -0.10419 | 0.68281 | 3.02782 | 21.91807 | 21.92195 |
| rank_pct | 2 | 2 | 0.00758 | -0.04675 | 0.05434 | -0.03482 | -0.04675 | 7.41444 | -0.38366 | 21.58692 | 21.83281 |
| rank_pct | 2 | 3 | 0.08550 | 0.00216 | 0.08334 | -0.02894 | -0.02977 | 1.13609 | 14.33730 | 21.66851 | 21.89621 |
| rank_pct | 2 | 5 | 0.06754 | -0.01469 | 0.08222 | -0.05656 | -0.04821 | 1.37500 | -2.02908 | 21.62409 | 21.86100 |
| rank_pct | 2 | 10 | 0.17964 | 0.06848 | 0.11116 | -0.08984 | -0.06236 | 0.79349 | 0.62991 | 21.49778 | 21.84297 |
| rank_pct | 3 | 3 | 0.04192 | 0.09222 | -0.05030 | -0.05842 | -0.01684 | 1.45692 | 0.39305 | 22.04809 | 22.07161 |
| rank_pct | 3 | 5 | 0.08432 | 0.07929 | 0.00503 | -0.05401 | -0.02142 | 0.93990 | 0.42171 | 22.02678 | 22.01547 |
| rank_pct | 3 | 10 | 0.06715 | 0.11816 | -0.05101 | -0.09419 | -0.05999 | 1.84487 | 0.40134 | 21.82674 | 21.90744 |
| rank_pct | 5 | 5 | 0.12853 | 0.06316 | 0.06537 | -0.03371 | -0.01528 | 0.79561 | 0.51429 | 21.62491 | 21.89255 |
| rank_pct | 5 | 10 | 0.29702 | 0.13416 | 0.16286 | -0.08575 | -0.03981 | 0.53431 | 0.35338 | 21.47612 | 21.81523 |
| rank_pct | 10 | 10 | 0.24350 | 0.06992 | 0.17358 | -0.06695 | -0.04731 | 0.60628 | 0.61763 | 21.91115 | 21.88094 |
| return_abs | 1 | 1 | 0.03312 | -0.01866 | 0.05178 | -0.03442 | -0.02780 | 1.26975 | -0.66981 | 21.63351 | 21.86382 |
| return_abs | 1 | 2 | 0.09232 | -0.00096 | 0.09328 | -0.02514 | -0.02717 | 0.90904 | -26.73551 | 21.66221 | 21.87910 |
| return_abs | 1 | 3 | 0.24427 | 0.08198 | 0.16229 | -0.05164 | -0.02861 | 0.65357 | 0.57767 | 21.76534 | 21.94965 |
| return_abs | 1 | 5 | 0.09222 | 0.02024 | 0.07197 | -0.09643 | -0.04521 | 1.33377 | 2.03552 | 21.63588 | 21.86740 |
| return_abs | 1 | 10 | -0.06032 | -0.00043 | -0.05989 | -0.26517 | -0.10274 | -2.67601 | -118.09531 | 21.22723 | 21.74415 |
| return_abs | 2 | 2 | 0.03197 | 0.01232 | 0.01964 | -0.04707 | -0.03003 | 2.67712 | 2.25312 | 21.61092 | 21.88375 |
| return_abs | 2 | 3 | 0.14468 | 0.09300 | 0.05167 | -0.04261 | -0.03147 | 0.74720 | 0.51770 | 21.70902 | 21.95315 |
| return_abs | 2 | 5 | 0.04803 | 0.00332 | 0.04471 | -0.07024 | -0.05149 | 2.09648 | 12.54716 | 21.62146 | 21.86037 |
| return_abs | 2 | 10 | 0.10526 | 0.00072 | 0.10454 | -0.09072 | -0.10013 | 1.44045 | 73.84347 | 21.47189 | 21.77109 |
| return_abs | 3 | 3 | 0.19766 | 0.07908 | 0.11857 | -0.02190 | -0.04123 | 0.76146 | 0.61196 | 21.72787 | 21.94343 |
| return_abs | 3 | 5 | 0.12773 | 0.02465 | 0.10308 | -0.08559 | -0.04862 | 0.95473 | 1.51563 | 21.63485 | 21.85905 |
| return_abs | 3 | 10 | 0.22349 | 0.08540 | 0.13809 | -0.10258 | -0.10096 | 0.69577 | 0.65533 | 21.35785 | 21.75096 |
| return_abs | 5 | 5 | 0.16321 | -0.01480 | 0.17800 | -0.03849 | -0.05638 | 0.70425 | -2.21043 | 21.65656 | 21.84639 |
| return_abs | 5 | 10 | 0.35590 | 0.00180 | 0.35411 | -0.09855 | -0.09357 | 0.50438 | 27.10456 | 21.40971 | 21.76465 |
| return_abs | 10 | 10 | 0.18859 | 0.05616 | 0.13242 | -0.11964 | -0.10182 | 0.80525 | 0.86576 | 21.38027 | 21.75519 |

## L. Incertitude, benchmark et limites

Le benchmark utilise le même univers commun, les mêmes 22 décisions et deux compartiments, équipondéré ; une référence distincte est nécessaire pour chaque durée de détention. Il ne change pas selon l'horizon appris du score.

| exit_horizon | cumulative_return | max_drawdown | average_active_session_capital | turnover |
| --- | --- | --- | --- | --- |
| 1 | -0.02299 | -0.02299 | 0.07462 | 21.96474 |
| 2 | -0.02895 | -0.03136 | 0.14924 | 21.95792 |
| 3 | -0.00507 | -0.03465 | 0.22387 | 21.98509 |
| 5 | -0.02550 | -0.04082 | 0.37319 | 21.95710 |
| 10 | -0.04258 | -0.08532 | 0.74534 | 21.91577 |

Bootstrap circulaire par blocs 2/4/6, 10 000 réplications, seed 20261006 : intervalles individuels 90 % de la moyenne des rendements de paniers par cutoff et différences appariées à H10 face au score H5. Tirages communs entre variantes ; pas d'intervalle présenté comme probabilité d'alpha. Résultats dans `basket_bootstrap.parquet`. Seulement 22 dates ; multiplicité, chevauchement, survivance et vintages/volumes non certifiés restent des limites.

## M. Réponses aux quatorze questions

1. **H3 reste-t-il meilleur ?** Parmi les sorties natives de rendement, H3 garde le meilleur net 45 bp (+19.77 %), brut +25.79 %, contre +23,48 % sur les 23 dates anciennes. Dans le rang natif, H10 est premier. Dans la matrice entière, H3 n'est pas premier.
2. **Concentration H3 :** top cinq = 76.1 % du gain net ; X-FAB, cutoff 2026-05-22, trade +50 %, apporte 5.48 points (27.7 % du net). Le résultat reste fortement concentré ; ces trades sont conservés.
3. **Meilleurs scores courts ou turnover ?** À détention H5 fixe, le score H5 donne +12.85 % (rang) et +16.32 % (rendement), devant tous les H1/H2/H3. À H10 fixe, H5 est aussi premier dans chaque famille. Le turnover principal varie peu (environ 21–22 fois NAV), car chaque variante effectue les mêmes 22 achats hebdomadaires, quelle que soit sa détention. Les grands PnL courts ne prouvent donc pas un meilleur score ; ils dépendent aussi des titres et événements sélectionnés.
4. **Score H1 détenu H5 :** rang +5.28 %, rendement +9.22 % nets 45 bp. Positifs face à l'univers H5 (−2,55 %), mais inférieurs au score H5 dans chaque famille ; aucun avantage du score court établi.
5. **Score H2 détenu H5 :** rang +6.75 %, rendement +4.80 % nets 45 bp. Positifs face à l'univers H5 (−2,55 %), mais inférieurs au score H5 dans chaque famille ; aucun avantage du score court établi.
6. **Rang H5→H10 :** +12.85 % → +29.70 % ; gain 16.85 points. Capital actif 36.5 % → 72.0 %, DD -3.37 % → -8.58 %. L'amélioration reste observée ici, avec davantage de risque et d'immobilisation.
7. **Rang H10 natif vs H5 natif :** +24.35 % contre +12.85 % ; H10 natif est plus rentable. À même durée H10, le score H5 (+29.70 %) dépasse H10.
8. **Meilleur net 45 bp observé :** Rendement absolu, H5→H10, +35.59 %. Ce classement est descriptif après exploration.
9. **Meilleur ratio de capital actif :** Rendement absolu, H1→H3, ratio 1.114. Son exposition inclut l'intraday ; ce ratio n'est ni annualisé ni extrapolable à une exposition constante de 100 %.
10. **Compromis rendement/DD/turnover :** rendement H3→H3 : +19.77 %, DD -2.19 %, turnover 21.73. Rang H5→H5 : +12.85 %, DD -3.37 %, turnover 21.62. Rang H5→H10 accroît le gain et le DD. Ces exemples illustrent les différences de rendement, de risque et de concentration ; aucune fonction d'utilité n'a été fixée, donc pas de meilleur compromis objectif unique.
11. **Mêmes titres ?** Jaccard moyen entre horizons d'une même famille : 0.138 à 0.723. Il existe des titres communs, mais les sélections ne sont pas identiques. Les corrélations de scores/rangs K complètent ce diagnostic sans prouver l'indépendance des informations économiques.
12. **Mêmes événements extrêmes ?** X-FAB et MaaT se retrouvent dans plusieurs variantes ; Nacon contribue à des pertes et retards. Le Jaccard des cinq meilleurs trades H10 va de 0.111 à 0.667. Les gagnants communs comptent, sans expliquer seuls toute la performance.
13. **Top 3 % indispensable ?** 21/30 variantes restent positives à top 10 %, contre 29/30 à top 3 %. Rang H5→H10 : +29.70 % → +13.42 % ; rendement H5→H10 : +35.59 % → +0.18 %. La concentration n'est pas nécessaire à tout gain, mais elle est essentielle à l'amplitude de certaines variantes. Aucun percentile n'est choisi à nouveau.
14. **Durée robuste indépendamment du score ?** H10 améliore H5 dans 6/8 comparaisons appariées, mais rendement H1→H10 devient négatif et rang H3 perd en allongeant. Aucune durée universellement robuste n'est établie. H10 mérite un examen pour les scores H5 ; H3 pour les scores courts de rendement, sans optimiser une règle sur 2026.

### Durée fixée H5 · net 45 bp

| target | score_horizon | exit_horizon | model | cost_bp | top_fraction | cumulative_return | max_drawdown | average_exposure | average_active_session_capital | turnover | hit_rate | positions | common_benchmark_return | excess_vs_common_benchmark | top_5_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 5 | rf | 45 | 0.03000 | 0.05275 | -0.06488 | 0.29995 | 0.37268 | 22.02916 | 0.52727 | 110 | -0.02550 | 0.07825 | 1.44697 |
| rank_pct | 2 | 5 | rf | 45 | 0.03000 | 0.06754 | -0.05656 | 0.29481 | 0.36567 | 21.62409 | 0.49074 | 108 | -0.02550 | 0.09303 | 1.37500 |
| rank_pct | 3 | 5 | rf | 45 | 0.03000 | 0.08432 | -0.05401 | 0.30000 | 0.37263 | 22.02678 | 0.50909 | 110 | -0.02550 | 0.10982 | 0.93990 |
| rank_pct | 5 | 5 | rf | 45 | 0.03000 | 0.12853 | -0.03371 | 0.29556 | 0.36501 | 21.62491 | 0.52778 | 108 | -0.02550 | 0.15403 | 0.79561 |
| return_abs | 1 | 5 | xgb | 45 | 0.03000 | 0.09222 | -0.09643 | 0.29975 | 0.37064 | 21.63588 | 0.58333 | 108 | -0.02550 | 0.11772 | 1.33377 |
| return_abs | 2 | 5 | rf | 45 | 0.03000 | 0.04803 | -0.07024 | 0.29497 | 0.36556 | 21.62146 | 0.55556 | 108 | -0.02550 | 0.07353 | 2.09648 |
| return_abs | 3 | 5 | xgb | 45 | 0.03000 | 0.12773 | -0.08559 | 0.29967 | 0.37029 | 21.63485 | 0.59259 | 108 | -0.02550 | 0.15323 | 0.95473 |
| return_abs | 5 | 5 | rf | 45 | 0.03000 | 0.16321 | -0.03849 | 0.29566 | 0.36492 | 21.65656 | 0.56481 | 108 | -0.02550 | 0.18870 | 0.70425 |

### Durée fixée H10 · net 45 bp

| target | score_horizon | exit_horizon | model | cost_bp | top_fraction | cumulative_return | max_drawdown | average_exposure | average_active_session_capital | turnover | hit_rate | positions | common_benchmark_return | excess_vs_common_benchmark | top_5_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rank_pct | 1 | 10 | rf | 45 | 0.03000 | 0.22919 | -0.10522 | 0.66939 | 0.73531 | 21.91807 | 0.55455 | 110 | -0.04258 | 0.27176 | 0.68281 |
| rank_pct | 2 | 10 | rf | 45 | 0.03000 | 0.17964 | -0.08984 | 0.65799 | 0.72313 | 21.49778 | 0.55556 | 108 | -0.04258 | 0.22222 | 0.79349 |
| rank_pct | 3 | 10 | rf | 45 | 0.03000 | 0.06715 | -0.09419 | 0.67084 | 0.73834 | 21.82674 | 0.50000 | 110 | -0.04258 | 0.10973 | 1.84487 |
| rank_pct | 5 | 10 | rf | 45 | 0.03000 | 0.29702 | -0.08575 | 0.65933 | 0.72032 | 21.47612 | 0.61111 | 108 | -0.04258 | 0.33960 | 0.53431 |
| rank_pct | 10 | 10 | rf | 45 | 0.03000 | 0.24350 | -0.06695 | 0.67209 | 0.73578 | 21.91115 | 0.56364 | 110 | -0.04258 | 0.28608 | 0.60628 |
| return_abs | 1 | 10 | xgb | 45 | 0.03000 | -0.06032 | -0.26517 | 0.66183 | 0.72837 | 21.22723 | 0.48148 | 108 | -0.04258 | -0.01774 | -2.67601 |
| return_abs | 2 | 10 | rf | 45 | 0.03000 | 0.10526 | -0.09072 | 0.65733 | 0.72359 | 21.47189 | 0.54630 | 108 | -0.04258 | 0.14783 | 1.44045 |
| return_abs | 3 | 10 | xgb | 45 | 0.03000 | 0.22349 | -0.10258 | 0.66204 | 0.72367 | 21.35785 | 0.57407 | 108 | -0.04258 | 0.26607 | 0.69577 |
| return_abs | 5 | 10 | rf | 45 | 0.03000 | 0.35590 | -0.09855 | 0.66011 | 0.72053 | 21.40971 | 0.60185 | 108 | -0.04258 | 0.39848 | 0.50438 |
| return_abs | 10 | 10 | rf | 45 | 0.03000 | 0.18859 | -0.11964 | 0.65971 | 0.72415 | 21.38027 | 0.55556 | 108 | -0.04258 | 0.23116 | 0.80525 |

### IC après open — mêmes dates et univers, sans exclusion qualité future

| model_id | exit_horizon | mean_ic | minimum_pairs | target | horizon |
| --- | --- | --- | --- | --- | --- |
| rank_pct-h1-all-rf-0df3b166dc71 | 1 | 0.02550 | 159 | rank_pct | 1 |
| rank_pct-h1-all-rf-0df3b166dc71 | 2 | 0.00816 | 159 | rank_pct | 1 |
| rank_pct-h1-all-rf-0df3b166dc71 | 3 | 0.01116 | 159 | rank_pct | 1 |
| rank_pct-h1-all-rf-0df3b166dc71 | 5 | 0.00851 | 159 | rank_pct | 1 |
| rank_pct-h1-all-rf-0df3b166dc71 | 10 | 0.02728 | 159 | rank_pct | 1 |
| rank_pct-h10-all-rf-bedd78069821 | 10 | 0.05907 | 159 | rank_pct | 10 |
| rank_pct-h2-all-rf-90eeb04f8762 | 2 | -0.00063 | 159 | rank_pct | 2 |
| rank_pct-h2-all-rf-90eeb04f8762 | 3 | 0.02099 | 159 | rank_pct | 2 |
| rank_pct-h2-all-rf-90eeb04f8762 | 5 | 0.01480 | 159 | rank_pct | 2 |
| rank_pct-h2-all-rf-90eeb04f8762 | 10 | 0.03859 | 159 | rank_pct | 2 |
| rank_pct-h3-all-rf-6ef7625d42fd | 3 | 0.05850 | 159 | rank_pct | 3 |
| rank_pct-h3-all-rf-6ef7625d42fd | 5 | 0.03254 | 159 | rank_pct | 3 |
| rank_pct-h3-all-rf-6ef7625d42fd | 10 | 0.04485 | 159 | rank_pct | 3 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | 5 | 0.04307 | 159 | rank_pct | 5 |
| rank_pct-h5-all-rf-3c5fa028d3f4 | 10 | 0.06641 | 159 | rank_pct | 5 |
| return_abs-h1-all-xgb-2cb02f543be3 | 1 | -0.01826 | 159 | return_abs | 1 |
| return_abs-h1-all-xgb-2cb02f543be3 | 2 | 0.00626 | 159 | return_abs | 1 |
| return_abs-h1-all-xgb-2cb02f543be3 | 3 | 0.01392 | 159 | return_abs | 1 |
| return_abs-h1-all-xgb-2cb02f543be3 | 5 | 0.02114 | 159 | return_abs | 1 |
| return_abs-h1-all-xgb-2cb02f543be3 | 10 | 0.00905 | 159 | return_abs | 1 |
| return_abs-h10-all-rf-1bbd2af1ad50 | 10 | 0.04518 | 159 | return_abs | 10 |
| return_abs-h2-all-rf-06dc2b7ed8ec | 2 | 0.03197 | 159 | return_abs | 2 |
| return_abs-h2-all-rf-06dc2b7ed8ec | 3 | 0.04471 | 159 | return_abs | 2 |
| return_abs-h2-all-rf-06dc2b7ed8ec | 5 | 0.00455 | 159 | return_abs | 2 |
| return_abs-h2-all-rf-06dc2b7ed8ec | 10 | 0.00172 | 159 | return_abs | 2 |
| return_abs-h3-all-xgb-d139323e99e0 | 3 | 0.05640 | 159 | return_abs | 3 |
| return_abs-h3-all-xgb-d139323e99e0 | 5 | 0.03604 | 159 | return_abs | 3 |
| return_abs-h3-all-xgb-d139323e99e0 | 10 | 0.05270 | 159 | return_abs | 3 |
| return_abs-h5-all-rf-1273ae260f86 | 5 | 0.02576 | 159 | return_abs | 5 |
| return_abs-h5-all-rf-1273ae260f86 | 10 | 0.05213 | 159 | return_abs | 5 |

L'IC décrit les paires dont les deux prix sont disponibles à l'entrée et au close théorique ; les cas sans prix sont comptés, pas remplacés par des sorties retardées dans cet indicateur. Le ledger portfolio conserve ces retards. Le gap close→open est calculé séparément dans `gap_ic.parquet`, sans participation à la sélection.

### Différences de paniers à H10 face au score H5 — intervalles individuels 90 %

| simulation_id | block | mean_basket_return | lower90 | upper90 | positive_sign_support | reference_simulation |
| --- | --- | --- | --- | --- | --- | --- |
| return_abs-h1-all-xgb-2cb02f543be3-common-top3-exit10-cost45 | 2 | -0.03245 | -0.06161 | -0.00767 | 0.01050 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h2-all-rf-06dc2b7ed8ec-common-top3-exit10-cost45 | 2 | -0.01930 | -0.04257 | 0.00460 | 0.08940 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h3-all-xgb-d139323e99e0-common-top3-exit10-cost45 | 2 | -0.01008 | -0.02890 | 0.00795 | 0.18540 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 | 2 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h10-all-rf-1bbd2af1ad50-common-top3-exit10-cost45 | 2 | -0.01185 | -0.02384 | -0.00051 | 0.04290 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| rank_pct-h1-all-rf-0df3b166dc71-common-top3-exit10-cost45 | 2 | -0.00446 | -0.01896 | 0.01073 | 0.30240 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h2-all-rf-90eeb04f8762-common-top3-exit10-cost45 | 2 | -0.00855 | -0.01661 | -0.00063 | 0.03830 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h3-all-rf-6ef7625d42fd-common-top3-exit10-cost45 | 2 | -0.01780 | -0.02659 | -0.00946 | 0.00030 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 | 2 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h10-all-rf-bedd78069821-common-top3-exit10-cost45 | 2 | -0.00404 | -0.01098 | 0.00248 | 0.16410 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| return_abs-h1-all-xgb-2cb02f543be3-common-top3-exit10-cost45 | 4 | -0.03245 | -0.05874 | -0.00842 | 0.01070 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h2-all-rf-06dc2b7ed8ec-common-top3-exit10-cost45 | 4 | -0.01930 | -0.04130 | 0.00479 | 0.08840 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h3-all-xgb-d139323e99e0-common-top3-exit10-cost45 | 4 | -0.01008 | -0.02864 | 0.00736 | 0.18380 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 | 4 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h10-all-rf-1bbd2af1ad50-common-top3-exit10-cost45 | 4 | -0.01185 | -0.02278 | -0.00126 | 0.03250 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| rank_pct-h1-all-rf-0df3b166dc71-common-top3-exit10-cost45 | 4 | -0.00446 | -0.02058 | 0.01271 | 0.32500 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h2-all-rf-90eeb04f8762-common-top3-exit10-cost45 | 4 | -0.00855 | -0.01494 | -0.00173 | 0.02160 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h3-all-rf-6ef7625d42fd-common-top3-exit10-cost45 | 4 | -0.01780 | -0.02592 | -0.00929 | 0.00010 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 | 4 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h10-all-rf-bedd78069821-common-top3-exit10-cost45 | 4 | -0.00404 | -0.01007 | 0.00222 | 0.14330 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| return_abs-h1-all-xgb-2cb02f543be3-common-top3-exit10-cost45 | 6 | -0.03245 | -0.05821 | -0.00952 | 0.00380 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h2-all-rf-06dc2b7ed8ec-common-top3-exit10-cost45 | 6 | -0.01930 | -0.04021 | 0.00238 | 0.07010 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h3-all-xgb-d139323e99e0-common-top3-exit10-cost45 | 6 | -0.01008 | -0.02654 | 0.00569 | 0.15310 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 | 6 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| return_abs-h10-all-rf-1bbd2af1ad50-common-top3-exit10-cost45 | 6 | -0.01185 | -0.02083 | -0.00287 | 0.01660 | return_abs-h5-all-rf-1273ae260f86-common-top3-exit10-cost45 |
| rank_pct-h1-all-rf-0df3b166dc71-common-top3-exit10-cost45 | 6 | -0.00446 | -0.01994 | 0.01122 | 0.32830 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h2-all-rf-90eeb04f8762-common-top3-exit10-cost45 | 6 | -0.00855 | -0.01550 | -0.00172 | 0.01800 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h3-all-rf-6ef7625d42fd-common-top3-exit10-cost45 | 6 | -0.01780 | -0.02536 | -0.00995 | 0.00000 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 | 6 | 0.00000 | 0.00000 | 0.00000 | 0.00000 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |
| rank_pct-h10-all-rf-bedd78069821-common-top3-exit10-cost45 | 6 | -0.00404 | -0.01020 | 0.00249 | 0.14930 | rank_pct-h5-all-rf-3c5fa028d3f4-common-top3-exit10-cost45 |

## N. Conclusion en trois points

**A. Horizon appris : H5**, premier en rendement cumulé dans chacune des deux familles à durée H5 et à durée H10 fixe. Les IC après open du rapport permettent de distinguer le classement de tout l'univers des quelques titres achetés. Ce constat descriptif ne remplace pas une comparaison prospective des scores.

**B. Durée de détention : H10 pour les scores H5**, qui progressent dans les deux familles, avec capital actif environ doublé et DD accru. H3 reste intéressant pour les scores courts de rendement. Il n'existe pas de durée optimale commune à tous les scores dans cette matrice.

**C. Couple à examiner pour un futur gel : rang RF H5→H10**, +29.70 % net 45 bp, encore +13.42 % à top 10 %. Le maximum de PnL est rendement RF H5→H10 (+35.59 %), mais sa sensibilité à la concentration est bien plus forte. La préférence de recherche pour le rang n'est pas un nouveau choix de modèle ou un lock exécuté ; un futur protocole doit fixer ses hypothèses avant de recevoir les outcomes.

**development evidence only — no independent alpha confirmation.**

## O. Reproduction, tests et sandbox

```bash
uv run python scripts/replay_srd_common_horizons.py
uv run python scripts/publish_srd_common_horizons.py
uv run pytest tests/test_srd_common_replay.py -q
```

Les données et joblib sont locaux, ignorés par Git. Le dossier `data/analysis/srd-horizon-common-replay-v1/` contient le contrat, les cohortes, scores, sélections, ledgers, NAV, matrices, overlap, concentration, audit et résumé.

[Horizon Comparison · Model Lab](https://sandbox.hocus.works/quant-model-lab/) sous authentification. Tests et observation de publication sont enregistrés dans les reçus locaux (`tests.xml` et `sandbox_publication.json`). Le contrôle cash/absence de levier tolère 1e-12 : les valeurs négatives résiduelles, au plus 1,81e-15 de capital, sont des arrondis numériques. Les compteurs legacy `negative_cash_days` comptent tout strict négatif, même ces arrondis ; aucun jour ne dépasse cette tolérance. [Sources et empreintes](SRD_HORIZON_COMMON_REPLAY_RESULTS.sources.json).

**Tests exécutés : 24 passés, 0 échec, 0 ignoré.** Couverture des 25 exigences techniques, réplication déterministe, conservation exacte des scores et comptabilité quotidienne des 375 NAV.
