import marimo

__generated_with = "0.25.0"
app = marimo.App(width="wide")


@app.cell
def _():
    import json
    import os
    import re
    from datetime import date
    from pathlib import Path

    import duckdb
    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.express as px
    import polars as pl
    from scipy.stats import spearmanr

    return Path, date, duckdb, json, mo, np, os, pd, pl, px, re, spearmanr


@app.cell
def _(Path, duckdb, json, mo, os):
    project_root = Path(__file__).resolve().parents[1]
    database_path = Path(
        os.environ.get("HOCUS_QUANT_DB", project_root / "data" / "research.duckdb")
    )
    atlas_paths = {
        "H5 uniquement · top 500": (
            project_root / "data" / "analysis" / "spec006r-stability-atlas-h5-top500"
        ),
        "Tous horizons · ancien top 500": (
            project_root / "data" / "analysis" / "spec006r-stability-atlas-top500"
        ),
    }
    root_cause_path = (
        project_root / "data" / "analysis" / "spec006r-root-cause-audit" / "root_cause_audit.json"
    )
    period_paths = {
        "2024 · discovery": {
            "features": project_root / "data" / "feature_cube" / "spec006-weekly-demo",
            "targets": project_root / "data" / "targets" / "spec006-weekly-demo",
            "start_date": "2024-04-05",
            "end_date": "2024-10-04",
        },
        "2025 · development": {
            "features": project_root / "data" / "feature_cube" / "spec006-2025-matched",
            "targets": project_root / "data" / "targets" / "spec006-2025-matched",
            "start_date": "2025-04-05",
            "end_date": "2025-10-04",
        },
        "2026 · development partiel": {
            "features": project_root / "data" / "feature_cube" / "spec006-2026-matched",
            "targets": project_root / "data" / "targets" / "spec006-2026-matched",
            "start_date": "2026-04-05",
            "end_date": "2026-10-04",
        },
    }
    mo.stop(
        not database_path.is_file(),
        mo.callout(
            mo.md(
                f"Base SRD absente : `{database_path}`. "
                "Importez la livraison ABC Bourse avant de lancer ce laboratoire."
            ),
            kind="danger",
        ),
    )
    connection = duckdb.connect(str(database_path), read_only=True)
    market_summary = connection.execute(
        """
        SELECT count(*) AS observations,
               count(DISTINCT instrument_id) AS instruments,
               count(DISTINCT isin) AS isins,
               min(session_date) AS date_min,
               max(session_date) AS date_max,
               min(retrieved_at) AS first_retrieval,
               max(retrieved_at) AS last_retrieval
        FROM market_daily
        """
    ).fetchone()
    table_names = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables UNION "
            "SELECT table_name FROM information_schema.views"
        ).fetchall()
    }
    if "instrument_labels_by_code" in table_names:
        label_rows = connection.execute(
            """
            SELECT provider_instrument_id, display_name, ticker
            FROM instrument_labels_by_code
            """
        ).fetchall()
        labels = {
            str(provider_id): {"name": name, "ticker": ticker}
            for provider_id, name, ticker in label_rows
        }
    else:
        labels = {}
    instrument_rows = connection.execute(
        """
        SELECT DISTINCT instrument_id, isin
        FROM market_daily
        WHERE isin IS NOT NULL
        ORDER BY isin
        """
    ).fetchall()
    instrument_options = {}
    for instrument_id, isin in instrument_rows:
        metadata = labels.get(str(instrument_id), labels.get(str(isin), {}))
        display_name = metadata.get("name") or str(instrument_id)
        ticker = metadata.get("ticker")
        label = f"{display_name} · {ticker} [{isin}]" if ticker else f"{display_name} [{isin}]"
        instrument_options[label] = str(isin)
    try:
        root_cause_audit = (
            json.loads(root_cause_path.read_text(encoding="utf-8"))
            if root_cause_path.is_file()
            else None
        )
    except PermissionError:
        root_cause_audit = None
    return (
        atlas_paths,
        connection,
        database_path,
        instrument_options,
        market_summary,
        period_paths,
        root_cause_audit,
    )


@app.cell
def _(database_path, market_summary, mo):
    mo.md(
        f"""
        # Laboratoire SRD · rendement et direction

        Environnement interactif en lecture seule pour reprendre l'expérience
        2024–2026 depuis les prix jusqu'aux IC. Le parcours principal expose le
        **candidate lock SPEC-006T**, dédupliqué, vers la direction absolue
        **H5 : cinq séances futures**. Les périodes 2025/2026 servent désormais
        au développement ; la confirmation attend de nouvelles données. La base utilisée est
        `{database_path}`.

        | Surface | Valeur |
        |:--|--:|
        | Observations SRD distinctes | {market_summary[0]:,} |
        | Instruments | {market_summary[1]:,} |
        | ISIN | {market_summary[2]:,} |
        | Couverture | {market_summary[3]} → {market_summary[4]} |
        | Récupération source | {market_summary[5]} |

        **Parcours conseillé :** lire Research Contract, explorer les candidats et
        comparer les deux politiques dans Signal Detail. Les étapes d'audit ci-dessous
        permettent ensuite d'inspecter les prix, ruptures, IC historiques, déciles et SQL.

        Les données ABC ont été récupérées en 2026. Leur grade PIT est
        `reconstructed`; elles ne constituent pas un univers SBF 120 historique.
        """
    )
    return


