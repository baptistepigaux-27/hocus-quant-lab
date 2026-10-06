"""Frozen short forecasts, independent quote audits and paired execution replays."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.stats import rankdata

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_data import normal_dates
from hocus_quant.model_lab.metrics import correlation
from hocus_quant.model_lab.models import predict_score
from hocus_quant.model_lab.portfolio_extensions import MarketTape, picks, simulate_signed
from hocus_quant.model_lab.report import table

LABELS = {
    "direction_abs": "Direction absolue",
    "direction_rel": "Direction relative",
    "return_abs": "Rendement absolu",
    "rank_pct": "Rang du rendement",
    "excursion_balance": "Équilibre des excursions",
    "trend_tstat": "Tendance / erreur-type",
}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def audit_dataset(output: Path, parent: Path, tape: MarketTape) -> dict[str, Any]:
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    for name, sha in manifest["source_sha256"].items():
        assert file_sha(output / name) == sha
    for name in ["features", "eligibility", "source_market", "source_benchmark"]:
        assert file_sha(output / f"{name}.parquet") == file_sha(parent / f"{name}.parquet")
    targets = normal_dates(pd.read_parquet(output / "targets.parquet"), ["cutoff", "target_end"])
    calendar = tape.calendar
    count, error = 0, 0.0
    for row in targets.itertuples(index=False):
        assert row.reference_quote_date <= row.cutoff
        assert tape.quotes[row.reference_quote_date][row.entity_id]["close"] == row.reference_close
        days = calendar[np.searchsorted(calendar, row.cutoff, side="right") :][: row.horizon]
        assert len(days) == row.horizon and days[-1] == row.target_end
        prices = [tape.quotes[d].get(row.entity_id, {}).get("close", np.nan) for d in days]
        if not np.isfinite(prices).all() or min(prices) <= 0:
            assert pd.isna(row.candidate_return_abs)
            continue
        returns = np.asarray(prices) / row.reference_close - 1
        delta = abs(returns[-1] - row.candidate_return_abs)
        error = max(error, float(delta))
        assert delta < 1e-12
        assert row.candidate_direction_abs == np.sign(returns[-1])
        assert abs(row.candidate_excursion_balance - (returns.max() + returns.min())) < 1e-12
        if row.horizon < 3:
            assert pd.isna(row.trend_tstat) and pd.isna(row.candidate_trend_tstat)
        if row.horizon == 1:
            assert abs(row.candidate_excursion_balance - 2 * row.candidate_return_abs) < 1e-12
        if row.horizon == 3:
            b = 100 * np.asarray(prices) / prices[0]
            slope = (b[2] - b[0]) / 2
            se = abs(b[0] - 2 * b[1] + b[2]) / np.sqrt(12)
            tolerance = 1e-12 * max(1.0, float(np.max(np.abs(b))))
            expected = (
                0.0
                if np.ptp(b) <= tolerance
                else np.copysign(1e6, slope)
                if se <= tolerance
                else np.clip(slope / se, -1e6, 1e6)
            )
            assert np.isclose(row.candidate_trend_tstat, expected, rtol=1e-7, atol=1e-7)
        benchmark_day = max(d for d in tape.benchmark if d <= row.cutoff)
        if days[-1] in tape.benchmark:
            br = tape.benchmark[days[-1]]["close"] / tape.benchmark[benchmark_day]["close"] - 1
            assert row.candidate_direction_rel == np.sign(returns[-1] - br)
        else:
            assert pd.isna(row.candidate_direction_rel)
        count += 1
    for _, part in targets.groupby(["cutoff", "horizon"]):
        valid = part.interpretable & (part.purge_reason == "accepted")
        values = part.loc[valid, "return_abs"].to_numpy()
        assert np.allclose(part.loc[valid, "rank_pct"], rankdata(values) / len(values))
    for split, end in [
        ("train", date(2024, 12, 31)),
        ("validation", date(2025, 6, 30)),
        ("test", date(2026, 6, 30)),
    ]:
        part = targets[(targets.split == split) & targets.return_abs.notna()]
        assert (part.target_end <= end).all()
    receipt = {
        "target_rows": len(targets),
        "quote_paths_recalculated": count,
        "max_return_error": error,
        "parent_features_and_sources_byte_identical": True,
        "reference_closes_match_source_quotes": True,
        "undefined_trend_h1_h2_is_null": True,
        "h1_excursion_equals_twice_return": True,
        "h3_trend_closed_form_recalculated": True,
        "benchmark_direction_and_cross_section_ranks_recalculated": True,
        "label_ends_respect_split_boundaries": True,
    }
    write_json(output / "dataset_audit.json", receipt)
    return receipt


def replay_models(output: Path, registry: list[dict], predictions: pd.DataFrame) -> dict:
    features = normal_dates(pd.read_parquet(output / "features.parquet"), ["cutoff"])
    maximum, rows = 0.0, 0
    for n, entry in enumerate(registry, 1):
        path = output / "models" / f"{entry['model_id']}.joblib"
        assert file_sha(path) == entry["model_sha256"]
        artifact = joblib.load(path)
        part = predictions[predictions.model_id == entry["model_id"]]
        matrix = part[["cutoff", "entity_id"]].merge(
            features, on=["cutoff", "entity_id"], validate="one_to_one", sort=False
        )
        values = predict_score(
            artifact["estimator"],
            matrix[entry["feature_ids"]].to_numpy(float),
            artifact["classification"],
        )
        delta = float(np.abs(values - part.score.to_numpy()).max())
        assert np.allclose(values, part.score, rtol=1e-12, atol=1e-12), entry["model_id"]
        maximum, rows = max(maximum, delta), rows + len(part)
        if n % 16 == 0:
            print(f"SHORT MODEL REPLAY {n}/{len(registry)}", flush=True)
    receipt = {
        "models_replayed": len(registry),
        "score_rows": rows,
        "max_absolute_score_error": maximum,
        "rtol": 1e-12,
        "atol": 1e-12,
    }
    write_json(output / "prediction_replay_audit.json", receipt)
    return receipt


def execution_diagnostics(
    output: Path, predictions: pd.DataFrame, tape: MarketTape
) -> pd.DataFrame:
    targets = normal_dates(pd.read_parquet(output / "targets.parquet"), ["cutoff"])
    targets = targets[targets.split == "test"]
    rows, errors = [], []
    for row in targets.itertuples(index=False):
        days = tape.calendar[np.searchsorted(tape.calendar, row.cutoff, side="right") :][:5]
        first = tape.quotes[days[0]].get(row.entity_id, {}).get("open", np.nan)
        last = tape.quotes[days[row.horizon - 1]].get(row.entity_id, {}).get("close", np.nan)
        fifth = tape.quotes[days[4]].get(row.entity_id, {}).get("close", np.nan)
        valid = np.isfinite(first) and first > 0
        gap = first / row.reference_close - 1 if valid else np.nan
        native = last / first - 1 if valid and np.isfinite(last) and last > 0 else np.nan
        h5 = fifth / first - 1 if valid and np.isfinite(fifth) and fifth > 0 else np.nan
        if np.isfinite(native) and np.isfinite(row.candidate_return_abs):
            errors.append(abs((1 + gap) * (1 + native) - 1 - row.candidate_return_abs))
        rows.append(
            {
                "cutoff": row.cutoff,
                "entity_id": row.entity_id,
                "horizon": row.horizon,
                "gap": gap,
                "exec_native": native,
                "exec_h5": h5,
            }
        )
    assert errors and max(errors) < 1e-12
    diagnostics = pd.DataFrame(rows)
    diagnostics.to_parquet(output / "execution_diagnostics.parquet", index=False)
    joined = predictions.merge(
        diagnostics, on=["cutoff", "entity_id", "horizon"], validate="many_to_one"
    )
    metrics = []
    for (mid, cutoff), part in joined.groupby(["model_id", "cutoff"]):
        for metric in ["exec_native", "exec_h5", "gap"]:
            finite = np.isfinite(part.score) & np.isfinite(part[metric])
            n = int(finite.sum())
            metrics.append(
                {
                    "model_id": mid,
                    "cutoff": cutoff,
                    "metric": metric,
                    "pairs": n,
                    "ic": correlation(
                        part.loc[finite, "score"].to_numpy(), part.loc[finite, metric].to_numpy()
                    )
                    if n >= 30
                    else None,
                }
            )
    result = pd.DataFrame(metrics)
    result.to_parquet(output / "execution_cutoff_metrics.parquet", index=False)
    write_json(
        output / "execution_identity_audit.json",
        {
            "pairs": len(errors),
            "maximum_identity_error": float(max(errors)),
            "identity": "1+target_return=(1+gap)*(1+open_to_native_close)",
            "diagnostics_do_not_filter_scores_or_portfolios": True,
        },
    )
    return result


def portfolio_replays(
    output: Path, predictions: pd.DataFrame, tape: MarketTape, config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries, curves, ledgers, baskets = [], [], [], []
    common = set.intersection(
        *[set(predictions[predictions.horizon == h].cutoff) for h in [1, 2, 3]]
    )
    gap_lookup = normal_dates(pd.read_parquet(output / "execution_diagnostics.parquet"), ["cutoff"])
    gap_lookup = gap_lookup.set_index(["cutoff", "entity_id", "horizon"]).gap.to_dict()
    tasks = []
    for mid, part in predictions.groupby("model_id", sort=True):
        meta = part.iloc[0]
        tasks.append((mid, meta.target, int(meta.horizon), meta.model, picks(part, 0.03)))
    for h in [1, 2, 3]:
        part = predictions[predictions.horizon == h].drop_duplicates(["cutoff", "entity_id"])
        selection = [
            {
                "cutoff": day,
                "long_ids": sorted(p.entity_id),
                "short_ids": [],
                "eligible_n": len(p),
                "selected_n_per_leg": len(p),
                "constant_scores": False,
            }
            for day, p in part.groupby("cutoff", sort=True)
        ]
        tasks.append((f"universe-h{h}", "universe", h, "universe", selection))
    for number, (mid, target, h, model, selection) in enumerate(tasks, 1):
        for hold in [h, 5]:
            for cost in config["costs_round_trip_bp"]:
                eq, ledger, stats = simulate_signed(
                    selection,
                    tape,
                    hold,
                    cost,
                    config["portfolio_sleeves"],
                    "long_only",
                    0.0,
                    date.fromisoformat(config["portfolio_end"]),
                )
                sid = f"{mid}-hold{hold}-cost{cost}"
                meta = {
                    "simulation_id": sid,
                    "model_id": mid,
                    "target": target,
                    "horizon": h,
                    "model": model,
                    "holding_horizon": hold,
                    "cost_bp": cost,
                }
                # Include entry/exit sessions, unlike end-of-day exposure (H1 closes each day).
                active = np.zeros(len(eq))
                previous_nav = eq.equity.shift(1, fill_value=1).to_numpy()
                for trade in ledger.itertuples(index=False):
                    if trade.status == "missing_entry_or_no_cash":
                        continue
                    exit_day = (
                        trade.exit_date if pd.notna(trade.exit_date) else eq.session_date.iloc[-1]
                    )
                    mask = (eq.session_date >= trade.entry_date) & (eq.session_date <= exit_day)
                    active[mask] += trade.shares * trade.entry_price / previous_nav[mask]
                eq["active_session_capital"] = active
                stats["average_active_session_capital"] = float(active.mean())
                summaries.append({**stats, **meta})
                curves.append(eq.assign(**meta))
                ledgers.append(ledger.assign(**meta))
                if cost == 0:
                    assert abs(eq.fees.sum()) < 1e-15
                    assert abs(ledger.pnl_gross.sum() - stats["cumulative_return"]) < 1e-10
                    for day, part in ledger.groupby("cutoff"):
                        basket = float(part.pnl_gross.sum() / part.allocation.sum())
                        baskets.append(
                            {
                                **meta,
                                "cutoff": day,
                                "gross_basket_return": basket,
                                "common_cutoff": day in common,
                                "missing_entries": int(
                                    (part.status == "missing_entry_or_no_cash").sum()
                                ),
                                "mean_entry_gap": float(
                                    np.nanmean(
                                        [
                                            gap_lookup[(day, r.entity_id, h)]
                                            for r in part.itertuples(index=False)
                                        ]
                                    )
                                ),
                            }
                        )
        if number % 10 == 0:
            print(f"SHORT PORTFOLIOS {number}/{len(tasks)}", flush=True)
    summary = pd.DataFrame(summaries)
    summary.to_parquet(output / "backtest_summary.parquet", index=False)
    summary.to_csv(output / "backtest_summary.csv", index=False)
    pd.concat(curves, ignore_index=True).to_parquet(output / "backtest_equity.parquet", index=False)
    pd.concat(ledgers, ignore_index=True).to_parquet(
        output / "backtest_trades.parquet", index=False
    )
    basket_frame = pd.DataFrame(baskets)
    basket_frame.to_parquet(output / "basket_metrics.parquet", index=False)
    basket_frame.to_csv(output / "basket_metrics.csv", index=False)
    write_json(
        output / "portfolio_summary.json",
        {
            "replays": len(summary),
            "models": len(tasks) - 3,
            "universe_references": 3,
            "common_score_cutoffs": len(common),
            "sleeves": config["portfolio_sleeves"],
            "gross_cost_bp": 0,
            "cost_sensitivity_bp": [25, 45],
            "strategy": "long_only",
            "annualized_return": None,
            "gross_ledgers_reconcile_with_nav": True,
        },
    )
    return summary, basket_frame


def publish(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    marker = output / "report_complete.json"
    marker.unlink(missing_ok=True)
    training = json.loads((output / "summary.json").read_text())
    for name, sha in training["artifact_sha256"].items():
        assert file_sha(output / name) == sha, name
    market = normal_dates(pd.read_parquet(output / "source_market.parquet"), ["session_date"])
    bench = normal_dates(pd.read_parquet(output / "source_benchmark.parquet"), ["session_date"])
    tape = MarketTape.build(market, bench)
    dataset_audit = audit_dataset(output, root / config["source_path"], tape)
    registry = json.loads((output / "model_registry.json").read_text())
    assert len(registry) == 74
    predictions = normal_dates(pd.read_parquet(output / "predictions.parquet"), ["cutoff"])
    predictions = predictions[predictions.split == "test"].reset_index(drop=True)
    model_audit = replay_models(output, registry, predictions)
    execution = execution_diagnostics(output, predictions, tape)
    summary, baskets = portfolio_replays(output, predictions, tape, config)
    winner_ids = [r["model_id"] for r in registry if r["validation_winner_within_feature_set"]]
    assert len(winner_ids) == 16
    winners = summary[summary.model_id.isin(winner_ids)].copy()
    winners.to_parquet(output / "winners_summary.parquet", index=False)
    trades = pd.read_parquet(output / "backtest_trades.parquet")
    gross_trades = trades[trades.model_id.isin(winner_ids) & (trades.cost_bp == 0)]
    concentrations, top_trades = [], []
    for _, part in gross_trades.groupby("simulation_id"):
        first = part.iloc[0]
        top = part.nlargest(5, "pnl_gross")
        top_trades.append(top)
        concentrations.append(
            {
                "model_id": first.model_id,
                "target": first.target,
                "horizon": first.horizon,
                "holding_horizon": first.holding_horizon,
                "total_gross_contribution": float(part.pnl_gross.sum()),
                "top5_trade_contribution": float(top.pnl_gross.sum()),
                "largest_trade_contribution": float(top.pnl_gross.iloc[0]),
                "largest_trade_entity": top.entity_id.iloc[0],
                "review_trade_count": int((part.future_quality == "review").sum()),
                "review_trade_contribution": float(
                    part.loc[part.future_quality == "review", "pnl_gross"].sum()
                ),
            }
        )
    concentration = pd.DataFrame(concentrations)
    concentration.to_parquet(output / "concentration_winners.parquet", index=False)
    pd.concat(top_trades, ignore_index=True).to_parquet(
        output / "top_trades_winners.parquet", index=False
    )
    test_metrics = pd.read_parquet(output / "metrics.parquet")
    test_metrics = test_metrics[test_metrics.split == "test"].set_index("model_id")
    execution_mean = execution.groupby(["model_id", "metric"]).ic.mean().unstack()
    rows = []
    for (mid, cost), part in winners.groupby(["model_id", "cost_bp"]):
        h = int(part.horizon.iloc[0])
        native, extended = [part[part.holding_horizon == hold].iloc[0] for hold in [h, 5]]
        row = {
            "model_id": mid,
            "target": native.target,
            "horizon": h,
            "model": native.model,
            "cost_bp": int(cost),
            "test_ic": test_metrics.loc[mid, "mean_ic"],
            "test_auc": test_metrics.loc[mid].get("roc_auc", np.nan),
            "execution_ic_native": execution_mean.loc[mid, "exec_native"],
            "execution_ic_h5": execution_mean.loc[mid, "exec_h5"],
            "gap_ic": execution_mean.loc[mid, "gap"],
        }
        for suffix, r in [("native", native), ("h5", extended)]:
            row.update(
                {
                    f"{key}_{suffix}": r[key]
                    for key in [
                        "cumulative_return",
                        "max_drawdown",
                        "average_exposure",
                        "average_active_session_capital",
                        "missing_entries",
                        "delayed_exits",
                        "unresolved_exits",
                    ]
                }
            )
            b = baskets[(baskets.model_id == mid) & (baskets.holding_horizon == r.holding_horizon)]
            u = baskets[
                (baskets.model_id == f"universe-h{h}")
                & (baskets.holding_horizon == r.holding_horizon)
            ]
            row[f"mean_basket_{suffix}"] = b.gross_basket_return.mean()
            row[f"matched_basket_{suffix}"] = b[b.common_cutoff].gross_basket_return.mean()
            row[f"matched_excess_{suffix}"] = (
                b[b.common_cutoff].gross_basket_return.mean()
                - u[u.common_cutoff].gross_basket_return.mean()
            )
        rows.append(row)
    comparison = pd.DataFrame(rows).sort_values(["horizon", "target", "cost_bp"])
    comparison.to_parquet(output / "comparison_winners.parquet", index=False)
    comparison.to_csv(output / "comparison_winners.csv", index=False)
    report = root / "docs/SRD_SHORT_HORIZONS_RESULTS.md"
    gross = comparison[comparison.cost_bp == 0]
    view = pd.DataFrame(
        {
            "Target": gross.target.map(LABELS),
            "H": gross.horizon,
            "Modèle validation": gross.model,
            "IC target": gross.test_ic.round(4),
            "AUC": gross.test_auc.round(4),
            "Brut sortie H (%)": (100 * gross.cumulative_return_native).round(3),
            "Brut sortie H5 (%)": (100 * gross.cumulative_return_h5).round(3),
            "DD H (%)": (100 * gross.max_drawdown_native).round(2),
            "DD H5 (%)": (100 * gross.max_drawdown_h5).round(2),
        }
    )
    basket_view = pd.DataFrame(
        {
            "Target": gross.target.map(LABELS),
            "H": gross.horizon,
            "Panier H (%)": (100 * gross.matched_basket_native).round(3),
            "Panier H5 (%)": (100 * gross.matched_basket_h5).round(3),
            "Excès univers H (pt)": (100 * gross.matched_excess_native).round(3),
            "Excès univers H5 (pt)": (100 * gross.matched_excess_h5).round(3),
            "IC après open H": gross.execution_ic_native.round(4),
            "IC après open H5": gross.execution_ic_h5.round(4),
            "IC gap": gross.gap_ic.round(4),
        }
    )
    net = comparison[comparison.cost_bp != 0]
    net_view = pd.DataFrame(
        {
            "Target": net.target.map(LABELS),
            "H": net.horizon,
            "bp AR": net.cost_bp,
            "Net H (%)": (100 * net.cumulative_return_native).round(3),
            "Net H5 (%)": (100 * net.cumulative_return_h5).round(3),
        }
    )
    all_scores = gross.model_id.tolist()
    integrity = summary[summary.model_id.isin(all_scores) & (summary.cost_bp == 0)]
    native_concentration = concentration[concentration.holding_horizon == concentration.horizon]
    concentration_view = pd.DataFrame(
        {
            "Target": native_concentration.target.map(LABELS),
            "H": native_concentration.horizon,
            "PnL total (pt)": (100 * native_concentration.total_gross_contribution).round(3),
            "Cinq meilleurs trades (pt)": (
                100 * native_concentration.top5_trade_contribution
            ).round(3),
            "Trades en revue": native_concentration.review_trade_count,
            "Contribution revue (pt)": (100 * native_concentration.review_trade_contribution).round(
                3
            ),
        }
    )
    text = f"""# Actions seules — modèles H1/H2/H3 et détention H5

