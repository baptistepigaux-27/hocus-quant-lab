"""Descriptive sector/action reports; selection remains frozen upstream."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.common_replay import write_json
from hocus_quant.model_lab.metrics import correlation
from hocus_quant.model_lab.report import table


def publish(root: Path):
    config = json.loads((root / "contract.json").read_text())
    audit = json.loads((root / "audit.json").read_text())
    m = pd.read_parquet(root / "metrics.parquet")
    trades = pd.read_parquet(root / "trades.parquet")
    bridge = pd.DataFrame(json.loads((root / "industry_bridge.json").read_text()))
    sector_names = bridge.set_index("sector_id").sector_name.to_dict() | {
        "UNMAPPED": "Sans secteur"
    }
    # Link preserved price evidence; annotations never alter selected names, shares or NAV.
    previous = pd.read_parquet(Path(config["common_root"]) / "trades.parquet")
    previous = previous[
        ["entity_id", "entry_date", "exit_date", "price_audit_status"]
    ].drop_duplicates()
    trades = trades.drop(columns=["price_audit_status"], errors="ignore").merge(
        previous, on=["entity_id", "entry_date", "exit_date"], how="left", validate="many_to_one"
    )
    trades["price_audit_status"] = trades.price_audit_status.fillna("pending_new_case")
    trades["sector_name"] = trades.sector_id.map(sector_names)
    trades.to_parquet(root / "trades.parquet", index=False)
    events = trades[
        (trades.return_gross.abs() > 0.10)
        | (trades.pnl_net.abs() > 0.01)
        | (trades.future_quality != "approved")
        | (trades.status != "closed")
    ].copy()
    events.to_parquet(root / "event_concentration.parquet", index=False)
    events[events.price_audit_status == "pending_new_case"].sort_values(
        "pnl_net", key=abs, ascending=False
    ).drop_duplicates(["entity_id", "entry_date", "exit_date"]).to_parquet(
        root / "new_price_audit_cases.parquet", index=False
    )
    # Incremental strategy metrics, at identical fee scenarios.
    delta = []
    for cost, g in m.groupby("cost_bp"):
        for a, b in [("S1", "S0"), ("S1", "S2"), ("S2", "S0")]:
            x = g[g.strategy_id == a].iloc[0]
            y = g[g.strategy_id == b].iloc[0]
            row = {"comparison": a + "-" + b, "cost_bp": cost}
            for c in [
                "cumulative_return",
                "max_drawdown",
                "turnover",
                "average_exposure",
                "average_active_session_capital",
                "average_cash_fraction",
            ]:
                row["delta_" + c] = float(x[c] - y[c])
            delta.append(row)
    differences = pd.DataFrame(delta)
    differences.to_parquet(root / "metric_deltas.parquet", index=False)
    cp = pd.read_parquet(root / "portfolio_cutoff.parquet")
    stability = []
    paired = []
    for cost, g in cp.groupby("cost_bp"):
        p = g.pivot(index="cutoff", columns="strategy_id", values="pnl")
        budgets = g.pivot(index="cutoff", columns="strategy_id", values="basket_return")
        for ref in ["S0", "S2"]:
            d = p.S1 - p[ref]
            stability.append(
                {
                    "reference": ref,
                    "cost_bp": cost,
                    "cutoffs": len(d),
                    "s1_win_fraction": float((d > 0).mean()),
                    "mean_delta_pnl": float(d.mean()),
                    "median_delta_pnl": float(d.median()),
                    "sum_delta_pnl": float(d.sum()),
                    "best_delta": float(d.max()),
                    "worst_delta": float(d.min()),
                }
            )
            paired.extend(
                [
                    {
                        "cutoff": day,
                        "reference": ref,
                        "cost_bp": cost,
                        "delta_pnl": val,
                        "delta_basket_return": budgets.loc[day, "S1"] - budgets.loc[day, ref],
                    }
                    for day, val in d.items()
                ]
            )
    stability = pd.DataFrame(stability)
    paired = pd.DataFrame(paired)
    stability.to_parquet(root / "cutoff_stability_summary.parquet", index=False)
    paired.to_parquet(root / "paired_cutoff_deltas.parquet", index=False)
    # Matched block draws; no probability of alpha, no tuning/selection use.
    rng = np.random.default_rng(config["seed"])
    bootstrap = []
    pairs = paired[paired.cost_bp == 45].pivot(
        index="cutoff", columns="reference", values="delta_basket_return"
    )
    for block in config["bootstrap_blocks"]:
        starts = rng.integers(0, 22, size=(10000, int(np.ceil(22 / block))))
        ix = ((starts[:, :, None] + np.arange(block)) % 22).reshape(10000, -1)[:, :22]
        samples = pairs.to_numpy()[ix].mean(axis=1)
        for j, ref in enumerate(pairs.columns):
            bootstrap.append(
                {
                    "reference": ref,
                    "block": block,
                    "mean_delta_basket": float(pairs[ref].mean()),
                    "lower90": float(np.quantile(samples[:, j], 0.05)),
                    "upper90": float(np.quantile(samples[:, j], 0.95)),
                    "positive_sign_support": float((samples[:, j] > 0).mean()),
                }
            )
    pd.DataFrame(bootstrap).to_parquet(root / "incremental_bootstrap.parquet", index=False)
    conditional = pd.read_parquet(root / "conditional_ic.parquet")
    cis = conditional.groupby("group", as_index=False).agg(
        mean_ic=("ic", "mean"),
        median_ic=("ic", "median"),
        positive_ic_fraction=("ic", lambda x: float((x.dropna() > 0).mean())),
        valid_cutoffs=("ic", "count"),
        total_n=("n", "sum"),
        mean_n=("n", "mean"),
        missing_outcomes=("missing_outcomes", "sum"),
    )
    cis.to_parquet(root / "conditional_ic_summary.parquet", index=False)
    outcomes = pd.read_parquet(root / "sector_outcomes.parquet")
    momentum = pd.read_parquet(root / "sector_scores.parquet")[["cutoff", "sector_id", "momentum"]]
    outcomes = outcomes.drop(columns=["momentum"], errors="ignore").merge(
        momentum, on=["cutoff", "sector_id"], validate="one_to_one"
    )
    sector_metrics = []
    for day, g in outcomes.groupby("cutoff"):
        g = g.copy()
        g["real_rank"] = g.sector_future_return.rank(ascending=False, method="average")
        g["real_top2"] = g.real_rank <= 2
        selected = g[g.selected_model]
        selected_momentum = g[g.selected_momentum]
        valid_momentum = g.dropna(subset=["momentum", "sector_future_return"])
        valid = g.dropna(subset=["model_score", "sector_future_return"])
        sector_metrics.append(
            {
                "cutoff": day,
                "n": len(valid),
                "spearman": correlation(
                    valid.model_score.to_numpy(), valid.sector_future_return.to_numpy()
                )
                if len(valid) >= 5
                else None,
                "momentum_spearman": correlation(
                    valid_momentum.momentum.to_numpy(),
                    valid_momentum.sector_future_return.to_numpy(),
                ),
                "momentum_top2_hit": float(selected_momentum.real_top2.mean()),
                "top2_hit": float(selected.real_top2.mean()),
                "top2_positive_fraction": float((selected.sector_future_return > 0).mean()),
                "top2_real_return": float(selected.sector_future_return.mean()),
                "top2_mean_real_rank": float(selected.real_rank.mean()),
            }
        )
        outcomes.loc[g.index, "real_rank"] = g.real_rank
        outcomes.loc[g.index, "real_top2"] = g.real_top2
    outcomes["sector_name"] = outcomes.sector_id.map(sector_names)
    outcomes.to_parquet(root / "sector_outcomes.parquet", index=False)
    pd.DataFrame(sector_metrics).to_parquet(root / "sector_score_diagnostics.parquet", index=False)
    interaction = pd.read_parquet(root / "interaction_diagnostics.parquet")
    ir = []
    for day, g in interaction.groupby("cutoff"):
        v = g.dropna(subset=["interaction_score", "future_return"])
        ir.append(
            {
                "cutoff": day,
                "n": len(v),
                "action_ic_same_mapped_sample": correlation(
                    v.score.to_numpy(), v.future_return.to_numpy()
                ),
                "interaction_ic": correlation(
                    v.interaction_score.to_numpy(), v.future_return.to_numpy()
                ),
            }
        )
    interaction_summary = pd.DataFrame(ir)
    interaction_summary.to_parquet(root / "interaction_ic.parquet", index=False)
    interaction["action_bin"] = (np.ceil(interaction.action_rank_normalized * 5)).clip(1, 5)
    interaction["sector_bin"] = (np.ceil(interaction.sector_rank_normalized * 5)).clip(1, 5)
    bins = interaction.groupby(["cutoff", "action_bin", "sector_bin"], as_index=False).agg(
        future_return=("future_return", "mean"), n=("future_return", "count")
    )
    bins.groupby(["action_bin", "sector_bin"], as_index=False).agg(
        mean_return=("future_return", "mean"),
        cutoffs=("future_return", "count"),
        pairs=("n", "sum"),
    ).to_parquet(root / "interaction_bins.parquet", index=False)
    overlap = pd.read_parquet(root / "selection_overlap.parquet")
    ovs = overlap.groupby("strategy_id", as_index=False).agg(
        jaccard=("jaccard", "mean"),
        overlap_fraction=("overlap_fraction", "mean"),
        changed_fraction=("basket_changed", "mean"),
        identical_cutoffs=("identical", "sum"),
        mean_substitutions=("substitutions", "mean"),
        mean_removed_score=("mean_removed_action_score", "mean"),
        mean_retained_score=("mean_retained_action_score", "mean"),
        sector_jaccard=("sector_jaccard_model_momentum", "mean"),
    )
    ovs.to_parquet(root / "overlap_summary.parquet", index=False)
    attribution = pd.read_parquet(root / "sector_attribution.parquet")
    attribution["sector_name"] = attribution.sector_id.map(sector_names)
    attribution.to_parquet(root / "sector_attribution.parquet", index=False)
    metrics = m.sort_values(["strategy_id", "cost_bp"])
    metrics.to_csv(root / "principal_table.csv", index=False)
    scores = pd.read_parquet(root / "sector_scores.parquet")
    scores["sector_name"] = scores.sector_id.map(sector_names)
    scores.to_parquet(root / "sector_scores.parquet", index=False)
    cov = pd.read_parquet(root / "coverage.parquet")
    mapping = pd.read_parquet(root / "action_sector_mapping.parquet")
    m45 = m[m.cost_bp == 45].set_index("strategy_id")
    s0, s1, s2 = (m45.loc[k] for k in ["S0", "S1", "S2"])
    maincols = [
        "strategy_id",
        "cost_bp",
        "cumulative_return",
        "max_drawdown",
        "turnover",
        "average_exposure",
        "average_active_session_capital",
        "hit_rate",
        "positions",
        "average_actions_per_basket",
        "average_cash_fraction",
        "positive_cutoff_fraction",
        "best_cutoff",
        "best_cutoff_pnl",
        "worst_cutoff",
        "worst_cutoff_pnl",
        "top_5_share",
    ]

    def pct(x):
        return f"{100 * x:+.2f} %"

    compact = []
    for strategy in ["S0", "S1", "S2"]:
        cost_rows = metrics[metrics.strategy_id == strategy].set_index("cost_bp")
        row = cost_rows.loc[45]
        compact.append(
            {
                "Stratégie": strategy,
                "Brut": pct(cost_rows.loc[0, "cumulative_return"]),
                "Net 25 bp": pct(cost_rows.loc[25, "cumulative_return"]),
                "Net 45 bp": pct(row.cumulative_return),
                "DD 45 bp": pct(row.max_drawdown),
                "Exposition EOD": f"{100 * row.average_exposure:.1f} %",
                "Capital actif": f"{100 * row.average_active_session_capital:.1f} %",
                "Turnover": f"{row.turnover:.2f}",
            }
        )

    tops = attribution[(attribution.strategy_id == "S1") & (attribution.cost_bp == 45)].nlargest(
        2, "pnl"
    )
    topstr = ", ".join(
        f"{r.sector_name} ({r.contribution_points:+.2f} points)" for r in tops.itertuples()
    )
    full = cis.set_index("group")
    ov = ovs.set_index("strategy_id").loc["S1"]
    sectordiag = pd.DataFrame(sector_metrics)
    verdict = (
        "Oui, descriptivement"
        if s1.cumulative_return > s0.cumulative_return
        else "Non sur cette période"
    )
    modelverdict = (
        "supérieur en rendement net observé"
        if s1.cumulative_return > s2.cumulative_return
        else "inférieur en rendement net observé"
    )
    lines = [
        "# SRD — Sector-first + prédiction action",
        "",
        "**6 octobre 2026 · version 1 · développement, sans nouvel entraînement.**",
        "",
        "## A. Hypothèse",
        "",
        "Un gate sectoriel améliore-t-il les cinq actions choisies par le rang RF H5 ? "
        "Comparaison appariée S0/S1/S2 sur les 22 cutoffs du replay commun, sans contexte "
        "ajouté au score action.",
        "",
        "## B. Contrat et mapping",
        "",
        "[Configuration figée](../configs/experiments/srd_sector_action_v1.json), "
        "enregistrée avant lecture des PnL ; calendrier et empreintes y sont explicites.",
        "",
        "Deux secteurs, **cinq actions au total**, H10, deux compartiments, capital 1, "
        "prochain open. "
        "Coûts 0/25/45 bp AR appliqués moitié aux deux nominaux. Sortie H10 entrée incluse ; "
        "absence d’open = cash, absence de close = sortie retardée. "
        "Si moins de cinq actions : chaque action reçoit 1/5 du budget, les slots vides "
        "restent cash. "
        "Aucun troisième secteur, levier, short, complément ou exclusion selon outcome.",
        "",
        "L’ancien projet ne possédait **aucun mapping action/secteur** : les 356 contextes étaient "
        "globaux. La présente expérience capture les industries "
        "[ABC Bourse](https://www.abcbourse.com/marches/secteurs), réutilise les **onze "
        "industries CAC** "
        "déjà présentes et leur pont vers les codes d’indices. Les super-secteurs STOXX, SOX et "
        "Biotechnology se chevauchent et ne sont pas ajoutés à cette partition. Cette règle de "
        "scope a été fixée avant les PnL ; le RF sectoriel lui-même reste entraîné sur son "
        "corpus original.",
        "",
        f"Mapping actuel : **{mapping.sector_id.notna().sum()}/{len(mapping)} actions** de "
        f"l’union commune. "
        "Identité ISIN vérifiée sur les fiches publiques et rattachement par ticker à une seule "
        "industrie ; captures, sources et SHAs conservés. Airbus et Stellantis avaient une "
        "cotation canonique étrangère ; le lien parisien a été vérifié avec le même ISIN, "
        "avant la lecture des performances. Le premier mapping de 162 correspondances et "
        "ses replays techniques sont archivés localement ; le résultat publié utilise 164. "
        "Le référentiel est projeté sur 2026, "
        "**sans preuve PIT historique**. Aucun changement historique n’est certifié. Les titres "
        "sans mapping restent dans S0 et l’univers, mais ne passent pas les gates S1/S2.",
        "",
        table(bridge[["industry_code", "sector_code", "sector_name", "member_count"]]),
        "",
        "`member_count` décrit les tables ABC sources, tous titres confondus. "
        "Les effectifs du seul univers SRD commun figurent par cutoff ci-dessous.",
        "",
        table(cov),
        "",
        "Actions sans rattachement :",
        "",
        table(mapping[mapping.sector_id.isna()][["ISIN", "instrument", "missing_reason"]]),
        "",
        "## C. Score secteur et score action",
        "",
        f"Secteur : **`{config['sector_model']['model_id']}`**, RF H10, target "
        f"`{config['sector_model']['target_id']}`. Sélection de validation 2025 : IC "
        f"{config['sector_model']['validation_metric']:.5f}, déjà figée. Aucun alternatif choisi. "
        "Le score est un rang futur prédit, pas une prévision de rendement en %.",
        "",
        f"Action : **`{config['action_model']['model_id']}`**, target "
        f"`future.rank_pct.h5.family.v1`. "
        "Les 3 573 scores du replay commun sont conservés exactement. Les features sont les "
        "1 048 entrées originelles dans chaque moteur, avec masques indices historiques.",
        "",
        "Train 2024, choix sur S1 2025, fit final 2024+S1 2025 ; aucun label au-delà de la "
        "borne de retrain. Les prédictions sectorielles sont reproduites depuis le modèle "
        f"sauvegardé, erreur max {audit['sector_score_replay_error']:.2e}. "
        "Le contrat versionné conserve les IDs, périodes exactes, fingerprints, SHAs du code "
        "original et des modèles ; `sector_model_metadata.json` conserve les 1 048 IDs de "
        "features.",
        "",
        "Disponibilité modélisée des scores : minuit UTC D+1, avant l’open. Le mapping actuel "
        "constitue une exception documentaire explicite : il ne devient pas une information "
        "certifiée disponible à T par rétrodatation.",
        "",
        "## D. Baselines et équivalence des gates",
        "",
        "S0 = cinq meilleurs scores actions dans l’univers commun, exactement la référence "
        "rang H5→H10. S1 = top deux industries par RF existant puis top cinq actions. "
        "S2 = top deux industries par momentum passé **C(T)/C(T−20)−1**, observations "
        "natives disponibles à T, quote âgée au plus de trois jours, puis même top cinq actions.",
        "",
        "**S1 et Action-first avec gate sont identiques** : filtrer un classement total conserve "
        "l’ordre de son sous-ensemble. Les égalités sont départagées par ID dans les deux "
        "variantes. "
        "Égalité vérifiée sur les 22 paniers ; aucun S1b supplémentaire.",
        "",
        "Le moteur commun accepte désormais `allocation_slots=5` pour garder cash les slots "
        "absents ; son comportement par défaut est conservé. Les trois S0 reproduisent "
        "exactement les rendements, drawdowns, turnover et exposition du replay de référence.",
        "",
        "## E. Résultats brut / 25 / 45 bp",
        "",
        table(pd.DataFrame(compact)),
        "",
        "### Détail des neuf simulations",
        "",
        "Valeurs de rendement/exposition/hit rate/cash en fractions (×100 pour %) ; turnover "
        "en multiples de NAV ; PnL cutoff en fractions du capital initial. Rendements cumulés, "
        "non annualisés, suivis jusqu’au 31 juillet.",
        "",
        table(metrics[maincols]),
        "",
        "### Valeur incrémentale : mêmes coûts",
        "",
        table(differences),
        "",
        "## F. Drawdown, exposition et stabilité par cutoff",
        "",
        "Le capital actif inclut entrée et sortie pendant la séance. La valeur EOD/cash "
        "vient des mêmes parts et marks que la NAV. Les périodes et le budget sont identiques, "
        "mais des paniers incomplets ou des retards peuvent modifier l’exposition.",
        "",
        table(stability),
        "",
        "Les deltas ci-dessus attribuent des points de NAV par décision : les budgets "
        "capitalisés peuvent diverger. Les rendements de panier et leurs différences appariées "
        "sont séparés dans `paired_cutoff_deltas.parquet`.",
        "",
        "Intervalles individuels 90 % par bootstrap circulaire partagé, 10 000 tirages, seed "
        "20261006, blocs 2/4/6 sur les 22 dates, **deltas de rendement de panier**, pas une "
        "simulation d’une nouvelle NAV. Pas de contrôle de multiplicité ni confirmation "
        "indépendante.",
        "",
        table(pd.DataFrame(bootstrap)),
        "",
        "## G. Selection overlap",
        "",
        table(ovs),
        "",
        "Le modèle ne fournit que dix scores d'industrie par date : CAC Biens de consommation "
        "est `review` dans son éligibilité passée, donc son score reste absent aux 22 cutoffs. "
        "Le momentum W20 y est calculable et appartient à son scope de onze industries ; "
        "il choisit cette industrie au cutoff du 12 juin. Cette différence de disponibilité "
        "est conservée et limite l'attribution de S1−S2 à la seule qualité du RF. "
        "Aucun score n'a été inventé et aucune date n'a été retirée. "
        "Les scores conservés/supprimés sont moyennés par cutoff. Les fichiers `selections`, "
        "`rejections` et `coverage` conservent les deux secteurs, scores, actions ajoutées "
        "et rejetées ; une absence de mapping/score est explicite, aucun cutoff supprimé.",
        "",
        "## H. Attribution sectorielle",
        "",
        "PnL = fractions du capital initial ; contribution en points ; poids moyen = "
        "valeur du secteur au close / NAV, cash et jours sans position compris. Les trades "
        "sans mapping S0 sont attribués à `UNMAPPED`.",
        "",
        table(
            attribution[attribution.cost_bp == 45][
                [
                    "strategy_id",
                    "sector_name",
                    "pnl",
                    "contribution_points",
                    "average_weight",
                    "trades",
                    "hit_rate",
                ]
            ]
        ),
        "",
        "## I. Conditional IC et première couche sectorielle",
        "",
        table(cis),
        "",
        "IC = Spearman entre score action préservé et rendement réellement calculable "
        "open→H10 théorique, minimum cinq couples non constants. Les sorties retardées "
        "restent au portefeuille ; les endpoints manquants sont comptés dans cet IC. "
        "La coupe « autres » comprend les autres secteurs mappés ; `unmapped` est séparé. "
        "Ces groupes peuvent être petits et ont une dispersion propre.",
        "",
        f"Couche secteurs, onze candidats : IC moyen {sectordiag.spearman.mean():+.4f}, "
        f"médiane {sectordiag.spearman.median():+.4f}, hit top2 "
        f"{100 * sectordiag.top2_hit.mean():.1f} %. Hit top2 = part des deux choix réellement "
        "dans les deux premières industries futures ; il diffère de la part de rendements "
        "positifs. "
        "Outcomes close-à-close H10 alignés sur le calendrier commun, quotes as-of âge ≤3 jours, "
        "indices descriptifs sans exécution négociable. "
        f"Momentum : IC sectoriel moyen {sectordiag.momentum_spearman.mean():+.4f}, "
        f"hit top2 {100 * sectordiag.momentum_top2_hit.mean():.1f} %. "
        "Le résultat publié 0,1583 sur le panel "
        "sectoriel complet ne s’applique pas automatiquement à ce sous-ensemble CAC.",
        "",
        table(pd.DataFrame(sector_metrics)),
        "",
        "### Interaction, diagnostic uniquement",
        "",
        "Produit du rang percentile du score action et du rang percentile du score secteur. "
        "Aucun entraînement et aucune sélection de portefeuille sur ce produit. Comparaison "
        "à l’action seule sur le même sous-échantillon mappé et scoré :",
        "",
        table(interaction_summary),
        "",
        f"IC moyen du produit : {interaction_summary.interaction_ic.mean():+.5f} ; "
        f"action seule sur les mêmes paires : "
        f"{interaction_summary.action_ic_same_mapped_sample.mean():+.5f}. "
        "Le produit ne montre pas de gain moyen avec ce diagnostic. "
        "Les 25 cellules action×secteur (quintiles) sont dans `interaction_bins.parquet` ; "
        "moyenne des moyennes par date, N et couverture conservés. L’effet monotone ou "
        "incrémental n’est pas présupposé par cette construction multiplicative.",
        "",
        "## J. Concentration et événements",
        "",
        table(
            m[m.cost_bp == 45][
                [
                    "strategy_id",
                    "top1_contribution",
                    "top3_contribution",
                    "top5_contribution",
                    "top10_contribution",
                    "top_5_share",
                    "absolute_contribution_hhi",
                    "top_sector_contribution",
                    "top2_sector_contribution",
                ]
            ]
        ),
        "",
        "Tous les événements restent inclus. Les preuves prix sont réutilisées quand "
        "instrument/entrée/sortie concordent avec les replays déjà audités ; les nouveaux "
        "cas ont un registre séparé pending. Aucun volume n’a été remplacé.",
        "",
        "## K. Limites et réponses aux dix questions",
        "",
        f"1. **Gate et net 45 bp : {verdict}.** S1 {pct(s1.cumulative_return)}, "
        f"S0 {pct(s0.cumulative_return)} ; delta "
        f"{100 * (s1.cumulative_return - s0.cumulative_return):+.2f} points.",
        f"2. **Drawdown :** S1 {pct(s1.max_drawdown)}, S0 {pct(s0.max_drawdown)} ; "
        + ("moins sévère." if s1.max_drawdown > s0.max_drawdown else "plus sévère ou égal."),
        f"3. **Turnover :** S1 {s1.turnover:.2f}, S0 {s0.turnover:.2f} fois NAV ; "
        f"delta {s1.turnover - s0.turnover:+.2f}.",
        f"4. **Paniers réellement changés :** {100 * ov.changed_fraction:.1f} % des dates, "
        f"{ov.mean_substitutions:.2f} substitutions en moyenne, Jaccard {ov.jaccard:.3f}.",
        f"5. **Modèle vs momentum :** S1 {pct(s1.cumulative_return)}, S2 "
        f"{pct(s2.cumulative_return)} ; "
        f"modèle {modelverdict}. Pas de preuve indépendante de supériorité.",
        f"6. **IC action conditionnel :** top2 {full.loc['top2_model', 'mean_ic']:+.4f}, "
        f"univers {full.loc['full', 'mean_ic']:+.4f}, autres secteurs "
        f"{full.loc['other_mapped_sectors', 'mean_ic']:+.4f}. "
        "Composition et petits N empêchent une lecture causale simple.",
        f"7. **Concentration :** cinq meilleurs trades = {100 * s1.top_5_share:.1f} % du gain "
        f"net S1 ; "
        f"deux meilleurs secteurs = {100 * s1.top2_sector_contribution:+.2f} points. "
        "Les parts peuvent dépasser 100 % avec compensation par pertes.",
        f"8. **Secteurs contributeurs principaux S1 :** {topstr}.",
        f"9. **Résistance aux 45 bp :** S1 {pct(s1.cumulative_return)} après le forfait ; "
        "fiscalité par titre, minimums, spread et impact non certifiés.",
        "10. **Gel prospectif : non exécuté.** "
        + (
            "La variante mérite une confirmation séparée seulement après examen du mapping et "
            "des concentrations. "
            if s1.cumulative_return > s0.cumulative_return
            and s1.cumulative_return > s2.cumulative_return
            else "Ce replay ne justifie pas de privilégier la variante face aux deux références. "
        )
        + "Le mapping actuel devra être capturé à l’avance pour une vraie phase prospective.",
        "",
        "La source de prix reste reconstruite, corporate actions/vintages et volumes incomplets. "
        "2024–2026 ont été explorés ; les choix de gate n’en font pas une nouvelle période "
        "indépendante. "
        "Le mapping sectoriel actuel est une limite supplémentaire, sans rétrodatation de sa "
        "capture. "
        "SPEC-007, les deux modèles et leurs scores restent inchangés.",
        "",
        "## L. Reproduction, tests et sandbox",
        "",
        "```bash\n# Capture actuelle seulement ; conserver ses vintages pour reproduire\n"
        "uv run --with beautifulsoup4 python scripts/capture_srd_sector_mapping.py\n"
        "uv run python scripts/replay_srd_sector_action.py\n"
        "uv run python scripts/publish_srd_sector_action.py\n"
        "uv run pytest tests/test_srd_sector_action.py tests/test_srd_common_replay.py -q\n```",
        "",
        "[Sector + Action · Model Lab](https://sandbox.hocus.works/quant-model-lab/), sous "
        "authentification. "
        "Filtres de consultation, aucune modification du top cinq scientifique. "
        "Les captures et données sont locales, non versionnées ; contrat/config/code/docs et "
        "[empreintes](SRD_SECTOR_ACTION_RESULTS.sources.json) sont dans Git.",
        "",
        "### A. Valeur du filtre secteur",
        "",
        verdict + " pour le gate RF S1. Le gate momentum S2 donne "
        + f"{pct(s2.cumulative_return)} contre {pct(s0.cumulative_return)} pour S0, "
        + f"soit {100 * (s2.cumulative_return - s0.cumulative_return):+.2f} points : "
        + "un résultat descriptif positif pour cette règle, sans confirmation indépendante.",
        "",
        "### B. Valeur du modèle secteur",
        "",
        modelverdict.capitalize() + " face au momentum W20, descriptivement.",
        "",
        "### C. Décision",
        "",
        "Ne pas geler S1 sur la base de ce résultat. S2 peut servir une hypothèse distincte, "
        "après examen de sa concentration et des différences de couverture. "
        "Aucun gel automatique : la confirmation demanderait un protocole distinct et un mapping "
        "observé à chaque décision. Les résultats actuels servent au développement.",
        "",
        "**development evidence only — no independent alpha confirmation.**",
        "",
    ]
    receipt = root / "test_receipt.json"
    if receipt.exists():
        rr = json.loads(receipt.read_text())
        lines += [
            "",
            f"**Tests : {rr['passed']} passés, {rr['failed']} échec, {rr['skipped']} ignoré.**",
        ]
    doc = Path("docs/SRD_SECTOR_ACTION_RESULTS.md")
    doc.write_text("\n".join(lines))
    sources = [
        doc,
        Path("configs/experiments/srd_sector_action_v1.json"),
        Path("src/hocus_quant/model_lab/sector_action.py"),
        Path("src/hocus_quant/model_lab/sector_action_report.py"),
        Path("src/hocus_quant/model_lab/portfolio_extensions.py"),
        Path("tests/test_srd_sector_action.py"),
        Path("scripts/capture_srd_sector_mapping.py"),
        Path("scripts/replay_srd_sector_action.py"),
        Path("scripts/publish_srd_sector_action.py"),
        Path("notebooks/model_lab.py"),
        Path("deploy/model-lab-sandbox.service"),
    ]
    sources += list(root.glob("*.*")) + [Path(p) for p in audit["input_sha256"]]
    write_json(
        Path("docs/SRD_SECTOR_ACTION_RESULTS.sources.json"),
        {
            "as_of": "2026-10-06",
            "base_commit": config["base_commit"],
            "development_only": True,
            "sha256": {str(p): file_sha(p) for p in sources if p.is_file()},
            "raw_mapping_manifest": "data/analysis/srd-sector-action-v1/mapping_manifest.json",
        },
    )