@app.cell
def _(Path, mo):
    from hocus_quant.analysis.research_ui import load_research_contract_artifacts

    contract_directory = Path(__file__).resolve().parents[1] / "data/analysis/spec006t-ex-ante"
    mo.stop(
        not (contract_directory / "audit.json").is_file(),
        mo.callout(
            mo.md("Research Contract SPEC-006T : artefacts locaux en attente."), kind="warn"
        ),
    )
    contract_artifacts = load_research_contract_artifacts(contract_directory)
    return (contract_artifacts,)


@app.cell
def _(contract_artifacts, mo, pl):
    contract_audit = contract_artifacts.audit
    contract_policy = mo.ui.radio(
        options={"Ex-ante cohort": "ex_ante", "Future-clean cohort": "clean_future"},
        value="Ex-ante cohort",
        inline=True,
        label="Politique de recherche H5",
    )
    candidate_tier_filter = mo.ui.dropdown(
        options={
            "Tous les groupes admissibles": "all",
            "Broad candidates": "broad_candidates",
            "Strong sign candidates": "strong_sign_candidates",
            "Strict candidates": "strict_candidates",
        },
        value="Strict candidates",
        label="Candidate Explorer · cohorte",
    )
    contract_candidate_options = {
        f"#{row['discovery_rank']} · {row['canonical_feature']} [{row['candidate_tier']}]": row[
            "canonical_feature"
        ]
        for row in contract_artifacts.candidates.to_dicts()
    }
    _strict_ids = set(
        contract_artifacts.candidates.filter(pl.col("strict_candidates"))["canonical_feature"]
    )
    _default_contract_feature = next(
        (label for label, feature in contract_candidate_options.items() if feature in _strict_ids),
        next(iter(contract_candidate_options), None),
    )
    contract_feature_choice = mo.ui.dropdown(
        options=contract_candidate_options,
        value=_default_contract_feature,
        searchable=True,
        label="Signal Detail · feature canonique",
    )
    mo.vstack(
        [
            mo.md(f"""
        ## Research Contract · SPEC-006T

        **Ex-ante eligibility :** décision figée à T, avec qualité passée approved
        et historique de features. Chaque feature doit ensuite être disponible à T.

        **Future quality :** review, quarantaine, corporate action suspectée et censure
        sont des annotations futures. Elles ne modifient pas la cohorte figée.
        Les erreurs source fortes restent ininterprétables pour l'IC numérique.

        **Candidate lock :** `{contract_audit["lock_sha256"][:16]}…` ·
        {contract_audit["candidate_counts_nested"]} · target `direction_abs H5` uniquement.
        H120 reste dans l'audit historique.

        **Development periods :** 2024 discovery, 2025 et 2026 partiel sont déjà consultés.
        **Confirmation period status :** nouvelles données non consultées en attente ;
        aucun résultat de confirmation, aucun retuning du lock.

        Target actuel : départ au close T. Une future stratégie devra définir
        une exécution après calcul, convention préparée : **next_open**.
        """),
            mo.ui.table(pl.DataFrame(contract_audit["cohort_by_period"]), selection=None),
            contract_policy,
            mo.md(
                "Les deux cohortes et leurs IC sont précalculés. Le toggle ne relance aucun scan."
            ),
            mo.md("## Candidate Explorer · H5 après déduplication"),
            mo.md(
                "Les tiers et le bootstrap sont figés selon la politique ex ante. "
                "La politique future-clean affiche seulement la sensibilité des IC ; "
                "elle ne retune pas le lock."
            ),
            mo.hstack([candidate_tier_filter, contract_feature_choice], justify="start", gap=2),
        ]
    )
    return candidate_tier_filter, contract_feature_choice, contract_policy


@app.cell
def _(Path, mo):
    from hocus_quant.analysis.confirmation import load_monitor

    confirmation_directory = (
        Path(__file__).resolve().parents[1] / "data/analysis/spec007-confirmation"
    )
    mo.stop(
        not (confirmation_directory / "confirmation_manifest.json").exists(),
        mo.md("Confirmation Monitor · SPEC-007 : protocole local en attente."),
    )
    confirmation_monitor = load_monitor(confirmation_directory)
    return (confirmation_monitor,)


