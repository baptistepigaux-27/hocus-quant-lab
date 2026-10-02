import marimo

__generated_with = "0.25.0"
app = marimo.App(width="wide")


@app.cell
def _():
    import os
    from datetime import date, datetime, time
    from pathlib import Path
    from zoneinfo import ZoneInfo

    import duckdb
    import marimo as mo
    import plotly.express as px

    database_path = Path(
        os.environ.get(
            "HOCUS_QUANT_DB",
            Path(__file__).resolve().parents[1] / "data" / "research.duckdb",
        )
    )
    mo.stop(
        not database_path.is_file(),
        mo.md(
            f"""
            # Explorateur Quant Lab

            Base DuckDB introuvable : `{database_path}`.

            Importez d’abord les snapshots avec les commandes du README, ou définissez
            `HOCUS_QUANT_DB` vers votre base locale.
            """
        ),
    )
    connection = duckdb.connect(str(database_path), read_only=True)

    market_summary = connection.execute(
        """
        SELECT count(*) AS rows, count(DISTINCT isin) AS isins,
               min(session_date) AS date_min, max(session_date) AS date_max
        FROM market_daily
        """
    ).fetchone()
    amf_summary = connection.execute(
        """
        SELECT count(*) AS rows, count(DISTINCT isin) AS isins,
               min(position_date) AS date_min, max(position_date) AS date_max
        FROM amf_short_positions
        """
    ).fetchone()
    series_summary = connection.execute(
        """
        SELECT count(*) AS rows, count(DISTINCT universe_id) AS universes,
               count(DISTINCT series_id) AS series,
               min(session_date) AS date_min, max(session_date) AS date_max
        FROM market_series
        """
    ).fetchone()
    series_universes = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT universe_id FROM market_series ORDER BY universe_id"
        ).fetchall()
    ]
    labels_by_code = {
        row[0]: {"name": row[1], "ticker": row[2]}
        for row in connection.execute(
            "SELECT provider_instrument_id, display_name, ticker FROM instrument_labels_by_code"
        ).fetchall()
    }
    series_options = {universe_id: {} for universe_id in series_universes}
    for universe_id, series_id, provider_id, label_name, ticker in connection.execute(
        """
        SELECT DISTINCT universe_id, series_id, provider_instrument_id,
                        display_name, ticker
        FROM market_series_with_labels
        ORDER BY universe_id, display_name, provider_instrument_id
        """
    ).fetchall():
        label = label_name or provider_id
        if ticker:
            label = f"{label} · {ticker}"
        option = f"{label} [{provider_id}]"
        series_options[universe_id][option] = series_id
    market_isins = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT isin FROM market_daily_history WHERE isin IS NOT NULL ORDER BY isin"
        ).fetchall()
    ]
    amf_isins = [
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT isin FROM amf_short_positions WHERE isin IS NOT NULL ORDER BY isin"
        ).fetchall()
    ]
    all_isins = sorted(set(market_isins) | set(amf_isins))
    isin_options = {"Tous les ISIN": "Tous les ISIN"}
    for isin_value in all_isins:
        label = labels_by_code.get(isin_value, {}).get("name") or isin_value
        ticker = labels_by_code.get(isin_value, {}).get("ticker")
        if ticker:
            label = f"{label} · {ticker}"
        isin_options[f"{label} [{isin_value}]"] = isin_value
    latest_available_dates = [
        row[0]
        for row in connection.execute(
            """
            SELECT max(CAST(available_at AS DATE)) FROM market_daily_history
            UNION ALL
            SELECT max(CAST(available_at AS DATE)) FROM amf_short_positions
            """
        ).fetchall()
        if row[0] is not None
    ]
    max_date = max(latest_available_dates) if latest_available_dates else date.today()
    default_as_of = max_date
    return (
        all_isins,
        amf_isins,
        amf_summary,
        connection,
        default_as_of,
        datetime,
        market_isins,
        market_summary,
        max_date,
        mo,
        px,
        isin_options,
        series_options,
        series_summary,
        series_universes,
        time,
        ZoneInfo,
    )


@app.cell
def _(amf_summary, market_summary, mo, series_summary):
    mo.md(
        f"""
        # Explorateur Quant Lab

        Lecture seule de `data/research.duckdb`. Les données restent locales.

        | Dataset | Observations | ISIN |
        |:--|--:|--:|
        | Prix OHLCV | {market_summary[0]:,} | {market_summary[1]:,} |
        | Positions courtes AMF | {amf_summary[0]:,} | {amf_summary[1]:,} |
        | Autres univers ABC Bourse | {series_summary[0]:,} | {series_summary[2]:,} séries |

        Couverture prix : {market_summary[2]} → {market_summary[3]} ·
        couverture AMF : {amf_summary[2]} → {amf_summary[3]} ·
        autres univers : {series_summary[3]} → {series_summary[4]}.

        La coupure `as_of` inclut les informations disponibles jusqu'à la fin du jour choisi.
        Les lignes sont filtrées par `available_at`. Les positions AMF
        restent datées par `position_date`, mais cette date ne détermine jamais leur
        disponibilité.
        """
    )
    return


