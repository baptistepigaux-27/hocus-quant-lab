# Rang du rendement — actions et performance détaillée

**Random Forest, 1 048 variables, top 3 %, frais aller-retour 25 bp.** Modèles choisis sur validation S1 2025 ; portefeuille simulé du 5 janvier au 30 juin 2026. Aucun nouvel entraînement ou retrait de position.

## Lecture

La target `rank_pct` classe le rendement futur close/close. Le portefeuille achète les cinq titres aux scores les plus élevés à chaque cutoff, au prochain open commun, puis sort au H-ième close commun. Deux compartiments H5, trois H10 : le cash et les compartiments inactifs limitent l'exposition moyenne.

**Rendement moyen par position** : moyenne simple des rendements nets des positions exécutées, pas rendement semestriel buy-and-hold de l'action. **Contribution** : bénéfice/perte réalisé net divisé par le capital initial, en points. Les contributions s'additionnent exactement au rendement du portefeuille. Pour 10 000 € initiaux, 1 point = 100 €.

## Performance des portefeuilles

| horizon | cumulative_return | benchmark_return | max_drawdown | volatility | sharpe | positions | hit_rate | average_trade_return | average_exposure | fees | missing_entries | flagged_closed_positions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | +10.81 | -1.48 | -5.17 | +13.12 | 1.65439 | 113 | +55.75 | +0.94 | +36.64 | +2.99 | 2 | 1 |
| 10 | +17.68 | -1.48 | -4.44 | +13.13 | 2.58659 | 110 | +57.27 | +2.29 | +53.53 | +1.98 | 0 | 1 |

Volatilité/Sharpe annualisés par convention, estimés sur ce seul semestre. Le benchmark est une série de prix, sans dividendes. Les frais sont les sommes payées rapportées au capital initial ; leur somme n'est pas la différence entre simulations brut et net, car les allocations évoluent.

## Rendements mensuels

| horizon | month | portfolio_net | benchmark_price_return | cumulative_net |
| --- | --- | --- | --- | --- |
| 5 | 2026-01 | +0.31 | -1.52 | +0.31 |
| 5 | 2026-02 | +2.66 | +4.31 | +2.97 |
| 5 | 2026-03 | +0.40 | -9.86 | +3.39 |
| 5 | 2026-04 | +3.43 | +3.30 | +6.94 |
| 5 | 2026-05 | +6.91 | +1.91 | +14.33 |
| 5 | 2026-06 | -3.08 | +1.07 | +10.81 |
| 10 | 2026-01 | +0.56 | -1.52 | +0.56 |
| 10 | 2026-02 | +4.49 | +4.31 | +5.07 |
| 10 | 2026-03 | -0.24 | -9.86 | +4.82 |
| 10 | 2026-04 | +4.49 | +3.30 | +9.52 |
| 10 | 2026-05 | +8.97 | +1.91 | +19.34 |
| 10 | 2026-06 | -1.39 | +1.07 | +17.68 |

## Toutes les actions — H10

34 titres sélectionnés ; 34 titres exécutés. Tableau trié par contribution nette. Valeurs de rendement en %, contributions en points.