@app.cell
def _(confirmation_monitor, contract_artifacts, mo, pl, px):
    confirmation_manifest = confirmation_monitor["manifest"]
    mo.stop(
        confirmation_manifest["candidate_lock_sha256"] != contract_artifacts.lock["lock_sha256"],
        mo.callout(
            mo.md("Confirmation et développement référencent des locks différents."), kind="danger"
        ),
    )
    _mature = confirmation_manifest["mature_cutoffs"]
    _strict_summary = (
        confirmation_monitor["cohorts"]
        .filter(
            (pl.col("tier") == "strict_candidates")
            & (pl.col("policy") == "ex_ante")
            & (pl.col("mature_cutoffs") == _mature)
        )
        .to_dicts()
        if _mature
        else []
    )
    _strict_row = _strict_summary[0] if _strict_summary else {}
    _conforming = _strict_row.get("positive_fraction")
    _mean = _strict_row.get("mean_oriented_ic")
    _median = _strict_row.get("median_oriented_ic")
    _conforming_text = f"{_conforming:.1%}" if _conforming is not None else "en attente"
    _mean_text = f"{_mean:+.5f}" if _mean is not None else "en attente"
    _median_text = f"{_median:+.5f}" if _median is not None else "en attente"
    _lock_text = (
        confirmation_manifest["candidate_lock_version"]
        + " · "
        + confirmation_manifest["candidate_lock_sha256"][:16]
        + "…"
    )
    _next_maturity = (
        confirmation_manifest["next_target_maturity"] or "inconnue : nouvelles séances nécessaires"
    )
    confirmation_header = mo.md(f"""
    ## Confirmation Monitor · SPEC-007

    **Development — 2024–2026 :** périodes déjà consultées et utilisées pour le lock.
    **Independent confirmation :** nouvelles observations uniquement, aucun mélange des moyennes.

    | Contrat / suivi | Valeur |
    |:--|:--|
    | État mécanique | `{confirmation_manifest["status"]}` |
    | Candidate lock | `{_lock_text}` |
    | Début de confirmation | {confirmation_manifest["confirmation_start_date"]} |
    | Cutoffs enregistrés / matures | {confirmation_manifest["registered_cutoffs"]} / {_mature} |
    | Broad / Strong / Strict | 504 / 138 / **85 (test principal)** |
    | Strict : signe conforme | {_conforming_text} |
    | Strict : IC orienté moyen / médian | {_mean_text} / {_median_text} |
    | Checkpoint | `{confirmation_manifest["checkpoint"]}` ; étapes 8 / 13 / 26 |
    | Verdict descriptif | `{_strict_row.get("verdict", "insufficient_data")}` |
    | Prochaine maturité | {_next_maturity} |
    | PIT | reconstructed ; jamais strict PIT |

    **oriented IC = IC × signe attendu figé.** Positif : conforme ; négatif : inversion.
    Supportive : >60 % conformes, moyenne et médiane positives. Unsupportive : <40 %,
    moyenne et médiane négatives. Aucune conclusion avant 8 cutoffs ni arrêt selon les résultats.
    Profondeur cible : 26. Les intervalles aux checkpoints restent individuels/descriptifs,
    sans contrôle d'erreur séquentielle ni indépendance présumée des candidats.
    """)
    if _mature:
        _curve = confirmation_monitor["cohorts"].filter(pl.col("policy") == "ex_ante")
        confirmation_plot = mo.ui.plotly(
            px.line(
                _curve.to_pandas(),
                x="mature_cutoffs",
                y="mean_oriented_ic",
                color="tier",
                markers=True,
                title="Independent confirmation · IC orienté cumulatif par cohorte",
            )
        )
    else:
        confirmation_plot = mo.callout(
            mo.md(
                "**SPEC-007 ready — awaiting independent data.** Aucun résultat scientifique "
                "de confirmation n'est calculé avec les années de développement."
            ),
            kind="info",
        )
    _monitor_outputs = [confirmation_header, confirmation_plot]
    if _mature:
        _monitor_outputs.extend(
            [
                mo.md("### Cohortes et groupes · dernier cutoff mature"),
                mo.ui.table(
                    confirmation_monitor["cohorts"].filter(pl.col("mature_cutoffs") == _mature),
                    selection=None,
                ),
                mo.ui.table(
                    confirmation_monitor["groups"].filter(pl.col("mature_cutoffs") == _mature),
                    selection=None,
                    page_size=10,
                ),
            ]
        )
    mo.vstack(_monitor_outputs)
    return


@app.cell
def _(confirmation_monitor, contract_artifacts, contract_feature_choice, mo, pl, px):
    from hocus_quant.features.registry import FEATURE_REGISTRY

    _feature_id = contract_feature_choice.value
    _locked = next(
        (r for r in contract_artifacts.lock["candidates"] if r["canonical_feature"] == _feature_id),
        None,
    )
    mo.stop(_locked is None, mo.md("Choisir un candidat du lock pour le détail de confirmation."))
    _metadata = next(r for r in FEATURE_REGISTRY if r.feature_id == _feature_id)
    _correlation_group = confirmation_monitor["protocol"]["known_groups"]["correlation_group"][
        _feature_id
    ]
    _dev = contract_artifacts.history.filter(
        (pl.col("feature_id") == _feature_id) & (pl.col("policy") == "ex_ante")
    ).sort("as_of_date")
    _dev_chart = px.line(
        _dev.to_pandas(),
        x="as_of_date",
        y="spearman_ic",
        title="Development seulement · historique 2024–2026",
    )
    _dev_chart.update_traces(line_color="#9ca3af")
    _detail_outputs = [
        mo.md(f"""
        ### Candidate detail · confirmation indépendante

        Feature : `{_feature_id}` · fenêtre {_locked["feature_window"]} ·
        **signe attendu : {_locked["locked_direction"]:+d}**, jamais réestimé sur confirmation.
        Famille : `{_metadata.family}` · série : `{_metadata.source_series}` ·
        métrique : `{_metadata.metric}` · formule : `{_metadata.formula_version}` ·
        historique minimum : {_metadata.minimum_observations} observations.
        Groupe de rang : `{_locked["rank_signature"][:16]}…` · aliases : {_locked["aliases"]}.
        Groupe de corrélation connu : `{_correlation_group}`.
        Le choix du candidat suit l'ordre de discovery figé ; aucun classement de confirmation.
        """),
        mo.ui.plotly(_dev_chart),
    ]
    if confirmation_monitor["manifest"]["mature_cutoffs"]:
        _confirmation_detail = (
            confirmation_monitor["history"]
            .filter((pl.col("feature_id") == _feature_id) & (pl.col("policy") == "ex_ante"))
            .sort("cutoff")
        )
        _progress_detail = (
            confirmation_monitor["candidates"]
            .filter((pl.col("feature_id") == _feature_id) & (pl.col("policy") == "ex_ante"))
            .sort("cutoff")
        )
        _detail_outputs.extend(
            [
                mo.ui.plotly(
                    px.line(
                        _confirmation_detail.to_pandas(),
                        x="cutoff",
                        y="oriented_ic",
                        markers=True,
                        title="Independent confirmation seulement",
                    )
                ),
                mo.ui.table(_progress_detail, selection=None),
            ]
        )
    else:
        _detail_outputs.append(
            mo.md(
                "**Independent confirmation : en attente.** Maturité, IC et moyenne cumulative "
                "seront ajoutés uniquement après enregistrement prospectif et maturation H5."
            )
        )
    mo.vstack(_detail_outputs)
    return


