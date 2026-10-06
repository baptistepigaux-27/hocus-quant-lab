# Actions seules — modèles H1/H2/H3 et détention H5

**6 octobre 2026 · expérience de développement.**
[Contrat fixé](SRD_SHORT_HORIZONS_CONTRACT.md) · [Journal](RESEARCH_PROGRESS_2026_10_06.md).

## Données et apprentissage

Même corpus ABC SRD et **1 048 features actions**, sans contexte d'indice ni K-means.
Features et sources identiques octet pour octet au benchmark parent : 17 494 lignes,
100 cutoffs. Nouvelles targets sur le calendrier commun observé, sans avancer un prix
manquant. Train 2024, choix sur S1 2025, retrain 2024+S1 2025, lecture S1 2026.
**16 tâches, 74 modèles finaux, 106 fits de validation.**
Gagnants choisis sur validation uniquement : AUC des directions, IC des régressions.
Les 74 variantes sont conservées, et les 16 gagnants présentés ci-dessous.

Tendance/erreur-type indéfinie à H1/H2 ; disponible à H3 avec un seul degré de
liberté, donc fragile. Excursions H1 = 2 × rendement H1 : tâches redondantes.
Les lignes test gardent les actions éligibles à T même si leur label est indisponible.
H1/H2 : 24 décisions ; H3 : 23. Purges et bornes des labels enregistrées.

## Performance brute : avant frais

Top 3 % acheté, **long-only**, sans levier ; entrée au prochain open et sortie au
close de la H-ième séance commune ou H5. Mêmes scores dans chaque paire.
Deux compartiments pour toutes les simulations ; capital initial 1. Les chiffres
sont les rendements **cumulés du portefeuille**, pas annualisés, jusqu'au 31 juillet
2026 avec cash après la dernière liquidation. Toutes les décisions sont en S1.

