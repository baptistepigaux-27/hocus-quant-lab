import marimo

__generated_with = "0.25.0"
app = marimo.App(width="full", app_title="Hocus Quant · Model Lab")


@app.cell
def _():
    import json
    import os
    from pathlib import Path

    import marimo as mo
    import pandas as pd
    import plotly.express as px

    baseline_root = Path(os.environ.get("HOCUS_MODEL_LAB_DATA", "data/analysis/spec008-model-lab"))
    all_features_root = Path(
        os.environ.get("HOCUS_MODEL_LAB_ALL_DATA", str(baseline_root) + "-all-features")
    )
    index_root = Path(
        os.environ.get(
            "HOCUS_INDEX_MODEL_LAB_DATA", str(baseline_root.parent / "spec008-index-model-lab")
        )
    )
    return mo, pd, px, json, Path, baseline_root, all_features_root, index_root


@app.cell
def _(mo):
    index_group = mo.ui.dropdown(
        options={"Indices de marché": "market", "Indices sectoriels": "sector"},
        value="Indices de marché",
        label="Groupe d'indices",
    )
    index_target = mo.ui.dropdown(
        options=[
            "rank_pct",
            "direction_abs",
            "return_abs",
            "direction_rel",
            "excursion_balance",
            "trend_tstat",
        ],
        value="rank_pct",
        label="Target indices",
    )
    index_horizon = mo.ui.dropdown(
        options={"H5": 5, "H10": 10}, value="H5", label="Horizon indices"
    )
    return index_group, index_target, index_horizon


@app.cell
def _(mo, pd, px, index_root, index_group, index_target, index_horizon):
    if not (index_root / "index_report_complete.json").exists():
        index_panel = mo.md("## Indices\nPremière phase de performance en cours de calcul.")
    else:
        _overview = pd.read_parquet(index_root / "index_overview.parquet")
        _metric = pd.read_parquet(index_root / "metrics.parquet")
        _profiles = pd.read_parquet(index_root / "index_feature_profiles.parquet")
        _label_profiles = pd.read_parquet(index_root / "index_label_profiles.parquet")
        _history = pd.read_parquet(index_root / "cutoff_metrics.parquet")
        _picks = pd.read_parquet(index_root / "index_selected_picks.parquet")
        _selection = _overview[
            (_overview.feature_set == index_group.value)
            & (_overview.target == index_target.value)
            & (_overview.horizon == index_horizon.value)
        ]
        _mid = _selection.model_id.iloc[0]
        _history = _history[(_history.model_id == _mid) & (_history.split == "test")]
        index_panel = mo.vstack(
            [
                mo.md("""
            ## Indices · futurs facteurs de contexte SRD
            **Développement rétrospectif : train 2024, validation S1 2025, test S1 2026.**
            Expérience indices : 112 modèles finaux sur 24 tâches, 160 essais de validation.
            65 indices de marché et 27 sectoriels candidats, éligibilité recalculée à T.
            Deux groupes classés séparément, 1 048 IDs de features avec masques de disponibilité.
            Les performances des paniers sont des moyennes de rendements futurs par cutoff,
            exprimées en quote native. Elles ne sont ni composées ni converties en euros.
            Les dates peuvent se chevaucher et les indices partager des constituants.
            """),
                mo.hstack([index_group, index_target, index_horizon], justify="start"),
                mo.md("### Gagnant choisi sur validation · performance test"),
                mo.ui.table(
                    _selection[
                        [
                            "feature_set",
                            "target",
                            "horizon",
                            "model",
                            "validation_mean_ic",
                            "mean_ic",
                            "roc_auc",
                            "r2",
                            "ic_lo90",
                            "ic_hi90",
                            "top3_mean_future_return",
                            "universe_mean_future_return",
                            "universe_mean_on_top_observed_cutoffs",
                            "top_minus_universe",
                            "minimum_selected",
                            "maximum_selected",
                            "top3_observed_cutoffs",
                            "top3_complete_cutoffs",
                        ]
                    ],
                    selection=None,
                ),
                mo.ui.plotly(
                    px.line(
                        _history,
                        x="cutoff",
                        y="ic",
                        markers=True,
                        title="IC test par cutoff · gagnant de validation",
                    )
                ),
                mo.md("### Comparaison de tous les modèles · validation et test"),
                mo.ui.table(
                    _metric[
                        (_metric.feature_set == index_group.value)
                        & (_metric.target == index_target.value)
                        & (_metric.horizon == index_horizon.value)
                    ],
                    selection=None,
                    page_size=12,
                ),
                mo.md("### Indices du panier top 3 % · résultats futurs observés"),
                mo.ui.table(
                    _picks[_picks.model_id == _mid][
                        [
                            "cutoff",
                            "display_name",
                            "entity_id",
                            "score",
                            "future_return",
                            "target_end",
                            "reference_quote_date",
                            "index_quote_end",
                            "future_quality",
                            "purge_reason",
                        ]
                    ],
                    selection=None,
                    page_size=12,
                ),
                mo.md("### Panel et disponibilité des variables"),
                mo.ui.table(_profiles[_profiles.group == index_group.value], selection=None),
                mo.md("### Couverture des labels et durée calendaire réelle"),
                mo.ui.table(
                    _label_profiles[
                        (_label_profiles.group == index_group.value)
                        & (_label_profiles.horizon == index_horizon.value)
                    ],
                    selection=None,
                ),
                mo.md("""
            Les intervalles à 90 % présentés utilisent un bootstrap par blocs de 4 cutoffs ;
            les blocs 2/6 sont aussi conservés. Ils sont individuels, sans correction multiple.
            Un modèle naïf constant donne un panier arbitraire par identifiant.
            Les exports de scores pour la suite SRD concernent seulement le test 2026,
            avec dates de disponibilité modélisées et grade PIT reconstruit.
            Le raccordement historique 2024/2025 demandera des scores OOF et une jointure as-of.
            La version corrigée utilise minuit UTC D+1 et des horizons sur le calendrier CAC40.
            Les trous source rendent les labels indisponibles, sans remplacer l'indice choisi.
            Les snapshots SRD portent déjà minuit Paris ; leur coupe historique est cohérente.
            """),
            ]
        )
    return (index_panel,)


