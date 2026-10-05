# SPEC-008 — extension au registre complet

**Demande :** faire tourner toutes les variables ensemble, sans se limiter aux 85/138
candidats. Le set `all` contient les **1 048 IDs du registre canonique**, y compris
les fenêtres 504, les aliases, les transformations redondantes et les variables constantes.
Il s'agit des features de marché existantes ; aucune nouvelle feature AMF ou macro
n'est inventée pour cette expérience.

## Contrat de comparaison

- Même univers SRD, mêmes lignes entité/cutoff, mêmes targets et même ledger de qualité
  que SPEC-008 initial. Les sources, targets, éligibilité et splits sont copiés
  à l'identique depuis les snapshots du premier run, après vérification des checksums.
- Les 1 048 features sont recalculées avec le moteur canonique sur les seules observations
  de date ≤T et disponibles au cutoff. Chaque valeur des 138 anciennes features est
  comparée au premier run avec une tolérance numérique de 1e-12.
- Aucun filtre de feature selon un IC, une importance ou un résultat 2025/2026.
- Train 2024, validation S1 2025, retrain 2024 + S1 2025, test S1 2026 ; purges H5/H10
  et frontière des labels inchangées.
- Même seed, grilles RF/XGB, Logistic/Ridge, baselines, prétraitement train-only,
  seuil de classification et frais 0/10/25/50 bp. Les hyperparamètres sont choisis
  en validation uniquement ; aucun retuning 2026.
- 12 tâches, 80 fits de découverte/validation, 56 modèles finaux, 232 backtests.
  Le benchmark initial Strict/Strong est relu depuis ses artefacts, sans le réentraîner.
- Importance par permutation des 1 048 features sur validation, une réplication,
  estimateur original entraîné sur 2024 ; RF impurity/XGB gain conservés.

## Disponibilité et valeurs constantes

Les fenêtres longues sont souvent absentes au début de 2024. Les NaN restent des NaN
dans la matrice et dans XGBoost. RF/linéaire conservent l'imputation médiane train-only
et les indicateurs d'absence. Une colonne entièrement absente de train est conservée
avec la constante 0 par `keep_empty_features=True` ; cette exception est explicite et
ne représente pas une valeur observée. Les constantes comme base100 restent incluses.

Le nombre d'IDs ne mesure pas le nombre d'informations indépendantes. Ce run teste
l'effet de fournir le registre entier, sans prétendre que chacune des variables est
utile ou disponible sur chaque ligne. Le rapport conserve la missingness par feature.

## Lecture des résultats

Comparer d'abord les mêmes targets/horizons entre `all`, Strict et Strong. Les modèles
retenus dans chaque set sont choisis sur validation, puis leurs résultats test sont lus.
Un artefact séparé compare aussi les mêmes types de modèle entre sets. Cela évite de
confondre mécaniquement un changement de modèle et un changement du nombre de features.

Le rapport conserve le critère descriptif de suite SPEC-008, sans lui attribuer de
significativité. Les résultats 2024–2026 restent du développement déjà exploré.
SPEC-007 et le lock restent gelés. Aucune observation de confirmation n'est consommée.

## Reproduction et accès

```bash
uv run python scripts/model_lab_spec008.py data \
  --config configs/experiments/model_lab_all_features_v1.toml \
  --output data/analysis/spec008-model-lab-all-features
uv run python scripts/model_lab_spec008.py run \
  --config configs/experiments/model_lab_all_features_v1.toml \
  --output data/analysis/spec008-model-lab-all-features
uv run python scripts/model_lab_spec008.py report \
  --config configs/experiments/model_lab_all_features_v1.toml \
  --output data/analysis/spec008-model-lab-all-features
uv run python scripts/compare_model_lab_all_features.py
```

Les données locales sont hors Git. Les partitions de calcul des features permettent
une reprise, à configuration et registre identiques. Le calcul utilise quatre workers
au maximum ; il n'ajoute aucun service d'orchestration.

[Model Lab sandbox](https://sandbox.hocus.works/quant-model-lab/) : le sélecteur
d'expérience distingue Strict/Strong et « Toutes les variables · 1 048 features ».
Les sept onglets et les contrôles H5/H10/target/modèle/frais restent disponibles.

Le benchmark initial est conservé sous `data/analysis/spec008-model-lab` ; l'extension
utilise exclusivement `data/analysis/spec008-model-lab-all-features` et des rapports dédiés.

## Exécution et contrôles

Le run complet a terminé les 80 fits de validation, 56 retrains finaux et 232 backtests
en environ 59 minutes. Les résultats sont dans le [rapport complet](SPEC_008_ALL_FEATURES_RESULTS.md)
et le [comparatif Strict / Strong / All](SPEC_008_ALL_FEATURES_COMPARISON.md).

Les contrôles de parité des 138 anciennes features et des clés de cohorte ont passé.
Les 56 modèles enregistrent chacun les 1 048 IDs ; les essais d'hyperparamètres utilisent
uniquement la validation. Le rechargement d'un modèle de chacune des quatre familles
reproduit ses prédictions stockées à 1e-12 près. Ruff, mypy et le contrôle Marimo passent.
Les sept onglets, le changement d'expérience et les sélecteurs target/horizon/frais ont
été vérifiés dans le navigateur sans erreur JavaScript. Les artefacts initiaux et
SPEC-007 sont conservés à l'identique.
