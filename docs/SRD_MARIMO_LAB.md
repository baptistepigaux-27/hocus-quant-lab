# Laboratoire Marimo SRD 2024–2026

**Parcours principal depuis SPEC-006T :** [Research Contract et candidate lock H5](SPEC_006T_EX_ANTE_RESEARCH_CONTRACT.md).
Le sandbox ouvre désormais les sections Research Contract, Candidate Explorer et Signal Detail.
Le toggle **Ex-ante cohort / Future-clean cohort** consulte les IC précalculés ; les tiers
et le bootstrap restent ceux du lock ex ante. Les années 2025/2026 sont des périodes de
développement, et la confirmation indépendante attend de nouvelles données.
Les étapes historiques ci-dessous restent disponibles pour l'audit de l'ancienne méthode.

Le notebook [`notebooks/srd_research_lab.py`](../notebooks/srd_research_lab.py)
permet de reprendre l'analyse rendement/direction à partir des données SRD
locales. Il ouvre DuckDB en lecture seule et ne modifie ni raw, ni silver, ni les
artefacts SPEC-006.

## Installation et lancement

Depuis la racine du dépôt :

```bash
uv sync --extra notebook
make srd-lab
```

La commande ouvre l'éditeur Marimo sur l'interface locale indiquée dans le
terminal. Pour exécuter le notebook comme une application sans éditeur :

```bash
make srd-lab-run
```

