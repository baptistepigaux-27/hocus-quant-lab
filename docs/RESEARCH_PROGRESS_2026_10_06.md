# Journal de recherche — étapes après l'exploration des corrélations

**Mise à jour : 6 octobre 2026.** Branche `spec/008-multivariate-model-backtest`,
checkout `/home/ubuntu/worktrees/hocus-quant-spec008`.

## État actuel

La [synthèse des corrélations](EXPLORATION_CORRELATIONS_SYNTHESE.md) décrit la phase
initiale. Depuis, le laboratoire possède des modèles prédictifs et des simulations
de portefeuille **de développement**, ainsi que des modèles d'indices, un
K-means SBF 120 et leur intégration historique aux modèles actions. Les phrases
de la synthèse indiquant l'absence de modèles et de
backtest s'appliquent à la phase qu'elle clôture. Son PDF reste cette archive du
5 octobre ; le présent journal décrit la suite.

Les données réelles s'arrêtent toujours au 28 septembre 2026. L'ensemble des
résultats ci-dessous utilise des périodes déjà explorées : aucun alpha confirmé
sur une période indépendante n'est revendiqué.

## 1. Chronologie et liens de reproduction

| Étape | Travail livré | Documentation / commit |
| --- | --- | --- |
| SPEC-006T | Éligibilité à T séparée de la qualité future ; candidate lock | [Contrat ex ante](SPEC_006T_EX_ANTE_RESEARCH_CONTRACT.md), [audit](SPEC_006T_AUDIT.md) |
| SPEC-007 | Protocole prospectif et suivi de confirmation ; nouvelles observations requises | [Protocole indépendant](SPEC_007_INDEPENDENT_CONFIRMATION.md) |
| SPEC-008 SRD | Modèles naïfs, linéaires, RF/XGB ; six targets H5/H10 ; ensembles strict/strong ; simulations d'exécution | [Contrat](SPEC_008_MULTIVARIATE_MODEL_BACKTEST.md), [résultats](SPEC_008_RESULTS.md), `c61fd52` |
| Registre complet | Même méthodologie avec les 1 048 variables ; comparaison aux ensembles précédents | [Extension](SPEC_008_ALL_FEATURES.md), [comparaison](SPEC_008_ALL_FEATURES_COMPARISON.md), `7311033` |
| Top 3 % | Rejeu des mêmes scores en portefeuille plus concentré ; aucune réoptimisation de modèle | [Résultats](SPEC_008_TOP3_RESULTS.md), `390aa78` |
| Détail du rang | Actions, paniers, mois, contributions et réconciliation des performances H5/H10 | [Détail](SPEC_008_RANK_PORTFOLIO_DETAIL.md), `cb1c78d` |
| Frais 25/45 bp | Deux replays complets sur les mêmes décisions ; cash et allocations recalculés | [Scénarios](SPEC_008_COST_SCENARIOS_25_45.md), `b7fb77f` |
| Indices par groupes | Modèles sur groupes d'indices de marché/sectoriels, métriques et diagnostics de paniers | [Contrat](SPEC_008_INDICES_CONTRACT.md), [résultats](SPEC_008_INDICES_RESULTS.md), `0ab07ba` |
| Grands marchés | Estimateurs distincts sur les dates de CAC40/SBF120/S&P500/DAX40/FTSE100 | [Contrat](INDEX_SERIES_MODELS_CONTRACT.md), [résultats](INDEX_SERIES_MODELS_RESULTS.md), `9e15c6a` |
| SBF 120, sept régimes | K-means des dates de l'indice, centres et tables de prévision 2024 figés | [Contrat](SBF120_KMEANS7_CONTRACT.md), [résultats](SBF120_KMEANS7_RESULTS.md) |
| Contextes SRD | Producteurs historiques hors apprentissage, centres 2023 et jointure as-of ; 356 features ajoutées ; comparaison aux modèles actions seuls | [Contrat](SRD_CONTEXT_INTEGRATION_CONTRACT.md), [résultats](SRD_CONTEXT_RESULTS.md) |
| VAD et détention | Modèles actions seuls, 50/50 top/flop 3 %, coûts 25/45 bp, prêt 0/3 %, détentions H5→H10 et H10→H20 | [Contrat](SRD_VAD_HOLDING_CONTRACT.md), [résultats](SRD_VAD_HOLDING_RESULTS.md) |

Les données locales, modèles sérialisés et grands ledgers sont ignorés par Git.
Les contrats, configs, scripts, rapports et empreintes des sources sont versionnés.

## 2. Ce qu'apportent les simulations SRD et les scénarios de coûts

