# SRD — Sector-first + prédiction action

**6 octobre 2026 · version 1 · développement, sans nouvel entraînement.**

## A. Hypothèse

Un gate sectoriel améliore-t-il les cinq actions choisies par le rang RF H5 ? Comparaison appariée S0/S1/S2 sur les 22 cutoffs du replay commun, sans contexte ajouté au score action.

## B. Contrat et mapping

[Configuration figée](../configs/experiments/srd_sector_action_v1.json), enregistrée avant lecture des PnL ; calendrier et empreintes y sont explicites.

Deux secteurs, **cinq actions au total**, H10, deux compartiments, capital 1, prochain open. Coûts 0/25/45 bp AR appliqués moitié aux deux nominaux. Sortie H10 entrée incluse ; absence d’open = cash, absence de close = sortie retardée. Si moins de cinq actions : chaque action reçoit 1/5 du budget, les slots vides restent cash. Aucun troisième secteur, levier, short, complément ou exclusion selon outcome.

L’ancien projet ne possédait **aucun mapping action/secteur** : les 356 contextes étaient globaux. La présente expérience capture les industries [ABC Bourse](https://www.abcbourse.com/marches/secteurs), réutilise les **onze industries CAC** déjà présentes et leur pont vers les codes d’indices. Les super-secteurs STOXX, SOX et Biotechnology se chevauchent et ne sont pas ajoutés à cette partition. Cette règle de scope a été fixée avant les PnL ; le RF sectoriel lui-même reste entraîné sur son corpus original.

Mapping actuel : **164/164 actions** de l’union commune. Identité ISIN vérifiée sur les fiches publiques et rattachement par ticker à une seule industrie ; captures, sources et SHAs conservés. Airbus et Stellantis avaient une cotation canonique étrangère ; le lien parisien a été vérifié avec le même ISIN, avant la lecture des performances. Le premier mapping de 162 correspondances et ses replays techniques sont archivés localement ; le résultat publié utilise 164. Le référentiel est projeté sur 2026, **sans preuve PIT historique**. Aucun changement historique n’est certifié. Les titres sans mapping restent dans S0 et l’univers, mais ne passent pas les gates S1/S2.

| industry_code | sector_code | sector_name | member_count |
| --- | --- | --- | --- |
| 45 | QS0011017686 | CAC Biens de consommation | 31 |
| 50 | QS0011017652 | CAC Industries | 108 |
| 35 | FR0013506771 | CAC Immobilier | 44 |
| 55 | QS0011017637 | CAC Materiaux de base | 25 |
| 60 | QS0011017603 | CAC Petrole et Gaz | 22 |
| 20 | QS0011017702 | CAC Sante | 70 |
| 40 | QS0011017736 | CAC Services aux consommateurs | 141 |
| 65 | QS0011017785 | CAC Services aux collectivites | 17 |
| 30 | QS0011017801 | CAC Finances | 47 |
| 15 | QS0011017769 | CAC Telecommunications | 13 |
| 10 | QS0011017827 | CAC Technologie | 75 |

`member_count` décrit les tables ABC sources, tous titres confondus. Les effectifs du seul univers SRD commun figurent par cutoff ci-dessous.

| cutoff | universe_n | mapped_n | unmapped_n | model_sectors_n | momentum_sectors_n | model_top2 | momentum_top2 | s1_actions_n | s2_actions_n | s1_cash_slots | s2_cash_slots | counts_by_sector |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-01-02 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017801"] | ["abc-bourse-manual:index:QS0011017801", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-01-09 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017801"] | ["abc-bourse-manual:index:QS0011017785", "abc-bourse-manual:index:QS0011017801"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-01-16 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017785"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-01-23 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017801"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-01-30 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017637"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017603"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-02-06 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017801"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017603"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-02-13 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017801", "abc-bourse-manual:index:QS0011017785"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017603"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-02-20 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017785", "abc-bourse-manual:index:QS0011017827"] | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017637"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-02-27 | 164 | 164 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:FR0013506771"] | ["abc-bourse-manual:index:QS0011017637", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 37, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-03-06 | 163 | 163 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017652", "abc-bourse-manual:index:QS0011017769"] | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:QS0011017769"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-03-13 | 163 | 163 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017801", "abc-bourse-manual:index:QS0011017652"] | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-03-20 | 163 | 163 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017801", "abc-bourse-manual:index:FR0013506771"] | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:QS0011017785"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 17, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-03-27 | 162 | 162 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017652", "abc-bourse-manual:index:QS0011017801"] | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:QS0011017769"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 16, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-04-10 | 162 | 162 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:FR0013506771"] | ["abc-bourse-manual:index:QS0011017603", "abc-bourse-manual:index:QS0011017637"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 16, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-04-17 | 162 | 162 | 0 | 10 | 11 | ["abc-bourse-manual:index:FR0013506771", "abc-bourse-manual:index:QS0011017637"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017637"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 16, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-04-24 | 162 | 162 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017801", "abc-bourse-manual:index:FR0013506771"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017637"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 16, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-05-08 | 162 | 162 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017702", "abc-bourse-manual:index:QS0011017736"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017769"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 16, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-05-15 | 161 | 161 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017702", "abc-bourse-manual:index:QS0011017827"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017603"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 15, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-05-22 | 160 | 160 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017702", "abc-bourse-manual:index:QS0011017736"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017769"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 14, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 18} |
| 2026-05-29 | 159 | 159 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017736", "abc-bourse-manual:index:QS0011017827"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017769"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 14, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 17} |
| 2026-06-05 | 159 | 159 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017827"] | ["abc-bourse-manual:index:QS0011017827", "abc-bourse-manual:index:QS0011017637"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 14, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 17} |
| 2026-06-12 | 159 | 159 | 0 | 10 | 11 | ["abc-bourse-manual:index:QS0011017769", "abc-bourse-manual:index:QS0011017827"] | ["abc-bourse-manual:index:QS0011017686", "abc-bourse-manual:index:QS0011017827"] | 5 | 5 | 0 | 0 | {"abc-bourse-manual:index:FR0013506771": 11, "abc-bourse-manual:index:QS0011017603": 5, "abc-bourse-manual:index:QS0011017637": 7, "abc-bourse-manual:index:QS0011017652": 35, "abc-bourse-manual:index:QS0011017686": 7, "abc-bourse-manual:index:QS0011017702": 14, "abc-bourse-manual:index:QS0011017736": 36, "abc-bourse-manual:index:QS0011017769": 2, "abc-bourse-manual:index:QS0011017785": 8, "abc-bourse-manual:index:QS0011017801": 17, "abc-bourse-manual:index:QS0011017827": 17} |