| Target | H | Modèle validation | IC target | AUC | Brut sortie H (%) | Brut sortie H5 (%) | DD H (%) | DD H5 (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direction absolue | 1 | naive | — | 0.50000 | 2.96900 | 4.00400 | -1.50000 | -6.61000 |
| Direction relative | 1 | xgb | 0.05850 | 0.53700 | 6.72700 | 16.79400 | -1.16000 | -5.97000 |
| Équilibre des excursions | 1 | xgb | -0.02710 | — | 8.09600 | 15.98000 | -1.41000 | -8.34000 |
| Rang du rendement | 1 | rf | 0.03740 | — | 5.04800 | 8.31200 | -1.40000 | -7.54000 |
| Rendement absolu | 1 | xgb | -0.01750 | — | 9.33500 | 15.33300 | -1.95000 | -8.77000 |
| Direction absolue | 2 | naive | — | 0.50000 | 2.87700 | 4.00400 | -3.19000 | -6.61000 |
| Direction relative | 2 | rf | 0.06420 | 0.52860 | 3.99400 | 13.58900 | -2.80000 | -4.10000 |
| Équilibre des excursions | 2 | xgb | 0.01270 | — | 11.11800 | 9.63400 | -3.20000 | -7.02000 |
| Rang du rendement | 2 | rf | 0.02420 | — | 7.07500 | 13.87400 | -2.62000 | -4.70000 |
| Rendement absolu | 2 | rf | 0.02300 | — | 8.75200 | 12.55300 | -4.07000 | -8.23000 |
| Direction absolue | 3 | naive | — | 0.50000 | 10.67500 | 3.89700 | -3.33000 | -6.61000 |
| Direction relative | 3 | rf | 0.08040 | 0.54940 | 8.91800 | 7.57700 | -5.50000 | -5.77000 |
| Équilibre des excursions | 3 | xgb | 0.02680 | — | 22.92100 | 10.41400 | -4.30000 | -4.57000 |
| Rang du rendement | 3 | rf | 0.06590 | — | 8.06600 | 9.94500 | -6.35000 | -8.53000 |
| Rendement absolu | 3 | xgb | 0.04080 | — | 23.47600 | 13.77000 | -2.99000 | -6.88000 |
| Tendance / erreur-type | 3 | rf | 0.03620 | — | 1.33300 | -0.27000 | -3.96000 | -4.97000 |

IC target = moyenne des corrélations cross-sectionnelles par cutoff avec la target
close-à-close ; AUC concerne seulement les deux directions. Une référence naïve
constante classe les titres par identifiant : son top est arbitraire.

## Comparaison à dates communes et après l'open

Les rendements moyens ci-dessous portent sur les **23 dates communes H1/H2/H3**.
Panier = somme des PnL bruts / budget du panier ; une entrée manquante reste en cash.
Excès = différence face au panier équipondéré de tout l'univers éligible avec les
mêmes dates, compartiments et détention. Il ne s'agit pas d'un alpha ajusté des risques.
Les IC après open mesurent un rendement continu, différent des IC des targets de direction.

| Target | H | Panier H (%) | Panier H5 (%) | Excès univers H (pt) | Excès univers H5 (pt) | IC après open H | IC après open H5 | IC gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direction absolue | 1 | 0.28400 | 0.36400 | 0.08000 | 0.21300 | — | — | — |
| Direction relative | 1 | 0.53000 | 1.02300 | 0.32600 | 0.87200 | 0.05460 | 0.03480 | 0.01580 |
| Équilibre des excursions | 1 | 0.59200 | 0.98000 | 0.38800 | 0.82900 | -0.01750 | 0.01510 | -0.03360 |
| Rang du rendement | 1 | 0.42400 | 0.61800 | 0.22000 | 0.46800 | 0.02870 | 0.01800 | 0.03070 |
| Rendement absolu | 1 | 0.69000 | 0.90800 | 0.48600 | 0.75800 | -0.00770 | 0.02070 | -0.02740 |
| Direction absolue | 2 | 0.29800 | 0.36400 | 0.16700 | 0.21300 | — | — | — |
| Direction relative | 2 | 0.26300 | 0.97000 | 0.13200 | 0.81900 | 0.04370 | 0.04180 | 0.02050 |
| Équilibre des excursions | 2 | 0.85900 | 0.51600 | 0.72800 | 0.36600 | 0.04340 | 0.01410 | -0.05370 |
| Rang du rendement | 2 | 0.56000 | 0.90500 | 0.42800 | 0.75400 | 0.01100 | 0.01840 | 0.03700 |
| Rendement absolu | 2 | 0.60300 | 0.52900 | 0.47100 | 0.37800 | 0.03990 | 0.00360 | -0.02870 |
| Direction absolue | 3 | 0.90900 | 0.36400 | 0.57100 | 0.21300 | — | — | — |
| Direction relative | 3 | 0.76500 | 0.66200 | 0.42800 | 0.51100 | 0.06120 | 0.03980 | 0.02010 |
| Équilibre des excursions | 3 | 1.83200 | 0.89300 | 1.49400 | 0.74300 | 0.04750 | 0.02250 | -0.04160 |
| Rang du rendement | 3 | 0.69500 | 0.86000 | 0.35700 | 0.71000 | 0.05540 | 0.02820 | 0.03090 |
| Rendement absolu | 3 | 1.86600 | 1.16300 | 1.52900 | 1.01300 | 0.05400 | 0.03390 | 0.00490 |
| Tendance / erreur-type | 3 | 0.12400 | -0.00500 | -0.21400 | -0.15500 | 0.03970 | 0.01010 | -0.00140 |

La target close T → close T+H comprend un gap qui précède l'entrée simulée.
Identité auditée : `1+target = (1+gap) × (1+rendement après open)`.
Il faut lire IC du gap et IC après l'open séparément ; un bon classement du gap
ne serait pas nécessairement exploitable après cet open.

## Frais : sensibilité 25/45 bp aller-retour

| Target | H | bp AR | Net H (%) | Net H5 (%) |
| --- | --- | --- | --- | --- |
| Direction absolue | 1 | 25 | -0.07600 | 0.92800 |
| Direction absolue | 1 | 45 | -2.44400 | -1.46500 |
| Direction relative | 1 | 25 | 3.56600 | 13.32300 |
| Direction relative | 1 | 45 | 1.10800 | 10.62300 |
| Équilibre des excursions | 1 | 25 | 4.94500 | 12.58400 |
| Équilibre des excursions | 1 | 45 | 2.49400 | 9.94100 |
| Rang du rendement | 1 | 25 | 1.93900 | 5.10300 |
| Rang du rendement | 1 | 45 | -0.47900 | 2.60700 |
| Rendement absolu | 1 | 25 | 6.14700 | 11.95600 |
| Rendement absolu | 1 | 45 | 3.66600 | 9.32800 |
| Direction absolue | 2 | 25 | -0.16500 | 0.92800 |
| Direction absolue | 2 | 45 | -2.53100 | -1.46500 |
| Direction relative | 2 | 25 | 0.91700 | 10.21700 |
| Direction relative | 2 | 45 | -1.47600 | 7.59400 |
| Équilibre des excursions | 2 | 25 | 7.87600 | 6.43000 |
| Équilibre des excursions | 2 | 45 | 5.35300 | 3.93800 |
| Rang du rendement | 2 | 25 | 3.95500 | 10.54800 |
| Rang du rendement | 2 | 45 | 1.52800 | 7.96000 |
| Rendement absolu | 2 | 25 | 5.58100 | 9.26700 |
| Rendement absolu | 2 | 45 | 3.11400 | 6.71000 |
| Direction absolue | 3 | 25 | 7.52700 | 0.94900 |
| Direction absolue | 3 | 45 | 5.07600 | -1.34500 |
| Direction relative | 3 | 25 | 5.82200 | 4.52100 |
| Direction relative | 3 | 45 | 3.41100 | 2.14100 |
| Équilibre des excursions | 3 | 25 | 19.46800 | 7.32000 |
| Équilibre des excursions | 3 | 45 | 16.77900 | 4.91000 |
| Rang du rendement | 3 | 25 | 4.99500 | 6.81900 |
| Rang du rendement | 3 | 45 | 2.60400 | 4.38500 |
| Rendement absolu | 3 | 25 | 20.00700 | 10.57800 |
| Rendement absolu | 3 | 45 | 17.30500 | 8.09200 |
| Tendance / erreur-type | 3 | 25 | -1.53900 | -3.09400 |
| Tendance / erreur-type | 3 | 45 | -3.77500 | -5.29300 |

Forfaits globaux partagés achat/vente ; aucune TTF titre par titre ni minimum de broker.
Pas de VAD dans cette expérience. Même décisions, budgets et NAV recalculés pour les frais.

## Exposition et intégrité

Une détention H5 mobilise le capital plus longtemps : sa performance cumulée ne
mesure pas seule une persistance du signal. Les CSV/Parquet et Marimo affichent
drawdown, capital actif par séance et exposition en fin de séance. À H1, la position
est ouverte puis fermée dans la même séance : **exposition de fin de séance nulle**,
malgré un capital engagé pendant la séance. Le capital actif inclut entrée et sortie,
sans prétendre mesurer des heures exactes d'exposition.

Sur les gagnants bruts : 28 entrées manquantes,
5 sorties retardées,
0 positions non liquidées. Le ledger et la NAV
se réconcilient ; la qualité future annote les trades sans retirer de décision.

### Concentration du résultat brut à la détention native

| Target | H | PnL total (pt) | Cinq meilleurs trades (pt) | Trades en revue | Contribution revue (pt) |
| --- | --- | --- | --- | --- | --- |
| Direction absolue | 1 | 2.96900 | 3.54300 | 0 | 0.00000 |
| Direction absolue | 2 | 2.87700 | 4.64900 | 0 | 0.00000 |
| Direction absolue | 3 | 10.67500 | 9.78800 | 1 | 5.39200 |
| Direction relative | 1 | 6.72700 | 3.48100 | 0 | 0.00000 |
| Direction relative | 2 | 3.99400 | 3.39900 | 0 | 0.00000 |
| Direction relative | 3 | 8.91800 | 9.33500 | 1 | 5.42100 |
| Équilibre des excursions | 1 | 8.09600 | 4.57600 | 0 | 0.00000 |
| Équilibre des excursions | 2 | 11.11800 | 8.50000 | 0 | 0.00000 |
| Équilibre des excursions | 3 | 22.92100 | 16.15600 | 1 | 5.85500 |
| Rang du rendement | 1 | 5.04800 | 4.73500 | 0 | 0.00000 |
| Rang du rendement | 2 | 7.07500 | 6.08600 | 0 | 0.00000 |
| Rang du rendement | 3 | 8.06600 | 6.55400 | 0 | 0.00000 |
| Rendement absolu | 1 | 9.33500 | 4.59200 | 0 | 0.00000 |
| Rendement absolu | 2 | 8.75200 | 9.04200 | 0 | 0.00000 |
| Rendement absolu | 3 | 23.47600 | 15.83400 | 1 | 5.77900 |
| Tendance / erreur-type | 3 | 1.33300 | 3.44900 | 0 | 0.00000 |

Ces contributions sont des points du capital initial ; elles ne sont pas les
rendements individuels des titres. Pour rendement H3, les cinq meilleurs trades
apportent **15,834 points sur 23,476**. Un trade `BE0974310428`, cutoff 22 mai 2026,
entrée à 8 et sortie à 12 (+50 %), contribue **5,779 points** et est marqué `review`.
La cause de cette variation n'est pas certifiée. Il reste inclus : aucune exclusion
favorable après lecture du résultat. Les deux entrées manquantes restent en cash.
Cette concentration et les prix non certifiés limitent particulièrement la lecture
du résultat H3. `top_trades_winners.parquet` conserve les lignes concernées.

## Limites et reproduction

Prix source non certifiés ajustés, corporate actions et univers historique incomplets,
PIT reconstruit ; période déjà explorée et comparaisons multiples sans correction.
Ces résultats restent des simulations de développement, aucune confirmation indépendante.
Grille hebdomadaire conservée : H1 ne signifie pas un nouveau score tous les jours.

```bash
uv run python scripts/srd_short_horizons.py data
uv run python scripts/srd_short_horizons.py run
uv run python scripts/srd_short_horizons.py publish
```

Le run refuse d'écraser des modèles complets. Artefacts locaux non versionnés :
`data/analysis/srd-short-horizons-v1/`. Registre 74 modèles, métriques, scores,
462 replays (444 modèles + 18 univers), ledgers, courbes, paniers, diagnostics des gaps,
audits dataset et artefacts sauvegardés. Sources/checksums dans le fichier compagnon.
