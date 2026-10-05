# SPEC-006R — audit de bout en bout des inversions rendement/direction

**Périmètre :** actions françaises du corpus ABC Bourse, cutoffs hebdomadaires du
5 avril au 4 octobre 2024 et du 6 avril au 4 octobre 2025, targets rendement et
direction. Les deux périodes contiennent 27 cutoffs.

**Verdict :** le résultat « 479 inversions sur 500 » ne peut pas être interprété
comme 479 signaux économiques qui changent de régime. La formule du rendement,
la jointure `entity_id + as_of_date` et le calcul de Spearman sont justes sur les
contrôles indépendants. En revanche, la chaîne de recherche comporte plusieurs
défauts confirmés : données de prix non certifiées et sans corporate actions,
univers reconstruit depuis une livraison 2026, filtrage des targets en fonction
du futur, fenêtres H120 presque entièrement superposées, inférence supposant à
tort 27 observations indépendantes, puis comptage multiple de relations
équivalentes. Ces défauts invalident les p-values, q-values et l'interprétation
du top 500.

L'inversion spectaculaire est surtout un artefact de présentation et de
sélection. Sur les 500 lignes choisies en 2024, l'IC médian absolu tombe de
`0,1647` en 2024 à `0,0636` en 2025. Seules 39 lignes conservent un
`|IC| >= 0,10` en 2025, contre 466 en découverte. La médiane du rapport
`|IC 2025| / |IC 2024|` est `0,378`. La plupart des « inversions » sont donc un
fort signal sélectionné en 2024 qui revient vers zéro et le traverse légèrement,
pas un signal opposé de force comparable.

## 1. Constitution de la base

### 1.1 Source et import

La matière première est une livraison manuelle ABC Bourse récupérée le
29 septembre 2026. Pour le SRD :

- 199 416 lignes distinctes ;
- 197 instruments et 197 ISIN ;
- historique du 29 septembre 2022 au 28 septembre 2026 ;
- aucune valeur `adjusted_close` disponible ;
- toutes les lignes portent le même instant de récupération du 29 septembre
  2026.

Les couches raw, bronze, silver et DuckDB préservent la provenance. L'historique
DuckDB contient 321 958 lignes de captures : 61 271 couples
`instrument_id/session_date` sont présents trois fois. Le choix de la dernière
capture ramène correctement le jeu à 199 416 lignes et aucune divergence OHLCV
n'a été trouvée entre ces copies. La déduplication n'est donc pas la cause de
l'inversion.

### 1.2 Convention point-in-time

La disponibilité historique n'a pas été observée à l'époque. Elle est
reconstruite par convention à `session_date + 1 jour, 00:00 Europe/Paris`.
Une barre téléchargée en septembre 2026 peut ainsi être utilisée dans un cutoff
2024. Les manifests déclarent correctement `pit_grade=reconstructed` et
`strict_pit_claimed=false`.

Cette convention évite un look-ahead explicite par date de séance, mais elle ne
reconstitue ni les vintages, ni les corrections historiques, ni le moment où un
titre entrait réellement dans l'univers. Le fichier SRD livré en 2026 ne fournit
pas un SBF 120 point-in-time : il projette dans le passé une liste de codes
disponible lors de la livraison.

### 1.3 Prix et corporate actions

Le moteur utilise `close`, pas une série ajustée accompagnée de son historique
d'ajustements. La documentation ABC indique que certains historiques peuvent
être réajustés lors de divisions nominales, mais la livraison ne contient aucun
registre de corporate actions permettant de prouver ou de reproduire ces
ajustements à chaque cutoff.

Le corpus actions contient notamment :

| Année | Mouvements close/close d'au moins 30 % | Titres touchés | Plus grand mouvement absolu |
| --- | ---: | ---: | ---: |
| 2022 | 4 | 4 | 37,4 % |
| 2023 | 21 | 11 | 157,8 % |
| 2024 | 27 | 11 | 8 444,9 % |
| 2025 | 32 | 18 | 510,1 % |
| 2026 | 24 | 14 | 80,4 % |

Exemples observés : `FR001400X2S4` passe de 49 à 4 187 le 12 novembre 2024,
`FR001400SU99` de 12 000 à 123,6 le 29 octobre 2024, puis
`FR001400X2S4` de 1 778 à 26 le 6 décembre 2024. Trois violations OHLC sont
également présentes en 2025.