Actions sans rattachement :

| ISIN | instrument | missing_reason |
| --- | --- | --- |


## C. Score secteur et score action

Secteur : **`rank_pct-h10-sector-rf-a701e8b7056b`**, RF H10, target `future.rank_pct.h10.family.v1`. Sélection de validation 2025 : IC 0.06194, déjà figée. Aucun alternatif choisi. Le score est un rang futur prédit, pas une prévision de rendement en %.

Action : **`rank_pct-h5-all-rf-3c5fa028d3f4`**, target `future.rank_pct.h5.family.v1`. Les 3 573 scores du replay commun sont conservés exactement. Les features sont les 1 048 entrées originelles dans chaque moteur, avec masques indices historiques.

Train 2024, choix sur S1 2025, fit final 2024+S1 2025 ; aucun label au-delà de la borne de retrain. Les prédictions sectorielles sont reproduites depuis le modèle sauvegardé, erreur max 3.33e-16. Le contrat versionné conserve les IDs, périodes exactes, fingerprints, SHAs du code original et des modèles ; `sector_model_metadata.json` conserve les 1 048 IDs de features.

Disponibilité modélisée des scores : minuit UTC D+1, avant l’open. Le mapping actuel constitue une exception documentaire explicite : il ne devient pas une information certifiée disponible à T par rétrodatation.

## D. Baselines et équivalence des gates

S0 = cinq meilleurs scores actions dans l’univers commun, exactement la référence rang H5→H10. S1 = top deux industries par RF existant puis top cinq actions. S2 = top deux industries par momentum passé **C(T)/C(T−20)−1**, observations natives disponibles à T, quote âgée au plus de trois jours, puis même top cinq actions.

