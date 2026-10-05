# SPEC-006R — Top 100 de 2024 par fenêtre historique, inversions en 2025

**Calcul : 5 octobre 2026.** Périmètre `equity`, livraison ABC Bourse SRD Paris.

## Ce qui est fixe et ce qui varie

- Target unique : `future.direction_abs.h5.v1`, soit le signe de `close(T+5)/close(T)-1`.
- La fenêtre indiquée dans les résultats appartient à la **feature historique**. La durée future du target reste cinq séances pour chaque ligne.
- Sélection séparée des 100 premières features **dans chaque fenêtre**, parmi toutes les variables admissibles de 2024. Le calcul repart du scan complet, pas des seules variables de l’ancien top 500.
- Chaque couple feature/target conserve son identité en 2025 ; aucune sélection ne dépend des performances 2025.

## Règle de sélection et de comparaison

En 2024 : statut `eligible`, au moins 1 000 couples, 13 cutoffs et 60 % de couverture ; classement q-value croissante, puis amplitude d’IC, couverture et cutoffs décroissants, enfin identifiants. Le classement reprend `q_abs_ic_coverage_cutoff_v1`. Les q-values restent celles du scan complet et sont descriptives.

En 2025 : utiliser l’IC moyen des mêmes couples feature/target sur les 27 cutoffs disponibles. Les définitions du target, son horizon, son échelle et les métadonnées des features sont comparées entre les deux scans. Toutes les variables sélectionnées sont évaluables sur 27 cutoffs.

Une inversion signifie `IC_moyen_2024 × IC_moyen_2025 < 0`. Les valeurs non évaluables ou quasi nulles (amplitude ≤ 1e-12) sont comptées séparément et ne sont pas incluses dans le dénominateur du taux d’inversion. Aucun cas de ce type dans cette sélection.

| Période | Premier cutoff | Dernier cutoff | Dates |
|---|---|---|---:|
| Découverte 2024 | 2024-04-05 | 2024-10-04 | 27 |
| Validation 2025 | 2025-04-06 | 2025-10-04 | 27 |

## Fenêtres standard

| Fenêtre passée (séances) | Candidats 2024 | Top retenu | Inversions 2025 | Taux | Sens conservés | Médiane amplitude IC 2024 | Médiane amplitude IC 2025 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 104 | 100 | 46/100 | 46 % | 54 | 0.01430 | 0.02264 |
| 5 | 110 | 100 | 54/100 | 54 % | 46 | 0.01705 | 0.02563 |
| 10 | 110 | 100 | 44/100 | 44 % | 56 | 0.01624 | 0.02439 |
| 20 | 117 | 100 | 51/100 | 51 % | 49 | 0.01671 | 0.01961 |
| 30 | 110 | 100 | 68/100 | 68 % | 32 | 0.01938 | 0.02285 |
| 60 | 110 | 100 | 83/100 | 83 % | 17 | 0.01773 | 0.02135 |
| 120 | 110 | 100 | 78/100 | 78 % | 22 | 0.02078 | 0.01584 |
| 252 | 110 | 100 | 62/100 | 62 % | 38 | 0.03122 | 0.01599 |
| 504 | 0 | 0 | — | — | 0 | — | — |

Au total, **486/800 = 60.75 %** d’inversions sur les huit tops de 100. Ce total est un comptage descriptif de relations corrélées, pas un test sur des hypothèses indépendantes.

La fenêtre 504 n’a aucune variable admissible : ses 110 relations dans le scan 2024 n’ont que **3 cutoffs** et 475 à 525 couples, contre les seuils de 13 cutoffs et 1 000 couples. Aucune variable d’une autre fenêtre n’est utilisée pour la compléter.

## Fenêtres propres à certains indicateurs techniques

Certaines features ont une fenêtre fixe différente de la grille standard. Elles sont conservées dans le calcul, sans inventer 100 variables là où il en existe moins.

| Fenêtre (séances) | Variables retenues / évaluables | Inversions 2025 | Taux |
|---:|---:|---:|---:|
| 13 | 1 | 0 | 0.0 % |
| 14 | 7 | 3 | 42.9 % |
| 15 | 1 | 0 | 0.0 % |
| 16 | 1 | 0 | 0.0 % |
| 21 | 1 | 0 | 0.0 % |
| 28 | 1 | 1 | 100.0 % |
| 34 | 3 | 2 | 66.7 % |

## Lecture

- Les fenêtres 3, 5, 10 et 20 ont respectivement **46 %, 54 %, 44 % et 51 %** d’inversions. L’inversion de sens massive ne se retrouve pas sur ces fenêtres courtes.
- Les fenêtres 60 et 120 ont **83 % et 78 %** d’inversions. L’instabilité concerne donc aussi la fenêtre historique de la feature, avec un target H5 fixe.
- Les amplitudes médianes des IC restent faibles (environ 0,014 à 0,031 en 2024). Une petite variation peut changer le signe ; compter les inversions ne mesure pas à lui seul une perte de prédictivité.
- La redondance des features, la sélection sur 2024, le filtre de qualité futur et l’univers reconstruit restent les limites du pipeline. Cette analyse n’établit ni une cause économique ni un alpha exploitable.

## Reproduction et livrables

```bash
uv run python scripts/compare_h5_by_feature_window.py
```

Le script lit les deux scans existants en lecture seule. Il écrit sous `data/analysis/spec006r-h5-top100-by-window/` :

- `frozen_top100_by_feature_window.parquet` : sélection complète enregistrée avant lecture des métriques 2025.
- `signal_comparison.csv` et `.parquet` : **815 variables**, rang par fenêtre, IC 2024 et 2025, statut d’inversion et ratio d’amplitude.
- `window_summary.csv` : comptages par fenêtre.
- `audit.json` : paramètres, périodes, provenances des deux scans et effectifs.

Les 815 variables comprennent 800 features de la grille standard et 15 indicateurs à fenêtre fixe. Les fichiers sous `data/` restent non versionnés.

Les 500 relations communes avec l’atlas H5 précédent donnent les mêmes IC 2025 à l’arrondi numérique près (écart absolu maximal ≈ 2,1 × 10^-17).

## Suite : comparaison 2025–2026

La [comparaison 2025–2026](SPEC_006R_H5_BY_WINDOW_2025_2026.md) reprend exactement
ces tops sélectionnés en 2024. Les huit tops de 100 donnent 153/800 inversions
(19,125 %), avec une période 2026 partielle.
