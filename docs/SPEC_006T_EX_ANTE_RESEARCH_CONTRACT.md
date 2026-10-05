# SPEC-006T — Éligibilité ex ante et candidate lock H5

**5 octobre 2026 · version 1 · target unique : `future.direction_abs.h5.v1` · scope `equity`**

**Statut : candidate lock ready for independent confirmation.** Le protocole et les candidats sont
figés ; les résultats de confirmation sont absents. Ce statut technique ne certifie ni un alpha,
ni les vintages de prix, ni un univers SRD historiquement complet.

## 1. Correction apportée

La cohorte à T est définie avant de consulter le futur. La qualité future devient une annotation
distincte. Une review ultérieure ne retire plus une target calculable du calcul ex ante.

La décision figée conserve toutes les entités observées à T, y compris les entités non admissibles
et leurs motifs. Le minimum d'historique propre à chaque feature est appliqué par son statut de
disponibilité à T. Le futur ne modifie ni ce statut ni `eligible_at_cutoff`.

La correction est publiée dans un nouveau dossier. Les artefacts des expériences précédentes
restent inchangés et servent à reproduire les anciens chiffres.

| Objet | Information admise | Rôle |
|---|---|---|
| `EligibilityAtCutoff` / ledger | Prix et qualité disponibles au cutoff ; univers et historique passés | Décision figée d'appartenance à la cohorte à T |
| Disponibilité d'une feature | Historique passé nécessaire à sa formule | Condition de calcul du couple feature/target, connue à T |
| Future outcome | Fenêtre après T | Candidate calculée et annotations ; aucune révision de l'éligibilité |
| Échantillon numérique | Cohorte figée, feature disponible, résultat observable et interprétable | Ensemble effectivement utilisé pour l'IC, avec ses exclusions comptées |

Le ledger et l'échantillon numérique ne sont pas identiques. Un résultat censuré ou
ininterprétable n'a pas d'IC numérique, mais son entité reste dans la cohorte initiale.

## 2. Champs et politiques

| Champ | Définition V1 |
|---|---|
| `eligible_at_cutoff` | Qualité approved à T, série/historique présents et entité dans le périmètre de features à T |
| `eligibility_reason` | Motif passé de la décision : approved, qualité passée non approved ou absence d'historique de features |
| `target_observable` | `candidate_value` finie et calculable avec les observations futures requises |
| `future_quality_status` | clean, review, quarantined, suspected_corporate_action, scale_change, source_issue, ou état d'indisponibilité |
| `target_interpretable` | Observable et sans violation forte de qualité source selon la politique V1 |
| `interpretability_reason` | Motif explicite de l'ininterprétabilité ; ne change pas l'éligibilité |
| `candidate_value` | Calcul brut conservé, même si le résultat devient ininterprétable |
| `target_value` | Valeur utilisable ex ante ; review conservée, erreur forte null |
| `legacy_target_value`, `research_ready` | Compatibilité et reproduction de la politique précédente ; exclus du rôle de filtre unique |

La candidate direction H5 est recalculée depuis les prix de début/fin stockés, puis comparée
à la candidate originale. Il n'y a aucune modification de la formule ou du signe du target.

### Deux vues explicites

- **`targets_ex_ante`** : toutes les targets observables de la cohorte figée. Les résultats
  ininterprétables y restent visibles, avec `candidate_value` conservée et `target_value=null`.
- **`targets_clean_future`** : sous-vue observable/interprétable dont le futur est clean.

Ces vues V1 sont limitées à **direction absolue H5 / equity**. Les autres horizons/familles
conservent leur historique de compatibilité ; les cohortes de `rank_pct`, notamment, ne sont
pas présentées comme des rankings ex ante réparés dans cette SPEC.

Pour le calcul d'IC, `select_targets(..., "ex_ante")` exige en plus
`target_interpretable=true`. La politique `clean_future` impose aussi le statut clean.
La politique `legacy_research_ready` reproduit le filtre précédent.

### Erreurs fortes et corporate actions

