# Indices — première performance des modèles

**Développement rétrospectif. Scores destinés à une future recherche de features de contexte SRD ; aucune intégration au modèle SRD dans ce run.**

[Contrat fixé avant entraînement](SPEC_008_INDICES_CONTRACT.md). 112 modèles finaux, 160 fits de validation, deux groupes et six targets H5/H10. Train 2024, validation S1 2025, retrain 2024 + S1 2025, test S1 2026.

## Lecture rapide — rang du rendement

| Groupe | Horizon | Modèle | IC validation 2025 | IC test 2026 | Intervalle IC 90 % | Top3 moyen (%) | Groupe mêmes cutoffs (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| market | 5 | linear | -0.07068 | 0.04872 | [-0.035 ; +0.128] | 0.48963 | 0.10059 |
| market | 10 | rf | -0.04854 | -0.01677 | [-0.113 ; +0.092] | 0.79150 | 0.41833 |
| sector | 5 | linear | 0.07949 | 0.07351 | [-0.065 ; +0.192] | 0.23279 | 0.24731 |
| sector | 10 | rf | 0.06194 | 0.15834 | [+0.084 ; +0.226] | 0.97570 | 0.65155 |

Ce résumé reprend les modèles choisis sur validation, sans retenir le meilleur modèle test après coup. La conservation du signe se lit entre validation et test ; les intervalles individuels restent conditionnels au corpus et au protocole. Les paniers top3 représentent deux indices de marché ou un indice sectoriel par cutoff, sans composition.

## Périmètre effectif et disponibilité des features

| group | split | rows | min_series | max_series | registry_ids | entirely_missing | constant_nonmissing | mean_missing_fraction | close_only_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| market | test | 1306 | 54 | 57 | 1048 | 18 | 0 | 0.07978 | 118 |
| market | train | 3081 | 59 | 63 | 1048 | 18 | 0 | 0.15168 | 292 |
| market | validation | 1412 | 56 | 59 | 1048 | 18 | 0 | 0.07199 | 120 |
| sector | test | 584 | 12 | 26 | 1048 | 18 | 0 | 0.01875 | 0 |
| sector | train | 1275 | 13 | 27 | 1048 | 18 | 0 | 0.10015 | 0 |
| sector | validation | 624 | 26 | 26 | 1048 | 18 | 0 | 0.01987 | 0 |

Les 1 048 IDs sont conservés ; colonnes constantes/absentes et masques intraday/volume sont décrits par le contrat. Le nombre de séries varie selon les dates et la qualité à T. En juin 2026, des trous de cotation dans plusieurs STOXX sectoriels déclenchent le seuil de fraîcheur à T et réduisent le panel.

### Durée réelle et couverture des labels

| group | split | horizon | predicted_rows | observed_return_rows | boundary_censored_rows | calendar_missing_rows | median_calendar_days_observed | max_calendar_days_observed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| market | test | 5 | 1306 | 1297 | 0 | 9 | 7.00000 | 11 |
| market | test | 10 | 1252 | 1231 | 0 | 21 | 14.00000 | 18 |
| market | train | 5 | 3081 | 3048 | 0 | 33 | 7.00000 | 11 |
| market | train | 10 | 3021 | 2959 | 0 | 62 | 14.00000 | 18 |
| market | validation | 5 | 1412 | 1401 | 0 | 11 | 7.00000 | 11 |
| market | validation | 10 | 1353 | 1333 | 0 | 20 | 14.00000 | 18 |
| sector | test | 5 | 584 | 570 | 0 | 14 | 7.00000 | 11 |
| sector | test | 10 | 572 | 544 | 0 | 28 | 14.00000 | 18 |
| sector | train | 5 | 1275 | 1260 | 0 | 15 | 7.00000 | 11 |
| sector | train | 10 | 1249 | 1218 | 0 | 31 | 14.00000 | 18 |
| sector | validation | 5 | 624 | 624 | 0 | 0 | 7.00000 | 11 |
| sector | validation | 10 | 598 | 598 | 0 | 0 | 14.00000 | 18 |

H5/H10 comptent les séances du calendrier commun CAC40. La quote native est la dernière connue jusqu'à chaque séance, avec un âge maximal de trois jours calendaires ; un trou plus long rend le label indisponible. Un label franchissant la frontière de période reste censuré, alors que son score à T est conservé. Le panier est choisi avant examen des outcomes et aucun indice sans résultat exploitable n'est remplacé.

**Correction avant publication :** la v1 a été retirée après le contrôle indépendant : une coupe à minuit Paris excluait le close D disponible à minuit UTC D+1, et quelques horizons propres aux séries traversaient des trous de six mois. Les données et modèles v2 ont été entièrement recalculés après correction de l'heure et du calendrier, sans ajustement au résultat test. La v1 reste archivée pour audit. Les snapshots SRD portent déjà minuit Paris et sont cohérents avec leur coupe historique ; leurs artefacts restent conservés. L'export reste `ready_for_srd_integration=false` : le raccordement as-of, les scores OOF et une confirmation indépendante restent à construire.

## Gagnants choisis sur validation — performance test

La sélection est mécanique : AUC pooled de validation pour la direction, IC temporel moyen pour les régressions. Aucun seuil de performance minimale ne force l'abstention. Un meilleur IC encore négatif ne valide donc pas un pouvoir de classement. L'IC d'une baseline à score constant est indéfini ; elle reste visible dans les métriques comparatives.

Les IC sont cross-sectionnels par date, puis moyennés dans le temps. AUC directions : mesure pooled. Les rendements ci-dessous sont en fractions (0.01 = 1 %), **moyennes de fenêtres futures par cutoff**, sans composition. Les paniers ne représentent pas un portefeuille exécuté. Prix en quote native, sans harmonisation de devises ou des conventions de dividendes.

| feature_set | target | horizon | model | validation_mean_ic | mean_ic | roc_auc | r2 | ic_lo90 | ic_hi90 | top3_mean_future_return | universe_mean_future_return | universe_mean_on_top_observed_cutoffs | top_minus_universe | minimum_selected | maximum_selected | top3_observed_cutoffs | top3_complete_cutoffs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| market | direction_abs | 5 | linear | -0.01782 | 0.00710 | 0.51675 | — | -0.06324 | 0.07588 | -0.00452 | 0.00101 | 0.00101 | -0.00553 | 2 | 2 | 23 | 23 |
| market | direction_abs | 10 | linear | 0.00181 | 0.07850 | 0.54213 | — | 0.02689 | 0.13587 | 0.00867 | 0.00418 | 0.00418 | 0.00449 | 2 | 2 | 22 | 21 |
| market | direction_rel | 5 | naive | — | — | 0.50000 | — | — | — | -0.00440 | 0.00101 | 0.00101 | -0.00541 | 2 | 2 | 23 | 21 |
| market | direction_rel | 10 | naive | — | — | 0.50000 | — | — | — | -0.00803 | 0.00418 | 0.00418 | -0.01221 | 2 | 2 | 22 | 18 |
| market | excursion_balance | 5 | linear | -0.03647 | 0.02068 | — | -0.44742 | -0.05905 | 0.09070 | -0.00045 | 0.00101 | 0.00101 | -0.00146 | 2 | 2 | 23 | 23 |
| market | excursion_balance | 10 | rf | -0.01048 | 0.04762 | — | 0.01523 | -0.03702 | 0.13861 | 0.02805 | 0.00418 | 0.00418 | 0.02387 | 2 | 2 | 22 | 19 |
| market | rank_pct | 5 | linear | -0.07068 | 0.04872 | — | -0.53601 | -0.03510 | 0.12772 | 0.00490 | 0.00101 | 0.00101 | 0.00389 | 2 | 2 | 23 | 22 |
| market | rank_pct | 10 | rf | -0.04854 | -0.01677 | — | -0.01597 | -0.11261 | 0.09215 | 0.00792 | 0.00418 | 0.00418 | 0.00373 | 2 | 2 | 22 | 21 |
| market | return_abs | 5 | linear | -0.04927 | 0.04687 | — | -0.47107 | -0.00654 | 0.09448 | 0.00936 | 0.00101 | 0.00101 | 0.00835 | 2 | 2 | 23 | 23 |
| market | return_abs | 10 | xgb | -0.01982 | 0.00328 | — | -0.00860 | -0.07390 | 0.08199 | 0.01174 | 0.00418 | 0.00418 | 0.00756 | 2 | 2 | 22 | 20 |
| market | trend_tstat | 5 | linear | -0.05794 | 0.14804 | — | -1.22388 | 0.10724 | 0.18915 | 0.00645 | 0.00101 | 0.00101 | 0.00545 | 2 | 2 | 23 | 23 |
| market | trend_tstat | 10 | rf | -0.02991 | 0.04203 | — | -0.01935 | -0.04700 | 0.13229 | 0.01840 | 0.00418 | 0.00347 | 0.01493 | 2 | 2 | 21 | 19 |
| sector | direction_abs | 5 | linear | 0.07279 | 0.02484 | 0.50526 | — | -0.04746 | 0.09560 | -0.00311 | 0.00247 | 0.00247 | -0.00558 | 1 | 1 | 23 | 23 |
| sector | direction_abs | 10 | xgb | 0.12353 | 0.07053 | 0.53733 | — | 0.00787 | 0.12875 | 0.02077 | 0.00675 | 0.00717 | 0.01361 | 1 | 1 | 20 | 20 |
| sector | direction_rel | 5 | linear | 0.11165 | 0.03945 | 0.50757 | — | -0.07984 | 0.14536 | 0.00034 | 0.00247 | 0.00247 | -0.00213 | 1 | 1 | 23 | 23 |
| sector | direction_rel | 10 | linear | 0.04756 | 0.06358 | 0.53060 | — | -0.07699 | 0.20658 | 0.01698 | 0.00675 | 0.00675 | 0.01023 | 1 | 1 | 22 | 22 |
| sector | excursion_balance | 5 | linear | 0.06208 | -0.03994 | — | -0.62632 | -0.12464 | 0.03875 | 0.00045 | 0.00247 | 0.00247 | -0.00203 | 1 | 1 | 23 | 23 |
| sector | excursion_balance | 10 | xgb | 0.06078 | 0.13983 | — | -0.00038 | 0.07456 | 0.20329 | 0.00832 | 0.00675 | 0.00675 | 0.00156 | 1 | 1 | 22 | 22 |
| sector | rank_pct | 5 | linear | 0.07949 | 0.07351 | — | -0.65682 | -0.06513 | 0.19152 | 0.00233 | 0.00247 | 0.00247 | -0.00015 | 1 | 1 | 23 | 23 |
| sector | rank_pct | 10 | rf | 0.06194 | 0.15834 | — | 0.02482 | 0.08364 | 0.22594 | 0.00976 | 0.00675 | 0.00652 | 0.00324 | 1 | 1 | 21 | 21 |
| sector | return_abs | 5 | rf | 0.06558 | 0.02898 | — | -0.01716 | -0.03423 | 0.09444 | 0.00834 | 0.00247 | 0.00247 | 0.00586 | 1 | 1 | 23 | 23 |
| sector | return_abs | 10 | xgb | 0.06988 | 0.10787 | — | 0.00953 | 0.01720 | 0.19742 | 0.01790 | 0.00675 | 0.00675 | 0.01115 | 1 | 1 | 22 | 22 |
| sector | trend_tstat | 5 | xgb | -0.02051 | -0.00532 | — | -0.06565 | -0.08150 | 0.06670 | 0.00245 | 0.00247 | 0.00247 | -0.00002 | 1 | 1 | 23 | 23 |
| sector | trend_tstat | 10 | xgb | 0.02995 | 0.11987 | — | 0.01373 | 0.05266 | 0.19381 | 0.02267 | 0.00675 | 0.00717 | 0.01550 | 1 | 1 | 20 | 20 |

Une baseline à score constant donne un panier choisi par identifiant, sans pouvoir de classement. Les labels durs ininterprétables sont absents, sans remplacement d'un titre sélectionné. Les scopes sont classés séparément.

Les moyennes de paniers utilisent les résultats disponibles parmi les choix à T ; la couverture par cutoff est conservée. Un cutoff sans aucun label de panier n'entre pas dans sa moyenne. L'écart au groupe est moyenné sur les cutoffs où les deux moyennes sont calculables.

## Incertitude et dépendances

Intervalles individuels à 90 % par bootstrap circulaire de la moyenne des IC, 10 000 réplications, seed 20261006 ; blocs 2/4/6. Le tableau présente les blocs de 4. Pas de correction multiple ; petit nombre de dates, facteurs communs entre indices et chevauchement H10. Aucun seuil de preuve d'alpha n'est attribué.

## Scores disponibles pour la suite SRD

`historical_index_score_features.parquet` contient 22284 lignes et 996 flux de score pour les gagnants figés sur validation. Uniquement test S1 2026 : dates de disponibilité **modélisées**, date limite d'apprentissage/sélection 30 juin 2025, grade reconstruit explicite, aucun target futur dans cet export. Les prédictions de validation ne sont pas des features historiquement utilisables, car leurs paramètres utilisent la validation complète. Le raccordement SRD doit produire des scores OOF pour 2024/2025, définir le mapping des contextes et réaliser une jointure as-of. Il n'est pas exécuté ici.

## Inventaire des candidats et exclusions

| code | name | research_group | reason |
| --- | --- | --- | --- |
| ABC000000080 | All Ordinaries - Australia | market | equity_market_index |
| ABC000000081 | Hang Seng Index | market | equity_market_index |
| ABC000000083 | RTSI Index - Russie | market | equity_market_index |
| ABC000000084 | Straits Times - Singapour | market | equity_market_index |
| ABC000000085 | KOSPI Composite - Coree | market | equity_market_index |
| ABC000000086 | Bovespa Index - Bresil | market | equity_market_index |
| ABC000000116 | Bombay BSE 30 | market | equity_market_index |
| ABC000000177 | CBOE SKEW INDEX | — | auxiliary_non_equity_signal |
| ABC000000188 | CRB Excess Return Index | — | auxiliary_non_equity_signal |
| ABC000000189 | MSCI World Index | market | equity_market_index |
| ABC003500361 | Nikkei Index | market | equity_market_index |
| ABC003500379 | Nasdaq 100 | market | equity_market_index |
| ABC003500387 | S&P 500 | market | equity_market_index |
| ABC003500395 | Wall Street 30 | market | equity_market_index |
| ABC003500403 | Nasdaq Composite | market | equity_market_index |
| ABC003500437 | IBEX | market | equity_market_index |
| ABC003500445 | Semiconductor Sector | sector | equity_sector_index |
| ABC003500452 | FTSE 100 | market | equity_market_index |
| ABC003500453 | China Shanghai Composite | market | equity_market_index |
| ABC003500458 | Volatility Index VIX | — | auxiliary_non_equity_signal |
| ABC003500461 | VVIX | — | auxiliary_non_equity_signal |
| ABC003500465 | 10-Year T-Note Futures | — | auxiliary_non_equity_signal |
| ABC003500466 | NASDAQ 100 Volatility | — | auxiliary_non_equity_signal |
| ABC003500467 | DAX Volatility | — | auxiliary_non_equity_signal |
| ABC003500468 | DJIA Volatility | — | auxiliary_non_equity_signal |
| ABC003500469 | MSCI China | market | equity_market_index |
| ABC003500470 | MSCI Emerging Markets | market | equity_market_index |
| ABC003500471 | MSCI Europe | market | equity_market_index |
| ABC003500472 | MSCI Europe Ex UK | market | equity_market_index |
| ABC003500473 | MSCI USA | market | equity_market_index |
| ABC003500474 | Nigerian All Share Index | market | equity_market_index |
| ABC003500475 | NIFTY 100 | market | equity_market_index |
| ABC003500476 | NYSE Declining Stocks | — | auxiliary_non_equity_signal |
| ABC003500477 | NYSE Advancing Stocks | — | auxiliary_non_equity_signal |
| ABC003500478 | Topix | market | equity_market_index |
| ABC003500479 | MSCI AC Asia Pacific Index | market | equity_market_index |
| ABC003500480 | MSCI Japan JPY | market | equity_market_index |
| ABC003500481 | MSCI Brazil | market | equity_market_index |
| ABC003500482 | Nikkei 400 | market | equity_market_index |
| ABC003500483 | Baltic Dry Index | — | auxiliary_non_equity_signal |
| ABC003500486 | FTSE 100 Equally weighted 45 point decrement index | — | decrement_or_adjusted_return_product |
| ABC003500495 | Wilshire 5000 Total Market | market | equity_market_index |
| ABC003500504 | VENTES A DECOUVERT - PARIS | — | auxiliary_non_equity_signal |
| ABC003500505 | FTSE Developed Eurozone Top 30 Family Owned Capped Decrement | — | decrement_or_adjusted_return_product |
| ABC003500508 | S&P 500 Equal Weighted | market | equity_market_index |
| BE0004645868 | BEL ESG | market | equity_market_index |
| BE0389549941 | BEL ALL-SHARE | market | equity_market_index |
| BE0389555039 | BEL 20 | market | equity_market_index |
| CH0009980894 | Smi | market | equity_market_index |
| DE0008469008 | DAX 40 | market | equity_market_index |
| DE000A0C3QF1 | STOXX 50 Volatility | — | auxiliary_non_equity_signal |
| DE000SL0BWG3 | Solactive K Thematic Green Transition 5% AR Index | — | decrement_or_adjusted_return_product |
| DE000SL0FEY5 | Solactive K Thematic Millenials 5% AR Index | — | decrement_or_adjusted_return_product |
| DE000SL0G3R5 | Solactive Excellence Europeenne 5% AR | — | decrement_or_adjusted_return_product |
| DE000SL0G3V7 | Solactive Excellence Transatlantique 5% AR | — | decrement_or_adjusted_return_product |
| DE000SL0KKE4 | Solactive Transatlantic Leaders Index 50 points AR | — | decrement_or_adjusted_return_product |
| DE000SLA4ZB0 | Solactive Euro 50 ESG 5.5% AR Index | — | decrement_or_adjusted_return_product |
| DE000SLA8PK3 | Solactive Transatlantique 5% AR Index | — | decrement_or_adjusted_return_product |
| EU0009658145 | Euro Stoxx 50 | market | equity_market_index |
| EU0009658202 | Europe Stoxx 600 | market | equity_market_index |
| FR0003500008 | Cac 40 | market | equity_market_index |
| FR0003502079 | Euronext 100 | market | equity_market_index |
| FR0003502087 | Next 150 | market | equity_market_index |
| FR0003999481 | SBF 120 | market | equity_market_index |
| FR0003999499 | CAC All Tradable | market | equity_market_index |
| FR0012246023 | Euronext PEA-PME 150 Index | market | equity_market_index |
| FR0014002B31 | CAC 40 ESG | market | equity_market_index |
| FRESG0000900 | EN Equileap Gender Equality France40 | market | equity_market_index |
| FRESG0001031 | CAC SBT 1.5 | market | equity_market_index |
| FRESG0002690 | Euronext Earth Focus 40 | market | equity_market_index |
| FRESG0002708 | Euronext Earth Focus 40 NR | — | alternate_variant_same_index_family |
| FRESG0002716 | Euronext Earth Focus 40 GR | — | alternate_variant_same_index_family |
| GRI99117A004 | Athens General Composite | market | equity_market_index |
| IE00B0500264 | ISEQ 20 | market | equity_market_index |
| IT0003465736 | FTSE MIB | market | equity_market_index |
| MIIN00000PIN | MSCI India | market | equity_market_index |
| NL0000000107 | AEX Index | market | equity_market_index |
| NO0000000021 | Oslo OBX Index | market | equity_market_index |
| PTING0200002 | PSI 20 | market | equity_market_index |
| QS0010989109 | Cac Next20 | market | equity_market_index |
| QS0010989117 | CAC Mid 60 | market | equity_market_index |
| QS0010989125 | CAC Small | market | equity_market_index |
| QS0010989133 | CAC Mid & Small | market | equity_market_index |
| QS0010989141 | Cac AllShares | market | equity_market_index |
| QS0011040902 | Euronext Growth All-Share index | market | equity_market_index |
| QS0011095955 | Next Biotech | market | equity_market_index |
| QS0011131826 | CAC 40 NR | — | alternate_variant_same_index_family |
| QS0011131834 | CAC 40 GR | — | alternate_variant_same_index_family |
| QS0011131842 | SBF 120 NR | — | alternate_variant_same_index_family |
| QS0011213657 | CAC Large 60 | market | equity_market_index |
| QS0011213756 | CAC Mid & Small GR | — | alternate_variant_same_index_family |
| US7827001089 | Russell 2000 Index | market | equity_market_index |
| US7837901088 | S&P 100 | market | equity_market_index |
| XC0006170267 | Nasdaq Biotechnology | sector | equity_sector_index |
| XC0009695252 | TSX Composite - Canada | market | equity_market_index |
| EU0009658608 | STOXX Europe 600 Chemicals | sector | equity_sector_index |
| EU0009658624 | STOXX Europe 600 Basic Resources | sector | equity_sector_index |
| EU0009658632 | STOXX Europe 600 Basic Resources | — | alternate_variant_same_index_family |
| EU0009658640 | STOXX Europe 600 Media | sector | equity_sector_index |
| EU0009658681 | STOXX Europe 600 Automobiles & Parts | sector | equity_sector_index |
| EU0009658723 | STOXX Europe 600 Health Care | sector | equity_sector_index |
| EU0009658749 | STOXX Europe 600 Food & Beverage | sector | equity_sector_index |
| EU0009658780 | STOXX Europe 600 Oil & Gas | sector | equity_sector_index |
| EU0009658822 | STOXX Europe 600 Insurance | sector | equity_sector_index |
| EU0009658848 | STOXX Europe 600 Financial Services | sector | equity_sector_index |
| EU0009658889 | STOXX Europe 600 Construction & Materials | sector | equity_sector_index |
| EU0009658905 | STOXX Europe 600 Industrial Goods & Services | sector | equity_sector_index |
| EU0009658921 | STOXX Europe 600 Technology | sector | equity_sector_index |
| EU0009658947 | STOXX Europe 600 Telecommunications | sector | equity_sector_index |
| EU0009658962 | STOXX Europe 600 Utilities | sector | equity_sector_index |
| FR0013506771 | CAC Immobilier | sector | equity_sector_index |
| QS0011017603 | CAC Petrole et Gaz | sector | equity_sector_index |
| QS0011017637 | CAC Materiaux de base | sector | equity_sector_index |
| QS0011017652 | CAC Industries | sector | equity_sector_index |
| QS0011017686 | CAC Biens de consommation | sector | equity_sector_index |
| QS0011017702 | CAC Sante | sector | equity_sector_index |
| QS0011017736 | CAC Services aux consommateurs | sector | equity_sector_index |
| QS0011017769 | CAC Telecommunications | sector | equity_sector_index |
| QS0011017785 | CAC Services aux collectivites | sector | equity_sector_index |
| QS0011017801 | CAC Finances | sector | equity_sector_index |
| QS0011017827 | CAC Technologie | sector | equity_sector_index |

## Artefacts et reproduction

Dossier `data/analysis/spec008-index-model-lab/` : snapshots source, manifestes, modèles, essais, métriques, calibration, déciles et scores. `index_selected_picks.csv` donne les indices sélectionnés et leurs résultats futurs. `index_top3_cutoffs.csv` détaille les paniers et leur couverture. `index_ic_history.html` est un graphique interactif standalone.

Après les commandes data/run du contrat : `uv run python scripts/report_index_models.py`. Aucune modification des données SRD ou du protocole SPEC-007.
