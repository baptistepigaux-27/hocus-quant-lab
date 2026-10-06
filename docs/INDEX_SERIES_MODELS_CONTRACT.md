# Grands marchés — modèles propres à chaque série

**Contrat v1 fixé avant entraînement, 6 octobre 2026.**

## Objet et périmètre

Un estimateur distinct apprend sur les dates d'un seul indice et prédit son résultat
futur. Les cinq indices confirmés sont CAC40, SBF120, S&P500, DAX40 et FTSE100.
Les poids, les paramètres de prétraitement et les hyperparamètres sont propres
à chaque indice/target/horizon. Aucun identifiant d'indice n'entre dans les variables.
Il n'y a ni pooling d'indices dans un fit, ni classement cross-sectionnel.

Les futurs scores doivent servir de contexte aux modèles SRD. Cette première phase
mesure la prévision temporelle ; elle ne spécifie pas une stratégie d'exécution.

## Données, dates et disponibilité

Le snapshot ABC de l'expérience indices v2 est copié et vérifié par checksum.
Son historique couvre septembre 2022 à septembre 2026. Les disponibilités source
sont `session_date + 1 jour à 00:00 UTC`, soit 01:00/02:00 Paris. Vintages historiques
non certifiés : le grade reste reconstruit, sans revendication de PIT strict.

Les coupes sont **quotidiennes sur le calendrier CAC40** pour préparer le contexte
SRD. Pour chaque indice/date, le prix est le dernier close natif connu jusqu'à la
date, avec âge maximal de trois jours calendaires. Un jour férié peut conserver
le dernier close connu ; les absences plus longues restent nulles. Aucun prix
ultérieur n'est utilisé pour remplir une date. Les quotes OHLC/volume ne sont pas
utilisées dans cette première version ; les devises et conventions de dividendes
restent natives.

## Variables figées : 22

- Trois rendements journaliers retardés : courant, lag 1, lag 2.
- Momentum cumulé sur 3, 5, 10, 20, 60, 120 séances de référence.
- Volatilité historique annualisée sur 5, 10, 20, 60 rendements.
- Distance à la moyenne des closes sur 5, 20, 60, 120 séances.
- Écart au maximum de close sur 20 et 60 séances.
- Position dans le range des closes sur 20 et 60 séances.
- RSI simple sur 14 rendements, normalisé entre 0 et 1.

Une fenêtre comprenant une absence non remplissable reste indisponible. Momentum
nécessite W+1 closes, volatilité W rendements (écart-type échantillonnal), moyennes
et ranges W closes. RSI utilise les moyennes simples des gains/pertes ; absence
de pertes donne 1, série plate 0,5. Range nul donne 0,5. Aucun tri de variables
sur leurs performances de validation ou test n'est effectué.

## Targets H5/H10

Les H closes futurs sont ceux des H prochaines séances du calendrier de référence.
Un close requis absent invalide le label, sans retirer le score possible à T.

- **Rendement :** `close(T+H) / close(T) - 1`.
- **Direction :** +1, 0 ou −1 selon le rendement. Les zéros restent dans le ledger
  et sont exclus du fit binaire et des métriques de direction.
- **Volatilité :** écart-type échantillonnal des H log-rendements de T à T+H,
  multiplié par √252. Le rendement T→T+1 est inclus. Les prévisions négatives
  de volatilité sont bornées à zéro selon une règle fixée avant fitting.

L'éligibilité à T dépend uniquement d'un close connu et valide à T. Les labels
inobservables sont explicitement conservés comme absents. Les ruptures ≥30 %
restent des annotations, sans exclusion liée à l'amplitude future.

## Entraînement et sélection

Train 2024, validation S1 2025, retrain 2024 + S1 2025, test S1 2026. La purge
H séances et le contrôle de fin réelle du label empêchent de franchir un split.
Chaque fit exige au moins 100 labels train et 50 labels validation.

Modèles : logit/Ridge régularisés, forêt aléatoire peu profonde, XGBoost peu profond.
Grilles et seed sont dans `configs/experiments/index_series_v1.toml`. Médianes,
indicateurs de manquants et standardisation sont appris dans le train seulement,
puis réappris dans le retrain déclaré. Les arbres XGBoost traitent les NaN nativement.

Références : fréquence de hausse historique pour direction ; zéro et moyenne
historique pour rendement ; volatilité historique sur H et moyenne train pour
volatilité. Une référence simple peut gagner la sélection.

Choix sur validation : log-loss minimale pour direction, RMSE minimale pour
régressions, puis ordre stable pour les ex æquo. Les résultats test ne choisissent
ni modèle, ni sens, ni variables. Le classement des modèles est propre à chaque
indice/target/horizon, sans partage entre indices.

## Évaluation temporelle et incertitude

Direction : AUC sur les dates du seul indice, log-loss, Brier, accuracy et balanced
accuracy. Régressions : RMSE, MAE, R², corrélation de rang **temporelle** entre
prévisions et résultats. Ce coefficient n'est pas un IC cross-sectionnel.

Comparaison appariée des pertes au benchmark : fréquence historique, rendement
zéro, ou volatilité historique H, respectivement. Le skill est
`1 - perte_modèle / perte_référence` (log-loss ou MSE). Une valeur négative est
un résultat moins bon que la référence. Les n et absences sont affichés.

Bootstrap circulaire sur les dates test, 5 000 réplications, blocs 5/10/20 pour H5
et 10/20/40 pour H10. Les labels manquants restent dans la grille des dates.
Intervalles individuels 90 %, sensibles au peu de fenêtres indépendantes, sans
correction multiple et conditionnels aux modèles ajustés. Aucune probabilité
d'alpha n'est attribuée. 2024–2026 sont des périodes de développement déjà explorées.

## Export pour une future expérience SRD

Seuls les scores test 2026 des gagnants figés sur validation sont exportés, avec
disponibilité modélisée, fin d'apprentissage/sélection, grade et modèle d'origine.
Ils ne contiennent pas le résultat futur. Pour un raccordement sur 2024/2025,
produire des scores OOF avec sélection roulante et une jointure as-of. La présente
phase conserve les expériences précédentes et SPEC-007.
