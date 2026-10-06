# SRD — contrat de comparaison des horizons et de l'exécution

**6 octobre 2026 · version 2 · paramètres utilisateur appliqués au replay livré.**

**Statut :** replay de développement exécuté : [résultats et quatorze réponses](SRD_HORIZON_COMMON_REPLAY_RESULTS.md),
[matrices](SRD_HORIZON_COMMON_REPLAY_MATRICES.md). Dix modèles gelés, 22 cutoffs,
360 stratégies et 15 références. Les anciennes simulations restent des expériences distinctes.

**Amendement avant calcul :** la consigne utilisateur a remplacé les quatre
compartiments et l'extension H20 de la version 1 par **deux compartiments** et
la matrice triangulaire H1/H2/H3/H5/H10. La
[configuration scellée](../configs/experiments/srd_horizon_common_replay_v1.json)
précède la lecture des résultats. Il ne s'agit pas d'un ajustement selon le PnL.

## 1. Question et références

Séparer deux questions : **quel horizon appris fournit le meilleur classement à
durée de détention fixée ?** Et **que change la durée de détention pour les mêmes scores ?**

Les références sont les modèles actions seuls, 1 048 features, gagnants figés sur
la validation S1 2025 : [H1/H2/H3](SRD_SHORT_HORIZONS_CONTRACT.md),
[H5/H10](SPEC_008_ALL_FEATURES.md) et [prolongations](SRD_VAD_HOLDING_CONTRACT.md).
Les contextes de marché restent un facteur d'expérience séparé.
L'[audit des prix](SRD_PRICE_AUDIT.md) doit accompagner les replays.

Le choix des durées et critères intervient après exploration de 2026. Une
amélioration sur ces données constituera du développement, sans confirmation indépendante.

## 2. Matrice fixée et exécutée

| Horizon du score appris | Durées de détention à relire |
| ---: | --- |
| H1 | 1, 2, 3, 5, 10 séances communes |
| H2 | 2, 3, 5, 10 séances communes |
| H3 | 3, 5, 10 séances communes |
| H5 | 5, 10 séances communes |
| H10 | 10 séances communes |

Les deux familles exécutées sont **rendement absolu** et **rang du rendement**,
soit dix gagnants choisis sur validation 2025 et réutilisés sans refit.
Directions constantes, excursions et tendance ne sont pas ajoutées à ce replay.
Les features/actions et scores restent exactement ceux des expériences sources.
Top 3 % principal et top 10 % de sensibilité, aucune autre concentration.

Les scénarios sont **brut, 25 et 45 bp aller-retour**. La VAD n'entre pas dans cette
première comparaison commune long-only. Elle pourra être relue séparément avec
son allocation 50/50 et ses contraintes de prêt.

## 3. Horloge, calendrier et cohorte

| Objet | Règle |
| --- | --- |
| Décision | Après disponibilité de toutes les entrées ; borne commune 00:00 UTC le lendemain du cutoff |
| Features | Informations connues au cutoff ; disponibilité vérifiée, aucune donnée future |
| Admission des titres | Cohorte issue des features et de l'éligibilité connue à T ; ne pas la restreindre selon les rendements futurs |
| Calendrier d'exécution | Union des séances actions observées, rapprochée du snapshot CAC AllShares ; aucune date actions seule dans la période, certification de place indépendante non revendiquée |
| Achat | Open réellement traité de la première séance après le cutoff, postérieur à la décision |
| Sortie native ou prolongée | Close de la H-ième séance de la grille commune, entrée incluse ; H1 = open→close de la séance d'entrée |
| Prix absent à l'entrée | Allocation laissée en cash, sans remplacement du titre |
| Prix absent à la sortie | Attente du premier close réellement traité ; retard et mark stale signalés ; pas de fill à un prix indicatif de suspension |
| Qualité future | Annotation ; aucune exclusion destinée à améliorer les résultats |
| Erreur forte documentée | Nouveau vintage/correction sourcée ou résultat indisponible explicitement signalé ; conservation du cas et des versions originales |

La grille actuelle des replays est l'union des dates observées des actions.
La remplacer par une grille de place demande un rapprochement documenté ;
ne pas prétendre que la grille observée est déjà certifiée officiellement.

### Inventaire réalisé sur les scores existants

| Scores | Dates test présentes | Dernier cutoff |
| --- | ---: | --- |
| H1, H2 | 24 chacun | 26/06/2026 |
| H3 | 23 | 19/06/2026 |
| H5 actions seules | 23 | 19/06/2026 |
| H10 actions seules | 22 | 12/06/2026 |
| **Intersection H1 à H10** | **22** | **12/06/2026** |

Cette intersection commence le **2 janvier 2026**. Sa liste exacte est dans
`data/analysis/srd-price-audit-v1/common_cutoffs.json`.
Les résultats actuels couvrant davantage de dates ne doivent pas être présentés
comme les performances de cette nouvelle intersection.