@app.cell
def _(mo, px):
    import json as _json
    import os as _os
    from pathlib import Path as _Path

    import duckdb as _duckdb
    import pandas as pd

    signal_db_path = _Path(
        _os.environ.get(
            "HOCUS_QUANT_SIGNALS_DB",
            _Path(__file__).resolve().parents[1]
            / "data"
            / "analysis"
            / "spec006-weekly-demo"
            / "signals.duckdb",
        )
    )
    signal_manifest_path = signal_db_path.parent / "manifest.json"
    mo.stop(
        not signal_db_path.is_file(),
        mo.callout(
            mo.md(
                f"Les résultats SPEC-006 ne sont pas encore matérialisés. "
                f"Base attendue : `{signal_db_path}`."
            ),
            kind="neutral",
        ),
    )
    signal_connection = _duckdb.connect(str(signal_db_path), read_only=True)
    signal_meta = signal_connection.execute(
        "SELECT count(*), count(DISTINCT feature_id), count(DISTINCT target_id), "
        "count(DISTINCT as_of_date), min(as_of_date), max(as_of_date) "
        "FROM signal_ic_history WHERE scope='global'"
    ).fetchone()
    signal_relation_count = signal_connection.execute(
        "SELECT count(*) FROM signal_summary WHERE scope='global'"
    ).fetchone()[0]
    signal_fdr_025_count = signal_connection.execute(
        "SELECT count(*) FROM signal_summary WHERE scope='global' AND fdr_q_value<=0.25"
    ).fetchone()[0]
    signal_run = (
        _json.loads(signal_manifest_path.read_text(encoding="utf-8"))
        if signal_manifest_path.is_file()
        else {}
    )
    signal_filters = signal_connection.execute(
        "SELECT DISTINCT target_family FROM signal_summary ORDER BY target_family"
    ).fetchall()
    signal_families = [row[0] for row in signal_filters]
    median_entities = (
        signal_run.get("data_quality", {})
        .get("feature_cube", {})
        .get("entity_count_median", "n.c.")
    )
    signal_home = mo.md(
        f"""
        <style>
        :root {{ --ql-ink:#e6e5d9; --ql-muted:#9da49b; --ql-line:#323b36; --ql-accent:#d8a45c; }}
        .ql-shell {{ border:1px solid #323b36; border-radius:18px; padding:24px;
                    background:radial-gradient(ellipse at 85% 0%, #27332f 0, #171d1b 55%); }}
        .ql-eyebrow {{ color:#d8a45c; letter-spacing:.18em; text-transform:uppercase;
                      font-size:11px; }}
        .ql-shell h2 {{ color:#f0efe5; font-size:30px; margin:8px 0; }}
        .ql-sub {{ color:#9da49b; max-width:760px; }}
        .ql-nav {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:18px; }}
        .ql-nav a {{ color:#d8a45c; text-decoration:none; font-size:13px; }}
        .ql-statrow {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
          gap:10px; margin-top:22px; }}
        .ql-stat {{ border:1px solid #323b36; border-radius:12px; padding:12px; }}
        .ql-stat b {{ display:block; color:#f0efe5; font-size:21px; }}
        .ql-stat span {{ color:#9da49b; font-size:11px; text-transform:uppercase; }}
        </style>
        <section class="ql-shell" id="quant-home">
          <div class="ql-eyebrow">Hocus · Market observatory</div>
          <h2>Signal Atlas</h2>
          <div class="ql-sub">Associations historiques entre mesures connues à T et outcomes futurs.
          Lecture exploratoire, PIT reconstruit, aucune stratégie ni recommandation.</div>
          <div class="ql-statrow">
            <div class="ql-stat"><b>{median_entities}</b>
              <span>entities / cutoff · median</span></div>
            <div class="ql-stat"><b>{signal_meta[1]:,}</b><span>features</span></div>
            <div class="ql-stat"><b>{signal_meta[2]:,}</b><span>targets</span></div>
            <div class="ql-stat"><b>{signal_meta[3]:,}</b><span>cutoffs</span></div>
            <div class="ql-stat"><b>{signal_relation_count:,}</b><span>relations</span></div>
            <div class="ql-stat"><b>{signal_meta[4]} → {signal_meta[5]}</b>
              <span>période · PIT reconstructed</span></div>
          </div>
          <nav class="ql-nav">
            <a href="#signal-atlas">Signal Atlas</a><a href="#signal-heatmap">Horizon map</a>
            <a href="#signal-detail">Signal detail</a><a href="#market-data">Market data</a>
            <a href="#stability-atlas">Stability Atlas</a>
            <a href="#signal-method">Methodology</a>
          </nav>
        </section>
        """
    )
    signal_home  # noqa: B018 -- render the landing card with live analysis counts.
    return (
        pd,
        signal_connection,
        signal_db_path,
        signal_families,
        signal_meta,
        signal_relation_count,
        signal_fdr_025_count,
        signal_run,
    )


@app.cell
def _(mo, signal_connection, signal_families):
    target_labels = {
        "return_abs": "Future absolute return",
        "return_rel": "Future relative return",
        "rank_pct": "Relative performance rank",
        "direction_abs": "Absolute direction",
        "direction_rel": "Relative direction",
        "volatility": "Future volatility",
        "max_drawdown": "Future maximum drawdown",
        "max_upside": "Future maximum upside",
        "max_downside": "Future maximum downside",
    }
    available_families = signal_families or ["return_rel"]
    family_filter = mo.ui.dropdown(
        options={target_labels.get(item, item): item for item in available_families},
        value=target_labels.get(
            "return_rel" if "return_rel" in available_families else available_families[0],
            available_families[0],
        ),
        label="Outcome",
    )
    horizons_available = [
        row[0]
        for row in signal_connection.execute(
            "SELECT DISTINCT horizon FROM signal_summary ORDER BY horizon"
        ).fetchall()
    ] or [20]
    horizon_filter = mo.ui.dropdown(
        options=horizons_available,
        value=20 if 20 in horizons_available else horizons_available[0],
        label="Horizon · séances",
    )
    scope_options = [
        "global",
        *[
            row[0]
            for row in signal_connection.execute(
                "SELECT DISTINCT scope FROM signal_summary WHERE scope<>'global' ORDER BY scope"
            ).fetchall()
        ],
    ]
    scope_filter = mo.ui.dropdown(options=scope_options, value="global", label="Univers")
    feature_families = [
        row[0]
        for row in signal_connection.execute(
            "SELECT DISTINCT feature_family FROM signal_summary "
            "WHERE feature_family IS NOT NULL ORDER BY feature_family"
        ).fetchall()
    ]
    feature_family_filter = mo.ui.dropdown(
        options=["Any", *feature_families], value="Any", label="Famille de feature"
    )
    direction_filter = mo.ui.dropdown(
        options=["Any", "Positive", "Negative"], value="Any", label="Signe de l’IC"
    )
    n_filter = mo.ui.slider(start=0, stop=500000, step=1000, value=1000, label="N minimal")
    fdr_filter = mo.ui.slider(start=0.01, stop=1.0, step=0.01, value=1.0, label="FDR q maximal")
    controls = mo.hstack(
        [
            family_filter,
            horizon_filter,
            scope_filter,
            feature_family_filter,
            direction_filter,
            n_filter,
            fdr_filter,
        ],
        justify="start",
        gap=1.5,
    )
    controls  # noqa: B018 -- marimo renders the controls from this cell.
    return (
        direction_filter,
        family_filter,
        fdr_filter,
        feature_family_filter,
        horizon_filter,
        n_filter,
        scope_filter,
        target_labels,
    )


@app.cell
def _(mo):
    heatmap_metric = mo.ui.dropdown(
        options=["Mean cross-sectional Spearman IC", "Decile spread D10 − D1"],
        value="Mean cross-sectional Spearman IC",
        label="Heatmap metric",
    )
    mo.hstack([heatmap_metric])
    return (heatmap_metric,)