@app.cell
def _(candidate_tier_filter, contract_artifacts, contract_policy, mo, pl):
    contract_explorer = contract_artifacts.candidates
    if candidate_tier_filter.value != "all":
        contract_explorer = contract_explorer.filter(pl.col(candidate_tier_filter.value))
    for _year in [2024, 2025, 2026]:
        _policy_summary = contract_artifacts.summaries.filter(
            (pl.col("year") == _year) & (pl.col("policy") == contract_policy.value)
        ).select(
            pl.col("feature_id").alias("canonical_feature"),
            pl.col("ic_mean").alias(f"selected_policy_ic_{_year}"),
        )
        contract_explorer = contract_explorer.join(
            _policy_summary, on="canonical_feature", how="left"
        )
    mo.ui.table(
        contract_explorer.select(
            [
                "discovery_rank",
                "canonical_feature",
                "aliases",
                "feature_window",
                "selected_policy_ic_2024",
                "selected_policy_ic_2025",
                "selected_policy_ic_2026",
                "annual_support_2025",
                "annual_support_2026",
                "joint_support",
                "ci90_same_side_both_years",
                "ci90_lower_2025",
                "ci90_upper_2025",
                "ci90_lower_2026",
                "ci90_upper_2026",
                "amplitude_minimum",
                "rank_signature",
                "group_size",
                "ex_ante_clean_delta_2024",
                "ex_ante_clean_delta_2025",
                "ex_ante_clean_delta_2026",
                "candidate_tier",
            ]
        ),
        page_size=15,
        selection=None,
        freeze_columns_left=["canonical_feature"],
        wrapped_columns=["canonical_feature", "aliases"],
    )
    return


@app.cell
def _(contract_artifacts, contract_feature_choice, contract_policy, mo, pl, px):
    mo.stop(contract_feature_choice.value is None, mo.md("Aucune feature canonique."))
    contract_signal_sensitivity = contract_artifacts.sensitivity.filter(
        pl.col("feature_id") == contract_feature_choice.value
    ).sort("year")
    contract_signal_history = contract_artifacts.history.filter(
        (pl.col("feature_id") == contract_feature_choice.value)
        & (pl.col("policy") == contract_policy.value)
    ).sort("as_of_date")
    contract_signal_chart = px.line(
        contract_signal_history.to_pandas(),
        x="as_of_date",
        y="spearman_ic",
        color="year",
        markers=True,
        title="Signal Detail · IC par cutoff, politique choisie",
    )
    contract_signal_chart.add_hline(y=0, line_dash="dot")
    mo.vstack(
        [
            mo.md("### Signal Detail · effet du filtre futur sur les IC 2024 / 2025 / 2026"),
            mo.ui.table(contract_signal_sensitivity, selection=None),
            mo.ui.plotly(contract_signal_chart),
            mo.md("### Contexte de marché descriptif"),
            mo.ui.table(contract_artifacts.regimes, page_size=10, selection=None),
            mo.md(
                "Les sections suivantes conservent le parcours d'audit initial. "
                "Leurs anciennes sélections ne définissent pas le nouveau candidate lock."
            ),
        ]
    )
    return


@app.cell
def _(date, instrument_options, market_summary, mo):
    default_start = max(market_summary[3], date(2024, 4, 5))
    default_end = min(market_summary[4], date(2025, 10, 4))
    instrument_choice = mo.ui.dropdown(
        options=instrument_options,
        value=next(iter(instrument_options), None),
        searchable=True,
        label="Action SRD",
    )
    start_date = mo.ui.date(
        start=market_summary[3],
        stop=market_summary[4],
        value=default_start,
        label="Début",
    )
    end_date = mo.ui.date(
        start=market_summary[3],
        stop=market_summary[4],
        value=default_end,
        label="Fin",
    )
    jump_threshold = mo.ui.slider(
        start=0.10,
        stop=1.00,
        step=0.05,
        value=0.30,
        show_value=True,
        label="Seuil rupture close/close",
    )
    quality_scope = mo.ui.dropdown(
        options={"Action choisie": "selected", "Tout le SRD": "all"},
        value="Action choisie",
        label="Audit qualité",
    )
    mo.vstack(
        [
            mo.md("## Étape 1 — Prix et périmètre"),
            mo.hstack(
                [instrument_choice, start_date, end_date, jump_threshold, quality_scope],
                justify="start",
                gap=1.5,
            ),
        ]
    )
    return (
        end_date,
        instrument_choice,
        jump_threshold,
        quality_scope,
        start_date,
    )