| display_name | isin | selections | trades_closed | mean_trade_net | worst_trade_net | best_trade_net | contribution_net | flagged_trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stmicroelectronics | NL0000226223 | 8 | 8 | +11.65 | -10.03 | +26.77 | +6.86 | 0 |
| X-FAB | BE0974310428 | 2 | 2 | +22.25 | +8.11 | +36.38 | +3.28 | 1 |
| Guerbet | FR0000032526 | 2 | 2 | +19.54 | +13.77 | +25.31 | +2.75 | 0 |
| Mersen | FR0000039620 | 6 | 6 | +5.77 | -15.81 | +24.52 | +2.48 | 0 |
| Maurel & Prom | FR0000051070 | 9 | 9 | +3.32 | -7.97 | +14.00 | +2.08 | 0 |
| Crédit Agricole Île-de-France (CCI) | FR0000045528 | 4 | 4 | +5.61 | +0.23 | +10.07 | +1.73 | 0 |
| Genfit | FR0004163111 | 9 | 9 | +2.67 | -14.48 | +23.54 | +1.57 | 0 |
| Synergie | FR0000032658 | 2 | 2 | +6.95 | +5.42 | +8.47 | +0.96 | 0 |
| Engie | FR0010208488 | 4 | 4 | +2.63 | -0.81 | +5.80 | +0.71 | 0 |
| Covivio Hotels | FR0000060303 | 1 | 1 | +8.33 | +8.33 | +8.33 | +0.57 | 0 |
| Altamir | FR0000053837 | 3 | 3 | +2.36 | -1.61 | +7.56 | +0.50 | 0 |
| Compagnie Odet | FR0000062234 | 3 | 3 | +2.06 | -12.52 | +14.71 | +0.42 | 0 |
| Ldc | FR001400SF56 | 4 | 4 | +1.25 | -2.57 | +6.33 | +0.34 | 0 |
| Air Liquide / Air Liquide SA | FR0000120073 | 4 | 4 | +1.22 | -1.29 | +6.88 | +0.33 | 0 |
| Lagardere | FR0000130213 | 3 | 3 | +1.45 | -1.95 | +3.54 | +0.29 | 0 |
| Orange / Orange SA | FR0000133308 | 1 | 1 | +2.78 | +2.78 | +2.78 | +0.19 | 0 |
| Carmila | FR0010828137 | 2 | 2 | +1.19 | -1.16 | +3.54 | +0.16 | 0 |
| Axa | FR0000120628 | 2 | 2 | +0.64 | -3.10 | +4.38 | +0.09 | 0 |
| Bouygues | FR0000120503 | 1 | 1 | +1.04 | +1.04 | +1.04 | +0.07 | 0 |
| Rubis | FR0013269123 | 5 | 5 | +0.16 | -8.32 | +5.81 | +0.03 | 0 |
| Danone | FR0000120644 | 1 | 1 | -0.18 | -0.18 | -0.18 | -0.01 | 0 |
| Unibail Rodamco Westfield | FR0013326246 | 2 | 2 | -0.40 | -3.19 | +2.39 | -0.05 | 0 |
| Fnac Darty | FR0011476928 | 5 | 5 | -0.56 | -2.65 | +0.18 | -0.21 | 0 |
| Vallourec | FR0013506730 | 1 | 1 | -3.52 | -3.52 | -3.52 | -0.25 | 0 |
| Eiffage | FR0000130452 | 1 | 1 | -3.83 | -3.83 | -3.83 | -0.26 | 0 |
| Coface | FR0010667147 | 3 | 3 | -1.46 | -4.18 | +1.73 | -0.29 | 0 |
| ABC Arbitrage | FR0004040608 | 9 | 9 | -0.50 | -11.45 | +4.10 | -0.33 | 0 |
| STEF | FR0000064271 | 3 | 3 | -1.55 | -4.72 | +4.72 | -0.33 | 0 |
| Gecina Nom. | FR0010040865 | 1 | 1 | -5.58 | -5.58 | -5.58 | -0.37 | 0 |
| Eramet | FR0000131757 | 3 | 3 | -3.02 | -22.07 | +19.95 | -0.63 | 0 |
| OVHCLOUD | FR0014005HJ9 | 2 | 2 | -4.28 | -12.76 | +4.20 | -0.70 | 0 |
| Crédit Agricole Nord de France (CCI) | FR0000185514 | 1 | 1 | -15.76 | -15.76 | -15.76 | -1.26 | 0 |
| SES Sa | LU0088087324 | 2 | 2 | -9.23 | -12.17 | -6.30 | -1.45 | 0 |
| Biomerieux | FR0013280286 | 1 | 1 | -22.15 | -22.15 | -22.15 | -1.56 | 0 |

### Paniers par date — H10

