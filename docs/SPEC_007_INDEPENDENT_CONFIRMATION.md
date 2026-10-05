# SPEC-007 — Independent Confirmation Protocol

**5 octobre 2026 · protocole V1 · equity / `future.direction_abs.h5.v1`**

**SPEC-007 ready — awaiting independent data.** Aucun résultat de confirmation n'existe.
Le protocole ne recycle aucune observation de 2024/2025/2026 déjà consultée. Aucun modèle,
portefeuille, PnL, optimisation de poids ou sélection de survivants n'est ajouté.

## 1. Contrat figé

Base de développement : commit `af0af57ddacfc57515a807034f1bd3bfa0588454`, SPEC-006T.

- Candidate lock : `candidate_lock_v1`.
- Fingerprint du lock :
  `7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f`.
- **504 broad / 138 strong / 85 strict**, cohortes imbriquées, inchangées.
- **Strict constitue le test collectif principal** ; broad et strong donnent le contexte.
- Target unique : direction absolue H5, signe de `close(T+5)/close(T)-1`.
- Signe attendu : `locked_direction` du lock, fixé pendant le développement.

Le [TOML versionné](../configs/research/confirmation_protocol_v1.toml) définit les paramètres.
Le [contrat de gel JSON](../configs/research/confirmation_protocol_v1.freeze.json) persiste la
frontière temporelle, les signes et les empreintes du protocole et des sources scientifiques.

Fingerprint du protocole V1 :
`a805e6c218479b14d45da412d9d237e767bf76d2d6bc44c0cbea10a5b7b545da`.

Chaque exécution vérifie le lock, les signes, les registres feature/target, les sources de
formules, l'éligibilité, le calcul statistique, les versions des bibliothèques, Python et
`uv.lock`. Les sources scientifiques héritées sont également épinglées à leur état de
développement. Un changement est rejeté ; il demande une nouvelle version de protocole.
Les commits purement documentaires peuvent changer le SHA Git sans changer ces définitions.

## 2. Frontière développement / confirmation

L'initialisation inspecte les **81 partitions de targets de développement**, tous horizons
inclus. Elle prend le maximum des cutoffs, fins de targets, dernières observations futures
et de la borne du lock. Les chemins et checksums de ces fichiers sont persistés.

| Élément | Date |
|---|---|
| Dernière observation / outcome de développement | **28/09/2026** |
| Date de gel du protocole | **05/10/2026** |
| Début autorisé de confirmation | **06/10/2026** |
| Premier vendredi admissible de la grille V1 | **09/10/2026** |

Formule : lendemain de `max(fin du développement, date du gel)`. Le garde supplémentaire
de gel empêche un remplissage rétrospectif entre le développement et l'enregistrement
prospectif. La borne n'est plus recalculée avec les nouvelles données.

Au déploiement, le corpus réel s'arrête toujours le **28/09/2026**. Il existe **0 nouveau cutoff
source**, **0 cutoff enregistré**, **0 cutoff mature**. La prochaine maturité est inconnue :
elle exige cinq séances futures effectivement reçues et disponibles, pas une estimation
calendaire. Aucun rendement ou IC de confirmation n'est fabriqué.

## 3. Pipeline incrémental

```mermaid
flowchart LR
    A[Nouvelle séance vendredi] --> B[Prix disponibles au cutoff]
    B --> C[Éligibilité et features figées]
    C --> D[Registration scellée]
    D --> E[Attente de cinq séances futures]
    E --> F[Outcome et métriques scellés]
    F --> G[Monitor et checkpoints]
```

### Enregistrement prospectif

La grille V1 utilise les vendredis pour lesquels une séance equity existe. Un vendredi sans
séance ne fait pas l'objet d'un rollback implicite. Le cutoff D utilise les données disponibles
au plus tard à **00:00 Europe/Paris, D+1**, comme en développement. L'enregistrement a lieu
après disponibilité des prix et **avant qu'une observation future ne soit accessible** dans
la source locale. Une ancienne date, un doublon, un cutoff hors ordre ou un enregistrement
après observation du futur est rejeté.

L'éligibilité conserve la qualité approved connue à T, la présence de la série et au moins
une feature disponible selon le moteur hérité. Les valeurs manquantes propres aux candidats
restent explicites. Aucun univers historique SBF 120 n'est inféré.

