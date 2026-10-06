# Hocus Quant Lab — synthèse des expérimentations

**6 octobre 2026 · version 1 · base de lecture `9a292e2`.**

**Objet :** retrouver toutes les étapes de recherche, leur statut, les résultats
utiles, la documentation et les prochaines expériences proposées.

**Référence :** branche `spec/008-multivariate-model-backtest`. Les données et
modèles sont locaux, non versionnés ; les contrats, configs, rapports et empreintes
sont dans Git. Le [journal chronologique](RESEARCH_PROGRESS_2026_10_06.md) et la
[synthèse des corrélations](EXPLORATION_CORRELATIONS_SYNTHESE.md) détaillent les phases.
Le fichier compagnon [sources et empreintes](EXPERIMENTATIONS_SYNTHESE.sources.json)
identifie les documents et artefacts utilisés. Cette synthèse ne lance aucun nouveau calcul.

## 1. Synthèse en cinq points

1. **La chaîne de recherche fonctionne :** ingestion, provenance, features, targets,
   modèles, simulations après l'open, audits et consultation Marimo.
2. **Le rang du rendement SRD est une piste à approfondir.** Les RF H5/H10,
   la concentration top 3 % et certains contextes donnent des simulations positives.
3. **Le contexte et la durée de détention ont des effets contrastés.** Le contexte
   améliore cinq tâches sur douze ; prolonger une détention peut améliorer ou réduire le gain.
4. **La prévision de volatilité des indices est plus convaincante que leur prévision
   de rendement.** La VAD et les directions absolues courtes ont des résultats moins favorables.
5. **Aucun alpha indépendant n'est confirmé.** Les prix, opérations sur titres,
   coûts et périodes déjà explorées limitent l'interprétation. La confirmation
   prospective SPEC-007 attend de nouvelles observations.

Les priorités ci-dessous sont **des propositions**, sans nouvelle expérience exécutée.

## 2. Comment lire les statuts et les chiffres

| Statut | Sens |
| --- | --- |
| **Livré** | Calcul et documentation présents ; niveau de preuve précisé dans la ligne |
| **Archivé pour diagnostic** | Résultat historique utile pour comprendre une erreur ou un biais |
| **En attente de données** | Protocole disponible ; observations requises absentes de l'état documenté |
| **Non commencé** | Aucune expérience dédiée comparable n'est documentée |

**Livré ne signifie pas confirmé scientifiquement.** Un audit arithmétique ou le
rejeu d'un modèle certifie les contrôles examinés ; il ne prouve pas l'alpha.
Les simulations et sélections examinées en 2024–2026 restent du développement.

| Objet mesuré | Interprétation |
| --- | --- |
| IC cross-sectionnel | Corrélation de rang entre actions ou indices à la même date, puis moyenne des dates |
| AUC | Discrimination des catégories de direction ; 0,50 est l'AUC de la référence constante |
| Erreur/MSE des indices | Qualité d'une prévision sur les dates d'un indice ; différente du classement des actions |
| Rendement de panier | Moyenne d'une fenêtre future ou PnL rapporté au budget d'un panier, selon le contrat |
| Rendement de portefeuille | Variation cumulée de NAV, avec compartiments, cash et exécution simulée |
| Contribution d'une jambe/action | Points du capital initial ; à distinguer du rendement du titre |

Les rendements de portefeuille ci-dessous sont **cumulés, non annualisés**.
Les tableaux précisent brut/net, horizon appris et durée de détention.
Les diagnostics de paniers d'indices ne simulent pas un portefeuille négociable.

### Périodes