| cutoff | actions | selections | executed | contribution_net |
| --- | --- | --- | --- | --- |
| 2026-01-02 00:00:00 | Genfit; Orange / Orange SA; Eiffage; Engie; Air Liquide / Air Liquide SA | 5 | 5 | +0.12 |
| 2026-01-09 00:00:00 | Eramet; Rubis; Air Liquide / Air Liquide SA; Gecina Nom.; Unibail Rodamco Westfield | 5 | 5 | +0.87 |
| 2026-01-16 00:00:00 | Eramet; Air Liquide / Air Liquide SA; Bouygues; Rubis; Unibail Rodamco Westfield | 5 | 5 | +0.14 |
| 2026-01-23 00:00:00 | Eramet; Engie; ABC Arbitrage; Altamir; Axa | 5 | 5 | -0.71 |
| 2026-01-30 00:00:00 | Carmila; ABC Arbitrage; Axa; Air Liquide / Air Liquide SA; Lagardere | 5 | 5 | +0.34 |
| 2026-02-06 00:00:00 | ABC Arbitrage; Engie; Lagardere; Coface; Rubis | 5 | 5 | +0.30 |
| 2026-02-13 00:00:00 | Genfit; Coface; ABC Arbitrage; Altamir; Lagardere | 5 | 5 | +2.04 |
| 2026-02-20 00:00:00 | Genfit; Maurel & Prom; Carmila; Rubis; Engie | 5 | 5 | +0.55 |
| 2026-02-27 00:00:00 | Genfit; Maurel & Prom; ABC Arbitrage; Rubis; Compagnie Odet | 5 | 5 | -0.57 |
| 2026-03-06 00:00:00 | Genfit; Maurel & Prom; ABC Arbitrage; Compagnie Odet; Ldc | 5 | 5 | +1.85 |
| 2026-03-13 00:00:00 | Maurel & Prom; Genfit; ABC Arbitrage; Compagnie Odet; Ldc | 5 | 5 | -0.41 |
| 2026-03-20 00:00:00 | Maurel & Prom; Genfit; Synergie; ABC Arbitrage; Ldc | 5 | 5 | -0.94 |
| 2026-03-27 00:00:00 | Maurel & Prom; Synergie; Covivio Hotels; Ldc; Genfit | 5 | 5 | +1.91 |
| 2026-04-10 00:00:00 | Guerbet; Maurel & Prom; Altamir; Genfit; Crédit Agricole Île-de-France (CCI) | 5 | 5 | +1.70 |
| 2026-04-17 00:00:00 | Stmicroelectronics; Maurel & Prom; Guerbet; Biomerieux; STEF | 5 | 5 | +1.64 |
| 2026-04-24 00:00:00 | Stmicroelectronics; X-FAB; Maurel & Prom; Vallourec; Fnac Darty | 5 | 5 | +1.53 |
| 2026-05-08 00:00:00 | Stmicroelectronics; Mersen; Fnac Darty; Crédit Agricole Île-de-France (CCI); Coface | 5 | 5 | +2.31 |
| 2026-05-15 00:00:00 | Stmicroelectronics; Mersen; X-FAB; ABC Arbitrage; Danone | 5 | 5 | +5.62 |
| 2026-05-22 00:00:00 | Stmicroelectronics; Mersen; SES Sa; Fnac Darty; Crédit Agricole Île-de-France (CCI) | 5 | 5 | +1.30 |
| 2026-05-29 00:00:00 | Mersen; SES Sa; Stmicroelectronics; STEF; Crédit Agricole Île-de-France (CCI) | 5 | 5 | +1.49 |
| 2026-06-05 00:00:00 | OVHCLOUD; Stmicroelectronics; Mersen; Crédit Agricole Nord de France (CCI); Fnac Darty | 5 | 5 | +0.12 |
| 2026-06-12 00:00:00 | Stmicroelectronics; Mersen; OVHCLOUD; Fnac Darty; STEF | 5 | 5 | -3.52 |

## Toutes les actions — H5

49 titres sélectionnés ; 48 titres exécutés. Tableau trié par contribution nette. Valeurs de rendement en %, contributions en points.