**S1 et Action-first avec gate sont identiques** : filtrer un classement total conserve l’ordre de son sous-ensemble. Les égalités sont départagées par ID dans les deux variantes. Égalité vérifiée sur les 22 paniers ; aucun S1b supplémentaire.

Le moteur commun accepte désormais `allocation_slots=5` pour garder cash les slots absents ; son comportement par défaut est conservé. Les trois S0 reproduisent exactement les rendements, drawdowns, turnover et exposition du replay de référence.

## E. Résultats brut / 25 / 45 bp

| Stratégie | Brut | Net 25 bp | Net 45 bp | DD 45 bp | Exposition EOD | Capital actif | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | +36.14 % | +32.52 % | +29.70 % | -8.58 % | 65.9 % | 72.0 % | 21.48 |
| S1 | +7.02 % | +4.13 % | +1.88 % | -6.51 % | 67.1 % | 74.2 % | 21.88 |
| S2 | +41.42 % | +37.60 % | +34.61 % | -6.70 % | 67.2 % | 73.3 % | 21.88 |

### Détail des neuf simulations

Valeurs de rendement/exposition/hit rate/cash en fractions (×100 pour %) ; turnover en multiples de NAV ; PnL cutoff en fractions du capital initial. Rendements cumulés, non annualisés, suivis jusqu’au 31 juillet.

| strategy_id | cost_bp | cumulative_return | max_drawdown | turnover | average_exposure | average_active_session_capital | hit_rate | positions | average_actions_per_basket | average_cash_fraction | positive_cutoff_fraction | best_cutoff | best_cutoff_pnl | worst_cutoff | worst_cutoff_pnl | top_5_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | 0 | 0.36135 | -0.07962 | 21.49044 | 0.65939 | 0.72055 | 0.64815 | 108 | 5.00000 | 0.34061 | 0.77273 | 2026-05-15 | 0.10110 | 2026-06-12 | -0.06449 | 0.46285 |
| S0 | 25 | 0.32523 | -0.08303 | 21.48247 | 0.65936 | 0.72042 | 0.62037 | 108 | 5.00000 | 0.34064 | 0.77273 | 2026-05-15 | 0.09734 | 2026-06-12 | -0.06449 | 0.49950 |
| S0 | 45 | 0.29702 | -0.08575 | 21.47612 | 0.65933 | 0.72032 | 0.61111 | 108 | 5.00000 | 0.34067 | 0.77273 | 2026-05-15 | 0.09441 | 2026-06-12 | -0.06446 | 0.53431 |
| S1 | 0 | 0.07019 | -0.06093 | 21.89292 | 0.67055 | 0.74219 | 0.50000 | 110 | 5.00000 | 0.32945 | 0.50000 | 2026-05-15 | 0.05218 | 2026-06-12 | -0.04548 | 1.35811 |
| S1 | 25 | 0.04130 | -0.06326 | 21.88511 | 0.67053 | 0.74207 | 0.49091 | 110 | 5.00000 | 0.32947 | 0.50000 | 2026-05-15 | 0.04972 | 2026-06-12 | -0.04560 | 2.22088 |
| S1 | 45 | 0.01875 | -0.06512 | 21.87888 | 0.67052 | 0.74198 | 0.43636 | 110 | 5.00000 | 0.32948 | 0.50000 | 2026-05-15 | 0.04781 | 2026-06-12 | -0.04567 | 4.74196 |
| S2 | 0 | 0.41422 | -0.06488 | 21.88913 | 0.67173 | 0.73332 | 0.56364 | 110 | 5.00000 | 0.32827 | 0.77273 | 2026-05-15 | 0.05485 | 2026-06-12 | -0.03400 | 0.40657 |
| S2 | 25 | 0.37597 | -0.06604 | 21.88195 | 0.67173 | 0.73322 | 0.56364 | 110 | 5.00000 | 0.32827 | 0.72727 | 2026-02-13 | 0.05232 | 2026-06-12 | -0.03483 | 0.43613 |
| S2 | 45 | 0.34611 | -0.06697 | 21.87623 | 0.67173 | 0.73315 | 0.53636 | 110 | 5.00000 | 0.32827 | 0.68182 | 2026-02-13 | 0.05083 | 2026-06-12 | -0.03544 | 0.46372 |