Pour chaque date commune, comparer les mêmes titres éligibles à T. Les fichiers
de prédictions existants peuvent avoir des lignes différentes selon la disponibilité
des labels ; **leur intersection d'entités ne suffit pas à reconstruire une cohorte ex ante**.
Rapprocher features et registres d'éligibilité ; produire les scores absents depuis
les modèles sauvegardés, sans refit. Les outcomes manquants restent dénombrés.

Le rapprochement a trouvé des features et registres d'éligibilité byte-identiques :
**159–164 actions**, univers natif = commun, aucun instrument exclu par intersection.
Les **35 730 scores** préexistants couvrent toutes les lignes de ces dix modèles ;
aucune inférence complémentaire n'est requise. Le rejeu des estimateurs sauvegardés
corrobore ces scores, ensuite conservés à l'identique. Les targets relatives et
prévisions de contexte ne participent pas à cette expérience.

## 4. Deux niveaux de comparaison

### A. Qualité des scores et paniers par décision

Sur les mêmes dates et cohortes, conserver les classements puis mesurer :

- IC entre score et rendement **après open**, par date, pour chaque détention ;
- IC du score avec le gap close→open, pour distinguer une association non capturable ;
- panier top 3 %, équipondéré, et rendement de l'univers éligible équipondéré ;
- excès du panier sur cet univers, rang du titre, couverture et ex æquo ;
- distributions des gains/pertes et contributions, pas seulement leur moyenne.

Les paniers sont des diagnostics par décision, sans capitalisation d'une fenêtre
dans la suivante. Ils ne deviennent pas un portefeuille négociable si leurs
périodes se chevauchent.

### B. Portefeuille à capital commun

Fixer pour toute la matrice : **capital initial 1, deux compartiments,
long-only, aucun levier**, répartition équipondérée du top 3 %, même calendrier
de NAV et liquidation suivie jusqu'au 31 juillet 2026.

À chaque entrée, le budget est au plus `NAV du close précédent / 2`, borné par
le cash disponible. Un retard de sortie peut immobiliser du capital ; publier
les entrées réduites ou bloquées, sans augmenter les compartiments après lecture
des performances. Les horizons H1/H2/H3 gardent plus de cash entre décisions.

Les deux compartiments déterminent un plafond de budget par nouvelle décision,
et non deux comptes dont les gains seraient isolés. Le cash est commun ; une
position retardée peut réduire un prochain budget. Les positions d'une décision
reçoivent toutes la même allocation, open absent compris (cette part reste en cash).
Actions fractionnaires, aucun arrondi de lots, cash à taux zéro. Le nombre de
positions est ceil(top × N), soit cinq à top 3 %, seize ou dix-sept à top 10 %.

Les frais sont répartis moitié à l'entrée, moitié à la sortie et appliqués aux
nominaux effectivement échangés. Les 45 bp restent un scénario global,
sans calcul fiscal réel par action. Courtage minimum, spreads, TTF par instrument
et impact de marché demandent une expérience distincte.

Publier cumul NAV, drawdown, frais, turnover, cash et exposition quotidienne.
**Inclure le capital mobilisé pendant la séance** : une position H1 ouverte puis
fermée le même jour peut avoir une exposition nulle au close tout en mobilisant
du capital intraday. Ne pas annualiser un rendement en divisant simplement par
l'exposition moyenne ou la durée de détention.

## 5. Inférence et limites

L'unité temporelle est le cutoff. Comparer les écarts de paniers de façon appariée
sur les 22 dates. Une incertitude descriptive par blocs de 2/4/6 cutoffs, avec
10 000 réplications et seed fixée, doit conserver les mêmes tirages entre variantes.
Les horizons H10 et événements partagés peuvent rester dépendants : afficher
cette sensibilité et ne pas traiter 22 observations comme indépendantes.

Les intervalles individuels et critères de conservation du signe ne contrôlent pas
à eux seuls la sélection multiple des modèles et horizons. La comparaison reste
exploratoire et conditionnelle à un univers reconstruit. Le nouvel écart de définition
des volumes n'est pas réparé par un bootstrap.

## 6. Livrables exigés avant lecture des résultats

1. Config de matrice et liste des 22 cutoffs scellées, SHA des modèles/scores/sources.
2. Audit calendrier/horloge/cohorte, avec toutes les indisponibilités conservées.
3. Scores et paniers appariés, couverture et IC après open/gap.
4. Ledgers, NAV et attribution des gains/pertes pour chaque durée et coût.
5. Incertitude descriptive, concentration, retards, défauts de volume et limites.

**Replay livré :** [rapport](SRD_HORIZON_COMMON_REPLAY_RESULTS.md),
[matrices](SRD_HORIZON_COMMON_REPLAY_MATRICES.md), onglet **Horizon Comparison**
du [Model Lab](https://sandbox.hocus.works/quant-model-lab/).
Artefacts dans `data/analysis/srd-horizon-common-replay-v1/`, tests techniques et
comptabilité quotidienne conservés dans `tests.xml` et `test_receipt.json`.
Une ablation de contexte pourra suivre avec ses propres paramètres fixés avant calcul.
Une confirmation prospective ML demandera son propre gel préalable ; le
[protocole SPEC-007](SPEC_007_INDEPENDENT_CONFIRMATION.md) concerne un autre lock.