| display_name | isin | selections | trades_closed | mean_trade_net | worst_trade_net | best_trade_net | contribution_net | flagged_trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stmicroelectronics | NL0000226223 | 9 | 9 | +5.34 | -8.25 | +16.97 | +5.15 | 0 |
| X-FAB | BE0974310428 | 3 | 3 | +9.06 | -7.00 | +34.16 | +3.00 | 1 |
| Eramet | FR0000131757 | 4 | 4 | +5.96 | -15.48 | +18.15 | +2.37 | 0 |
| Genfit | FR0004163111 | 8 | 8 | +1.79 | -5.11 | +9.43 | +1.34 | 0 |
| Legrand SA | FR0010307819 | 1 | 1 | +11.16 | +11.16 | +11.16 | +1.29 | 0 |
| Mersen | FR0000039620 | 7 | 7 | +1.70 | -12.43 | +16.13 | +1.17 | 0 |
| Wendel Invest. | FR0000121204 | 2 | 2 | +4.17 | +2.90 | +5.45 | +0.86 | 0 |
| Airbus / Airbus SE | NL0000235190 | 1 | 1 | +6.77 | +6.77 | +6.77 | +0.71 | 0 |
| Amundi | FR0004125920 | 1 | 1 | +5.42 | +5.42 | +5.42 | +0.57 | 0 |
| Electricite de Strasbourg | FR0000031023 | 1 | 1 | +4.87 | +4.87 | +4.87 | +0.56 | 0 |
| Carmila | FR0010828137 | 2 | 2 | +2.71 | +0.46 | +4.95 | +0.56 | 0 |
| Danone | FR0000120644 | 3 | 3 | +1.49 | -2.35 | +5.52 | +0.52 | 0 |
| Aubay | FR0000063737 | 1 | 1 | +4.03 | +4.03 | +4.03 | +0.41 | 0 |
| Credit Agricole | FR0000045072 | 2 | 2 | +1.98 | +0.32 | +3.63 | +0.41 | 0 |
| Guerbet | FR0000032526 | 1 | 1 | +3.70 | +3.70 | +3.70 | +0.38 | 0 |
| Spie | FR0012757854 | 1 | 1 | +3.61 | +3.61 | +3.61 | +0.36 | 0 |
| Aramis Group | FR0014003U94 | 1 | 1 | +2.33 | +2.33 | +2.33 | +0.25 | 0 |
| TotalEnergies | FR0000120271 | 1 | 1 | +2.21 | +2.21 | +2.21 | +0.23 | 0 |
| Orange / Orange SA | FR0000133308 | 1 | 1 | +1.89 | +1.89 | +1.89 | +0.20 | 0 |
| Manitou | FR0000038606 | 1 | 1 | +1.11 | +1.11 | +1.11 | +0.11 | 0 |
| Axa | FR0000120628 | 3 | 3 | +0.33 | -5.78 | +5.61 | +0.09 | 0 |
| Argan | FR0010481960 | 2 | 2 | +0.31 | -5.44 | +6.07 | +0.07 | 0 |
| Adp | FR0010340141 | 1 | 1 | +0.33 | +0.33 | +0.33 | +0.03 | 0 |
| L'Oreal S.A. / L'oreal | FR0000120321 | 1 | 1 | +0.20 | +0.20 | +0.20 | +0.02 | 0 |
| Covivio | FR0000064578 | 5 | 5 | +0.01 | -4.97 | +6.20 | +0.00 | 0 |
| Nacon | FR0013482791 | 2 | 0 | — | — | — | +0.00 | 0 |
| Mercialys | FR0010241638 | 1 | 1 | -0.06 | -0.06 | -0.06 | -0.01 | 0 |
| Fnac Darty | FR0011476928 | 1 | 1 | -0.25 | -0.25 | -0.25 | -0.03 | 0 |
| STEF | FR0000064271 | 4 | 4 | -0.09 | -3.23 | +2.15 | -0.03 | 0 |
| Eiffage | FR0000130452 | 2 | 2 | -0.13 | -1.17 | +0.92 | -0.03 | 0 |
| Wavestone | FR0013357621 | 1 | 1 | -0.67 | -0.67 | -0.67 | -0.07 | 0 |
| Getlink | FR0010533075 | 1 | 1 | -0.79 | -0.79 | -0.79 | -0.08 | 0 |
| Air Liquide / Air Liquide SA | FR0000120073 | 3 | 3 | -0.35 | -0.49 | -0.29 | -0.11 | 0 |
| ABC Arbitrage | FR0004040608 | 1 | 1 | -1.12 | -1.12 | -1.12 | -0.12 | 0 |
| Valeo | FR0013176526 | 1 | 1 | -2.20 | -2.20 | -2.20 | -0.25 | 0 |
| Bonduelle | FR0000063935 | 2 | 2 | -1.43 | -3.48 | +0.61 | -0.30 | 0 |
| Maurel & Prom | FR0000051070 | 6 | 6 | -0.56 | -13.87 | +11.27 | -0.39 | 0 |
| Gecina Nom. | FR0010040865 | 1 | 1 | -4.15 | -4.15 | -4.15 | -0.43 | 0 |
| Compagnie Odet | FR0000062234 | 1 | 1 | -4.33 | -4.33 | -4.33 | -0.45 | 0 |
| Vinci | FR0000125486 | 2 | 2 | -2.46 | -3.22 | -1.70 | -0.50 | 0 |
| MaaT Pharma | FR0012634822 | 1 | 1 | -5.20 | -5.20 | -5.20 | -0.52 | 0 |
| Biomerieux | FR0013280286 | 3 | 3 | -1.86 | -3.21 | +0.04 | -0.56 | 0 |
| SES Sa | LU0088087324 | 2 | 2 | -2.49 | -11.75 | +6.76 | -0.60 | 0 |
| Elior | FR0011950732 | 1 | 1 | -5.92 | -5.92 | -5.92 | -0.65 | 0 |
| Coface | FR0010667147 | 5 | 5 | -1.47 | -2.77 | -0.31 | -0.73 | 0 |
| Unibail Rodamco Westfield | FR0013326246 | 4 | 4 | -1.82 | -6.50 | +1.63 | -0.77 | 0 |
| Crédit Agricole Nord de France (CCI) | FR0000185514 | 1 | 1 | -7.57 | -7.57 | -7.57 | -0.87 | 0 |
| Rubis | FR0013269123 | 3 | 3 | -2.51 | -8.85 | +0.85 | -0.89 | 0 |
| OVHCLOUD | FR0014005HJ9 | 3 | 3 | -4.32 | -18.33 | +6.55 | -1.50 | 0 |