| Étape | Période et grille |
| --- | --- |
| Prix ABC livrés | 29/09/2022 → 28/09/2026 |
| Corrélations exploratoires | Environ avril → octobre 2024/2025 ; avril → septembre 2026 partiel, grille hebdomadaire |
| Modèles SRD | Train 2024, sélection S1 2025, retrain 2024+S1 2025, lecture S1 2026 ; cutoffs hebdomadaires et purges |
| Grands marchés séparés | Grille quotidienne ; train 2024, sélection S1 2025, retrain 2024+S1 2025, lecture S1 2026 |
| K-means descriptif E15 | Centres et tables ajustés sur 2024 puis gelés pour S1 2025 et S1 2026 ; budget d'information différent des modèles supervisés |
| Contextes historiques SRD | Amorçage 2023, producteurs ajustés avant chaque trimestre ; contexte test borné avant juillet 2025 |
| Replays de détention | Décisions S1 2026 ; liquidations suivies jusqu'au 31/07/2026 |
| Confirmation SPEC-007 | Début autorisé 06/10/2026 ; premier vendredi admissible 09/10/2026, sous réserve de données reçues |

## 3. Fondations et couverture des données

| Périmètre | Disponible | Utilisation réalisée | Statut / documentation |
| --- | --- | --- | --- |
| Actions ABC SRD | 199 416 observations, 197 identifiants, quatre ans de prix | Corrélations, modèles H1/H2/H3/H5/H10 et simulations | **Livré, PIT reconstruit** · [Livraison ABC](ABC_BOURSE_DELIVERY.md) |
| Indices de marché | 90 268 lignes source | Comparaisons par groupes et modèles individuels de cinq grands marchés | **Livré, expérimental** · [Indices](SPEC_008_INDICES_CONTRACT.md) |
| Indices sectoriels | 29 998 lignes source ; 27 indices dans le contrat de contexte | Modèles par groupe et prévisions historiques utilisées comme contexte global SRD | **Livré, expérimental** · [Intégration](SRD_CONTEXT_INTEGRATION_CONTRACT.md) |
| Actions US / allemandes | 904 551 / 465 958 lignes source | Données ingérées et scan global exploratoire ; pas de benchmark prédictif comparable au SRD documenté | **Recherche dédiée non commencée** · [Sources](DATA_SOURCES.md) |
| FX/taux, crypto, matières premières, obligations | Livraisons normalisées | Scan exploratoire global ; pas de stratégie dédiée comparable au SRD documentée | **Recherche dédiée non commencée** · [Livraison](ABC_BOURSE_DELIVERY.md) |
| Positions courtes publiques AMF | 40 819 lignes du premier import ; positions depuis 17/10/2012 | Ingestion, normalisation et disponibilité par publication | **Données livrées ; expérience prédictive non commencée** · [AMF](AMF_SHORT_POSITIONS.md) |
| INSEE / Banque de France | Sources prévues dans le plan | Aucun benchmark macro documenté | **Non commencé** · [Sources](DATA_SOURCES.md) |
| Référentiel de libellés | 2 135 codes, 2 067 libellés, 68 non résolus | Lecture des instruments ; variantes conservées | **Livré, référentiel actuel** · [Livraison](ABC_BOURSE_DELIVERY.md) |

Le corpus SRD livré ne reconstitue pas les composants historiques du SBF 120.
Le **SBF 120 utilisé comme indice** est une série distincte de cet univers d'actions.
Les vintages historiques des prix et les opérations sur titres restent insuffisamment
certifiés. Les règles d'ingestion et les contrôles sont dans
[POINT_IN_TIME](POINT_IN_TIME.md), [qualité](SPEC_003Q_MARKET_DATA_QUALITY.md),
[features](FEATURES.md), [cube historique](SPEC_004_HISTORICAL_FEATURE_CUBE.md) et
[targets](SPEC_005_TARGET_FACTORY.md).

## 4. Catalogue — corrélations, audits et confirmation