@app.cell
def _(
    family_filter,
    fdr_filter,
    feature_family_filter,
    horizon_filter,
    mo,
    n_filter,
    pd,
    signal_fdr_025_count,
    target_labels,
    signal_connection,
    signal_meta,
    scope_filter,
    direction_filter,
):
    filtered = signal_connection.execute(
        "SELECT * FROM signal_summary WHERE target_family=? AND horizon=? AND scope=? "
        "AND n_total>=? AND fdr_q_value IS NOT NULL AND fdr_q_value<=? "
        "AND (?='Any' OR feature_family=?) "
        "AND (?='Any' OR (?='Positive' AND spearman_ic_mean>0) "
        "OR (?='Negative' AND spearman_ic_mean<0)) "
        "ORDER BY fdr_q_value, abs(spearman_ic_mean) DESC "
        "LIMIT 500",
        [
            family_filter.value,
            horizon_filter.value,
            scope_filter.value,
            n_filter.value,
            fdr_filter.value,
            feature_family_filter.value,
            feature_family_filter.value,
            direction_filter.value,
            direction_filter.value,
            direction_filter.value,
        ],
    ).fetchdf()
    if not filtered.empty:

        def human_feature_label(feature_id):
            parts = feature_id.split(".")
            metric = parts[-3].replace("_", " ").title() if len(parts) >= 4 else feature_id
            family = parts[0].upper() if parts[0] == "ohlc" else parts[0].title()
            window = next(
                (part[1:] for part in parts if part.startswith("w") and part[1:].isdigit()),
                None,
            )
            suffix = f" · {window} sessions" if window else ""
            return f"{family} {metric}{suffix}"

        filtered["feature_label"] = filtered["feature_id"].map(human_feature_label)
        filtered["target_label"] = filtered.apply(
            lambda row: (
                f"{target_labels.get(row.target_family, row.target_family)} · "
                f"H{row.horizon} · {row.target_id}"
            ),
            axis=1,
        )
        columns = [
            "feature_label",
            "target_label",
            "spearman_ic_mean",
            "ic_t_stat",
            "hit_rate",
            "top_bottom_spread",
            "monotonicity_spearman",
            "n_total",
            "cutoff_count",
            "fdr_q_value",
            "feature_id",
        ]
        visible = filtered[[column for column in columns if column in filtered.columns]]
        signal_options = {
            f"{human_feature_label(row.feature_id)} · {row.feature_id} · "
            f"q={row.fdr_q_value if pd.notna(row.fdr_q_value) else 'n.c.'}": (
                row.feature_id,
                row.target_id,
                row.scope,
            )
            for row in filtered.itertuples()
        }
        detail_choice = mo.ui.dropdown(
            options=signal_options,
            value=next(iter(signal_options), None),
            searchable=True,
            label="Explorer une relation",
        )
        signal_view = mo.vstack(
            [
                mo.md(
                    f"**{signal_meta[2]:,} targets** · {signal_meta[1]:,} features · "
                    f"{signal_meta[3]:,} cutoffs · {signal_meta[4]} → {signal_meta[5]} · "
                    "PIT reconstructed"
                ),
                mo.callout(
                    mo.md(
                        f"{signal_fdr_025_count:,} global relations pass descriptive FDR q≤0.25. "
                        "The default view keeps all available q-values visible for exploratory "
                        "inspection; no relationship is treated as statistically confirmed."
                    ),
                    kind="neutral",
                ),
                mo.md(
                    f"<div id='signal-atlas'></div>\n"
                    f"#### {len(visible):,} relations dans la sélection"
                ),
                mo.ui.table(visible, page_size=16),
                detail_choice,
            ]
        )
    else:
        detail_choice = mo.ui.dropdown(options={}, value=None, label="Explorer une relation")

        def human_feature_label(feature_id):
            return feature_id

        signal_view = mo.callout(
            mo.md("Aucune relation ne satisfait ces filtres. Réduisez N ou élargissez FDR."),
            kind="neutral",
        )
    signal_view  # noqa: B018 -- marimo renders the atlas table and selection.
    return detail_choice, human_feature_label


