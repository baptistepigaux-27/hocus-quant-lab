# SPEC-006T — audit de recherche ex ante

**Statut : candidate lock ready for independent confirmation**

2024–2026 sont des périodes de développement. Confirmation indépendante en attente.

## Cohortes (sommes de lignes entité/cutoff, pas titres uniques)

| Année | Dates | Éligibles à T | Observables | IC ex ante | Future clean | Ininterprétables |
|---|---:|---:|---:|---:|---:|---:|
| 2024 | 27 | 4918 | 4918 | 4918 | 4914 | 0 |
| 2025 | 27 | 4589 | 4589 | 4587 | 4583 | 2 |
| 2026 | 27 | 4304 | 3988 | 3988 | 3984 | 0 |

## Sensibilité au filtre futur

| Année | Moyenne abs Δ IC vs legacy | Maximum abs Δ | Signes moyens changés |
|---|---:|---:|---:|
| 2024 | 0.001180 | 0.008751 | 25 |
| 2025 | 0.001083 | 0.002497 | 2 |
| 2026 | 0.000301 | 0.001380 | 1 |

## Déduplication et candidats

- Signatures discovery uniques : 937.
- Duplicats de rang regroupés : 105.
- Cohortes imbriquées : {'broad_candidates': 504, 'strong_sign_candidates': 138, 'strict_candidates': 85}.

## Régimes descriptifs (information passée seulement)

| Année | Retour marché 20 séances | Volatilité | Dispersion | Breadth | Trend 60 | Dates haussières |
|---|---:|---:|---:|---:|---:|---:|
| 2024 | -0.0131 | 0.1374 | 0.0883 | 0.4789 | -0.0165 | 9 |
| 2025 | -0.0062 | 0.1601 | 0.0907 | 0.5048 | -0.0099 | 12 |
| 2026 | 0.0001 | 0.1452 | 0.0809 | 0.4856 | -0.0007 | 13 |

Ces états décrivent le contexte ; ils ne prouvent pas la cause des inversions.
Les moyennes de régime ne sont pas des rendements annuels.

## Limites

- Reconstructed PIT and delivered SRD universe
- Hard future source errors excluded from numerical IC, never from frozen cohort
- Pointwise bootstrap, no multiple-comparison correction
- Development periods reused; lock is exploratory, not confirmation or alpha
- Current close_T target is not an executable next_open strategy

Lock SHA256 : `7508b6900e36c11757bd84d82c1a9f7d322a07db6ce4ff00e961e5a258432e0f`