Une violation forte OHLC, ou un flag explicite `confirmed_source_error`, rend le résultat
ininterprétable selon V1. Les reviews et les corporate actions seulement suspectées restent
calculables et annotées. La politique clean permet d'en mesurer la sensibilité.

Cela ne transforme pas un mouvement suspect en événement confirmé. Les flags, raisons,
prix de début/fin, run IDs et checksums des fichiers sources sont conservés. Une correction
de prix devra être documentée séparément, avec sa provenance.

Deux résultats H5 de 2025 sont ininterprétables pour incohérence OHLC :

| Cutoff | Identifiant source | Candidate direction |
|---|---|---:|
| 25/05/2025 | `FR0011466069` | −1 |
| 01/06/2025 | `US2220702037` | −1 |

Les deux entités restent `eligible_at_cutoff=true`. Ces violations de règle ne constituent pas
à elles seules une confirmation humaine de la cause de l'erreur.

## 3. Cohortes réelles

Les nombres additionnent des lignes **entité/cutoff** ; ils ne sont pas des effectifs indépendants.

| Période | Cutoffs | Titres uniques éligibles | Éligibles à T | Observables | IC ex ante | Future clean | Ininterprétables |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024, 05/04–04/10 | 27 | 184 | 4 918 | 4 918 | 4 918 | 4 914 | 0 |
| 2025, 06/04–04/10 | 27 | 173 | 4 589 | 4 589 | 4 587 | 4 583 | 2 |
| 2026, 05/04–28/09 | 27 | 162 | 4 304 | 3 988 | 3 988 | 3 984 | 0 |

Les IC H5 2026 utilisent **25 dates jusqu'au 18 septembre**. Les deux derniers cutoffs
conservent 316 lignes éligibles au total, mais leurs targets ne sont pas mûres. La cohorte par
cutoff compte 180–183 titres en 2024, 167–173 en 2025 et 158–162 en 2026.

## 4. Reproduction et sensibilité exacte

La politique legacy reproduit les IC moyens des **815 relations** précédemment publiées,
dans chacune des trois années : erreur maximale **2,78×10⁻¹⁷** en 2024/2025 et **0** en 2026.
Le nouveau calcul vectorisé est également comparé à SciPy dans les tests.

### Même ancien top 500, sans nouvelle sélection

| Période | IC signé moyen legacy / clean | IC signé moyen ex ante | Delta signé | Médiane abs IC ex ante |
|---|---:|---:|---:|---:|
| 2024 | −0,01656899 | −0,01628844 | +0,00028055 | 0,02769590 |
| 2025 | +0,01125199 | +0,01190439 | +0,00065240 | 0,02329630 |
| 2026 partiel | +0,00847806 | +0,00836801 | −0,00011005 | 0,02268512 |

| Comparaison, mêmes 500 relations | Inversions legacy | Inversions ex ante |
|---|---:|---:|
| 2024 → 2025 | 330 ; 66 % | 329 ; 65,8 % |
| 2024 → 2026 | 321 ; 64,2 % | 320 ; 64 % |
| 2025 → 2026 | 91 ; 18,2 % | 91 ; 18,2 % |

Sur les features mesurées dans chaque période, la moyenne des **deltas absolus par relation**
est 0,001180 en 2024, 0,001083 en 2025 et 0,000301 en 2026. Les maxima sont 0,008751,
0,002497 et 0,001380. Respectivement 25, 2 et 1 signes moyens changent entre legacy et ex ante
dans cette population mesurée, qui est plus large que l'ancien top 500.

Dans ce corpus H5, clean et legacy donnent les mêmes IC à l'arrondi numérique près.
Leur équivalence ici n'est pas une règle générale de contrat.

**Conclusion de sensibilité :** le défaut méthodologique était réel. Sa correction a un effet
faible sur les IC H5 agrégés de l'ancien top 500 et ne fournit pas l'explication principale de
son instabilité 2024 vs 2025–2026. Quelques associations proches de zéro changent de signe.

