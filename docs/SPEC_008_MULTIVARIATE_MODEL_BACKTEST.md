# SPEC-008 — benchmark multivarié H5/H10 et backtest de développement

**5 octobre 2026 · V1 · equity ABC Bourse SRD**

**Development backtest — not independent confirmation.**

Base : SPEC-006T et SPEC-007, commit `429f12e984debdd8a1587771a3418bcb51ca43f3`.
La réalisation est isolée dans la branche `spec/008-multivariate-model-backtest` et le
worktree `/home/ubuntu/worktrees/hocus-quant-spec008`. Les entrées marché sont lues seulement ;
les nouveaux artefacts sont dans son propre `data/analysis/spec008-model-lab`.

[Résultats générés depuis les artefacts](SPEC_008_RESULTS.md) ·
[Model Lab](https://sandbox.hocus.works/quant-model-lab/)

## A. Question de recherche et portée du test

Les variables verrouillées fournissent-elles un ranking multivarié de la direction,
du rendement ou de la trajectoire future, en H5 et H10 ? RF et XGBoost ajoutent-ils une
information aux références constantes et linéaires ? Un ranking produit-il un résultat
long-only intéressant avec une exécution ultérieure et des frais explicités ?

Le benchmark est une expérience de **développement**, même si le tuning des modèles
n'utilise pas 2026. La membership strict/strong du lock résulte déjà de la lecture des
outcomes **2025 et 2026** dans SPEC-006T. Cette contamination de sélection est explicite :
S1 2026 ne constitue ni un holdout intact, ni une confirmation scientifique indépendante.
Les dépendances entre titres, features, cutoffs et essais restent présentes.

**SPEC-007 est conservé byte-identique** : lock, config, gel JSON, sources scientifiques
et `uv.lock`. Son stockage, son registre, ses views et son dashboard ne sont pas modifiés.
Aucune observation de confirmation n'est consommée. Le nouvel environnement utilise
les mêmes dépendances verrouillées, dans une `.venv` distincte.

## B. Découpage temporel et purge

| Usage | Période demandée | Cutoffs H5 effectifs | Cutoffs H10 effectifs |
|---|---|---|---|
| Train | année 2024 | 05/01 → 20/12/2024 | 05/01 → 13/12/2024 |
| Validation / tuning | S1 2025 | 03/01 → 20/06/2025 | 03/01 → 13/06/2025 |
| Retrain final | union des deux lignes précédentes | union H5 | union H10 |
| Test de développement | S1 2026 | 02/01 → 19/06/2026 | 02/01 → 12/06/2026 |

Les effectifs, dates de fins des labels et comptes de cutoffs sont générés dans le rapport.
Le calendrier est celui des séances equity réellement présentes dans la source ; la grille
utilise seulement les vendredis de séance, sans rollback implicite des jours fermés.
Les horizons comptent des séances/observations, jamais des jours calendaires.

Deux contrôles complémentaires :

1. **Embargo H séances minimum** avant la fin de chaque période : le cutoff doit disposer
   de H séances communes jusqu'à la borne déclarée. Le test S1 est également purgé en fin
   de juin. Aucune évaluation de période n'utilise une target au-delà de sa borne.
2. **Fin réelle du label** : une série ayant des trous peut atteindre son H-ième close
   plus tard que le calendrier commun. Si cette fin dépasse la frontière, la valeur de
   target est censurée, avec motif, et conservée dans `candidate_*` pour audit.

Une censure liée au futur **ne retire pas l'entité de la matrice de features/prédictions**.
La sélection du portefeuille utilise tous les scores disponibles à T, y compris ceux
dont le futur sera non observable ou ininterprétable. Le ledger garde les exclusions
connues à T et les annotations futures séparément. Aucune ligne censurée ne reçoit un
label artificiel, de zéro ou d'horizon raccourci.

Les observations de 2022–2023 servent uniquement au passé nécessaire aux features 2024.
L'historique 2025 S2 n'entre pas dans le retrain ; les features 2026 peuvent naturellement
utiliser les prix passés de S2 2025, connus à leur cutoff.

## C. Six familles, douze tâches et registre additif

Pour P0 = dernier close disponible à T et Ph = h-ième close strictement futur :

| Famille | Définition H5/H10 | Modèle |
|---|---|---|
| direction_abs | sign(PH/P0 − 1) | classification binaire hors zéros |
| return_abs | PH/P0 − 1 | régression |
| direction_rel | sign(return_abs − return_benchmark) | classification binaire hors zéros |
| rank_pct | rang moyen ascendant du rendement / N | régression de percentile |
| excursion_balance | max(Ph/P0−1) + min(Ph/P0−1), h=1..H | régression |
| trend_tstat | pente OLS / son erreur-type, sur H closes futurs base 100 | régression |

Les labels direction **−1/0/+1** sont conservés dans la base. Les zéros exacts sont exclus
du fit et des métriques binaires ; les scores sont quand même produits pour leurs entités.
La classe binaire vaut 1 si direction positive, sinon 0 pour direction négative. Le seuil
de décision est **strictement >0,5**, fixé avant évaluation. L'IC de direction utilise
les modalités originales, zéros compris lorsqu'ils sont observables.

### Excursion balance

La mesure utilise les **closes**, pas les highs/lows. Elle n'est ni une amplitude max−min,
ni une volatilité. Aucun zéro n'est ajouté à la fenêtre : une trajectoire entièrement
positive a un min positif, et une entièrement négative un max négatif.

- max +7 %, min −3 % : +4 % ;
- max +4 %, min −9 % : −5 % ;
- max +10 %, min −10 % : 0.

### Trend t-stat

```text
Bh = 100 × Ph / P1, h=1..H
Bh = a + b × h + epsilon_h
SE(b) = sqrt[(sum(epsilon²)/(H−2)) / sum((h−mean(h))²)]
target = b / SE(b)
```

La base 100 rend la trajectoire lisible ; une multiplication des prix par une constante
positive ne change pas le t-stat. Pour gérer la limite numérique, une trajectoire plate
vaut 0, une linéaire non plate atteint ±1e6 ; tous les t-stats sont plafonnés à cette limite.
La tolérance est 1e−12 × max(1,max(abs(B))). Aucun réglage de ce plafond à la lecture de 2026.
Les valeurs limites peuvent dominer une perte quadratique ; cette sensibilité est une limite.

### Registre et views

`hocus_quant.model_lab.targets.registry_document()` est **SPEC-008-targets/1.0.0** : les
45 définitions historiques sont reprises sans modification, puis quatre IDs sont ajoutés :

- `future.excursion_balance.h5.v1`, `future.excursion_balance.h10.v1` ;
- `future.trend_tstat.h5.v1`, `future.trend_tstat.h10.v1`.

Le nouveau document contient 49 définitions et son propre fingerprint, avec le fingerprint
parent. Le registre gelé SPEC-005/SPEC-007 n'est jamais remplacé. Un catalogue DuckDB séparé
`model_lab.duckdb` expose `spec008_features`, `spec008_targets`, `spec008_eligibility`,
`spec008_split_audit` et une view par famille. Les IDs exacts se retrouvent dans le registre
de modèles, les prédictions et toutes les métriques.

Le benchmark relatif est le **CAC AllShares** mappé. La formule héritée utilise son propre
H-ième close futur ; `benchmark_end` permet d'auditer les éventuelles dates de fin différentes
de celles de l'action. Le rank_pct est recalculé dans la cohorte éligible à T avec rendements
observables/interprétables à l'intérieur de la période. Son échantillon de labels peut donc
être plus petit que la cohorte de décision, explicitement conservée.

## D. Features strict 85 / strong 138

Fingerprint : `7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f`.

Seuls les IDs canoniques des **85 strict** et des **138 strong** sont utilisés, avec les
aliases/signatures de rang d'origine et les valeurs manquantes. Broad 504 n'est pas lancé.
La routine additive évalue ces IDs avec les helpers de formules hérités inchangés ; un
test de parité compare les 138 valeurs au moteur complet.

Les features utilisent seulement session_date<=T et available_at<=00:00 Europe/Paris D+1.
L'éligibilité approved utilise exclusivement la qualité passée, puis la présence d'au
moins une feature strong calculable. Les deux feature sets partagent cette cohorte.
Les nulls sont conservés dans les matrices ; leur taux est reporté par split/feature set.

## E. Modèles et preprocessing

| Référence | Classification | Régression |
|---|---|---|
| Naïve | prior de classe train, décision majorité | constante moyenne et constante médiane train |
| Linéaire | Logistic Regression C=1, max_iter=2000 | Ridge alpha=10 |
| RF | RandomForestClassifier | RandomForestRegressor |
| Principal XGB | XGBClassifier binary:logistic | XGBRegressor squarederror |

RF et linéaire : médiane train par colonne + **indicateur de missing pour chaque feature**.
Le scaler linéaire est fit après cette transformation sur train uniquement. Une colonne
entièrement manquante dans le train est conservée avec constante technique 0 et indicateur
1, pour maintenir les dimensions ; elle n'est pas reconstruite à partir du futur.
XGB utilise ses NaN natifs, sans imputation ni scaler externes.

Au retrain final, tous les preprocessors sont refit uniquement sur 2024 + S1 2025 avec les
paramètres déjà choisis. Les scores test sont produits sans refit, seuil optimisé,
calibration ajustée ni choix de features en 2026. Les modèles sont persistés en joblib
avec l'ordre des IDs et leur provenance ; le reload identique est testé.

## F. Tuning limité

[Configuration versionnée](../configs/experiments/model_lab_v1.toml).

- RF 1 : 80 arbres, profondeur 4, feuille minimum 30, max_features 0,5.
- RF 2 : 120 arbres, profondeur 7, feuille minimum 50, max_features 0,7.
- XGB 1 : 100 arbres, profondeur 2, learning_rate 0,04, subsample 0,8,
  colsample 0,7, min_child_weight 30, alpha 0,1, lambda 10.
- XGB 2 : 160 arbres, profondeur 3, learning_rate 0,03, subsample 0,8,
  colsample 0,8, min_child_weight 50, alpha 0,5, lambda 20.

XGB CPU hist, quatre threads ; toutes les seeds = **20261005**. Pas d'early stopping sur
le test. Sélection : AUC pooled validation pour les directions, **IC moyen par cutoff
validation** pour les régressions. Égalités de paramètres : premier essai de la grille.
Le modèle et feature set présentés comme gagnants dans le rapport sont choisis sur
validation exclusivement, puis relus en test. Le rapport conserve tous les comparateurs.

Comptes prévus : 8 combinaisons classification × 6 fits = 48 ; 16 combinaisons régression
× 7 fits = 112 ; **160 fits train/validation**, puis **112 retrains finaux**. Le petit
ensemble de grilles n'élimine ni la multiplicité ni la contamination préalable du lock.

## G. Métriques et contrôles de fuite

Classification : ROC AUC, PR AUC (average precision), accuracy, balanced accuracy,
log loss, Brier, calibration à dix bins fixes et ECE, confusion matrix, taux positif.
Une coupe à une seule classe ne reçoit pas d'AUC/balanced accuracy artificielles.

Régression : RMSE, MAE, R², Pearson et Spearman pooled, IC de rang par cutoff, moyenne,
médiane, écart-type et fraction IC>0. Minimum de 30 couples pour l'IC, rangs moyens
pour les ex æquo. Une prédiction constante ne reçoit pas un IC de zéro inventé.

Toutes tâches : D1..D10, N, moyenne/médiane du target, moyenne du rendement absolu,
taux positif, spread D10−D1 et monotonicité. Les déciles sont construits **par date**,
sans casser artificiellement les ties. Les lifts top10/top20/bottom10 sont rapportés
à la population du même cutoff ; les quantiles à ties peuvent englober plus de titres.
Pour rank_pct, les labels sont toujours positifs : son lift de taux positif est trivial
et le rendement top-bottom / backtest est nécessaire pour la lecture économique.

Les joins sont 1:1 par entité/cutoff ; features et labels sont dans des tables distinctes.
Les preprocessors n'acceptent jamais la target comme colonne. Les résultats de tuning
portent tous split=validation et les dates des fits sont persistées. Une target qui
franchit la borne est nulle ; aucune exclusion future ne modifie la matrice de décision.

## H. Résultats et trajectoires

Le [rapport automatique](SPEC_008_RESULTS.md) fournit dates, effectifs, couvertures,
gagnants de validation, tous les comparateurs, résultats test et coûts. Il est généré
depuis les Parquet et les JSON ; ses tables ne sont pas recopiées à la main.

`trajectory_diagnostics.parquet` compare prédictions et vérités des nouvelles targets
avec return_abs, max_upside, max_downside et volatilité future. Ces diagnostics aident
à identifier une proxy de risque ; les corrélations pooled ne sont pas une décomposition
causale ni un test indépendant. Les trajectoires faible rendement/t-stat élevé et
fort rendement/t-stat faible sont illustrées dans le rapport à partir des prix observés.

Importances RF impurity / XGB gain, plus permutation de **toutes** les features sur
validation S1 2025, estimateur original fit sur 2024, une réplication à seed fixe.
La permutation mélange les lignes de validation, sans blocs temporels : elle mesure
une sensibilité marginale descriptive, sans fournir d'inférence temporelle.
Les importances ne déclenchent aucune suppression de variables. Les corrélations entre
features rendent leurs contributions marginales instables. SHAP n'est pas ajouté en V1.

## I. Simulation et coûts

**Development backtest — not independent confirmation.**

- Score du cutoff D calculé après disponibilité du dernier prix entrant dans les features.
- Entrée : open de la prochaine séance commune strictement après D.
- Sortie : close de la H-ième séance commune après D ; H closes de tenue, sans raccourcissement.
- Sélection : ceil(10 % × N) scores les plus élevés, égalités départagées par ID stable.
- Long-only, sans levier ; le nouveau compartiment reçoit au plus NAV précédente / 2
  en H5, / 3 en H10, limité au cash disponible, réparti également entre les titres choisis.
- Chaque vintage est tenu séparément ; le même titre peut figurer dans plusieurs vintages.
  Les entrées au matin ne peuvent utiliser une liquidation prévue au close du même jour.
- Cash non rémunéré, positions valorisées aux closes observés, sans fill futur inventé.
- Open absent : ordre non exécuté, capital correspondant reste en cash, motif conservé.
  Close de sortie absent : liquidation au prochain vrai close, retard explicitement annoté.
  Position non liquidable à la fin : unresolved, elle reste dans la NAV et interdit une
  lecture de performance complète de la stratégie.

Frais **aller-retour all-in** : 0 / 10 / 25 / 50 bp, moitié par jambe. Les shares d'entrée
tiennent compte du fee d'achat ; le fee de vente est déduit des proceeds une seule fois.
Les cohortes ne sont jamais supprimées parce que leurs prix futurs sont suspects.
Les séries raw sont simulées avec annotations : aucune correction implicite de split,
aucun dividende ajouté, aucune promesse de rendement ajusté.

Baselines : equal-weight de toute la cohorte de scores avec les **mêmes compartiments,
dates et frais** ; CAC AllShares buy-and-hold next_open→dernier close sur la fenêtre.
Le benchmark index est pleinement investi, donc son exposition diffère de celle des
compartiments : l'excess return n'est pas un alpha ajusté du risque.

Outputs : NAV quotidienne/cutoff, cash/exposure/holding count, coûts, turnover achats+ventes,
trades/retards/anomalies, rendement cumulé, volatilité annualisée, Sharpe descriptif,
drawdown, hit rate, rendement moyen trade, benchmark et excès. Rendement annualisé
seulement à partir de **126 séances** ; S1 reste court pour une lecture Sharpe.

## J. Limites et décision de suite

- PIT **reconstructed**, strict_pit_claimed=false ; récupération réelle en septembre 2026.
- Composition SRD de livraison, survivorship/radiations incomplets ; aucun SBF 120 PIT.
- Corporate actions, ajustements historiques et dividendes insuffisamment certifiés.
- Univers progressivement réduit par la qualité cumulée passée ; modalités à auditer.
- H10 hebdomadaire comporte des outcomes chevauchants ; cutoffs et titres dépendants.
- Lock déjà choisi sur 2025/2026 ; test de développement uniquement.
- Grilles et tables multiples ; aucune correction multiple ni preuve d'alpha.
- Coûts all-in stylisés sans capacité, slippage variable ni liquidité de marché.

La règle descriptive de lecture du rapport demande pour un **GO exploratoire** au moins
75 % d'IC test positifs parmi les gagnants RF/XGB choisis en validation, et au moins 75 %
de gagnants dépassant la baseline equal-weight comparable à 50 bp. Sinon : NO-GO pour
un nouveau cycle de tuning en l'état. Cette grille de lecture n'est pas un test statistique.
Un backtest plus réaliste demande d'abord la réparation des limites de prix/univers.
SPEC-007 reste le protocole distinct pour les observations vraiment nouvelles.

## Reproduction, UI et provenance

```bash
uv sync --locked --all-extras
uv run python scripts/model_lab_spec008.py data
uv run python scripts/model_lab_spec008.py run
uv run python scripts/model_lab_spec008.py report
uv run marimo run notebooks/model_lab.py
```

Le `data/research.duckdb` et ses fichiers silver doivent exister ; les vues source relatives
demandent de lancer depuis la racine du worktree. Aucun import réseau n'est déclenché.
La config sérialisée est vérifiée au replay ; un changement demande un nouveau dossier.
Chaque run conserve config/dataset/registre/lock/versions/source hashes, SHA Git et dirty,
dates, hyperparamètres, seed et checksum du modèle. Tous les datasets/modèles sont hors Git.

Model Lab : **Overview · Model Benchmark · Target Comparison · Score Deciles · Backtest ·
Feature Importance · Methodology**. Filtres target/horizon/set/model/coût. XGB strict
direction_abs H5 est le défaut explicite, sans choix du meilleur test.

Tests : nouvelles formules, scaling/limites, purge H5/H10, preprocessing train-only,
sélection validation-only, conservation des fichiers SPEC-007, déterminisme/reload,
NaN/empty/single-class/ties, dates d'exécution, chevauchement, frais, equal-weight,
prix manquants, corporate-action flagged et replay. Les résultats réels servent à des
contrôles de provenance/splits, jamais à sélectionner des hyperparamètres.

### Vérifications exécutées le 5 octobre 2026

- Suite complète : **149 tests réussis, 1 ignoré**, en 182,11 secondes. Le test ignoré
  attend un grand snapshot local historique volontairement absent de Git.
- Ruff : aucune erreur ; MyPy : aucune erreur dans les 45 fichiers source.
- Marimo : notebooks Model Lab et SRD valides ; `git diff --check` sans erreur.
- Navigateur : les sept onglets s'ouvrent, graphique de déciles visible, aucun
  événement JavaScript d'erreur ; service local HTTP 200, route publique protégée
  par l'authentification sandbox existante.
- SPEC-007 et lock : comparaison des octets avec le commit de départ, protocole
  gelé vérifié en lecture seule ; dépôt initial conservé propre.

Accès : [Model Lab sandbox](https://sandbox.hocus.works/quant-model-lab/).
Déploiement isolé : service `hocus-quant-model-lab-sandbox`, port loopback 8069,
worktree `spec/008-multivariate-model-backtest`. Le laboratoire SRD reste sur son service.

Références primaires : [API XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html),
[SimpleImputer](https://scikit-learn.org/stable/modules/generated/sklearn.impute.SimpleImputer.html),
[métriques scikit-learn](https://scikit-learn.org/stable/modules/model_evaluation.html).
