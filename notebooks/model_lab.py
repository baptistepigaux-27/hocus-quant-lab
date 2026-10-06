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
    series_root = Path(
        os.environ.get(
            "HOCUS_INDEX_SERIES_DATA", str(baseline_root.parent / "index-series-models-v1")
        )
    )
    regimes_root = Path(
        os.environ.get("HOCUS_SBF120_REGIMES_DATA", str(baseline_root.parent / "sbf120-kmeans7-v1"))
    )
    context_root = Path(
        os.environ.get("HOCUS_SRD_CONTEXT_DATA", str(baseline_root.parent / "srd-context-v1"))
    )
    vad_root = Path(
        os.environ.get(
            "HOCUS_SRD_VAD_DATA", str(baseline_root.parent / "srd-portfolio-extensions-v1")
        )
    )
    short_root = Path(
        os.environ.get("HOCUS_SRD_SHORT_DATA", str(baseline_root.parent / "srd-short-horizons-v1"))
    )
    return (
        mo,
        pd,
        px,
        json,
        Path,
        baseline_root,
        all_features_root,
        index_root,
        series_root,
        regimes_root,
        context_root,
        vad_root,
        short_root,
    )


@app.cell
def _(mo):
    short_horizon = mo.ui.dropdown(
        options={"H1 · une séance": 1, "H2 · deux séances": 2, "H3 · trois séances": 3},
        value="H1 · une séance",
        label="Horizon d'apprentissage",
    )
    short_target = mo.ui.dropdown(
        options={
            "Direction absolue": "direction_abs",
            "Direction relative": "direction_rel",
            "Rendement absolu": "return_abs",
            "Rang du rendement": "rank_pct",
            "Équilibre des excursions": "excursion_balance",
            "Tendance / erreur-type (H3 uniquement)": "trend_tstat",
        },
        value="Rang du rendement",
        label="Target",
    )
    short_cost = mo.ui.dropdown(
        options={"Brut · 0 bp": 0, "Net · 25 bp AR": 25, "Net · 45 bp AR": 45},
        value="Brut · 0 bp",
        label="Frais",
    )
    return short_horizon, short_target, short_cost