**6 octobre 2026 · expérience de développement.**
[Contrat fixé](SRD_SHORT_HORIZONS_CONTRACT.md) · [Journal](RESEARCH_PROGRESS_2026_10_06.md).

## Données et apprentissage

Même corpus ABC SRD et **1 048 features actions**, sans contexte d'indice ni K-means.
Features et sources identiques octet pour octet au benchmark parent : 17 494 lignes,
100 cutoffs. Nouvelles targets sur le calendrier commun observé, sans avancer un prix
manquant. Train 2024, choix sur S1 2025, retrain 2024+S1 2025, lecture S1 2026.
**16 tâches, 74 modèles finaux, {training["tuning_fits"]} fits de validation.**
Gagnants choisis sur validation uniquement : AUC des directions, IC des régressions.
Les 74 variantes sont conservées, et les 16 gagnants présentés ci-dessous.

Tendance/erreur-type indéfinie à H1/H2 ; disponible à H3 avec un seul degré de
liberté, donc fragile. Excursions H1 = 2 × rendement H1 : tâches redondantes.
Les lignes test gardent les actions éligibles à T même si leur label est indisponible.
H1/H2 : 24 décisions ; H3 : 23. Purges et bornes des labels enregistrées.

## Performance brute : avant frais

Top 3 % acheté, **long-only**, sans levier ; entrée au prochain open et sortie au
close de la H-ième séance commune ou H5. Mêmes scores dans chaque paire.
Deux compartiments pour toutes les simulations ; capital initial 1. Les chiffres
sont les rendements **cumulés du portefeuille**, pas annualisés, jusqu'au 31 juillet
2026 avec cash après la dernière liquidation. Toutes les décisions sont en S1.