Prix consommés, éligibilité, features canoniques, agrégats strict et baseline connue à T
sont stockés dans une partition scellée. Aucun résultat futur n'entre dans cette étape.

### Maturation et fermeture

Le premier snapshot contenant **cinq dates de séance equity communes après T** permet de
fermer le cutoff. Les observations futures sont limitées à cette fin de fenêtre. Une entité
ayant cinq observations dispose du target H5 hérité ; une série avec des trous conserve un
résultat non observable. L'horizon n'est jamais raccourci. Une target locale encore immature
ne reçoit pas une valeur et ne sera pas remplie rétrospectivement dans ce cutoff fermé.

Cette règle de fermeture est explicite et figée avant confirmation. Elle évite qu'une série
suspendue bloque tous les cutoffs. Elle peut réduire la couverture par rapport à un calcul
fait beaucoup plus tard dans le corpus de développement : cette sensibilité est une limite
du protocole et reste visible dans l'audit.

Une review future laisse la candidate calculable dans la politique ex ante. Une violation
forte peut être ininterprétable, avec candidate conservée. Aucune de ces annotations ne
modifie l'éligibilité à T. Les politiques **ex ante / future clean** restent comparables.

## 4. Append-only et provenance

Partitions faisant autorité :

```text
data/analysis/spec007-confirmation/
  protocol.json
  cutoffs/as_of_date=YYYY-MM-DD/
    registration.json
    past_observations.parquet
    eligibility.parquet
    features.parquet
    scores.parquet
    outcome/
      outcome_manifest.json
      future_observations.parquet
      targets.parquet
      cutoff_metrics.parquet
      prediction_metrics.parquet
```

Chaque partition est publiée par renommage après préparation, avec checksums. La fermeture
ajoute `outcome/` ; elle ne réécrit pas la registration. Une modification ou suppression
d'une partition, de ses données ou de ses métadonnées déjà publiées est détectée. Un verrou
de processus sérialise les writers. Un second appel de maturation ignore les cutoffs fermés.

Les fichiers récapitulatifs à la racine sont des **projections régénérables**, issues des
partitions immuables. Les préfixes des anciennes métriques restent identiques. Un nouveau
cutoff ne peut pas remplacer une ancienne observation, ni rétroactivement changer un ancien
checkpoint en raison d'une alerte de données survenue plus tard.

Les manifests enregistrent lock, registres, protocole, sources consommées, SHA Git et état
dirty, cutoff, dates d'enregistrement/maturité et grade PIT. Les révisions de prix après
fermeture ne sont pas réinjectées silencieusement.

## 5. Statistiques fixes

### Par candidat et cutoff

Les **504 candidats restent présents**, même avec zéro couple exploitable ou IC indisponible.
Les tables exposent, séparément par politique : Spearman à rangs moyens, N, couverture,
target moyen, taux de direction positive et spread D10−D1.

- Minimum IC : **30 couples**, feature et target non constants.
- Déciles : minimum **100 couples**, soit dix titres par décile en l'absence d'ex æquo.
- Les rangs sont calculés dans la coupe ; les ex æquo peuvent déséquilibrer les déciles.
- Coverage : N / nombre d'entités initialement éligibles, sans masquer les outcomes manquants.
- Spread : différence de target direction moyen ; **aucune unité de rendement ou PnL**.

### Cumul individuel

Nombre de cutoffs matures et d'IC observés, IC moyen/médian, écart-type échantillonnal,
concordance du signe par cutoff, moyenne glissante sur les huit derniers cutoffs,
spread moyen et couverture moyenne. Les valeurs indisponibles ne deviennent pas zéro.
L'ordre des candidats demeure celui de discovery ; aucun tri par réussite en confirmation.

### Test collectif principal

```text
oriented_ic = spearman_ic × expected_sign
```

Pour strict, strong et broad : nombre conforme, nombre inconnu, proportion conforme,
moyenne/médiane des IC moyens orientés, quartiles et nombre fortement inversé
(`mean oriented IC <= -0.01`). La proportion conforme utilise toute la cohorte figée comme
dénominateur ; les candidats inconnus sont également comptés séparément.