Le rapport SPEC-003R concluait déjà que le snapshot n'était **pas prêt à
alimenter SPEC-004 directement** tant que ces événements n'étaient pas résolus
ou mis en quarantaine avec un contrat de données. La recherche a néanmoins été
construite sur cette base. C'est le premier défaut de gouvernance confirmé.

### 1.4 Population effectivement étudiée

Le filtre de qualité est cumulatif : dès qu'un titre a connu dans son passé un
mouvement journalier d'au moins 30 %, toute sa série passe en `review` et il est
absent des cutoffs suivants.

| Période | Actions par cutoff | Union | Présentes à tous les cutoffs |
| --- | ---: | ---: | ---: |
| 2024 | 180–183 | 184 | 178 |
| 2025 | 167–173 | 173 | 167 |

Il reste 165 actions présentes à chacun des 54 cutoffs des deux périodes. Le
recalcul sur ces 165 actions donne encore 476 inversions sur 500, soit 95,2 %.
Le changement de composition n'est donc pas la cause principale du résultat,
même si l'univers reste impropre à une affirmation historique SBF 120.

## 2. Fabrication des features

### 2.1 Coupe temporelle

Pour un cutoff D, le moteur charge les observations dont
`session_date <= D` et `available_at <= D+1 00:00 Europe/Paris`, choisit la
dernière capture de chaque barre, applique la qualité connue à D, puis calcule
les features uniquement avec l'historique ainsi obtenu.

Les cutoffs hebdomadaires sont dérivés de toutes les familles de marché
présentes dans DuckDB, crypto comprise. En 2025 ils tombent souvent le dimanche ;
le dernier close d'une action est alors celui du vendredi. Cela ne crée pas
l'inversion de signe, mais ce calendrier global ne doit pas servir de calendrier
de séance Euronext.

### 2.2 Formules

Le registre contient 1 048 features : statistiques de niveaux normalisées,
tendances, distributions de rendements, relations OHLC, volume et indicateurs
techniques, sur des fenêtres de 3 à 504 observations. Les fenêtres utilisent les
dernières observations valides disponibles, sans interpolation.

Trois exemples qui dominent la sélection 2024 :

- `ohlc.relation.candle_body.w252.v1` : moyenne sur 252 observations de
  `100 * abs(close-open) / previous_close` ;
- `close.return.std.w252.v1` : écart-type des rendements simples sur 252
  observations ;
- `close.log_return.q25.w252.v1` : premier quartile des log-rendements sur 252
  observations.

Les deux premières sont essentiellement des mesures de volatilité/range. La
troisième mesure la sévérité des mauvais jours. Il n'y a donc pas 500 idées
économiques différentes dans le résultat.

### 2.3 Ce que contient réellement le top 500

Le top 500 compte 137 feature IDs seulement : 71 de rendement, 41 OHLC, 19 de
distribution et 6 techniques. Les fenêtres 252 et 120 représentent à elles
seules 277 lignes. Une comparaison exacte des rangs cross-sectionnels 2024
réduit encore ces 137 IDs à 98 signatures de rang distinctes ; 73 features
appartiennent à un groupe de doublons exacts.

La sélection est aussi presque entièrement H120 : 484 lignes sur 500. Pour 133
features H120, `return_abs`, `return_rel` et `rank_pct` ont le même Spearman :

- soustraire le même rendement de benchmark à toutes les actions ne change pas
  leur rang ;
- convertir le rendement absolu en percentile est une transformation monotone.

Ainsi, 137 associations feature/horizon sont comptées trois fois. Parmi elles,
130 changent de signe, ce qui représente déjà 390 des 479 « inversions ».

### 2.4 Timing d'exécution

Une feature datée D inclut le close D et le target démarre à ce même close.
Le calcul est arithmétiquement cohérent, mais il suppose implicitement que la
stratégie peut être exécutée au close qui vient de servir au calcul. Pour une
simulation négociable, la décision doit être décalée vers la prochaine
observation exécutable, par exemple le prochain open ou close selon le contrat.

## 3. Méthodologie rendement/direction

### 3.1 Construction des targets

Pour chaque action et horizon H :

```text
return_abs(T,H) = close(T+H) / close(T) - 1
return_rel(T,H) = return_abs(action) - return_abs(benchmark)
direction_abs   = sign(return_abs)
direction_rel   = sign(return_rel)
rank_pct        = percentile cross-sectionnel de return_abs
```

Les observations futures commencent strictement après T. Vingt lignes H120 ont
été recalculées directement depuis `market_daily_history` : erreur maximale
`0`. Le Spearman a été recalculé avec SciPy sur 1 080 couples
relation/cutoff : écart maximal avec le pipeline `1,11 × 10^-16`. Aucune
inversion triviale de formule, de colonne ou de jointure n'a été trouvée.