{table(view)}

IC target = moyenne des corrélations cross-sectionnelles par cutoff avec la target
close-à-close ; AUC concerne seulement les deux directions. Une référence naïve
constante classe les titres par identifiant : son top est arbitraire.

## Comparaison à dates communes et après l'open

Les rendements moyens ci-dessous portent sur les **23 dates communes H1/H2/H3**.
Panier = somme des PnL bruts / budget du panier ; une entrée manquante reste en cash.
Excès = différence face au panier équipondéré de tout l'univers éligible avec les
mêmes dates, compartiments et détention. Il ne s'agit pas d'un alpha ajusté des risques.
Les IC après open mesurent un rendement continu, différent des IC des targets de direction.

{table(basket_view)}

La target close T → close T+H comprend un gap qui précède l'entrée simulée.
Identité auditée : `1+target = (1+gap) × (1+rendement après open)`.
Il faut lire IC du gap et IC après l'open séparément ; un bon classement du gap
ne serait pas nécessairement exploitable après cet open.

## Frais : sensibilité 25/45 bp aller-retour

{table(net_view)}

Forfaits globaux partagés achat/vente ; aucune TTF titre par titre ni minimum de broker.
Pas de VAD dans cette expérience. Même décisions, budgets et NAV recalculés pour les frais.