| ID | Expérience / question | Statut et résultat | Documentation | Suite proposée |
| --- | --- | --- | --- | --- |
| E01 | Scan initial, toutes familles : quelles associations apparaissent ? | **Livré, descriptif** · 45 270 relations globales ; le top SRD est surtout lié à volatilité/drawdown | [Méthode](SPEC_006_SIGNAL_ANALYSIS.md), [résultats](SPEC_006_DATA_REPORT.md) | Séparer objectifs de risque et de rendement ; utiliser une inférence tenant compte des dépendances |
| E02 | Top 100 de 2024 relu en 2025/2026 | **Livré, exploratoire** · risque : signes conservés ; performance : sélection H120 très instable | [Comparaison](SPEC_006_PERIOD_STABILITY_2025_2026.md) | Réserver la persistance de volatilité à une expérience de risque dédiée |
| E03 | Top 500 rendement/direction, puis audit des inversions | **Archivé pour diagnostic** · 479/500 inversions en 2025 ; chevauchement, redondance et biais de sélection localisés | [Audit](SPEC_006R_REVERSAL_AUDIT.md), [bilan complet](EXPLORATION_CORRELATIONS_SYNTHESE.md) | Conserver l'archive ; fixer calendrier, admission à T et inférence avant un nouveau scan |
| E04 | Nouveau top 500 limité à H5 | **Livré, exploration historique** · 66 % d'inversions 2024→2025 ; 18,2 % entre 2025 et 2026 | [H5](SPEC_006R_H5_RESULTS.md) | Examiner amplitudes et incertitude, puis utiliser le contrat corrigé E07 |
| E05 | Top 100 par fenêtre historique | **Livré, exploration historique** · 153/800 inversions 2025→2026 ; fenêtre 504 non admissible | [2024→2025](SPEC_006R_H5_BY_WINDOW.md), [2025→2026](SPEC_006R_H5_BY_WINDOW_2025_2026.md) | Regrouper les variables redondantes et fixer les familles avant sélection |
| E06 | Incertitude bootstrap du signe des IC H5 | **Livré, individuel** · sur 800 variables : 133 soutiens conjoints >90 %, 78 doubles intervalles 90 % hors zéro | [Intervalles](SPEC_006R_H5_IC_CONFIDENCE.md) | Traiter multiplicité et faible nombre de dates ; ne pas convertir ces fréquences en probabilité d'alpha |
| E07 | SPEC-006T : réparer l'admission fondée sur le futur et geler les candidats | **Livré, lock exploratoire** · 504 broad / 138 strong / 85 strict, ensembles imbriqués | [Contrat](SPEC_006T_EX_ANTE_RESEARCH_CONTRACT.md), [audit](SPEC_006T_AUDIT.md) | Conserver le lock figé pour la confirmation prospective |
| E08 | SPEC-007 : confirmation indépendante du lock | **En attente de données** · aucun résultat indépendant documenté ; checkpoints 8/13/26 cutoffs | [Protocole](SPEC_007_INDEPENDENT_CONFIRMATION.md), [configuration](../configs/research/confirmation_protocol_v1.toml) | Recevoir les prix, enregistrer les scores avant les outcomes, attendre la maturité H5 |

Les résultats E04–E06 conservent les filtres de leurs expériences initiales.
Le signe du top risque en 2026 est particulièrement peu documenté pour H120 :
ses relations disposent d'une médiane de deux cutoffs mûrs dans la première comparaison.
**SPEC-006T ne réécrit pas rétrospectivement ces chiffres.** Il fixe un contrat
corrigé pour la direction absolue H5, avec éligibilité à T séparée de la qualité future.
Les erreurs sources fortes peuvent rendre un résultat ininterprétable ; elles ne
retirent pas le titre de la cohorte déjà figée.

Dans le top H5 historique, la meilleure q-value de découverte est **0,4549** :
aucune relation ne franchit q≤0,25 dans cette table. Le classement et la conservation
du signe décrivent donc des candidats exploratoires, souvent de faible amplitude.

Le soutien bootstrap de 90 % concerne le rééchantillonnage des IC, sous ses
hypothèses. Il ne représente pas une probabilité de hausse ou d'alpha.

## 5. Catalogue — modèles, contexte et portefeuilles

