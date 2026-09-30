# SPEC-006 — premier rapport sur les données

**Exécution :** 30 septembre 2026
**Run :** `d3e905f7c34741b83c70b910`
**Périmètre :** 27 dates hebdomadaires, du 5 avril au 4 octobre 2024, avec `quality_scope=approved`, les seuls targets `research_ready` et un PIT de grade `reconstructed`.

## Couverture matérialisée

| Élément | Résultat |
| --- | ---: |
| Dates analysées | 27 |
| Fenêtre couverte | 2024-04-05 → 2024-10-04 |
| Entités par date | 1 650 min. · 1 664 médiane · 1 674 max. |
| Cellules de features dans le cube | 47 047 864 |
| Cellules disponibles | 41 446 793 · 88,09 % |
| Features avec au moins une relation globale | 1 006 |
| Targets | 45 (9 familles × 5 horizons : H5, H10, H20, H60, H120) |
| Relations feature × target globales testées | 45 270 |
| Relations avec au moins 13 cutoffs | 40 320 |
| Relations écartées du test temporel faute de cutoffs | 4 950 |
| Lignes d’historique IC, toutes portées confondues | 6 359 361 |
| Lignes de déciles | 2 785 266 |
| Taille des artefacts d’analyse | env. 1,54 Go |

Les 1 006 features sont celles présentes dans les sorties de l’analyse, parmi les 1 048 entrées du registre. Le nombre de `aligned_x_y_observations_global` du manifeste, 1 700 094 443, est une somme des observations alignées sur chaque relation feature-target et **ne représente pas 1,7 milliard de lignes uniques**.

Le cube a 0 erreur de partition. L’audit des targets a également 0 erreur de slice. Le jeu contient 2 020 185 lignes de targets en entrée ; 1 905 057 sont research-ready et 115 128 sont exclues de cette analyse. Les exclusions incluent des observations indisponibles, des historiques futurs insuffisants, des références de benchmark absentes ou des contrôles de qualité. Le grade PIT est `reconstructed` et `strict_pit_claimed=false`.

Les cibles de rendement relatif ont une couverture de benchmark d’environ 81,8 % de la population mappée. Sur H20, 36 454 targets relatifs sont disponibles dans l’audit, sur 44 893 lignes de cette cible (environ 81,2 %). Les extrêmes représentent 1 941 lignes sur 143 événements ; 50 événements restent non résolus. Les règles SPEC-005R les excluent du périmètre research-ready lorsqu’elles l’exigent.

## Résultats descriptifs

La médiane de l’IC Spearman par date, toutes les relations globales réunies, est −0,0056. Les quantiles 1 %, 25 %, 75 % et 99 % sont respectivement −0,5869, −0,0437, 0,0276 et 0,7036. Ces agrégats mêlent familles de features et de targets ; ils ne décrivent pas un signal unique.

Pour `return_rel` H20, 896 relations globales remplissent le seuil de 13 dates. La médiane de leur IC moyen est −0,0105 ; la médiane de couverture est 99,70 %. Parmi elles, 246 ont une q-value descriptive ≤0,25 après Benjamini-Hochberg appliqué séparément par portée, famille de target et horizon.

| Portée | Relations q ≤ 0,25 | Relations éligibles |
| --- | ---: | ---: |
| Global | 22 762 | 40 320 |
| Equity | 20 835 | 40 320 |
| Equity DE | 27 951 | 40 320 |
| Equity US | 18 442 | 40 320 |
| FX / taux | 14 660 | 30 975 |
| Indices | 10 752 | 31 010 |
| Indices sectoriels | 1 431 | 11 361 |

Exemple de relation ressortant pour `return_rel` H20 : `close.log.trend_r2.w60.v1`, IC moyen −0,0461, t descriptif −6,341, q=0,00023, 27 dates et couverture 99,4 %. Cette relation est une piste exploratoire et ne prouve ni stabilité hors période, ni rendement de stratégie.

Les q-values globales calculées sont 17 795 à 0,05, 19 527 à 0,10 et 22 762 à 0,25. Une correction FDR n’annule pas les limites du test utilisé. Les rendements futurs H10 à H120 se chevauchent entre dates hebdomadaires ; les IC successifs sont donc dépendants. Les tests t et q-values sont **descriptifs**, et leur interprétation comme tests confirmatoires serait trop forte.

## Décision de recherche

**NO-GO pour SPEC-007 comme preuve confirmatoire d’alpha ou sélection d’une stratégie. GO pour une étape suivante de recherche exploratoire et de contrôle du pipeline.**

La fenêtre analysée ne couvre que six mois en 2024, une seule période de marché, avec des targets à rendements chevauchants et un PIT reconstruit. Il faut étendre le panel dans le temps, examiner la stabilité par sous-période et famille, puis corriger l’inférence pour la dépendance temporelle avant de tirer des conclusions. Aucun modèle, feature de delta short, stratégie ou backtest n’est produit par SPEC-006.

## Reproduction

```bash
uv run python -m hocus_quant.cli analyze-signals \
  --feature-cube data/feature_cube/spec006-weekly-demo \
  --target-set data/targets/spec006-weekly-demo \
  --output data/analysis/spec006-weekly-demo \
  --minimum-n 30 --minimum-cutoffs 13 --fdr-alpha 0.25
```

Les données source de ces résultats restent dans `data/` et ne sont pas ajoutées à Git. Le manifeste de sortie donne les empreintes des contrats du cube et des targets ainsi que l’empreinte du code d’analyse.
