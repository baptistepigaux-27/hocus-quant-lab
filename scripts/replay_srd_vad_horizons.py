"""Replay the saved stock-only scores with long/short legs and longer holdings."""

from __future__ import annotations

import json
import time
import tomllib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.portfolio_extensions import MarketTape, picks, simulate_signed
from hocus_quant.model_lab.report import table, validation_winners
from hocus_quant.model_lab.run import code_identity


def load_dates(path: Path, columns: list[str]) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    for column in columns:
        frame[column] = pd.to_datetime(frame[column]).dt.date
    return frame


def reconcile(output: Path, source: Path, tape: MarketTape) -> dict:
    curves = load_dates(output / "backtest_equity.parquet", ["session_date"])
    trades = load_dates(output / "backtest_trades.parquet", ["entry_date", "exit_date"])
    original = pd.concat(
        [
            load_dates(source / "portfolio-top03/backtest_equity.parquet", ["session_date"]),
            load_dates(
                source / "portfolio-top03/costs-25-45/backtest_equity.parquet", ["session_date"]
            ),
        ]
    )
    original = original[original.cost_bp.isin([25, 45]) & (original.model != "universe")]
    control = curves[
        (curves.strategy == "long_only")
        & (curves.horizon == curves.holding_horizon)
        & (curves.session_date <= date(2026, 6, 30))
    ]
    paired = control.merge(
        original[["model_id", "cost_bp", "session_date", "equity"]],
        on=["model_id", "cost_bp", "session_date"],
        suffixes=("_new", "_original"),
        validate="one_to_one",
    )
    assert len(paired) == len(control) == len(original)
    error = float(np.abs(paired.equity_new - paired.equity_original).max())
    assert error < 1e-10
    closed = trades[trades.status.isin(["closed", "delayed_missing_exit"])]
    sign = np.where(closed.side == "long", 1.0, -1.0)
    gross = sign * closed.shares * (closed.exit_price - closed.entry_price)
    pnl_error = float(np.abs(gross - closed.pnl_gross).max())
    net_error = float(
        np.abs(
            gross - closed.entry_fee - closed.exit_fee - closed.borrow_fees - closed.pnl_net
        ).max()
    )
    assert pnl_error < 1e-12 and net_error < 1e-12
    borrow_cache = {}
    borrow_errors = []
    for row in closed[(closed.side == "short") & (closed.borrow_rate_annual > 0)].itertuples():
        key = row.entity_id, row.entry_date, row.exit_date
        if key not in borrow_cache:
            prior_date = row.entry_date
            prior_price = tape.quotes[prior_date][row.entity_id]["open"]
            units = 0.0
            for day in [d for d in tape.calendar if row.entry_date <= d <= row.exit_date]:
                units += prior_price * (day - prior_date).days / 365
                close = tape.quotes[day].get(row.entity_id, {}).get("close")
                if close is not None and np.isfinite(close) and close > 0:
                    prior_price = close
                prior_date = day
            borrow_cache[key] = units
        expected = row.shares * row.borrow_rate_annual * borrow_cache[key]
        borrow_errors.append(abs(expected - row.borrow_fees))
    assert borrow_errors and max(borrow_errors) < 1e-12
    selection = pd.read_parquet(output / "selection_audit.parquet")
    assert all(set(row.long_ids).isdisjoint(row.short_ids) for row in selection.itertuples())
    receipt = {
        "native_long_only_curves": control.simulation_id.nunique(),
        "native_control_rows": len(paired),
        "max_native_equity_difference": error,
        "closed_positions": len(closed),
        "max_position_gross_pnl_error": pnl_error,
        "max_position_net_pnl_error": net_error,
        "short_borrow_positions_recomputed": len(borrow_errors),
        "max_short_borrow_fee_error": float(max(borrow_errors)),
        "all_long_short_selections_disjoint": True,
        "training_fits": 0,
    }
    (output / "reconciliation_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def publish(root: Path, output: Path, source: Path, config: dict, audit: dict) -> None:
    summary = pd.read_parquet(output / "backtest_summary.parquet")
    winners = validation_winners(source)
    selected = summary.merge(
        winners[["model_id", "validation_metric"]], on="model_id", validate="many_to_one"
    )
    selected.to_parquet(output / "winners_summary.parquet", index=False)
    selected.to_csv(output / "winners_summary.csv", index=False)
    rows = []
    for winner in winners.itertuples():
        part = selected[selected.model_id == winner.model_id]
        h, extended = int(winner.horizon), 2 * int(winner.horizon)
        for cost in config["costs_round_trip_bp"]:
            for rate in config["short_borrow_rates_annual"]:
                row = {
                    "model_id": winner.model_id,
                    "target": winner.target,
                    "horizon": h,
                    "extended_horizon": extended,
                    "model": winner.model,
                    "cost_bp": cost,
                    "borrow_rate_annual": rate,
                }
                for strategy in config["strategies"]:
                    for hold, prefix in [(h, "native"), (extended, "extended")]:
                        chosen = part[
                            (part.cost_bp == cost)
                            & (part.strategy == strategy)
                            & (part.holding_horizon == hold)
                            & (part.borrow_rate_annual == (rate if strategy == "long_short" else 0))
                        ]
                        assert len(chosen) == 1
                        for metric in [
                            "cumulative_return",
                            "max_drawdown",
                            "average_exposure",
                            "average_net_exposure",
                            "long_contribution",
                            "short_contribution",
                            "borrow_fees",
                            "fees",
                            "turnover",
                            "positions",
                        ]:
                            row[f"{prefix}_{strategy}_{metric}"] = chosen.iloc[0][metric]
                rows.append(row)
    comparison = pd.DataFrame(rows)
    comparison.to_parquet(output / "comparison_winners.parquet", index=False)
    comparison.to_csv(output / "comparison_winners.csv", index=False)
    trades = pd.read_parquet(output / "backtest_trades.parquet")
    # Labels are the previously delivered reference snapshot, not historical membership.
    labels_path = source / "portfolio-top03/rank-detail/local_label_snapshot.csv"
    if labels_path.exists():
        labels = pd.read_csv(labels_path)[["provider_instrument_id", "display_name"]]
        market = pd.read_parquet(source / "source_market.parquet")
        identities = market[["entity_id", "instrument_id", "isin"]].drop_duplicates()
        identities = identities.merge(
            labels,
            left_on="instrument_id",
            right_on="provider_instrument_id",
            how="left",
            validate="many_to_one",
        )
        trades = trades.merge(identities, on="entity_id", how="left", validate="many_to_one")
        trades.display_name = trades.display_name.fillna(trades["isin"])
    else:
        trades["display_name"] = trades.entity_id
    trades["closed"] = trades.status.isin(["closed", "delayed_missing_exit"])
    stock = (
        trades.groupby(
            [
                "simulation_id",
                "model_id",
                "target",
                "horizon",
                "holding_horizon",
                "strategy",
                "cost_bp",
                "borrow_rate_annual",
                "side",
                "entity_id",
                "display_name",
            ],
            dropna=False,
        )
        .agg(
            selections=("status", "size"),
            closed=("closed", "sum"),
            contribution_gross=("pnl_gross", "sum"),
            contribution_net=("pnl_net", "sum"),
            transaction_entry_fees=("entry_fee", "sum"),
            transaction_exit_fees=("exit_fee", "sum"),
            borrow_fees=("borrow_fees", "sum"),
            mean_trade_net=("return_net", "mean"),
        )
        .reset_index()
    )
    stock.to_parquet(output / "stock_contributions.parquet", index=False)
    stock.to_csv(output / "stock_contributions.csv", index=False)
    curves = pd.read_parquet(output / "backtest_equity.parquet")
    monthly = []
    for sid, frame in curves.groupby("simulation_id"):
        frame = frame.sort_values("session_date").copy()
        frame["month"] = pd.to_datetime(frame.session_date).dt.to_period("M").astype(str)
        previous = 1.0
        for month, group in frame.groupby("month", sort=True):
            nav = group.equity.iloc[-1]
            monthly.append(
                {
                    "simulation_id": sid,
                    "month": month,
                    "return_net": nav / previous - 1 if previous > 0 else np.nan,
                    "long_contribution": group.pnl_long_net.sum(),
                    "short_contribution": group.pnl_short_net.sum(),
                    "end_equity": nav,
                }
            )
            previous = nav
    pd.DataFrame(monthly).to_parquet(output / "monthly_performance.parquet", index=False)
    report = root / "docs/SRD_VAD_HOLDING_RESULTS.md"
    text = (
        "# SRD sans contexte — VAD et détention prolongée\n\n"
        "**6 octobre 2026 · développement rétrospectif.** "
        "[Contrat et comptabilité](SRD_VAD_HOLDING_CONTRACT.md).\n\n"
        "56 modèles, 1 048 variables d'action, scores et gagnants de validation inchangés. "
        "Top 3 % à l'achat ; flop 3 % en VAD, allocation **50/50 sans levier**. "
        "Les deux horizons de détention sont simulés en long-only et long/short. "
        "Aucun entraînement ni choix de modèle sur les résultats ci-dessous.\n\n"
        "**Période : décisions S1 2026, valorisation jusqu'au 31 juillet 2026.** "
        "Les liquidations H20 peuvent être en juillet. Les résultats sont cumulés, "
        "non annualisés. Frais 25/45 bp par aller-retour de chaque position. "
        "Le scénario principal ajoute **3 % annuel de coût d'emprunt sur les shorts**, "
        "hypothèse de sensibilité, sans tarif de prêt observé.\n\n"
    )
    for cost in config["costs_round_trip_bp"]:
        part = comparison[(comparison.cost_bp == cost) & (comparison.borrow_rate_annual == 0.03)]
        columns = ["target", "horizon", "extended_horizon", "model"]
        view = part[columns].copy()
        for phase in ["native", "extended"]:
            for strategy in config["strategies"]:
                view[f"{strategy} {phase} (%)"] = part[f"{phase}_{strategy}_cumulative_return"].map(
                    lambda v: f"{100 * v:+.2f}"
                )
        text += f"## Gagnants de validation — {cost} bp, emprunt 3 %\n\n" + table(view) + "\n\n"
    text += (
        "Le modèle naïf direction absolue H10 prédit une constante : ses achats et "
        "shorts proviennent d'un départage arbitraire par ISIN. Il ne fournit aucun "
        "classement prédictif, même lorsqu'un panier gagne.\n\n"
        "## Rendement du rang — risque et contributions\n\n"
    )
    rank = selected[
        (selected.target == "rank_pct")
        & ((selected.strategy == "long_only") | (selected.borrow_rate_annual == 0.03))
    ][
        [
            "horizon",
            "holding_horizon",
            "strategy",
            "cost_bp",
            "cumulative_return",
            "max_drawdown",
            "average_exposure",
            "average_net_exposure",
            "long_contribution",
            "short_contribution",
            "fees",
            "borrow_fees",
            "positions",
        ]
    ]
    text += table(rank) + "\n\nLes contributions sont en fraction du capital initial et "
    text += (
        "s'additionnent au rendement cumulé ; ce ne sont pas les moyennes des rendements "
        "des titres.\n\n"
    )
    text += "## Sensibilité au prêt des titres — long/short seulement\n\n"
    sensitivity = selected[selected.strategy == "long_short"][
        [
            "target",
            "horizon",
            "holding_horizon",
            "cost_bp",
            "borrow_rate_annual",
            "cumulative_return",
            "max_drawdown",
            "borrow_fees",
        ]
    ]
    text += table(sensitivity) + "\n\nLe taux 0 % isole la mécanique des positions. "
    text += "Le taux 3 % est ajouté aux frais de transaction et modifie cash et allocations ; "
    text += "la différence est rejouée directement. Les compartiments restent séparés, "
    text += "sans netting entre vintages ; les oppositions de positions sont mesurées.\n\n"
    text += "## Réconciliation et limites\n\n" + table(pd.DataFrame([audit])) + "\n\n"
    text += (
        "Les courbes long-only natives sont réconciliées à la référence existante au "
        "30 juin, sur les 56 modèles et les deux coûts. PnL signé, frais d'emprunt et "
        "identités de NAV/contributions vérifiés sur les ledgers. "
        "Les sources restent inchangées.\n\n"
        "VAD théorique : disponibilités de prêt, dividendes à payer, rappels de titres, "
        "marge et fiscalité par instrument ne sont pas connus. Prix raw/corporate actions "
        "et univers SRD survivant ne sont pas certifiés. Les anomalies restent annotées ; "
        "aucune sélection perdante n'est retirée ex post.\n\n"
        "Les 56 modèles, jambes, paniers et courbes sont disponibles localement dans "
        "`data/analysis/srd-portfolio-extensions-v1/`. Les résultats des 12 gagnants "
        "se lisent dans le [Model Lab](https://sandbox.hocus.works/quant-model-lab/), "
        "onglet **VAD et détention**.\n\n"
        "Reproduction : `uv run python scripts/replay_srd_vad_horizons.py`. "
        "Une expérience terminée n'est pas écrasée. Les variations de durée changent "
        "les compartiments et l'exposition moyenne ; le rapport permet d'examiner ce risque. "
        "Aucune confirmation indépendante sur les périodes déjà explorées.\n"
    )
    report.write_text(text)
    receipt = {
        "status": "development_portfolio_extension_complete",
        "training_fits": 0,
        "backtest_count": len(summary),
        "report_sha256": file_sha(report),
        "generator_sha256": file_sha(Path(__file__)),
        "ledger_generator_sha256": file_sha(
            root / "src/hocus_quant/model_lab/portfolio_extensions.py"
        ),
        "reconciliation_audit_sha256": file_sha(output / "reconciliation_audit.json"),
        "artifacts": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    report.with_suffix(".sources.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (output / "report_complete.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main() -> None:
    started = time.monotonic()
    root = Path(__file__).resolve().parents[1]
    config_path = root / "configs/experiments/srd_portfolio_extensions_v1.toml"
    config = tomllib.loads(config_path.read_text())
    source, output = root / config["source_path"], root / config["output_path"]
    if (output / "report_complete.json").exists():
        raise ValueError("Completed replay exists; use a new version")
    output.mkdir(exist_ok=True)
    frozen = output / "experiment_config.json"
    if frozen.exists():
        assert json.loads(frozen.read_text()) == config
    else:
        frozen.write_text(json.dumps(config, indent=2) + "\n")
    inputs = {
        name: file_sha(source / name)
        for name in [
            "predictions.parquet",
            "model_registry.json",
            "summary.json",
            "dataset_manifest.json",
            "source_market.parquet",
            "source_benchmark.parquet",
            "portfolio-top03/backtest_equity.parquet",
            "portfolio-top03/costs-25-45/backtest_equity.parquet",
        ]
    }
    source_summary = json.loads((source / "summary.json").read_text())
    dataset = json.loads((source / "dataset_manifest.json").read_text())
    assert inputs["predictions.parquet"] == source_summary["artifact_sha256"]["predictions.parquet"]
    for name in ["source_market.parquet", "source_benchmark.parquet"]:
        assert inputs[name] == dataset["source_sha256"][name]
    predictions = load_dates(source / "predictions.parquet", ["cutoff"])
    predictions = predictions[predictions.split == "test"]
    assert set(predictions.feature_set) == {"all"} and predictions.model_id.nunique() == 56
    market = load_dates(source / "source_market.parquet", ["session_date"])
    bench = load_dates(source / "source_benchmark.parquet", ["session_date"])
    end = date.fromisoformat(config["end_date"])
    lo = predictions.cutoff.min()
    market = market[(market.session_date >= lo) & (market.session_date <= end)]
    bench = bench[(bench.session_date >= lo) & (bench.session_date <= end)]
    tape = MarketTape.build(market, bench)
    selections, folders = [], []
    for number, (model_id, part) in enumerate(predictions.groupby("model_id", sort=True), start=1):
        horizon = int(part.horizon.iloc[0])
        selection = picks(part, config["selection_fraction"])
        selections.extend({"model_id": model_id, "horizon": horizon, **s} for s in selection)
        folder = output / "model_runs" / model_id
        folder.mkdir(parents=True, exist_ok=True)
        folders.append(folder)
        if (folder / "receipt.json").exists():
            receipt = json.loads((folder / "receipt.json").read_text())
            assert receipt["input_sha256"] == inputs and receipt["config_sha256"] == file_sha(
                frozen
            )
            for name, sha in receipt["artifacts"].items():
                assert file_sha(folder / name) == sha
            print(f"REPLAY RESUMED {number}/56 {model_id}", flush=True)
            continue
        equities, ledgers, results = [], [], []
        for hold in config[f"holding_horizons_for_h{horizon}"]:
            for strategy in config["strategies"]:
                rates = config["short_borrow_rates_annual"] if strategy == "long_short" else [0.0]
                for cost in config["costs_round_trip_bp"]:
                    for rate in rates:
                        identity = fingerprint(
                            {
                                "model": model_id,
                                "hold": hold,
                                "strategy": strategy,
                                "cost": cost,
                                "borrow": rate,
                                "config": config,
                            }
                        )[:16]
                        info = {
                            "simulation_id": identity,
                            "model_id": model_id,
                            "target": part.target.iloc[0],
                            "model": part.model.iloc[0],
                            "horizon": horizon,
                            "holding_horizon": hold,
                            "strategy": strategy,
                            "cost_bp": cost,
                            "borrow_rate_annual": rate,
                        }
                        eq, tr, stats = simulate_signed(
                            selection,
                            tape,
                            hold,
                            cost,
                            config[f"portfolio_sleeves_h{hold}"],
                            strategy,
                            rate,
                            end,
                        )
                        for frame in [eq, tr]:
                            for key, value in info.items():
                                frame[key] = value
                        equities.append(eq)
                        ledgers.append(tr)
                        results.append({**info, **stats})
        pd.concat(equities, ignore_index=True).to_parquet(
            folder / "backtest_equity.parquet", index=False
        )
        pd.concat(ledgers, ignore_index=True).to_parquet(
            folder / "backtest_trades.parquet", index=False
        )
        pd.DataFrame(results).to_parquet(folder / "backtest_summary.parquet", index=False)
        (folder / "receipt.json").write_text(
            json.dumps(
                {
                    "input_sha256": inputs,
                    "config_sha256": file_sha(frozen),
                    "ledger_source_sha256": file_sha(
                        root / "src/hocus_quant/model_lab/portfolio_extensions.py"
                    ),
                    "artifacts": {p.name: file_sha(p) for p in folder.glob("*.parquet")},
                },
                indent=2,
            )
            + "\n"
        )
        print(f"REPLAY COMPLETE {number}/56 {model_id}", flush=True)
    for name in ["backtest_equity", "backtest_trades", "backtest_summary"]:
        pd.concat(
            [pd.read_parquet(folder / f"{name}.parquet") for folder in folders], ignore_index=True
        ).to_parquet(output / f"{name}.parquet", index=False)
    pd.DataFrame(selections).to_parquet(output / "selection_audit.parquet", index=False)
    audit = reconcile(output, source, tape)
    assert all(file_sha(source / name) == sha for name, sha in inputs.items())
    publish(root, output, source, config, audit)
    (output / "summary.json").write_text(
        json.dumps(
            {
                "status": "development_complete",
                "model_count": 56,
                "backtest_count": 672,
                "training_fits": 0,
                "market_context_used": False,
                "input_sha256": inputs,
                "config_sha256": file_sha(frozen),
                "elapsed_seconds": time.monotonic() - started,
                **code_identity(root),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == "__main__":
    main()