### Valeur incrémentale : mêmes coûts

| comparison | cost_bp | delta_cumulative_return | delta_max_drawdown | delta_turnover | delta_average_exposure | delta_average_active_session_capital | delta_average_cash_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1-S0 | 0 | -0.29116 | 0.01869 | 0.40248 | 0.01116 | 0.02164 | -0.01116 |
| S1-S2 | 0 | -0.34403 | 0.00395 | 0.00379 | -0.00118 | 0.00887 | 0.00118 |
| S2-S0 | 0 | 0.05287 | 0.01474 | 0.39869 | 0.01234 | 0.01277 | -0.01234 |
| S1-S0 | 25 | -0.28392 | 0.01977 | 0.40263 | 0.01118 | 0.02165 | -0.01118 |
| S1-S2 | 25 | -0.33467 | 0.00279 | 0.00315 | -0.00120 | 0.00885 | 0.00120 |
| S2-S0 | 25 | 0.05074 | 0.01699 | 0.39948 | 0.01237 | 0.01280 | -0.01237 |
| S1-S0 | 45 | -0.27827 | 0.02064 | 0.40276 | 0.01119 | 0.02166 | -0.01119 |
| S1-S2 | 45 | -0.32736 | 0.00186 | 0.00264 | -0.00121 | 0.00883 | 0.00121 |
| S2-S0 | 45 | 0.04909 | 0.01878 | 0.40012 | 0.01240 | 0.01283 | -0.01240 |

## F. Drawdown, exposition et stabilité par cutoff

Le capital actif inclut entrée et sortie pendant la séance. La valeur EOD/cash vient des mêmes parts et marks que la NAV. Les périodes et le budget sont identiques, mais des paniers incomplets ou des retards peuvent modifier l’exposition.

| reference | cost_bp | cutoffs | s1_win_fraction | mean_delta_pnl | median_delta_pnl | sum_delta_pnl | best_delta | worst_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | 0 | 22 | 0.27273 | -0.01323 | -0.01216 | -0.29116 | 0.01925 | -0.06827 |
| S2 | 0 | 22 | 0.18182 | -0.01564 | -0.01336 | -0.34403 | 0.02783 | -0.05951 |
| S0 | 25 | 22 | 0.27273 | -0.01291 | -0.01199 | -0.28392 | 0.01917 | -0.06686 |
| S2 | 25 | 22 | 0.18182 | -0.01521 | -0.01289 | -0.33467 | 0.02758 | -0.05821 |
| S0 | 45 | 22 | 0.31818 | -0.01265 | -0.01185 | -0.27827 | 0.01910 | -0.06575 |
| S2 | 45 | 22 | 0.18182 | -0.01488 | -0.01252 | -0.32736 | 0.02739 | -0.05720 |

Les deltas ci-dessus attribuent des points de NAV par décision : les budgets capitalisés peuvent diverger. Les rendements de panier et leurs différences appariées sont séparés dans `paired_cutoff_deltas.parquet`.

Intervalles individuels 90 % par bootstrap circulaire partagé, 10 000 tirages, seed 20261006, blocs 2/4/6 sur les 22 dates, **deltas de rendement de panier**, pas une simulation d’une nouvelle NAV. Pas de contrôle de multiplicité ni confirmation indépendante.

| reference | block | mean_delta_basket | lower90 | upper90 | positive_sign_support |
| --- | --- | --- | --- | --- | --- |
| S0 | 2 | -0.02264 | -0.03786 | -0.00824 | 0.00450 |
| S2 | 2 | -0.02593 | -0.03834 | -0.01310 | 0.00010 |
| S0 | 4 | -0.02264 | -0.03836 | -0.00764 | 0.00390 |
| S2 | 4 | -0.02593 | -0.03689 | -0.01489 | 0.00000 |
| S0 | 6 | -0.02264 | -0.03929 | -0.00697 | 0.00530 |
| S2 | 6 | -0.02593 | -0.03565 | -0.01557 | 0.00000 |

## G. Selection overlap