## Exposition et intégrité

Une détention H5 mobilise le capital plus longtemps : sa performance cumulée ne
mesure pas seule une persistance du signal. Les CSV/Parquet et Marimo affichent
drawdown, capital actif par séance et exposition en fin de séance. À H1, la position
est ouverte puis fermée dans la même séance : **exposition de fin de séance nulle**,
malgré un capital engagé pendant la séance. Le capital actif inclut entrée et sortie,
sans prétendre mesurer des heures exactes d'exposition.

Sur les gagnants bruts : {int(integrity.missing_entries.sum())} entrées manquantes,
{int(integrity.delayed_exits.sum())} sorties retardées,
{int(integrity.unresolved_exits.sum())} positions non liquidées. Le ledger et la NAV
se réconcilient ; la qualité future annote les trades sans retirer de décision.

### Concentration du résultat brut à la détention native

{table(concentration_view)}

Ces contributions sont des points du capital initial ; elles ne sont pas les
rendements individuels des titres. Pour rendement H3, les cinq meilleurs trades
apportent **15,834 points sur 23,476**. Un trade `BE0974310428`, cutoff 22 mai 2026,
entrée à 8 et sortie à 12 (+50 %), contribue **5,779 points** et est marqué `review`.
La cause de cette variation n'est pas certifiée. Il reste inclus : aucune exclusion
favorable après lecture du résultat. Les deux entrées manquantes restent en cash.
Cette concentration et les prix non certifiés limitent particulièrement la lecture
du résultat H3. `top_trades_winners.parquet` conserve les lignes concernées.