### 3.2 Défaut du filtre futur

Après avoir calculé le rendement, `_future_outcomes` concatène l'historique à T
et les H observations futures, réexécute `assess_series`, puis classe la target
`future_quality_review` ou `future_quality_quarantined` si un événement apparaît
après T. `targets_research_ready` retire ensuite cette ligne.

La présence d'une action dans le calcul à T dépend donc de ce qui lui arrive
après T. C'est un filtrage ex post et une fuite de sélection directe. Le
`rank_pct` est lui aussi calculé uniquement sur la cohorte déclarée `available`
après ce contrôle futur.

Sur H120 :

| Période | Disponibles | Review futur | Quarantaine future | Part exclue |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 4 796 | 122 | 0 | 2,48 % |
| 2025 | 4 445 | 127 | 17 | 3,14 % |

Ces lignes ne sont pas manquantes au hasard. En 2024, les lignes `review` ont
un rendement moyen de +107,4 %, une médiane de -38,3 % et un maximum de
+13 540,8 %. En 2025, leur moyenne est +234,9 % et leur médiane +100,3 %.

Ce défaut doit être corrigé, mais il n'explique pas l'inversion observée : en
réinjectant les `candidate_value` de toutes les lignes review/quarantaine, le
taux d'inversion passe de 95,8 % à 97,0 %. Il s'agit donc d'un défaut réel dont
l'effet net sur ce diagnostic précis est secondaire.

### 3.3 Calcul des IC et fausse taille d'échantillon

À chaque cutoff, le pipeline calcule le Spearman cross-sectionnel entre feature
et target. Il moyenne ensuite les 27 IC hebdomadaires, calcule :

```text
t = mean(IC) / (std(IC) / sqrt(27))
```

puis applique Benjamini-Hochberg aux p-values. Ce calcul suppose que les 27 IC
sont des observations temporelles indépendantes.

Cette hypothèse est fausse pour H120. Deux cutoffs espacés d'une semaine
partagent environ 115 séances futures sur 120, soit 95,8 % de leur target. Une
sélection gloutonne de fenêtres non superposées ne conserve que deux fenêtres
H120 par période :

- 2024 : 5 avril–23 septembre, puis 27 septembre–19 mars 2025 ;
- 2025 : 6 avril–24 septembre, puis 28 septembre–18 mars 2026.

L'autocorrélation de premier ordre médiane des IC est `0,748` en 2024 et
`0,835` en 2025. Malgré cela, les q-values du top 500 vont de
`1,43 × 10^-14` à `3,21 × 10^-8`. Elles ne mesurent pas la significativité
effective de ces relations et ne doivent pas être utilisées pour les classer.

### 3.4 Sélection puis validation

Le top 500 est choisi sur 2024 par q-value, puis par `|IC|`. Cette procédure
sélectionne les réalisations les plus extrêmes parmi des milliers de relations
très corrélées. Le résultat 2025 est ensuite résumé par le seul maintien du
signe.

Les chiffres complets sont :

| Calcul | Relations | Inversions | IC moyen 2024 → 2025 | Médiane 2024 → 2025 |
| --- | ---: | ---: | ---: | ---: |
| Pipeline actuel | 500 | 479 (95,8 %) | -0,1019 → +0,0496 | -0,1564 → +0,0633 |
| Targets candidates, sans exclusion future | 500 | 485 (97,0 %) | -0,0961 → +0,0542 | -0,1488 → +0,0706 |
| Univers commun de 165 actions | 500 | 476 (95,2 %) | -0,0869 → +0,0464 | -0,1316 → +0,0587 |
| Univers commun + candidates | 500 | 473 (94,6 %) | -0,0869 → +0,0450 | -0,1316 → +0,0552 |

La population entière des relations communes change de signe à 60,2 %, contre
95,8 % après sélection du top 2024. Un placebo sélectionné en 2025 puis relu en
2024 ne change de signe que dans 34,2 % des cas. Le chiffre 479 provient donc de
la combinaison asymétrique suivante : épisode de découverte 2024, sélection des
extrêmes négatifs, forte dépendance entre relations, puis comptage de tout
passage au-dessus de zéro comme une inversion.

### 3.5 Trois exemples lisibles

Les valeurs ci-dessous utilisent `future.return_abs.h120.v1` et le pipeline
actuel. Le spread est le rendement moyen du décile de feature le plus élevé
moins celui du décile le plus faible, moyenné sur les cutoffs.

