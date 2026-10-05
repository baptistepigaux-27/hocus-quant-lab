# SPEC-006R — Top 500 rendement/direction, H5 uniquement

**Calcul exécuté le 3 octobre 2026.** Univers `equity` : livraison ABC Bourse SRD Paris.

## Méthode

1. Réutiliser les features et targets existants, avec leurs règles de disponibilité et de qualité.
2. Restreindre les candidats de 2024 aux targets H5 **avant** le classement et la troncature.
3. Conserver les cinq familles rendement/direction : `return_abs`, `return_rel`, `direction_abs`, `direction_rel`, `rank_pct`.
4. Exiger au moins 1 000 couples, 13 cutoffs et 60 % de couverture. Il reste **4 480 candidats** (896 par famille).
5. Appliquer la règle historique `q_abs_ic_coverage_cutoff_v1` : q-value croissante, puis amplitude IC décroissante, couverture et cutoffs décroissants, identifiants.
6. Geler les 500 relations en 2024, puis évaluer exactement leurs identités feature/target sur 2025 et 2026. Aucune nouvelle sélection sur ces années.

H5 signifie **cinq séances futures**, avec le rendement `close(T+5)/close(T)-1`. Les fenêtres historiques des features ne sont pas restreintes à cinq séances.

Le classement donne **500 targets `future.direction_abs.h5.v1`**, associés à 500 features. Les quatre autres familles étaient candidates mais arrivent derrière. Le mode actuel ne force aucune répartition par famille.

Les q-values du tableau de découverte ont été calculées par groupe dans le scan précédent ; ce calcul ne les recalcule pas sur les seuls 500 retenus. Les q-values de validation sont descriptives et corrigées au sein de la cohorte gelée.

## Résultats sur les mêmes 500 relations

| Période | Cutoffs évalués | IC moyen signé | Médiane \|IC\| | Sens conservés vs 2024 | Inversions | Rétention médiane amplitude |
|---|---:|---:|---:|---:|---:|---:|
| 2024_discovery | 27 | -0.016569 | 0.028067 | Référence | — | Référence |
| 2025_validation | 27 | +0.011252 | 0.022962 | 170/500 (34.0 %) | 330/500 (66.0 %) | 65.9 % |
| 2026_validation | 25 | +0.008478 | 0.022968 | 179/500 (35.8 %) | 321/500 (64.2 %) | 70.6 % |

**IC = corrélation de rang de Spearman, pas un rendement.** La moyenne signée mélange des relations positives et négatives. La médiane des amplitudes et le nombre de signes conservés complètent sa lecture.

La rétention d’amplitude est la médiane des ratios `abs(IC_validation)/abs(IC_2024)` relation par relation. Elle ne mesure ni un rendement, ni une confiance statistique.

### Dates et maturité

- 2024 : cutoffs du 05/04 au 04/10, 27 dates.
- 2025 : cutoffs du 06/04 au 04/10, 27 dates, tous mûrs à H5.
- 2026 : partitions du 05/04 au 28/09 ; seules 25 dates, jusqu’au **18/09**, ont une target H5 suffisamment mûre. Comparaison partielle.

### Stabilité commune à 2025 et 2026

- **129/500 (25,8 %) ont le même signe qu’en 2024 dans les deux validations.**
- 65/500 conservent aussi au moins 80 % de l’amplitude 2024 dans chacune des deux validations.
- 22/500 sont classés `stable` dans les deux validations par la règle de l’atlas, qui exige également une cohérence du signe des IC par cutoff.

Ces comptages décrivent la cohorte sélectionnée, pas 500 hypothèses indépendantes.

## Interprétation et limites

- Les inversions 2025 passent de 479/500 dans l’ancien top tous horizons (484 H120 et 16 H60) à **330/500** dans le nouveau top H5. Ce sont deux sélections différentes ; cette comparaison ne constitue pas une estimation causale de l’effet de l’horizon.
- Les IC H5 sont faibles. La meilleure q-value de découverte est **0,454851** ; les meilleures q-values descriptives de validation sont **0,562542** en 2025 et **0,701452** en 2026. Aucune relation de cette cohorte ne passe les seuils q ≤ 0,05, 0,10 ou 0,25.
- Le nombre de relations positives/négatives est 136/364 en 2024, 360/140 en 2025 et 333/167 en 2026.
- Les 500 features représentent **420 signatures exactes de rang** sur le panel SRD 2024 ; 153 features appartiennent à des groupes ayant une signature dupliquée. Des relations supplémentaires peuvent aussi être fortement corrélées.
- H5 réduit le chevauchement des fenêtres hebdomadaires ; les jours fériés, les calendriers par titre et la dépendance des IC interdisent de supposer automatiquement leur indépendance.
- Le filtre qualité dépendant des mouvements futurs reste celui du pipeline existant. Le mode candidate de Marimo permet d’en explorer la sensibilité pour une relation.
- L’univers SRD est reconstruit à partir de livraisons 2026 ; ce n’est pas un univers SBF 120 point-in-time. Les corporate actions et la convention d’exécution après close restent à traiter.

**Conclusion : cette sélection H5 ne fournit pas de preuve établie de prédictivité exploitable.** Le phénomène d’inversion extrême H120 s’atténue, mais le classement H5 sélectionne surtout des associations faibles et instables.

## Extension : top 100 par fenêtre historique

La [comparaison par fenêtre](SPEC_006R_H5_BY_WINDOW.md) sélectionne 100 features
par fenêtre en 2024 et compare leurs signes d’IC en 2025, avec la même target
direction H5. Elle utilise le scan complet de 2024.

## Reproduction et artefacts

```bash
uv run python -m hocus_quant.cli build-stability-atlas \
  --config configs/experiments/stability_atlas_h5.toml \
  --output data/analysis/spec006r-stability-atlas-h5-top500
```

Le moteur produit aussi un top général de 100 relations pour compatibilité avec l’atlas. Les statistiques ci-dessus utilisent exclusivement `selection_bucket = return_direction` et le scope `equity`.

Artefacts locaux non versionnés dans `data/analysis/spec006r-stability-atlas-h5-top500/` :

- `frozen_top_signals.parquet` : sélection gelée et définitions.
- `signal_stability_summary.parquet` : mesures par période sur le scope de sélection.
- `signal_period_ic_history.parquet` : IC par cutoff.
- `signal_period_deciles.parquet` : déciles et cibles.
- `stability_audit.json` / `.md` : méthode, maturité et comparaison.
- `h5_diagnostics.json` : synthèse et redondance des rangs. Les signatures exactes utilisent la fonction `_rank_signature_count` du script de cause racine avec les features de cette cohorte.

Les fichiers sous `data/` ne sont pas versionnés. Aucun modèle ni backtest portefeuille n’est ajouté.

## Marimo

Le [laboratoire SRD](https://sandbox.hocus.works/quant-lab-srd/?v=h5) ouvre **H5 uniquement · top 500** par défaut. Les périodes 2024, 2025 et 2026 sont accessibles. L’ancien top tous horizons et son audit H120 restent explicitement séparés.

Ruff et MyPy sur le code d’analyse modifié passent ; `marimo check --strict` passe. Un export HTML a exécuté les cellules sous l’utilisateur du service et ses montages en lecture seule. La route locale répond 200 et la route publique conserve l’authentification du sandbox (401 sans identifiants).
