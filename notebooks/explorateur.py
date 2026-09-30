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
def _(default_as_of, isin_options, max_date, mo, series_options, series_universes):
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
    selected_series_options = series_options.get(universe.value, {})
    series = mo.ui.dropdown(
        options=selected_series_options,
        value=next(iter(selected_series_options.values()), None),
        searchable=True,
        label="Série / identifiant fournisseur",
    )
    mo.hstack([dataset, isin, universe, series, as_of], justify="start", gap=2)
    return as_of, dataset, isin, series, universe


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


if __name__ == "__main__":
    app.run()
