# SRD — audit des prix et des contributions matérielles

**6 octobre 2026 · version 1 · base scientifique `76629a6`.**

**Statut :** audit exécuté sur les horizons courts. Les simulations originales,
scores, modèles et règles d'éligibilité sont conservés. Le
[registre des expérimentations](EXPERIMENTATIONS_SYNTHESE.md) décrit leur contexte.

## 1. Résultat de l'audit

**Le trade X-FAB à +50 % est corroboré par les prix historiques Euronext.**
L'audit ne trouve pas de prix d'entrée ou de sortie erroné dans les cas matériels
examinés. Il trouve en revanche **des différences de volume**, ainsi qu'une
forte concentration des gains et des pertes dans quelques événements.

| Contrôle | Périmètre | Résultat |
| --- | ---: | --- |
| Source normalisée → fichiers ABC bruts | 199 416 lignes, 49 payloads | Checksums valides ; valeurs OHLCV identiques, aucun écart |
| Ledger → open/close source | 3 752 trades exécutés | Aucun écart de prix, de rendement ou de PnL |
| Sélections non exécutées | 28 lignes | Conservées, sans remplacement ; Nacon sans open pendant la suspension |
| Cas matériels regroupés | 148 cas, 46 instruments | Gains et pertes, warnings et exécutions manquantes inclus |
| Entrées/sorties matérielles → Euronext | 140 cas exécutés | Tous les opens d'entrée et closes de sortie correspondent |
| Entrées manquantes → Euronext | 8 cas distincts | Pas d'open traité ; volume nul dans la table de la place |
| Barres externes comparables, dédupliquées | 1 180 séances/instrument | Opens, highs et closes identiques ; un low diffère de 0,00005 € |
| Volumes externes comparables | 1 180 séances/instrument | 66 différences sur 23 instruments ; volume Euronext supérieur dans les 66 cas |