Les simulations utilisent les actions du corpus ABC SRD livré ; elles ne reconstruisent
pas les composants historiques du SBF 120. Le top 3 % retient cinq titres par nouveau
compartiment, aux décisions publiées. Il utilise les scores et gagnants de validation
existants. Le détail des paniers et l'ensemble des variantes sont dans les rapports liés.

Pour le **Random Forest, target rang du rendement**, test S1 2026 :

| Horizon | Rendement cumulé à 25 bp | Rendement cumulé à 45 bp |
| --- | ---: | ---: |
| H5 | +10,806 % | +8,320 % |
| H10 | +17,679 % | +15,954 % |

25 bp = 0,25 % aller-retour, partagé à parts égales entre achat et vente.
45 bp = 0,45 % aller-retour, avec la même convention. Ce sont des **forfaits de
simulation**. Aucun barème de broker, minimum par ordre ou application titre par
titre de la TTF n'est implémenté. Les 45 bp ne représentent pas une taxe de 0,4 %
ajoutée aux 25 bp ; ils constituent une seconde hypothèse globale.

Ces chiffres portent sur un portefeuille simulé avec ses décisions et compartiments.
Les rendements moyens futurs des indices, plus bas, sont un autre objet statistique.

## 3. Indices : correction de l'heure et du calendrier avant publication

La première expérience d'indices a mis en évidence deux incohérences :

- La source indices déclare les closes disponibles à **minuit UTC D+1**. Une coupe
  à minuit Paris les rendait indisponibles trop tôt.
- Un horizon comptant les prochaines lignes propres à un indice pouvait traverser
  un trou de série de plusieurs mois.

La v2 utilise l'heure UTC de la source et le calendrier CAC40 commun, avec tolérance
de trois jours calendaires pour le dernier close connu. Au-delà, les quotes restent
absentes. Source, features, targets et modèles ont été reconstruits. La v1 avec
heure incorrecte reste archivée localement dans
`data/analysis/spec008-index-model-lab-v1-invalid-cutoff/` et ne sert pas au rapport.

L'expérience publiée comprend **112 modèles finaux**, 160 fits de validation et
deux groupes. L'audit indépendant est requis avant le marqueur de publication.
Les métriques d'IC portent sur les indices comparés **à une même date**.
Les paniers top3 sont des diagnostics de rendements futurs moyens ; aucune
exécution ou commission d'indice n'est simulée.

Les 22 284 scores exportés sur 996 flux concernent seulement le test 2026.
Ils restent les résultats de cette première phase. La section 6 décrit la variante
historique reconstruite pour l'intégration SRD, sans réutiliser ces exports pour
remplir le train 2024.

## 4. Dernière étape supervisée : modèles temporels indépendants

Chaque estimateur des grands marchés apprend seulement sur les dates de son
indice. Aucun coefficient ni prétraitement n'est partagé entre indices. Le
SBF 120 demandé est `FR0003999481`, distinct du CAC AllShares.

Les 22 variables de close sont figées : rendements retardés, momentum, volatilité,
écarts aux moyennes, drawdown, position dans le range et RSI simple. Les cinq indices
partagent la grille quotidienne CAC40 pour préparer un contexte de recherche SRD.

| Phase | Période | Utilisation |
| --- | --- | --- |
| Train | 2024 | Ajustement et prétraitement initiaux |
| Validation | S1 2025 | Choix des hyperparamètres et du modèle |
| Retrain | 2024 + S1 2025 | Ajustement final des paramètres choisis |
| Test de développement | S1 2026 | Lecture des performances, sans sélection supplémentaire |

Trois targets × deux horizons × cinq indices = **30 tâches**.
Le registre compte **90 modèles ML** (linéaires, RF, XGB) et **50 références**,
soit 140 artefacts. Le compteur de 120 fits finaux inclut les références ajustées ;
il ne désigne pas 120 modèles ML distincts. 210 fits et 230 évaluations de validation
sont enregistrés. Les fonctions des autres expériences restent conservées.

Les résultats 2026 sont faibles pour le rendement. Aucun gagnant de validation
n'améliore l'erreur quadratique de la référence rendement zéro. Le DAX direction
H5 atteint une AUC de **0,6557**, mais sa log-loss reste légèrement moins bonne
que celle du prior historique : discrimination et qualité des probabilités diffèrent.

La volatilité H5 est le résultat le plus utile à approfondir : MSE réduite de
**37,9 % CAC40**, **32,4 % SBF120** et **32,2 % FTSE100** face à la volatilité
historique H5. Ces trois avantages ont des intervalles individuels 90 % positifs
pour les trois tailles de blocs. Ils ne sont pas corrigés pour les comparaisons
multiples, ni une preuve de performance économique.