## Limites et reproduction

Prix source non certifiés ajustés, corporate actions et univers historique incomplets,
PIT reconstruit ; période déjà explorée et comparaisons multiples sans correction.
Ces résultats restent des simulations de développement, aucune confirmation indépendante.
Grille hebdomadaire conservée : H1 ne signifie pas un nouveau score tous les jours.

```bash
uv run python scripts/srd_short_horizons.py data
uv run python scripts/srd_short_horizons.py run
uv run python scripts/srd_short_horizons.py publish
```

Le run refuse d'écraser des modèles complets. Artefacts locaux non versionnés :
`data/analysis/srd-short-horizons-v1/`. Registre 74 modèles, métriques, scores,
462 replays (444 modèles + 18 univers), ledgers, courbes, paniers, diagnostics des gaps,
audits dataset et artefacts sauvegardés. Sources/checksums dans le fichier compagnon.
"""
    report.write_text(text)
    artifacts = {
        str(p.relative_to(root)): file_sha(p)
        for p in [
            root / "configs/experiments/srd_short_horizons_v1.toml",
            report,
            root / "docs/SRD_SHORT_HORIZONS_CONTRACT.md",
            root / "src/hocus_quant/model_lab/short_horizons.py",
            root / "src/hocus_quant/model_lab/short_horizon_report.py",
            root / "scripts/srd_short_horizons.py",
            *[
                output / n
                for n in [
                    "dataset_manifest.json",
                    "summary.json",
                    "model_registry.json",
                    "dataset_audit.json",
                    "prediction_replay_audit.json",
                    "execution_identity_audit.json",
                    "portfolio_summary.json",
                ]
            ],
            *output.glob("*.parquet"),
            *output.glob("*.csv"),
            *output.glob("benchmark_clock_correction.json"),
        ]
    }
    write_json(
        report.with_suffix(".sources.json"), {"created_at": "2026-10-06", "sha256": artifacts}
    )
    receipt = {
        "models": 74,
        "winners": 16,
        "portfolio_replays": len(summary),
        "dataset_audit": dataset_audit,
        "model_replay": model_audit,
        "report_sha256": file_sha(report),
        "development_only": True,
    }
    write_json(marker, receipt)
    return receipt
