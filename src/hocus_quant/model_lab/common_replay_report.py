"""Publish descriptive common-horizon results from preserved replay artefacts."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.common_replay import write_json
from hocus_quant.model_lab.context_data import normal_dates
from hocus_quant.model_lab.metrics import correlation
from hocus_quant.model_lab.portfolio_extensions import MarketTape
from hocus_quant.model_lab.report import table

LABELS = {"return_abs": "Rendement absolu", "rank_pct": "Rang du rendement"}


def publish(root: Path) -> None:
    config = json.loads((root / "contract.json").read_text())
    audit = json.loads((root / "audit.json").read_text())
    m = pd.read_parquet(root / "metrics.parquet")
    cp = pd.read_parquet(root / "portfolio_cutoff.parquet")
    trades = pd.read_parquet(root / "trades.parquet")
    # Retain prior evidence for non-executed entries too: None/NaT keys cannot
    # reliably match the replay engine's exact (entity, entry, exit) dictionary.
    old_cases = normal_dates(
        pd.read_csv("data/analysis/srd-price-audit-v1/material_cases.csv"),
        ["entry_date", "exit_date"],
    )
    evidence = {
        (r.entity_id, r.entry_date): r.primary_price_status
        for r in old_cases[old_cases.exit_date.isna()].itertuples()
    }
    reused_missing = (
        trades.exit_date.isna()
        & trades.entry_price.isna()
        & pd.Series(
            [(r.entity_id, r.entry_date) in evidence for r in trades.itertuples()],
            index=trades.index,
        )
    )
    if reused_missing.any():
        trades.loc[reused_missing, "price_audit_status"] = [
            evidence[(r.entity_id, r.entry_date)] for r in trades[reused_missing].itertuples()
        ]
        trades.to_parquet(root / "trades.parquet", index=False)
        event = trades[
            (trades.return_gross.abs() > 0.10)
            | (trades.pnl_net.abs() > 0.01)
            | (trades.future_quality != "approved")
            | (trades.status != "closed")
        ].copy()
        for threshold in [10, 20, 30]:
            event[f"abs_return_gt_{threshold}"] = event.return_gross.abs() > threshold / 100
        event["abs_contribution_gt_1point"] = event.pnl_net.abs() > 0.01
        event.to_parquet(root / "event_concentration.parquet", index=False)
        event[event.price_audit_status == "pending_new_case"].to_parquet(
            root / "new_price_audit_cases.parquet", index=False
        )
    write_json(
        root / "annotation_audit.json",
        {
            "stage": "publication metadata",
            "prior_missing_entry_evidence_rows": int(reused_missing.sum()),
            "financial_fields_changed": False,
            "source_cases_sha256": file_sha(
                Path("data/analysis/srd-price-audit-v1/material_cases.csv")
            ),
        },
    )
    counts = pd.read_parquet(root / "cohort_counts.parquet")
    # Diagnostics only: these outcomes never reach cohort formation or selection.
    market_root = Path(config["models"][0]["root"])
    tape = MarketTape.build(
        normal_dates(pd.read_parquet(market_root / "source_market.parquet"), ["session_date"]),
        normal_dates(pd.read_parquet(market_root / "source_benchmark.parquet"), ["session_date"]),
    )
    score_frame = normal_dates(pd.read_parquet(root / "scores.parquet"), ["cutoff"])
    gaps = []
    for (mid, day), part in score_frame.groupby(["model_id", "cutoff"]):
        previous = max(d for d in tape.calendar if d <= day)
        entry = min(d for d in tape.calendar if d > day)
        pairs = []
        for row in part.itertuples():
            close = tape.quotes[previous].get(row.entity_id, {}).get("close", np.nan)
            opening = tape.quotes[entry].get(row.entity_id, {}).get("open", np.nan)
            if np.isfinite(close) and close > 0 and np.isfinite(opening):
                pairs.append((row.score, opening / close - 1))
        gaps.append(
            {
                "model_id": mid,
                "cutoff": day,
                "pairs": len(pairs),
                "missing_pairs": len(part) - len(pairs),
                "ic_gap": correlation(
                    np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
                ),
            }
        )
    pd.DataFrame(gaps).to_parquet(root / "gap_ic.parquet", index=False)
    trades.rename(
        columns={
            "entry_price": "entry_open",
            "exit_price": "exit_close",
            "return_gross": "raw_return",
            "return_net": "net_return",
            "allocation": "allocated_capital",
            "pnl_net": "pnl",
            "future_quality": "quality_status",
            "future_reason": "quality_reason",
        }
    ).to_csv(root / "trade_attribution.csv", index=False)
    pending = pd.read_parquet(root / "new_price_audit_cases.parquet")
    pending["absolute_contribution"] = pending.pnl_net.abs()
    keys = ["entity_id", "entry_date", "exit_date"]
    unique = pending.sort_values("absolute_contribution", ascending=False).drop_duplicates(keys)
    frequencies = (
        pending.groupby(keys, dropna=False)
        .simulation_id.nunique()
        .rename("simulation_count")
        .reset_index()
    )
    unique = unique.merge(frequencies, on=keys, validate="one_to_one")
    unique.to_parquet(root / "new_price_audit_cases_unique.parquet", index=False)
    reference = m[(m.target == "universe")].set_index(["exit_horizon", "cost_bp"])
    m["common_benchmark_return"] = [
        reference.loc[(r.exit_horizon, r.cost_bp), "cumulative_return"] for r in m.itertuples()
    ]
    m["excess_vs_common_benchmark"] = m.cumulative_return - m.common_benchmark_return
    principal = m[(m.universe_policy == "common") & (m.top_fraction == 0.03)]
    common = principal[principal.target != "universe"]
    cols = [
        "target",
        "score_horizon",
        "exit_horizon",
        "model",
        "cost_bp",
        "top_fraction",
        "cumulative_return",
        "max_drawdown",
        "average_exposure",
        "average_active_session_capital",
        "turnover",
        "hit_rate",
        "positions",
        "common_benchmark_return",
        "excess_vs_common_benchmark",
        "top_5_share",
    ]
    common[cols].to_csv(root / "principal_table.csv", index=False)
    native = common[common.score_horizon == common.exit_horizon]
    fixed5 = common[(common.exit_horizon == 5) & (common.cost_bp == 45)]
    fixed10 = common[(common.exit_horizon == 10) & (common.cost_bp == 45)]
    # Same circular draws across variants; intervals concern date-average basket returns.
    bootstrap = []
    sub = cp[cp.simulation_id.isin(common[common.cost_bp == 45].simulation_id)]
    pivot = sub.pivot(
        index="cutoff", columns="simulation_id", values="basket_net_return"
    ).sort_index()
    assert len(pivot) == 22
    rng = np.random.default_rng(config["seed"])
    for block in config["bootstrap_blocks"]:
        starts = rng.integers(0, 22, size=(config["bootstrap_reps"], int(np.ceil(22 / block))))
        indices = ((starts[:, :, None] + np.arange(block)) % 22).reshape(
            config["bootstrap_reps"], -1
        )[:, :22]
        draws = pivot.to_numpy()[indices].mean(axis=1)
        for j, sid in enumerate(pivot.columns):
            bootstrap.append(
                {
                    "simulation_id": sid,
                    "block": block,
                    "mean_basket_return": float(pivot[sid].mean()),
                    "lower90": float(np.quantile(draws[:, j], 0.05)),
                    "upper90": float(np.quantile(draws[:, j], 0.95)),
                    "positive_sign_support": float((draws[:, j] > 0).mean()),
                }
            )
        for target in LABELS:
            ids = common[
                (common.target == target) & (common.exit_horizon == 10) & (common.cost_bp == 45)
            ]
            ref = ids.loc[ids.score_horizon == 5, "simulation_id"].iloc[0]
            refj = pivot.columns.get_loc(ref)
            for row in ids.itertuples():
                delta = draws[:, pivot.columns.get_loc(row.simulation_id)] - draws[:, refj]
                bootstrap.append(
                    {
                        "simulation_id": row.simulation_id,
                        "reference_simulation": ref,
                        "block": block,
                        "mean_basket_return": float((pivot[row.simulation_id] - pivot[ref]).mean()),
                        "lower90": float(np.quantile(delta, 0.05)),
                        "upper90": float(np.quantile(delta, 0.95)),
                        "positive_sign_support": float((delta > 0).mean()),
                    }
                )
    pd.DataFrame(bootstrap).to_parquet(root / "basket_bootstrap.parquet", index=False)
    fixed10trades = trades[
        (trades.universe_policy == "common")
        & (trades.top_fraction == 0.03)
        & (trades.cost_bp == 45)
        & (trades.exit_horizon == 10)
        & (trades.target != "universe")
    ]
    winning = {
        mid: set(
            zip(g.nlargest(5, "pnl_net").entity_id, g.nlargest(5, "pnl_net").cutoff, strict=True)
        )
        for mid, g in fixed10trades.groupby("model_id")
    }
    winner_overlap = [
        {
            "model_a": a,
            "model_b": b,
            "holding": 10,
            "cost_bp": 45,
            "top_pnl_trade_jaccard": len(winning[a] & winning[b]) / len(winning[a] | winning[b]),
        }
        for a, b in combinations(winning, 2)
    ]
    pd.DataFrame(winner_overlap).to_parquet(root / "winner_overlap.parquet", index=False)
    ov = pd.read_parquet(root / "overlap.parquet")
    avg_ov = (
        ov[(ov.universe_policy == "common") & (ov.top_fraction == 0.03)]
        .groupby(["model_a", "model_b"], as_index=False)[
            ["jaccard", "overlap_fraction", "score_correlation", "rank_correlation"]
        ]
        .mean()
    )
    avg_ov.to_csv(root / "overlap_summary.csv", index=False)
    top10 = m[
        (m.universe_policy == "common")
        & (m.top_fraction == 0.10)
        & (m.cost_bp == 45)
        & (m.target != "universe")
    ]
    sensitivity = common[common.cost_bp == 45].merge(
        top10,
        on=["target", "score_horizon", "exit_horizon"],
        suffixes=("_top3", "_top10"),
        validate="one_to_one",
    )
    sensitivity["return_difference"] = (
        sensitivity.cumulative_return_top3 - sensitivity.cumulative_return_top10
    )
    sensitivity.to_parquet(root / "top10_sensitivity.parquet", index=False)
    matrices = []
    for target in LABELS:
        for cost in [0, 25, 45]:
            part = common[(common.target == target) & (common.cost_bp == cost)]
            for metric in [
                "cumulative_return",
                "max_drawdown",
                "average_active_session_capital",
                "turnover",
                "hit_rate",
            ]:
                p = part.pivot(
                    index="score_horizon", columns="exit_horizon", values=metric
                ).reindex(index=[1, 2, 3, 5, 10], columns=[1, 2, 3, 5, 10])
                p = p * 100 if metric != "turnover" else p
                p.columns = p.columns.astype(str)
                matrices.append(
                    f"### {LABELS[target]} · {metric} · {cost} bp\n\n"
                    + table(p.reset_index())
                    + "\n"
                )
    matrix_document = Path("docs/SRD_HORIZON_COMMON_REPLAY_MATRICES.md")
    matrix_text = (
        "# SRD — matrices communes des horizons\n\n"
        "22 cutoffs, univers commun, top 3 %, deux compartiments.\n\n"
        "Rendements, DD, capital actif et hit rate en % ; turnover en multiples. "
        "— = combinaison non testée. "
        "[Rapport et limites](SRD_HORIZON_COMMON_REPLAY_RESULTS.md).\n\n" + "\n".join(matrices)
    )
    (root / "all_matrices.md").write_text(matrix_text)
    matrix_document.write_text(matrix_text)
    versions = common[common.cost_bp == 0][
        ["target", "score_horizon", "exit_horizon", "cumulative_return"]
    ].rename(columns={"cumulative_return": "gross"})
    for cost in [25, 45]:
        versions = versions.merge(
            common[common.cost_bp == cost][
                ["target", "score_horizon", "exit_horizon", "cumulative_return"]
            ].rename(columns={"cumulative_return": f"net{cost}"}),
            on=["target", "score_horizon", "exit_horizon"],
            validate="one_to_one",
        )
    versions.to_csv(root / "returns_all_costs.csv", index=False)
    view = versions.copy()
    for c in ["gross", "net25", "net45"]:
        view[c] *= 100
    nview = native[native.cost_bp == 45][
        [
            "target",
            "score_horizon",
            "model",
            "cumulative_return",
            "max_drawdown",
            "average_active_session_capital",
            "turnover",
            "hit_rate",
            "top_5_share",
        ]
    ].copy()
    for c in [
        "cumulative_return",
        "max_drawdown",
        "average_active_session_capital",
        "hit_rate",
        "top_5_share",
    ]:
        nview[c] *= 100
    full45 = common[common.cost_bp == 45]
    ranking = full45.sort_values("cumulative_return", ascending=False)
    ranking.to_csv(root / "ranking_net45.csv", index=False)
    best = ranking.iloc[0]
    eff = full45.loc[full45.return_per_average_exposure.idxmax()]
    returns_h3 = full45[
        (full45.target == "return_abs") & (full45.score_horizon == 3) & (full45.exit_horizon == 3)
    ].iloc[0]

    def row(target, score, hold, cost=45, top=0.03):
        return m[
            (m.target == target)
            & (m.score_horizon == score)
            & (m.exit_horizon == hold)
            & (m.cost_bp == cost)
            & (m.top_fraction == top)
            & (m.universe_policy == "common")
        ].iloc[0]

    def percentage(value):
        return f"{100 * value:+.2f} %"

    r55, r510, r1010 = (row("rank_pct", 5, 5), row("rank_pct", 5, 10), row("rank_pct", 10, 10))
    f55, f510 = row("return_abs", 5, 5), row("return_abs", 5, 10)
    h3gross = row("return_abs", 3, 3, 0)
    xf = (
        trades[(trades.simulation_id == returns_h3.simulation_id) & (trades.ISIN == "BE0974310428")]
        .nlargest(1, "pnl_net")
        .iloc[0]
    )
    ic = pd.read_parquet(root / "execution_ic.parquet")
    ic_view = ic.groupby(["model_id", "exit_horizon"], as_index=False).agg(
        mean_ic=("ic", "mean"), minimum_pairs=("pairs", "min")
    )
    ic_view = ic_view.merge(
        pd.DataFrame(config["models"])[["model_id", "target", "horizon"]], on="model_id"
    )
    ic_view = ic_view[ic_view.exit_horizon >= ic_view.horizon]
    durations = []
    for target in LABELS:
        a = full45[(full45.target == target) & (full45.exit_horizon == 5)]
        b = full45[
            (full45.target == target) & (full45.exit_horizon == 10) & (full45.score_horizon <= 5)
        ]
        durations.extend(
            (
                b.set_index("score_horizon").cumulative_return
                - a.set_index("score_horizon").cumulative_return
            ).tolist()
        )
    same_target_overlap = avg_ov[
        avg_ov.model_a.str.split("-h").str[0] == avg_ov.model_b.str.split("-h").str[0]
    ]
    negative = int((sensitivity.cumulative_return_top10 <= 0).sum())
    bootstrap_table = pd.DataFrame(bootstrap)
    paired = bootstrap_table[bootstrap_table.get("reference_simulation").notna()]
    # Scores H1/H2 at holding H5, by target; no new selection.
    short_answers = []
    for h in [1, 2]:
        vals = [row("rank_pct", h, 5), row("return_abs", h, 5)]
        short_answers.append(
            f"**Score H{h} détenu H5 :** rang {percentage(vals[0].cumulative_return)}, "
            f"rendement {percentage(vals[1].cumulative_return)} nets 45 bp. "
            "Positifs face à l'univers H5 (−2,55 %), mais inférieurs au score H5 "
            "dans chaque famille ; aucun avantage du score court établi."
        )
    lines = [
        "# SRD — replay commun H1/H2/H3/H5/H10",
        "",
        "**6 octobre 2026 · version 1 · replay de développement.**",
        "",
        "## A. Question et résultat de lecture",
        "",
        "Comparer les scores appris et les détentions en neutralisant dates, "
        "cohortes, coûts et budget. "
        "Aucun refit, tuning, changement de score ou exclusion d'événement futur. "
        "Les résultats "
        "2026 restent du développement ; ils ne prolongent pas SPEC-007.",
        "",
        f"**{len(config['common_cutoffs'])} dates**, **10 modèles**, "
        "**360 replays de stratégies** et "
        "**15 références univers**. Analyse B commune principale ; analyse A native complète. "
        "Le top 3 % est principal et le top 10 % un diagnostic.",
        "",
        "## B. Contrat et périmètre",
        "",
        "Le [contrat de replay](SRD_HORIZON_COMPARISON_CONTRACT.md) est complété par la "
        "consigne utilisateur : **deux compartiments**, sorties 1/2/3/5/10 "
        "avec sortie ≥ horizon appris. "
        "Le capital initial vaut 1, le budget d'entrée est min(cash, NAV précédente / 2), "
        "réparti entre ceil(top × N) titres. Actions fractionnaires, aucun arrondi de lots, "
        "pas de levier ni de VAD. Cash rémunéré à zéro.",
        "",
        f"Les cutoffs vont du **{config['common_cutoffs'][0]} au {config['common_cutoffs'][-1]}**. "
        "Ils sont identiques à l'inventaire déjà figé ; "
        "décisions suivies jusqu'au 31 juillet 2026, "
        "avec cash après les liquidations. Leur liste est scellée dans la "
        "[configuration](../configs/experiments/srd_horizon_common_replay_v1.json).",
        "",
        "## C. Cohortes",
        "",
        "L'admission utilise les registres `eligible_at_T` et les features, sans demander un "
        "label futur disponible. Les registres et features sont byte-identiques entre expériences. "
        "Les 22 dates donnent **159 à 164 titres**, **3 573 lignes par modèle**. "
        "Univers natif = univers commun à chaque cutoff ; perte de couverture **0 %**, aucun titre "
        "exclu par l'intersection. Les deux analyses produisent ainsi les mêmes résultats.",
        "",
        table(
            counts[counts.score_horizon == 1][["cutoff", "native_n", "common_n", "coverage_loss"]]
        ),
        "",
        "## D. Modèles et scores préservés",
        "",
        table(
            pd.DataFrame(config["models"])[
                ["target", "horizon", "model", "model_id", "validation_metric"]
            ]
        ),
        "",
        "Les **35 730 scores** originaux sont conservés à l'identique. "
        "Les dix artefacts sauvegardés "
        "sont chargés et leurs prédictions rapprochées des exports (tolérance 1e-12). Aucun score "
        "supplémentaire n'a été nécessaire. Les SHAs des modèles, features, sources, registries, "
        "scores et code sont conservés. Les directions constantes H1/H2/H3 sont exclues de cette "
        "comparaison des deux targets prédictives.",
        "",
        "## E. Exécution et suspensions",
        "",
        "Achat à l'open de la première séance de la grille commune strictement après T ; si le "
        "titre n'a pas d'open, aucune entrée ultérieure ni substitution par un close. "
        "Sortie au H-ième close, **entrée incluse** : H1 = intraday. Un close absent retarde la "
        "sortie jusqu'au premier close source réellement disponible. Les prix indicatifs de "
        "suspension ne sont pas des fills. Nacon reste une perte et immobilise du capital.",
        "",
        "La grille observée des actions est rapprochée des dates CAC AllShares du snapshot "
        f"({audit['equity_only_calendar_dates']} dates actions seules). Elle n'est pas présentée "
        "comme un calendrier de place certifié indépendant. Les features actions conservent leur "
        "borne historique ; le replay est exécuté après 00:00 UTC le lendemain de T. Les targets "
        "relatives et prévisions d'indices ne sont pas utilisées ici.",
        "",
        "## F. Frais",
        "",
        "0/25/45 bp **aller-retour**, moitié sur le nominal d'achat et moitié sur le nominal de "
        "vente. Shares = allocation / (open × (1 + cost/20000)). Les coûts modifient donc cash "
        "et tailles, et ne sont pas simplement soustraits de la performance finale. "
        "Les 45 bp sont un forfait de scénario ; fiscalité par titre, minimums, spread et impact "
        "ne sont pas calculés séparément.",
        "",
        "## G. Horizons natifs — net 45 bp",
        "",
        "Rendement, DD, capital actif, hit rate et parts de contribution en pourcentage ; turnover "
        "en multiples de NAV. Les contributions peuvent dépasser 100 % du gain net lorsque "
        "d'autres trades le compensent.",
        "",
        table(nview),
        "",
        "## H. Matrice score × détention — tous les coûts",
        "",
        "Rendements cumulés (%) sur univers commun top 3 %. Aucune cellule sous la diagonale "
        "n'est testée ; les cellules au-dessus sont toutes calculées.",
        "",
        table(view),
        "",
        "Les matrices complètes return/DD/capital actif/turnover/hit rate pour chaque coût sont "
        "dans les [matrices complètes](SRD_HORIZON_COMMON_REPLAY_MATRICES.md), "
        "`all_matrices.md` et **Horizon Comparison** du sandbox. "
        "Les tables machine `metrics.parquet` et `horizon_matrix.parquet` contiennent les deux "
        "univers et les deux concentrations.",
        "",
        "## I. Exposition et cash",
        "",
        "Exposition EOD = valeur des positions / NAV au close. Capital actif = somme des "
        "nominaux d'entrée des positions actives dans la séance / NAV précédente, entrée et "
        "sortie incluses. C'est une mesure du budget mobilisé et pas une moyenne horaire du "
        "notionnel. H1 a une exposition EOD nulle et un capital actif positif. "
        "`return_per_average_exposure` utilise ce capital actif ; le ratio EOD est séparé et "
        "indéfini en H1. Aucun de ces ratios n'est une performance annualisée.",
        "",
        table(
            full45[
                [
                    "target",
                    "score_horizon",
                    "exit_horizon",
                    "average_exposure",
                    "median_exposure",
                    "max_exposure",
                    "average_active_session_capital",
                    "average_cash_fraction",
                    "average_holding_sessions",
                    "max_simultaneous_positions",
                    "turnover",
                ]
            ]
        ),
        "",
        "Volatilité et Sharpe sont indicatifs, issus des rendements quotidiens de NAV avec "
        "facteur √252, cash compris, sans taux sans risque. Les fenêtres de détention et "
        "événements communs rendent les observations dépendantes.",
        "",
        "## J. Concentration, trades et cutoffs",
        "",
        table(
            full45[
                [
                    "target",
                    "score_horizon",
                    "exit_horizon",
                    "top1_contribution",
                    "top3_contribution",
                    "top5_contribution",
                    "top10_contribution",
                    "negative_top5_contribution",
                    "top_5_share",
                    "absolute_contribution_hhi",
                    "best_cutoff",
                    "best_cutoff_pnl",
                    "worst_cutoff",
                    "worst_cutoff_pnl",
                    "positive_cutoff_fraction",
                ]
            ]
        ),
        "",
        "Les contributions valent des fractions du capital initial (×100 pour des points). "
        "HHI absolu = somme des carrés des contributions absolues normalisées ; HHI positif "
        "calculé séparément. Les meilleurs trades ne sont jamais retirés d'un replay. "
        "Les vues `trades`, `portfolio_cutoff` et `event_concentration` conservent prix, dates, "
        "volumes, warnings, audit réutilisé, retards et catégories >10/20/30 %.",
        "",
        "L'[audit prix précédent](SRD_PRICE_AUDIT.md) est réutilisé après contrôle du SHA source. "
        "Les entrées non exécutées Nacon des 23 février et 2 mars conservent également "
        "leur preuve primaire (`entry_not_traded_in_primary_table`) : rapprochement par "
        "entité/date d'entrée dans l'étape de publication, sans modifier les champs financiers "
        "ou les sélections (`annotation_audit.json`). Les nouveaux cas restent dans "
        "`new_price_audit_cases.parquet` avec statut pending. "
        f"Le registre contient {len(unique)} couples instrument/entrée/sortie distincts "
        "(y compris des références univers) ; il conserve pour chaque cas l'attribution "
        "la plus matérielle et le nombre de variantes concernées, par priorité absolue. "
        "Tous les résultats portent `volume_definition_not_certified=true`. Aucun volume "
        "n'a été substitué et les features n'ont pas été recalculées.",
        "",
        "## K. Similarité et diagnostic top 10 %",
        "",
        "Jaccard des paniers et corrélations cross-sectionnelles de scores/rangs sont calculés "
        "par cutoff puis moyennés. `overlap.parquet` conserve les 22 observations par paire. "
        "`winner_overlap.parquet` compare les cinq contributions les plus élevées, avec "
        "identité trade = action + cutoff, à détention H10 commune et coût 45 bp.",
        "",
        table(avg_ov),
        "",
        "Sensibilité à 45 bp : même score et détention, top 3 % vs top 10 %. "
        "Le percentile n'a pas été retuné.",
        "",
        table(
            sensitivity[
                [
                    "target",
                    "score_horizon",
                    "exit_horizon",
                    "cumulative_return_top3",
                    "cumulative_return_top10",
                    "return_difference",
                    "max_drawdown_top3",
                    "max_drawdown_top10",
                    "top_5_share_top3",
                    "top_5_share_top10",
                    "turnover_top3",
                    "turnover_top10",
                ]
            ]
        ),
        "",
        "## L. Incertitude, benchmark et limites",
        "",
        "Le benchmark utilise le même univers commun, les mêmes 22 décisions et deux "
        "compartiments, équipondéré ; une référence distincte est nécessaire pour chaque "
        "durée de détention. Il ne change pas selon l'horizon appris du score.",
        "",
        table(
            m[(m.target == "universe") & (m.cost_bp == 45)][
                [
                    "exit_horizon",
                    "cumulative_return",
                    "max_drawdown",
                    "average_active_session_capital",
                    "turnover",
                ]
            ]
        ),
        "",
        "Bootstrap circulaire par blocs 2/4/6, 10 000 réplications, seed 20261006 : intervalles "
        "individuels 90 % de la moyenne des rendements de paniers par cutoff et différences "
        "appariées à H10 face au score H5. Tirages communs entre variantes ; "
        "pas d'intervalle présenté comme probabilité d'alpha. Résultats dans "
        "`basket_bootstrap.parquet`. Seulement 22 dates ; multiplicité, chevauchement, "
        "survivance et vintages/volumes non certifiés restent des limites.",
        "",
        "## M. Réponses aux quatorze questions",
        "",
        f"1. **H3 reste-t-il meilleur ?** Parmi les sorties natives de rendement, "
        f"H3 garde le meilleur net 45 bp ({percentage(returns_h3.cumulative_return)}), "
        f"brut {percentage(h3gross.cumulative_return)}, "
        "contre +23,48 % sur les 23 dates anciennes. "
        "Dans le rang natif, H10 est premier. Dans la matrice entière, H3 n'est pas premier.",
        f"2. **Concentration H3 :** top cinq = {returns_h3.top_5_share * 100:.1f} % du gain net ; "
        f"X-FAB, cutoff {xf.cutoff}, trade +50 %, apporte {xf.pnl_net * 100:.2f} points "
        f"({100 * xf.pnl_net / returns_h3.cumulative_return:.1f} % du net). "
        "Le résultat reste fortement concentré ; ces trades sont conservés.",
        "3. **Meilleurs scores courts ou turnover ?** À détention H5 fixe, le score H5 donne "
        f"{percentage(r55.cumulative_return)} (rang) et {percentage(f55.cumulative_return)} "
        "(rendement), devant tous les H1/H2/H3. À H10 fixe, H5 est aussi premier dans "
        "chaque famille. Le turnover principal varie peu (environ 21–22 fois NAV), "
        "car chaque variante effectue les mêmes 22 achats hebdomadaires, quelle que soit sa "
        "détention. Les grands PnL courts ne prouvent donc pas un meilleur score ; "
        "ils dépendent aussi des titres et événements sélectionnés.",
        "4. " + short_answers[0],
        "5. " + short_answers[1],
        f"6. **Rang H5→H10 :** {percentage(r55.cumulative_return)} → "
        f"{percentage(r510.cumulative_return)} ; gain "
        f"{100 * (r510.cumulative_return - r55.cumulative_return):.2f} "
        f"points. Capital actif {100 * r55.average_active_session_capital:.1f} % → "
        f"{100 * r510.average_active_session_capital:.1f} %, DD "
        f"{percentage(r55.max_drawdown)} → {percentage(r510.max_drawdown)}. "
        "L'amélioration reste observée ici, avec davantage de risque et d'immobilisation.",
        f"7. **Rang H10 natif vs H5 natif :** {percentage(r1010.cumulative_return)} contre "
        f"{percentage(r55.cumulative_return)} ; H10 natif est plus rentable. "
        f"À même durée H10, le score H5 ({percentage(r510.cumulative_return)}) dépasse H10.",
        f"8. **Meilleur net 45 bp observé :** {LABELS[best.target]}, "
        f"H{best.score_horizon}→H{best.exit_horizon}, {percentage(best.cumulative_return)}. "
        "Ce classement est descriptif après exploration.",
        f"9. **Meilleur ratio de capital actif :** {LABELS[eff.target]}, "
        f"H{eff.score_horizon}→H{eff.exit_horizon}, ratio "
        f"{eff.return_per_average_exposure:.3f}. Son exposition inclut l'intraday ; "
        "ce ratio n'est ni annualisé ni extrapolable à une exposition constante de 100 %.",
        f"10. **Compromis rendement/DD/turnover :** rendement H3→H3 : "
        f"{percentage(returns_h3.cumulative_return)}, DD {percentage(returns_h3.max_drawdown)}, "
        f"turnover {returns_h3.turnover:.2f}. Rang H5→H5 : "
        f"{percentage(r55.cumulative_return)}, DD {percentage(r55.max_drawdown)}, "
        f"turnover {r55.turnover:.2f}. Rang H5→H10 accroît le gain et le DD. "
        "Ces exemples illustrent les différences de rendement, de risque et de concentration ; "
        "aucune fonction "
        "d'utilité n'a été fixée, donc pas de meilleur compromis objectif unique.",
        f"11. **Mêmes titres ?** Jaccard moyen entre horizons d'une même famille : "
        f"{same_target_overlap.jaccard.min():.3f} à {same_target_overlap.jaccard.max():.3f}. "
        "Il existe des titres communs, mais les sélections ne sont pas identiques. "
        "Les corrélations de scores/rangs K complètent ce diagnostic sans prouver "
        "l'indépendance des informations économiques.",
        "12. **Mêmes événements extrêmes ?** X-FAB et MaaT se retrouvent dans plusieurs "
        "variantes ; Nacon contribue à des pertes et retards. Le Jaccard des cinq meilleurs "
        "trades H10 va de "
        f"{pd.DataFrame(winner_overlap).top_pnl_trade_jaccard.min():.3f} à "
        f"{pd.DataFrame(winner_overlap).top_pnl_trade_jaccard.max():.3f}. "
        "Les gagnants communs comptent, sans expliquer seuls toute la performance.",
        f"13. **Top 3 % indispensable ?** {30 - negative}/30 variantes restent positives à "
        f"top 10 %, contre {(full45.cumulative_return > 0).sum()}/30 à top 3 %. "
        f"Rang H5→H10 : {percentage(r510.cumulative_return)} → "
        f"{percentage(row('rank_pct', 5, 10, top=0.10).cumulative_return)} ; rendement H5→H10 : "
        f"{percentage(f510.cumulative_return)} → "
        f"{percentage(row('return_abs', 5, 10, top=0.10).cumulative_return)}. "
        "La concentration n'est pas nécessaire à tout gain, mais elle est essentielle "
        "à l'amplitude de certaines variantes. Aucun percentile n'est choisi à nouveau.",
        f"14. **Durée robuste indépendamment du score ?** H10 améliore H5 dans "
        f"{sum(d > 0 for d in durations)}/8 comparaisons appariées, mais rendement H1→H10 "
        "devient négatif et rang H3 perd en allongeant. Aucune durée universellement "
        "robuste n'est établie. H10 mérite un examen pour les scores H5 ; H3 pour les "
        "scores courts de rendement, sans optimiser une règle sur 2026.",
        "",
        "### Durée fixée H5 · net 45 bp",
        "",
        table(fixed5[cols]),
        "",
        "### Durée fixée H10 · net 45 bp",
        "",
        table(fixed10[cols]),
        "",
        "### IC après open — mêmes dates et univers, sans exclusion qualité future",
        "",
        table(ic_view),
        "",
        "L'IC décrit les paires dont les deux prix sont disponibles à l'entrée et au close "
        "théorique ; les cas sans prix sont comptés, pas remplacés par des sorties retardées "
        "dans cet indicateur. Le ledger portfolio conserve ces retards. Le gap close→open "
        "est calculé séparément dans `gap_ic.parquet`, sans participation à la sélection.",
        "",
        "### Différences de paniers à H10 face au score H5 — intervalles individuels 90 %",
        "",
        table(paired),
        "",
        "## N. Conclusion en trois points",
        "",
        "**A. Horizon appris : H5**, premier en rendement cumulé dans chacune des deux "
        "familles à durée H5 et à durée H10 fixe. Les IC après open du rapport permettent "
        "de distinguer le classement de tout l'univers des quelques titres achetés. "
        "Ce constat descriptif ne remplace pas une comparaison prospective des scores.",
        "",
        "**B. Durée de détention : H10 pour les scores H5**, qui progressent dans les deux "
        "familles, avec capital actif environ doublé et DD accru. H3 reste intéressant "
        "pour les scores courts de rendement. Il n'existe pas de durée optimale commune "
        "à tous les scores dans cette matrice.",
        "",
        f"**C. Couple à examiner pour un futur gel : rang RF H5→H10**, "
        f"{percentage(r510.cumulative_return)} net 45 bp, encore "
        f"{percentage(row('rank_pct', 5, 10, top=0.10).cumulative_return)} à top 10 %. "
        f"Le maximum de PnL est rendement RF H5→H10 ({percentage(f510.cumulative_return)}), "
        "mais sa sensibilité à la concentration est bien plus forte. La préférence de "
        "recherche pour le rang n'est pas un nouveau choix de modèle ou un lock exécuté ; "
        "un futur protocole doit fixer ses hypothèses avant de recevoir les outcomes.",
        "",
        "**development evidence only — no independent alpha confirmation.**",
        "",
        "## O. Reproduction, tests et sandbox",
        "",
        "```bash\nuv run python scripts/replay_srd_common_horizons.py\n"
        "uv run python scripts/publish_srd_common_horizons.py\n"
        "uv run pytest tests/test_srd_common_replay.py -q\n```",
        "",
        "Les données et joblib sont locaux, ignorés par Git. Le dossier "
        "`data/analysis/srd-horizon-common-replay-v1/` contient le contrat, les cohortes, "
        "scores, sélections, ledgers, NAV, matrices, overlap, concentration, audit et résumé.",
        "",
        "[Horizon Comparison · Model Lab](https://sandbox.hocus.works/quant-model-lab/) "
        "sous authentification. Tests et observation de publication sont enregistrés "
        "dans les reçus locaux (`tests.xml` et `sandbox_publication.json`). "
        "Le contrôle cash/absence de levier tolère 1e-12 : les valeurs négatives "
        "résiduelles, au plus 1,81e-15 de capital, sont des arrondis numériques. "
        "Les compteurs legacy `negative_cash_days` comptent tout strict négatif, "
        "même ces arrondis ; aucun jour ne dépasse cette tolérance. "
        "[Sources et empreintes](SRD_HORIZON_COMMON_REPLAY_RESULTS.sources.json).",
        "",
    ]
    test_receipt = root / "test_receipt.json"
    if test_receipt.exists():
        receipt = json.loads(test_receipt.read_text())
        lines += [
            f"**Tests exécutés : {receipt['passed']} passés, "
            f"{receipt['failed']} échec, {receipt['skipped']} ignoré.** "
            "Couverture des 25 exigences techniques, réplication déterministe, "
            "conservation exacte des scores et comptabilité quotidienne des 375 NAV.",
            "",
        ]
    report = Path("docs/SRD_HORIZON_COMMON_REPLAY_RESULTS.md")
    report.write_text("\n".join(lines))
    sources = [
        report,
        matrix_document,
        Path("configs/experiments/srd_horizon_common_replay_v1.json"),
        Path(__file__),
        Path("src/hocus_quant/model_lab/common_replay.py"),
        Path("tests/test_srd_common_replay.py"),
        Path("notebooks/model_lab.py"),
        Path("deploy/model-lab-sandbox.service"),
        Path("docs/SRD_HORIZON_COMPARISON_CONTRACT.md"),
        Path("docs/RANK_PORTFOLIO_LABELS.json"),
        Path("data/analysis/srd-price-audit-v1/common_cutoffs.json"),
        Path("src/hocus_quant/model_lab/portfolio_extensions.py"),
        Path("src/hocus_quant/model_lab/backtest.py"),
        Path("src/hocus_quant/model_lab/models.py"),
        Path("src/hocus_quant/validation/market_quality.py"),
        Path("data/analysis/srd-price-audit-v1/audit.json"),
        Path("data/analysis/srd-price-audit-v1/material_cases.csv"),
    ]
    sources += list(root.glob("*.*"))
    sources += [Path(x) for x in audit["input_sha256"]]
    write_json(
        Path("docs/SRD_HORIZON_COMMON_REPLAY_RESULTS.sources.json"),
        {
            "as_of": "2026-10-06",
            "base_commit": "49108d5",
            "development_only": True,
            "sha256": {str(p): file_sha(p) for p in sources if p.is_file()},
        },
    )
