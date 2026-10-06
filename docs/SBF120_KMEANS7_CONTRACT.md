# SBF 120 — K-means à sept régimes

**Contrat v1, 6 octobre 2026, fixé avant le calcul.**

## Objet

Regrouper les **dates de l'indice SBF 120** (`FR0003999481`) en sept états
historiques à partir de ses 22 features de close. Une ligne est une date, pas une
action composant l'indice. Le périmètre est celui des modèles temporels de grands
marchés, avec la même source ABC et le même calendrier CAC40.

Le K-means est non supervisé : ses centres ne voient aucun rendement futur.
Une table de résultats moyens de 2024, apprise séparément, transforme ensuite
le régime en prévision de direction, rendement ou volatilité H5/H10.

## Construction figée

- Prétraitement et centres ajustés sur les features éligibles du 02/01 au
  31/12/2024. Les features peuvent utiliser l'historique 2022/2023 déjà disponible.
- Médianes d'imputation et standardisation moyenne/écart-type apprises seulement
  sur 2024 ; aucun ajustement sur 2025/2026. Une feature sans valeur finie train
  provoque un arrêt explicite. Les manquants restent documentés.
- K-means euclidien : **K=7**, `k-means++`, 50 initialisations, 500 itérations,
  algorithme Lloyd, seed 20261006. K n'est pas sélectionné sur la performance.
- Chaque variable standardisée a le même poids ; leurs corrélations peuvent
  surpondérer une famille de mesures. Aucune PCA ni pondération supplémentaire.
- Numéros de clusters réordonnés par volatilité historique 20 croissante du
  centre train, puis momentum 20 et identifiant initial. Ce sont des catégories,
  pas une échelle ordinale de signal. Les profils demeurent ceux de 2024.
- Centres et tables de prévision restent **figés sur 2024**. Cela permet de suivre
  les mêmes groupes en S1 2025 et S1 2026 ; aucun retrain ni retournement de signe.

## Tables de prévision

Les labels sont ceux de l'expérience `index-series-models-v1`, avec les purges et
fins de fenêtre déjà définies. Seuls les labels **train** observés terminant en
2024 apprennent la table, jamais ceux de validation/test.

Pour un cluster c, n labels et une moyenne globale train m :

```text
prévision(c) = (somme des labels(c) + 20 × m) / (n + 20)
```

Pour direction, le label est 1 si hausse, 0 si baisse, et les rendements exactement
nuls sont exclus. Si n<10, utiliser la moyenne globale train, et afficher ce
fallback. La règle est identique pour rendement et volatilité. Les tables sont
spécifiques à la target et à H, les sept centres sont partagés entre ces six tâches.

## Évaluation et export

Profils train/validation/test : effectifs, occupation, transitions entre dates
consécutives de la grille, distance aux centres, variables historiques moyennes,
résultats futurs moyens, taux de hausse et rendements médians. Ces résultats futurs
décrivent les groupes ; ils n'interviennent pas dans leur affectation.

Prévisions : mêmes métriques et références que les modèles temporels (prior de
hausse **2024**, rendement zéro, volatilité historique H). La différence de période
de fit avec les modèles supervisés réentraînés jusqu'à juin 2025 est explicite ;
une comparaison directe n'est pas une expérience à budgets d'information égaux.
Pour les régressions, la moyenne train constante est également évaluée afin de
mesurer l'apport des régimes au-delà d'un simple retour à un niveau moyen.

Intervalles individuels 90 % par bootstrap circulaire sur les dates : 5 000 tirages,
blocs H, 2H et 4H. Les centres et tables ne sont pas réajustés dans les tirages.
L'incertitude des centres et la sélection multiple ne sont pas couvertes.

Exporter seulement S1 2025 et S1 2026 : sept indicatrices de cluster, sept distances
euclidiennes standardisées et six prévisions. Disponibilité modélisée à minuit UTC
D+1, fit disponible le 01/01/2025 à minuit UTC. Aucune colonne de résultat futur.
Distances = proximité géométrique, sans interprétation probabiliste. Elles
permettent de constater les états éloignés du support train ; aucune exclusion
automatique selon cette distance.

Le PIT reste reconstruit. 2024–2026 sont des périodes de développement déjà lues.
L'export prépare un futur contexte SRD ; la jointure as-of et la confirmation
indépendante ne sont pas réalisées ici. Aucun portefeuille ni coût de trading.

## Reproduction

```bash
uv run python scripts/sbf120_kmeans.py
```

La commande vérifie les checksums des features/targets parents et refuse de
réécrire une expérience terminée. Config :
[`sbf120_kmeans7_v1.toml`](../configs/experiments/sbf120_kmeans7_v1.toml).
Résultats locaux : `data/analysis/sbf120-kmeans7-v1/`.