## 5. Déduplication exacte des rangs

Le grouping utilise uniquement les features de discovery 2024, dans la cohorte passée.
Pour chaque date, il trie les entités, calcule les rangs moyens, et encode leur double entier
pour éviter tout arrondi. La signature contient dates, identifiants d'entité et masque de
disponibilité. Les dates sont triées explicitement ; l'ordre des lignes d'entrée ne change
pas la signature.

Une transformation ne devient alias que si **tous ces rangs sont exactement identiques**.
Un simple-return/log-return proche n'est pas automatiquement fusionné. Les inversions
monotones de rang demeurent des groupes différents. Une égalité constatée en discovery
ne garantit pas une égalité dans une nouvelle période : la feature canonique seule est figée.

- **1 042 features** ont au moins une valeur discovery dans ce périmètre.
- **937 signatures exactes** ; **105 identifiants redondants regroupés**.
- **838 features canoniques** passent ensuite les seuils de discovery.
- Canonique : identifiant lexicalement minimal ; aliases et taille de groupe conservés.

Les 937 groupes incluent des historiques trop courts pour l'admissibilité ; ils ne représentent
pas 937 candidats de confirmation. La redondance économique approximative reste possible.

## 6. Candidate lock V1

Le classement est refait sur les features canoniques corrigées : amplitude de l'IC 2024
décroissante, puis identifiant. La q-value naïve précédente n'est plus utilisée pour le nouveau
classement. Il n'y a aucun score combiné opaque et aucune réutilisation directe des listes
133 ou 78 de l'expérience précédente.

La discovery demande 1 000 couples, 13 cutoffs et 60 % de couverture. Le calcul de chaque IC
demande au moins 30 couples. Les deux années de développement doivent chacune fournir
au moins 1 000 couples et 13 cutoffs. Une amplitude minimale **0,01 dans chaque année** est
fixée dans la configuration, sans recherche du meilleur seuil.

Le bootstrap conserve la méthode précédente : 10 000 réplications, blocs circulaires de
2/4/6 cutoffs, seed 20261005, tirages communs aux features dans une année et indépendants
entre années. Les critères doivent passer pour **les trois blocs**. Une série d'IC incomplète
ne reçoit pas silencieusement de valeurs imputées : ses flags de soutien ne passent pas.

| Cohorte imbriquée | Critères additionnels | Effectif |
|---|---|---:|
| `broad_candidates` | Même signe 2025/2026, amplitude et effectifs minimaux, signature unique | **504** |
| `strong_sign_candidates` | Broad + soutien annuel >90 % dans les deux années + conjoint >90 %, tous blocs | **138** |
| `strict_candidates` | Strong + deux intervalles bilatéraux 90 % entièrement du même côté de zéro, tous blocs | **85** |

Le lock contient les 504 candidats et leurs flags strong/strict. Le sens prévu est figé dans
`locked_direction`, issu du signe moyen 2025, également conservé en 2026 par définition.
Les tiers sont imbriqués ; leurs effectifs ne s'additionnent pas.

Les 504/138/85 relations gardent toutes le signe entre 2025 et 2026 **par leur règle de
sélection**. Ce 100 % ne mesure pas une validation indépendante. Sur les 838 relations
canoniques admissibles avant shortlist, **172/838**, soit **20,53 %**, inversent leur signe.

| Cohorte ex ante | Médiane abs IC 2025 | Médiane abs IC 2026 | Rétention médiane d'amplitude 2025 → 2026 |
|---|---:|---:|---:|
| Broad | 0,02548 | 0,03194 | 1,211 |
| Strong | 0,03419 | 0,04498 | 1,339 |
| Strict | 0,03585 | 0,04573 | 1,331 |

Les intervalles sont individuels, sans correction multiple ou post-sélection. Les données 2025
et 2026 ont contribué à la shortlist et deviennent explicitement des périodes de développement.

### Gel et confirmation