### Vérifications et provenance auparavant dispersées

Le fichier local `index-series-models-v1/prediction_replay_audit.json` documente
**140 replays des artefacts sauvegardés**, différence maximale
`2,220446049250313e-16`. L'audit dataset documente **4 835 rendements et volatilités**
recalculés depuis les quotes natives, erreurs nulles, et **50 préfixes historiques**
de features vérifiés. Les métadonnées attestent un seul indice par fit.

L'export compte **3 525 scores sur 30 flux**, uniquement test 2026, sans résultats
futurs. L'heure de disponibilité des features suit minuit UTC D+1 ; la borne
d'information du fit final est le 01/07/2025 à minuit UTC. Le grade reste reconstruit.

## 5. Ajout du K-means SBF 120

Le nouveau modèle classe **les dates de l'indice**, à partir des mêmes 22 variables.
Les sept centres et le prétraitement utilisent uniquement les **256 dates de 2024**.
Les centres restent identiques pour les **125 dates de S1 2025** et **125 dates de
S1 2026**. La silhouette train vaut **0,2158**, avec une séparation modérée des états.

Une table de moyennes futures apprise sur les seuls labels purgés de 2024 fournit
six prévisions : direction, rendement et volatilité, H5/H10. Shrinkage fixé à
20 labels et fallback global si moins de 10 labels par cluster. Aucune table
n'est ajustée sur les résultats 2025/2026.

| Mesure test 2026 | H5 | H10 |
| --- | ---: | ---: |
| AUC direction | 0,4527 | 0,4819 |
| Skill log-loss direction vs prior 2024 | −2,38 % | −4,50 % |
| Skill MSE rendement vs zéro | −4,76 % | −4,93 % |
| Skill MSE volatilité vs volatilité historique H | +28,42 % | +12,72 % |
| Skill MSE volatilité vs moyenne 2024 constante | +4,31 % | −5,98 % |

La prévision de volatilité H5 dépasse la référence historique avec un intervalle
individuel 90 % positif sur les trois tailles de blocs. L'amélioration de **4,31 %
face à une moyenne constante** est un diagnostic ponctuel distinct, sans intervalle
d'avantage publié pour ce comparateur. Le H10 ne bat pas cette moyenne constante.
Les régimes ne produisent donc pas de preuve de prévision de direction/rendement.

**Décalage des états :** 58,4 % des jours de 2025 et 27,2 % de ceux de 2026 ont une
distance à leur centre supérieure au quantile 95 % train (seuil 4,3138 dans l'espace
standardisé). Aucun de ces jours n'est exclu. Les épisodes ultérieurs sortent
souvent du voisinage des états 2024 ; cela limite l'interprétation d'un régime figé.

Le modèle sauvegardé reproduit **506 affectations et 3 036 prévisions**, erreur
de prévision nulle. L'export contient **250 dates et 20 flux** : sept indicatrices,
sept distances et six prévisions. Les indicatrices permettent de transmettre une
catégorie à un modèle SRD sans traiter C7 comme « plus de signal » que C1.

Les centres ont été demandés à K=7 ; aucune recherche du meilleur K n'est effectuée.
Les variables corrélées peuvent surpondérer certains types d'état. Les 2024 du
K-means correspondent au fit, pas à une validation. Les modèles supervisés utilisent
un retrain 2025, et ne disposent donc pas du même budget d'information.

## 6. Intégration des contextes aux modèles actions SRD

L'expérience `srd-context-v1` ajoute **356 variables** aux 1 048 variables d'action :
20 variables de régime SBF120, 324 prévisions des 27 secteurs et 12 prévisions
CAC40/SBF120. Les secteurs forment un contexte global ; aucune classification
sectorielle historique des actions n'est inventée.

Un score calculé par un modèle entraîné jusqu'en 2025 ne peut pas remplir le train
2024. Les producteurs sont donc reconstruits avec un amorçage 2023, des fits
expansifs avant chaque trimestre de 2024/S1 2025 et des labels déjà matures.
Le test 2026 utilise un fit borné avant juillet 2025. Les paramètres des RF de
contexte sont fixés avant les résultats SRD, sans reprendre les anciens gagnants.

Les sept centres K-means sont ancrés en **2023**, puis gelés. C'est une variante
historique distincte du fit 2024 publié précédemment : les noms C1…C7 ne désignent
pas les mêmes centres. Les tables de prévisions par régime suivent les mêmes
bornes d'apprentissage que les producteurs supervisés.

