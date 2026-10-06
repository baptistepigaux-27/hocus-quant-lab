# SPEC-008 — modèles d'indices comme futurs facteurs SRD

**Contrat v2 fixé avant les nouveaux fits, 6 octobre 2026.**

Le contrôle indépendant de la première exécution a détecté une différence UTC/Paris
qui excluait le close du cutoff, ainsi que des horizons allongés par les trous source.
La v1 est conservée localement dans `spec008-index-model-lab-v1-invalid-cutoff` pour
audit et ne constitue pas le résultat publié. La v2 corrige ces deux conventions
avant de refaire les données et les 112 modèles, sans modifier la sélection selon
la performance 2026. Les snapshots SRD historiques portent déjà minuit Paris,
contrairement à la vue `market_series` des indices qui porte minuit UTC. Le contrôle
des timestamps SRD confirme leur cohérence avec la coupe Paris du moteur existant.

## But

Mesurer d'abord la performance prédictive des modèles sur les indices. Les scores
doivent ensuite pouvoir servir de features de contexte aux modèles SRD. Cette phase
ne fabrique pas de portefeuille négociable d'indices et ne modifie pas le modèle SRD.

## Univers figés

La livraison contient 125 références, 121 codes distincts. Classification explicite
dans `src/hocus_quant/model_lab/indices.py`, indépendante des résultats des modèles :

- **market : 65 indices actions de marché** candidats ;
- **sector : 27 indices sectoriels** candidats, dont SOX et Nasdaq Biotechnology ;
- 13 séries auxiliaires (volatilité, taux, statistiques/breadth, Baltic Dry, CRB)
  conservées dans le snapshot source mais hors target de classement actions ;
- 9 indices à décrément/produits de rendement ajusté hors classement principal ;
- 7 variantes alternatives d'une même famille hors classement, choix documenté par code.

Les quatre codes présents dans les deux archives sont dédupliqués par code. Les
indices proches restant dans les groupes peuvent encore partager des constituants.
La liste livrée est une sélection actuelle, sans registre des créations ou disparitions
d'indices à chaque date ; les comparaisons restent conditionnelles à ce panel reconstruit.
Les quotes sont natives : les devises et conventions dividendes/price-return ne sont
pas harmonisées dans la livraison. Les résultats ne sont pas des rendements en euros.

## Données, features et qualité

Snapshots locaux en lecture seule, source brute conservée. Éligibilité à T : qualité
historique `approved`, au moins trois observations passées et dernière quote datant
d'au plus trois jours calendaires. Aucune inclusion fondée sur la performance future.
Les vrais défauts source futurs rendent le label ininterprétable ; les avertissements
futurs restent annotés et n'écartent pas le label.

Les **1 048 IDs canoniques** sont conservés, sans sélection par outcome. Disponibilité
des features : données de séance ≤T, disponibles selon les timestamps source
à minuit UTC le lendemain de T (01:00/02:00 Paris). La coupe v2 inclut ainsi le
close D quand il existe. Les volumes d'indices ne sont pas comparables :
volume relatif et indicateurs dépendant du volume restent indisponibles pour tout
l'univers, y compris le CAC40. Les valeurs source ne sont pas altérées.

Une série dont au moins 90 % des bougies passées sont `O=H=L=C` est traitée comme
close-only à ce cutoff : ses features d'open/high/low et d'intraday sont nulles.
Les statistiques de close, rendements, tendances et indicateurs calculables sur close
restent disponibles. Ce masque n'utilise que l'historique à T. Les colonnes entièrement
absentes ou constantes sont conservées et décrites dans les diagnostics train-only.

## Méthode du benchmark

- Train 2024, validation S1 2025, retrain 2024 + S1 2025, test S1 2026.
- Cutoffs du vendredi et horizons H5/H10 sur le calendrier commun CAC40. Chaque
  séance future utilise le dernier close natif connu jusqu'à cette date, sans
  regarder une quote ultérieure ; âge maximal trois jours calendaires. Les jours
  fériés propres à un marché peuvent donc conserver le close précédent. Un trou
  plus long rend le label indisponible et conserve le score à T. Date de référence,
  date commune de fin et date de la quote finale sont conservées.
- Purge de H séances du calendrier de référence et aucun label franchissant un split.
- Six targets identiques : direction absolue, rendement absolu, direction relative,
  rang du rendement, équilibre d'excursions, t-stat de tendance future.
- Le rang est calculé **dans chaque groupe**, jamais entre market et sector.
- Benchmark descriptif de direction relative : MSCI World, dernier close observé
  jusqu'à la date commune de fin du target. Ce mapping ne neutralise pas
  les effets de devise et les heures de clôture différentes.
- Même seed 20261005, mêmes grilles linéaires / RF / XGB, baselines et preprocessing
  train-only que le run SRD. AUC de validation pour directions, IC moyen pour régressions.
- Minimum **10 couples** pour un IC de cutoff, au lieu de 30 pour le SRD : le groupe
  sector n'a que 27 candidats. Ce changement précède les fits, sans adaptation au résultat.
- 24 tâches groupe/target/horizon ; 160 fits de validation et 112 modèles finaux.
- Cette phase mesure IC, AUC, calibration, R², déciles et paniers top 3 % descriptifs.
  Gain/impurity des arbres disponibles ; pas de permutation marginale dans cette phase
  de performance, et aucune nouvelle sélection de features à partir de l'importance.

## Performance et futur raccordement SRD

Les paniers top 3 % sont des **moyennes de rendements futurs par cutoff**, comparées
à l'univers et au bas du classement. Les fenêtres peuvent se chevaucher, surtout H10.
On ne les compose pas en equity curve et on ne leur attribue ni frais de broker ni
TTF : ils ne représentent pas des ordres sur des instruments exécutables.

Les scores test 2026 peuvent être exportés comme features rétrospectives : modèle
et hyperparamètres appris/choisis jusqu'au 30 juin 2025, score disponible après les
features à T. **Les scores de validation 2025 ne sont pas exportés comme features PIT** :
leur sélection d'hyperparamètres utilise la période de validation complète.
Pour étudier un raccordement SRD sur 2024/2025, produire ultérieurement des scores OOF
avec sélection et entraînement roulant, puis jointure as-of aux dates SRD.

Le grade PIT reste reconstruit. Les périodes 2024–2026 ont déjà été explorées dans le
labo ; elles restent des données de développement. SPEC-007 demeure gelé.
La comparaison SRD/indices ne doit pas attribuer un effet au seul changement d'univers :
les indices utilisent ici un calendrier de target commun, tandis que l'ancien
benchmark SRD emploie les observations futures propres à chaque titre.

## Reproduction

```sh
uv run python scripts/model_lab_spec008.py data \
  --config configs/experiments/model_lab_indices_v2.toml \
  --output data/analysis/spec008-index-model-lab
uv run python scripts/audit_index_dataset.py
uv run python scripts/model_lab_spec008.py run \
  --config configs/experiments/model_lab_indices_v2.toml \
  --output data/analysis/spec008-index-model-lab
uv run python scripts/report_index_models.py
uv run python scripts/audit_index_dataset.py --include-models
```

Le [rapport de résultats](SPEC_008_INDICES_RESULTS.md), les paniers descriptifs et
les scores destinés au futur raccordement sont générés après la fin du benchmark.
Les datasets sont locaux et ignorés par Git. L'onglet **Indices** du
[Model Lab](https://sandbox.hocus.works/quant-model-lab/) lit ces résultats précalculés.