Le [lock versionné](../configs/research/candidate_lock_v1.json) contient les features,
aliases, signatures, orientations, tiers, mesures, seuils, registre et empreintes des entrées
et de l'implémentation. Son écriture est déterministe ; une tentative de remplacement par un
document différent échoue. Un changement requiert une nouvelle version explicitement revue.

La confirmation préparée démarre après les données consultées et les fins de targets de
développement. La requête préparée porte un premier cutoff au **06/10/2026**, avec résultats
null et `retuning_allowed=false`. Ce choix ne prétend pas que ces nouvelles données existent.
Une autre date future peut être préparée avec le même lock et le même registre.

La période consultée est bornée au 28/09/2026. Le registre doit correspondre exactement au
fingerprint du lock. Aucun H120, autre target ou nouveau paramétrage n'entre dans V1.

## 7. Contexte de marché descriptif

Les états utilisent seulement le passé au cutoff, avec disponibilité reconstruite :

- marché up/down : signe du rendement CAC AllShares sur 20 observations passées ;
- volatilité globale : écart-type de 20 log-rendements, annualisé √252 ;
- dispersion : écart-type cross-sectionnel des rendements passés à 20 observations ;
- breadth : fraction de ces rendements strictement positifs ;
- trend large market : close CAC AllShares / moyenne passée 60 observations − 1.

Il n'y a aucun découpage optimisé ni utilisation de ces états dans le classement ou les tiers.

| Période | Retour marché passé 20 obs, moyen | Volatilité moyenne | Dispersion moyenne | Breadth moyenne | Cutoffs up/down |
|---|---:|---:|---:|---:|---|
| 2024 | −1,31 % | 13,74 % | 8,83 % | 47,89 % | 9 / 18 |
| 2025 | −0,62 % | 16,01 % | 9,07 % | 50,48 % | 12 / 15 |
| 2026 partiel | +0,01 % | 14,52 % | 8,09 % | 48,56 % | 13 / 14 |

Ces moyennes de retours passés ne sont pas des performances annuelles. Le contexte de 2024
compte davantage de cutoffs baissiers ; la volatilité moyenne est plus élevée en 2025.

Sur les 138 strong candidates, avec orientation figée issue de 2025 :

| Année | IC moyen orienté, état up | IC moyen orienté, état down | Cutoffs d'IC up/down |
|---|---:|---:|---|
| 2024 | −0,00379 | +0,00447 | 9 / 18 |
| 2025 | +0,02619 | +0,04104 | 12 / 15 |
| 2026 partiel | +0,05798 | +0,03029 | 13 / 12 |

L'association agrégée reste positive dans les deux états en 2025 et en 2026. Son amplitude
par état change et le sens était proche de zéro en 2024. La simple distinction haussier/baissier
n'explique donc pas à elle seule la différence annuelle. Ces mesures post-sélection sont
descriptives, avec faibles effectifs temporels et variables encore corrélées.

## 8. Sandbox et artefacts