Les courbes affichent chaque préfixe mature, avec jalons 1/2/4/8/13/26. Les analyses de
groupe sont conservées par signature exacte de discovery, famille, fenêtre et corrélation
connue. Des moyennes donnant le même poids à chaque groupe complètent la moyenne par candidat.

Le lock contient 504 signatures distinctes et leurs aliases. Les corrélations déjà documentées
dans le snapshot de développement du 01/04/2026 ajoutent **12 liens / 492 groupes** parmi les
candidats. Ce diagnostic ancien porte sur plusieurs familles d'actifs ; il n'est ni une
preuve de 492 informations indépendantes ni un clustering adapté après lecture de confirmation.
La redondance approximative inconnue reste possible.

## 6. Inférence et checkpoints

**Profondeur cible : 26 cutoffs matures.** Aucun arrêt anticipé ou prolongement automatique
selon les résultats. Les checkpoints prévus sont **8 / 13 / 26**.

| Profondeur | Lecture |
|---|---|
| 1–3 | Descriptif uniquement |
| 4–7 | Descriptif ; V1 ne publie pas de bootstrap précoce |
| 8 / 13 / 26 | Intervalles aux checkpoints préannoncés |
| Entre checkpoints | Suivi descriptif, sans nouveau test significatif |

Bootstrap circulaire temporel, 10 000 réplications, seed de base 20261005, blocs **2/4/6**
comme en développement. Les dates tirées sont communes aux candidats. Les paramètres ne
sont jamais choisis d'après le meilleur résultat.

Les intervalles individuels portent sur l'IC orienté moyen et les collectifs sur la série
temporelle de l'IC orienté moyen de cohorte. La présentation retient l'enveloppe des intervalles
bilatéraux 90 % pour les trois blocs. Un candidat doit avoir un panel temporel complet pour
son intervalle. L'intervalle collectif exige tous les IC de sa cohorte à chaque date.
Un panel incomplet est signalé ; il n'est pas imputé.

Ces intervalles sont **pointwise**, sans correction multiple ni contrôle des regards
successifs. Aucun p-value, probabilité d'alpha ou verdict confirmatoire statistique n'en
est déduit. L'état du protocole et le verdict descriptif sont deux champs séparés.

| Verdict descriptif | Règle stricte préannoncée |
|---|---|
| supportive | >60 % conformes, moyenne >0 et médiane >0 |
| unsupportive | <40 % conformes, moyenne <0 et médiane <0 |
| mixed | Autres résultats exploitables |
| insufficient_data | <8 cutoffs, statistiques indéfinies, panel de checkpoint incomplet ou alerte de données |

Le statut mécanique est awaiting_new_data, collecting, checkpoint_8, checkpoint_13,
checkpoint_26 ; une fois 26 cutoffs fermés, il devient confirmation_complete avec le
checkpoint 26 conservé. Ces règles ne modifient jamais le lock.

## 7. Agrégats strict et baselines

Deux scores strict sont calculés **à T**, avec les 85 signes attendus :

1. **Equal-weight oriented rank** : `(rang moyen(feature × signe) − 0.5) / N`, puis
   moyenne des percentiles disponibles.
2. **Strict consensus** : fraction de ces percentiles strictement supérieurs à 0.5.

Il faut au moins **43/85 features** disponibles pour produire un score d'une entité.
Les poids sont égaux, sans calibration, régression ou sélection de variables.

Métriques : Spearman direction, AUC, accuracy au seuil strictement supérieur à 0.5,
balanced accuracy, lift du quintile supérieur et taille effective de ce quintile.
Les ex æquo au seuil Q80 peuvent élargir le groupe. Les targets exactement nulles restent
dans l'IC à trois modalités, mais sont exclues des métriques binaires. AUC et balanced
accuracy exigent les deux classes.

La baseline always-up expose le taux positif observé. Une baseline constante de majorité
utilise la direction des dernières fenêtres H5 **déjà terminées à T** dans la cohorte passée
(égalité : positif). La majorité future n'est jamais utilisée comme une prédiction.
Ces métriques restent distinctes des tests univariés et ne représentent pas une stratégie.

## 8. Audit et limites des données

