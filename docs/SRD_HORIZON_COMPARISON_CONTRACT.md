# SRD — contrat de comparaison des horizons et de l'exécution

**6 octobre 2026 · version 1.**

**Statut :** contrat écrit pour le prochain replay de développement. Inventaire
des dates exécuté ; matrice commune de performances **non encore calculée**.
Ce contrat ne modifie pas les simulations H1/H2/H3, H5/H10 ou VAD publiées.

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

## 2. Matrice fixée pour la prochaine comparaison

| Horizon du score appris | Durées de détention à relire |
| ---: | --- |
| H1 | 1, 5 séances communes |
| H2 | 2, 5 séances communes |
| H3 | 3, 5 séances communes |
| H5 | 5, 10 séances communes |
| H10 | 10, 20 séances communes |

Chaque target conserve sa définition et son modèle choisi sur validation. Ne pas
choisir un autre modèle selon la meilleure détention en 2026. Présenter séparément
rang, rendement, directions et excursions. Tendance/erreur-type est indéfinie à
H1/H2 ; à H3 son faible nombre de degrés de liberté demande une lecture séparée.
Les scores constants restent identifiés comme références et leurs sélections
départagées par ISIN ne constituent pas un signal appris.

Les scénarios sont **brut, 25 et 45 bp aller-retour**. La VAD n'entre pas dans cette
première comparaison commune long-only. Elle pourra être relue séparément avec
son allocation 50/50 et ses contraintes de prêt.

## 3. Horloge, calendrier et cohorte

| Objet | Règle |
| --- | --- |
| Décision | Après disponibilité de toutes les entrées ; borne commune 00:00 UTC le lendemain du cutoff |
| Features | Informations connues au cutoff ; disponibilité vérifiée, aucune donnée future |
| Admission des titres | Cohorte issue des features et de l'éligibilité connue à T ; ne pas la restreindre selon les rendements futurs |
| Calendrier d'exécution | Grille Euronext Paris versionnée et rapprochée des séances observées ; archive de la grille et des exceptions |
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

Avant replay, vérifier les bornes de disponibilité du benchmark des anciennes
targets relatives H5/H10. La correction UTC des horizons courts ne leur donne
pas automatiquement la même convention. Toute différence de contrat doit être
signalée ou faire l'objet d'un nouveau run distinct.

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

Fixer pour toute la matrice : **capital initial 1, quatre compartiments,
long-only, aucun levier**, répartition équipondérée du top 3 %, même calendrier
de NAV et liquidation suivie jusqu'au 31 juillet 2026.

À chaque entrée, le budget est au plus `NAV du close précédent / 4`, borné par
le cash disponible. Un retard de sortie peut immobiliser du capital ; publier
les entrées réduites ou bloquées, sans augmenter les compartiments après lecture
des performances. Les horizons H1/H2/H3 gardent plus de cash entre décisions.

Ces quatre compartiments sont une **nouvelle convention** pour la matrice jusqu'à
H20. Les tableaux précédents utilisent deux compartiments pour les horizons courts ;
leurs NAV ne peuvent pas être comparées directement à ce nouveau run.

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
Les horizons H20 peuvent rester dépendants au-delà des blocs courts : afficher
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

**Prochaine action : exécuter cette matrice commune après le rapprochement de
cohorte/horloge.** Une ablation de contexte viendra ensuite avec les mêmes règles.
Une confirmation prospective ML demandera son propre gel préalable ; le
[protocole SPEC-007](SPEC_007_INDEPENDENT_CONFIRMATION.md) concerne un autre lock.