@app.cell
def _(detail_choice, human_feature_label, mo, px, signal_connection, signal_run):
    mo.stop(detail_choice.value is None, mo.md("Aucune relation à détailler."))
    selected_feature, selected_target, selected_scope = detail_choice.value
    signal_hero = signal_connection.execute(
        "SELECT target_family, horizon, spearman_ic_mean, pearson_pooled, spearman_pooled, "
        "ic_t_stat, n_total, cutoff_count, fdr_q_value, top_bottom_spread, "
        "target_formula, target_scale "
        "FROM signal_summary WHERE feature_id=? AND target_id=? AND scope=?",
        [selected_feature, selected_target, selected_scope],
    ).fetchone()
    deciles = signal_connection.execute(
        "SELECT * FROM signal_deciles WHERE feature_id=? AND target_id=? AND scope=? "
        "ORDER BY decile",
        [selected_feature, selected_target, selected_scope],
    ).fetchdf()
    history = signal_connection.execute(
        "SELECT * FROM signal_ic_history WHERE feature_id=? AND target_id=? AND scope=? "
        "ORDER BY as_of_date",
        [selected_feature, selected_target, selected_scope],
    ).fetchdf()
    family_stability = signal_connection.execute(
        "SELECT scope AS family, spearman_ic_mean, hit_rate, top_bottom_spread, "
        "n_total, cutoff_count, fdr_q_value FROM signal_by_family "
        "WHERE feature_id=? AND target_id=? ORDER BY scope",
        [selected_feature, selected_target],
    ).fetchdf()
    period_stability = signal_connection.execute(
        "SELECT year, date_min, date_max, cutoff_count, spearman_ic_mean, spearman_ic_median, "
        "positive_ratio, status FROM signal_period_stability "
        "WHERE feature_id=? AND target_id=? AND scope=? ORDER BY year",
        [selected_feature, selected_target, selected_scope],
    ).fetchdf()
    quality = signal_run.get("data_quality", {})
    cube_quality = quality.get("feature_cube", {})
    target_quality = quality.get("target_set", {})
    benchmark_coverages = target_quality.get("relative_benchmark_coverage_by_horizon", [])
    benchmark_coverage = next(
        (
            item.get("benchmark_mapped_population_rate")
            for item in benchmark_coverages
            if item.get("horizon") == 20
        ),
        None,
    )

    def _fmt(value, spec=".3f"):
        return format(value, spec) if value is not None else "—"

    feature_availability_display = (
        f"{_fmt(cube_quality['availability_rate'] * 100, '.1f')}%"
        if cube_quality.get("availability_rate") is not None
        else "n.c."
    )
    benchmark_coverage_display = (
        f"{_fmt(benchmark_coverage * 100, '.1f')}%" if benchmark_coverage is not None else "n.c."
    )
    ready_target_rows = target_quality.get("research_ready_target_rows", "n.c.")
    excluded_target_rows = target_quality.get("target_rows_excluded_from_research_ready", "n.c.")
    unresolved_extreme_events = target_quality.get("unresolved_event_count", "n.c.")

    decile_chart = None
    if not deciles.empty:
        decile_chart = px.line(
            deciles,
            x="decile",
            y="mean_target",
            markers=True,
            title="Outcome moyen par décile de feature",
            labels={"decile": "Décile · faible → élevé", "mean_target": "Outcome moyen"},
        )
        decile_chart.update_traces(line_color="#d8a45c")
    ic_chart = None
    if not history.empty:
        ic_chart = px.line(
            history,
            x="as_of_date",
            y=["spearman_ic", "rolling_spearman_ic_13"],
            title="IC cross-sectionnel dans le temps",
            labels={"as_of_date": "Cutoff", "value": "Spearman IC", "variable": "Mesure"},
        )
        ic_chart.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    detail_view = mo.vstack(
        [
            mo.md(
                f"<div id='signal-detail'></div>\n"
                f"### {human_feature_label(selected_feature)}\n"
                f"`{selected_feature}` → `{selected_target}` · scope `{selected_scope}`"
            ),
            mo.md(
                f"**{signal_hero[0]} · H{signal_hero[1]}**　·　"
                f"Spearman IC moyen **{_fmt(signal_hero[2])}**　·　"
                f"Pearson pooled {_fmt(signal_hero[3])}　·　"
                f"Spearman pooled {_fmt(signal_hero[4])}　·　"
                f"t-stat {_fmt(signal_hero[5], '.2f')}　·　"
                f"N {signal_hero[6]:,} / {signal_hero[7]} cutoffs　·　"
                f"FDR q {_fmt(signal_hero[8], '.3g')}　·　"
                f"spread D10–D1 {_fmt(signal_hero[9], '.4g')}"
                if signal_hero
                else "Métriques résumé indisponibles pour cette relation."
            ),
            mo.md(
                f"**Target definition.** `{signal_hero[10]}` · échelle : `{signal_hero[11]}`"
                if signal_hero
                else "Définition du target indisponible."
            ),
            mo.ui.plotly(decile_chart)
            if decile_chart is not None
            else mo.md("Déciles indisponibles."),
            mo.ui.plotly(ic_chart)
            if ic_chart is not None
            else mo.md("Historique IC indisponible."),
            mo.md("#### Répétition par famille d’actifs"),
            mo.ui.table(family_stability, page_size=10)
            if not family_stability.empty
            else mo.md("Pas de famille avec un effectif suffisant."),
            mo.md("#### Stabilité annuelle · périodes de 4 cutoffs minimum"),
            mo.ui.table(period_stability, page_size=8)
            if not period_stability.empty
            else mo.md("Pas de périodes annuelles disponibles."),
            mo.callout(
                mo.md(
                    "<div id='signal-method'></div>\n**Méthode.** Chaque cutoff calcule une "
                    "corrélation transversale "
                    "feature/target après jointure sur titre et date. Les déciles sont "
                    "recalculés séparément à chaque cutoff. Le t-stat et sa p-value "
                    "sont descriptifs ; les cutoffs hebdomadaires se chevauchent, "
                    "donc ils ne corrigent pas l’autocorrélation et ne démontrent pas "
                    "un pouvoir prédictif exploitable. PIT : reconstructed."
                ),
                kind="neutral",
            ),
            mo.md(
                "#### Data quality / provenance\n"
                f"Feature availability: {feature_availability_display} · "
                f"entities/cutoff: {cube_quality.get('entity_count_min', 'n.c.')}–"
                f"{cube_quality.get('entity_count_max', 'n.c.')} · "
                f"targets research-ready: "
                f"{ready_target_rows} · excluded: {excluded_target_rows} · "
                f"unresolved extreme events: {unresolved_extreme_events} · "
                f"H20 relative benchmark mapped: "
                f"{benchmark_coverage_display}\n\n"
                f"Cube contract: `{signal_run.get('feature_cube_contract_fingerprint', 'n.c.')}` · "
                f"Target contract: "
                f"`{signal_run.get('target_set_contract_fingerprint', 'n.c.')}`\n\n"
                f"Feature registry: `{signal_run.get('feature_registry_sha256', 'n.c.')}` · "
                f"Target registry: `{signal_run.get('target_registry_sha256', 'n.c.')}`"
            ),
        ]
    )
    detail_view  # noqa: B018 -- marimo renders the selected relation detail.
    return


@app.cell
def _(
    family_filter,
    heatmap_metric,
    human_feature_label,
    mo,
    px,
    scope_filter,
    signal_connection,
):
    metric_column = (
        "spearman_ic_mean"
        if heatmap_metric.value == "Mean cross-sectional Spearman IC"
        else "top_bottom_spread"
    )
    heatmap = signal_connection.execute(
        f"""WITH rows AS (
               SELECT feature_id, horizon, avg({metric_column}) AS metric_value
               FROM signal_summary
               WHERE target_family=? AND scope=?
               GROUP BY feature_id, horizon
             ), ranked AS (
               SELECT *, avg(abs(metric_value)) OVER (PARTITION BY feature_id) AS strength
               FROM rows
             ), selected AS (
               SELECT feature_id, horizon, metric_value FROM ranked
               QUALIFY dense_rank() OVER (ORDER BY strength DESC, feature_id) <= 40
             )
             SELECT * FROM selected ORDER BY feature_id, horizon""",
        [family_filter.value, scope_filter.value],
    ).fetchdf()
    heading = mo.md(f"<div id='signal-heatmap'></div>\n### Horizon map · {heatmap_metric.value}")
    if heatmap.empty:
        heatmap_content = mo.md("Aucune donnée disponible pour cette famille et ce scope.")
    else:
        heatmap["feature_label"] = heatmap["feature_id"].map(human_feature_label)
        matrix = heatmap.pivot_table(
            index="feature_label", columns="horizon", values="metric_value", aggfunc="mean"
        )
        heatmap_chart = px.imshow(
            matrix,
            aspect="auto",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            labels={"x": "Horizon · séances", "y": "Feature", "color": metric_column},
        )
        heatmap_chart.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        heatmap_content = mo.ui.plotly(heatmap_chart)
    mo.vstack([heading, heatmap_content])
    return


