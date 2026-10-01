# SPEC-006 — stabilité hors échantillon 2025 / 2026

## Protocole préenregistré

La période de référence est le premier run SPEC-006 : cutoffs observés du
**5 avril au 4 octobre 2024**. Les fenêtres test sont le 5 avril–4 octobre
2025, puis le 5 avril–28 septembre 2026, dernière date de marché disponible
dans le corpus au moment de l’exécution. Chaque fenêtre résout 27 cutoffs selon
la grille hebdomadaire des dates réellement présentes dans les sources.

Les features et targets sont régénérés avec les commandes SPEC-004 et SPEC-005R,
`quality_scope=approved`, targets `research_ready` uniquement. Le top 100 est
figé sur les résultats 2024 avant de regarder 2025 et 2026. La sélection est
faite sur la portée `equity`, avec les critères `cutoff_count >= 13`,
`n_total >= 1 000` et `coverage >= 60 %`, puis tri par q-value croissante,
|IC Spearman moyen| décroissant, couverture décroissante et identifiants
lexicographiques. Cela évite de sélectionner le jeu de test avec les résultats
du jeu de test.

Le top 100 tous targets est constitué de 68 features et de 3 catégories de
targets : 30 relations `volatility H60`, 65 `volatility H120` et 5
`max_drawdown H120`. Pour vérifier séparément les signaux de performance, un
second top 100 est sélectionné avec les mêmes règles sur les familles
`return_abs`, `return_rel`, `rank_pct`, `direction_abs` et `direction_rel`.
Cette sélection comprend 32 features et uniquement des targets H120.

Pour chaque relation figée, l’impact est mesuré par la moyenne et la médiane
des IC Spearman cross-sectionnels par cutoff. La stabilité de signe rapporte
la part des cutoffs dont l’IC conserve le signe 2024, ainsi que le signe de
l’IC moyen annuel. La rétention d’impact est `abs(IC moyen test) / abs(IC moyen
2024)`. Ce sont des associations descriptives, pas des rendements de
portefeuille.

Le PIT reste `reconstructed`, non strict. Le scope `equity` du corpus ne
constitue pas un historique d’appartenance SBF 120. La fenêtre 2026 se termine
le 28 septembre parce que le corpus s’arrête à cette date. Les targets futurs
H60/H120 qui n’ont pas assez de séances ultérieures sont censurés et exclus ;
le nombre de cutoffs évaluables doit donc être lu avec les résultats de chaque
horizon. Les dates hebdomadaires et les rendements futurs chevauchants rendent
les IC temporels dépendants ; les q-values restent descriptives.

## Résultats

Les cubes de features et les targets ont chacun 27 partitions pour chaque
année, sans erreur de génération. Les targets 2025 comptent 1 856 060 lignes
`research_ready` et 117 280 lignes exclues par le hardening. En 2026, il y a
1 247 016 lignes `research_ready` et 841 659 lignes exclues, principalement
parce que les résultats futurs ne sont pas encore observables à la date d’arrêt.

### Top 100 tous targets — portée `equity`

Ce top est composé de 95 relations vers la volatilité future (30 H60, 65 H120)
et de 5 relations vers le drawdown maximal H120. Les 100 relations sont
observables sur les 27 cutoffs de 2025. Leur IC moyen passe de 0,5168 en 2024 à
0,5027 en 2025 ; la médiane des rétentions d’IC absolu est 95,6 %. Les 100
relations conservent leur signe moyen 2024 et le signe est aligné à chaque
cutoff 2025. Par famille, la rétention médiane est de 95,9 % pour la volatilité
H60, 95,7 % pour la volatilité H120 et 82,0 % pour le drawdown H120.

En 2026, les 100 relations conservent leur signe moyen sur les observations
disponibles ; la rétention médiane d’IC absolu est 93,0 %. Mais l’exposition
temporelle varie fortement : les relations H60 ont une médiane de 14 cutoffs,
alors que les H120 et drawdowns H120 n’en ont que 2. Les rétentions médianes
sont respectivement 94,5 %, 93,0 % et 63,8 %. Pour H120, cela ne constitue donc
qu’un contrôle préliminaire sur deux dates de cutoff.