@app.cell
def _(connection, end_date, instrument_choice, mo, pd, px, start_date):
    mo.stop(instrument_choice.value is None, mo.md("Aucun instrument SRD disponible."))
    price_frame = connection.execute(
        """
        SELECT session_date, open, high, low, close, volume, available_at,
               instrument_id, isin
        FROM market_daily
        WHERE isin=? AND session_date BETWEEN ? AND ?
        ORDER BY session_date
        """,
        [instrument_choice.value, start_date.value, end_date.value],
    ).fetchdf()
    mo.stop(price_frame.empty, mo.md("Aucune barre pour cette action sur la période."))
    price_frame["return_1d"] = price_frame["close"].pct_change()
    close_chart = px.line(
        price_frame,
        x="session_date",
        y="close",
        title=f"Close · {instrument_choice.value}",
        labels={"session_date": "Séance", "close": "Close"},
    )
    close_chart.update_traces(line_color="#d8a45c")
    volume_chart = px.bar(
        price_frame,
        x="session_date",
        y="volume",
        title="Volume source",
        labels={"session_date": "Séance", "volume": "Volume"},
    )
    price_stats = pd.DataFrame(
        [
            {
                "observations": len(price_frame),
                "date_min": price_frame.session_date.min(),
                "date_max": price_frame.session_date.max(),
                "close_min": price_frame.close.min(),
                "close_max": price_frame.close.max(),
                "rendement_période": price_frame.close.iloc[-1] / price_frame.close.iloc[0] - 1,
                "plus_grande_variation_1j": price_frame.return_1d.abs().max(),
            }
        ]
    )
    mo.vstack(
        [
            mo.ui.table(price_stats, selection=None),
            mo.ui.plotly(close_chart),
            mo.ui.plotly(volume_chart),
            mo.md("Dernières barres et instant de disponibilité déclaré"),
            mo.ui.table(price_frame.tail(20), page_size=20, selection=None),
        ]
    )
    return


@app.cell
def _(
    connection,
    end_date,
    instrument_choice,
    jump_threshold,
    mo,
    px,
    quality_scope,
    start_date,
):
    quality_filter = "" if quality_scope.value == "all" else "AND isin=?"
    quality_parameters = [start_date.value, end_date.value]
    if quality_scope.value != "all":
        quality_parameters.append(instrument_choice.value)
    quality_frame = connection.execute(
        f"""
        WITH ordered AS (
          SELECT instrument_id, isin, session_date, open, high, low, close, volume,
                 lag(close) OVER (
                   PARTITION BY instrument_id ORDER BY session_date
                 ) AS previous_close
          FROM market_daily
        ), measured AS (
          SELECT *, close / previous_close - 1 AS return_1d,
                 (high-low) / nullif(close, 0) AS intraday_range
          FROM ordered
          WHERE session_date BETWEEN ? AND ? {quality_filter}
        )
        SELECT * FROM measured
        WHERE abs(return_1d) >= ?
           OR intraday_range > 0.50
           OR high < low
           OR open > high + close * 0.02
           OR open < low - close * 0.02
           OR close > high + close * 0.02
           OR close < low - close * 0.02
        ORDER BY abs(return_1d) DESC NULLS LAST, session_date
        """,
        [*quality_parameters, jump_threshold.value],
    ).fetchdf()
    if quality_frame.empty:
        quality_view = mo.callout(
            mo.md("Aucune rupture au seuil choisi sur ce périmètre."), kind="success"
        )
    else:
        quality_chart = px.scatter(
            quality_frame,
            x="session_date",
            y="return_1d",
            color="isin",
            hover_data=["instrument_id", "previous_close", "close", "intraday_range"],
            title="Observations à contrôler",
            labels={"session_date": "Séance", "return_1d": "Rendement 1 jour"},
        )
        quality_view = mo.vstack(
            [
                mo.ui.plotly(quality_chart),
                mo.ui.table(quality_frame, page_size=20, selection=None),
            ]
        )
    mo.vstack(
        [
            mo.md(
                """
                ## Étape 2 — Contrôle des ruptures

                Ce tableau recherche les variations close/close au-delà du seuil,
                les ranges intraday supérieurs à 50 % et les violations de
                l'enveloppe OHLC. Une rupture est un élément à expliquer par la
                source ou une corporate action ; elle n'est pas automatiquement
                supprimée ou corrigée.
                """
            ),
            quality_view,
        ]
    )
    return


@app.cell
def _(atlas_paths, mo):
    atlas_choice = mo.ui.dropdown(
        options=list(atlas_paths),
        value="H5 uniquement · top 500",
        label="Sélection gelée en 2024",
    )
    mo.vstack(
        [
            mo.md("## Étape 3 — Ouvrir une relation feature/target"),
            atlas_choice,
            mo.md(
                "Le top H5 est sélectionné parmi les relations H5 avant classement. "
                "Il ne s'agit pas de filtrer l'ancien top 500. Les fenêtres des features "
                "peuvent être plus longues : elles décrivent le passé."
            ),
        ]
    )
    return (atlas_choice,)