@app.cell
def _(default_as_of, isin_options, max_date, mo, series_universes):
    dataset = mo.ui.dropdown(
        options={
            "Prix OHLCV · SRD / XPAR": "market",
            "Positions courtes AMF": "amf",
            "Autres univers ABC Bourse": "series",
        },
        value="Prix OHLCV · SRD / XPAR",
        label="Jeu de données",
    )
    isin = mo.ui.dropdown(
        options=isin_options,
        value="Tous les ISIN",
        searchable=True,
        label="ISIN",
    )
    as_of = mo.ui.date(
        start="2012-10-17",
        stop=max_date,
        value=default_as_of,
        label="Connu à la fin du",
    )
    universe = mo.ui.dropdown(
        options=series_universes,
        value=series_universes[0] if series_universes else None,
        label="Univers",
    )
    mo.md("<div id='market-data'></div>\n### Data Explorer · séries de marché et snapshots as-of")
    mo.hstack([dataset, isin, universe, as_of], justify="start", gap=2)
    return as_of, dataset, isin, universe


@app.cell
def _(mo, series_options, universe):
    selected_series_options = series_options.get(universe.value, {})
    series = mo.ui.dropdown(
        options=selected_series_options,
        value=next(iter(selected_series_options), None),
        searchable=True,
        label="Série / identifiant fournisseur",
    )
    mo.hstack([universe, series], justify="start", gap=2)
    return (series,)


@app.cell
def _(as_of, connection, dataset, datetime, isin, mo, px, series, time, universe, ZoneInfo):
    cutoff_date = as_of.value
    cutoff = datetime.combine(cutoff_date, time.max, tzinfo=ZoneInfo("Europe/Paris"))
    selected_isin = isin.value

    if dataset.value == "market":
        market_rows = connection.execute(
            """
            SELECT market.session_date, market.isin, labels.display_name, labels.ticker,
                   market.open, market.high, market.low, market.close,
                   market.adjusted_close, market.volume, market.currency,
                   market.provider, market.available_at
            FROM market_daily_history AS market
            LEFT JOIN instrument_labels_by_code AS labels
              ON labels.provider_instrument_id = market.isin
            WHERE market.available_at <= ?
              AND market.session_date <= ?
              AND (? = 'Tous les ISIN' OR market.isin = ?)
            QUALIFY row_number() OVER (
                PARTITION BY market.provider, market.isin, market.session_date
                ORDER BY market.available_at DESC, market.retrieved_at DESC,
                         market.snapshot_id DESC
            ) = 1
            ORDER BY market.session_date, market.isin
            """,
            [cutoff, cutoff_date, selected_isin, selected_isin],
        ).fetchdf()
        if market_rows.empty:
            result = mo.md("Aucun prix connu à cette date pour la sélection.")
        else:
            if selected_isin == "Tous les ISIN":
                chart = mo.md("Choisissez un ISIN pour afficher son graphique de clôture.")
            else:
                selected_market_name = market_rows["display_name"].dropna()
                chart_title = (
                    selected_market_name.iloc[0]
                    if not selected_market_name.empty
                    else selected_isin
                )
                price_chart = px.line(
                    market_rows,
                    x="session_date",
                    y="close",
                    title=f"Cours de clôture · {chart_title}",
                    labels={"session_date": "Séance", "close": "Clôture"},
                )
                chart = mo.ui.plotly(price_chart)
            result = mo.vstack(
                [
                    mo.md(
                        f"**{len(market_rows):,} lignes** · "
                        f"{market_rows['session_date'].min()} → "
                        f"{market_rows['session_date'].max()}"
                    ),
                    chart,
                    mo.ui.table(market_rows, page_size=15),
                ]
            )
    elif dataset.value == "amf":
        amf_rows = connection.execute(
            """
            SELECT positions.position_date, positions.publication_date,
                   positions.published_at, positions.available_at,
                   positions.issuer, positions.isin, labels.display_name, labels.ticker,
                   positions.holder, positions.net_short_position_pct,
                   positions.source_url, positions.snapshot_checksum
            FROM amf_short_positions AS positions
            LEFT JOIN instrument_labels_by_code AS labels
              ON labels.provider_instrument_id = positions.isin
            WHERE positions.available_at <= ?
              AND positions.position_date <= ?
              AND (? = 'Tous les ISIN' OR positions.isin = ?)
            ORDER BY positions.position_date, positions.issuer, positions.holder
            """,
            [cutoff, cutoff_date, selected_isin, selected_isin],
        ).fetchdf()
        if amf_rows.empty:
            result = mo.md("Aucune position AMF connue à cette date pour la sélection.")
        else:
            if selected_isin == "Tous les ISIN":
                chart = mo.md("Choisissez un ISIN pour afficher les déclarants et positions.")
            else:
                short_chart = px.line(
                    amf_rows,
                    x="position_date",
                    y="net_short_position_pct",
                    color="holder",
                    title=f"Positions courtes disponibles · {selected_isin}",
                    labels={
                        "position_date": "Date de position",
                        "net_short_position_pct": "Position courte nette (%)",
                        "holder": "Déclarant",
                    },
                )
                chart = mo.ui.plotly(short_chart)
            result = mo.vstack(
                [
                    mo.md(
                        f"**{len(amf_rows):,} lignes** · "
                        f"{amf_rows['position_date'].min()} → "
                        f"{amf_rows['position_date'].max()}"
                    ),
                    chart,
                    mo.ui.table(amf_rows, page_size=15),
                ]
            )
    else:
        if not universe.value or not series.value:
            result = mo.md("Aucune série disponible dans cet univers.")
        else:
            series_rows = connection.execute(
                """
                SELECT session_date, universe_id, series_id, provider_instrument_id,
                       display_name, ticker, label_variant_count, isin, open, high,
                       low, close, volume, currency, mic, provider, available_at,
                       retrieved_at
                FROM market_series_with_labels
                WHERE universe_id = ? AND series_id = ?
                  AND available_at <= ? AND session_date <= ?
                ORDER BY session_date
                """,
                [universe.value, series.value, cutoff, cutoff_date],
            ).fetchdf()
            if series_rows.empty:
                result = mo.md("Aucune observation disponible pour cette série à cette date.")
            else:
                selected_series_name = series_rows["display_name"].dropna()
                chart_title = (
                    selected_series_name.iloc[0] if not selected_series_name.empty else series.value
                )
                price_chart = px.line(
                    series_rows,
                    x="session_date",
                    y="close",
                    title=f"Cours de clôture · {chart_title}",
                    labels={"session_date": "Séance", "close": "Clôture"},
                )
                result = mo.vstack(
                    [
                        mo.md(
                            f"**{len(series_rows):,} lignes** · "
                            f"{series_rows['session_date'].min()} → "
                            f"{series_rows['session_date'].max()} · "
                            f"ISIN : {series_rows['isin'].notna().sum():,}/{len(series_rows):,}"
                        ),
                        mo.ui.plotly(price_chart),
                        mo.ui.table(series_rows, page_size=15),
                    ]
                )
    result  # noqa: B018 -- marimo renders the final cell expression.
    return


