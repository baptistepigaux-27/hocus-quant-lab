# Grands marchés — modèles temporels par indice

**Développement rétrospectif, 6 octobre 2026.** [Contrat et formules](INDEX_SERIES_MODELS_CONTRACT.md).

140 artefacts de modèles/références, 120 fits finaux, 210 fits de validation. Cinq séries, trois targets, H5/H10 : 30 tâches. Chaque estimateur apprend sur **un seul indice**. 22 features de close, grille quotidienne CAC40, disponibilité source à minuit UTC D+1. Train 2024, validation S1 2025, retrain 2024+S1 2025, test S1 2026.

## Gagnants de validation — résultats test

Direction : sélection par log-loss ; régressions par RMSE. Une référence simple peut gagner. AUC et corrélation temporelle sont calculées **sur les dates de chaque indice**. Le skill compare la perte test au prior historique (direction), à zéro (rendement) ou à la volatilité historique H. Skill ≤0 : aucune amélioration avec ce critère. Rendements/volatilités sont en fractions.

| index_name | target | horizon | model | n | roc_auc | temporal_spearman | rmse | reference_rmse | skill | primary_lo90 | primary_hi90 | loss_advantage_lo90 | loss_advantage_hi90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cac 40 | direction | 5 | linear | 120 | 0.34188 | -0.27202 | — | — | -0.09183 | 0.24866 | 0.44986 | -0.12112 | -0.01439 |
| Cac 40 | direction | 10 | xgb | 115 | 0.42872 | -0.12296 | — | — | -0.02030 | 0.29378 | 0.55479 | -0.02722 | -0.00000 |
| DAX 40 | direction | 5 | xgb | 120 | 0.65574 | 0.27025 | — | — | -0.00623 | 0.54483 | 0.76772 | -0.03475 | 0.02485 |
| DAX 40 | direction | 10 | xgb | 115 | 0.59848 | 0.17081 | — | — | -0.02891 | 0.48973 | 0.70743 | -0.06371 | 0.01610 |
| FTSE 100 | direction | 5 | rf | 120 | 0.43322 | -0.11436 | — | — | -0.30008 | 0.27148 | 0.62558 | -0.35396 | -0.05878 |
| FTSE 100 | direction | 10 | rf | 115 | 0.52154 | 0.03699 | — | — | -0.15476 | 0.39188 | 0.75785 | -0.21410 | -0.00620 |
| S&P 500 | direction | 5 | naive | 120 | 0.50000 | — | — | — | 0.00000 | 0.50000 | 0.50000 | 0.00000 | 0.00000 |
| S&P 500 | direction | 10 | naive | 115 | 0.50000 | — | — | — | 0.00000 | 0.50000 | 0.50000 | 0.00000 | 0.00000 |
| SBF 120 | direction | 5 | linear | 120 | 0.35943 | -0.24227 | — | — | -0.07511 | 0.25254 | 0.47059 | -0.10634 | -0.00780 |
| SBF 120 | direction | 10 | xgb | 115 | 0.40619 | -0.16231 | — | — | -0.02306 | 0.27851 | 0.53715 | -0.03074 | -0.00194 |
| Cac 40 | return | 5 | linear | 120 | — | -0.18053 | 0.02285 | 0.02211 | -0.06835 | -0.43424 | 0.06762 | -0.00008 | 0.00001 |
| Cac 40 | return | 10 | linear | 115 | — | -0.20888 | 0.03298 | 0.03175 | -0.07890 | -0.52307 | 0.12963 | -0.00022 | 0.00009 |
| DAX 40 | return | 5 | xgb | 120 | — | — | 0.02332 | 0.02282 | -0.04409 | — | — | -0.00009 | 0.00004 |
| DAX 40 | return | 10 | rf | 115 | — | 0.23428 | 0.03770 | 0.03208 | -0.38081 | -0.05287 | 0.57326 | -0.00139 | 0.00036 |
| FTSE 100 | return | 5 | rf | 120 | — | -0.10895 | 0.02045 | 0.01819 | -0.26436 | -0.37196 | 0.22545 | -0.00019 | 0.00003 |
| FTSE 100 | return | 10 | rf | 115 | — | -0.06502 | 0.03088 | 0.02660 | -0.34787 | -0.38584 | 0.42303 | -0.00047 | -0.00002 |
| S&P 500 | return | 5 | zero | 120 | — | — | 0.01947 | 0.01947 | 0.00000 | — | — | 0.00000 | 0.00000 |
| S&P 500 | return | 10 | zero | 115 | — | — | 0.03017 | 0.03017 | 0.00000 | — | — | 0.00000 | 0.00000 |
| SBF 120 | return | 5 | linear | 120 | — | -0.15723 | 0.02230 | 0.02171 | -0.05520 | -0.43010 | 0.10486 | -0.00006 | 0.00001 |
| SBF 120 | return | 10 | linear | 115 | — | -0.17105 | 0.03196 | 0.03118 | -0.05025 | -0.53018 | 0.18351 | -0.00018 | 0.00012 |
| Cac 40 | volatility | 5 | xgb | 120 | — | 0.28409 | 0.07099 | 0.09012 | 0.37942 | -0.01986 | 0.48588 | 0.00115 | 0.00520 |
| Cac 40 | volatility | 10 | xgb | 115 | — | 0.07962 | 0.06270 | 0.07203 | 0.24229 | -0.37479 | 0.49893 | -0.00017 | 0.00284 |
| DAX 40 | volatility | 5 | historical_vol | 120 | — | 0.33647 | 0.10524 | 0.10524 | 0.00000 | 0.04696 | 0.48715 | 0.00000 | 0.00000 |
| DAX 40 | volatility | 10 | xgb | 115 | — | 0.44109 | 0.06767 | 0.08242 | 0.32587 | 0.00760 | 0.69444 | -0.00015 | 0.00495 |
| FTSE 100 | volatility | 5 | rf | 120 | — | 0.43592 | 0.06096 | 0.07401 | 0.32156 | 0.17097 | 0.57680 | 0.00032 | 0.00323 |
| FTSE 100 | volatility | 10 | rf | 115 | — | 0.59821 | 0.04680 | 0.05933 | 0.37772 | 0.27632 | 0.74268 | 0.00002 | 0.00269 |
| S&P 500 | volatility | 5 | linear | 120 | — | 0.36495 | 0.07292 | 0.07760 | 0.11708 | 0.08056 | 0.57407 | -0.00134 | 0.00282 |
| S&P 500 | volatility | 10 | linear | 115 | — | 0.27312 | 0.08047 | 0.06125 | -0.72608 | -0.19809 | 0.66972 | -0.00577 | -0.00020 |
| SBF 120 | volatility | 5 | rf | 120 | — | 0.31220 | 0.07246 | 0.08813 | 0.32388 | 0.01594 | 0.53349 | 0.00063 | 0.00450 |
| SBF 120 | volatility | 10 | xgb | 115 | — | 0.19227 | 0.06043 | 0.07254 | 0.30610 | -0.27538 | 0.56441 | 0.00013 | 0.00312 |