@app.cell
def _(atlas_choice, atlas_paths, json, mo, pl):
    selected_atlas_path = atlas_paths[atlas_choice.value]
    frozen_path = selected_atlas_path / "frozen_top_signals.parquet"
    mo.stop(
        not frozen_path.is_file(),
        mo.callout(
            mo.md(
                f"Sélection SPEC-006R absente : `{frozen_path}`. "
                "Construisez le Stability Atlas pour activer cette section."
            ),
            kind="warn",
        ),
    )
    frozen_signals = (
        pl.read_parquet(frozen_path)
        .filter((pl.col("scope") == "equity") & (pl.col("selection_bucket") == "return_direction"))
        .sort("discovery_rank")
    )
    feature_options = {
        f"#{rank} · {feature_id}": feature_id
        for rank, feature_id in frozen_signals.select(["discovery_rank", "feature_id"])
        .unique("feature_id", keep="first", maintain_order=True)
        .iter_rows()
    }
    feature_choice = mo.ui.dropdown(
        options=feature_options,
        value=next(iter(feature_options), None),
        searchable=True,
        label="Feature gelée en 2024",
    )
    selected_audit_path = selected_atlas_path / "stability_audit.json"
    selected_atlas_audit = (
        json.loads(selected_audit_path.read_text(encoding="utf-8"))
        if selected_audit_path.is_file()
        else None
    )
    mo.vstack(
        [
            mo.md(
                f"**{frozen_signals.height} relations** · horizons targets : "
                f"{frozen_signals['horizon'].unique().sort().to_list()}"
            ),
            mo.ui.table(
                frozen_signals.group_by("target_family").len().sort("target_family"),
                selection=None,
            ),
            mo.md(
                "Classement descriptif : q-value minimale en 2024 = "
                f"**{frozen_signals['discovery_fdr_q'].min():.4f}**. "
                "Une place dans le top ne signifie pas que la relation est significative."
            ),
            feature_choice,
        ]
    )
    return feature_choice, frozen_signals, selected_atlas_audit


@app.cell
def _(feature_choice, frozen_signals, mo, period_paths):
    target_rows = frozen_signals.filter(
        frozen_signals["feature_id"] == feature_choice.value
    ).select(["target_id", "target_family", "horizon", "discovery_rank"])
    target_options = {
        f"#{rank} · {family} H{horizon} · {target_id}": target_id
        for target_id, family, horizon, rank in target_rows.iter_rows()
    }
    target_choice = mo.ui.dropdown(
        options=target_options,
        value=next(iter(target_options), None),
        searchable=True,
        label="Target",
    )
    period_choice = mo.ui.dropdown(
        options=list(period_paths), value="2024 · discovery", label="Période"
    )
    sample_mode = mo.ui.dropdown(
        options={
            "Pipeline research-ready": "current",
            "Candidates, y compris review/quarantaine": "candidate",
        },
        value="Pipeline research-ready",
        label="Échantillon target",
    )
    mo.hstack([target_choice, period_choice, sample_mode], justify="start", gap=2)
    return period_choice, sample_mode, target_choice


