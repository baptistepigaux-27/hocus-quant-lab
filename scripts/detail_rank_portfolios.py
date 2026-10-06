"""Attribute the fixed rank H5/H10 top3 portfolios; no refit, replay or exclusions."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.report import table, validation_winners


def pct_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame.copy()
    for col in columns:
        view[col] = view[col].map(lambda x: "—" if pd.isna(x) else f"{x * 100:+.2f}")
    return table(view)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "data/analysis/spec008-model-lab-all-features"
    replay = source / "portfolio-top03"
    output = replay / "rank-detail"
    output.mkdir(exist_ok=True)
    names = [
        "backtest_summary.parquet",
        "backtest_trades.parquet",
        "backtest_equity.parquet",
        "selection_audit.parquet",
    ]
    replay_manifest = json.loads((replay / "summary.json").read_text())
    for name in names:
        if file_sha(replay / name) != replay_manifest["artifact_sha256"][name]:
            raise ValueError(f"Replay artifact changed: {name}")
    winners = validation_winners(source)
    winners = winners[winners.target == "rank_pct"]
    if set(winners.model) != {"rf"}:
        raise ValueError("Expected the original RF validation winners")
    ids = winners.model_id.tolist()
    summary = pd.read_parquet(replay / "backtest_summary.parquet")
    summary = summary[summary.model_id.isin(ids)].sort_values(["horizon", "cost_bp"])
    trades = pd.read_parquet(replay / "backtest_trades.parquet")
    trades = trades[trades.model_id.isin(ids) & (trades.cost_bp == 25)].copy()
    equity = pd.read_parquet(replay / "backtest_equity.parquet")
    equity = equity[equity.model_id.isin(ids) & (equity.cost_bp == 25)].copy()
    market = pd.read_parquet(source / "source_market.parquet")
    metadata = market[["entity_id", "instrument_id", "isin"]].drop_duplicates()
    with duckdb.connect(str(root / "data/research.duckdb"), read_only=True) as db:
        labels = db.execute(
            "SELECT provider_instrument_id, display_name, ticker FROM instrument_labels_by_code"
        ).fetchdf()
    labels.to_csv(output / "local_label_snapshot.csv", index=False)
    metadata = metadata.merge(
        labels,
        left_on="instrument_id",
        right_on="provider_instrument_id",
        how="left",
        validate="many_to_one",
    )
    supplements_path = root / "docs/RANK_PORTFOLIO_LABELS.json"
    supplements = json.loads(supplements_path.read_text())["labels"]
    metadata["label_source"] = "local instrument_labels_by_code"
    for code, entry in supplements.items():
        mask = (metadata["isin"] == code) & metadata.display_name.isna()
        metadata.loc[mask, "display_name"] = entry["name"]
        metadata.loc[mask, "label_source"] = entry["source"]
    trades = trades.merge(metadata, on="entity_id", validate="many_to_one")
    if trades.display_name.isna().any():
        raise ValueError("Missing presentation name")
    closed = trades.status.isin(["closed", "delayed_missing_exit"])
    trades["pnl_gross_initial_nav"] = np.where(
        closed, trades.shares * (trades.exit_price - trades.entry_price), 0.0
    )
    trades["fees_initial_nav"] = trades.entry_fee.fillna(0) + trades.exit_fee.fillna(0)
    trades["pnl_net_initial_nav"] = trades.pnl_gross_initial_nav - trades.fees_initial_nav
    trades["contribution_net_pp"] = trades.pnl_net_initial_nav * 100
    trades["pnl_eur_for_initial_10000"] = trades.pnl_net_initial_nav * 10000
    trades["closed"] = closed
    trades["winner"] = closed & (trades.return_net > 0)
    trades["quality_flag"] = closed & trades.future_quality.ne("approved")
    predictions = pd.read_parquet(source / "predictions.parquet")
    predictions = predictions[predictions.model_id.isin(ids) & (predictions.split == "test")]
    trades["cutoff"] = pd.to_datetime(trades.cutoff)
    predictions["cutoff"] = pd.to_datetime(predictions.cutoff)
    trades = trades.merge(
        predictions[["model_id", "cutoff", "entity_id", "score"]],
        on=["model_id", "cutoff", "entity_id"],
        validate="one_to_one",
    )
    stocks = (
        trades.groupby(["horizon", "entity_id", "isin", "display_name"], dropna=False)
        .agg(
            selections=("status", "size"),
            trades_closed=("closed", "sum"),
            winning_trades=("winner", "sum"),
            mean_trade_net=("return_net", "mean"),
            best_trade_net=("return_net", "max"),
            worst_trade_net=("return_net", "min"),
            contribution_net=("pnl_net_initial_nav", "sum"),
            contribution_gross=("pnl_gross_initial_nav", "sum"),
            fees_initial_nav=("fees_initial_nav", "sum"),
            flagged_trades=("quality_flag", "sum"),
            first_entry=("entry_date", "min"),
            last_exit=("exit_date", "max"),
        )
        .reset_index()
        .sort_values(["horizon", "contribution_net"], ascending=[True, False])
    )
    stocks["hit_rate"] = stocks.winning_trades / stocks.trades_closed.replace(0, np.nan)
    stocks["pnl_eur_for_initial_10000"] = stocks.contribution_net * 10000
    monthly_rows = []
    vintages = (
        trades.groupby(["horizon", "cutoff"])
        .agg(
            actions=("display_name", lambda x: "; ".join(x)),
            selections=("status", "size"),
            executed=("closed", "sum"),
            contribution_net=("pnl_net_initial_nav", "sum"),
        )
        .reset_index()
    )
    for h in [5, 10]:
        eq = equity[equity.horizon == h].sort_values("session_date").copy()
        eq["month"] = pd.to_datetime(eq.session_date).dt.to_period("M").astype(str)
        previous, previous_bench = 1.0, 1.0
        for month, part in eq.groupby("month", sort=True):
            last = part.iloc[-1]
            monthly_rows.append(
                {
                    "horizon": h,
                    "month": month,
                    "portfolio_net": last.equity / previous - 1,
                    "benchmark_price_return": last.benchmark_equity / previous_bench - 1,
                    "cumulative_net": last.equity - 1,
                }
            )
            previous, previous_bench = last.equity, last.benchmark_equity
        stats = summary[(summary.horizon == h) & (summary.cost_bp == 25)].iloc[0]
        if not np.isclose(
            stocks[stocks.horizon == h].contribution_net.sum(), stats.cumulative_return, atol=1e-12
        ):
            raise ValueError("Stock attribution does not reconcile with portfolio NAV")
        if not np.isclose(eq.iloc[-1].equity - 1, stats.cumulative_return, atol=1e-12):
            raise ValueError("Equity mismatch")
        trades[trades.horizon == h].sort_values(["cutoff", "entity_id"]).to_csv(
            output / f"trades_h{h}.csv", index=False
        )
        stocks[stocks.horizon == h].to_csv(output / f"stocks_h{h}.csv", index=False)
    monthly = pd.DataFrame(monthly_rows)
    for name, frame in [
        ("monthly", monthly),
        ("vintages", vintages),
        ("equity", equity),
        ("summary", summary),
        ("stocks", stocks),
        ("trades", trades),
    ]:
        frame.to_csv(output / f"{name}.csv", index=False)
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=[
            "Portefeuilles · base 100, net 25 bp",
            "Contributions par titre · H10 (points)",
        ],
    )
    for h in [5, 10]:
        eq = equity[equity.horizon == h].sort_values("session_date")
        fig.add_trace(
            go.Scatter(x=eq.session_date, y=eq.equity * 100, name=f"RF rang H{h}"), row=1, col=1
        )
    eq = equity[equity.horizon == 10].sort_values("session_date")
    fig.add_trace(
        go.Scatter(x=eq.session_date, y=eq.benchmark_equity * 100, name="CAC AllShares · prix"),
        row=1,
        col=1,
    )
    h10 = stocks[stocks.horizon == 10]
    fig.add_trace(
        go.Bar(
            x=h10.display_name,
            y=h10.contribution_net * 100,
            name="Contribution H10",
            customdata=h10["isin"],
        ),
        row=2,
        col=1,
    )
    fig.update_layout(
        height=950, title="Rang du rendement · top 3 % · S1 2026", template="plotly_white"
    )
    fig.write_html(output / "rank_portfolio_detail.html", include_plotlyjs=True)
    report = [
        "# Rang du rendement — actions et performance détaillée\n",
        "**Random Forest, 1 048 variables, top 3 %, frais aller-retour 25 bp.** "
        "Modèles choisis sur validation S1 2025 ; portefeuille simulé du 5 janvier au "
        "30 juin 2026. Aucun nouvel entraînement ou retrait de position.\n",
        "## Lecture\n",
        "La target `rank_pct` classe le rendement futur close/close. Le portefeuille "
        "achète les cinq titres aux scores les plus élevés à chaque cutoff, au prochain "
        "open commun, puis sort au H-ième close commun. Deux compartiments H5, trois "
        "H10 : le cash et les compartiments inactifs limitent l'exposition moyenne.\n",
        "**Rendement moyen par position** : moyenne simple des rendements nets des "
        "positions exécutées, pas rendement semestriel buy-and-hold de l'action. "
        "**Contribution** : bénéfice/perte réalisé net divisé par le capital initial, "
        "en points. Les contributions s'additionnent exactement au rendement du "
        "portefeuille. Pour 10 000 € initiaux, 1 point = 100 €.\n",
        "## Performance des portefeuilles\n",
    ]
    selected = summary[summary.cost_bp == 25][
        [
            "horizon",
            "cumulative_return",
            "benchmark_return",
            "max_drawdown",
            "volatility",
            "sharpe",
            "positions",
            "hit_rate",
            "average_trade_return",
            "average_exposure",
            "fees",
            "missing_entries",
            "flagged_closed_positions",
        ]
    ]
    report.append(
        pct_table(
            selected,
            [
                "cumulative_return",
                "benchmark_return",
                "max_drawdown",
                "volatility",
                "hit_rate",
                "average_trade_return",
                "average_exposure",
                "fees",
            ],
        )
    )
    report += [
        "\nVolatilité/Sharpe annualisés par convention, estimés sur ce seul semestre. "
        "Le benchmark est une série de prix, sans dividendes. Les frais sont les "
        "sommes payées rapportées au capital initial ; leur somme n'est pas la "
        "différence entre simulations brut et net, car les allocations évoluent.\n",
        "## Rendements mensuels\n",
        pct_table(monthly, ["portfolio_net", "benchmark_price_return", "cumulative_net"]),
    ]
    for h in [10, 5]:
        part = stocks[stocks.horizon == h]
        report += [
            f"\n## Toutes les actions — H{h}\n",
            f"{len(part)} titres sélectionnés ; {int((part.trades_closed > 0).sum())} "
            "titres exécutés. Tableau trié par contribution nette. Valeurs de "
            "rendement en %, contributions en points.\n",
            pct_table(
                part[
                    [
                        "display_name",
                        "isin",
                        "selections",
                        "trades_closed",
                        "mean_trade_net",
                        "worst_trade_net",
                        "best_trade_net",
                        "contribution_net",
                        "flagged_trades",
                    ]
                ],
                ["mean_trade_net", "worst_trade_net", "best_trade_net", "contribution_net"],
            ),
            f"\n### Paniers par date — H{h}\n",
            pct_table(
                vintages[vintages.horizon == h].drop(columns="horizon"), ["contribution_net"]
            ),
        ]
    flagged = trades[trades.quality_flag]
    report += [
        "\n## Mouvement signalé par le contrôle qualité\n",
        pct_table(
            flagged[
                [
                    "horizon",
                    "display_name",
                    "isin",
                    "entry_date",
                    "exit_date",
                    "entry_price",
                    "exit_price",
                    "return_net",
                    "pnl_net_initial_nav",
                    "future_reason",
                ]
            ],
            ["return_net", "pnl_net_initial_nav"],
        ),
        "\nCes positions restent dans le calcul. L'annotation `large_move_plausible` "
        "ne certifie pas la cause du mouvement. Les prix raw et corporate actions "
        "restent à vérifier. H5 a également deux entrées Nacon non exécutées ; "
        "aucune position n'est retirée après examen de son rendement futur.\n",
        "## Exports et provenance\n",
        f"Dossier : `{output.relative_to(root)}`. `stocks_h5.csv` / `stocks_h10.csv` : "
        "tous les titres. `trades_h5.csv` / `trades_h10.csv` : chaque position, score, "
        "ISIN, dates, prix, frais, rendement et contribution. `vintages.csv` : paniers "
        "par cutoff. `monthly.csv` / `equity.csv` : trajectoire. "
        "`rank_portfolio_detail.html` : courbes et contributions interactives.\n",
        "Les libellés locaux sont conservés dans `local_label_snapshot.csv`. Les "
        "17 libellés non résolus sont complétés uniquement pour la présentation à "
        "partir d'Euronext ; ils ne changent ni features ni scores. Sources :\n",
    ]
    report.extend(f"- [{v['name']} — {code}]({v['source']})\n" for code, v in supplements.items())
    report += [
        "\nReproduction : `uv run python scripts/detail_rank_portfolios.py`. "
        "Les résultats demeurent du développement sur 2026 déjà exploré ; "
        "univers reconstruit et prix non certifiés.\n"
    ]
    report_path = root / "docs/SPEC_008_RANK_PORTFOLIO_DETAIL.md"
    report_path.write_text("\n".join(report))
    provenance = {
        "model_and_price_inputs": {
            str((source / name).relative_to(root)): file_sha(source / name)
            for name in ["model_registry.json", "predictions.parquet", "source_market.parquet"]
        },
        "source_artifacts": {
            str((replay / n).relative_to(root)): file_sha(replay / n) for n in names
        },
        "label_supplements_sha256": file_sha(supplements_path),
        "local_label_snapshot_sha256": file_sha(output / "local_label_snapshot.csv"),
        "generator_sha256": file_sha(Path(__file__)),
        "report_sha256": file_sha(report_path),
        "exports": {p.name: file_sha(p) for p in sorted(output.iterdir()) if p.is_file()},
        "attribution_reconciles_to_nav": True,
        "refits": 0,
        "replays": 0,
    }
    (root / "docs/SPEC_008_RANK_PORTFOLIO_DETAIL.sources.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(selected.to_string(index=False))
    print(monthly.to_string(index=False))
    print(h10.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