@app.cell
def _(mo):
    import json as stability_json
    import os as stability_os
    from pathlib import Path as StabilityPath

    import pandas as stability_load_pd

    stability_data_dir = StabilityPath(
        stability_os.environ.get(
            "HOCUS_QUANT_STABILITY_DIR",
            StabilityPath(__file__).resolve().parents[1]
            / "data"
            / "analysis"
            / "spec006r-stability-atlas",
        )
    )
    stability_required_files = [
        "signal_stability_summary.parquet",
        "signal_stability_by_family.parquet",
        "signal_period_metrics.parquet",
        "signal_period_ic_history.parquet",
        "signal_period_deciles.parquet",
        "stability_audit.json",
    ]
    mo.stop(
        not all((stability_data_dir / file).is_file() for file in stability_required_files),
        mo.md(
            "## Stability Atlas\n\n"
            "Le snapshot de stabilité est absent ou incomplet. Construisez-le avec "
            "`build-stability-atlas` avant d’ouvrir cette vue."
        ),
    )
    stability_summary = stability_load_pd.read_parquet(
        stability_data_dir / "signal_stability_summary.parquet"
    )
    stability_families = stability_load_pd.read_parquet(
        stability_data_dir / "signal_stability_by_family.parquet"
    )
    stability_periods = stability_load_pd.read_parquet(
        stability_data_dir / "signal_period_metrics.parquet"
    )
    stability_history = stability_load_pd.read_parquet(
        stability_data_dir / "signal_period_ic_history.parquet"
    )
    stability_deciles = stability_load_pd.read_parquet(
        stability_data_dir / "signal_period_deciles.parquet"
    )
    stability_audit = stability_json.loads(
        (stability_data_dir / "stability_audit.json").read_text(encoding="utf-8")
    )
    return (
        stability_audit,
        stability_deciles,
        stability_families,
        stability_history,
        stability_periods,
        stability_summary,
    )


@app.cell
def _(mo, stability_audit, stability_periods, stability_summary):
    stability_scopes = sorted(stability_summary["scope"].dropna().unique().tolist())
    stability_scope_filter = mo.ui.dropdown(
        options=stability_scopes,
        value="equity" if "equity" in stability_scopes else stability_scopes[0],
        label="Scope de discovery",
    )
    stability_bucket_filter = mo.ui.dropdown(
        options=["General · risque", "Rendement / direction"],
        value="General · risque",
        label="Cohorte figée en discovery",
    )
    stability_families_options = sorted(stability_summary["target_family"].dropna().unique())
    stability_family_filter = mo.ui.dropdown(
        options={"Toutes": "Toutes", **{value: value for value in stability_families_options}},
        value="Toutes",
        label="Target family",
    )
    stability_horizons = sorted(
        int(value) for value in stability_summary["horizon"].dropna().unique()
    )
    stability_horizon_filter = mo.ui.dropdown(
        options=["Tous", *[f"H{value}" for value in stability_horizons]],
        value="Tous",
        label="Horizon · séances",
    )
    stability_validation_ids = [
        period["period_id"]
        for period in stability_audit["periods"]
        if period["role"] == "validation"
    ]
    stability_latest_period = stability_validation_ids[-1] if stability_validation_ids else None
    stability_latest = stability_summary.loc[
        stability_summary["period_id"] == stability_latest_period
    ]
    stability_classes = sorted(stability_latest["stability_class"].dropna().unique().tolist())
    stability_class_filter = mo.ui.dropdown(
        options={"Toutes": "Toutes", **{value: value for value in stability_classes}},
        value="Toutes",
        label="Classe descriptive · dernière validation",
    )
    stability_maturity_filter = mo.ui.slider(
        start=0,
        stop=100,
        step=10,
        value=0,
        label="Maturité cible minimale · dernière validation (%)",
    )
    stability_sign_filter = mo.ui.dropdown(
        options=["Tous les signes", "Discovery positif", "Discovery négatif"],
        value="Tous les signes",
        label="Signe IC discovery",
    )
    stability_controls = mo.hstack(
        [
            stability_scope_filter,
            stability_bucket_filter,
            stability_family_filter,
            stability_horizon_filter,
            stability_class_filter,
            stability_maturity_filter,
            stability_sign_filter,
        ],
        justify="start",
        gap=1,
    )
    stability_controls  # noqa: B018 -- render interactive atlas filters.
    return (
        stability_bucket_filter,
        stability_class_filter,
        stability_family_filter,
        stability_horizon_filter,
        stability_latest_period,
        stability_maturity_filter,
        stability_scope_filter,
        stability_sign_filter,
        stability_validation_ids,
    )