### Paniers par date — H5

| cutoff | actions | selections | executed | contribution_net |
| --- | --- | --- | --- | --- |
| 2026-01-02 00:00:00 | Genfit; Rubis; Coface; Unibail Rodamco Westfield; Eiffage | 5 | 5 | +0.38 |
| 2026-01-09 00:00:00 | Eramet; Covivio; Unibail Rodamco Westfield; Air Liquide / Air Liquide SA; Vinci | 5 | 5 | +0.54 |
| 2026-01-16 00:00:00 | Eramet; Mercialys; Unibail Rodamco Westfield; Biomerieux; Air Liquide / Air Liquide SA | 5 | 5 | +0.94 |
| 2026-01-23 00:00:00 | Eramet; Axa; Covivio; Air Liquide / Air Liquide SA; Coface | 5 | 5 | -1.55 |
| 2026-01-30 00:00:00 | MaaT Pharma; Manitou; Biomerieux; Fnac Darty; Spie | 5 | 5 | -0.39 |
| 2026-02-06 00:00:00 | Biomerieux; Coface; Covivio; Carmila; Axa | 5 | 5 | -1.19 |
| 2026-02-13 00:00:00 | Genfit; Wavestone; Axa; STEF; Coface | 5 | 5 | +1.25 |
| 2026-02-20 00:00:00 | Nacon; Genfit; Maurel & Prom; Eramet; Coface | 5 | 4 | +3.00 |
| 2026-02-27 00:00:00 | Nacon; Genfit; Maurel & Prom; Aubay; ABC Arbitrage | 5 | 4 | +0.27 |
| 2026-03-06 00:00:00 | Genfit; Maurel & Prom; Bonduelle; Compagnie Odet; Gecina Nom. | 5 | 5 | +0.11 |
| 2026-03-13 00:00:00 | Maurel & Prom; Genfit; Guerbet; Adp; Bonduelle | 5 | 5 | +1.02 |
| 2026-03-20 00:00:00 | Maurel & Prom; Genfit; Credit Agricole; Wendel Invest.; Covivio | 5 | 5 | -1.24 |
| 2026-03-27 00:00:00 | Covivio; Wendel Invest.; Argan; Credit Agricole; Carmila | 5 | 5 | +1.53 |
| 2026-04-10 00:00:00 | Maurel & Prom; Argan; Airbus / Airbus SE; Amundi; L'Oreal S.A. / L'oreal | 5 | 5 | +0.48 |
| 2026-04-17 00:00:00 | Stmicroelectronics; Rubis; TotalEnergies; STEF; Orange / Orange SA | 5 | 5 | +1.92 |
| 2026-04-24 00:00:00 | Stmicroelectronics; X-FAB; Vinci; STEF; Eiffage | 5 | 5 | -0.42 |
| 2026-05-08 00:00:00 | Mersen; Stmicroelectronics; Danone; Getlink; Unibail Rodamco Westfield | 5 | 5 | -0.17 |
| 2026-05-15 00:00:00 | Stmicroelectronics; X-FAB; Mersen; Aramis Group; Danone | 5 | 5 | +3.28 |
| 2026-05-22 00:00:00 | Stmicroelectronics; Mersen; Elior; SES Sa; X-FAB | 5 | 5 | +4.57 |
| 2026-05-29 00:00:00 | SES Sa; Mersen; Stmicroelectronics; Danone; STEF | 5 | 5 | +0.20 |
| 2026-06-05 00:00:00 | OVHCLOUD; Stmicroelectronics; Mersen; Valeo; Crédit Agricole Nord de France (CCI) | 5 | 5 | +0.67 |
| 2026-06-12 00:00:00 | OVHCLOUD; Stmicroelectronics; Mersen; Legrand SA; Rubis | 5 | 5 | +0.13 |
| 2026-06-19 00:00:00 | OVHCLOUD; Electricite de Strasbourg; Stmicroelectronics; Genfit; Mersen | 5 | 5 | -4.53 |