Intervalles individuels 90 %, bootstrap temporel de 5 000 réplications, blocs principaux 2×H ; variantes H et 4×H conservées. L'avantage de perte est perte référence − perte modèle, positif si meilleur. Une corrélation positive peut coexister avec une erreur plus grande. Les intervalles sont conditionnels aux modèles et aux données, sans correction multiple ni preuve d'alpha. Les fenêtres futures quotidiennes se chevauchent fortement.

## Données et contrôles

4835 rendements et volatilités futurs recalculés depuis les quotes natives ; contrôle de 50 préfixes historiques pour les features ; contrôle des timestamps et frontières de split. Aucun poids ou prétraitement partagé entre indices. Labels absents conservés, sans remplacement ni filtre selon le rendement futur. Les résultats précédents restent conservés.

## Artefacts et futur contexte SRD

`context_score_features.parquet` : 3525 scores sur 30 flux, seulement test 2026, sans résultat futur. OOF roulant et jointure as-of nécessaires pour une intégration historique au SRD. Grade reconstruit, confirmation indépendante et intégration SRD encore ouvertes.

Dossier local `data/analysis/index-series-models-v1/` : source figée, features, targets, audit, grilles, métriques par modèle, prédictions validation/test, modèles joblib, intervalles et scores. Onglet **Grands marchés** dans le [Model Lab](https://sandbox.hocus.works/quant-model-lab/).

Reproduction : `uv run python scripts/index_series_models.py prepare`, puis `run`, puis `publish`. Configuration `configs/experiments/index_series_v1.toml`.