L'application interactive déployée dans le sandbox est disponible sous
[`https://sandbox.hocus.works/quant-lab-srd/`](https://sandbox.hocus.works/quant-lab-srd/).
Elle hérite de l'authentification du sandbox et conserve DuckDB, les Parquet et
le notebook en lecture seule.

La base par défaut est `data/research.duckdb`. Une autre base compatible peut
être fournie sans modifier le notebook :

```bash
HOCUS_QUANT_DB=/chemin/vers/research.duckdb make srd-lab
```

## Données attendues

Le parcours prix/qualité requiert :

- `data/research.duckdb` ;
- les vues `market_daily` et `market_daily_history` ;
- la livraison ABC Bourse SRD déjà importée.

Le parcours feature/target requiert aussi :

- `data/analysis/spec006t-ex-ante/`, généré par `scripts/build_spec006t_research_contract.py`,
  pour les sections de contrat, candidats et sensibilité ;
- `data/feature_cube/spec006-weekly-demo/` ;
- `data/feature_cube/spec006-2025-matched/` ;
- `data/feature_cube/spec006-2026-matched/` ;
- `data/targets/spec006-weekly-demo/` ;
- `data/targets/spec006-2025-matched/` ;
- `data/targets/spec006-2026-matched/` ;
- `data/analysis/spec006r-stability-atlas-h5-top500/frozen_top_signals.parquet` (défaut H5) ;
- `data/analysis/spec006r-stability-atlas-top500/frozen_top_signals.parquet`.

Les résultats H5 sont documentés dans [SPEC_006R_H5_RESULTS.md](SPEC_006R_H5_RESULTS.md).

Le tableau de diagnostic historique est généré avec :

```bash
uv run python scripts/audit_spec006r_root_causes.py
```

## Démarche intégrée au notebook

### 1. Prix et période

Choisir une action par ISIN et une période. Le notebook affiche le close, le
volume, la performance brute de la période, la variation journalière maximale
et l'instant `available_at` déclaré.

### 2. Ruptures de série

Choisir l'action courante ou tout le SRD, puis ajuster le seuil de variation
close/close. Le contrôle recherche aussi les ranges intraday supérieurs à 50 %
et les incohérences OHLC. Une ligne détectée reste une observation source à
expliquer ; le notebook ne la corrige pas automatiquement.

### 3. Relation feature/target

Le sélecteur propose **H5 uniquement · top 500** par défaut. Le filtre
`target_horizons = [5]` s'applique aux candidats avant classement et avant
troncature à 500. La liste est gelée sur 2024 ; les mêmes identités de relations
sont évaluées ensuite sur 2025 et 2026. Le périmètre est `equity` (SRD Paris).
L'ancien top tous horizons reste disponible via le même sélecteur.

H5 décrit les cinq séances **futures** du target. Une feature avec une fenêtre
historique de 120 ou 252 séances reste admissible : son information vient du passé.
Le rendement absolu conserve la convention de SPEC-005 : `close(T+5)/close(T)-1`.
Une simulation négociable doit encore préciser l'exécution après le close T.

Reproduction du nouveau calcul :

```bash
uv run python -m hocus_quant.cli build-stability-atlas \
  --config configs/experiments/stability_atlas_h5.toml \
  --output data/analysis/spec006r-stability-atlas-h5-top500
```


Choisir une feature du top rendement/direction gelé en 2024, son target exact,
la période 2024, 2025 ou 2026 (partielle) et l'un des deux échantillons :

- `research-ready` reproduit le pipeline publié ;
- `candidate` réintègre les valeurs marquées future review/quarantaine pour
  mesurer l'effet du filtre futur.

Pour un target `rank_pct`, le mode candidate utilise le rendement absolu brut du
même horizon. Cette substitution conserve le rang nécessaire au Spearman.

### 4. Recalcul

Le notebook joint feature et target sur `entity_id` dans chaque partition,
recalcule le Spearman par cutoff et reconstruit les déciles séparément à chaque
date. Il affiche les observations utilisées afin de permettre un contrôle
ligne par ligne.

### 5. Stabilité et cause racine

Le premier tableau donne le sens et l'amplitude des IC pour la sélection choisie.
Les IC sont des corrélations de rang, pas des rendements. Le mode H5 garde la règle
de classement historique (q-value, puis amplitude d'IC) pour rendre la comparaison
possible. Les q-values restent descriptives. H5 réduit le chevauchement hebdomadaire
mais ne résout ni le filtre qualité futur, ni les tests multiples et la redondance
des features, ni le caractère reconstruit de l'univers.

L'accordéon **Audit historique H120** est distinct de ce résultat. Son tableau compare le pipeline courant, les candidates et l'univers commun. Il
affiche aussi l'autocorrélation des IC. Les cutoffs H120 hebdomadaires se
chevauchent presque entièrement ; leurs p-values naïves ne doivent pas être
interprétées comme celles de répétitions indépendantes.

### 6. SQL libre

La dernière section fournit une console DuckDB limitée aux requêtes `SELECT` et
`WITH` sur les vues de la base. Les fonctions de lecture de fichiers, URLs,
extensions et commandes d'administration DuckDB sont bloquées. L'affichage est
plafonné à 1 000 lignes. Exemples utiles :

```sql
-- Couverture par action
SELECT isin, min(session_date), max(session_date), count(*)
FROM market_daily
GROUP BY isin
ORDER BY isin;

-- Variations journalières extrêmes
WITH ordered AS (
  SELECT isin, session_date, close,
         lag(close) OVER (PARTITION BY isin ORDER BY session_date) AS previous_close
  FROM market_daily
)
SELECT *, close / previous_close - 1 AS return_1d
FROM ordered
WHERE abs(close / previous_close - 1) >= 0.30
ORDER BY abs(return_1d) DESC;
```

## Limites à conserver visibles

- Les données ont été récupérées en septembre 2026 : PIT `reconstructed`.
- La livraison SRD n'est pas un historique de composition du SBF 120.
- Les corporate actions et vintages d'ajustement ne sont pas disponibles.
- Les features datées D utilisent le close D ; une simulation négociable doit
  définir un prix d'exécution ultérieur.
- Le mode candidate est un test de sensibilité et ne certifie pas les prix
  suspects.
- Les résultats décrivent des associations historiques, pas un alpha validé.