@app.cell
def _(mo, baseline_root, all_features_root):
    _options = {"Strict 85 / Strong 138": str(baseline_root)}
    if (all_features_root / "summary.json").exists():
        _options["Toutes les variables · 1 048 features"] = str(all_features_root)
    experiment_choice = mo.ui.dropdown(
        options=_options,
        value=list(_options)[-1],
        label="Expérience · mêmes périodes et même univers",
    )
    mo.output.replace(experiment_choice)
    return (experiment_choice,)


@app.cell
def _(mo, pd, json, Path, experiment_choice):
    from hocus_quant.model_lab.report import validation_winners

    model_root = Path(experiment_choice.value)
    mo.stop(
        not (model_root / "summary.json").exists(),
        mo.md("# Model Lab\nBenchmark SPEC-008 en cours de calcul."),
    )
    summary = json.loads((model_root / "summary.json").read_text())
    registry = json.loads((model_root / "model_registry.json").read_text())
    metrics = pd.read_parquet(model_root / "metrics.parquet")
    _periods = pd.DataFrame(
        [
            {
                "model_id": r["model_id"],
                "train_period": f"{r['training_dates'][0]} → {r['training_dates'][-1]}",
                "validation_period": f"{r['validation_dates'][0]} → {r['validation_dates'][-1]}",
                "test_period": f"{r['test_dates'][0]} → {r['test_dates'][-1]}",
                "status": "development_only",
            }
            for r in registry
        ]
    )
    metrics = metrics.merge(_periods, on="model_id", validate="many_to_one")
    metrics["main_metric"] = [
        r.roc_auc if r.target in {"direction_abs", "direction_rel"} else r.mean_ic
        for r in metrics.itertuples()
    ]
    cutoff_metrics = pd.read_parquet(model_root / "cutoff_metrics.parquet")
    deciles = pd.read_parquet(model_root / "decile_metrics.parquet")
    importances = pd.read_parquet(model_root / "feature_importances.parquet")
    coverage = pd.read_parquet(model_root / "label_coverage.parquet")
    _comparison_file = model_root / "comparison_validation_winners.parquet"
    feature_comparison = (
        pd.read_parquet(_comparison_file) if _comparison_file.exists() else pd.DataFrame()
    )
    calibration = pd.read_parquet(model_root / "calibration.parquet")
    winners = validation_winners(model_root)
    return (
        summary,
        registry,
        metrics,
        cutoff_metrics,
        deciles,
        importances,
        model_root,
        coverage,
        feature_comparison,
        calibration,
        winners,
    )


@app.cell
def _(mo, model_root):
    _options = {"Top 10 %": 0.1}
    if (model_root / "portfolio-top03" / "summary.json").exists():
        _options["Top 3 %"] = 0.03
    portfolio_choice = mo.ui.dropdown(
        options=_options, value=list(_options)[-1], label="Titres retenus par compartiment"
    )
    mo.output.replace(portfolio_choice)
    return (portfolio_choice,)