@app.cell
def _(mo, pd, px, short_root, short_horizon, short_target, short_cost):
    _controls = mo.hstack([short_horizon, short_target, short_cost], justify="start")
    if not (short_root / "report_complete.json").exists():
        short_panel = mo.md("## Horizons courts\nModèles actions H1/H2/H3 en préparation.")
    else:
        _comparisons = pd.read_parquet(short_root / "comparison_winners.parquet")
        _comparisons = _comparisons[_comparisons.cost_bp == short_cost.value]
        _selection = _comparisons[
            (_comparisons.horizon == short_horizon.value)
            & (_comparisons.target == short_target.value)
        ]
        _overview = _comparisons[
            [
                "target",
                "horizon",
                "model",
                "test_ic",
                "test_auc",
                "cumulative_return_native",
                "cumulative_return_h5",
                "max_drawdown_native",
                "max_drawdown_h5",
            ]
        ].copy()
        for _column in [
            "cumulative_return_native",
            "cumulative_return_h5",
            "max_drawdown_native",
            "max_drawdown_h5",
        ]:
            _overview[_column] *= 100
        _overview = _overview.rename(
            columns={
                "target": "Target",
                "horizon": "H",
                "model": "Modèle validation",
                "test_ic": "IC target",
                "test_auc": "AUC",
                "cumulative_return_native": "Performance sortie H (%)",
                "cumulative_return_h5": "Performance sortie H5 (%)",
                "max_drawdown_native": "Drawdown H (%)",
                "max_drawdown_h5": "Drawdown H5 (%)",
            }
        ).round(4)
        _overview["Target"] = _overview["Target"].map(
            {
                "direction_abs": "Direction absolue",
                "direction_rel": "Direction relative",
                "return_abs": "Rendement absolu",
                "rank_pct": "Rang du rendement",
                "excursion_balance": "Équilibre des excursions",
                "trend_tstat": "Tendance / erreur-type",
            }
        )
        _detail = mo.md("Tendance / erreur-type indéfinie à H1/H2 ; disponible à H3.")
        if not _selection.empty:
            _selected = _selection.iloc[0]
            _mid = _selected.model_id
            _curves = pd.read_parquet(short_root / "backtest_equity.parquet")
            _curves = _curves[
                (_curves.model_id.isin([_mid, f"universe-h{short_horizon.value}"]))
                & (_curves.cost_bp == short_cost.value)
            ].copy()
            _curves["Simulation"] = (
                _curves.model.map({"universe": "Univers équipondéré"}).fillna("Top 3 %")
                + " · détention H"
                + _curves.holding_horizon.astype(str)
            )
            _stats = pd.read_parquet(short_root / "winners_summary.parquet")
            _stats = _stats[(_stats.model_id == _mid) & (_stats.cost_bp == short_cost.value)]
            _basket = pd.read_parquet(short_root / "basket_metrics.parquet")
            _basket = _basket[(_basket.model_id == _mid) & _basket.common_cutoff].copy()
            _basket["Rendement panier brut (%)"] = 100 * _basket.gross_basket_return
            _basket["Détention"] = "H" + _basket.holding_horizon.astype(str)
            _metrics = pd.read_parquet(short_root / "metrics.parquet")
            _metrics = _metrics[
                (_metrics.target == short_target.value)
                & (_metrics.horizon == short_horizon.value)
                & (_metrics.split == "test")
            ]
            _concentration = pd.read_parquet(short_root / "concentration_winners.parquet")
            _concentration = _concentration[_concentration.model_id == _mid]
            _concentration = _concentration[
                [
                    "holding_horizon",
                    "total_gross_contribution",
                    "top5_trade_contribution",
                    "review_trade_count",
                    "review_trade_contribution",
                ]
            ].copy()
            for _c in [
                "total_gross_contribution",
                "top5_trade_contribution",
                "review_trade_contribution",
            ]:
                _concentration[_c] *= 100
            _detail = mo.vstack(
                [
                    mo.md(
                        f"### {_selected.model} · H{short_horizon.value}\n"
                        "Modèle choisi sur S1 2025 ; aucune sélection sur la performance 2026."
                    ),
                    mo.ui.plotly(
                        px.line(
                            _curves,
                            x="session_date",
                            y="equity",
                            color="Simulation",
                            title="Capital simulé · base 1 · mêmes scores",
                        )
                    ),
                    mo.ui.plotly(
                        px.line(
                            _curves,
                            x="session_date",
                            y="active_session_capital",
                            color="Simulation",
                            title="Capital actif par séance",
                        )
                    ),
                    mo.ui.table(
                        _stats[
                            [
                                "holding_horizon",
                                "cumulative_return",
                                "max_drawdown",
                                "average_active_session_capital",
                                "average_exposure",
                                "missing_entries",
                                "delayed_exits",
                                "unresolved_exits",
                            ]
                        ],
                        selection=None,
                    ),
                    mo.md(
                        "### Rendements bruts des paniers · 23 dates communes\n"
                        "Le graphe reste avant frais même si le scénario de portefeuille est net."
                    ),
                    mo.ui.plotly(
                        px.bar(
                            _basket,
                            x="cutoff",
                            y="Rendement panier brut (%)",
                            color="Détention",
                            barmode="group",
                        )
                    ),
                    mo.md("### Association après l'open et gap préalable"),
                    mo.ui.table(
                        _selection[
                            [
                                "test_ic",
                                "execution_ic_native",
                                "execution_ic_h5",
                                "gap_ic",
                                "matched_basket_native",
                                "matched_basket_h5",
                                "matched_excess_native",
                                "matched_excess_h5",
                            ]
                        ],
                        selection=None,
                    ),
                    mo.md("### Toutes les variantes de cette target · métriques test"),
                    mo.ui.table(_metrics, selection=None),
                    mo.md(
                        "### Concentration du PnL brut · points du capital initial\n"
                        "Les variations marquées en revue restent incluses. Les cinq meilleurs "
                        "trades peuvent expliquer une grande partie du résultat ; leur cause "
                        "n'est pas certifiée par ces prix source."
                    ),
                    mo.ui.table(_concentration.round(4), selection=None),
                ]
            )
        short_panel = mo.vstack(
            [
                mo.md(
                    "## Horizons courts · actions seules\n"
                    "**1 048 features, 74 modèles, 16 tâches.** Train 2024, choix S1 2025, "
                    "lecture S1 2026. Top 3 % acheté, entrée au prochain open, "
                    "sortie H ou H5. Deux compartiments, sans levier ni VAD. "
                    "Décisions hebdomadaires ; H1 ne signifie pas un score quotidien."
                ),
                _controls,
                mo.ui.table(_overview, selection=None),
                _detail,
                mo.md(
                    "### Lecture\n"
                    "À H1, l'exposition en fin de séance est nulle car entrée et sortie ont "
                    "lieu le même jour. Le capital actif inclut cette séance. "
                    "H5 mobilise plus longtemps le capital : comparer aussi les paniers "
                    "et l'univers équipondéré. L'IC de target close-à-close comprend le "
                    "gap préalable à l'entrée ; l'IC après open mesure le rendement continu "
                    "exécutable. Excursions H1 = 2 × rendement H1. Prix bruts, "
                    "PIT reconstruit, frais forfaitaires, période déjà explorée."
                ),
            ]
        )
    return (short_panel,)