| ID | Expérience / question | Statut et résultat | Documentation | Suite proposée |
| --- | --- | --- | --- | --- |
| E09 | SRD Strict/Strong, six targets H5/H10 | **Livré, développement** · 112 modèles ; prétraitements appris sur train et sélection sur validation | [Contrat](SPEC_008_MULTIVARIATE_MODEL_BACKTEST.md), [résultats](SPEC_008_RESULTS.md) | Garder comme références ; les listes de variables avaient déjà utilisé 2025/2026 |
| E10 | SRD avec les 1 048 variables ensemble | **Livré, développement** · 56 modèles ; résultat contrasté face à Strict/Strong | [Extension](SPEC_008_ALL_FEATURES.md), [comparaison](SPEC_008_ALL_FEATURES_COMPARISON.md) | Comparer parcimonie, redondance et régularisation avec un choix fixé avant une nouvelle période |
| E11 | Concentrer le portefeuille du top 10 % au top 3 % | **Livré, replay** · mêmes scores ; rang RF H5/H10 à 25 bp : +10,81 % / +17,68 % | [Top 3 %](SPEC_008_TOP3_RESULTS.md) | Fixer la concentration ; mesurer contributions, liquidité et effet des frais |
| E12 | Détail des actions du rang et coûts 25/45 bp | **Livré, diagnostic de portefeuille** · ledgers réconciliés ; rang H5/H10 à 45 bp : +8,32 % / +15,95 % | [Actions et contributions](SPEC_008_RANK_PORTFOLIO_DETAIL.md), [frais](SPEC_008_COST_SCENARIOS_25_45.md) | Ajouter des coûts observables par instrument et montant |
| E13 | Modèles sur groupes d'indices de marché et sectoriels | **Livré, v2 corrigée** · 112 modèles ; rang sectoriel H10 IC 0,1583, intervalle individuel 90 % positif | [Contrat](SPEC_008_INDICES_CONTRACT.md), [résultats](SPEC_008_INDICES_RESULTS.md) | Vérifier stabilité et couverture des secteurs ; les paniers restent des diagnostics sans exécution |
| E14 | Modèles temporels séparés CAC40, SBF120, S&P500, DAX40, FTSE100 | **Livré, développement** · 30 tâches, 140 artefacts dont 90 ML ; volatilité plus intéressante que rendement | [Contrat](INDEX_SERIES_MODELS_CONTRACT.md), [résultats](INDEX_SERIES_MODELS_RESULTS.md) | Approfondir les prévisions de risque et leur valeur incrémentale dans le SRD |
| E15 | K-means SBF120 à sept clusters | **Livré, descriptif + prévisions** · centres 2024 figés ; volatilité H5 utile face à certaines références | [Contrat](SBF120_KMEANS7_CONTRACT.md), [résultats](SBF120_KMEANS7_RESULTS.md) | Mesurer dérive des états et valeur des régimes face à une simple moyenne passée |
| E16 | Ajouter K-means et prévisions d'indices aux actions SRD | **Livré, développement** · 356 contextes, 1 404 variables, 56 modèles ; rendement net amélioré dans 5/12 tâches | [Intégration historique](SRD_CONTEXT_INTEGRATION_CONTRACT.md), [résultats](SRD_CONTEXT_RESULTS.md) | Faire une ablation par bloc et conserver les baisses observées |
| E17 | VAD top/flop 3 % et détention H5→H10 / H10→H20 | **Livré, replay théorique** · 672 simulations ; VAD défavorable pour le rang H5 ; prolongation parfois favorable | [Contrat](SRD_VAD_HOLDING_CONTRACT.md), [résultats](SRD_VAD_HOLDING_RESULTS.md) | Séparer signal short, neutralisation du risque et coûts réels du prêt |
| E18 | Nouveaux modèles H1/H2/H3, détenus à H ou H5 | **Livré, développement** · 74 modèles, 16 tâches, 462 replays ; gains parfois concentrés | [Contrat](SRD_SHORT_HORIZONS_CONTRACT.md), [résultats](SRD_SHORT_HORIZONS_RESULTS.md) | Auditer les trades matériels puis comparer horizons, exposition et frais sur les mêmes dates |

Les nombres de modèles ne doivent pas être additionnés comme autant de preuves
indépendantes : plusieurs expériences réutilisent les mêmes modèles ou sources.
E11, E12 et E17 rejouent des décisions existantes. Les grands marchés distinguent
artefacts, références et fits ; 140 artefacts ne signifie pas 140 modèles ML.