@app.cell
def _(
    mo,
    stability_audit,
    stability_bucket_filter,
    stability_class_filter,
    stability_family_filter,
    stability_horizon_filter,
    stability_latest_period,
    stability_maturity_filter,
    stability_periods,
    stability_scope_filter,
    stability_sign_filter,
    stability_validation_ids,
):
    import numpy as stability_np
    import pandas as stability_pd
    import plotly.express as stability_px

    stability_scope = stability_scope_filter.value
    stability_primary = stability_periods.loc[
        (stability_periods["scope"] == stability_scope)
        & (stability_periods["evaluation_scope"] == stability_scope)
    ].copy()
    stability_latest_rows = stability_primary.loc[
        stability_primary["period_id"] == stability_latest_period
    ]
    stability_latest_rows = stability_latest_rows.loc[
        stability_latest_rows["selection_bucket"]
        == {
            "General · risque": "general",
            "Rendement / direction": "return_direction",
        }[stability_bucket_filter.value]
    ]
    if stability_family_filter.value != "Toutes":
        stability_latest_rows = stability_latest_rows.loc[
            stability_latest_rows["target_family"] == stability_family_filter.value
        ]
    if stability_horizon_filter.value != "Tous":
        stability_latest_rows = stability_latest_rows.loc[
            stability_latest_rows["horizon"]
            == int(stability_horizon_filter.value.removeprefix("H"))
        ]
    if stability_class_filter.value != "Toutes":
        stability_latest_rows = stability_latest_rows.loc[
            stability_latest_rows["stability_class"] == stability_class_filter.value
        ]
    stability_latest_rows = stability_latest_rows.loc[
        stability_latest_rows["maturity_ratio"].fillna(0) >= stability_maturity_filter.value / 100
    ]
    if stability_sign_filter.value == "Discovery positif":
        stability_latest_rows = stability_latest_rows.loc[
            stability_latest_rows["discovery_ic_mean"] > 0
        ]
    elif stability_sign_filter.value == "Discovery négatif":
        stability_latest_rows = stability_latest_rows.loc[
            stability_latest_rows["discovery_ic_mean"] < 0
        ]
    stability_ids = stability_latest_rows["signal_id"].unique().tolist()
    stability_visible = stability_primary.loc[stability_primary["signal_id"].isin(stability_ids)]
    stability_period_ids = [period["period_id"] for period in stability_audit["periods"]]
    stability_table_rows = []
    for stability_id, stability_group in stability_visible.groupby("signal_id", sort=False):
        stability_discovery = stability_group.loc[stability_group["is_discovery_period"]].head(1)
        if stability_discovery.empty:
            continue
        stability_discovery_row = stability_discovery.iloc[0]
        stability_row = {
            "Feature": stability_discovery_row["feature_id"],
            "Target": stability_discovery_row["target_id"],
            "Horizon": f"H{int(stability_discovery_row['horizon'])}",
            "Discovery rank": int(stability_discovery_row["discovery_rank"]),
            f"IC · {stability_discovery_row['period_id']}": stability_discovery_row["ic_mean"],
            "signal_id": stability_id,
        }
        for stability_period_id in stability_period_ids:
            stability_period_row = stability_group.loc[
                stability_group["period_id"] == stability_period_id
            ].head(1)
            if stability_period_row.empty:
                continue
            stability_period_value = stability_period_row.iloc[0]
            if stability_period_id != stability_discovery_row["period_id"]:
                stability_row[f"IC · {stability_period_id}"] = stability_period_value["ic_mean"]
                stability_row[f"Signe · {stability_period_id}"] = stability_period_value[
                    "sign_retained"
                ]
                stability_row[f"Rétention · {stability_period_id}"] = stability_period_value[
                    "impact_retention"
                ]
                stability_row[f"Maturité · {stability_period_id}"] = (
                    f"{int(stability_period_value['target_mature_cutoffs'])}/"
                    f"{int(stability_period_value['theoretical_cutoffs'])}"
                )
                stability_row["Classe"] = stability_period_value["stability_class"]
                stability_row["Preuve"] = stability_period_value["evidence_level"]
        stability_table_rows.append(stability_row)
    stability_table = stability_pd.DataFrame(stability_table_rows)
    if not stability_table.empty:
        stability_table = stability_table.sort_values("Discovery rank")
    stability_detail_options = {
        f"{row['Feature']} → {row['Target']} · {row['Horizon']} · {row['signal_id']}": row[
            "signal_id"
        ]
        for row in stability_table.to_dict(orient="records")
    }
    stability_detail_choice = mo.ui.dropdown(
        options=list(stability_detail_options),
        value=next(iter(stability_detail_options), None),
        searchable=True,
        label="Détail cross-period",
    )
    stability_heading = mo.md(
        "<div id='stability-atlas'></div>\n"
        "## Stability Atlas\n\n"
        "Discovery reste figée ; les colonnes de validation mesurent les mêmes relations "
        "sur les fenêtres suivantes. Les classes et la maturité décrivent les données observées."
    )
    if stability_table.empty:
        stability_main_view = mo.callout(
            mo.md(
                "Aucun signal ne passe ces filtres. Réduisez la maturité minimale "
                "ou élargissez le scope."
            ),
            kind="neutral",
        )
        stability_risk_return = mo.md("Aucun agrégat disponible pour cette sélection.")
        stability_heatmap_view = mo.md("Aucune relation à représenter.")
    else:
        stability_main_view = mo.vstack(
            [
                mo.md(f"**{len(stability_table):,} relations** · sélection initiale inchangée"),
                mo.ui.table(stability_table, page_size=18),
                stability_detail_choice,
            ]
        )
        stability_aggregate_rows = []
        for (stability_bucket, stability_period_id), stability_group in stability_visible.loc[
            stability_visible["period_id"].isin(stability_validation_ids)
        ].groupby(["selection_bucket", "period_id"]):
            stability_observed = stability_group.loc[stability_group["ic_mean"].notna()]
            stability_aggregate_rows.append(
                {
                    "Cohorte": stability_bucket,
                    "Période": stability_period_id,
                    "Signes conservés (%)": (
                        float(stability_observed["sign_retained"].fillna(False).mean() * 100)
                        if not stability_observed.empty
                        else None
                    ),
                    "Rétention médiane |IC|": stability_observed["impact_retention"].median(),
                    "Médiane |IC|": stability_observed["ic_mean"].abs().median(),
                    "Signaux observés": int(stability_observed["signal_id"].nunique()),
                    "Maturité médiane (%)": float(
                        stability_observed["maturity_ratio"].median() * 100
                    )
                    if not stability_observed.empty
                    else None,
                }
            )
        stability_risk_return = mo.vstack(
            [
                mo.md("### Comparaison risque vs rendement / direction"),
                mo.ui.table(stability_pd.DataFrame(stability_aggregate_rows), page_size=8),
            ]
        )
        stability_heatmap_rows = (
            stability_visible.loc[stability_visible["is_discovery_period"]]
            .sort_values("discovery_rank")
            .head(40)["signal_id"]
            .tolist()
        )
        stability_heatmap_data = stability_visible.loc[
            stability_visible["signal_id"].isin(stability_heatmap_rows)
        ]
        stability_heatmap_matrix = stability_heatmap_data.pivot_table(
            index="signal_id", columns="period_id", values="ic_mean", aggfunc="first"
        ).reindex(columns=stability_period_ids)
        stability_labels = stability_visible.drop_duplicates("signal_id").set_index("signal_id")
        stability_heatmap_matrix.index = [
            f"{stability_labels.loc[signal_id, 'feature_id']} → "
            f"{stability_labels.loc[signal_id, 'target_id']}"
            for signal_id in stability_heatmap_matrix.index
        ]
        stability_color_max = float(
            stability_np.nanmax(stability_np.abs(stability_heatmap_matrix.to_numpy()))
        )
        if not stability_color_max:
            stability_color_max = 1.0
        stability_figure = stability_px.imshow(
            stability_heatmap_matrix,
            aspect="auto",
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            zmin=-stability_color_max,
            zmax=stability_color_max,
            labels={"x": "Period", "y": "Frozen signal", "color": "Mean Spearman IC"},
            title="Discovery / validation · IC signé",
        )
        stability_figure.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        stability_heatmap_view = mo.vstack(
            [
                mo.md(
                    "### Heatmap période × signal · rouge négatif / bleu positif · "
                    "échelle centrée sur zéro"
                ),
                mo.ui.plotly(stability_figure),
            ]
        )
    stability_atlas_view = mo.vstack(
        [
            stability_heading,
            stability_main_view,
            stability_risk_return,
            stability_heatmap_view,
        ]
    )
    stability_atlas_view  # noqa: B018 -- render filtered atlas, comparison, and heatmap.
    return stability_detail_choice, stability_detail_options, stability_visible


