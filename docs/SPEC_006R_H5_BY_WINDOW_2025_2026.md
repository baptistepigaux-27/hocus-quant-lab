# SPEC-006R — Top 100 de 2024 par fenêtre, comparaison 2025–2026

**Calcul : 5 octobre 2026.** Les cohortes restent les mêmes que dans la [comparaison 2024–2025](SPEC_006R_H5_BY_WINDOW.md).

## Méthode

- Univers `equity` : actions ABC Bourse SRD Paris.
- Target fixe : `future.direction_abs.h5.v1` (signe du rendement à cinq séances futures).
- Réutiliser les tops de 100 features par fenêtre historique sélectionnés en 2024 ; aucune sélection nouvelle sur 2025 ou 2026.
- Réutiliser les IC 2025 du scan complet (27 cutoffs, du 06/04 au 04/10).
- Recalculer les IC 2026 sur les mêmes identités et la même méthode `analyze_cutoff`, avec jointure entity/date, rangs moyens pour les ex æquo et filtres research-ready existants.
- 2026 : 27 partitions disponibles du 05/04 au 28/09, dont **25 évaluables** jusqu’au **18/09**. Les targets H5 des deux dernières partitions ne sont pas suffisamment mûres.
- Inversion : signes opposés des **IC moyens** en 2025 et 2026 ; minimum 30 couples par cutoff et 4 cutoffs par relation. Valeurs non finies ou quasi nulles (≤ 1e-12) exclues du dénominateur et comptées séparément.

Toutes les 815 relations sélectionnées sont évaluables sur les 27 cutoffs de 2025 et les 25 cutoffs mûrs de 2026, sans cas nul ou non évaluable.

## Fenêtres standard

| Fenêtre historique (séances) | Relations | Inversions 2024–2025 | Inversions 2025–2026 | Taux 2025–2026 | Sens conservés 2025–2026 |
|---:|---:|---:|---:|---:|---:|
| 3 | 100 | 46/100 | 25/100 | 25 % | 75 |
| 5 | 100 | 54/100 | 17/100 | 17 % | 83 |
| 10 | 100 | 44/100 | 16/100 | 16 % | 84 |
| 20 | 100 | 51/100 | 11/100 | 11 % | 89 |
| 30 | 100 | 68/100 | 15/100 | 15 % | 85 |
| 60 | 100 | 83/100 | 25/100 | 25 % | 75 |
| 120 | 100 | 78/100 | 24/100 | 24 % | 76 |
| 252 | 100 | 62/100 | 20/100 | 20 % | 80 |
| 504 | 0 | — | — | — | 0 |

**153/800 = 19.125 % d’inversions**, soit 647/800 = 80.875 % de signes conservés sur les huit tops de 100.

La fenêtre 504 reste vide : aucune feature admissible lors de la sélection 2024. Le calcul ne remplit pas cette fenêtre avec des variables sélectionnées une autre année.

## Fenêtres fixes des indicateurs techniques

| Fenêtre | Relations | Inversions 2025–2026 |
|---:|---:|---:|
| 13 | 1 | 0 |
| 14 | 7 | 0 |
| 15 | 1 | 0 |
| 16 | 1 | 0 |
| 21 | 1 | 0 |
| 28 | 1 | 0 |
| 34 | 3 | 0 |

Les 15 indicateurs à fenêtre fixe gardent tous leur signe entre 2025 et 2026. Les effectifs par fenêtre sont petits (1 à 7) et ne permettent pas de les interpréter comme des taux précis de stabilité.

## Lecture et limites

- Le sens des associations est plus stable entre 2025 et 2026 que par rapport à 2024 dans toutes les fenêtres standard.
- Stabilité de signe ne signifie pas force prédictive : les IC restent faibles et de nombreuses features sont corrélées.
- La sélection reste fondée sur 2024 ; ces résultats ne décrivent pas un top sélectionné en 2025.
- 2025 utilise sa période complète ; 2026 est partiel. Les amplitudes et les inversions ne doivent pas être interprétées comme une comparaison définitive d’années complètes.
- Le filtre de qualité fondé sur les prix futurs et l’univers SRD reconstruit sont conservés. Le calcul ne constitue ni un modèle négociable, ni un backtest.

## Reproduction et fichiers

```bash
uv run python scripts/compare_h5_windows_2025_2026.py
```

Les résultats sont sous `data/analysis/spec006r-h5-top100-by-window-2025-2026/` (non versionnés) :

- `frozen_2024_selection.parquet` : copie des identités sélectionnées en 2024 et des mesures de référence.
- `ic_history_2026.parquet` : IC par cutoff, effectifs et couverture.
- `signal_comparison.csv` / `.parquet` : les 815 variables avec les IC moyens des trois années et le statut d’inversion 2025–2026.
- `window_summary.csv` : taux et effectifs par fenêtre.
- `audit.json` : source et checksum, périodes, maturité, méthode, cohérence avec l’atlas précédent.

Sur les 500 relations communes à l’atlas H5 précédent, les IC 2026 concordent (écart absolu maximal 1.4e-17) et donnent les mêmes **91 inversions sur 500**. Ruff et MyPy passent pour le script ajouté.

## Incertitude des IC

Les [intervalles et soutiens bootstrap des signes](SPEC_006R_H5_IC_CONFIDENCE.md)
complètent les comptages : 169/800 relations ont le même signe et un soutien
annuel >90 % en 2025 et 2026 pour les trois tailles de blocs, contre 78/800 avec
deux intervalles bilatéraux à 90 % hors de zéro. Ces critères restent individuels,
sans correction des comparaisons multiples.