La décision commune est minuit UTC D+1, après disponibilité des closes d'indices
et avant le prochain open. La jointure as-of vérifie les horloges de disponibilité,
le fit et la maturité des labels. Aucun stock ni label n'est retiré ; les 1 048
valeurs d'action et les 17 494 lignes sur 100 dates sont identiques à la référence.
Environ 5 % des valeurs de contexte sont manquantes explicitement.

Les mêmes grilles SRD et seeds servent à ajuster **56 modèles**, sur les six targets
H5/H10, sélectionnés sur S1 2025 puis rejoués sur S1 2026. Les simulations top 3 %
à 25/45 bp comparent les gagnants avec et sans contexte. Le rapport conserve aussi
les comparaisons par type de modèle et des intervalles individuels appariés d'IC.
L'amélioration de prédiction et celle du portefeuille sont évaluées séparément.

Les contextes historiques sont hors apprentissage de leurs producteurs ; les
modèles SRD utilisent toujours leur validation 2025 pour choisir leurs paramètres.
L'intégration ne crée pas une période de confirmation indépendante. Résultats et
diagnostics : [rapport complet](SRD_CONTEXT_RESULTS.md).

Sur les gagnants de validation, **5/12** améliorent le rendement net à 25 bp.
Le Random Forest sur le rang du rendement passe de **10,81 % à 16,99 % en H5**,
et de **17,68 % à 25,49 % en H10**. À 45 bp, les performances enrichies sont
**14,35 % et 23,64 %**. Le drawdown se dégrade toutefois sur ces deux modèles :
à 45 bp, **−5,41 % → −6,48 % en H5** et **−4,50 % → −6,76 % en H10**.

L'ajout n'améliore pas toutes les targets : rendement absolu H5 passe de **14,05 %
à 2,69 %** à 25 bp, malgré un IC ponctuel plus élevé. Aucun écart d'IC ne possède
trois intervalles individuels à 90 % entièrement positifs, pour blocs 2/4/6.
Ces chiffres ne justifient pas de remplacer systématiquement la référence.

Les **168 modèles RF producteurs**, **56 modèles SRD**, l'ancrage K-means et
**42 tables par régime** reproduisent les scores sauvegardés. L'écart maximal est
`2,220446049250313e-15` pour les producteurs et `1,971756091734278e-13` pour le SRD ;
les 2 000 valeurs de régime sont reproduites exactement. Les empreintes et
replays sont dans `srd-context-v1/comparison_replay_audit.json` et le
[manifeste de publication](SRD_CONTEXT_RESULTS.sources.json).

## 7. Modèles actions seuls : VAD et détention prolongée

Les **56 modèles sans contexte** sont rejoués sur leurs scores sauvegardés ; les
12 gagnants de validation restent identiques. Le choix utilisateur est **50 % achat
/ 50 % VAD**, sans levier. Top/flop 3 % = **cinq titres par jambe** dans les coupes
disponibles, sélections disjointes. Produits des shorts bloqués avec garantie ;
aucun réinvestissement de ces produits et aucun nouveau fit.

Les modèles H5 sont détenus 5 ou 10 séances, les H10 pendant 10 ou 20 séances.
Les compartiments suivent la détention (2/3/5). Frais 25/45 bp par aller-retour,
plus prêt des titres à 0 % ou 3 % annuel. Le taux 3 % est une hypothèse explicite,
pas un tarif observé. Les décisions S1 2026 sont conservées ; les liquidations
prolongées sont suivies jusqu'au 31 juillet, sans annualisation de la synthèse.

**Rang du rendement, RF, frais 25 bp, prêt short 3 % annuel :**

| Modèle | Détention | Achat seul | Achat/VAD 50/50 |
| --- | --- | ---: | ---: |
| H5 | H5 | +10,81 % | +0,08 % |
| H5 | H10 | +21,98 % | +6,96 % |
| H10 | H10 | +17,68 % | +8,49 % |
| H10 | H20 | +11,32 % | +4,78 % |

Pour le rang H5 détenu H5, les achats contribuent **+4,96 points** et les shorts
**−4,88 points** au capital initial. La VAD ne consiste pas à ajouter gratuitement
une seconde performance au portefeuille précédent : la moitié du budget va aux
shorts, dont la contribution peut être négative. Pour le H5 détenu H10, ces
contributions deviennent **+9,94 et −2,98 points**. Les variations d'exposition
dues aux détentions figurent dans le rapport.