@app.cell
def _(
    mo,
    stability_deciles,
    stability_detail_choice,
    stability_detail_options,
    stability_families,
    stability_history,
    stability_periods,
):
    import plotly.express as stability_detail_px

    mo.stop(
        stability_detail_choice.value is None,
        mo.md("Aucun signal disponible dans cette sélection."),
    )
    stability_selected_id = stability_detail_options[stability_detail_choice.value]
    stability_selected_metrics = stability_periods.loc[
        (stability_periods["signal_id"] == stability_selected_id)
        & (
            stability_periods["evaluation_scope"]
            == stability_periods.loc[
                stability_periods["signal_id"] == stability_selected_id, "scope"
            ].iloc[0]
        )
    ].copy()
    stability_selected_history = stability_history.loc[
        (stability_history["signal_id"] == stability_selected_id)
        & (stability_history["evaluation_scope"] == stability_selected_metrics["scope"].iloc[0])
    ].copy()
    stability_selected_deciles = stability_deciles.loc[
        (stability_deciles["signal_id"] == stability_selected_id)
        & (stability_deciles["evaluation_scope"] == stability_selected_metrics["scope"].iloc[0])
    ].copy()
    stability_selected_families = stability_families.loc[
        (stability_families["signal_id"] == stability_selected_id)
        & (~stability_families["is_discovery_period"])
    ].copy()
    stability_selected_name = stability_selected_metrics.iloc[0]
    if stability_selected_history.empty:
        stability_ic_chart = None
    else:
        stability_ic_chart = stability_detail_px.line(
            stability_selected_history,
            x="as_of_date",
            y="spearman_ic",
            color="period_id",
            markers=True,
            title="IC cross-sectionnel par cutoff · mêmes feature/target",
            labels={"as_of_date": "Cutoff", "spearman_ic": "Spearman IC", "period_id": "Période"},
        )
        stability_ic_chart.add_hline(y=0, line_dash="dot", line_color="#9da49b")
        stability_ic_chart.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    if stability_selected_deciles.empty:
        stability_decile_chart = None
    else:
        stability_decile_profile = stability_selected_deciles.groupby(
            ["period_id", "decile"], as_index=False
        )["mean_target"].mean()
        stability_decile_chart = stability_detail_px.line(
            stability_decile_profile,
            x="decile",
            y="mean_target",
            color="period_id",
            markers=True,
            title="Outcome moyen par décile de feature · agrégé par période",
            labels={"decile": "Décile feature · bas → haut", "mean_target": "Outcome moyen"},
        )
        stability_decile_chart.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    if stability_selected_metrics["stability_class"].eq("insufficient_validation").any():
        stability_auto_note = (
            "Certaines validations n’ont pas quatre cutoffs avec targets mûrs ; "
            "leur classe reste insufficient_validation, même si un signe observé diffère."
        )
    elif stability_selected_metrics["sign_retained"].eq(False).any():
        stability_auto_note = (
            "Au moins une période affiche un IC moyen de signe opposé à la discovery."
        )
    elif stability_selected_metrics["stability_class"].eq("unstable").any():
        stability_auto_note = (
            "Les signes d’IC varient entre cutoffs malgré un signe moyen conservé."
        )
    elif stability_selected_metrics["stability_class"].eq("weakened").any():
        stability_auto_note = (
            "Le signe observé est conservé, avec un impact ou une maturité sous le seuil stable."
        )
    else:
        stability_auto_note = (
            "Les observations disponibles gardent le signe et dépassent "
            "les seuils descriptifs stable."
        )
    stability_cross_period = stability_selected_metrics[
        [
            "period_id",
            "ic_mean",
            "ic_median",
            "t_stat",
            "hit_rate",
            "top_bottom_decile_spread",
            "monotonicity",
            "fdr_q_descriptive",
            "evaluated_cutoffs",
            "target_mature_cutoffs",
            "theoretical_cutoffs",
            "maturity_ratio",
            "signed_retention",
            "impact_retention",
            "rank_retention",
            "periods_sign_retained",
            "periods_evaluated",
            "evidence_level",
            "stability_class",
        ]
    ]
    stability_detail_view = mo.vstack(
        [
            mo.md(
                f"<div id='stability-signal-detail'></div>\n### Détail cross-period\n"
                f"`{stability_selected_name['feature_id']}` → "
                f"`{stability_selected_name['target_id']}` · "
                f"{stability_selected_name['selection_bucket']} · "
                f"{stability_selected_name['scope']}"
            ),
            mo.callout(mo.md(stability_auto_note), kind="neutral"),
            mo.md("#### Discovery, validation et maturité"),
            mo.ui.table(stability_cross_period, page_size=8),
            mo.ui.plotly(stability_ic_chart)
            if stability_ic_chart is not None
            else mo.md("IC timeline indisponible."),
            mo.ui.plotly(stability_decile_chart)
            if stability_decile_chart is not None
            else mo.md("Déciles indisponibles."),
            mo.md("#### Stabilité par scope/famille d’entités"),
            mo.ui.table(
                stability_selected_families[
                    [
                        "period_id",
                        "evaluation_scope",
                        "ic_mean",
                        "sign_retained",
                        "impact_retention",
                        "target_mature_cutoffs",
                        "theoretical_cutoffs",
                        "maturity_ratio",
                        "evidence_level",
                        "stability_class",
                    ]
                ],
                page_size=12,
            ),
            mo.md(
                "**Méthode descriptive.** Le signal est gelé sur discovery ; les mêmes clés "
                "feature/target/scope sont évaluées ensuite. Les IC cross-sectionnels et leurs "
                "périodes chevauchantes ne démontrent pas un alpha. Maturité = cutoffs avec au "
                "moins 30 targets research-ready ; `thin`, `partial`, `adequate` indiquent la "
                "quantité observée, pas une probabilité de confiance. PIT : reconstructed."
            ),
        ]
    )
    stability_detail_view  # noqa: B018 -- render the selected signal's detail.
    return


if __name__ == "__main__":
    app.run()