Les 32 portefeuilles audités sont les deux détentions — native et H5 — des
**16 gagnants choisis sur la validation 2025**, en brut, long-only et top 3 %,
avec deux compartiments. Ils proviennent de
[l'expérience H1/H2/H3](SRD_SHORT_HORIZONS_RESULTS.md). Les répétitions d'un trade
dans plusieurs portefeuilles expliquent la différence entre lignes et cas distincts.

Le rapprochement externe est rétrospectif. Il ne prouve ni le vintage disponible
à T, ni la possibilité d'obtenir ces fills avec un montant donné. Les autres
modèles H5/H10, contextes et VAD ne sont pas couverts par cette nouvelle vérification externe.

## 2. Méthode et traçabilité

1. Identifier les modèles gagnants depuis la table de validation déjà publiée.
2. Relire leurs ledgers bruts à détention native et H5 ; ne sélectionner aucun
   modèle à partir de la performance 2026.
3. Vérifier chaque SHA256 du payload ABC puis comparer les cinq champs OHLCV de
   chaque ligne source avec le fichier texte ; conserver chemin et numéro de ligne.
4. Recalculer `exit_close / entry_open − 1` et
   `shares × (exit_close − entry_open)` pour toutes les entrées exécutées.
5. Former un registre de diagnostic : contribution absolue d'au moins **un point
   du capital initial**, ou qualité différente de `approved`, ou statut différent
   de `closed`. Ce seuil sert à prioriser l'audit après observation des résultats ;
   **il ne définit pas une règle de trading ou d'exclusion**.
6. Collecter les tables historiques publiques de la place pour les dates concernées,
   via son interface JavaScript normale, paramètres `adjusted=0`, `base100=0`.
   Conserver réponse, requête, heure de récupération, table et SHA256.
7. Dédupliquer les comparaisons par ISIN/date/champ ; rapprocher séparément
   prix, volume, absence de transaction et événement économique.

La première capture contient dix épisodes, la seconde couvre les cas restants
sur 46 instruments : **56 réponses** au total. Les intervalles collectés comptent
1 188 couples instrument/date, dont huit dates Nacon sans transaction.
Les preuves complètes restent locales. Les liens de lecture passent par les
fiches de [X-FAB](https://live.euronext.com/en/product/equities/BE0974310428-XPAR),
[MaaT Pharma](https://live.euronext.com/en/product/equities/FR0012634822-XPAR)
et [Nacon](https://live.euronext.com/en/product/equities/FR0013482791-XPAR), rubrique
« Historical Price », avec les dates indiquées ci-dessous.

## 3. X-FAB : gain réel dans la source, effet fortement concentré

Pour le **modèle rendement absolu H3 XGBoost**, détention trois séances :

| Étape | Date | Prix / indicateur |
| --- | --- | ---: |
| Décision | 22/05/2026 | Dernier close : 7,89 € |
| Achat simulé au prochain open | 25/05/2026 | 8,00 € |
| Close intermédiaire | 26/05/2026 | 8,985 € |
| Close de sortie H3 | 27/05/2026 | 12,00 € |
| Plus haut de la séance de sortie | 27/05/2026 | 15,88 € |
| Volume de la séance de sortie | 27/05/2026 | 5 936 619 titres |
| Rendement du trade | Trois séances | **+50,00 %** |
| Contribution du trade | Capital initial du portefeuille | **+5,7788 points** |

Ces barres, y compris les volumes de cet épisode, correspondent à la table
[Euronext X-FAB](https://live.euronext.com/en/product/equities/BE0974310428-XPAR).
Le modèle n'est pas sorti au pic de 15,88 €, mais au close de 12 €.
Le statut `review` découle de l'amplitude du mouvement ; il ne démontre pas un split.
La cause économique précise n'est pas établie par un communiqué primaire dans cet audit.

| Attribution comptable du portefeuille H3 | Points du capital initial |
| --- | ---: |
| Gain brut total | **+23,4759** |
| X-FAB seul | +5,7788 |
| Cinq meilleurs trades, X-FAB inclus | **+15,8342** |
| Tous les autres trades, pertes incluses | +7,6416 |

Le premier trade représente **24,62 %** du gain, les cinq premiers **67,45 %**.
Le dernier chiffre est une somme de contributions aux tailles originales.
**Ce n'est pas la performance d'une stratégie rejouée après suppression des gagnants** :
une telle suppression changerait cash, tailles ultérieures et composition.

### Les cinq premières contributions du même portefeuille

| Action | Entrée → sortie | Open → close | Rendement titre | Contribution |
| --- | --- | --- | ---: | ---: |
| X-FAB · BE0974310428 | 25/05 → 27/05 | 8,00 → 12,00 € | +50,00 % | +5,7788 points |
| MaaT Pharma · FR0012634822 | 26/01 → 28/01 | 5,70 → 7,36 € | +29,12 % | +2,9834 points |
| Eramet · FR0000131757 | 23/02 → 25/02 | 49,98 → 63,15 € | +26,35 % | +2,7296 points |
| OVH · FR0014005HJ9 | 01/06 → 03/06 | 13,92 → 16,85 € | +21,05 % | +2,5579 points |
| STMicroelectronics · NL0000226223 | 01/06 → 03/06 | 59,72 → 68,49 € | +14,69 % | +1,7846 points |

Les cinq paires de prix concordent avec les captures de la place. Ce résultat
certifie le rapprochement des chiffres observés, sans attribuer une causalité au modèle.

## 4. Pertes matérielles : les conserver dans l'expérience

### Nacon : suspension et sortie retardée

Le panier entré le **16 février à 0,383 €**, prévu pour sortir en H5 le **20 février**,
ne dispose pas de close traité ce jour-là. Le ledger attend le **4 mars**, date
de reprise, et sort à **0,1438 €**, soit **−62,4543 %** pour le titre.
Cette même trajectoire apparaît dans cinq portefeuilles gagnants, avec une
contribution entre **−6,3851 et −6,5877 points** selon la taille de l'allocation.

L'émetteur annonce la suspension dès l'ouverture du 20 février, puis une reprise
le 4 mars. Ces dates concordent avec la table de la place et les données livrées.
[Communiqué du 20 février](https://corporate.nacongaming.com/wp-content/uploads/2026/02/Nacon-CP-20.02.2026-Diffusion.pdf),
[communiqué du 3 mars](https://corporate.nacongaming.com/wp-content/uploads/2026/03/Nacon-CP-03.03.2026-Diffusion.pdf).

La place affiche un close de valorisation inchangé pendant la suspension, avec
open absent et volume nul. **Ce prix indicatif ne permet pas de simuler une sortie.**
Le moteur conserve les positions jusqu'au prochain close source et annote le retard.
Les 28 tentatives d'entrée manquantes, regroupées en huit cas, restent du cash.
Le communiqué de reprise présente un ISIN incomplet dans son texte ; l'identité
est rapprochée avec le premier communiqué et la fiche de la place.

### MaaT Pharma : mauvaise nouvelle pendant la détention

Le panier entré le **18 mai à 7,20 €** sort le **22 mai à 3,255 €**, soit
**−54,7917 %**. Le communiqué du 20 mai au soir rapporte une orientation
défavorable du CHMP sur le dossier d'autorisation. L'open du 21 mai est **2,70 €**.
L'événement est cohérent temporellement avec la rupture observée ; il ne certifie
pas à lui seul une explication causale complète de chaque transaction.
[Communiqué de MaaT Pharma](https://www.maatpharma.com/may-20-2026-maat-pharma-provides-an-update-on-the-application-for-marketing-authorization-of-maat013-xervyteg-in-the-treatment-of-acute-graft-versus-host-disease/).

Cette perte reste incluse dans quatre portefeuilles gagnants détenus H5,
avec des contributions de **−5,7824 à −6,2255 points**. Retirer les événements
extrêmes défavorables tout en conservant X-FAB introduirait une sélection ex post.

## 5. Nouveau point ouvert : définition des volumes

Les **66 écarts de volume** représentent 5,59 % des 1 180 séances comparables
de ce sous-échantillon orienté vers les cas matériels. Ce taux ne mesure pas le
taux d'erreur de l'ensemble du corpus. Les prix d'exécution correspondent même
sur ces séances, mais le volume Euronext est chaque fois supérieur au volume ABC.

Exemple : **FR0010331421, 16 avril 2026** : 438 675 dans le fichier ABC contre
1 107 675 dans la table Euronext, différence de 669 000 titres.
Les deux chiffres et leurs empreintes sont conservés dans `primary_differences.csv`.

Plusieurs mécanismes restent possibles : périmètre de transactions, blocs,
heure de consolidation ou révision. Euronext documente des flux distincts pour
transactions négociées, blocs et transactions après séance, ce qui fournit une
piste de vérification, **sans établir la cause de nos écarts**.
[Guide officiel TCS](https://connect.euronext.com/sites/default/files/it-documentation/Euronext%20Cash%20Markets%20-%20TCS%20Web%20Access%20-%20User%20Guide%20-%20External%20-%20v5.20.0%20%2BTC.pdf).

Le contrôle brut → silver montre que ces écarts ne sont pas créés par notre
parseur. Ils ne changent pas directement les PnL open/close des trades existants ;
ils **peuvent changer les features de volume et donc les scores et paniers**.
Leur impact prédictif n'a pas été mesuré. Ne pas remplacer seulement les volumes
des trades observés : il faut une convention cohérente sur tout l'historique,
avec vintage, puis une expérience distincte et versionnée.

Le seul écart de prix de barre hors endpoints concerne le low Nacon du 21 janvier :
**0,4083 € contre 0,40825 €**. Sa taille est compatible avec un arrondi ;
son origine exacte n'est pas certifiée. Les 1 180 opens, highs et closes correspondent.

## 6. Décisions et statut des prochaines étapes

- **Conserver les résultats H1/H2/H3 publiés**, accompagnés de cet audit.
- **Conserver les warnings futurs et les pertes de suspension**, sans les convertir
  en exclusions rétroactives.
- **Prix d'exécution matériels : rapprochement terminé** pour ces 32 portefeuilles.
- **Volumes : revue de définition ouverte** ; aucune correction ponctuelle ni refit.
- **Corporate actions/vintages : certification générale encore ouverte**, en
  particulier pour les autres modèles et les autres périodes.
- **Comparaison H1 à H10 : contrat commun écrit**, inventaire de 22 dates disponible ;
  voir le [contrat de comparaison](SRD_HORIZON_COMPARISON_CONTRACT.md).

## 7. Artefacts et reproduction

Sous `data/analysis/srd-price-audit-v1/` — local, non versionné :

| Fichier | Usage |
| --- | --- |
| `audit.json` | Compteurs, erreurs, checksums des sources et payloads |
| `winner_ledger_audit.parquet` | Les 3 780 lignes de sélection des 32 portefeuilles |
| `material_cases.csv` | 148 cas regroupés et état de rapprochement primaire |
| `material_quote_paths.parquet` | Barres de chaque détention, checksum et ligne du payload ABC |
| `primary_price_comparison.csv` | Comparaisons dédupliquées des cinq champs |
| `primary_field_summary.csv`, `primary_differences.csv` | Compteurs par champ et différences conservées |
| `primary*/euronext_histories.json` et HTML | Requêtes et captures des prix primaires |
| `primary/event_receipts.json`, PDF/HTML émetteurs | Preuves des événements ; les réponses HTTP 202 initiales ne sont pas des preuves de contenu |
| `winner_attribution.csv` | Contributions, concentration, warnings et entrées/sorties anormales |
| `common_cutoffs.json` | Inventaire des grilles H1/H2/H3/H5/H10, sans nouvelle évaluation |

```bash
# Depuis la racine du worktree ; adapter le chemin aux payloads bruts locaux.
uv run python scripts/audit_srd_short_prices.py \
  --raw-root /home/ubuntu/hocus-quant-lab/data/raw/market
```

Le script requiert les expériences et les captures primaires présentes. Pour une
nouvelle capture, utiliser un nouveau dossier afin de préserver le vintage actuel :

```bash
uv run --with playwright python scripts/capture_srd_price_evidence.py \
  --output data/analysis/srd-price-audit-v2/primary

uv run python scripts/audit_srd_short_prices.py \
  --raw-root /home/ubuntu/hocus-quant-lab/data/raw/market \
  --output data/analysis/srd-price-audit-v2

uv run --with playwright python scripts/capture_srd_price_evidence.py \
  --cases data/analysis/srd-price-audit-v2/material_cases.csv \
  --output data/analysis/srd-price-audit-v2/primary-material

# Réexécuter ensuite l'audit vers ce dossier v2 pour intégrer l'extension.
```

Le navigateur Chromium doit être installé pour la capture ; les tables publiques
peuvent évoluer. Les résultats sont une corroboration de prix après coup et un
diagnostic de concentration, **aucune preuve nouvelle d'alpha**.
Les empreintes et URLs exactes sont dans le
[manifeste compagnon](SRD_PRICE_AUDIT.sources.json).