Les **672 simulations** couvrent les deux détentions, les deux coûts et les
sensibilités de prêt pour tous les modèles. Les **112 contrôles long-only natifs**
reproduisent exactement **13 888 points de courbe** des résultats existants au
30 juin. PnL de 125 512 positions fermées et frais d'emprunt de 25 160 shorts sont
réconciliés indépendamment. Aucun résultat n'a de position non liquidée au 31 juillet.
Les prix ou sorties absents restent signalés, et les anomalies futures annotées.

Prêt historique, rappels, dividendes dus, fiscalité par titre et marge ne sont
pas connus : VAD théorique et prix raw, toujours en développement rétrospectif.
Tous les gagnants et toutes les simulations sont conservés, sans choix sur 2026.

## 8. Publication et accès

[Model Lab](https://sandbox.hocus.works/quant-model-lab/) :

- **Indices** : comparaisons par groupes, diagnostics de rang.
- **Grands marchés** : prévisions temporelles par indice, métriques et intervalles.
- **SBF 120 · régimes** : sept centres, chronologie des régimes, occupation,
  distances au support train, profils futurs, prévisions et ledger.
- **Contextes SRD** : modèles actions seuls/enrichis, coûts 25/45 bp, intervalles
  appariés et disponibilité historique ; jeu « Actions + contextes · 1 404 features »
  dans les contrôles de l'explorateur de modèles.
- **VAD et détention** : actions seules, comparaison achat/VAD et détentions
  prolongées, courbes, contributions par jambe/action et ledger.

Le service `hocus-quant-model-lab-sandbox` utilise le port loopback **8069** et le
checkout isolé. Chaque expérience a son bind en lecture seule. Les données et
modèles ne sont pas exposés en fichiers statiques. L'authentification existante
reste active. Le service SRD sur **8068** demeure distinct. Aucun fitting n'est
déclenché dans l'interface. [Guide d'installation](SANDBOX_DEPLOYMENT.md).

Publication des régimes observée le 6 octobre : service Model Lab actif, réponse
locale **200**, route publique sans credentials **401**, service SRD distinct actif.
Les dix onglets s'affichent et l'onglet SBF 120 montre les profils et graphiques
2026 H5. Aucune erreur JavaScript n'a été observée à l'ouverture. La capture locale
`/tmp/hocus-sbf120-regimes.png` conserve cette inspection visuelle.

Publication des contextes SRD observée le 6 octobre : **onze onglets**, comparaison
des douze gagnants et ledger visibles ; le jeu enrichi expose top 3 % et les seuls
scénarios calculés 25/45 bp. Le navigateur a affiché le RF rang H10 à 45 bp,
rendement cumulé **23,64 %**, avec sa courbe. Le sélecteur de modèle propose désormais
le gagnant de validation par défaut. Aucune erreur JavaScript ni alerte affichée.
Service Model Lab actif, loopback **200**, route publique sans credentials **401** ;
service SRD 8068 toujours actif. La publication et les empreintes des captures sont
dans `data/analysis/srd-context-v1/sandbox_publication.json`.

Publication VAD/détention observée le 6 octobre : **douze onglets**, contrôles
indépendants 25/45 bp et prêt 0/3 %, courbes des quatre portefeuilles et ledger
achat/VAD. Le navigateur a affiché le rang H5 puis H10/H20 à 45 bp, sans erreur
JavaScript ni alerte. Les contrôles généraux ouvrent désormais le jeu actions
seules de 1 048 variables par défaut. Le service et ses binds en lecture seule
incluent le dossier des replays. Trace :
`data/analysis/srd-portfolio-extensions-v1/sandbox_publication.json`.

Pour la publication initiale des grands marchés, les choix CAC40 direction H5 et
FTSE100 volatilité H10 avaient été inspectés au navigateur ; le log local
`/tmp/hocus-index-series-browser.log` et les captures correspondantes sont des
traces opérationnelles, pas des preuves statistiques. Les replays scientifiques
et empreintes sont persistés dans `data/analysis/`, et référencés dans le
[fichier de provenance du journal](RESEARCH_PROGRESS_2026_10_06.sources.json).

## 9. Prochaines étapes ouvertes

1. Décomposer l'ajout de contexte par blocs dans une nouvelle expérience fixée
   à l'avance ; le benchmark complet ne mesure pas une contribution causale par bloc.
2. Explorer les interactions action/contexte et la stabilité sur d'autres épisodes,
   en conservant les baisses de performance de cette première comparaison.
3. Traiter prix ajustés/corporate actions et composition historique de l'univers.
4. Préciser fiscalité par instrument, minimums de courtage, spread et exécution
   si l'objectif devient une simulation négociable.
5. Recueillir des observations de confirmation nouvelles selon le protocole
   SPEC-007. Aucun résultat rétrospectif supplémentaire ne remplit cette exigence.
