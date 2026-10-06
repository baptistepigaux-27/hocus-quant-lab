# SRD — intégration des contextes de marché

**Contrat v1, 6 octobre 2026, fixé avant calcul des résultats SRD enrichis.**

## Objet

Ajouter aux 1 048 features propres à chaque action SRD :

| Bloc | Définition | Colonnes |
| --- | --- | ---: |
| K-means SBF 120 | Sept indicatrices de régime, sept distances aux centres, six prévisions par régime H5/H10 | 20 |
| Indices sectoriels | Six familles de prévisions H5/H10 pour chacun des 27 indices du corpus sectoriel | 324 |
| CAC40 et SBF120 | Direction, rendement, volatilité H5/H10, modèles séparés par indice | 12 |
| Total contexte | Vecteur de marché partagé par les actions d'une même date | **356** |
| SRD enrichi | 1 048 features action + 356 contextes | **1 404** |

Tous les secteurs sont transmis comme contexte global. Aucun rattachement sectoriel
historique action/indice n'est inventé. Les arbres peuvent apprendre des interactions
entre caractéristiques d'action et contexte ; une variable constante dans la coupe
ne produit pas à elle seule un classement des actions.

## Prédictions historiques sans apprentissage sur leur propre futur

Les exports existants des indices sont limités au test 2026. Leurs gagnants et
paramètres ont utilisé S1 2025. Ils ne sont donc pas utilisés pour remplir 2024/2025.
Les centres du K-means initial, ajustés sur 2024, ne sont pas utilisables à T en 2024.

Cette expérience ajoute une variante historique :

- **Amorçage 2023**, à partir des mêmes quotes livrées depuis septembre 2022.
- **Sept centres SBF120 fixés sur 2023**, même algorithme et 22 variables de close.
  Centres, médianes et standardisation restent identiques sur toute l'expérience.
  Les groupes sont numérotés par volatilité 20 du centre train, puis momentum 20.
  Les C1…C7 sont propres à cette variante, pas les centres du précédent fit 2024.
- **Prédicteurs de contexte RF fixés à l'avance** : 80 arbres, profondeur 4,
  feuille minimale 30, fraction de variables 0,5. Pas de sélection d'un gagnant
  ayant déjà vu 2025/2026. Les six targets sectoriels conservent leurs définitions
  canoniques ; CAC40/SBF120 utilisent les trois targets temporels précédents.
- **Ajustements expansifs trimestriels** avant chaque trimestre de 2024 et de
  S1 2025. Chaque fit utilise seulement features et fins de labels déjà disponibles
  avant le début du bloc. Les fenêtres futures traversant cette borne sont purgées.
- **Test S1 2026** : contexte entraîné uniquement avec information antérieure au
  01/07/2025, pour conserver la borne de retrain du SRD. Aucune observation S2 2025
  ou 2026 n'entre dans le fit des producteurs de contexte.
- **Tables K-means** : moyennes par cluster apprises sur ces mêmes labels historiques,
  shrinkage de 20 labels vers la moyenne globale ; fallback global si n<10.

Les folds et hyperparamètres sont dans
[`srd_context_v1.toml`](../configs/experiments/srd_context_v1.toml). Un manque de
labels de contexte produit un statut d'indisponibilité, sans score fictif.
Les contextes ne voient aucun label d'action SRD.

## Sources et disponibilité

Les 27 secteurs et leurs identités viennent du snapshot d'indices publié v2.
Features sectorielles : registre de 1 048 variables, volumes masqués, gabarits
close-only identiques. L'amorçage 2023 est recalculé depuis les mêmes sources.
Les matrices de prix CAC40/SBF120 sont alignées sur le calendrier quotidien CAC40.
Quotes manquantes : dernier close connu avec âge maximal de trois jours ; au-delà,
absence explicite. Aucun remplissage par un prix futur.

