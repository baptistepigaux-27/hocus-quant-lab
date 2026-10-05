"""SPEC-006T corrected direction-H5 scan, sensitivity and candidate locking."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.stats import rankdata

from hocus_quant.analysis.candidate_lock import (
    TARGET,
    build_lock_document,
    fingerprint,
    prepare_confirmation,
    rank_signature_groups,
    write_lock_once,
)
from hocus_quant.features.registry import registry_document
from hocus_quant.targets.research_contract import (
    annotate_outcomes,
    refresh_contract_views,
    select_targets,
)

PERIODS = {2024: "spec006-weekly-demo", 2025: "spec006-2025-matched", 2026: "spec006-2026-matched"}


def measure_h5(
    features: pl.DataFrame,
    targets: pl.DataFrame,
    *,
    minimum_n: int = 30,
) -> pl.DataFrame:
    """Exact pairwise-complete average-rank Spearman for a single H5 cutoff."""
    matrix = features.pivot(on="feature_id", index="entity_id", values="feature_value")
    matrix = matrix.sort("entity_id")
    if targets["entity_id"].is_duplicated().any():
        raise ValueError("multiple H5 outcomes for an entity")
    aligned = matrix.join(
        targets.select("entity_id", "target_value"), on="entity_id", how="left", validate="1:1"
    )
    ids = [col for col in matrix.columns if col != "entity_id"]
    x = aligned.select(ids).to_numpy().astype(float)
    y = aligned["target_value"].to_numpy().astype(float)
    valid = np.isfinite(x) & np.isfinite(y[:, None])
    n = valid.sum(axis=0)
    rx = rankdata(np.where(valid, x, np.nan), axis=0, method="average", nan_policy="omit")
    ry = rankdata(np.where(valid, y[:, None], np.nan), axis=0, method="average", nan_policy="omit")
    rx, ry = np.where(valid, rx, 0), np.where(valid, ry, 0)
    mean_x = rx.sum(axis=0) / np.maximum(n, 1)
    mean_y = ry.sum(axis=0) / np.maximum(n, 1)
    cx, cy = np.where(valid, rx - mean_x, 0), np.where(valid, ry - mean_y, 0)
    denom = np.sqrt((cx**2).sum(axis=0) * (cy**2).sum(axis=0))
    ic = np.divide((cx * cy).sum(axis=0), denom, out=np.full(len(ids), np.nan), where=denom > 0)
    keep = (n >= minimum_n) & np.isfinite(ic)
    return pl.DataFrame(
        {
            "feature_id": np.asarray(ids)[keep].tolist(),
            "spearman_ic": ic[keep],
            "n": n[keep],
            "coverage": n[keep] / max(targets.height, 1),
        },
        schema_overrides={"feature_id": pl.String},
    )


def draw_means(
    values: npt.NDArray[np.float64],
    *,
    block: int,
    replicates: int,
    seed: int,
) -> npt.NDArray[np.float64]:
    n = len(values)
    if not 1 <= block < n or not np.isfinite(values).all():
        raise ValueError("finite complete IC panel required for block bootstrap")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replicates, (n + block - 1) // block))
    indices = ((starts[:, :, None] + np.arange(block)) % n).reshape(replicates, -1)[:, :n]
    counts = np.zeros((replicates, n), dtype=float)
    np.add.at(counts, (np.arange(replicates)[:, None], indices), 1)
    return np.asarray(counts @ values / n, dtype=np.float64)


def bootstrap_candidates(
    history: pl.DataFrame,
    ids: list[str],
    config: dict[str, Any],
) -> pl.DataFrame:
    """Incomplete date panels fail the bootstrap flag; never silently impute ICs."""
    frames: list[pl.DataFrame] = []
    panels = {}
    for year in [2025, 2026]:
        panel = history.filter((pl.col("year") == year) & (pl.col("policy") == "ex_ante"))
        matrix = panel.pivot(on="feature_id", index="as_of_date", values="spearman_ic")
        matrix = matrix.sort("as_of_date")
        panels[year] = matrix
    complete = [
        feature
        for feature in ids
        if all(
            feature in panel.columns and panel[feature].null_count() == 0
            for panel in panels.values()
        )
    ]
    if not complete:
        raise ValueError("no complete development IC panels")
    for block in config["bootstrap_blocks"]:
        draws: dict[int, npt.NDArray[np.float64]] = {}
        record: dict[str, Any] = {"feature_id": complete, "block_length": block}
        for year, panel in panels.items():
            values = panel.select(complete).to_numpy().astype(float)
            means = values.mean(axis=0)
            draws[year] = draw_means(
                values,
                block=block,
                replicates=config["bootstrap_replicates"],
                seed=config["bootstrap_seed"] + year * 100 + block,
            )
            q = np.quantile(draws[year], [0.025, 0.05, 0.95, 0.975], axis=0)
            record[f"support_{year}"] = (draws[year] * np.sign(means) > 0).mean(axis=0)
            record[f"ci90_lower_{year}"], record[f"ci90_upper_{year}"] = q[1], q[2]
            record[f"ci95_lower_{year}"], record[f"ci95_upper_{year}"] = q[0], q[3]
        record["joint_support"] = (draws[2025] * draws[2026] > 0).mean(axis=0)
        frames.append(pl.DataFrame(record))
    return pl.concat(frames)


def _past_bars(db: duckdb.DuckDBPyConnection, day: date) -> pl.DataFrame:
    cutoff = datetime.combine(
        day + timedelta(days=1), datetime.min.time(), ZoneInfo("Europe/Paris")
    )
    return db.execute(
        """SELECT 'abc-bourse-manual:equity:' || COALESCE(isin,instrument_id)
        AS entity_id, session_date, close FROM market_daily_history
        WHERE session_date<=? AND available_at<=? AND close>0
        QUALIFY row_number() OVER (PARTITION BY instrument_id,session_date
            ORDER BY retrieved_at DESC,snapshot_id DESC)=1
        ORDER BY entity_id,session_date""",
        [day, cutoff],
    ).pl()


def _regime(
    db: duckdb.DuckDBPyConnection,
    day: date,
    past: pl.DataFrame,
    eligible: set[str],
) -> dict[str, Any]:
    cutoff = datetime.combine(
        day + timedelta(days=1), datetime.min.time(), ZoneInfo("Europe/Paris")
    )
    index = db.execute(
        """SELECT session_date,close FROM market_series_history
        WHERE universe_id='market_indices' AND series_id='market_indices:QS0010989141'
        AND session_date<=? AND available_at<=? AND close>0
        QUALIFY row_number() OVER(PARTITION BY series_id,session_date
            ORDER BY retrieved_at DESC,snapshot_checksum DESC)=1
        ORDER BY session_date""",
        [day, cutoff],
    ).pl()
    prices = index["close"].to_numpy()
    market_return = float(prices[-1] / prices[-21] - 1) if len(prices) >= 21 else None
    volatility = (
        float(np.std(np.diff(np.log(prices[-21:])), ddof=1) * np.sqrt(252))
        if len(prices) >= 21
        else None
    )
    returns = []
    for part in past.filter(pl.col("entity_id").is_in(eligible)).partition_by("entity_id"):
        closes = part["close"].to_numpy()
        if len(closes) >= 21:
            returns.append(float(closes[-1] / closes[-21] - 1))
    return {
        "as_of_date": day,
        "market_return_20": market_return,
        "market_state": "up"
        if market_return is not None and market_return > 0
        else "down"
        if market_return is not None and market_return < 0
        else "flat_or_missing",
        "global_volatility_20": volatility,
        "dispersion_20": float(np.std(returns, ddof=1)) if len(returns) > 1 else None,
        "breadth_20": float(np.mean(np.asarray(returns) > 0)) if returns else None,
        "large_market_trend_60": float(prices[-1] / np.mean(prices[-60:]) - 1)
        if len(prices) >= 60
        else None,
        "equity_regime_observations": len(returns),
        "pit_grade": "reconstructed",
    }


def _summary(history: pl.DataFrame) -> pl.DataFrame:
    return (
        history.group_by(["year", "policy", "feature_id"])
        .agg(
            pl.col("spearman_ic").mean().alias("ic_mean"),
            pl.len().alias("cutoffs"),
            pl.col("n").sum().alias("observations"),
            pl.col("coverage").mean().alias("coverage"),
            pl.col("spearman_ic").std().alias("ic_std"),
        )
        .sort(["year", "policy", "feature_id"])
    )


def _sensitivity(summary: pl.DataFrame) -> pl.DataFrame:
    frame = summary.select("year", "policy", "feature_id", "ic_mean").pivot(
        on="policy", index=["year", "feature_id"], values="ic_mean"
    )
    return frame.with_columns(
        (pl.col("ex_ante") - pl.col("legacy_research_ready")).alias("ic_delta_vs_legacy"),
        (pl.col("ex_ante") - pl.col("clean_future")).alias("ic_delta_vs_clean"),
        (pl.col("ex_ante") * pl.col("legacy_research_ready") < 0).alias("sign_flip_vs_legacy"),
    ).sort(["year", "feature_id"])


def compare_existing_h5(root: Path, summary: pl.DataFrame) -> list[dict[str, Any]]:
    reference_path = root / (
        "data/analysis/spec006r-h5-top100-by-window-2025-2026/signal_comparison.parquet"
    )
    reference = pl.read_parquet(reference_path)
    checks = []
    for year in [2024, 2025, 2026]:
        legacy = summary.filter(
            (pl.col("year") == year) & (pl.col("policy") == "legacy_research_ready")
        )
        joined = legacy.join(
            reference.select("feature_id", pl.col(f"ic_{year}").alias("reference_ic")),
            on="feature_id",
            how="inner",
            validate="1:1",
        )
        maximum = joined.select((pl.col("ic_mean") - pl.col("reference_ic")).abs().max()).item()
        if joined.height != reference.height or maximum is None or maximum > 1e-12:
            raise ValueError(f"legacy H5 IC reproduction failed in {year}")
        checks.append({"year": year, "relations": joined.height, "max_abs_ic_error": maximum})
    return checks


def period_comparisons(
    summary: pl.DataFrame,
    cohorts: dict[str, list[str]],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    metrics, stability = [], []
    for cohort_name, ids in cohorts.items():
        for policy in ["legacy_research_ready", "ex_ante", "clean_future"]:
            chosen = summary.filter((pl.col("policy") == policy) & pl.col("feature_id").is_in(ids))
            for year in [2024, 2025, 2026]:
                part = chosen.filter(pl.col("year") == year)
                metrics.append(
                    {
                        "cohort": cohort_name,
                        "policy": policy,
                        "year": year,
                        "relations": part.height,
                        "mean_ic": part["ic_mean"].mean(),
                        "median_abs_ic": part["ic_mean"].abs().median(),
                        "minimum_cutoffs": part["cutoffs"].min(),
                        "observations": part["observations"].sum(),
                    }
                )
            for first, second in [(2024, 2025), (2024, 2026), (2025, 2026)]:
                left = chosen.filter(pl.col("year") == first).select("feature_id", "ic_mean")
                right = chosen.filter(pl.col("year") == second).select("feature_id", "ic_mean")
                pairs = left.join(right, on="feature_id", suffix="_later").filter(
                    (pl.col("ic_mean").abs() > 1e-12) & (pl.col("ic_mean_later").abs() > 1e-12)
                )
                flipped = pairs.filter(pl.col("ic_mean") * pl.col("ic_mean_later") < 0).height
                retention = pairs.select(
                    (pl.col("ic_mean_later").abs() / pl.col("ic_mean").abs()).median()
                ).item()
                stability.append(
                    {
                        "cohort": cohort_name,
                        "policy": policy,
                        "first_year": first,
                        "second_year": second,
                        "evaluable": pairs.height,
                        "inverted": flipped,
                        "retained": pairs.height - flipped,
                        "inversion_rate": flipped / pairs.height if pairs.height else None,
                        "median_amplitude_retention": retention,
                    }
                )
    return pl.DataFrame(metrics), pl.DataFrame(stability)


def _candidate_table(
    summary: pl.DataFrame,
    groups: pl.DataFrame,
    bootstrap: pl.DataFrame,
    sensitivity: pl.DataFrame,
    config: dict[str, Any],
) -> pl.DataFrame:
    table = groups.rename({"canonical_feature": "feature_id"})
    for year in [2024, 2025, 2026]:
        part = summary.filter((pl.col("year") == year) & (pl.col("policy") == "ex_ante"))
        part = part.select("feature_id", "ic_mean", "cutoffs", "observations", "coverage")
        part = part.rename({c: f"{c}_{year}" for c in part.columns if c != "feature_id"})
        table = table.join(part, on="feature_id", how="left", validate="1:1")
        deltas = sensitivity.filter(pl.col("year") == year).select(
            "feature_id", pl.col("ic_delta_vs_clean").alias(f"ex_ante_clean_delta_{year}")
        )
        table = table.join(deltas, on="feature_id", how="left", validate="1:1")
    table = table.filter(
        (pl.col("cutoffs_2024") >= config["minimum_discovery_cutoffs"])
        & (pl.col("observations_2024") >= config["minimum_discovery_pairs"])
        & (pl.col("coverage_2024") >= config["minimum_discovery_coverage"])
    )
    robust = bootstrap.group_by("feature_id").agg(
        pl.col("support_2025").min().alias("annual_support_2025"),
        pl.col("support_2026").min().alias("annual_support_2026"),
        pl.col("joint_support").min().alias("joint_support"),
        (
            ((pl.col("ci90_lower_2025") > 0) & (pl.col("ci90_lower_2026") > 0))
            | ((pl.col("ci90_upper_2025") < 0) & (pl.col("ci90_upper_2026") < 0))
        )
        .all()
        .alias("ci90_same_side_both_years"),
    )
    bounds = bootstrap.filter(pl.col("block_length") == 4).select(
        "feature_id", "ci90_lower_2025", "ci90_upper_2025", "ci90_lower_2026", "ci90_upper_2026"
    )
    table = table.join(robust, on="feature_id", how="left").join(
        bounds, on="feature_id", how="left"
    )
    table = table.with_columns(
        (pl.col("ic_mean_2025") * pl.col("ic_mean_2026") > 0).alias("same_sign_2025_2026"),
        pl.col("ic_mean_2025").sign().cast(pl.Int32).alias("locked_direction"),
        ((pl.col("annual_support_2025") > 0.9) & (pl.col("annual_support_2026") > 0.9)).alias(
            "annual_sign_support_gt90"
        ),
        (pl.col("joint_support") > 0.9).alias("joint_sign_support_gt90"),
        (
            (pl.col("ic_mean_2025").abs() >= config["amplitude_minimum"])
            & (pl.col("ic_mean_2026").abs() >= config["amplitude_minimum"])
        ).alias("amplitude_minimum"),
        (
            (pl.col("observations_2025") >= config["minimum_discovery_pairs"])
            & (pl.col("observations_2026") >= config["minimum_discovery_pairs"])
        ).alias("minimum_observations"),
        (
            (pl.col("cutoffs_2025") >= config["minimum_development_cutoffs"])
            & (pl.col("cutoffs_2026") >= config["minimum_development_cutoffs"])
        ).alias("minimum_cutoffs"),
        pl.lit(True).alias("rank_signature_uniqueness"),
        pl.lit(TARGET).alias("target_id"),
        pl.lit(5).alias("horizon"),
        pl.col("feature_id").str.extract(r"\.w(\d+)\.", 1).cast(pl.Int64).alias("feature_window"),
    ).with_columns(
        pl.all_horizontal(
            "same_sign_2025_2026",
            "amplitude_minimum",
            "minimum_observations",
            "minimum_cutoffs",
            "rank_signature_uniqueness",
        )
        .fill_null(False)
        .alias("broad_candidates")
    )
    table = table.with_columns(
        pl.all_horizontal("broad_candidates", "annual_sign_support_gt90", "joint_sign_support_gt90")
        .fill_null(False)
        .alias("strong_sign_candidates")
    )
    table = table.with_columns(
        pl.all_horizontal("strong_sign_candidates", "ci90_same_side_both_years")
        .fill_null(False)
        .alias("strict_candidates")
    )
    table = table.with_columns(
        pl.when(pl.col("strict_candidates"))
        .then(pl.lit("strict"))
        .when(pl.col("strong_sign_candidates"))
        .then(pl.lit("strong_sign"))
        .when(pl.col("broad_candidates"))
        .then(pl.lit("broad"))
        .otherwise(pl.lit("not_selected"))
        .alias("candidate_tier")
    )
    table = table.sort(["ic_mean_2024", "feature_id"], descending=[True, False])
    # Ranking uses absolute discovery IC, with no opaque combined score.
    table = table.with_columns(pl.col("ic_mean_2024").abs().alias("abs_discovery_ic"))
    table = table.sort(["abs_discovery_ic", "feature_id"], descending=[True, False])
    return table.with_row_index("discovery_rank", offset=1).rename(
        {"feature_id": "canonical_feature"}
    )


def run_research_contract(*, root: Path, output: Path, config_path: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text())
    if config["target_id"] != TARGET or config["scope"] != "equity" or config["horizon"] != 5:
        raise ValueError("SPEC-006T V1 is restricted to equity absolute direction H5")
    output.mkdir(parents=True, exist_ok=True)
    histories, discovery, ledgers, outcomes, counts, regimes = [], [], [], [], [], []
    sources: list[dict[str, str]] = []
    with duckdb.connect(str(root / "data/research.duckdb"), read_only=True) as db:
        for year, name in PERIODS.items():
            feature_root, target_root = (
                root / "data/feature_cube" / name,
                root / "data/targets" / name,
            )
            cube_contract = json.loads((feature_root / "contract.json").read_text())["contract"]
            if cube_contract["feature_registry_fingerprint"] != registry_document()["sha256"]:
                raise ValueError(f"feature registry drift in development period {year}")
            for fp in sorted(feature_root.glob("as_of_date=*/features.parquet")):
                day = date.fromisoformat(fp.parent.name.split("=")[1])
                if not date(year, 4, 5) <= day <= date(year, 10, 4):
                    continue
                tp, qp = (
                    target_root / fp.parent.name / "targets.parquet",
                    fp.parent / "quality_status.parquet",
                )
                for path in [fp, tp, qp]:
                    sources.append(
                        {
                            "path": str(path.relative_to(root)),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    )
                features = pl.read_parquet(fp).filter(pl.col("entity_family") == "equity")
                feature_entities = set(features["entity_id"].to_list())
                past = _past_bars(db, day)
                history_counts = (
                    past.group_by("entity_id").len().rename({"len": "past_observation_count"})
                )
                quality = pl.read_parquet(qp).filter(pl.col("entity_family") == "equity")
                ledger = quality.join(history_counts, on="entity_id", how="left").with_columns(
                    pl.lit(day).alias("as_of_date"),
                    (
                        (pl.col("quality_status") == "approved")
                        & (pl.col("past_observation_count") >= 1)
                        & pl.col("entity_id").is_in(feature_entities)
                    )
                    .fill_null(False)
                    .alias("eligible_at_cutoff"),
                    pl.when(~pl.col("entity_id").is_in(feature_entities))
                    .then(pl.lit("no_feature_history_at_T"))
                    .when(pl.col("quality_status") == "approved")
                    .then(pl.lit("approved_at_T"))
                    .otherwise(pl.lit("quality_not_approved_at_T"))
                    .alias("eligibility_reason"),
                    pl.lit(year).alias("year"),
                )
                targets = pl.read_parquet(tp).filter(
                    (pl.col("entity_family") == "equity") & (pl.col("target_id") == TARGET)
                )
                # Recompute the unchanged H5 formula from stored endpoint evidence.
                computed = targets.with_columns(
                    ((pl.col("end_price") / pl.col("start_price") - 1).sign())
                    .cast(pl.Float64)
                    .alias("recomputed_candidate")
                )
                if computed.filter(
                    pl.col("candidate_value").is_not_null()
                    & (pl.col("candidate_value") != pl.col("recomputed_candidate"))
                ).height:
                    raise ValueError(f"H5 candidate formula mismatch: {day}")
                targets = annotate_outcomes(targets, ledger).with_columns(
                    pl.lit(year).alias("year")
                )
                approved = set(ledger.filter(pl.col("eligible_at_cutoff"))["entity_id"].to_list())
                if approved != set(targets["entity_id"].to_list()):
                    raise ValueError(
                        f"past eligible cohort differs from complete outcome ledger: {day}"
                    )
                # Available features are past-only; future outcomes never enter signatures.
                available = features.filter(
                    (pl.col("feature_status") == "available")
                    & pl.col("feature_value").is_not_null()
                    & pl.col("feature_value").is_finite()
                    & pl.col("entity_id").is_in(approved)
                )
                if year == 2024:
                    discovery.append(
                        available.select("entity_id", "as_of_date", "feature_id", "feature_value")
                    )
                ledgers.append(ledger)
                outcomes.append(targets)
                regimes.append({**_regime(db, day, past, approved), "year": year})
                count = {
                    "year": year,
                    "as_of_date": day,
                    "eligible_at_cutoff": len(approved),
                    "all_entities_at_cutoff": ledger.height,
                    "target_observable": targets.filter(pl.col("target_observable")).height,
                    "uninterpretable": targets.filter(
                        pl.col("target_observable") & ~pl.col("target_interpretable")
                    ).height,
                    "right_censored": targets.filter(pl.col("is_end_of_sample_censored")).height,
                }
                for policy in config["policies"]:
                    sample = select_targets(targets, policy)
                    count[policy] = sample.height
                    measured = measure_h5(
                        available, sample, minimum_n=config["minimum_pairs_per_cutoff"]
                    )
                    histories.append(
                        measured.with_columns(
                            pl.lit(year).alias("year"),
                            pl.lit(day).alias("as_of_date"),
                            pl.lit(policy).alias("policy"),
                        )
                    )
                counts.append(count)
                print(
                    f"{day}: cohort={len(approved)} "
                    f"ex_ante={count['ex_ante']} clean={count['clean_future']}",
                    flush=True,
                )
    history, ledger_frame, target_frame = (
        pl.concat(histories),
        pl.concat(ledgers),
        pl.concat(outcomes),
    )
    groups = rank_signature_groups(pl.concat(discovery))
    summary = _summary(history)
    reproduction = compare_existing_h5(root, summary)
    sensitivity = _sensitivity(summary)
    ids = groups["canonical_feature"].to_list()
    bootstrap = bootstrap_candidates(history, ids, config)
    candidates = _candidate_table(summary, groups, bootstrap, sensitivity, config)
    lock_rows = candidates.filter(pl.col("broad_candidates")).to_dicts()
    source_fingerprint = fingerprint(sources)
    registry_sha = str(registry_document()["sha256"])
    implementation_paths = [
        Path(__file__),
        Path(__file__).with_name("candidate_lock.py"),
        root / "src/hocus_quant/targets/research_contract.py",
    ]
    implementation_fingerprint = fingerprint(
        [
            {"path": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in implementation_paths
        ]
    )
    lock_contract = {
        **config,
        "feature_registry_sha256": registry_sha,
        "source_fingerprint": source_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
        "data_observed_through": "2026-09-28",
        "pit_grade": "reconstructed",
        "strict_pit_claimed": False,
        "execution_current_target": "close_T",
        "execution_future_strategy": "next_open",
        "confirmed_out_of_sample": False,
    }
    lock = build_lock_document(lock_rows, contract=lock_contract)
    write_lock_once(output / "candidate_lock_v1.json", lock)
    write_lock_once(root / "configs/research/candidate_lock_v1.json", lock)
    latest_outcome = target_frame["target_end_date"].drop_nulls().max()
    confirmation = prepare_confirmation(
        lock,
        first_cutoff="2026-10-06",
        feature_registry_sha256=registry_sha,
        last_development_outcome_date=str(latest_outcome),
    )
    counts_frame, regimes_frame = pl.DataFrame(counts), pl.DataFrame(regimes)
    regime_ics = history.filter(pl.col("policy") == "ex_ante").join(
        regimes_frame, on=["year", "as_of_date"], how="left", validate="m:1"
    )
    regime_summary = regime_ics.group_by(["year", "market_state", "feature_id"]).agg(
        pl.col("spearman_ic").mean().alias("ic_mean"), pl.len().alias("cutoffs")
    )
    old_500 = pl.read_parquet(
        root / ("data/analysis/spec006r-stability-atlas-h5-top500/frozen_top_signals.parquet")
    ).filter((pl.col("target_id") == TARGET) & (pl.col("scope") == "equity"))
    old_815 = pl.read_parquet(
        root / ("data/analysis/spec006r-h5-top100-by-window-2025-2026/signal_comparison.parquet")
    )
    cohorts = {
        "old_top500": old_500["feature_id"].to_list(),
        "old_top100_by_window_815": old_815["feature_id"].to_list(),
        "corrected_unique_discovery": candidates["canonical_feature"].to_list(),
    }
    for tier in ["broad_candidates", "strong_sign_candidates", "strict_candidates"]:
        cohorts[tier] = candidates.filter(pl.col(tier))["canonical_feature"].to_list()
    metrics, stability = period_comparisons(summary, cohorts)
    regime_candidate_parts = []
    for tier in ["broad_candidates", "strong_sign_candidates", "strict_candidates"]:
        selected = candidates.filter(pl.col(tier)).select(
            pl.col("canonical_feature").alias("feature_id"),
            pl.col("ic_mean_2025").sign().alias("development_orientation"),
        )
        aligned_regimes = regime_ics.join(selected, on="feature_id", how="inner")
        regime_candidate_parts.append(
            aligned_regimes.group_by(["year", "market_state"])
            .agg(
                (pl.col("spearman_ic") * pl.col("development_orientation"))
                .mean()
                .alias("mean_oriented_ic"),
                pl.col("as_of_date").n_unique().alias("cutoffs"),
                pl.col("feature_id").n_unique().alias("features"),
            )
            .with_columns(pl.lit(tier).alias("candidate_tier"))
        )
    regime_candidate_summary = pl.concat(regime_candidate_parts)
    for name, frame in {
        "eligibility_at_cutoff": ledger_frame,
        "targets": target_frame,
        "ic_history": history,
        "ic_summary": summary,
        "cohort_sizes": counts_frame,
        "rank_signature_groups": groups,
        "ex_ante_filter_sensitivity": sensitivity,
        "bootstrap_intervals": bootstrap,
        "candidate_explorer": candidates,
        "candidate_lock_v1": candidates.filter(pl.col("broad_candidates")),
        "market_regimes": regimes_frame,
        "regime_ic_summary": regime_summary,
        "period_metrics": metrics,
        "period_stability": stability,
        "regime_candidate_summary": regime_candidate_summary,
    }.items():
        frame.write_parquet(output / f"{name}.parquet")
    for policy in ["ex_ante", "clean_future"]:
        selected = target_frame.filter(pl.col("eligible_at_cutoff") & pl.col("target_observable"))
        if policy == "clean_future":
            selected = select_targets(selected, "clean_future")
        selected.write_parquet(output / f"targets_{policy}.parquet")
    with duckdb.connect(str(output / "research_contract.duckdb")) as db:
        for name in ["targets", "eligibility_at_cutoff", "candidate_explorer", "market_regimes"]:
            sql_path = str((output / f"{name}.parquet").resolve()).replace("'", "''")
            db.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{sql_path}')")
        refresh_contract_views(db)
    status = (
        "candidate lock ready for independent confirmation"
        if lock_rows
        else "candidate lock not ready for independent confirmation"
    )
    audit = {
        "contract": lock_contract,
        "lock_sha256": lock["lock_sha256"],
        "status": status,
        "confirmation": confirmation,
        "sources": sources,
        "discovery_features_with_data": int(groups["group_size"].sum()),
        "rank_signatures_unique": groups.height,
        "duplicate_features_removed": int(groups["group_size"].sum()) - groups.height,
        "legacy_reproduction": reproduction,
        "period_metrics": metrics.to_dicts(),
        "period_stability": stability.to_dicts(),
        "discovery_eligible_canonical_features": candidates.height,
        "candidate_counts_nested": {
            name: candidates.filter(pl.col(name)).height
            for name in ["broad_candidates", "strong_sign_candidates", "strict_candidates"]
        },
        "cohort_by_period": counts_frame.group_by("year")
        .agg(
            *[
                pl.col(c).sum().alias(f"{c}_sum")
                for c in [
                    "eligible_at_cutoff",
                    "target_observable",
                    "ex_ante",
                    "clean_future",
                    "uninterpretable",
                ]
            ],
            pl.col("eligible_at_cutoff").min().alias("eligible_min"),
            pl.col("eligible_at_cutoff").max().alias("eligible_max"),
            pl.len().alias("cutoffs"),
        )
        .sort("year")
        .to_dicts(),
        "sensitivity": sensitivity.group_by("year")
        .agg(
            pl.col("ic_delta_vs_legacy").abs().mean().alias("mean_abs_delta_vs_legacy"),
            pl.col("ic_delta_vs_legacy").abs().max().alias("max_abs_delta_vs_legacy"),
            pl.col("sign_flip_vs_legacy").sum().alias("mean_ic_sign_changes"),
            pl.col("ic_delta_vs_clean").abs().mean().alias("mean_abs_delta_vs_clean"),
        )
        .sort("year")
        .to_dicts(),
        "regime_by_period": regimes_frame.group_by("year")
        .agg(
            pl.col("market_return_20").mean(),
            pl.col("global_volatility_20").mean(),
            pl.col("dispersion_20").mean(),
            pl.col("breadth_20").mean(),
            pl.col("large_market_trend_60").mean(),
            (pl.col("market_state") == "up").sum().alias("up_cutoffs"),
        )
        .sort("year")
        .to_dicts(),
        "regime_candidate_summary": regime_candidate_summary.sort(
            ["candidate_tier", "year", "market_state"]
        ).to_dicts(),
        "limitations": [
            "Reconstructed PIT and delivered SRD universe",
            "Hard future source errors excluded from numerical IC, never from frozen cohort",
            "Pointwise bootstrap, no multiple-comparison correction",
            "Development periods reused; lock is exploratory, not confirmation or alpha",
            "Current close_T target is not an executable next_open strategy",
        ],
    }
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    (output / "confirmation_request.json").write_text(json.dumps(confirmation, indent=2) + "\n")
    (output / "audit.md").write_text(render_audit(audit))
    output.chmod(0o755)
    for path in output.iterdir():
        if path.is_file():
            path.chmod(0o644)
    return audit


def render_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# SPEC-006T — audit de recherche ex ante",
        "",
        f"**Statut : {audit['status']}**",
        "",
        "2024–2026 sont des périodes de développement. Confirmation indépendante en attente.",
        "",
        "## Cohortes (sommes de lignes entité/cutoff, pas titres uniques)",
        "",
        "| Année | Dates | Éligibles à T | Observables | IC ex ante | "
        "Future clean | Ininterprétables |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in audit["cohort_by_period"]:
        lines.append(
            f"| {row['year']} | {row['cutoffs']} | {row['eligible_at_cutoff_sum']} | "
            f"{row['target_observable_sum']} | {row['ex_ante_sum']} | {row['clean_future_sum']} | "
            f"{row['uninterpretable_sum']} |"
        )
    lines += [
        "",
        "## Sensibilité au filtre futur",
        "",
        "| Année | Moyenne abs Δ IC vs legacy | Maximum abs Δ | Signes moyens changés |",
        "|---|---:|---:|---:|",
    ]
    for row in audit["sensitivity"]:
        lines.append(
            f"| {row['year']} | {row['mean_abs_delta_vs_legacy']:.6f} | "
            f"{row['max_abs_delta_vs_legacy']:.6f} | {row['mean_ic_sign_changes']} |"
        )
    lines += [
        "",
        "## Déduplication et candidats",
        "",
        f"- Signatures discovery uniques : {audit['rank_signatures_unique']}.",
        f"- Duplicats de rang regroupés : {audit['duplicate_features_removed']}.",
        f"- Cohortes imbriquées : {audit['candidate_counts_nested']}.",
        "",
        "## Régimes descriptifs (information passée seulement)",
        "",
        "| Année | Retour marché 20 séances | Volatilité | Dispersion | "
        "Breadth | Trend 60 | Dates haussières |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in audit["regime_by_period"]:
        values = [
            f"{row[col]:.4f}" if row[col] is not None else "n.d."
            for col in [
                "market_return_20",
                "global_volatility_20",
                "dispersion_20",
                "breadth_20",
                "large_market_trend_60",
            ]
        ]
        lines.append(f"| {row['year']} | " + " | ".join(values) + f" | {row['up_cutoffs']} |")
    lines += [
        "",
        "Ces états décrivent le contexte ; ils ne prouvent pas la cause des inversions.",
        "Les moyennes de régime ne sont pas des rendements annuels.",
        "",
        "## Limites",
        "",
    ]
    lines += [f"- {item}" for item in audit["limitations"]]
    lines += ["", f"Lock SHA256 : `{audit['lock_sha256']}`", ""]
    return "\n".join(lines)
