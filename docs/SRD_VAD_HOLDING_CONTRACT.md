# SRD sans contexte — VAD et détention prolongée

**6 octobre 2026 · contrat fixé avant lecture des résultats.**

## Modèles et décisions

Réutiliser les **56 modèles du registre complet de 1 048 variables d'action**,
leurs scores test S1 2026 et leurs **12 gagnants sélectionnés sur S1 2025**.
Aucun contexte de marché, nouveau fit, changement de target ou nouvelle sélection
sur les performances 2026. Les résultats publiés concernent les mêmes décisions
que les simulations top 3 % précédentes, sur le corpus ABC SRD livré.

| Horizon de la target du modèle | Détention initiale | Détention prolongée |
| --- | ---: | ---: |
| H5 | 5 séances | 10 séances |
| H10 | 10 séances | 20 séances |

La target et les scores restent identiques : une détention H20 n'est pas un modèle
entraîné pour H20. Les cutoffs sont identiques au sein de chaque paire de détentions.
Les modèles H5 disposent de 23 dates, les H10 de 22 dates dans les exports sauvegardés.

## Sélection et capital

- **Long-only de référence :** top 3 %, capital disponible affecté aux achats.
- **Long/short demandé :** top 3 % acheté et flop 3 % vendu à découvert ;
  **50 % achat / 50 % VAD**, exposition brute nominale 100 %, sans levier.
- Une sélection retient `ceil(0.03 × nombre de scores finis)` titres par jambe,
  équipondérés. Un tri unique score décroissant puis ISIN croissant détermine
  le top et la fin du classement. Les jambes restent disjointes, y compris avec
  des ex æquo. Les scores constants donnent un classement arbitraire explicitement
  signalé ; le naïf direction H10 n'a pas de discrimination prédictive.
- Compartiments fixes par **détention**, 2 pour H5, 3 pour H10 et 5 pour H20,
  afin de financer les positions hebdomadaires qui se chevauchent. Chaque nouvelle
  date reçoit au plus `NAV précédente / nombre de compartiments`, dans la limite
  du cash libre. Les budgets et frais sont réévalués dans chaque replay.
- Les produits de vente à découvert sont bloqués avec une garantie égale au
  nominal initial du short ; ils ne financent aucune position supplémentaire.
  La part réservée à la VAD représente donc du capital immobilisé.

L'exposition brute effectivement investie est inférieure à 100 % quand des
compartiments sont libres. Elle peut varier après mouvements de prix. Les
détentions et leur nombre de compartiments modifient aussi le temps investi :
rendements, drawdown, exposition moyenne et turnover seront présentés ensemble.
50/50 est une égalité des budgets à l'ouverture, pas une neutralité de bêta garantie.

## Prix, sorties et dates

Entrée au prochain open du calendrier commun et sortie au H-ième close commun,
avec H égal à la détention. Les prix historiques source sont conservés. Un open
absent ne produit pas de fill ; une sortie absente attend le premier close réel
suivant et reste signalée. Un prix ancien utilisé pour valoriser une position est
signalé comme stale. Une anomalie future est annotée, sans retirer une sélection.

La comparaison utilise une clôture commune au **31 juillet 2026**, après les
dernières sorties H20. Les décisions restent celles de S1 2026 ; les liquidations
prolongées peuvent avoir lieu en juillet. Les portefeuilles initiaux liquides fin
juin restent en cash ensuite. Les rendements ne sont pas annualisés dans la synthèse.
Les replays long-only H5/H10 sont réconciliés aux ledgers 25/45 bp existants au 30 juin.

## Comptabilité et frais de VAD

Capital initial = 1. Pour une allocation A par position et un taux de frais par
transaction f = coût aller-retour / 2, le nominal initial est `N = A/(1+f)`.
Les quantités sont `q = N/prix d'entrée` sur les deux jambes.

```text
Valeur long  = q × prix courant
Valeur short = garantie N + produit bloqué N − q × prix courant
NAV = cash libre + valeurs des longs + valeurs des shorts
PnL brut long  = q × (prix sortie − prix entrée)
PnL brut short = q × (prix entrée − prix sortie)
PnL net = PnL brut − frais d'entrée − frais de sortie − frais d'emprunt
```

Deux forfaits de transaction, **25 et 45 bp aller-retour**, appliqués moitié à
l'ouverture et moitié à la fermeture de chaque position, achat ou short.
Ils conservent les conventions de la phase précédente : pas de fiscalité par
instrument, minimum par ordre ou spread observé.

Coût d'emprunt des titres : sensibilités **0 % et 3 % annuel**, distinctes des
25/45 bp. **3 % est une hypothèse de simulation, pas un tarif observé.** Les frais
s'accumulent sur le nominal short valorisé au dernier close connu, en jours
calendaires/365 ; le jour d'entrée débute la période, le rachat la termine.
Le coût d'un week-end est donc pris en compte. Cash non rémunéré.
Les compartiments sont suivis séparément, sans netting des positions opposées
d'un même titre entre vintages ; les journées concernées sont comptées. Le coût
d'emprunt est appliqué aux shorts de chaque compartiment.

Les tarifs et disponibilités historiques de prêt, rappels de titres, dividendes
dus par le vendeur à découvert et appels de marge ne sont pas disponibles dans
le corpus. La VAD est donc théorique ; son éligibilité historique n'est pas
certifiée par la livraison SRD actuelle. Un cash ou NAV négatif est signalé,
sans liquidation de marge fictive ni suppression du titre perdant.

## Livrables et statut

Ledgers de positions, courbes quotidiennes, sélections top/flop, contributions par
jambe et action, comparaisons des 12 gagnants et résultats des 56 modèles dans
`data/analysis/srd-portfolio-extensions-v1/`, ignoré par Git. Config, scripts,
contrat, rapport et checksums versionnés. Publication Marimo en lecture seule.
Aucun modèle d'indice ou de contexte n'est utilisé.

Les périodes ont déjà été explorées. Prix raw, corporate actions, dividendes et
composition historique d'univers restent incomplets. Ces replays sont du
développement rétrospectif, sans confirmation indépendante.