| Feature | IC 2024 | Spread 2024 | IC 2025 | Spread 2025 |
| --- | ---: | ---: | ---: | ---: |
| Candle body 252 | -0,224 | -5,98 % | +0,039 | +9,87 % |
| Écart-type rendement 252 | -0,228 | -6,97 % | +0,044 | +5,44 % |
| Q25 log-rendement 252 | +0,229 | +8,25 % | +0,017 | -6,18 % |

En 2024, le rendement H120 moyen de tout l'échantillon est -2,78 % et 41,5 %
des observations sont positives. En 2025, la moyenne est +3,94 % et 51,1 % sont
positives. Les deux premières lignes décrivent essentiellement le même facteur
de volatilité : très visible pendant l'épisode 2024, puis proche de zéro en
2025. Le signe seul masque cette perte de force.

## 4. Localisation du problème

### Défauts confirmés qui invalident la conclusion de recherche

1. **Inférence temporelle incorrecte.** Vingt-sept fenêtres H120 superposées
   sont traitées comme 27 répétitions indépendantes alors qu'il n'existe que
   deux fenêtres non chevauchantes. Les p-values et q-values sont invalides.
2. **Multiplicité fictive.** Les mêmes rangs de features et les mêmes rangs de
   targets sont comptés plusieurs fois. Le top 500 représente au plus 98
   signatures de rang exactes dans cet échantillon, avant même de regrouper les
   corrélations proches.
3. **Sélection sur l'extrême.** Le classement 2024 retient surtout un facteur de
   volatilité qui a connu un IC négatif exceptionnel pendant un seul épisode.
   Son passage faible au-dessus de zéro en 2025 est compté comme une inversion
   complète.
4. **Prix non certifiés.** La recherche utilise des closes sans registre de
   corporate actions, malgré des ruptures de facteur 10 à 100 et un gate
   SPEC-003R explicitement non satisfait.
5. **Filtrage conditionné par le futur.** Une trajectoire future détermine si sa
   target entre dans l'échantillon. Ce mécanisme viole le contrat de sélection,
   même si le test de sensibilité montre qu'il ne produit pas à lui seul les 479
   inversions.
6. **Univers et PIT reconstruits.** Le corpus 2026 et les disponibilités
   synthétiques sont projetés dans le passé. Ils ne décrivent pas l'univers
   investissable historique.
7. **Timing non négociable.** La décision et le prix initial utilisent le même
   close D sans délai d'exécution.

### Hypothèses écartées comme cause principale

- pas d'inversion de signe dans `P(T+H)/P(T)-1` ;
- pas de décalage visible de `entity_id` ou `as_of_date` ;
- pas de conflit entre captures dupliquées ;
- pas d'explication par le seul changement d'univers ;
- pas d'explication par le seul retrait des targets `future_quality_*` ;
- pas de changement de code feature/target entre les builds 2024 et 2025 qui
  puisse expliquer le signe.

## 5. Décision de recherche

Les résultats rendement/direction actuels doivent être marqués **invalides pour
inférence et sélection de signaux**. Ils restent utiles comme diagnostic de
pipeline et comme description de deux épisodes réalisés.

La reconstruction correcte doit suivre cet ordre :

1. résoudre les corporate actions et anomalies de prix, puis produire une série
   de rendement auditable ;
2. définir un univers d'éligibilité daté à chaque cutoff ;
3. utiliser un calendrier Euronext et une règle d'exécution à T+1 ;
4. conserver toute target calculable, avec les événements futurs en annotations
   plutôt qu'en filtre d'admission ;
5. réduire les features à des familles/signatures indépendantes avant toute
   correction multiple ;
6. utiliser des fenêtres non chevauchantes pour le test principal, ou une
   inférence HAC/bootstrap par blocs adaptée à H ;
7. séparer découverte, choix méthodologique et validation finale sans réutiliser
   la période de validation ;
8. rapporter IC, intervalle d'incertitude, magnitude retenue et courbe par
   cutoff, pas seulement le signe.

## Reproduction

Les contrôles arithmétiques et comparaisons de population sont produits par :

```bash
uv run python scripts/audit_spec006r_reversals.py
uv run python scripts/compare_spec006r_reversals.py
uv run python scripts/audit_spec006r_root_causes.py
```

Les sorties locales sont écrites sous
`data/analysis/spec006r-reversal-audit/` et
`data/analysis/spec006r-root-cause-audit/`. Ces données restent ignorées par
Git.