## Mouvement signalé par le contrôle qualité

| horizon | display_name | isin | entry_date | exit_date | entry_price | exit_price | return_net | pnl_net_initial_nav | future_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | X-FAB | BE0974310428 | 2026-05-18 | 2026-05-29 | 7.87000 | 10.76000 | +36.38 | +2.70 | large_move_plausible |
| 5 | X-FAB | BE0974310428 | 2026-05-25 | 2026-05-29 | 8.00000 | 10.76000 | +34.16 | +3.75 | large_move_plausible |

Ces positions restent dans le calcul. L'annotation `large_move_plausible` ne certifie pas la cause du mouvement. Les prix raw et corporate actions restent à vérifier. H5 a également deux entrées Nacon non exécutées ; aucune position n'est retirée après examen de son rendement futur.

## Exports et provenance

Dossier : `data/analysis/spec008-model-lab-all-features/portfolio-top03/rank-detail`. `stocks_h5.csv` / `stocks_h10.csv` : tous les titres. `trades_h5.csv` / `trades_h10.csv` : chaque position, score, ISIN, dates, prix, frais, rendement et contribution. `vintages.csv` : paniers par cutoff. `monthly.csv` / `equity.csv` : trajectoire. `rank_portfolio_detail.html` : courbes et contributions interactives.

Les libellés locaux sont conservés dans `local_label_snapshot.csv`. Les 17 libellés non résolus sont complétés uniquement pour la présentation à partir d'Euronext ; ils ne changent ni features ni scores. Sources :

- [X-FAB — BE0974310428](https://live.euronext.com/en/product/equities/be0974310428-XPAR)

- [Guerbet — FR0000032526](https://live.euronext.com/fr/products/equities/company-news/2026-03-20-guerbet-mise-disposition-du-document-denregistrement)

- [Mersen — FR0000039620](https://live.euronext.com/fr/product/indices/QS0010989117-XPAR)

- [Maurel & Prom — FR0000051070](https://live.euronext.com/fr/product/indices/QS0010989117-XPAR)

- [Crédit Agricole Île-de-France (CCI) — FR0000045528](https://live.euronext.com/sites/default/files/company_press_releases/attachments/2026/04/17/cpr01_notified_Rapport%20financier%20annuel%202025%20-%20Cr%C3%A9dit%20Agricole%20dIle-de-France.pdf)

- [Genfit — FR0004163111](https://live.euronext.com/fr/product/equities/FR0004163111-XPAR/ipo)

- [Synergie — FR0000032658](https://live.euronext.com/fr/products/equities/company-news/2026-04-27-synergie-communique-davis-reunion-assemblee-generale)

- [Fnac Darty — FR0011476928](https://live.euronext.com/en/product/equities/FR0011476928-xpar)

- [ABC Arbitrage — FR0004040608](https://live.euronext.com/fr/products/equities/company-news/2026-05-18-abc-arbitrage-mise-disposition-documents-preparatoires)

- [Crédit Agricole Nord de France (CCI) — FR0000185514](https://live.euronext.com/fr/products/equities/company-news/2026-04-30-credit-agricole-nord-france-resultats-financiers-au-31)

- [MaaT Pharma — FR0012634822](https://live.euronext.com/nl/product/equities/FR0012634822-XPAR)

- [Manitou — FR0000038606](https://live.euronext.com/en/product/equities/FR0000038606-XPAR)

- [Nacon — FR0013482791](https://live.euronext.com/en/ipo-showcase/nacon)

- [Aubay — FR0000063737](https://live.euronext.com/en/product/equities/FR0000063737-XPAR)

- [Bonduelle — FR0000063935](https://live.euronext.com/en/products/equities/company-news/2026-04-08-bonduelle-monthly-statement-number-shares-and-voting)

- [Aramis Group — FR0014003U94](https://live.euronext.com/en/product/equities/FR0014003U94-XPAR)

- [Elior — FR0011950732](https://live.euronext.com/fr/ipo-showcase/elior)


Reproduction : `uv run python scripts/detail_rank_portfolios.py`. Les résultats demeurent du développement sur 2026 déjà exploré ; univers reconstruit et prix non certifiés.
