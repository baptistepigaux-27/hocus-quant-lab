# Actions seules — modèles H1/H2/H3, détention jusqu'à H5

**6 octobre 2026 · contrat fixé avant les résultats.**

## Périmètre et définitions

Même corpus ABC SRD, **1 048 features d'action**, éligibilité à T et grille
hebdomadaire du benchmark parent. Les snapshots de features et sources sont
copiés avec leurs checksums ; aucun contexte de marché ajouté. Apprentissages
2024, sélection S1 2025, retrain 2024+S1 2025, lecture S1 2026.

| Target | H1 | H2 | H3 |
| --- | --- | --- | --- |
| Direction absolue | Oui | Oui | Oui |
| Rendement absolu | Oui | Oui | Oui |
| Direction relative au CAC AllShares | Oui | Oui | Oui |
| Rang du rendement | Oui | Oui | Oui |
| Équilibre des excursions | Oui | Oui | Oui |
| Tendance / erreur-type | Indéfinie | Indéfinie | Oui, 1 degré de liberté |

**16 tâches**, 74 modèles finaux : naïfs, linéaires, RF et XGB. Mêmes grilles et
seed que les modèles actions H5/H10, sans nouvelle recherche sur le test.
Pas de permutation marginale de 1 048 variables. Gagnants choisis par AUC pour
directions et IC moyen pour régressions sur validation uniquement.

Targets close-à-close : `close(T+H)/close(T)−1`. Les H closes futurs sont ceux du
calendrier commun observé, sans avancer vers une séance plus lointaine lorsqu'un
prix manque. Benchmark aligné aux mêmes dates. Direction = signe ; rang = rang
moyen ascendant / nombre de rendements interprétables dans la coupe éligible.
La borne d'information est minuit UTC D+1, compatible avec les indices déclarés
disponibles à cette heure et avec les cours d'actions déjà disponibles à minuit Paris.
Les features d'action ne changent pas : aucun nouveau close n'entre dans ces deux
heures supplémentaires. Le benchmark utilise son dernier close connu au cutoff,
normalement celui de cette séance, puis le close à la date future commune ;
une quote de fin absente laisse la direction relative indisponible. Un titre
sans quote au cutoff peut également utiliser un close de référence plus ancien.
Excursions = meilleur + pire rendement par rapport au close de référence.

À H1, excursion = deux fois le rendement absolu : ces deux tâches sont redondantes,
sans découverte indépendante. Le t-stat est mathématiquement indéfini pour H1/H2
et n'est pas remplacé par un faux zéro. À H3, les trois closes futurs définissent
la pente normalisée, avec un seul degré de liberté ; conventions de clipping du
registre précédent conservées. Volatilité diagnostique nulle au sens indisponible
pour H1/H2, calculable sur deux variations à H3.

## Disponibilité, frontières et qualité

Features strictement identiques au snapshot parent. Les futurs ne changent pas
l'éligibilité à T. Les dates sont purgées selon H séances et les labels franchissant
une frontière train/validation/test sont indisponibles. Une quote future absente
ou un hard error rend le label indisponible ; les warnings restent annotés.
Les valeurs candidates restent disponibles pour audit. Un label indisponible
ne retire pas l'action du fichier des scores test quand le cutoff est admissible.
PIT toujours reconstruit ; composition historique de l'univers non certifiée.

## Performance prédictive et performance exécutable

La feature peut utiliser le close T, disponible ensuite. **L'entrée simulée est
donc au prochain open**, puis sortie au H-ième close commun, ou au cinquième close
pour la prolongation. L'overnight close T → open suivant entre dans la target,
sans entrer dans le gain de la position. Le rapport distingue IC/AUC close-à-close
et rendements effectivement simulés. Diagnostic gap / rendement après l'open :

```text
1 + rendement target = (1 + gap close T → open suivant)
                    × (1 + rendement open suivant → close T+H)
```

Top 3 % acheté, long-only sans levier, mêmes scores pour détention H et H5.
Deux compartiments pour toutes les détentions H1/H2/H3/H5 : même budget nominal
par nouvelle date, mais exposition moyenne et temps investi différents.
Avec la grille hebdomadaire, H1 est principalement en cash entre deux décisions.
Rapporter NAV cumulée, drawdown, exposition moyenne et rendements moyens des
paniers par cutoff. Aucun réinvestissement quotidien de nouveaux signaux.

**Performance brute = avant frais**, scénario 0 bp. Replays supplémentaires à
25/45 bp pour mesurer la sensibilité. L'univers équipondéré utilise les mêmes
dates, compartiments et détentions. Les minimums de courtage, TTF titre par titre,
spread observé et dividendes ne sont pas modélisés.

Décisions S1 2026, liquidations suivies jusqu'au 31 juillet. Les modèles H1/H2
peuvent admettre une date de plus que H3 ; comparer aussi les cutoffs communs
dans les diagnostics de paniers, sans retirer de décision du replay principal.

## Reproduction et publication

```bash
uv run python scripts/srd_short_horizons.py data
uv run python scripts/srd_short_horizons.py run
uv run python scripts/srd_short_horizons.py publish
```

Dossier local `data/analysis/srd-short-horizons-v1/`, ignoré par Git. Fits deux par
deux, quatre threads par estimateur, tâches isolées et reprise des tâches complètes.
Calculs et modèles sauvegardés rejoués avant publication dans Marimo. Les anciens
registres et expériences H5/H10 restent conservés ; cette extension est additive.
Toutes les périodes ont déjà été explorées : développement, sans confirmation
indépendante ni certification des corporate actions.
