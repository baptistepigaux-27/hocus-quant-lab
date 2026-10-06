# SRD sans contexte — VAD et détention prolongée

**6 octobre 2026 · développement rétrospectif.** [Contrat et comptabilité](SRD_VAD_HOLDING_CONTRACT.md).

56 modèles, 1 048 variables d'action, scores et gagnants de validation inchangés. Top 3 % à l'achat ; flop 3 % en VAD, allocation **50/50 sans levier**. Les deux horizons de détention sont simulés en long-only et long/short. Aucun entraînement ni choix de modèle sur les résultats ci-dessous.

**Période : décisions S1 2026, valorisation jusqu'au 31 juillet 2026.** Les liquidations H20 peuvent être en juillet. Les résultats sont cumulés, non annualisés. Frais 25/45 bp par aller-retour de chaque position. Le scénario principal ajoute **3 % annuel de coût d'emprunt sur les shorts**, hypothèse de sensibilité, sans tarif de prêt observé.

## Gagnants de validation — 25 bp, emprunt 3 %

| target | horizon | extended_horizon | model | long_only native (%) | long_short native (%) | long_only extended (%) | long_short extended (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | 10 | rf | +2.30 | -3.79 | +5.15 | -0.87 |
| direction_abs | 10 | 20 | naive | +0.12 | +1.25 | -1.56 | -0.19 |
| return_abs | 5 | 10 | rf | +14.05 | +5.22 | +25.34 | +9.91 |
| return_abs | 10 | 20 | rf | +14.74 | +6.40 | +4.73 | -1.84 |
| direction_rel | 5 | 10 | rf | +7.74 | +7.21 | +4.38 | +5.19 |
| direction_rel | 10 | 20 | rf | +11.70 | +8.54 | +6.96 | +6.83 |
| rank_pct | 5 | 10 | rf | +10.81 | +0.08 | +21.98 | +6.96 |
| rank_pct | 10 | 20 | rf | +17.68 | +8.49 | +11.32 | +4.78 |
| excursion_balance | 5 | 10 | xgb | +14.49 | -1.82 | +20.46 | +3.57 |
| excursion_balance | 10 | 20 | linear | +9.24 | -0.07 | +6.41 | +1.84 |
| trend_tstat | 5 | 10 | xgb | +7.77 | +4.71 | +7.53 | +6.83 |
| trend_tstat | 10 | 20 | xgb | -0.67 | -0.88 | +5.35 | -0.93 |

## Gagnants de validation — 45 bp, emprunt 3 %

| target | horizon | extended_horizon | model | long_only native (%) | long_short native (%) | long_only extended (%) | long_short extended (%) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 5 | 10 | rf | +0.01 | -5.96 | +3.57 | -2.37 |
| direction_abs | 10 | 20 | naive | -1.34 | -0.22 | -2.42 | -1.07 |
| return_abs | 5 | 10 | rf | +11.49 | +2.84 | +23.44 | +8.24 |
| return_abs | 10 | 20 | rf | +13.09 | +4.86 | +3.82 | -2.70 |
| direction_rel | 5 | 10 | rf | +5.32 | +4.79 | +2.81 | +3.61 |
| direction_rel | 10 | 20 | rf | +10.06 | +6.96 | +6.02 | +5.90 |
| rank_pct | 5 | 10 | rf | +8.32 | -2.18 | +20.14 | +5.34 |
| rank_pct | 10 | 20 | rf | +15.95 | +6.91 | +10.33 | +3.86 |
| excursion_balance | 5 | 10 | xgb | +11.92 | -4.04 | +18.64 | +2.00 |
| excursion_balance | 10 | 20 | linear | +7.67 | -1.52 | +5.49 | +0.95 |
| trend_tstat | 5 | 10 | xgb | +5.31 | +2.33 | +5.89 | +5.21 |
| trend_tstat | 10 | 20 | xgb | -2.12 | -2.32 | +4.43 | -1.80 |

Le modèle naïf direction absolue H10 prédit une constante : ses achats et shorts proviennent d'un départage arbitraire par ISIN. Il ne fournit aucun classement prédictif, même lorsqu'un panier gagne.

## Rendement du rang — risque et contributions

| horizon | holding_horizon | strategy | cost_bp | cumulative_return | max_drawdown | average_exposure | average_net_exposure | long_contribution | short_contribution | fees | borrow_fees | positions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 10 | long_only | 25 | 0.17679 | -0.04437 | 0.45155 | 0.45155 | 0.17679 | 0.00000 | 0.01975 | 0.00000 | 110 |
| 10 | 10 | long_only | 45 | 0.15954 | -0.04498 | 0.45139 | 0.45139 | 0.15954 | 0.00000 | 0.03527 | 0.00000 | 110 |
| 10 | 10 | long_short | 25 | 0.08492 | -0.04083 | 0.45160 | 0.00247 | 0.08372 | 0.00119 | 0.01859 | 0.00355 | 220 |
| 10 | 10 | long_short | 45 | 0.06911 | -0.04405 | 0.45145 | 0.00247 | 0.07555 | -0.00644 | 0.03320 | 0.00352 | 220 |
| 10 | 20 | long_only | 25 | 0.11316 | -0.06638 | 0.57464 | 0.57464 | 0.11316 | 0.00000 | 0.01166 | 0.00000 | 110 |
| 10 | 20 | long_only | 45 | 0.10331 | -0.06722 | 0.57450 | 0.57450 | 0.10331 | 0.00000 | 0.02090 | 0.00000 | 110 |
| 10 | 20 | long_short | 25 | 0.04779 | -0.04802 | 0.57314 | 0.00495 | 0.05454 | -0.00675 | 0.01109 | 0.00474 | 220 |
| 10 | 20 | long_short | 45 | 0.03860 | -0.04930 | 0.57300 | 0.00495 | 0.04983 | -0.01123 | 0.01986 | 0.00472 | 220 |
| 5 | 5 | long_only | 25 | 0.10806 | -0.05174 | 0.30906 | 0.30906 | 0.10806 | 0.00000 | 0.02986 | 0.00000 | 113 |
| 5 | 5 | long_only | 45 | 0.08320 | -0.05413 | 0.30890 | 0.30890 | 0.08320 | 0.00000 | 0.05310 | 0.00000 | 113 |
| 5 | 5 | long_short | 25 | 0.00078 | -0.06415 | 0.31215 | -0.00182 | 0.04958 | -0.04880 | 0.02769 | 0.00198 | 228 |
| 5 | 5 | long_short | 45 | -0.02184 | -0.08029 | 0.31200 | -0.00182 | 0.03813 | -0.05997 | 0.04925 | 0.00196 | 228 |
| 5 | 10 | long_only | 25 | 0.21978 | -0.08188 | 0.46413 | 0.46413 | 0.21978 | 0.00000 | 0.02072 | 0.00000 | 113 |
| 5 | 10 | long_only | 45 | 0.20135 | -0.08400 | 0.46397 | 0.46397 | 0.20135 | 0.00000 | 0.03699 | 0.00000 | 113 |
| 5 | 10 | long_short | 25 | 0.06957 | -0.05605 | 0.46958 | -0.00244 | 0.09937 | -0.02980 | 0.01901 | 0.00365 | 228 |
| 5 | 10 | long_short | 45 | 0.05335 | -0.05859 | 0.46942 | -0.00244 | 0.09094 | -0.03759 | 0.03395 | 0.00362 | 228 |

Les contributions sont en fraction du capital initial et s'additionnent au rendement cumulé ; ce ne sont pas les moyennes des rendements des titres.

## Sensibilité au prêt des titres — long/short seulement

| target | horizon | holding_horizon | cost_bp | borrow_rate_annual | cumulative_return | max_drawdown | borrow_fees |
| --- | --- | --- | --- | --- | --- | --- | --- |
| direction_abs | 10 | 10 | 25 | 0.00000 | 0.01610 | -0.06139 | 0.00000 |
| direction_abs | 10 | 10 | 25 | 0.03000 | 0.01253 | -0.06260 | 0.00354 |
| direction_abs | 10 | 10 | 45 | 0.00000 | 0.00133 | -0.06605 | 0.00000 |
| direction_abs | 10 | 10 | 45 | 0.03000 | -0.00219 | -0.06725 | 0.00351 |
| direction_abs | 10 | 20 | 25 | 0.00000 | 0.00283 | -0.06995 | 0.00000 |
| direction_abs | 10 | 20 | 25 | 0.03000 | -0.00191 | -0.07157 | 0.00473 |
| direction_abs | 10 | 20 | 45 | 0.00000 | -0.00595 | -0.07268 | 0.00000 |
| direction_abs | 10 | 20 | 45 | 0.03000 | -0.01065 | -0.07430 | 0.00471 |
| direction_abs | 5 | 5 | 25 | 0.00000 | -0.03590 | -0.04865 | 0.00000 |
| direction_abs | 5 | 5 | 25 | 0.03000 | -0.03786 | -0.05027 | 0.00198 |
| direction_abs | 5 | 5 | 45 | 0.00000 | -0.05765 | -0.06593 | 0.00000 |
| direction_abs | 5 | 5 | 45 | 0.03000 | -0.05957 | -0.06751 | 0.00196 |
| direction_abs | 5 | 10 | 25 | 0.00000 | -0.00504 | -0.04968 | 0.00000 |
| direction_abs | 5 | 10 | 25 | 0.03000 | -0.00869 | -0.05036 | 0.00360 |
| direction_abs | 5 | 10 | 45 | 0.00000 | -0.02008 | -0.05537 | 0.00000 |
| direction_abs | 5 | 10 | 45 | 0.03000 | -0.02367 | -0.05831 | 0.00357 |
| direction_rel | 10 | 10 | 25 | 0.00000 | 0.08916 | -0.02779 | 0.00000 |
| direction_rel | 10 | 10 | 25 | 0.03000 | 0.08538 | -0.02797 | 0.00359 |
| direction_rel | 10 | 10 | 45 | 0.00000 | 0.07333 | -0.02875 | 0.00000 |
| direction_rel | 10 | 10 | 45 | 0.03000 | 0.06960 | -0.02893 | 0.00356 |
| direction_rel | 10 | 20 | 25 | 0.00000 | 0.07330 | -0.04855 | 0.00000 |
| direction_rel | 10 | 20 | 25 | 0.03000 | 0.06832 | -0.04960 | 0.00484 |
| direction_rel | 10 | 20 | 45 | 0.00000 | 0.06393 | -0.05051 | 0.00000 |
| direction_rel | 10 | 20 | 45 | 0.03000 | 0.05900 | -0.05157 | 0.00482 |
| direction_rel | 5 | 5 | 25 | 0.00000 | 0.07424 | -0.02152 | 0.00000 |
| direction_rel | 5 | 5 | 25 | 0.03000 | 0.07207 | -0.02184 | 0.00212 |
| direction_rel | 5 | 5 | 45 | 0.00000 | 0.05006 | -0.02542 | 0.00000 |
| direction_rel | 5 | 5 | 45 | 0.03000 | 0.04794 | -0.02575 | 0.00209 |
| direction_rel | 5 | 10 | 25 | 0.00000 | 0.05574 | -0.02865 | 0.00000 |
| direction_rel | 5 | 10 | 25 | 0.03000 | 0.05193 | -0.02920 | 0.00369 |
| direction_rel | 5 | 10 | 45 | 0.00000 | 0.03984 | -0.03094 | 0.00000 |
| direction_rel | 5 | 10 | 45 | 0.03000 | 0.03609 | -0.03150 | 0.00366 |
| excursion_balance | 10 | 10 | 25 | 0.00000 | 0.00285 | -0.07091 | 0.00000 |
| excursion_balance | 10 | 10 | 25 | 0.03000 | -0.00072 | -0.07167 | 0.00346 |
| excursion_balance | 10 | 10 | 45 | 0.00000 | -0.01166 | -0.07403 | 0.00000 |
| excursion_balance | 10 | 10 | 45 | 0.03000 | -0.01517 | -0.07482 | 0.00344 |
| excursion_balance | 10 | 20 | 25 | 0.00000 | 0.02323 | -0.03805 | 0.00000 |
| excursion_balance | 10 | 20 | 25 | 0.03000 | 0.01837 | -0.03895 | 0.00471 |
| excursion_balance | 10 | 20 | 45 | 0.00000 | 0.01433 | -0.03977 | 0.00000 |
| excursion_balance | 10 | 20 | 45 | 0.03000 | 0.00951 | -0.04067 | 0.00469 |
| excursion_balance | 5 | 5 | 25 | 0.00000 | -0.01619 | -0.07709 | 0.00000 |
| excursion_balance | 5 | 5 | 25 | 0.03000 | -0.01820 | -0.07819 | 0.00212 |
| excursion_balance | 5 | 5 | 45 | 0.00000 | -0.03848 | -0.08865 | 0.00000 |
| excursion_balance | 5 | 5 | 45 | 0.03000 | -0.04045 | -0.08974 | 0.00209 |
| excursion_balance | 5 | 10 | 25 | 0.00000 | 0.03957 | -0.04318 | 0.00000 |
| excursion_balance | 5 | 10 | 25 | 0.03000 | 0.03575 | -0.04391 | 0.00387 |
| excursion_balance | 5 | 10 | 45 | 0.00000 | 0.02376 | -0.04605 | 0.00000 |
| excursion_balance | 5 | 10 | 45 | 0.03000 | 0.01999 | -0.04678 | 0.00384 |
| rank_pct | 10 | 10 | 25 | 0.00000 | 0.08870 | -0.04012 | 0.00000 |
| rank_pct | 10 | 10 | 25 | 0.03000 | 0.08492 | -0.04083 | 0.00355 |
| rank_pct | 10 | 10 | 45 | 0.00000 | 0.07284 | -0.04333 | 0.00000 |
| rank_pct | 10 | 10 | 45 | 0.03000 | 0.06911 | -0.04405 | 0.00352 |
| rank_pct | 10 | 20 | 25 | 0.00000 | 0.05272 | -0.04728 | 0.00000 |
| rank_pct | 10 | 20 | 25 | 0.03000 | 0.04779 | -0.04802 | 0.00474 |
| rank_pct | 10 | 20 | 45 | 0.00000 | 0.04349 | -0.04845 | 0.00000 |
| rank_pct | 10 | 20 | 45 | 0.03000 | 0.03860 | -0.04930 | 0.00472 |
| rank_pct | 5 | 5 | 25 | 0.00000 | 0.00283 | -0.06266 | 0.00000 |
| rank_pct | 5 | 5 | 25 | 0.03000 | 0.00078 | -0.06415 | 0.00198 |
| rank_pct | 5 | 5 | 45 | 0.00000 | -0.01984 | -0.07883 | 0.00000 |
| rank_pct | 5 | 5 | 45 | 0.03000 | -0.02184 | -0.08029 | 0.00196 |
| rank_pct | 5 | 10 | 25 | 0.00000 | 0.07348 | -0.05550 | 0.00000 |
| rank_pct | 5 | 10 | 25 | 0.03000 | 0.06957 | -0.05605 | 0.00365 |
| rank_pct | 5 | 10 | 45 | 0.00000 | 0.05721 | -0.05804 | 0.00000 |
| rank_pct | 5 | 10 | 45 | 0.03000 | 0.05335 | -0.05859 | 0.00362 |
| return_abs | 10 | 10 | 25 | 0.00000 | 0.06767 | -0.07413 | 0.00000 |
| return_abs | 10 | 10 | 25 | 0.03000 | 0.06396 | -0.07486 | 0.00347 |
| return_abs | 10 | 10 | 45 | 0.00000 | 0.05222 | -0.07721 | 0.00000 |
| return_abs | 10 | 10 | 45 | 0.03000 | 0.04855 | -0.07794 | 0.00345 |
| return_abs | 10 | 20 | 25 | 0.00000 | -0.01366 | -0.08941 | 0.00000 |
| return_abs | 10 | 20 | 25 | 0.03000 | -0.01837 | -0.09125 | 0.00459 |
| return_abs | 10 | 20 | 45 | 0.00000 | -0.02232 | -0.09264 | 0.00000 |
| return_abs | 10 | 20 | 45 | 0.03000 | -0.02699 | -0.09447 | 0.00457 |
| return_abs | 5 | 5 | 25 | 0.00000 | 0.05432 | -0.04314 | 0.00000 |
| return_abs | 5 | 5 | 25 | 0.03000 | 0.05218 | -0.04354 | 0.00206 |
| return_abs | 5 | 5 | 45 | 0.00000 | 0.03051 | -0.04792 | 0.00000 |
| return_abs | 5 | 5 | 45 | 0.03000 | 0.02842 | -0.04832 | 0.00204 |
| return_abs | 5 | 10 | 25 | 0.00000 | 0.10306 | -0.03906 | 0.00000 |
| return_abs | 5 | 10 | 25 | 0.03000 | 0.09906 | -0.03962 | 0.00380 |
| return_abs | 5 | 10 | 45 | 0.00000 | 0.08633 | -0.04127 | 0.00000 |
| return_abs | 5 | 10 | 45 | 0.03000 | 0.08239 | -0.04183 | 0.00377 |
| trend_tstat | 10 | 10 | 25 | 0.00000 | -0.00527 | -0.05477 | 0.00000 |
| trend_tstat | 10 | 10 | 25 | 0.03000 | -0.00876 | -0.05739 | 0.00344 |
| trend_tstat | 10 | 10 | 45 | 0.00000 | -0.01972 | -0.06513 | 0.00000 |
| trend_tstat | 10 | 10 | 45 | 0.03000 | -0.02316 | -0.06772 | 0.00341 |
| trend_tstat | 10 | 20 | 25 | 0.00000 | -0.00457 | -0.05988 | 0.00000 |
| trend_tstat | 10 | 20 | 25 | 0.03000 | -0.00930 | -0.06313 | 0.00467 |
| trend_tstat | 10 | 20 | 45 | 0.00000 | -0.01332 | -0.06557 | 0.00000 |
| trend_tstat | 10 | 20 | 45 | 0.03000 | -0.01801 | -0.06880 | 0.00465 |
| trend_tstat | 5 | 5 | 25 | 0.00000 | 0.04928 | -0.03379 | 0.00000 |
| trend_tstat | 5 | 5 | 25 | 0.03000 | 0.04712 | -0.03460 | 0.00209 |
| trend_tstat | 5 | 5 | 45 | 0.00000 | 0.02546 | -0.04202 | 0.00000 |
| trend_tstat | 5 | 5 | 45 | 0.03000 | 0.02335 | -0.04282 | 0.00207 |
| trend_tstat | 5 | 10 | 25 | 0.00000 | 0.07222 | -0.04549 | 0.00000 |
| trend_tstat | 5 | 10 | 25 | 0.03000 | 0.06833 | -0.04594 | 0.00375 |
| trend_tstat | 5 | 10 | 45 | 0.00000 | 0.05595 | -0.04742 | 0.00000 |
| trend_tstat | 5 | 10 | 45 | 0.03000 | 0.05212 | -0.04788 | 0.00372 |

Le taux 0 % isole la mécanique des positions. Le taux 3 % est ajouté aux frais de transaction et modifie cash et allocations ; la différence est rejouée directement. Les compartiments restent séparés, sans netting entre vintages ; les oppositions de positions sont mesurées.

## Réconciliation et limites

| native_long_only_curves | native_control_rows | max_native_equity_difference | closed_positions | max_position_gross_pnl_error | max_position_net_pnl_error | short_borrow_positions_recomputed | max_short_borrow_fee_error | all_long_short_selections_disjoint | training_fits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 112 | 13888 | 0.00000 | 125512 | 0.00000 | 0.00000 | 25160 | 0.00000 | True | 0 |

Les courbes long-only natives sont réconciliées à la référence existante au 30 juin, sur les 56 modèles et les deux coûts. PnL signé, frais d'emprunt et identités de NAV/contributions vérifiés sur les ledgers. Les sources restent inchangées.

VAD théorique : disponibilités de prêt, dividendes à payer, rappels de titres, marge et fiscalité par instrument ne sont pas connus. Prix raw/corporate actions et univers SRD survivant ne sont pas certifiés. Les anomalies restent annotées ; aucune sélection perdante n'est retirée ex post.

Les 56 modèles, jambes, paniers et courbes sont disponibles localement dans `data/analysis/srd-portfolio-extensions-v1/`. Les résultats des 12 gagnants se lisent dans le [Model Lab](https://sandbox.hocus.works/quant-model-lab/), onglet **VAD et détention**.

Reproduction : `uv run python scripts/replay_srd_vad_horizons.py`. Une expérience terminée n'est pas écrasée. Les variations de durée changent les compartiments et l'exposition moyenne ; le rapport permet d'examiner ce risque. Aucune confirmation indépendante sur les périodes déjà explorées.