| strategy_id | jaccard | overlap_fraction | changed_fraction | identical_cutoffs | mean_substitutions | mean_removed_score | mean_retained_score | sector_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 0.19679 | 0.30000 | 1.00000 | 0 | 3.50000 | 0.55182 | 0.54479 | 0.15152 |
| S2 | 0.12302 | 0.20000 | 1.00000 | 0 | 4.00000 | 0.54488 | 0.56812 | 0.15152 |

Le modèle ne fournit que dix scores d'industrie par date : CAC Biens de consommation est `review` dans son éligibilité passée, donc son score reste absent aux 22 cutoffs. Le momentum W20 y est calculable et appartient à son scope de onze industries ; il choisit cette industrie au cutoff du 12 juin. Cette différence de disponibilité est conservée et limite l'attribution de S1−S2 à la seule qualité du RF. Aucun score n'a été inventé et aucune date n'a été retirée. Les scores conservés/supprimés sont moyennés par cutoff. Les fichiers `selections`, `rejections` et `coverage` conservent les deux secteurs, scores, actions ajoutées et rejetées ; une absence de mapping/score est explicite, aucun cutoff supprimé.

## H. Attribution sectorielle

PnL = fractions du capital initial ; contribution en points ; poids moyen = valeur du secteur au close / NAV, cash et jours sans position compris. Les trades sans mapping S0 sont attribués à `UNMAPPED`.

| strategy_id | sector_name | pnl | contribution_points | average_weight | trades | hit_rate |
| --- | --- | --- | --- | --- | --- | --- |
| S0 | CAC Immobilier | 0.02673 | 2.67301 | 0.09121 | 15 | 0.66667 |
| S0 | CAC Petrole et Gaz | 0.03025 | 3.02537 | 0.04266 | 7 | 0.71429 |
| S0 | CAC Materiaux de base | 0.00414 | 0.41445 | 0.04346 | 7 | 0.42857 |
| S0 | CAC Industries | 0.05074 | 5.07390 | 0.12795 | 21 | 0.71429 |
| S0 | CAC Biens de consommation | 0.00928 | 0.92810 | 0.03032 | 5 | 0.40000 |
| S0 | CAC Sante | 0.01910 | 1.91047 | 0.07416 | 12 | 0.50000 |
| S0 | CAC Services aux consommateurs | -0.00369 | -0.36938 | 0.02904 | 5 | 0.40000 |
| S0 | CAC Telecommunications | -0.02272 | -2.27235 | 0.01741 | 3 | 0.33333 |
| S0 | CAC Services aux collectivites | -0.01349 | -1.34909 | 0.01786 | 3 | 0.66667 |
| S0 | CAC Finances | 0.01844 | 1.84401 | 0.09116 | 15 | 0.53333 |
| S0 | CAC Technologie | 0.17823 | 17.82344 | 0.09411 | 15 | 0.80000 |
| S1 | CAC Immobilier | -0.03310 | -3.30973 | 0.18975 | 31 | 0.45161 |
| S1 | CAC Petrole et Gaz | -0.00961 | -0.96149 | 0.01167 | 2 | 0.00000 |
| S1 | CAC Materiaux de base | -0.01657 | -1.65724 | 0.01800 | 3 | 0.33333 |
| S1 | CAC Industries | 0.01909 | 1.90860 | 0.06137 | 10 | 0.60000 |
| S1 | CAC Sante | 0.00345 | 0.34463 | 0.02425 | 4 | 0.75000 |
| S1 | CAC Services aux consommateurs | -0.00275 | -0.27517 | 0.07102 | 12 | 0.25000 |
| S1 | CAC Telecommunications | -0.02201 | -2.20084 | 0.01768 | 3 | 0.00000 |
| S1 | CAC Services aux collectivites | 0.01268 | 1.26818 | 0.02473 | 4 | 0.50000 |
| S1 | CAC Finances | 0.02425 | 2.42487 | 0.14641 | 24 | 0.45833 |
| S1 | CAC Technologie | 0.04333 | 4.33349 | 0.10562 | 17 | 0.47059 |
| S2 | CAC Petrole et Gaz | 0.12701 | 12.70134 | 0.18856 | 31 | 0.54839 |
| S2 | CAC Materiaux de base | -0.04201 | -4.20119 | 0.09072 | 15 | 0.20000 |
| S2 | CAC Biens de consommation | -0.00339 | -0.33883 | 0.01808 | 3 | 0.33333 |
| S2 | CAC Telecommunications | 0.00766 | 0.76579 | 0.07775 | 13 | 0.53846 |
| S2 | CAC Services aux collectivites | 0.03243 | 3.24340 | 0.12816 | 21 | 0.71429 |
| S2 | CAC Finances | -0.01414 | -1.41429 | 0.03035 | 5 | 0.00000 |
| S2 | CAC Technologie | 0.23855 | 23.85503 | 0.13810 | 22 | 0.72727 |