@app.cell
def _(
    date,
    feature_choice,
    mo,
    np,
    pd,
    period_choice,
    period_paths,
    pl,
    px,
    re,
    sample_mode,
    spearmanr,
    target_choice,
):
    selected_paths = period_paths[period_choice.value]
    relation_parts = []
    horizon_match = re.search(r"\.h(\d+)\.", target_choice.value)
    selected_horizon = int(horizon_match.group(1)) if horizon_match else None
    for target_path in sorted(selected_paths["targets"].glob("as_of_date=*/targets.parquet")):
        partition = target_path.parent.name
        cutoff_date = date.fromisoformat(partition.removeprefix("as_of_date="))
        if not (
            date.fromisoformat(selected_paths["start_date"])
            <= cutoff_date
            <= date.fromisoformat(selected_paths["end_date"])
        ):
            continue
        feature_path = selected_paths["features"] / partition / "features.parquet"
        if not feature_path.is_file():
            continue
        feature_part = (
            pl.read_parquet(feature_path)
            .filter(
                (pl.col("entity_family") == "equity")
                & (pl.col("feature_id") == feature_choice.value)
                & (pl.col("feature_status") == "available")
                & pl.col("feature_value").is_not_null()
            )
            .select(["entity_id", "as_of_date", "feature_value"])
            .to_pandas()
        )
        target_part = pl.read_parquet(target_path).filter(
            (pl.col("entity_family") == "equity") & (pl.col("target_id") == target_choice.value)
        )
        if sample_mode.value == "current":
            target_part = target_part.filter(
                pl.col("research_ready")
                & (pl.col("target_status") == "available")
                & pl.col("target_value").is_not_null()
            ).select(["entity_id", "target_value", "target_status", "target_end_date"])
        elif target_choice.value.startswith("future.rank_pct."):
            absolute_id = f"future.return_abs.h{selected_horizon}.v1"
            target_part = (
                pl.read_parquet(target_path)
                .filter(
                    (pl.col("entity_family") == "equity")
                    & (pl.col("target_id") == absolute_id)
                    & pl.col("candidate_value").is_not_null()
                )
                .select(
                    [
                        "entity_id",
                        pl.col("candidate_value").alias("target_value"),
                        "target_status",
                        "target_end_date",
                    ]
                )
            )
        else:
            target_part = target_part.filter(pl.col("candidate_value").is_not_null()).select(
                [
                    "entity_id",
                    pl.col("candidate_value").alias("target_value"),
                    "target_status",
                    "target_end_date",
                ]
            )
        joined = feature_part.merge(target_part.to_pandas(), on="entity_id", how="inner")
        relation_parts.append(joined)
    mo.stop(not relation_parts, mo.md("Aucune partition exploitable pour cette relation."))
    relation_panel = pd.concat(relation_parts, ignore_index=True)
    relation_panel = relation_panel[
        np.isfinite(relation_panel.feature_value) & np.isfinite(relation_panel.target_value)
    ].copy()
    ic_rows = []
    decile_rows = []
    for cutoff, cutoff_frame in relation_panel.groupby("as_of_date"):
        if (
            len(cutoff_frame) < 30
            or cutoff_frame.feature_value.nunique() < 2
            or cutoff_frame.target_value.nunique() < 2
        ):
            continue
        ic_value = float(spearmanr(cutoff_frame.feature_value, cutoff_frame.target_value).statistic)
        ic_rows.append({"as_of_date": cutoff, "spearman_ic": ic_value, "n": len(cutoff_frame)})
        ranked = cutoff_frame.copy()
        ranked["decile"] = (
            pd.qcut(
                ranked.feature_value.rank(method="first"),
                10,
                labels=False,
                duplicates="drop",
            )
            + 1
        )
        aggregate = (
            ranked.groupby("decile", as_index=False)
            .agg(
                target_mean=("target_value", "mean"),
                target_median=("target_value", "median"),
                n=("target_value", "size"),
            )
            .assign(as_of_date=cutoff)
        )
        decile_rows.append(aggregate)
    ic_frame = pd.DataFrame(ic_rows)
    decile_frame = pd.concat(decile_rows, ignore_index=True) if decile_rows else pd.DataFrame()
    mo.stop(ic_frame.empty, mo.md("Moins de 30 couples valides à chaque cutoff."))
    relation_summary = pd.DataFrame(
        [
            {
                "période": period_choice.value,
                "mode": sample_mode.value,
                "feature": feature_choice.value,
                "target": target_choice.value,
                "cutoffs": len(ic_frame),
                "couples": int(ic_frame.n.sum()),
                "IC_moyen": ic_frame.spearman_ic.mean(),
                "IC_médian": ic_frame.spearman_ic.median(),
                "part_IC_positifs": (ic_frame.spearman_ic > 0).mean(),
            }
        ]
    )
    ic_chart = px.line(
        ic_frame,
        x="as_of_date",
        y="spearman_ic",
        markers=True,
        title="IC Spearman par cutoff",
        labels={"as_of_date": "Cutoff", "spearman_ic": "IC"},
    )
    ic_chart.add_hline(y=0, line_dash="dot", line_color="#888")
    decile_summary = (
        decile_frame.groupby("decile", as_index=False).agg(
            target_mean=("target_mean", "mean"),
            target_median=("target_median", "median"),
            observations=("n", "sum"),
        )
        if not decile_frame.empty
        else pd.DataFrame()
    )
    decile_chart = (
        px.line(
            decile_summary,
            x="decile",
            y=["target_mean", "target_median"],
            markers=True,
            title="Target par décile de feature",
            labels={"decile": "Décile faible → élevé", "value": "Target"},
        )
        if not decile_summary.empty
        else None
    )
    relation_view = [
        mo.md(
            """
            ## Étape 4 — Recalculer l'association

            L'IC est recalculé séparément à chaque cutoff après jointure exacte
            sur `entity_id`. Les déciles sont eux aussi reconstruits par cutoff.
            Le mode *candidate* conserve les valeurs numériques marquées
            `future_quality_review` ou `future_quality_quarantined` ; il sert à
            mesurer l'effet du filtre futur, pas à certifier ces prix.
            """
        ),
        mo.ui.table(relation_summary, selection=None),
        mo.ui.plotly(ic_chart),
    ]
    if decile_chart is not None:
        relation_view.extend([mo.ui.plotly(decile_chart), mo.ui.table(decile_summary)])
    relation_view.extend(
        [
            mo.md("Échantillon de couples feature/target"),
            mo.ui.table(relation_panel.head(500), page_size=20, selection=None),
        ]
    )
    mo.vstack(relation_view)
    return