@app.cell
def _(mo):
    vad_cost = mo.ui.dropdown(
        options={"25 bp": 25, "45 bp": 45}, value="25 bp", label="Frais aller-retour · VAD"
    )
    vad_borrow = mo.ui.dropdown(
        options={"0 % annuel": 0.0, "3 % annuel": 0.03},
        value="3 % annuel",
        label="Hypothèse de prêt des titres",
    )
    vad_target = mo.ui.dropdown(
        options=[
            "direction_abs",
            "return_abs",
            "direction_rel",
            "rank_pct",
            "excursion_balance",
            "trend_tstat",
        ],
        value="rank_pct",
        label="Target · actions seules",
    )
    vad_horizon = mo.ui.dropdown(
        options={"Modèle H5 → détention H5/H10": 5, "Modèle H10 → détention H10/H20": 10},
        value="Modèle H5 → détention H5/H10",
        label="Horizon du modèle",
    )
    vad_holding = mo.ui.dropdown(
        options={"Initiale": 1, "Prolongée": 2},
        value="Prolongée",
        label="Détention du ledger détaillé",
    )
    return vad_cost, vad_borrow, vad_target, vad_horizon, vad_holding


@app.cell
def _(mo, pd, px, vad_root, vad_cost, vad_borrow, vad_target, vad_horizon, vad_holding):
    if not (vad_root / "report_complete.json").exists():
        vad_panel = mo.md("## VAD et détention\nReplays des modèles actions seuls en préparation.")
    else:
        _comp = pd.read_parquet(vad_root / "comparison_winners.parquet")
        _comp = _comp[
            (_comp.cost_bp == vad_cost.value) & (_comp.borrow_rate_annual == vad_borrow.value)
        ]
        _view = _comp[["target", "horizon", "extended_horizon", "model"]].rename(
            columns={
                "target": "Target",
                "horizon": "H modèle",
                "extended_horizon": "Détention prolongée",
                "model": "Modèle",
            }
        )
        for _phase, _phase_label in [("native", "initiale"), ("extended", "prolongée")]:
            for _strategy, _label in [("long_only", "Achat"), ("long_short", "Achat/VAD")]:
                _view[f"{_label} · {_phase_label} (%)"] = (
                    100 * _comp[f"{_phase}_{_strategy}_cumulative_return"]
                ).round(2)
        _chosen = _comp[
            (_comp.target == vad_target.value) & (_comp.horizon == vad_horizon.value)
        ].iloc[0]
        _all = pd.read_parquet(vad_root / "winners_summary.parquet")
        _selected = _all[
            (_all.model_id == _chosen.model_id)
            & (_all.cost_bp == vad_cost.value)
            & ((_all.strategy == "long_only") | (_all.borrow_rate_annual == vad_borrow.value))
        ]
        _curve = pd.read_parquet(vad_root / "backtest_equity.parquet")
        _curve = _curve[_curve.simulation_id.isin(_selected.simulation_id)].copy()
        _curve["Portefeuille"] = (
            _curve.strategy.map({"long_only": "Achat", "long_short": "Achat/VAD"})
            + " · détention H"
            + _curve.holding_horizon.astype(str)
        )
        _risk = _selected[
            [
                "holding_horizon",
                "strategy",
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
        ].copy()
        for _column in [
            "cumulative_return",
            "max_drawdown",
            "average_exposure",
            "average_net_exposure",
            "long_contribution",
            "short_contribution",
            "fees",
            "borrow_fees",
        ]:
            _risk[_column] = (100 * _risk[_column]).round(3)
        _hold = vad_horizon.value * vad_holding.value
        _details = _selected[
            (_selected.strategy == "long_short") & (_selected.holding_horizon == _hold)
        ].iloc[0]
        _stocks = pd.read_parquet(vad_root / "stock_contributions.parquet")
        _stocks = _stocks[_stocks.simulation_id == _details.simulation_id].copy()
        _stocks["Contribution nette (points %)"] = (100 * _stocks.contribution_net).round(3)
        _trades = pd.read_parquet(vad_root / "backtest_trades.parquet")
        _trades = _trades[_trades.simulation_id == _details.simulation_id]
        vad_panel = mo.vstack(
            [
                mo.md("""
            ## VAD et détention
            **Modèles actions seuls · 1 048 variables · aucun contexte de marché.**
            Scores et 12 gagnants choisis sur validation 2025 inchangés, aucun nouveau fit.
            Achat/VAD : top 3 % acheté + flop 3 % vendu à découvert, **50/50 sans levier**.
            Décisions S1 2026 ; liquidations suivies jusqu'au 31 juillet. Rendements cumulés.
            Les contrôles de cet onglet sont indépendants des sélecteurs situés au-dessus.
            """),
                mo.hstack([vad_cost, vad_borrow], justify="start"),
                mo.md("### Comparaison des douze gagnants · même capital initial"),
                mo.ui.table(_view, selection=None, page_size=12),
                mo.hstack([vad_target, vad_horizon], justify="start"),
                mo.ui.plotly(
                    px.line(
                        _curve,
                        x="session_date",
                        y="equity",
                        color="Portefeuille",
                        title="NAV · mêmes scores, quatre portefeuilles",
                    )
                ),
                mo.md("### Risque et contributions · valeurs en % du capital ou de l'exposition"),
                mo.ui.table(_risk, selection=None),
                mo.md(
                    "Les contributions des achats et shorts s'additionnent au rendement net. "
                    "Les frais sont rapportés au capital initial. "
                    "L'exposition est celle effectivement investie."
                ),
                mo.md("### Actions et ledger · portefeuille achat/VAD"),
                vad_holding,
                mo.ui.table(
                    _stocks[
                        [
                            "side",
                            "display_name",
                            "entity_id",
                            "selections",
                            "closed",
                            "Contribution nette (points %)",
                        ]
                    ].sort_values("Contribution nette (points %)", ascending=False),
                    selection=None,
                    page_size=15,
                ),
                mo.ui.table(
                    _trades[
                        [
                            "cutoff",
                            "entity_id",
                            "side",
                            "entry_date",
                            "scheduled_exit",
                            "exit_date",
                            "entry_price",
                            "exit_price",
                            "shares",
                            "return_net",
                            "entry_fee",
                            "exit_fee",
                            "borrow_fees",
                            "pnl_net",
                            "status",
                            "future_quality",
                        ]
                    ].round(6),
                    selection=None,
                    page_size=15,
                ),
                mo.md("""
            Deux/trois/cinq compartiments pour détention H5/H10/H20 :
            la durée modifie aussi le temps investi.
            Produits de vente bloqués, frais d'emprunt calculés en jours calendaires/365.
            3 % annuel est une hypothèse, pas un tarif observé.
            Disponibilité historique de prêt, dividendes à payer et marge non simulés.
            Compartiments séparés sans netting entre vintages.
            Scores naïfs constants : départage arbitraire par ISIN.
            Prix raw et univers reconstruits.
            Résultats de développement, sans confirmation indépendante.
            """),
            ]
        )
    return (vad_panel,)


@app.cell
def _(mo, pd, context_root):
    if (context_root / "context_report_complete.json").exists():
        _scores = pd.read_parquet(context_root / "context/scores.parquet", columns=["cutoff"])
        _days = sorted(map(str, _scores.cutoff.unique()))
    else:
        _days = ["En préparation"]
    context_day = mo.ui.dropdown(options=_days, value=_days[-1], label="Date du contexte SRD")
    return (context_day,)


@app.cell
def _(mo, pd, px, context_root, context_day):
    if not (context_root / "context_report_complete.json").exists():
        context_panel = mo.md("## Contextes SRD\nExpérience enrichie en préparation.")
    else:
        _overview = pd.read_parquet(context_root / "comparison_validation_winners.parquet")
        _delta = pd.read_parquet(context_root / "comparison_baseline.parquet")
        _confidence = pd.read_parquet(context_root / "comparison_confidence.parquet")
        _coverage = pd.read_parquet(context_root / "context_coverage.parquet")
        _importance = pd.read_parquet(context_root / "context_importance_shares.parquet")
        _scores = pd.read_parquet(context_root / "context/scores.parquet")
        _scores = _scores[_scores.cutoff.astype(str) == context_day.value]
        _scores = _scores.assign(
            Bloc=_scores.feature_id.str.split(".").str[1],
        )
        _compact = _delta[["target", "horizon", "model_baseline", "model_context"]].rename(
            columns={
                "target": "Target",
                "horizon": "H",
                "model_baseline": "Référence",
                "model_context": "Enrichi",
            }
        )
        for _cost in (25, 45):
            for _variant, _label in [("baseline", "référence"), ("context", "enrichi")]:
                _compact[f"Net {_cost} bp · {_label} (%)"] = (
                    100 * _delta[f"cumulative_return_{_cost}bp_{_variant}"]
                ).round(2)
        _gains = int((_delta.delta_cumulative_return_25bp > 0).sum())
        _robust = int((_confidence.groupby(["target", "horizon"]).delta_ic_lo90.min() > 0).sum())
        context_panel = mo.vstack(
            [
                mo.md("""
            ## Contextes SRD
            **1 404 variables : 1 048 propres aux actions et 356 contextes de marché.**
            Sept régimes SBF 120 ancrés sur 2023, distances et prévisions par régime ;
            prévisions H5/H10 des 27 indices sectoriels, CAC40 et SBF120.
            Producteurs ajustés avant chaque trimestre ; seuls les labels déjà matures entrent
            dans le fit. Contexte test 2026 figé avec information antérieure à juillet 2025.
            Les vecteurs sectoriels sont partagés par toutes les actions de la date.
            """),
                mo.md("### Référence 1 048 variables et modèle enrichi · mêmes observations test"),
                mo.md(
                    f"**{_gains}/12 gagnants améliorent leur rendement net à 25 bp.** "
                    f"{_robust} gain d'IC possède trois intervalles 90 % entièrement positifs. "
                    "Rendements cumulés S1 2026, non annualisés ; top 3 %."
                ),
                mo.ui.table(_compact, selection=None, page_size=12),
                mo.md("### Métriques détaillées de tous les gagnants"),
                mo.ui.table(
                    _overview[
                        [
                            "target",
                            "horizon",
                            "feature_set",
                            "model",
                            "validation_metric",
                            "mean_ic",
                            "roc_auc",
                            "r2",
                            "n",
                            "cumulative_return_25bp",
                            "cumulative_return_45bp",
                            "max_drawdown_45bp",
                        ]
                    ].round(5),
                    selection=None,
                    page_size=24,
                ),
                mo.md("### Écarts contexte moins référence · gagnants choisis sur validation"),
                mo.ui.table(
                    _delta[
                        [
                            "target",
                            "horizon",
                            "model_context",
                            "model_baseline",
                            "delta_mean_ic",
                            "paired_ic_cutoffs",
                            "paired_delta_ic",
                            "delta_roc_auc",
                            "delta_r2",
                            "delta_cumulative_return_25bp",
                            "delta_cumulative_return_45bp",
                        ]
                    ].round(5),
                    selection=None,
                ),
                mo.md("### Incertitude de l'écart d'IC · blocs de 2/4/6 cutoffs"),
                mo.ui.table(_confidence.round(5), selection=None, page_size=12),
                mo.md("### Disponibilité historique des contextes"),
                mo.ui.table(_coverage, selection=None),
                mo.md("### Ledger : contextes disponibles à la date choisie"),
                context_day,
                mo.ui.table(
                    _scores[
                        [
                            "feature_id",
                            "value",
                            "source_available_at",
                            "fit_information_available_at",
                            "max_training_label_available_at",
                            "source_quote_date",
                            "quote_age_days",
                            "fold",
                            "producer_id",
                            "status",
                        ]
                    ],
                    selection=None,
                    page_size=15,
                ),
                mo.md("### Importance des blocs · descriptif"),
                mo.ui.plotly(
                    px.box(
                        _importance,
                        x="block",
                        y="importance_share",
                        color="model",
                        title="Parts de gain/impurity du fit SRD train 2024",
                    )
                ),
                mo.md("""
            Les centres 2023 constituent une variante historique du K-means ; leur C1…C7
            diffèrent du fit 2024 de l'onglet « SBF 120 · régimes ». L'ajout change le jeu
            d'information du modèle. Les gagnants de référence et enrichis sont sélectionnés
            séparément sur 2025. Intervalles individuels 90 %, sans correction multiple.
            Les écarts appariés d'IC utilisent seulement les dates où les deux IC existent.
            Décision commune : minuit UTC D+1, jointure as-of avant prochain open.
            Les absences de contexte restent NaN et aucune action n'est retirée.
            Top 3 %, frais forfaitaires 25/45 bp ; périodes déjà explorées, PIT reconstruit.
            """),
            ]
        )
    return (context_panel,)


@app.cell
def _(mo):
    regimes_period = mo.ui.dropdown(
        options={"Train 2024": "train", "Validation S1 2025": "validation", "Test S1 2026": "test"},
        value="Test S1 2026",
        label="Période des régimes",
    )
    regimes_target = mo.ui.dropdown(
        options={"Direction": "direction", "Rendement": "return", "Volatilité": "volatility"},
        value="Volatilité",
        label="Résultat futur par régime",
    )
    regimes_horizon = mo.ui.dropdown(
        options={"H5": 5, "H10": 10}, value="H5", label="Horizon régimes"
    )
    return regimes_period, regimes_target, regimes_horizon


@app.cell
def _(mo, pd, px, json, regimes_root, regimes_period, regimes_target, regimes_horizon):
    if not (regimes_root / "report_complete.json").exists():
        regimes_panel = mo.md("## SBF 120 · régimes\nK-means à sept clusters en préparation.")
    else:
        _summary = json.loads((regimes_root / "summary.json").read_text())
        _dates = pd.read_parquet(regimes_root / "assignments.parquet")
        _dates = _dates[_dates.period == regimes_period.value].copy()
        _dates["Régime"] = "C" + _dates.cluster.astype(str)
        _centers = pd.read_parquet(regimes_root / "centers.parquet")
        _occupancy = pd.read_parquet(regimes_root / "occupancy.parquet")
        _profiles = pd.read_parquet(regimes_root / "outcome_profiles.parquet")
        _profiles = _profiles[
            (_profiles.period == regimes_period.value)
            & (_profiles.target == regimes_target.value)
            & (_profiles.horizon == regimes_horizon.value)
        ]
        _lookup = pd.read_parquet(regimes_root / "lookup.parquet")
        _profiles = _profiles.merge(
            _lookup, on=["cluster", "target", "horizon"], validate="one_to_one"
        )
        _metrics = pd.read_parquet(regimes_root / "metrics.parquet")
        _metrics = _metrics[
            (_metrics.target == regimes_target.value) & (_metrics.horizon == regimes_horizon.value)
        ]
        _confidence = pd.read_parquet(regimes_root / "confidence.parquet")
        _predictions = pd.read_parquet(regimes_root / "predictions.parquet")
        _predictions = _predictions[
            (_predictions.target == regimes_target.value)
            & (_predictions.horizon == regimes_horizon.value)
            & (_predictions.split == regimes_period.value)
        ].copy()
        if regimes_target.value == "direction":
            _predictions["Observé"] = _predictions.target_value.map({-1.0: 0.0, 1.0: 1.0})
            _predictions["Prévision"] = _predictions.score
            _predictions["Référence"] = _predictions.reference_score
        else:
            _predictions["Observé"] = 100 * _predictions.target_value
            _predictions["Prévision"] = 100 * _predictions.score
            _predictions["Référence"] = 100 * _predictions.reference_score
        regimes_panel = mo.vstack(
            [
                mo.md("""
            ## SBF 120 · régimes
            **K-means à sept clusters sur les dates de l'indice SBF 120.**
            22 variables historiques standardisées. Centres et tables de prévision figés sur
            2024, appliqués sans réapprentissage à 2025/2026. Les clusters représentent des états
            du marché. Leur numéro est une catégorie, pas une intensité de signal.
            """),
                mo.hstack([regimes_period, regimes_target, regimes_horizon], justify="start"),
                mo.md(
                    f"Silhouette train : **{_summary['train_silhouette']:.3f}**. "
                    "Séparation géométrique des groupes ; aucune preuve de prédictivité."
                ),
                mo.ui.plotly(
                    px.scatter(
                        _dates,
                        x="cutoff",
                        y="reference_close",
                        color="Régime",
                        category_orders={"Régime": [f"C{_i}" for _i in range(1, 8)]},
                        hover_data=["nearest_distance", "outside_train_distance_q95"],
                        title="SBF 120 : dates et régimes assignés avec les centres 2024",
                    )
                ),
                mo.md("### Profils des sept centres · unités natives"),
                mo.ui.table(_centers, selection=None),
                mo.md("### Occupation et distance au support train"),
                mo.ui.table(_occupancy[_occupancy.period == regimes_period.value], selection=None),
                mo.md(
                    "Hors support : distance au centre le plus proche supérieure au quantile 95 % "
                    "des distances train. Aucun jour n'est exclu. "
                    "Les distances ne sont pas des probabilités."
                ),
                mo.md("### Résultats futurs par groupe et prévision apprise sur 2024"),
                mo.ui.table(_profiles, selection=None),
                mo.md(
                    "`outcome_mean` direction = fréquence de hausse. "
                    "Rendements et volatilités en fractions."
                ),
                mo.md("### Prévisions et références · mêmes centres sur les trois périodes"),
                mo.ui.table(_metrics, selection=None),
                mo.ui.plotly(
                    px.line(
                        _predictions,
                        x="cutoff",
                        y=["Prévision", "Observé", "Référence"],
                        title="Probabilité de hausse"
                        if regimes_target.value == "direction"
                        else "Valeurs en %",
                    )
                ),
                mo.md("### Intervalles individuels 90 % · test 2026"),
                mo.ui.table(
                    _confidence[
                        (_confidence.target == regimes_target.value)
                        & (_confidence.horizon == regimes_horizon.value)
                    ],
                    selection=None,
                ),
                mo.md("### Ledger des affectations et prévisions"),
                mo.ui.table(
                    _predictions.drop(columns=["Prévision", "Observé", "Référence"]),
                    selection=None,
                    page_size=12,
                ),
                mo.md("""
            Tables : moyenne de chaque cluster, shrinkage vers la moyenne train (20 labels),
            fallback si moins de 10 labels. Aucun label 2025/2026 ne choisit les centres ou tables.
            Train = ajustement, pas une performance hors période. Modèles supervisés antérieurs :
            retrain jusqu'à juin 2025, budget d'information différent.
            Bootstrap par blocs H/2H/4H, centres figés, sans correction multiple.
            Export : sept indicatrices, sept distances et six prévisions, S1 2025/S1 2026.
            PIT reconstruit. La variante historique ancrée 2023 est intégrée dans
            « Contextes SRD » ; cette expérience conserve les centres 2024.
            Aucune confirmation indépendante.
            """),
            ]
        )
    return (regimes_panel,)


@app.cell
def _(mo):
    series_index = mo.ui.dropdown(
        options={
            "CAC40": "FR0003500008",
            "SBF 120": "FR0003999481",
            "S&P 500": "ABC003500387",
            "DAX40": "DE0008469008",
            "FTSE 100": "ABC003500452",
        },
        value="CAC40",
        label="Indice · modèle temporel individuel",
    )
    series_target = mo.ui.dropdown(
        options={"Direction": "direction", "Rendement": "return", "Volatilité": "volatility"},
        value="Direction",
        label="Prévision temporelle",
    )
    series_horizon = mo.ui.dropdown(
        options={"H5": 5, "H10": 10}, value="H5", label="Horizon temporel"
    )
    return series_index, series_target, series_horizon


@app.cell
def _(mo, pd, px, series_root, series_index, series_target, series_horizon):
    if not (series_root / "report_complete.json").exists():
        series_panel = mo.md("## Grands marchés\nModèles temporels individuels en préparation.")
    else:
        _overview = pd.read_parquet(series_root / "overview.parquet")
        _metrics = pd.read_parquet(series_root / "metrics.parquet")
        _predictions = pd.read_parquet(series_root / "predictions.parquet")
        _confidence = pd.read_parquet(series_root / "confidence.parquet")
        _choice = _overview[
            (_overview.index_code == series_index.value)
            & (_overview.target == series_target.value)
            & (_overview.horizon == series_horizon.value)
        ]
        _mid = _choice.model_id.iloc[0]
        _pred = (
            _predictions[(_predictions.model_id == _mid) & (_predictions.split == "test")]
            .sort_values("cutoff")
            .copy()
        )
        if series_target.value == "direction":
            _pred["Résultat observé"] = _pred.target_value.map({-1.0: 0.0, 1.0: 1.0})
            _pred["Prévision"] = _pred.score
            _pred["Référence"] = _pred.reference_score
            _label = "Probabilité de hausse / direction observée"
        else:
            _pred["Résultat observé"] = 100 * _pred.target_value
            _pred["Prévision"] = 100 * _pred.score
            _pred["Référence"] = 100 * _pred.reference_score
            _label = (
                "Rendement futur (%)"
                if series_target.value == "return"
                else "Volatilité future annualisée (%)"
            )
        series_panel = mo.vstack(
            [
                mo.md("""
            ## Grands marchés · modèles temporels individuels
            **Un estimateur distinct apprend sur les dates d'un seul indice.**
            CAC40, SBF120, S&P500, DAX40, FTSE100 · 22 variables historiques de close.
            Direction, rendement et volatilité H5/H10 · coupes quotidiennes sur le calendrier CAC40.
            Train 2024, validation S1 2025, retrain, test S1 2026 · purge et préparation train-only.
            Les métriques portent sur les dates de l'indice choisi : AUC et corrélation temporelles.
            Les observations futures quotidiennes se chevauchent.
            Les résultats restent exploratoires.
            """),
                mo.hstack([series_index, series_target, series_horizon], justify="start"),
                mo.md("### Modèle choisi sur validation · performance test 2026"),
                mo.ui.table(
                    _choice[
                        [
                            "index_name",
                            "target",
                            "horizon",
                            "model",
                            "n",
                            "roc_auc",
                            "temporal_spearman",
                            "rmse",
                            "reference_rmse",
                            "skill",
                            "primary_lo90",
                            "primary_hi90",
                            "loss_advantage_lo90",
                            "loss_advantage_hi90",
                        ]
                    ],
                    selection=None,
                ),
                mo.md(
                    "Skill = 1 − perte modèle / perte référence. "
                    "Une valeur ≤0 indique aucune amélioration avec ce critère."
                ),
                mo.ui.plotly(
                    px.line(
                        _pred,
                        x="cutoff",
                        y=["Prévision", "Résultat observé", "Référence"],
                        title=_label,
                    )
                ),
                mo.md("### Tous les modèles · validation et test"),
                mo.ui.table(
                    _metrics[
                        (_metrics.index_code == series_index.value)
                        & (_metrics.target == series_target.value)
                        & (_metrics.horizon == series_horizon.value)
                    ],
                    selection=None,
                    page_size=12,
                ),
                mo.md("### Incertitude temporelle · trois tailles de blocs"),
                mo.ui.table(_confidence[_confidence.model_id == _mid], selection=None),
                mo.md("### Ledger des prévisions · données de référence et résultats futurs"),
                mo.ui.table(
                    _pred[
                        [
                            "cutoff",
                            "reference_quote_date",
                            "reference_close",
                            "score",
                            "reference_score",
                            "target_value",
                            "target_end",
                            "index_quote_end",
                            "label_status",
                        ]
                    ],
                    selection=None,
                    page_size=12,
                ),
                mo.md("""
            Références : fréquence de hausse historique, rendement zéro, volatilité historique H.
            Sélection sur log-loss pour direction, RMSE pour les régressions.
            Une référence peut gagner. Intervalles individuels 90 %, sans correction multiple,
            conditionnels aux modèles ajustés. Cet onglet conserve les exports test 2026 initiaux.
            Leur variante historique intégrée est dans « Contextes SRD ».
            Prix et timestamps reconstruits ;
            aucune confirmation indépendante revendiquée.
            """),
            ]
        )
    return (series_panel,)


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
            Le raccordement historique utilise des producteurs antérieurs dans
            « Contextes SRD ». Cet onglet conserve l'expérience indices initiale.
            La version corrigée utilise minuit UTC D+1 et des horizons sur le calendrier CAC40.
            Les trous source rendent les labels indisponibles, sans remplacer l'indice choisi.
            Les snapshots SRD portent déjà minuit Paris ; leur coupe historique est cohérente.
            """),
            ]
        )
    return (index_panel,)


@app.cell
def _(mo, baseline_root, all_features_root, context_root, vad_root):
    _options = {"Strict 85 / Strong 138": str(baseline_root)}
    if (all_features_root / "summary.json").exists():
        _options["Toutes les variables · 1 048 features"] = str(all_features_root)
    if (context_root / "context_report_complete.json").exists():
        _options["Actions + contextes · 1 404 features"] = str(context_root)
    experiment_choice = mo.ui.dropdown(
        options=_options,
        value="Toutes les variables · 1 048 features"
        if (vad_root / "report_complete.json").exists()
        else list(_options)[-1],
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
def _(mo, json, model_root):
    _config = json.loads((model_root / "experiment_config.json").read_text())
    _fraction = _config.get("portfolio_top_fraction", 0.1)
    _options = {f"Top {_fraction * 100:.0f} %": _fraction}
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
        model_root / "portfolio-top03"
        if portfolio_choice.value == 0.03
        and (model_root / "portfolio-top03" / "summary.json").exists()
        else model_root
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
    _sets = summary.get("feature_sets", {"strict": 85, "strong": 138})
    _feature_text = " / ".join(f"{name} : {count:,} variables" for name, count in _sets.items())
    mo.md(f"""
    # Model Lab · SPEC-008
    **Development backtest — not independent confirmation.**

    Train 2024 · validation S1 2025 · retrain 2024 + S1 2025 · test S1 2026.
    **Le lock a déjà utilisé des outcomes de 2025 et 2026 :
    ces résultats restent du développement.**
    12 tâches H5/H10 · {_feature_text}
    · {summary["model_count"]} modèles.
    Le set « all » utilise les 1 048 entrées du registre, sans sélection par les outcomes.
    Le set « context » y ajoute 356 contextes historiques d'indices et de régimes.
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
    _cost_options = {
        "45 bp · mixte" if _cost == 45 else f"{_cost} bp": _cost
        for _cost in sorted(set(backtest.cost_bp))
    }
    cost_choice = mo.ui.dropdown(
        options=_cost_options,
        value="25 bp",
        label="Frais aller-retour",
    )
    mo.hstack([target_choice, horizon_choice, feature_choice, cost_choice], justify="start")
    return target_choice, horizon_choice, feature_choice, cost_choice


@app.cell
def _(mo, registry, target_choice, horizon_choice, feature_choice):
    _entries = [
        r
        for r in registry
        if r["target"] == target_choice.value
        and r["horizon"] == horizon_choice.value
        and r["feature_set"] == feature_choice.value
    ]
    available_models = {r["model"]: r["model_id"] for r in _entries}
    _eligible = [r for r in _entries if r["validation_metric"] is not None]
    _default = max(_eligible, key=lambda r: r["validation_metric"])["model"]
    model_choice = mo.ui.dropdown(
        options=available_models, value=_default, label="Modèle · gagnant de validation par défaut"
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
    series_panel,
    regimes_panel,
    context_panel,
    vad_panel,
    short_panel,
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
    _importance_column = (
        "validation_permutation_drop"
        if not _imp.empty and _imp.validation_permutation_drop.notna().any()
        else "gain_or_impurity"
    )
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
                        _imp.sort_values(_importance_column, ascending=False).head(20),
                        x=_importance_column,
                        y="feature_id",
                        orientation="h",
                        title="Importance descriptive · fit 2024 uniquement",
                    )
                ),
                mo.ui.table(_imp, selection=None, page_size=15),
                mo.md(
                    "RF impurity / XGB gain ; permutation affichée seulement lorsqu'elle "
                    "a été calculée. Aucune permutation pour l'expérience enrichie. "
                    "Descriptif, sans causalité ; variables corrélées."
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
    Pour les replays de concentration d'un même modèle, scores et gagnants ne changent pas.
    L'expérience enrichie ajoute 356 contextes historiques ; ses propres gagnants
    sont choisis sur validation, puis simulés en top 3 %.
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
                            mo.md("### Comparaison des jeux de variables · expériences publiées"),
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
            "Grands marchés": series_panel,
            "SBF 120 · régimes": regimes_panel,
            "Contextes SRD": context_panel,
            "VAD et détention": vad_panel,
            "Horizons courts": short_panel,
        }
    )
    return


if __name__ == "__main__":
    app.run()