Pour chaque registration : entités observées/éligibles, exclusions de qualité passée,
couverture des features et changement d'univers. Les alertes V1 sont <30 entités éligibles,
couverture <60 %, ou variation d'effectif >20 % par rapport au cutoff précédent.
Une alerte ne retire aucun candidat ; les préfixes concernés sont marqués non interprétables
scientifiquement pour leur verdict.

Après fermeture : nombres future-clean, warnings, ininterprétables et non observables,
avec prix et evidence source. La maturité des registrations encore ouvertes est suivie
en nombre de séances reçues et manquantes, sans prédire une date de cotation.

Le corpus conserve **pit_grade=reconstructed / strict_pit_claimed=false**. La disponibilité
ABC reste une convention, les corporate actions et vintages ne sont pas certifiés, et
l'univers reçu ne reconstitue pas un SBF 120 historique. Le target commence au close T ;
une future stratégie devra définir next_open ou une autre exécution ultérieure explicite.

## 9. Utilisation et artefacts

```bash
# Initialisation idempotente, sans confirmation fabriquée
uv run python scripts/confirmation_spec007.py init

# Après réception du nouveau vendredi, avant disponibilité du futur
uv run python scripts/confirmation_spec007.py register --cutoff 2026-10-09

# Au fil de l'arrivée des données, fermeture des cutoffs réellement mûrs
uv run python scripts/confirmation_spec007.py advance

# Projections / monitor seulement ; aucune sélection ou modification du lock
uv run python scripts/confirmation_spec007.py monitor
```

Un gros lot livré après plusieurs semaines ne peut pas servir à enregistrer rétroactivement
un cutoff dont le futur est déjà connu. Il faut enregistrer prospectivement les prochains
cutoffs. Les commandes consomment la base existante ; elles ne récupèrent aucune source réseau.

Sous `data/analysis/spec007-confirmation/`, hors Git :

- `confirmation_manifest.json` et `confirmation_data_quality.json` ;
- `confirmation_cutoff_metrics.parquet` ;
- `confirmation_candidate_metrics.parquet` ;
- `confirmation_cohort_metrics.parquet` ;
- `confirmation_group_metrics.parquet`, `confirmation_intervals.parquet` ;
- `confirmation_prediction_metrics.parquet` et les partitions scellées.

Au départ les tables sont vides et le manifest expose results_available=false. Leur contenu
numérique provient exclusivement des nouveaux cutoffs fermés, jamais du développement.

## 10. Sandbox et contrôles

[Confirmation Monitor dans Marimo](https://sandbox.hocus.works/quant-lab-srd/?v=spec007).

La section montre lock, date de départ, cutoffs enregistrés/matures, prochaine maturité,
effectifs broad/strong/strict, IC orientés, conformité et état du checkpoint. La courbe
collective est créée seulement après le premier cutoff mature.
Candidate detail présente l'histoire de développement en gris et la confirmation sur
une surface séparée, avec signe attendu, fenêtre, aliases, groupe et cumul.
Le lecteur UI consulte des projections vérifiées, sans calcul de features ni bootstrap.

Les tests utilisent uniquement des fixtures synthétiques isolées : immuabilité des locks
et signes, refus des dates anciennes et post hoc, append-only/doublons, maturité H5,
qualité future séparée, IC orientés, cohortes/groupes, scores/baselines, checkpoints,
fingerprints, modification du registre ou de l'implémentation, et séparation UI.

Contrôles exécutés le 5 octobre 2026 :

- Suite complète : **120 tests passent**, dont **23 tests SPEC-007** ; fixtures de
  confirmation synthétiques uniquement. Les 23 tests ont également été relancés après
  les derniers ajustements UI.
- `uv run ruff check .`, `uv run mypy src/` (**37 fichiers sources**) et
  `uv run marimo check notebooks/srd_research_lab.py` : succès.
- Navigateur Chromium sur le service sandbox : état awaiting_new_data, compteurs 0/0,
  métadonnées visibles, courbe development gris `#9ca3af`, absence de courbe de
  confirmation et aucune erreur JavaScript observée.
- L'URL publique conserve son authentification : HTTP **401** sans credentials.
- Relecture du monitor : mêmes fingerprints et borne, aucun résultat ajouté.

**État actuel : protocole opérationnel et gelé, zéro résultat indépendant.**