### Top 100 performance — sélection distincte

Le top de performance comprend 6 relations `direction_abs`, 32 `rank_pct`,
31 `return_abs` et 31 `return_rel`, toutes H120. En 2025, les 100 relations
sont observables sur 27 cutoffs, mais seulement 6 conservent le signe moyen
2024. La médiane des cutoffs alignés en signe est 37,0 % et la rétention
médiane d’IC absolu est 22,9 %. L’IC moyen agrégé passe de -0,0999 à +0,0482.
Les médianes par famille montrent le même basculement : l’IC test est positif
pour `direction_abs`, `rank_pct`, `return_abs` et `return_rel`, alors que leurs
médianes 2024 étaient négatives.

En 2026, 69 relations sur 100 ont assez d’observations pour être évaluées, sur
2 cutoffs seulement (5 et 12 avril dans les partitions évaluées). À la date
d’arrêt des données, les targets H120 ne sont mûres que pour 4,9 % des lignes
`return_abs` candidates et 3,5 % des `return_rel`. Aucune des 69 relations ne
conserve le signe moyen 2024 ; la médiane de rétention absolue est 56,0 % et les
signes sont désalignés sur les deux dates. L’IC moyen passe de -0,1012 à +0,0545
pour ces 69 relations. Ce résultat est compatible avec l’instabilité déjà
constatée en 2025, mais deux cutoffs ne permettent pas de conclure sur la
période 2026.

### Conclusion

Le top 100 général est essentiellement un classement de prévision du risque
(volatilité/drawdown), et son sens reste remarquablement stable en 2025 ; en
2026, les horizons H60 restent cohérents sur davantage de dates, tandis que
H120 reste trop peu mûr pour une conclusion. Le top 100 performance ne montre
pas de stabilité de signe : il bascule dès 2025 et confirme ce basculement sur
les deux dates H120 exploitables en 2026. Il ne faut donc pas présenter ces
résultats comme un signal de rendement exploitable ni comme une preuve
statistique indépendante : les fenêtres sont courtes, les signaux corrélés et
les cibles H120 chevauchantes.

Les fichiers détaillés `signal_stability_*.csv` et `signal_ic_*.csv`, ainsi que
les JSON de synthèse, sont produits sous `data/analysis/spec006-period-comparison/`
et restent locaux/ignorés par Git.

## Reproduction

Les identifiants et métriques des deux tops figés sont enregistrés localement
dans `data/analysis/spec006-weekly-demo/top100_baseline_2024_equity.csv` et
`data/analysis/spec006-weekly-demo/top100_performance_equity_2024.csv`. Les
artefacts Parquet sont ignorés par Git. L’évaluateur est
`scripts/compare_signal_stability.py`. Les 4 comparaisons se rejouent avec les
commandes suivantes depuis la racine du dépôt :

```bash
uv run python scripts/compare_signal_stability.py \
  --baseline data/analysis/spec006-weekly-demo/top100_baseline_2024_equity.csv \
  --feature-cube data/feature_cube/spec006-2025-matched \
  --target-set data/targets/spec006-2025-matched \
  --output data/analysis/spec006-period-comparison --label equity_top100_2025

uv run python scripts/compare_signal_stability.py \
  --baseline data/analysis/spec006-weekly-demo/top100_performance_equity_2024.csv \
  --feature-cube data/feature_cube/spec006-2025-matched \
  --target-set data/targets/spec006-2025-matched \
  --output data/analysis/spec006-period-comparison --label performance_top100_2025

uv run python scripts/compare_signal_stability.py \
  --baseline data/analysis/spec006-weekly-demo/top100_baseline_2024_equity.csv \
  --feature-cube data/feature_cube/spec006-2026-matched \
  --target-set data/targets/spec006-2026-matched \
  --output data/analysis/spec006-period-comparison --label equity_top100_2026

uv run python scripts/compare_signal_stability.py \
  --baseline data/analysis/spec006-weekly-demo/top100_performance_equity_2024.csv \
  --feature-cube data/feature_cube/spec006-2026-matched \
  --target-set data/targets/spec006-2026-matched \
  --output data/analysis/spec006-period-comparison --label performance_top100_2026
```