@app.cell
def _(pd, model_root, portfolio_choice):
    _portfolio_root = (
        model_root / "portfolio-top03" if portfolio_choice.value == 0.03 else model_root
    )
    equity = pd.read_parquet(_portfolio_root / "backtest_equity.parquet")
    backtest = pd.read_parquet(_portfolio_root / "backtest_summary.parquet")
    _mixed_root = _portfolio_root / "costs-25-45"
    if (_mixed_root / "summary.json").exists():
        equity = pd.concat(
            [equity, pd.read_parquet(_mixed_root / "backtest_equity.parquet")], ignore_index=True
        )
        backtest = pd.concat(
            [backtest, pd.read_parquet(_mixed_root / "backtest_summary.parquet")], ignore_index=True
        )
    _comparison_path = model_root / "portfolio-top03" / "comparison_winners.parquet"
    concentration_comparison = (
        pd.read_parquet(_comparison_path) if _comparison_path.exists() else pd.DataFrame()
    )
    return equity, backtest, concentration_comparison


@app.cell
def _(mo, summary):
    mo.md(f"""
    # Model Lab · SPEC-008
    **Development backtest — not independent confirmation.**

    Train 2024 · validation S1 2025 · retrain 2024 + S1 2025 · test S1 2026.
    **Le lock a déjà utilisé des outcomes de 2025 et 2026 :
    ces résultats restent du développement.**
    12 tâches H5/H10 · {summary.get("feature_sets", {"strict": 85, "strong": 138})}
    · {summary["model_count"]} modèles.
    Le set « all » utilise les 1 048 entrées du registre, sans sélection par les outcomes.
    PIT reconstruit · aucune donnée ni modification de
    [SPEC-007](https://sandbox.hocus.works/quant-lab-srd/?v=spec007).
    """)
    return


@app.cell
def _(mo, registry, backtest):
    target_choice = mo.ui.dropdown(
        options=[
            "direction_abs",
            "return_abs",
            "direction_rel",
            "rank_pct",
            "excursion_balance",
            "trend_tstat",
        ],
        value="direction_abs",
        label="Target",
    )
    horizon_choice = mo.ui.dropdown(options={"H5": 5, "H10": 10}, value="H5", label="Horizon futur")
    _sets = list(dict.fromkeys(r["feature_set"] for r in registry))
    feature_choice = mo.ui.dropdown(options=_sets, value=_sets[0], label="Set de features")
    _cost_options = {"0 bp": 0, "10 bp": 10, "25 bp": 25}
    if 45 in set(backtest.cost_bp):
        _cost_options["45 bp · mixte"] = 45
    _cost_options["50 bp"] = 50
    cost_choice = mo.ui.dropdown(
        options=_cost_options,
        value="25 bp",
        label="Frais aller-retour",
    )
    mo.hstack([target_choice, horizon_choice, feature_choice, cost_choice], justify="start")
    return target_choice, horizon_choice, feature_choice, cost_choice


@app.cell
def _(mo, registry, target_choice, horizon_choice, feature_choice):
    available_models = {
        r["model"]: r["model_id"]
        for r in registry
        if r["target"] == target_choice.value
        and r["horizon"] == horizon_choice.value
        and r["feature_set"] == feature_choice.value
    }
    model_choice = mo.ui.dropdown(
        options=available_models, value="xgb", label="Modèle · XGB référence par défaut"
    )
    mo.output.replace(model_choice)
    return model_choice