### Les six targets des modèles SRD

Direction absolue, rendement absolu, direction relative au CAC AllShares,
rang du rendement, équilibre des excursions et tendance/erreur-type.
H est l'horizon futur du label ; W reste la fenêtre passée d'une feature.
Le portefeuille entre après l'information de la feature, au prochain open.
Le label close-à-close comprend donc un gap préalable à cette entrée.

À H1/H2, tendance/erreur-type est indéfinie. À H3, elle a un seul degré de liberté.
Excursions H1 = deux fois rendement H1 : ces deux tâches ne sont pas des idées indépendantes.

## 6. Résultats à retenir et portée pratique

### 6.1 SRD : variables et concentration

Le registre complet n'améliore pas systématiquement les ensembles réduits.
Avec le portefeuille **top 10 % à 25 bp**, le rang H5 passe de +4,16 %
(Strong, baseline choisie sur validation) à +6,39 % (All), tandis que le rang H10
passe de +8,35 % (Strict, baseline choisie sur validation) à +6,27 % (All).
[Source : comparaison des sets](SPEC_008_ALL_FEATURES_COMPARISON.md).

Le passage au **top 3 %** change ensuite les paniers, sans changer les scores :

| Rang du rendement, RF sans contexte | Top 10 %, net 25 bp | Top 3 %, net 25 bp | Top 3 %, net 45 bp |
| --- | ---: | ---: | ---: |
| Target H5, détenue H5 | +6,39 % | +10,81 % | +8,32 % |
| Target H10, détenue H10 | +6,27 % | +17,68 % | +15,95 % |

**Lecture :** la concentration est une piste de développement ; sa sélection a
été examinée sur 2026 et elle accroît la sensibilité à quelques titres.
[Top 3 %](SPEC_008_TOP3_RESULTS.md) et [scénarios de frais](SPEC_008_COST_SCENARIOS_25_45.md).

### 6.2 Contextes : gains sur le rang, absence de bénéfice global établi

| Rang RF, top 3 % | Sans contexte, net 25 bp | Avec contexte, net 25 bp | Avec contexte, net 45 bp |
| --- | ---: | ---: | ---: |
| H5, détention H5 | +10,81 % | +16,99 % | +14,35 % |
| H10, détention H10 | +17,68 % | +25,49 % | +23,64 % |

Sur les douze tâches, cinq améliorent le rendement net à 25 bp. **Aucune tâche
n'a un écart d'IC avec trois intervalles 90 % entièrement positifs** pour les
trois tailles de blocs étudiées. Des IC améliorés coexistent avec des portefeuilles
moins rentables ; les drawdowns du rang enrichi sont également plus élevés aux
scénarios documentés. [Résultats contextes](SRD_CONTEXT_RESULTS.md).

Les 356 contextes sont 20 variables de régimes SBF120, 324 prévisions sectorielles
et 12 prévisions CAC40/SBF120. La variante historique utilise des centres **2023**
et des producteurs antérieurs à chaque bloc. Les centres **2024** d'E15 constituent
une autre expérience ; leurs numéros C1…C7 ne désignent pas les mêmes états.
Les anciens exports test 2026 ne remplissent pas le train 2024. Les phrases des
anciens rapports annonçant une intégration « à construire » décrivent ces runs
initiaux ; E16 a livré une variante historique dédiée.

### 6.3 VAD et prolongation : résultats différents selon le score

| Rang RF sans contexte | Long-only, net 25 bp | Long/short 50/50, net 25 bp et prêt 3 % |
| --- | ---: | ---: |
| Score H5, détenu H5 | +10,81 % | +0,08 % |
| Score H5, détenu H10 | +21,98 % | +6,96 % |
| Score H10, détenu H10 | +17,68 % | +8,49 % |
| Score H10, détenu H20 | +11,32 % | +4,78 % |

Pour score H5/détention H5, la contribution short vaut **−4,88 points** du capital
initial : la jambe short perd de l'argent dans cette simulation. Le portefeuille
long/short répartit le budget 50/50 ; sa composition, son exposition nette et son
risque diffèrent du long-only.