[Ouvrir le laboratoire SRD](https://sandbox.hocus.works/quant-lab-srd/?v=spec006t), sous authentification.

Les sections ajoutées sont **Research Contract**, **Candidate Explorer** et **Signal Detail**.
Le toggle ex ante / future clean relit des tableaux précalculés. Il ne recalcule aucun scan,
bootstrap ou lock. Les IC changent selon la politique ; les tiers et intervalles demeurent
ceux du lock ex ante, explicitement signalés.

Le service conserve son compte dédié et ses montages en lecture seule. Le répertoire `src/`
est ajouté aux montages de lecture pour accéder au chargeur typé de ces artefacts.

Résultats locaux, hors Git : `data/analysis/spec006t-ex-ante/`.

| Fichier | Contenu |
|---|---|
| `eligibility_at_cutoff.parquet` | Ledger passé, y compris entités non admissibles |
| `targets.parquet` | Toutes les outcomes H5 de la cohorte passée, avec flags séparés |
| `targets_ex_ante.parquet`, `targets_clean_future.parquet` | Projections comparables ; première conserve aussi les lignes ininterprétables |
| `ic_history.parquet`, `ic_summary.parquet` | IC par cutoff et agrégats pour les trois politiques |
| `ex_ante_filter_sensitivity.parquet` | IC legacy/ex ante/clean et deltas par feature/période |
| `rank_signature_groups.parquet` | Canoniques, aliases, signatures et effectifs |
| `bootstrap_intervals.parquet` | Soutiens et intervalles 90/95 % par taille de bloc |
| `candidate_explorer.parquet` | Tous les groupes admissibles, flags et tiers |
| `candidate_lock_v1.json`, `candidate_lock_v1.parquet` | Shortlist immuable et projection analytique |
| `period_metrics.parquet`, `period_stability.parquet` | Anciennes cohortes et cohortes corrigées comparées séparément |
| `market_regimes.parquet`, `regime_ic_summary.parquet`, `regime_candidate_summary.parquet` | États connus à T et associations descriptives |
| `research_contract.duckdb` | Vues de recherche en lecture seule côté UI |
| `audit.json`, `audit.md`, `confirmation_request.json` | Provenance, résultats et confirmation en attente |

Le JSON du lock est versionné dans `configs/research/`. Les [audits Markdown](SPEC_006T_AUDIT.md)
et [JSON](SPEC_006T_AUDIT.json) exposent les statistiques et les checksums sans les prix source.

## 9. Reproduction

```bash
uv sync --all-extras
uv run python scripts/build_spec006t_research_contract.py

# Préparer une future confirmation, sans consulter de résultats ni sélectionner de nouveau
uv run python scripts/prepare_spec006t_confirmation.py \
  --first-cutoff 2027-01-04 \
  --output data/analysis/spec006t-ex-ante/confirmation_2027.json

uv run pytest
uv run ruff check .
uv run mypy src/
uv run marimo check notebooks/srd_research_lab.py
```

Le recalcul exige les trois cubes/targets locaux et les anciens rapports H5. Une modification
d'une source, d'un seuil, d'un registre ou d'un élément verrouillé n'écrase pas V1. Les essais
intermédiaires locaux avant gel final sont conservés dans des dossiers `preflight`, hors Git.

## 10. Tests et limites restantes

Les tests couvrent l'immuabilité de l'éligibilité malgré une anomalie future, les annotations,
les candidates review conservées, les erreurs fortes ininterprétables, les deux vues DuckDB,
les signatures et groupes déterministes, la concordance SciPy, le verrouillage et son refus
de retuning, l'exclusion H120, le registre de confirmation, et la lecture UI sans scan.
Le recalcul réel vérifie automatiquement la reproduction des 815 relations existantes.

Vérifications exécutées : **97 tests passent** (176,53 s), `ruff check .`, `mypy src/`
(34 modules) et `marimo check notebooks/srd_research_lab.py` passent. L'export HTML
Marimo a également terminé sans erreur. Le service répond HTTP 200 en local ; l'accès public
sans authentification répond 401. Un navigateur Chromium a vérifié les trois sections et
le basculement aller/retour des cohortes, sans erreur JavaScript.
Pour `low.level.range_pct.w60.v1`, le navigateur lit l'IC 2024 ex ante
−0,04140290, puis future-clean −0,04254092, puis retrouve la première valeur.
Un second recalcul complet produit exactement le même lock SHA-256 :
`7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f`.
La préparation d'une confirmation au 04/01/2027 retourne
`pending_new_unconsulted_data`, sans résultat.

Restent ouverts : corporate actions/vintages de prix, composition historique réelle du SRD,
calendrier commun et gaps, contrôle de multiplicité, faible nombre de dates de bootstrap,
redondance approximative et exécution future. Le target actuel commence au close T ; la
convention next_open est préparée pour une stratégie ultérieure, sans backtest dans cette SPEC.

**Décision : le candidate lock V1 est prêt pour organiser une confirmation indépendante.
Les candidats demeurent exploratoires ; aucune confirmation ni preuve d'alpha n'est acquise.**