## I. Conditional IC et première couche sectorielle

| group | mean_ic | median_ic | positive_ic_fraction | valid_cutoffs | total_n | mean_n | missing_outcomes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full | 0.06641 | 0.05083 | 0.68182 | 22 | 3569 | 162.22727 | 4 |
| other_mapped_sectors | 0.07929 | 0.08756 | 0.68182 | 22 | 2883 | 131.04545 | 4 |
| top2_model | -0.07031 | -0.13214 | 0.31818 | 22 | 686 | 31.18182 | 0 |
| unmapped | — | — | — | 0 | 0 | 0.00000 | 0 |

IC = Spearman entre score action préservé et rendement réellement calculable open→H10 théorique, minimum cinq couples non constants. Les sorties retardées restent au portefeuille ; les endpoints manquants sont comptés dans cet IC. La coupe « autres » comprend les autres secteurs mappés ; `unmapped` est séparé. Ces groupes peuvent être petits et ont une dispersion propre.

Couche secteurs, onze candidats : IC moyen +0.0832, médiane -0.0182, hit top2 20.5 %. Hit top2 = part des deux choix réellement dans les deux premières industries futures ; il diffère de la part de rendements positifs. Outcomes close-à-close H10 alignés sur le calendrier commun, quotes as-of âge ≤3 jours, indices descriptifs sans exécution négociable. Momentum : IC sectoriel moyen +0.2140, hit top2 27.3 %. Le résultat publié 0,1583 sur le panel sectoriel complet ne s’applique pas automatiquement à ce sous-ensemble CAC.

| cutoff | n | spearman | momentum_spearman | momentum_top2_hit | top2_hit | top2_positive_fraction | top2_real_return | top2_mean_real_rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-01-02 | 10 | -0.23636 | 0.33636 | 0.00000 | 0.00000 | 0.50000 | 0.00212 | 9.00000 |
| 2026-01-09 | 10 | 0.50303 | -0.00909 | 0.00000 | 0.00000 | 0.00000 | -0.02117 | 6.00000 |
| 2026-01-16 | 10 | 0.57576 | 0.84545 | 0.50000 | 0.00000 | 0.50000 | 0.02490 | 4.50000 |
| 2026-01-23 | 10 | 0.27273 | 0.55455 | 0.50000 | 0.00000 | 1.00000 | 0.03512 | 6.50000 |
| 2026-01-30 | 10 | 0.33333 | 0.24545 | 0.00000 | 0.50000 | 1.00000 | 0.05611 | 4.50000 |
| 2026-02-06 | 10 | 0.03030 | 0.59091 | 0.50000 | 0.00000 | 1.00000 | 0.02989 | 7.50000 |
| 2026-02-13 | 10 | 0.72121 | 0.35455 | 0.00000 | 1.00000 | 1.00000 | 0.08816 | 1.50000 |
| 2026-02-20 | 10 | 0.27273 | 0.18182 | 0.00000 | 0.50000 | 0.50000 | 0.00505 | 2.50000 |
| 2026-02-27 | 10 | -0.03030 | 0.10000 | 0.00000 | 0.50000 | 0.50000 | -0.04470 | 5.50000 |
| 2026-03-06 | 10 | -0.40606 | 0.68182 | 0.50000 | 0.00000 | 0.00000 | -0.03740 | 6.50000 |
| 2026-03-13 | 10 | -0.24848 | 0.20000 | 0.50000 | 0.00000 | 0.00000 | -0.04154 | 7.50000 |
| 2026-03-20 | 10 | -0.01818 | 0.49091 | 0.50000 | 0.00000 | 1.00000 | 0.03821 | 5.50000 |
| 2026-03-27 | 10 | 0.63636 | -0.41818 | 0.00000 | 0.50000 | 1.00000 | 0.11302 | 3.00000 |
| 2026-04-10 | 10 | -0.11515 | 0.23636 | 0.00000 | 0.50000 | 0.50000 | -0.00543 | 5.00000 |
| 2026-04-17 | 10 | -0.01818 | -0.15455 | 0.50000 | 0.00000 | 0.00000 | -0.04927 | 6.50000 |
| 2026-04-24 | 10 | -0.36970 | 0.36364 | 0.50000 | 0.00000 | 0.50000 | -0.00117 | 5.00000 |
| 2026-05-08 | 10 | -0.01818 | 0.11818 | 1.00000 | 0.00000 | 0.50000 | 0.00966 | 6.50000 |
| 2026-05-15 | 10 | -0.04242 | 0.18182 | 0.50000 | 0.50000 | 1.00000 | 0.04281 | 4.00000 |
| 2026-05-22 | 10 | 0.01818 | 0.04545 | 0.50000 | 0.00000 | 1.00000 | 0.00621 | 5.50000 |
| 2026-05-29 | 10 | 0.47879 | -0.13636 | 0.00000 | 0.50000 | 1.00000 | 0.04250 | 3.00000 |
| 2026-06-05 | 10 | -0.13939 | -0.41818 | 0.00000 | 0.00000 | 0.00000 | -0.03053 | 8.50000 |
| 2026-06-12 | 10 | -0.36970 | 0.31818 | 0.00000 | 0.00000 | 0.00000 | -0.06318 | 9.50000 |

