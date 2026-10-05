# SPEC-006R — Incertitude des IC H5, validation 2025–2026

**Calcul : 5 octobre 2026.** Cohorte fixée : les 815 variables du top 100 par fenêtre sélectionné en 2024 (800 de la grille standard, 15 indicateurs à fenêtre fixe). Target `future.direction_abs.h5.v1`, scope `equity`.

## Ce qui est estimé

L’incertitude porte sur la **moyenne temporelle des IC cross-sectionnels de Spearman**, à univers observé fixé. Chaque cutoff fournit une corrélation calculée sur les titres disponibles. Les rendements individuels ne sont pas rééchantillonnés séparément.

2025 contient 27 cutoffs (06/04–04/10) ; 2026 contient 25 cutoffs mûrs (05/04–18/09). Les mesures moyennes recalculées à partir des historiques concordent avec les mesures précédentes.

## Méthode

- Bootstrap circulaire par blocs : tirer des blocs de cutoffs consécutifs avec remise, en autorisant le passage de la dernière date à la première, puis tronquer à la taille de l’échantillon annuel.
- **10 000 réplications**, seed de base `20261005`. Blocs de **2, 4 et 6 cutoffs** ; 4 est la présentation principale, les trois tailles servent à une analyse de sensibilité. Aucune taille n’est choisie en fonction des résultats.
- Toutes les features reçoivent les mêmes tirages de dates dans une année, ce qui conserve leurs dépendances observées. Les tirages des deux années sont indépendants.
- À chaque réplication : moyenne simple des IC des dates tirées, avec le même poids par cutoff.
- Intervalle bilatéral à 90 % : quantiles bootstrap 5 % et 95 %. Intervalle à 95 % : quantiles 2,5 % et 97,5 %.

Ces conventions correspondent au [bootstrap temporel circulaire](https://arch.readthedocs.io/en/stable/bootstrap/timeseries-bootstraps.html) et aux [intervalles par percentiles](https://arch.readthedocs.io/en/latest/bootstrap/confidence-intervals.html). L’implémentation NumPy conserve ces principes sans ajouter de dépendance.

## Bien distinguer les critères

1. **Soutien du signe > 90 % dans une année** : plus de 90 % des moyennes bootstrap ont le même signe que l’IC moyen observé de cette année. C’est une fréquence de rééchantillonnage, pas une probabilité bayésienne que le vrai IC ait ce signe.
2. **Même signe et soutien > 90 % dans chacune des deux années** : les IC observés 2025 et 2026 ont le même signe et passent chacun le critère précédent.
3. **Soutien conjoint > 90 %** : plus de 90 % des paires de réplications 2025–2026 ont des moyennes de même signe. Deux soutiens annuels de 90 % ne garantissent pas 90 % conjointement.
4. **Deux intervalles bilatéraux à 90 % hors de zéro, du même côté** : critère plus strict que le simple soutien > 90 % annuel, car l’intervalle utilise les queues à 5 % et 95 %.

Un critère « sur les trois tailles de blocs » doit être vérifié pour 2, 4 **et** 6 cutoffs, pas seulement pour une taille favorable.

## Résultats sur les huit tops de 100

| Fenêtre historique | Même signe, soutien annuel >90 % sur les 3 blocs | Soutien conjoint >90 % sur les 3 blocs | Intervalles 90 % hors zéro, même côté, sur les 3 blocs |
|---:|---:|---:|---:|
| 3 | 12/100 | 9/100 | 2/100 |
| 5 | 21/100 | 15/100 | 7/100 |
| 10 | 36/100 | 34/100 | 12/100 |
| 20 | 34/100 | 28/100 | 22/100 |
| 30 | 21/100 | 18/100 | 16/100 |
| 60 | 27/100 | 24/100 | 17/100 |
| 120 | 5/100 | 0/100 | 0/100 |
| 252 | 13/100 | 5/100 | 2/100 |

Sur 800 variables : **169** satisfont le critère de soutien annuel >90 %, **133** le critère conjoint >90 %, et **78** le critère des deux intervalles à 90 % hors de zéro, toujours pour les trois tailles de blocs.

Avec le seul bloc de 4 cutoffs, ces nombres seraient respectivement **201, 154 et 101**. Le choix de la taille des blocs change donc les résultats.

Les 15 indicateurs à fenêtre fixe ajoutent 10, 9 et 5 variables respectivement. Sur la cohorte entière de 815 variables, les totaux sont **179, 142 et 83**.

## Exemple concret

`open.level.q90_delta.w30.v1` : écart en pourcentage entre le 90e percentile des opens sur 30 séances et l’open courant.

| Année | IC moyen | Intervalle bilatéral à 90 %, bloc de 4 | Soutien bootstrap du signe positif |
|---|---:|---|---:|
| 2025 | +0.04177 | [+0.01940 ; +0.06520] | 99.97 % |
| 2026 | +0.05463 | [+0.02328 ; +0.08815] | 99.92 % |

Le soutien conjoint de même signe vaut **99.89 %** pour les blocs de 4, avec un minimum de **99.56 %** parmi les tailles 2/4/6. Ce cas est un exemple descriptif choisi après lecture de la validation, pas une sélection indépendante du résultat.

## Limites d’interprétation

- Ces intervalles sont **individuels, sans correction des comparaisons multiples** entre les 815 relations. Les variables retenues par les seuils de soutien ne sont pas automatiquement des découvertes contrôlées à 90 %.
- Le soutien bootstrap ne correspond ni à une p-value, ni à la probabilité que la prochaine action monte, ni à la probabilité que le signal persiste l’année suivante.
- Une couverture nominale de 90 % décrit une procédure répétée sous ses hypothèses ; elle ne donne pas 90 % de probabilité au paramètre une fois l’intervalle observé.
- Les séries ne comportent que 25 ou 27 cutoffs. L’approximation suppose une stabilité raisonnable du processus d’IC sur chaque période ; les blocs ne corrigent pas une rupture de régime, et le raccord circulaire est une approximation.
- Les taux proches du seuil de 90 % ont aussi une incertitude Monte Carlo : avec 10 000 tirages, l’erreur-type de simulation autour de 90 % est environ 0,3 point de pourcentage.
- Le bootstrap ne corrige ni le biais du filtre qualité futur, ni l’univers reconstruit, ni les défauts de prix/corporate actions. Il conditionne l’analyse aux observations déjà retenues.
- Même un signe bien soutenu peut correspondre à un IC faible et à un effet non négociable après frais. Aucun modèle ou backtest n’est construit ici.

## Reproduction et artefacts

```bash
uv run python scripts/bootstrap_h5_ic_confidence.py
```

Résultats sous `data/analysis/spec006r-h5-ic-confidence/` (non versionnés) :

- `ic_intervals.csv` / `.parquet` : intervalles 90 % et 95 %, borne unilatérale 90 % du signe observé, soutiens de signe par année et taille de bloc.
- `sign_comparison.csv` / `.parquet` : signes observés, soutien conjoint, critères annuels et contrôles sur les trois tailles.
- `candidates_joint_sign_support_gt90.csv` : 142 candidats exploratoires, une ligne par variable, soutien conjoint >90 % sur toutes les tailles et intervalles présentés pour le bloc de 4. Cette liste est filtrée après validation et demande de nouvelles données pour une confirmation indépendante.
- `window_summary.csv` / `.parquet` : effectifs par fenêtre.
- `audit.json` : méthode, seeds, sources, checksum de la cohorte et périodes.

Ruff et MyPy passent sur le script. Les tirages ne changent ni les tops gelés en 2024 ni les résultats précédemment publiés.