Les labels des producteurs de contexte suivent les prochaines séances du calendrier
CAC40. Les ruptures futures ne retirent pas un score à T. Les prix positifs finis et
fenêtres complètes restent nécessaires pour observer un label. L'éligibilité des
secteurs reste celle de la qualité **passée** au cutoff.

L'information des indices est disponible à **minuit UTC D+1**, plus tard que
l'heure historique du snapshot SRD (minuit Paris D+1). La décision commune de
l'expérience enrichie est donc **minuit UTC D+1**, avant l'open suivant : features
actions déjà disponibles, puis contextes effectivement disponibles. Les prix et
labels actions ne changent pas. Une jointure as-of impose :

```text
source_available_at <= decision_at
fit_information_available_at <= source_available_at
max_training_label_available_at <= fit_information_available_at
```

Le ledger conserve source, fold, modèle, âge du dernier prix, dates du fit et
disponibilité. Une absence de contexte reste NaN ; elle ne retire aucune action
ni ne modifie les labels SRD. Disponibilités **modélisées**, PIT toujours reconstruit.

## Comparaison SRD et simulations

Même cohorte, mêmes labels, mêmes formules de features d'action, splits et purges
que `spec008-model-lab-all-features`. Six targets SRD × H5/H10. Naïfs, linéaires,
RF et XGBoost, mêmes grilles et seed que le benchmark parent. Prétraitements
appris uniquement dans le train SRD ; sélection exclusivement S1 2025 ; retrain
2024+S1 2025 ; lecture de S1 2026 ensuite.

La référence 1 048 variables garde ses modèles et scores existants. La nouvelle
sélection se fait sur validation avec 1 404 variables. Le rapport compare les
gagnants choisis séparément, ainsi que les mêmes familles de modèles. Les
hyperparamètres peuvent donc différer après sélection ; l'écart n'est pas une
décomposition causale de chaque bloc de contexte.

Portefeuilles **top 3 %**, compartiments H5/H10 inchangés, entrée prochain open et
sortie au H-ième close commun. Replays directs à **25 et 45 bp aller-retour**.
Les frais restent des forfaits ; minimum par ordre, TTF par instrument et spread
effectif ne sont pas modélisés. Paniers, contributions et ledgers sont conservés.

Le rapport décrit les écarts d'IC par cutoff, AUC/calibration, rendement net et
drawdown. Bootstrap apparié sur les cutoffs pour les écarts d'IC, blocs 2/4/6,
5 000 tirages ; intervalles individuels 90 %, sans correction multiple. Les gains
et importances des arbres sont descriptifs. Aucune permutation de milliers de
colonnes ni sélection complémentaire sur le test n'est effectuée.

## Statut scientifique et isolation

2024–2026 ont déjà été explorées. Le jeu de contextes et cette expérience constituent
du développement rétrospectif, sans confirmation indépendante ni certification de
prix ajustés. L'univers SRD livré n'est pas un SBF 120 historique reconstitué.
Le protocole SPEC-007, les modèles précédents et leurs artefacts restent conservés.

Résultats locaux dans `data/analysis/srd-context-v1/`, ignorés par Git. Contrat,
configs, scripts, rapport et empreintes sont versionnés. Le sandbox lira les
artefacts précalculés ; aucun entraînement dans l'interface.

## Commandes

```bash
uv run python scripts/srd_context.py inputs
uv run python scripts/srd_context.py context
uv run python scripts/srd_context.py data
uv run python scripts/srd_context.py run --workers 2
uv run python scripts/srd_context.py publish
```

Les douze tâches SRD sont indépendantes et peuvent tourner deux par deux, à quatre
threads par estimateur. La parallélisation change seulement leur ordre d'exécution ;
grilles, seed, lignes et sélection restent identiques. Les dossiers `task_runs/`
conservent chaque tâche complète et permettent une reprise. L'essai séquentiel
initial a été conservé localement avant le lancement en parallèle. Les outputs
publics réunissent 56 modèles et deux références de portefeuille, rejoués à chaque
coût. Une expérience terminée exige une nouvelle version pour être recalculée.