### Interaction, diagnostic uniquement

Produit du rang percentile du score action et du rang percentile du score secteur. Aucun entraînement et aucune sélection de portefeuille sur ce produit. Comparaison à l’action seule sur le même sous-échantillon mappé et scoré :

| cutoff | n | action_ic_same_mapped_sample | interaction_ic |
| --- | --- | --- | --- |
| 2026-01-02 | 157 | -0.05666 | -0.01359 |
| 2026-01-09 | 157 | 0.07868 | 0.15271 |
| 2026-01-16 | 157 | 0.00003 | 0.10502 |
| 2026-01-23 | 157 | 0.29832 | 0.39420 |
| 2026-01-30 | 157 | 0.10813 | 0.22282 |
| 2026-02-06 | 156 | 0.05013 | 0.08859 |
| 2026-02-13 | 156 | 0.21452 | 0.16765 |
| 2026-02-20 | 156 | 0.11871 | 0.14790 |
| 2026-02-27 | 156 | -0.00263 | 0.01819 |
| 2026-03-06 | 156 | 0.21075 | 0.08897 |
| 2026-03-13 | 156 | 0.22306 | 0.14086 |
| 2026-03-20 | 156 | 0.01703 | 0.03396 |
| 2026-03-27 | 155 | -0.05605 | 0.05020 |
| 2026-04-10 | 155 | -0.13331 | -0.12808 |
| 2026-04-17 | 155 | 0.05657 | 0.06448 |
| 2026-04-24 | 155 | -0.06431 | -0.08233 |
| 2026-05-08 | 155 | 0.04214 | 0.01323 |
| 2026-05-15 | 154 | -0.25544 | -0.17530 |
| 2026-05-22 | 153 | -0.02557 | -0.01285 |
| 2026-05-29 | 152 | 0.40023 | 0.35684 |
| 2026-06-05 | 152 | 0.07902 | -0.08035 |
| 2026-06-12 | 152 | 0.14364 | -0.13636 |

IC moyen du produit : +0.06440 ; action seule sur les mêmes paires : +0.06577. Le produit ne montre pas de gain moyen avec ce diagnostic. Les 25 cellules action×secteur (quintiles) sont dans `interaction_bins.parquet` ; moyenne des moyennes par date, N et couverture conservés. L’effet monotone ou incrémental n’est pas présupposé par cette construction multiplicative.

## J. Concentration et événements