@app.cell
def _(atlas_choice, mo, pd, root_cause_audit, selected_atlas_audit):
    stability_view = []
    if selected_atlas_audit is not None:
        stability_rows = [
            {
                "période": period_id,
                "relations évaluables": metrics["signals_evaluable"],
                "IC moyen 2024": metrics["mean_discovery_ic"],
                "IC moyen période": metrics["mean_validation_ic"],
                "sens conservés": metrics["sign_retained"],
                "inversions": metrics["sign_reversed"],
                "rétention médiane amplitude": metrics["median_impact_retention"],
            }
            for period_id, metrics in selected_atlas_audit[
                "regression_results_primary_scope_equity"
            ]["return_direction"].items()
        ]
        stability_view.extend(
            [
                mo.md(f"### Comparaison gelée · {atlas_choice.value}"),
                mo.ui.table(pd.DataFrame(stability_rows), selection=None),
                mo.md(
                    "`mean_discovery_ic` et `mean_validation_ic` sont des moyennes de "
                    "corrélations de rang, pas des rendements. `median_impact_retention` "
                    "compare les amplitudes absolues des IC. Les q-values sont descriptives ; "
                    "le filtre futur et les relations corrélées restent des limites. "
                    "2026 est partiel : seules les targets déjà mûres sont évaluées."
                ),
            ]
        )
    if root_cause_audit is None:
        root_cause_view = mo.callout(
            mo.md(
                "Audit de cause racine absent. Lancez "
                "`uv run python scripts/audit_spec006r_root_causes.py`."
            ),
            kind="warn",
        )
    else:
        mode_table = pd.DataFrame(root_cause_audit["mode_comparison"])
        serial_table = pd.DataFrame(root_cause_audit["serial_dependence"]).T.reset_index(
            names="période"
        )
        root_cause_view = mo.vstack(
            [
                mo.ui.table(mode_table, selection=None),
                mo.md("Autocorrélation des IC hebdomadaires"),
                mo.ui.table(serial_table, selection=None),
                mo.md(
                    f"Features du top 500 : **{root_cause_audit['top500_unique_features']}** · "
                    f"signatures de rang exactes : "
                    f"**{root_cause_audit['rank_signatures']['exact_rank_signatures']}** · "
                    f"actions communes aux 54 cutoffs : "
                    f"**{root_cause_audit['common_entities_all_54_cutoffs']}**."
                ),
            ]
        )
    mo.vstack(
        [
            mo.md(
                """
                ## Étape 5 — Comparer le sens et l'amplitude

                Les mêmes relations sélectionnées en 2024 sont évaluées en 2025
                et 2026, sans nouvelle sélection. H5 réduit fortement le
                chevauchement des fenêtres hebdomadaires, sans garantir
                l'indépendance des observations.

                """
            ),
            *stability_view,
            mo.accordion(
                {
                    "Audit historique H120 · ancien top tous horizons": mo.vstack(
                        [
                            mo.md(
                                "Ce diagnostic concerne l'ancien top 500, surtout H120. "
                                "Il ne décrit pas la sélection H5. Il compare le filtre futur, "
                                "les candidates et l'univers stable. Les 27 cutoffs H120 "
                                "ne représentent pas 27 fenêtres futures indépendantes."
                            ),
                            root_cause_view,
                        ]
                    ),
                }
            ),
        ]
    )
    return


@app.cell
def _(mo):
    default_query = """SELECT
      isin,
      session_date,
      close,
      volume,
      available_at
    FROM market_daily
    WHERE session_date BETWEEN DATE '2024-04-05' AND DATE '2025-10-04'
    ORDER BY isin, session_date
    LIMIT 200"""
    sql_form = mo.ui.text_area(
        value=default_query,
        rows=12,
        full_width=True,
        label="Requête DuckDB en lecture seule",
    ).form(submit_button_label="Exécuter la requête")
    mo.vstack(
        [
            mo.md(
                """
                ## Étape 6 — SQL libre

                Utilisez `market_daily`, `market_daily_history` et les autres
                vues DuckDB pour vérifier vos propres hypothèses. Le laboratoire
                accepte uniquement une requête commençant par `SELECT` ou `WITH`
                et limite l'affichage à 1 000 lignes.
                """
            ),
            sql_form,
        ]
    )
    return (sql_form,)


@app.cell
def _(connection, mo, re, sql_form):
    mo.stop(sql_form.value is None, mo.md("Soumettez une requête pour afficher le résultat."))
    sql_text = sql_form.value.strip().rstrip(";")
    forbidden_sql = re.compile(
        r"\b(ATTACH|CALL|COPY|EXPORT|IMPORT|INSTALL|LOAD|PRAGMA)\b|"
        r"\b(READ_[A-Z0-9_]*|[A-Z0-9_]*_SCAN|GLOB|QUERY_TABLE)\s*\(|"
        r"(?:HTTPS?|S3|FILE)://|['\"](?:/|\.\.?/)",
        flags=re.IGNORECASE,
    )
    sql_allowed = bool(re.match(r"^(SELECT|WITH)\b", sql_text, flags=re.IGNORECASE)) and not bool(
        forbidden_sql.search(sql_text)
    )
    mo.stop(
        not sql_allowed,
        mo.callout(
            mo.md(
                "Seules les requêtes `SELECT` et `WITH` sur les vues de la base "
                "sont autorisées. Les fichiers, URLs, extensions et commandes DuckDB "
                "d'administration sont bloqués."
            ),
            kind="danger",
        ),
    )
    try:
        sql_result = connection.execute(
            f"SELECT * FROM ({sql_text}) AS user_query LIMIT 1000"
        ).fetchdf()
        sql_view = mo.ui.table(sql_result, page_size=25, selection=None)
    except Exception as sql_error:
        sql_view = mo.callout(mo.md(f"Erreur DuckDB : `{sql_error}`"), kind="danger")
    sql_view  # noqa: B018 -- render the submitted read-only query.
    return


@app.cell
def _(mo):
    rules_text = (
        "## Règles d'interprétation\n\n"
        "1. Une feature utilisant le close D ne devient négociable qu'après ce close ; "
        "testez un prix d'exécution à T+1.\n"
        "2. Un mouvement futur suspect doit rester une annotation. L'utiliser pour retirer "
        "une target conditionne l'échantillon au résultat.\n"
        "3. Pour H120 hebdomadaire, utilisez des fenêtres non chevauchantes ou une "
        "inférence HAC/bootstrap par blocs.\n"
        "4. Regroupez les transformations de rang identiques avant de compter les "
        "découvertes.\n"
        "5. Aucun résultat de ce notebook ne devient tradable avant résolution des "
        "corporate actions et reconstruction d'un univers daté."
    )
    mo.md(rules_text)
    return


if __name__ == "__main__":
    app.run()