Prolonger le rang H5 jusqu'à H10 augmente le rendement long-only mais fait passer
l'exposition moyenne de **30,9 % à 46,4 %**, et le drawdown de **−5,17 % à −8,19 %**.
Prolonger le rang H10 jusqu'à H20 réduit au contraire le gain.
[Source : VAD et détention](SRD_VAD_HOLDING_RESULTS.md).

### 6.4 Horizons courts : performances brutes et sensibilité

Top 3 % acheté, sans contexte, deux compartiments :

| Target / modèle choisi en 2025 | Horizon appris | Brut, sortie native | Brut, sortie H5 | Net 45 bp, sortie native | Net 45 bp, sortie H5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rendement / XGB | H1 | +9,34 % | +15,33 % | +3,67 % | +9,33 % |
| Rendement / RF | H2 | +8,75 % | +12,55 % | +3,11 % | +6,71 % |
| Rendement / XGB | H3 | +23,48 % | +13,77 % | +17,31 % | +8,09 % |
| Rang / RF | H1 | +5,05 % | +8,31 % | −0,48 % | +2,61 % |
| Rang / RF | H2 | +7,07 % | +13,87 % | +1,53 % | +7,96 % |
| Rang / RF | H3 | +8,07 % | +9,94 % | +2,60 % | +4,39 % |

H1/H2 ont 24 décisions, H3 en a 23 ; le rapport présente aussi les paniers sur
les **23 dates communes**, leur excès face à l'univers et l'IC après l'open.
Les performances cumulées seules ne mesurent pas un effet pur de l'horizon.
À H1, la position est intraday : l'exposition en fin de séance est nulle, alors
que du capital est engagé pendant la séance.

**Le +23,48 % brut H3 est concentré.** Les cinq meilleurs trades apportent
15,83 points, dont 5,78 points pour `BE0974310428`, trade +50 % marqué en revue.
Sa cause n'est pas certifiée. Il reste inclus ; les deux entrées manquantes
restent en cash. Les directions absolues H1/H2/H3 retiennent la référence
constante sur validation : leurs paniers arbitraires ne sont pas un signal appris.
[Tous les modèles, diagnostics et contributions](SRD_SHORT_HORIZONS_RESULTS.md).

### 6.5 Indices : risque et rendement à distinguer

- **Groupes sectoriels :** rang H10, RF, IC test 0,1583 et intervalle individuel
  90 % [0,0836 ; 0,2259]. Le panier top 3 % retient un indice sectoriel et décrit
  un rendement futur moyen, sans exécution ni composition de portefeuille.
- **Grands marchés séparés :** aucun gagnant de rendement ne réduit la MSE de
  la référence zéro. DAX direction H5 : AUC 0,6557, mais log-loss légèrement
  moins bonne que le prior ; une bonne discrimination ne garantit pas une
  bonne probabilité calibrée.
- **Volatilité H5 :** MSE réduite de 37,9 % CAC40, 32,4 % SBF120 et 32,2 % FTSE100
  face à leur volatilité historique H5, avec soutien individuel des trois tailles de blocs.
- **K-means 2024 :** silhouette 0,2158 ; volatilité H5 MSE réduite de 28,4 % face
  à la volatilité historique, mais de 4,3 % face à la moyenne 2024 constante.
  58,4 % des dates 2025 et 27,2 % des dates 2026 sont hors du support train défini.
  La direction et le rendement ne battent pas leurs références.