| strategy_id | top1_contribution | top3_contribution | top5_contribution | top10_contribution | top_5_share | absolute_contribution_hhi | top_sector_contribution | top2_sector_contribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | 0.04280 | 0.10709 | 0.15870 | 0.24736 | 0.53431 | 0.01901 | 0.17823 | 0.22897 |
| S1 | 0.03621 | 0.06299 | 0.08893 | 0.14017 | 4.74196 | 0.01859 | 0.04333 | 0.06758 |
| S2 | 0.04476 | 0.11071 | 0.16050 | 0.25374 | 0.46372 | 0.01865 | 0.23855 | 0.36556 |

Tous les événements restent inclus. Les preuves prix sont réutilisées quand instrument/entrée/sortie concordent avec les replays déjà audités ; les nouveaux cas ont un registre séparé pending. Aucun volume n’a été remplacé.

## K. Limites et réponses aux dix questions

1. **Gate et net 45 bp : Non sur cette période.** S1 +1.88 %, S0 +29.70 % ; delta -27.83 points.
2. **Drawdown :** S1 -6.51 %, S0 -8.58 % ; moins sévère.
3. **Turnover :** S1 21.88, S0 21.48 fois NAV ; delta +0.40.
4. **Paniers réellement changés :** 100.0 % des dates, 3.50 substitutions en moyenne, Jaccard 0.197.
5. **Modèle vs momentum :** S1 +1.88 %, S2 +34.61 % ; modèle inférieur en rendement net observé. Pas de preuve indépendante de supériorité.
6. **IC action conditionnel :** top2 -0.0703, univers +0.0664, autres secteurs +0.0793. Composition et petits N empêchent une lecture causale simple.
7. **Concentration :** cinq meilleurs trades = 474.2 % du gain net S1 ; deux meilleurs secteurs = +6.76 points. Les parts peuvent dépasser 100 % avec compensation par pertes.
8. **Secteurs contributeurs principaux S1 :** CAC Technologie (+4.33 points), CAC Finances (+2.42 points).
9. **Résistance aux 45 bp :** S1 +1.88 % après le forfait ; fiscalité par titre, minimums, spread et impact non certifiés.
10. **Gel prospectif : non exécuté.** Ce replay ne justifie pas de privilégier la variante face aux deux références. Le mapping actuel devra être capturé à l’avance pour une vraie phase prospective.

La source de prix reste reconstruite, corporate actions/vintages et volumes incomplets. 2024–2026 ont été explorés ; les choix de gate n’en font pas une nouvelle période indépendante. Le mapping sectoriel actuel est une limite supplémentaire, sans rétrodatation de sa capture. SPEC-007, les deux modèles et leurs scores restent inchangés.

## L. Reproduction, tests et sandbox

```bash
# Capture actuelle seulement ; conserver ses vintages pour reproduire
uv run --with beautifulsoup4 python scripts/capture_srd_sector_mapping.py
uv run python scripts/replay_srd_sector_action.py
uv run python scripts/publish_srd_sector_action.py
uv run pytest tests/test_srd_sector_action.py tests/test_srd_common_replay.py -q
```

[Sector + Action · Model Lab](https://sandbox.hocus.works/quant-model-lab/), sous authentification. Filtres de consultation, aucune modification du top cinq scientifique. Les captures et données sont locales, non versionnées ; contrat/config/code/docs et [empreintes](SRD_SECTOR_ACTION_RESULTS.sources.json) sont dans Git.

### A. Valeur du filtre secteur

Non sur cette période pour le gate RF S1. Le gate momentum S2 donne +34.61 % contre +29.70 % pour S0, soit +4.91 points : un résultat descriptif positif pour cette règle, sans confirmation indépendante.

### B. Valeur du modèle secteur

Inférieur en rendement net observé face au momentum W20, descriptivement.

### C. Décision

Ne pas geler S1 sur la base de ce résultat. S2 peut servir une hypothèse distincte, après examen de sa concentration et des différences de couverture. Aucun gel automatique : la confirmation demanderait un protocole distinct et un mapping observé à chaque décision. Les résultats actuels servent au développement.

**development evidence only — no independent alpha confirmation.**


**Tests : 45 passés, 0 échec, 0 ignoré.**