@app.cell
def _(
    mo,
    pd,
    px,
    summary,
    registry,
    metrics,
    cutoff_metrics,
    deciles,
    importances,
    equity,
    backtest,
    coverage,
    feature_comparison,
    concentration_comparison,
    portfolio_choice,
    calibration,
    winners,
    target_choice,
    horizon_choice,
    feature_choice,
    cost_choice,
    model_choice,
    index_panel,
):
    _mid = model_choice.value
    _row = next(r for r in registry if r["model_id"] == _mid)
    _metrics = metrics[
        (metrics.target == target_choice.value)
        & (metrics.horizon == horizon_choice.value)
        & (metrics.feature_set == feature_choice.value)
    ]
    _test = metrics[metrics.split == "test"]
    _winner_table = winners.merge(
        _test, on=["model_id", "target", "horizon", "model", "feature_set"]
    )
    _winner_table = _winner_table.merge(
        backtest[backtest.cost_bp == cost_choice.value][
            ["model_id", "cumulative_return", "turnover", "max_drawdown"]
        ],
        on="model_id",
        validate="one_to_one",
    )
    _bt = backtest[(backtest.model_id == _mid) & (backtest.cost_bp == cost_choice.value)]
    _eq = (
        equity[(equity.model_id == _mid) & (equity.cost_bp == cost_choice.value)]
        .sort_values("session_date")
        .copy()
    )
    _eq["drawdown"] = _eq.equity / _eq.equity.cummax().clip(lower=1) - 1
    _cs = cutoff_metrics[(cutoff_metrics.model_id == _mid) & (cutoff_metrics.split == "test")]
    _ds = deciles[(deciles.model_id == _mid) & (deciles.split == "test")]
    _dd = _ds.groupby("decile", as_index=False).agg(
        mean_target=("mean_target", "mean"),
        positive_rate=("positive_rate", "mean"),
        mean_return_abs=("mean_return_abs", "mean"),
        n=("n", "sum"),
    )
    _imp = importances[importances.model_id == _mid]
    _cal = (
        calibration[(calibration.model_id == _mid) & (calibration.split == "test")]
        if "model_id" in calibration
        else pd.DataFrame()
    )
    _importance_view = (
        mo.md("Baseline : pas d’importance de feature.")
        if _imp.empty
        else mo.vstack(
            [
                mo.ui.plotly(
                    px.bar(
                        _imp.sort_values("validation_permutation_drop", ascending=False).head(20),
                        x="validation_permutation_drop",
                        y="feature_id",
                        orientation="h",
                        title="Permutation validation · 2024 fit uniquement",
                    )
                ),
                mo.ui.table(_imp, selection=None, page_size=15),
                mo.md(
                    "RF impurity / XGB gain et permutation marginale, sans causalité "
                    "ni nouvelle sélection. Une réplication ; variables corrélées."
                ),
            ]
        )
    )
    _method = mo.md(f"""
    ## Methodology
    **Development backtest — not independent confirmation.**
    Hyperparamètres choisis uniquement en validation 2025 : AUC directions, IC moyen régressions.
    Naïf train prior / mean / median ; Logistic C=1 / Ridge α=10 ; RF 2 configurations ; XGB 2.
    Imputation médiane et indicateurs + scaler fit sur train uniquement,
    puis refit sur retrain final.
    XGB conserve les NaN natifs. Zéro direction exclu des fits/métriques binaires ;
    conservé dans le ledger.

    **Dates modèle choisi :** train {_row["training_dates"][0]} → {_row["training_dates"][-1]} ;
    validation {_row["validation_dates"][0]} → {_row["validation_dates"][-1]} ;
    test {_row["test_dates"][0]} → {_row["test_dates"][-1]}.
    Purge H5/H10 sessions minimum et aucun label franchissant les frontières.

    `excursion_balance = max(P_h/P_T−1) + min(P_h/P_T−1)` sur h=1..H.
    `trend_tstat = b/SE(b)` OLS sur H closes futurs base 100, plate=0, linéaire parfaite=±1e6.

    **Simulation :** long-only, top {portfolio_choice.value * 100:.0f} %,
    next_open après feature cutoff,
    close H-ième séance commune,
    compartiments fixes 2 H5 / 3 H10, equipondération au sein du nouveau compartiment, cash à 0 %.
    Frais all-in aller-retour appliqués moitié par jambe, sans levier.
    Nombre de titres = max(1, ceil(fraction × scores finis)) ; ex æquo départagés par ISIN.
    Les scores et gagnants de validation sont identiques entre top 3 % et top 10 %.
    Les métriques IC/AUC et les déciles portent toujours sur l'univers complet.
    Le scénario 45 bp est un forfait mixte global, pas une TTF calculée titre par titre.
    Un score naïf constant donne un panier arbitraire, sans classement prédictif.
    Prix manquant : pas de fill inventé.
    Corporate actions/anomalies restent annotées ; séries raw non certifiées, univers survivant.
    **Lock utilisé :** `{summary["lock_sha256"]}`.
    Les périodes de 2025/2026 avaient déjà participé à la sélection du lock.
    Les différences entre modèles et les Sharpe S1 sont descriptifs.
    """)
    mo.ui.tabs(
        {
            "Overview": mo.vstack(
                [
                    mo.md(
                        "## Overview\nGagnants choisis sur validation uniquement ; "
                        "leurs résultats test sont lus ensuite."
                    ),
                    mo.ui.table(
                        _winner_table[
                            [
                                "target",
                                "horizon",
                                "model",
                                "feature_set",
                                "validation_metric",
                                "roc_auc",
                                "r2",
                                "mean_ic",
                                "median_ic",
                                "top10_lift",
                                "cumulative_return",
                                "turnover",
                                "max_drawdown",
                                "n",
                            ]
                        ],
                        selection=None,
                    ),
                    mo.ui.table(
                        coverage[
                            (coverage.feature_set == feature_choice.value)
                            & (coverage.target == "return_abs")
                        ],
                        selection=None,
                    ),
                    mo.vstack(
                        [
                            mo.md("### Comparaison des registres · référence top 10 %"),
                            mo.ui.table(
                                feature_comparison.drop(columns=["model_id"], errors="ignore"),
                                selection=None,
                                page_size=12,
                            ),
                        ]
                    )
                    if not feature_comparison.empty
                    else mo.md("Comparaison complète des sets disponible dans les rapports."),
                ]
            ),
            "Model Benchmark": mo.vstack(
                [
                    mo.md(
                        "## Model Benchmark\nFiltres ci-dessus. "
                        "Métriques par modèle, validation et test."
                    ),
                    mo.ui.table(_metrics, selection=None, page_size=20),
                    mo.ui.plotly(
                        px.line(
                            _cs,
                            x="cutoff",
                            y="ic",
                            markers=True,
                            title="IC test par cutoff · aucune moyenne pooled substituée",
                        )
                    ),
                    mo.ui.table(_cal, selection=None)
                    if not _cal.empty
                    else mo.md("Calibration applicable aux directions."),
                ]
            ),
            "Target Comparison": mo.vstack(
                [
                    mo.md(
                        "## Target Comparison\nSix définitions, H5 et H10, "
                        "modèle/set choisi en validation."
                    ),
                    mo.ui.table(
                        _winner_table[
                            [
                                "target",
                                "horizon",
                                "model",
                                "feature_set",
                                "validation_metric",
                                "roc_auc",
                                "r2",
                                "mean_ic",
                                "top10_lift",
                                "cumulative_return",
                                "turnover",
                                "max_drawdown",
                                "n",
                            ]
                        ],
                        selection=None,
                    ),
                ]
            ),
            "Score Deciles": mo.vstack(
                [
                    mo.md(
                        "## Score Deciles\nMoyennes par cutoff puis moyenne temporelle ; "
                        "ex æquo non séparés artificiellement."
                    ),
                    mo.ui.plotly(
                        px.bar(
                            _dd,
                            x="decile",
                            y="mean_target",
                            title="D1 → D10 · target moyenne S1 2026",
                        )
                    ),
                    mo.ui.table(_dd, selection=None),
                    mo.ui.table(_ds, selection=None, page_size=10),
                ]
            ),
            "Backtest": mo.vstack(
                [
                    mo.md(
                        f"## Backtest · top {portfolio_choice.value * 100:.0f} %\n"
                        "**Development backtest — not independent confirmation.**"
                    ),
                    mo.ui.table(_bt, selection=None),
                    mo.vstack(
                        [
                            mo.md("### Top 3 % versus top 10 % · mêmes gagnants de validation"),
                            mo.ui.table(
                                concentration_comparison[
                                    concentration_comparison.cost_bp == cost_choice.value
                                ][
                                    [
                                        "target",
                                        "horizon",
                                        "model",
                                        "cumulative_return_top3",
                                        "cumulative_return_top10",
                                        "delta_cumulative_return",
                                        "max_drawdown_top3",
                                        "max_drawdown_top10",
                                    ]
                                ],
                                selection=None,
                            ),
                        ]
                    )
                    if (
                        not concentration_comparison.empty
                        and (concentration_comparison.cost_bp == cost_choice.value).any()
                    )
                    else mo.md(""),
                    mo.ui.plotly(
                        px.line(
                            _eq,
                            x="session_date",
                            y=["equity", "benchmark_equity"],
                            title="Equity · portefeuille et CAC AllShares",
                        )
                    ),
                    mo.ui.plotly(px.line(_eq, x="session_date", y="drawdown", title="Drawdown")),
                    mo.ui.plotly(
                        px.line(
                            _eq,
                            x="session_date",
                            y=["turnover", "holding_count"],
                            title="Turnover et positions en cours",
                        )
                    ),
                    mo.ui.table(
                        backtest[
                            (backtest.model == "universe")
                            & (backtest.horizon == horizon_choice.value)
                        ],
                        selection=None,
                    ),
                ]
            ),
            "Feature Importance": _importance_view,
            "Methodology": _method,
            "Indices": index_panel,
        }
    )
    return


if __name__ == "__main__":
    app.run()