Sources : [groupes d'indices](SPEC_008_INDICES_RESULTS.md),
[modèles individuels](INDEX_SERIES_MODELS_RESULTS.md),
[K-means](SBF120_KMEANS7_RESULTS.md). Ces indices ont pour usage prévu le contexte
des modèles SRD ; leurs résultats ne constituent pas une stratégie de trading d'indice.

## 7. Défauts localisés, corrections et limites restantes

| Sujet | État au 6 octobre | Conséquence |
| --- | --- | --- |
| Admission selon qualité future dans les corrélations initiales | Défaut confirmé ; séparation à T livrée par SPEC-006T pour son contrat H5 | Conserver les scans initiaux comme archives ; ne pas leur attribuer les garanties du contrat corrigé |
| Inférence H120 initiale | Dépendance et chevauchement confirmés ; tests temporels naïfs inadéquats | Aucun niveau confirmatoire attribuable au top H120 |
| Redondance des variables/targets | Documentée ; déduplication de rang dans le lock | Plusieurs lignes ou modèles ne représentent pas plusieurs informations indépendantes |
| Heure et calendrier des groupes d'indices | v1 invalide archivée ; v2 recalculée après audit | Lire les rapports v2 et distinguer leur convention des expériences précédentes |
| Direction relative des nouveaux horizons courts | Borne UTC corrigée avant les 74 entraînements publiés ; 7 571 labels relatifs changés dans le dataset initial | La version partielle avant correction reste invalide ; les features et autres targets sont inchangées |
| Prix et opérations sur titres | Événements matériels et ajustements non entièrement certifiés | Priorité à l'audit des profits concentrés ; aucun retrait opportuniste selon le résultat |
| Univers et libellés | Corpus livré et référentiel actuel, historique des appartenances incomplet | Risque de survivance ; absence de preuve d'un SBF120 historique investissable |
| Frais et VAD | Forfaits 25/45 bp, prêt 0/3 % de sensibilité | Pas de minimum de courtage, fiscalité par titre, carnet d'ordres ou prêt effectif certifié |
| Validation indépendante | 2024–2026 déjà consultés ; SPEC-007 attend des données | Nouveau protocole séparé requis pour confirmer les modèles ML et les choix de portefeuille |

SPEC-007 concerne le **lock univarié direction H5**. Il ne confirme pas automatiquement
les RF/XGB, les contextes, le top 3 %, la VAD ni les nouveaux horizons courts.

## 8. Prochaines étapes proposées — ordre de travail

| Priorité | Travail proposé | Livrable concret | Critère de décision |
| --- | --- | --- | --- |
| **P0** | Auditer les prix et événements qui portent les gains | Registre des plus fortes contributions, barres sources, événements documentés, règles de traitement versionnées | Chaque événement matériel est expliqué ou reste explicitement non certifié ; aucune exclusion choisie pour améliorer la performance |
| **P0** | Établir une comparaison commune des horizons et de l'exécution | Contrat calendrier/disponibilité/entrée/sortie, mêmes dates comparables, budget et règles de qualité ; tableaux IC après open, paniers, NAV, risque et couverture | Les différences d'horizon, de cash et de composition sont séparées des variations de qualité du score |
| **P1** | Décomposer la valeur du contexte sur le rang SRD | Baseline, +CAC/SBF, +secteurs, +régimes, +volatilité de contexte ciblée, +ensemble complet ; mêmes cohortes et règles de sélection | Gain incrémental mesuré face à la référence, avec pertes et incertitude conservées ; aucun bloc choisi sur sa meilleure performance 2026 |
| **P1** | Comparer explicitement score et durée de détention | Matrice fixée d'avance, comprenant H1/H2/H3 natifs et H5, rang H5→H10 et H10→H20 ; coûts et exposition communs documentés | La meilleure durée n'est pas déduite du seul PnL cumulé ; effets sur paniers, risque et frais lisibles |
| **P1** | Préparer une confirmation propre aux modèles ML | Gel de quelques hypothèses, variables, modèles, paramètres, coûts et règles de portefeuille ; enregistrement prospectif séparé de SPEC-007 | Période réellement non consultée, décisions enregistrées avant les outcomes, règle d'arrêt et de lecture fixée |
| **P1, en parallèle** | Faire vivre SPEC-007 sans changer son contrat | Nouvelles captures, registrations scellées, outcomes H5, monitor et checkpoints 8/13/26 | Lecture des 85 strict selon leurs signes gelés ; disponibilité et qualité documentées |
| **P2** | Rendre l'exécution et les coûts plus réalistes | Fiscalité datée par instrument, courtage par montant, minimums, liquidité et écarts d'exécution ; scénarios auditables | Résultats lisibles après hypothèses réalisables, sans assimiler les 45 bp à une fiscalité calculée |
| **P2** | Reprendre la VAD comme question distincte | Mesures de classement du bas de distribution, contribution short, couverture de prêt, coût/dividendes/rappels et risque de marge | Montrer son utilité propre — prévision ou réduction de risque — face au long-only comparable |
| **P2** | Tester l'information AMF additionnelle | Features de positions publiques/deltas/événements construites selon publication, jointure ISIN datée, comparaison prix seuls → prix+AMF | Couverture et absences explicites ; information disponible à T ; absence de déclaration non assimilée silencieusement à zéro |
| **P3** | Étendre aux actions US/allemandes et autres univers | Contrat de données propre au marché, corporate actions, heures/devises/calendriers, puis benchmark comparable | Transportabilité examinée ; absence de revendication de confirmation à partir de données déjà explorées |
| **P3** | Consolider la référence Git et le catalogue | Référence commune de code/rapports, procédure de reconstruction des données locales et index de navigation | Un lecteur externe retrouve le bon état de recherche et ses limites depuis le README |

**Prochaine séquence recommandée : P0 prix → P0 comparaison commune → P1 ablation
du contexte et horizons → confirmation ML dédiée.** SPEC-007 peut avancer en
parallèle dès réception des nouvelles observations. Les expériences AMF et
d'autres marchés viennent ensuite, avec leur contrat propre.

Les configurations actuelles sont des références de reproduction ; elles ne sont
pas des protocoles à réoptimiser silencieusement à la lecture de 2026.
Au point de départ `9a292e2`, la branche de travail contient 31 commits absents
du `main` local ; la référence de cette synthèse est donc explicitement cette branche.

## 9. Documentation, consultation et reproduction

### Accès

- [Model Lab](https://sandbox.hocus.works/quant-model-lab/), sous authentification :
  modèles SRD, indices, grands marchés, régimes, **Contextes SRD**, **VAD et détention**
  et **Horizons courts** ; les treize onglets sont documentés dans le journal.
- [Laboratoire SRD](https://sandbox.hocus.works/quant-lab-srd/?v=h5) : prix,
  corrélations et diagnostics historiques ; [guide](SRD_MARIMO_LAB.md).
- [Déploiement et isolation des services](SANDBOX_DEPLOYMENT.md).
- [Bilan détaillé de la phase initiale](EXPLORATION_CORRELATIONS_SYNTHESE.md) et
  [journal de la suite](RESEARCH_PROGRESS_2026_10_06.md).

### Artefacts principaux locaux

| Dossier sous `data/analysis/` | Usage |
| --- | --- |
| `spec008-model-lab` | Strict/Strong H5/H10 et simulations top 10 % |
| `spec008-model-lab-all-features` | 1 048 variables, scores ; sous-dossiers top 3 %, détails du rang et frais |
| `spec008-index-model-lab` | Groupes d'indices, publication v2 |
| `index-series-models-v1` | Cinq séries temporelles indépendantes, 22 features |
| `sbf120-kmeans7-v1` | Centres 2024, affectations, distances et tables de prévision |
| `srd-context-v1` | Producteurs historiques, centres 2023, jointure as-of et modèles enrichis |
| `srd-portfolio-extensions-v1` | Ledgers achat/VAD et durées prolongées |
| `srd-short-horizons-v1` | Targets H1/H2/H3, 74 modèles, 462 replays, diagnostics et contributions |

Les artefacts des corrélations, du lock et de confirmation sont référencés par
leurs rapports dédiés. Les variantes initiales invalides ne sont pas des résultats
de remplacement. Les commandes de reconstruction sont dans chaque contrat et rapport ;
la présence du code seul ne donne pas accès aux données non versionnées.

**Décision de recherche proposée :** poursuivre les pistes rang, horizons courts
et risque de marché après audit des données et avec une confirmation réservée.
Les résultats actuels servent à formuler ces hypothèses ; ils n'établissent pas
encore leur rendement futur net de coûts.
