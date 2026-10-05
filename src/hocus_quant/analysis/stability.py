"""Discovery/validation stability atlas for frozen SPEC-006 relations."""

from __future__ import annotations

import hashlib
import json
import math
import tomllib
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from scipy.stats import t as student_t
from statsmodels.stats.multitest import multipletests

from hocus_quant.analysis.signals import analyze_cutoff

_GENERAL = "general"
_RETURN = "return_direction"
_IDENTITY_COLUMNS = (
    "feature_id",
    "target_id",
    "horizon",
    "scope",
    "metric_definition",
)


def signal_identity_id(identity: dict[str, Any]) -> str:
    """Return a deterministic ID for a feature/target/scope/metric relation."""
    payload = json.dumps(
        {key: identity[key] for key in _IDENTITY_COLUMNS}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def freeze_top_signals(
    discovery_period: dict[str, Any],
    target_scope: str,
    n: int,
    *,
    analysis_database: Path,
    selection_rule_version: str,
    minimum_n: int = 1000,
    minimum_cutoffs: int = 13,
    minimum_coverage: float = 0.60,
    return_target_families: set[str] | None = None,
    target_horizons: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Freeze a discovery-only top N; this function never reads validation data."""
    if n < 1:
        raise ValueError("N must be positive")
    if target_horizons is not None and (
        not target_horizons or any(horizon < 1 for horizon in target_horizons)
    ):
        raise ValueError("target_horizons must contain positive horizons")
    if not analysis_database.is_file():
        raise FileNotFoundError(f"discovery database not found: {analysis_database}")
    with duckdb.connect(str(analysis_database), read_only=True) as db:
        frame = db.execute(
            """SELECT feature_id, target_id, target_family, horizon, scope, n_total,
                      cutoff_count, spearman_ic_mean, ic_median, hit_rate, coverage,
                      fdr_q_value, top_bottom_spread, monotonicity_spearman,
                      feature_family, feature_source_series, feature_metric,
                      feature_window, target_formula, target_scale, status
               FROM signal_summary
               WHERE scope=? AND status='eligible' AND n_total>=?
                 AND cutoff_count>=? AND coverage>=?""",
            [target_scope, minimum_n, minimum_cutoffs, minimum_coverage],
        ).fetchdf()
    if return_target_families is not None:
        frame = frame.loc[frame["target_family"].isin(return_target_families)]
    if target_horizons is not None:
        frame = frame.loc[frame["horizon"].isin(target_horizons)]
    frame = frame.dropna(subset=["spearman_ic_mean", "feature_id", "target_id"]).copy()
    frame["fdr_q_value"] = pd.to_numeric(frame["fdr_q_value"], errors="coerce")
    frame["abs_ic"] = frame["spearman_ic_mean"].abs()
    frame = frame.sort_values(
        ["fdr_q_value", "abs_ic", "coverage", "cutoff_count", "feature_id", "target_id"],
        ascending=[True, False, False, False, True, True],
        na_position="last",
        kind="mergesort",
    ).head(n)
    bucket = _RETURN if return_target_families is not None else _GENERAL
    frozen: list[dict[str, Any]] = []
    for rank, row in enumerate(frame.to_dict(orient="records"), start=1):
        metric_definition = json.dumps(
            {
                "metric": "cross_sectional_spearman_ic",
                "target_formula": row.get("target_formula"),
                "target_scale": row.get("target_scale"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        identity = {
            "feature_id": str(row["feature_id"]),
            "target_id": str(row["target_id"]),
            "horizon": int(row["horizon"]),
            "scope": target_scope,
            "metric_definition": metric_definition,
        }
        frozen.append(
            {
                **identity,
                "signal_id": signal_identity_id(identity),
                "selection_bucket": bucket,
                "selection_rule_version": selection_rule_version,
                "discovery_period_id": str(discovery_period["id"]),
                "discovery_start_date": str(discovery_period["start_date"]),
                "discovery_end_date": str(discovery_period["end_date"]),
                "target_family": str(row["target_family"]),
                "discovery_rank": rank,
                "discovery_ic_mean": float(row["spearman_ic_mean"]),
                "discovery_ic_median": _optional_float(row.get("ic_median")),
                "discovery_hit_rate": _optional_float(row.get("hit_rate")),
                "discovery_n": int(row["n_total"]),
                "discovery_cutoffs": int(row["cutoff_count"]),
                "discovery_coverage": float(row["coverage"]),
                "discovery_fdr_q": _optional_float(row.get("fdr_q_value")),
                "discovery_top_bottom_spread": _optional_float(row.get("top_bottom_spread")),
                "discovery_monotonicity": _optional_float(row.get("monotonicity_spearman")),
                "feature_family": row.get("feature_family"),
                "feature_source_series": row.get("feature_source_series"),
                "feature_metric": row.get("feature_metric"),
                "feature_window": _optional_int(row.get("feature_window")),
                "target_formula": row.get("target_formula"),
                "target_scale": row.get("target_scale"),
            }
        )
    return frozen


def classify_stability(
    *,
    evaluated_cutoffs: int,
    mature_cutoffs: int,
    sign_retained: bool | None,
    aligned_sign_rate: float | None,
    impact_retention: float | None,
    maturity_ratio: float | None,
    minimum_cutoffs: int = 4,
    stable_impact_retention: float = 0.80,
    minimum_period_sign_consistency: float = 0.60,
) -> str:
    """Apply transparent descriptive classes; these are not significance labels."""
    if evaluated_cutoffs < minimum_cutoffs or mature_cutoffs < minimum_cutoffs:
        return "insufficient_validation"
    if sign_retained is False:
        return "sign_reversed"
    if aligned_sign_rate is not None and aligned_sign_rate < minimum_period_sign_consistency:
        return "unstable"
    if (
        sign_retained is True
        and impact_retention is not None
        and impact_retention >= stable_impact_retention
        and maturity_ratio is not None
        and maturity_ratio >= 0.80
    ):
        return "stable"
    if sign_retained is True:
        return "weakened"
    return "unstable"


def calculate_retention(
    discovery_ic: float | None, validation_ic: float | None
) -> tuple[bool | None, float | None, float | None]:
    """Return sign agreement, signed retention, and uncapped absolute retention."""
    if discovery_ic is None or validation_ic is None or abs(discovery_ic) <= 1e-12:
        return None, None, None
    signed = validation_ic / discovery_ic
    return bool(np.sign(discovery_ic) == np.sign(validation_ic)), signed, abs(signed)


def calculate_maturity_ratio(mature_cutoffs: int, theoretical_cutoffs: int) -> float | None:
    """Return the target maturity share while rejecting inconsistent counts."""
    if mature_cutoffs < 0 or theoretical_cutoffs < 0 or mature_cutoffs > theoretical_cutoffs:
        raise ValueError("mature cutoffs must be between zero and theoretical cutoffs")
    if theoretical_cutoffs == 0:
        return None
    return mature_cutoffs / theoretical_cutoffs


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)


def _read_period_config(path: Path, repo_root: Path) -> dict[str, Any]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    def resolve_period(period: dict[str, Any]) -> dict[str, Any]:
        result = dict(period)
        for key in ("analysis_database", "feature_cube", "target_set"):
            if key in result:
                candidate = Path(result[key])
                result[key] = candidate if candidate.is_absolute() else repo_root / candidate
        return result

    raw["discovery_period"] = resolve_period(raw["discovery_period"])
    raw["validation_periods"] = [resolve_period(p) for p in raw["validation_periods"]]
    return raw


def _partition_dates(root: Path, start: date, end: date, filename: str) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for path in sorted(root.glob(f"as_of_date=*/{filename}")):
        date_text = path.parent.name.split("=", maxsplit=1)[1]
        observed_date = date.fromisoformat(date_text)
        if start <= observed_date <= end:
            found.append((date_text, path))
    return found


def _baseline_rows(
    analysis_database: Path, selections: list[dict[str, Any]], scopes: list[str]
) -> dict[tuple[str, str, str], dict[str, Any]]:
    ids = sorted({(row["feature_id"], row["target_id"]) for row in selections})
    if not ids:
        return {}
    features = sorted({pair[0] for pair in ids})
    targets = sorted({pair[1] for pair in ids})
    feature_marks = ",".join("?" for _ in features)
    target_marks = ",".join("?" for _ in targets)
    scope_marks = ",".join("?" for _ in scopes)
    with duckdb.connect(str(analysis_database), read_only=True) as db:
        rows = db.execute(
            f"""SELECT feature_id, target_id, target_family, horizon, scope,
                       spearman_ic_mean, ic_median, hit_rate, n_total, cutoff_count,
                       coverage, fdr_q_value, top_bottom_spread, monotonicity_spearman,
                       ic_t_stat, p_value_descriptive
                FROM signal_summary
                WHERE feature_id IN ({feature_marks}) AND target_id IN ({target_marks})
                  AND scope IN ({scope_marks})""",
            [*features, *targets, *scopes],
        ).fetchdf()
    return {
        (str(row.feature_id), str(row.target_id), str(row.scope)): row._asdict()
        for row in rows.itertuples(index=False)
    }


def _target_maturity(
    targets: pd.DataFrame, scopes: list[str], minimum_n: int
) -> dict[tuple[str, str], int]:
    ready = targets.loc[
        targets["research_ready"].fillna(False)
        & (targets["target_status"] == "available")
        & np.isfinite(pd.to_numeric(targets["target_value"], errors="coerce"))
    ]
    counts: dict[tuple[str, str], int] = {}
    for scope in scopes:
        scoped = ready if scope == "global" else ready.loc[ready["entity_family"] == scope]
        sizes = scoped.groupby("target_id").size()
        for target_id, count in sizes.items():
            if int(count) >= minimum_n:
                counts[(str(target_id), scope)] = 1
    return counts


def _period_metrics(
    history: list[dict[str, Any]],
    decile_history: list[dict[str, Any]],
    *,
    selections: list[dict[str, Any]],
    period: dict[str, Any],
    theoretical_cutoffs: int,
    target_maturity_counts: dict[tuple[str, str], int],
    all_scopes: list[str],
    classification: dict[str, Any],
) -> list[dict[str, Any]]:
    history_frame = pd.DataFrame(history)
    decile_frame = pd.DataFrame(decile_history)
    grouped: dict[tuple[str, str], pd.DataFrame] = {}
    if not history_frame.empty:
        grouped = {
            (str(key[0]), str(key[1])): frame
            for key, frame in history_frame.groupby(["signal_id", "evaluation_scope"])
        }
    decile_groups: dict[tuple[str, str], pd.DataFrame] = {}
    if not decile_frame.empty:
        decile_groups = {
            (str(key[0]), str(key[1])): frame
            for key, frame in decile_frame.groupby(["signal_id", "evaluation_scope"])
        }

    result: list[dict[str, Any]] = []
    eval_scopes = sorted(set(all_scopes) | {row["scope"] for row in selections})
    for signal in selections:
        for evaluation_scope in eval_scopes:
            daily = grouped.get((signal["signal_id"], evaluation_scope), pd.DataFrame())
            baseline = signal.get("_baseline_by_scope", {}).get(evaluation_scope)
            is_discovery = str(period["id"]) == str(signal["discovery_period_id"])
            if is_discovery and baseline is None:
                continue
            if baseline is None:
                baseline = {}
            row_theoretical_cutoffs = (
                int(period.get("cutoffs_by_scope", {}).get(evaluation_scope, 0))
                if is_discovery
                else theoretical_cutoffs
            )
            values = (
                pd.to_numeric(daily["spearman_ic"], errors="coerce").dropna().to_numpy(float)
                if not daily.empty
                else np.array([], dtype=float)
            )
            count = int(values.size)
            ic_mean = float(np.mean(values)) if count else None
            ic_median = float(np.median(values)) if count else None
            ic_std = float(np.std(values, ddof=1)) if count > 1 else None
            standard_error = ic_std / math.sqrt(count) if ic_std is not None else None
            t_stat = ic_mean / standard_error if ic_mean is not None and standard_error else None
            p_value = (
                float(2 * student_t.sf(abs(t_stat), df=count - 1))
                if t_stat is not None and count > 1
                else None
            )
            hit_rate = float(np.mean(values > 0)) if count else None
            aligned_rate = None
            if count and not is_discovery:
                base_ic = _optional_float(baseline.get("spearman_ic_mean"))
                if base_ic is not None:
                    aligned_rate = float(np.mean(np.sign(values) == np.sign(base_ic)))
            deciles = decile_groups.get((signal["signal_id"], evaluation_scope), pd.DataFrame())
            spread_values: list[float] = []
            monotonicity_values: list[float] = []
            if not deciles.empty:
                for _, cutoff in deciles.groupby("as_of_date"):
                    means = cutoff.set_index("decile")["mean_target"].sort_index()
                    if 1 in means.index and 10 in means.index:
                        spread_values.append(float(means.loc[10] - means.loc[1]))
                    if len(means) >= 3 and means.nunique() > 1:
                        rho = spearmanr(
                            means.index.to_numpy(float), means.to_numpy(float)
                        ).statistic
                        if np.isfinite(rho):
                            monotonicity_values.append(float(rho))
            top_bottom = float(np.mean(spread_values)) if spread_values else None
            monotonicity = float(np.mean(monotonicity_values)) if monotonicity_values else None
            sign_retained: bool | None = None
            signed_retention: float | None = None
            impact_retention: float | None = None
            if is_discovery:
                mature_cutoffs = int(baseline.get("cutoff_count") or 0)
                target_maturity = calculate_maturity_ratio(mature_cutoffs, row_theoretical_cutoffs)
                row_ic_mean = _optional_float(baseline.get("spearman_ic_mean"))
                row_ic_median = _optional_float(baseline.get("ic_median"))
                row_hit_rate = _optional_float(baseline.get("hit_rate"))
                row_n = _optional_int(baseline.get("n_total")) or 0
                row_count = int(baseline.get("cutoff_count") or 0)
                row_top_bottom = _optional_float(baseline.get("top_bottom_spread"))
                row_monotonicity = _optional_float(baseline.get("monotonicity_spearman"))
                row_t_stat = _optional_float(baseline.get("ic_t_stat"))
                row_p_value = _optional_float(baseline.get("p_value_descriptive"))
                row_fdr = _optional_float(baseline.get("fdr_q_value"))
                sign_retained = True
                signed_retention = 1.0
                impact_retention = 1.0
                aligned_rate = 1.0
                stability_class = "discovery"
                evidence_level = _evidence_level(row_count, classification)
            else:
                mature_cutoffs = target_maturity_counts.get(
                    (signal["target_id"], evaluation_scope), 0
                )
                target_maturity = calculate_maturity_ratio(mature_cutoffs, row_theoretical_cutoffs)
                row_ic_mean, row_ic_median, row_hit_rate, row_n = (
                    ic_mean,
                    ic_median,
                    hit_rate,
                    int(pd.to_numeric(daily["n"], errors="coerce").sum()) if not daily.empty else 0,
                )
                row_count = count
                row_top_bottom, row_monotonicity = top_bottom, monotonicity
                row_t_stat, row_p_value = t_stat, p_value
                base_ic = _optional_float(baseline.get("spearman_ic_mean"))
                sign_retained, signed_retention, impact_retention = calculate_retention(
                    base_ic, ic_mean
                )
                stability_class = classify_stability(
                    evaluated_cutoffs=count,
                    mature_cutoffs=mature_cutoffs,
                    sign_retained=sign_retained,
                    aligned_sign_rate=aligned_rate,
                    impact_retention=impact_retention,
                    maturity_ratio=target_maturity,
                    minimum_cutoffs=int(classification["minimum_cutoffs"]),
                    stable_impact_retention=float(classification["stable_impact_retention"]),
                    minimum_period_sign_consistency=float(
                        classification["minimum_period_sign_consistency"]
                    ),
                )
                evidence_level = _evidence_level(mature_cutoffs, classification)
                row_fdr = None
            result.append(
                {
                    **{k: v for k, v in signal.items() if not k.startswith("_")},
                    "period_id": str(period["id"]),
                    "period_start_date": str(period["start_date"]),
                    "period_end_date": str(period["end_date"]),
                    "evaluation_scope": evaluation_scope,
                    "is_discovery_period": is_discovery,
                    "theoretical_cutoffs": row_theoretical_cutoffs,
                    "target_mature_cutoffs": mature_cutoffs,
                    "maturity_ratio": target_maturity,
                    "evaluated_cutoffs": row_count,
                    "observations": row_n,
                    "ic_mean": row_ic_mean,
                    "ic_median": row_ic_median,
                    "ic_std": ic_std if not is_discovery else baseline.get("ic_std"),
                    "ic_spearman_mean": row_ic_mean,
                    "t_stat": row_t_stat,
                    "hit_rate": row_hit_rate,
                    "top_bottom_decile_spread": row_top_bottom,
                    "monotonicity": row_monotonicity,
                    "p_value_descriptive": row_p_value,
                    "fdr_q_descriptive": row_fdr,
                    "discovery_ic_mean_for_scope": _optional_float(
                        baseline.get("spearman_ic_mean")
                    ),
                    "discovery_rank_for_scope": _optional_int(
                        signal.get("_discovery_rank_by_scope", {}).get(evaluation_scope)
                    ),
                    "validation_rank_within_frozen_group": None,
                    "rank_retention": None,
                    "sign_retained": sign_retained,
                    "aligned_sign_rate": aligned_rate,
                    "impact_retention": impact_retention,
                    "signed_retention": signed_retention,
                    "period_sign_consistent": sign_retained,
                    "stability_class": stability_class,
                    "evidence_level": evidence_level,
                    "first_cutoff": str(daily["as_of_date"].min()) if not daily.empty else None,
                    "last_cutoff": str(daily["as_of_date"].max()) if not daily.empty else None,
                }
            )
    # FDR is descriptive and corrected within the frozen validation cohort.
    frame = pd.DataFrame(result)
    if not frame.empty:
        valid = frame.loc[
            (~frame["is_discovery_period"])
            & frame["p_value_descriptive"].notna()
            & frame["evaluation_scope"].notna()
        ]
        for _, indices in valid.groupby(
            ["period_id", "evaluation_scope", "target_family", "horizon"]
        ).groups.items():
            pvalues = frame.loc[indices, "p_value_descriptive"].to_numpy(float)
            qvalues = multipletests(pvalues, method="fdr_bh")[1]
            frame.loc[indices, "fdr_q_descriptive"] = qvalues
        result = frame.to_dict(orient="records")
    return result


def _evidence_level(cutoffs: int, classification: dict[str, Any]) -> str:
    if cutoffs < int(classification["minimum_cutoffs"]):
        return "thin"
    if cutoffs < int(classification["adequate_cutoffs"]):
        return "partial"
    return "adequate"


def build_stability_atlas(
    *,
    config_path: Path,
    repo_root: Path,
    output_dir: Path,
    top_n: int | None = None,
    return_top_n: int | None = None,
) -> dict[str, Any]:
    """Freeze discovery selections and write period/family stability datasets."""
    config = _read_period_config(config_path, repo_root)
    discovery = config["discovery_period"]
    discovery_start = date.fromisoformat(discovery["start_date"])
    discovery_end = date.fromisoformat(discovery["end_date"])
    for validation in config["validation_periods"]:
        validation_start = date.fromisoformat(validation["start_date"])
        validation_end = date.fromisoformat(validation["end_date"])
        if validation["id"] == discovery["id"] or (
            validation_start <= discovery_end and validation_end >= discovery_start
        ):
            raise ValueError(
                "discovery and validation periods must have distinct IDs and non-overlapping dates"
            )
    general_selection_n = int(config["top_n"] if top_n is None else top_n)
    return_selection_n = int(
        config.get("return_top_n", config["top_n"]) if return_top_n is None else return_top_n
    )
    if general_selection_n < 1 or return_selection_n < 1:
        raise ValueError("top-N counts must be positive")
    config["top_n"] = general_selection_n
    config["return_top_n"] = return_selection_n
    target_horizons = (
        {int(value) for value in config["target_horizons"]} if "target_horizons" in config else None
    )
    scope_candidates: dict[str, list[dict[str, Any]]] = {}
    skipped_scopes: dict[str, dict[str, int]] = {}
    for scope in config["target_scopes"]:
        general = freeze_top_signals(
            discovery,
            scope,
            general_selection_n,
            analysis_database=discovery["analysis_database"],
            selection_rule_version=config["selection_rule_version"],
            minimum_n=int(config["minimum_discovery_n"]),
            minimum_cutoffs=int(config["minimum_discovery_cutoffs"]),
            minimum_coverage=float(config["minimum_discovery_coverage"]),
            target_horizons=target_horizons,
        )
        performance = freeze_top_signals(
            discovery,
            scope,
            return_selection_n,
            analysis_database=discovery["analysis_database"],
            selection_rule_version=config["selection_rule_version"],
            minimum_n=int(config["minimum_discovery_n"]),
            minimum_cutoffs=int(config["minimum_discovery_cutoffs"]),
            minimum_coverage=float(config["minimum_discovery_coverage"]),
            return_target_families=set(config["return_target_families"]),
            target_horizons=target_horizons,
        )
        scope_candidates[scope] = general + performance
        skipped_scopes[scope] = {
            _GENERAL: len(general),
            _RETURN: len(performance),
        }
    primary_scope = str(config.get("primary_scope", "equity"))
    for bucket, requested_n in (
        (_GENERAL, general_selection_n),
        (_RETURN, return_selection_n),
    ):
        count = sum(row["selection_bucket"] == bucket for row in scope_candidates[primary_scope])
        if count < requested_n:
            raise ValueError(
                f"primary scope {primary_scope!r} has {count} {bucket} candidates; "
                f"expected {requested_n}"
            )
    selections = [row for rows in scope_candidates.values() for row in rows]
    if not selections:
        raise ValueError("no discovery signals were eligible for freezing")

    theoretical_by_period: dict[str, int] = {}
    validation_partitions: dict[str, list[tuple[str, Path]]] = {}
    for period in config["validation_periods"]:
        features = _partition_dates(
            period["feature_cube"],
            date.fromisoformat(period["start_date"]),
            date.fromisoformat(period["end_date"]),
            "features.parquet",
        )
        if not features:
            raise FileNotFoundError(f"no feature partitions in validation period {period['id']}")
        target_dates = {
            p.parent.name
            for p in period["target_set"].glob("as_of_date=*/targets_research_ready.parquet")
        }
        missing = [d for d, _ in features if f"as_of_date={d}" not in target_dates]
        if missing:
            raise FileNotFoundError(
                f"missing research-ready target partitions in {period['id']}: {missing}"
            )
        theoretical_by_period[period["id"]] = len(features)
        validation_partitions[period["id"]] = features

    # Freeze only once, before any validation cube is read.
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = output_dir / "frozen_top_signals.parquet"
    frozen_frame = pd.DataFrame(selections).drop_duplicates(
        ["signal_id", "selection_bucket", "scope"]
    )
    pq.write_table(pa.Table.from_pandas(frozen_frame, preserve_index=False), frozen_path)
    all_scopes = sorted(set(config["target_scopes"]) | {"global"})
    baselines = _baseline_rows(discovery["analysis_database"], selections, all_scopes)
    for signal in selections:
        signal["_baseline_by_scope"] = {
            scope: baselines[(signal["feature_id"], signal["target_id"], scope)]
            for scope in all_scopes
            if (signal["feature_id"], signal["target_id"], scope) in baselines
        }
        signal["_discovery_rank_by_scope"] = {
            scope: rank
            for scope, rank in _discovery_scope_ranks(selections, baselines)
            .get(signal["signal_id"], {})
            .items()
        }

    discovery_pairs: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for signal in selections:
        discovery_pairs[(signal["feature_id"], signal["target_id"], signal["scope"])].append(signal)
    discovery_features = sorted({key[0] for key in discovery_pairs})
    discovery_targets = sorted({key[1] for key in discovery_pairs})
    selected_scopes = sorted({key[2] for key in discovery_pairs})
    feature_marks = ",".join("?" for _ in discovery_features)
    target_marks = ",".join("?" for _ in discovery_targets)
    scope_marks = ",".join("?" for _ in selected_scopes)
    with duckdb.connect(str(discovery["analysis_database"]), read_only=True) as db:
        discovery_history = db.execute(
            f"""SELECT feature_id, target_id, target_family, horizon, scope, as_of_date,
                       n, pearson_ic, spearman_ic, coverage
                FROM signal_ic_history
                WHERE feature_id IN ({feature_marks}) AND target_id IN ({target_marks})
                  AND scope IN ({scope_marks}) AND as_of_date>=? AND as_of_date<=?""",
            [
                *discovery_features,
                *discovery_targets,
                *selected_scopes,
                discovery["start_date"],
                discovery["end_date"],
            ],
        ).fetchdf()
        discovery_deciles = db.execute(
            f"""SELECT feature_id, target_id, scope, decile, mean_target,
                       median_target, count
                FROM signal_deciles
                WHERE feature_id IN ({feature_marks}) AND target_id IN ({target_marks})
                  AND scope IN ({scope_marks})""",
            [*discovery_features, *discovery_targets, *selected_scopes],
        ).fetchdf()
    discovery_history_rows: list[dict[str, Any]] = []
    for row in discovery_history.to_dict(orient="records"):
        for signal in discovery_pairs.get((row["feature_id"], row["target_id"], row["scope"]), []):
            discovery_history_rows.append(
                {
                    "period_id": discovery["id"],
                    "signal_id": signal["signal_id"],
                    "selection_bucket": signal["selection_bucket"],
                    "selection_scope": signal["scope"],
                    "evaluation_scope": row["scope"],
                    **row,
                }
            )
    discovery_decile_rows: list[dict[str, Any]] = []
    for row in discovery_deciles.to_dict(orient="records"):
        for signal in discovery_pairs.get((row["feature_id"], row["target_id"], row["scope"]), []):
            discovery_decile_rows.append(
                {
                    "period_id": discovery["id"],
                    "signal_id": signal["signal_id"],
                    "selection_bucket": signal["selection_bucket"],
                    "selection_scope": signal["scope"],
                    "evaluation_scope": row["scope"],
                    "as_of_date": "discovery_aggregate",
                    **row,
                }
            )

    analysis_history: list[dict[str, Any]] = []
    decile_history: list[dict[str, Any]] = discovery_decile_rows.copy()
    analysis_history.extend(discovery_history_rows)
    period_metric_rows: list[dict[str, Any]] = []
    target_maturity_by_period: dict[str, dict[tuple[str, str], int]] = {}
    for period in config["validation_periods"]:
        history_rows: list[dict[str, Any]] = []
        decile_rows: list[dict[str, Any]] = []
        maturity: dict[tuple[str, str], int] = defaultdict(int)
        target_ids = sorted({row["target_id"] for row in selections})
        feature_ids = sorted({row["feature_id"] for row in selections})
        relation_map: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for signal in selections:
            for eval_scope in all_scopes:
                relation_map[(signal["feature_id"], signal["target_id"], eval_scope)].append(signal)
        for date_text, feature_path in validation_partitions[period["id"]]:
            target_path = (
                period["target_set"] / f"as_of_date={date_text}" / "targets_research_ready.parquet"
            )
            feature_marks = ",".join("?" for _ in feature_ids)
            target_marks = ",".join("?" for _ in target_ids)
            with duckdb.connect() as db:
                features = db.execute(
                    f"""SELECT entity_id, entity_family, as_of_date, feature_id,
                               feature_value, feature_status
                        FROM read_parquet(?) WHERE feature_id IN ({feature_marks})""",
                    [str(feature_path), *feature_ids],
                ).fetchdf()
                targets = db.execute(
                    f"""SELECT entity_id, entity_family, as_of_date, target_id,
                               target_family, horizon, target_value, target_status, research_ready
                        FROM read_parquet(?) WHERE target_id IN ({target_marks})""",
                    [str(target_path), *target_ids],
                ).fetchdf()
            for target_id, scope in _target_maturity(
                targets, all_scopes, int(config["minimum_validation_n"])
            ).keys():
                maturity[(target_id, scope)] += 1
            pairs, deciles = analyze_cutoff(
                features, targets, minimum_n=int(config["minimum_validation_n"])
            )
            for row in pairs:
                matches = relation_map.get((row["feature_id"], row["target_id"], row["scope"]), [])
                for signal in matches:
                    identity_row = {
                        "signal_id": signal["signal_id"],
                        "selection_bucket": signal["selection_bucket"],
                        "selection_scope": signal["scope"],
                        "evaluation_scope": row["scope"],
                        "as_of_date": date_text,
                        "feature_id": row["feature_id"],
                        "target_id": row["target_id"],
                        "target_family": row["target_family"],
                        "horizon": row["horizon"],
                        "n": row["n"],
                        "coverage": row["coverage"],
                        "pearson_ic": row["pearson_ic"],
                        "spearman_ic": row["spearman_ic"],
                    }
                    history_rows.append(identity_row)
                    analysis_history.append({"period_id": period["id"], **identity_row})
            for row in deciles:
                matches = relation_map.get((row["feature_id"], row["target_id"], row["scope"]), [])
                for signal in matches:
                    decile_row = {
                        "signal_id": signal["signal_id"],
                        "selection_bucket": signal["selection_bucket"],
                        "selection_scope": signal["scope"],
                        "evaluation_scope": row["scope"],
                        "as_of_date": date_text,
                        "feature_id": row["feature_id"],
                        "target_id": row["target_id"],
                        "target_family": signal["target_family"],
                        "horizon": signal["horizon"],
                        "decile": row["decile"],
                        "mean_target": row["mean_target"],
                        "median_target": row["median_target"],
                        "count": row["count"],
                    }
                    decile_rows.append(decile_row)
                    decile_history.append({"period_id": period["id"], **decile_row})
        target_maturity_by_period[period["id"]] = dict(maturity)
        period_metric_rows.extend(
            _period_metrics(
                history_rows,
                decile_rows,
                selections=selections,
                period=period,
                theoretical_cutoffs=theoretical_by_period[period["id"]],
                target_maturity_counts=dict(maturity),
                all_scopes=all_scopes,
                classification=config["classification"],
            )
        )

    # Add the discovery measurements to the same long period × signal × family panel.
    discovery_period_rows: list[dict[str, Any]] = []
    discovery_cutoffs: dict[str, int] = {}
    discovery_dates: dict[str, dict[str, Any]] = {}
    for scope in all_scopes:
        with duckdb.connect(str(discovery["analysis_database"]), read_only=True) as db:
            cutoffs = db.execute(
                "SELECT count(DISTINCT as_of_date), min(as_of_date), max(as_of_date) "
                "FROM signal_ic_history WHERE scope=? "
                "AND as_of_date>=? AND as_of_date<=?",
                [scope, discovery["start_date"], discovery["end_date"]],
            ).fetchone()
        discovery_cutoffs[scope] = int(cutoffs[0] or 0) if cutoffs else 0
        discovery_dates[scope] = {
            "cutoff_count": discovery_cutoffs[scope],
            "start_date": str(cutoffs[1]) if cutoffs and cutoffs[1] else None,
            "end_date": str(cutoffs[2]) if cutoffs and cutoffs[2] else None,
        }
    discovery_for_metrics = {**discovery, "cutoffs_by_scope": discovery_cutoffs}
    discovery_period_rows.extend(
        _period_metrics(
            [],
            [],
            selections=selections,
            period=discovery_for_metrics,
            theoretical_cutoffs=discovery_cutoffs.get("equity", 0),
            target_maturity_counts={},
            all_scopes=all_scopes,
            classification=config["classification"],
        )
    )
    all_period_rows = discovery_period_rows + period_metric_rows
    # In the discovery period the helper already reads all scopes from the DB.
    period_frame = pd.DataFrame(all_period_rows)
    if not period_frame.empty:
        period_frame = _attach_validation_ranks(period_frame)
    summary_frame = period_frame.loc[
        period_frame["evaluation_scope"] == period_frame["scope"]
    ].copy()
    family_frame = period_frame.copy()
    _write_frame(output_dir / "signal_stability_summary.parquet", summary_frame)
    _write_frame(output_dir / "signal_stability_by_family.parquet", family_frame)
    _write_frame(output_dir / "signal_period_metrics.parquet", period_frame)
    _write_frame(output_dir / "signal_period_ic_history.parquet", pd.DataFrame(analysis_history))
    _write_frame(output_dir / "signal_period_deciles.parquet", pd.DataFrame(decile_history))

    audit = _make_audit(
        config=config,
        selections=selections,
        summary=summary_frame,
        family=family_frame,
        skipped_scopes=skipped_scopes,
        theoretical_by_period=theoretical_by_period,
        discovery_cutoffs=discovery_cutoffs,
        discovery_dates=discovery_dates,
        validation_partitions=validation_partitions,
        target_maturity_by_period=target_maturity_by_period,
        regression=_regression_results(summary_frame, primary_scope),
    )
    (output_dir / "stability_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "stability_audit.md").write_text(_audit_markdown(audit), encoding="utf-8")
    return audit


def _discovery_scope_ranks(
    selections: list[dict[str, Any]], baselines: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for scope in sorted({str(row["scope"]) for row in selections} | {"global"}):
        eligible = [
            row for row in selections if (row["feature_id"], row["target_id"], scope) in baselines
        ]
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in eligible:
            groups[
                (
                    row["selection_bucket"],
                    row["scope"],
                    row["target_family"],
                    str(row["horizon"]),
                )
            ].append(row)
        for rows in groups.values():
            ordered = sorted(
                rows,
                key=lambda row: (
                    -abs(
                        float(
                            baselines[(row["feature_id"], row["target_id"], scope)][
                                "spearman_ic_mean"
                            ]
                        )
                    )
                ),
            )
            for rank, row in enumerate(ordered, start=1):
                result[row["signal_id"]][scope] = rank
    return result


def _attach_validation_ranks(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["validation_rank_within_frozen_group"] = np.nan
    validation = result.loc[(~result["is_discovery_period"]) & result["ic_mean"].notna()]
    consistency: dict[tuple[str, str, str, str], tuple[int, int]] = {}
    if not validation.empty:
        for key, group in validation.groupby(
            ["signal_id", "selection_bucket", "scope", "evaluation_scope"]
        ):
            key_tuple = (str(key[0]), str(key[1]), str(key[2]), str(key[3]))
            consistency[key_tuple] = (
                int(len(group)),
                int(group["sign_retained"].fillna(False).sum()),
            )
        for index, row in result.iterrows():
            key = (
                str(row["signal_id"]),
                str(row["selection_bucket"]),
                str(row["scope"]),
                str(row["evaluation_scope"]),
            )
            observed, retained = consistency.get(key, (0, 0))
            result.at[index, "periods_evaluated"] = observed
            result.at[index, "periods_sign_retained"] = retained
    if not validation.empty:
        ranks = validation.groupby(
            [
                "period_id",
                "selection_bucket",
                "scope",
                "target_family",
                "horizon",
                "evaluation_scope",
            ]
        )["ic_mean"].transform(lambda values: values.abs().rank(method="min", ascending=False))
        result.loc[validation.index, "validation_rank_within_frozen_group"] = ranks
        result["rank_retention"] = (
            pd.to_numeric(result["discovery_rank_for_scope"], errors="coerce")
            / result["validation_rank_within_frozen_group"]
        )
    return result


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    if frame.empty:
        pq.write_table(pa.table({"empty": pa.array([], type=pa.string())}), path)
        return
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path, compression="zstd")


def _regression_results(summary: pd.DataFrame, primary_scope: str) -> dict[str, Any]:
    if summary.empty:
        return {}
    main = summary.loc[
        (summary["scope"] == primary_scope)
        & (summary["evaluation_scope"] == primary_scope)
        & (~summary["is_discovery_period"])
    ]
    result: dict[str, Any] = {}
    for bucket, group in main.groupby("selection_bucket"):
        result[str(bucket)] = {
            str(period): {
                "signals_discovered": int(len(rows)),
                "signals_evaluable": int(rows["ic_mean"].notna().sum()),
                "signals_missing_ic": int(rows["ic_mean"].isna().sum()),
                "sign_retained": int(rows["sign_retained"].fillna(False).sum()),
                "median_impact_retention": _optional_float(rows["impact_retention"].median()),
                "mean_discovery_ic": _optional_float(rows["discovery_ic_mean_for_scope"].mean()),
                "mean_validation_ic": _optional_float(rows["ic_mean"].mean()),
                "sign_reversed": int(
                    (
                        (~rows["sign_retained"].fillna(True).astype(bool)) & rows["ic_mean"].notna()
                    ).sum()
                ),
                "insufficient_validation": int(
                    (rows["stability_class"] == "insufficient_validation").sum()
                ),
            }
            for period, rows in group.groupby("period_id")
        }
    return result


def _make_audit(
    *,
    config: dict[str, Any],
    selections: list[dict[str, Any]],
    summary: pd.DataFrame,
    family: pd.DataFrame,
    skipped_scopes: dict[str, dict[str, int]],
    theoretical_by_period: dict[str, int],
    discovery_cutoffs: dict[str, int],
    discovery_dates: dict[str, dict[str, Any]],
    validation_partitions: dict[str, list[tuple[str, Path]]],
    target_maturity_by_period: dict[str, dict[tuple[str, str], int]],
    regression: dict[str, Any],
) -> dict[str, Any]:
    periods: list[dict[str, Any]] = []
    discovery = config["discovery_period"]
    periods.append(
        {
            "period_id": discovery["id"],
            "role": "discovery",
            "start_date": discovery["start_date"],
            "end_date": discovery["end_date"],
            "cutoff_count_by_scope": discovery_cutoffs,
            "observed_dates_by_scope": discovery_dates,
        }
    )
    for period in config["validation_periods"]:
        dates = [date_text for date_text, _ in validation_partitions[period["id"]]]
        maturity_rows = summary.loc[summary["period_id"] == period["id"]]
        periods.append(
            {
                "period_id": period["id"],
                "role": "validation",
                "configured_start_date": period["start_date"],
                "configured_end_date": period["end_date"],
                "observed_start_date": min(dates) if dates else None,
                "observed_end_date": max(dates) if dates else None,
                "theoretical_cutoffs": theoretical_by_period[period["id"]],
                "target_maturity_by_horizon": _maturity_by_horizon(maturity_rows),
            }
        )
    return {
        "schema_version": "spec006r-stability-atlas/1.0",
        "selection_rule_version": config["selection_rule_version"],
        "target_horizons": config.get("target_horizons"),
        "selection_period_ids": sorted({row["discovery_period_id"] for row in selections}),
        "invariant_selection_period_differs_from_validation_period": True,
        "top_n_per_bucket_and_scope": {
            _GENERAL: int(config["top_n"]),
            _RETURN: int(config.get("return_top_n", config["top_n"])),
        },
        "minimum_discovery_n": int(config["minimum_discovery_n"]),
        "minimum_discovery_cutoffs": int(config["minimum_discovery_cutoffs"]),
        "minimum_discovery_coverage": float(config["minimum_discovery_coverage"]),
        "minimum_validation_n": int(config["minimum_validation_n"]),
        "selection_counts_by_scope_and_bucket": skipped_scopes,
        "periods": periods,
        "period_metrics_rows": int(len(summary)),
        "family_metrics_rows": int(len(family)),
        "unique_signal_ids": int(len({row["signal_id"] for row in selections})),
        "classification_thresholds": config["classification"],
        "regression_results_primary_scope_equity": regression,
        "notes": [
            "Selection uses discovery rows only; validation partitions are opened "
            "only after all tops are frozen.",
            "FDR q-values are descriptive and corrected within the frozen validation cohort.",
            "Evidence level describes the number of available cutoffs; it is not "
            "a probability or a confidence score.",
            "Ranks in validation are computed within the frozen cohort and "
            "family/horizon; the candidate universe is not reselected.",
        ],
    }


def _maturity_by_horizon(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    result: list[dict[str, Any]] = []
    for horizon, group in frame.groupby("horizon"):
        if group.empty:
            continue
        result.append(
            {
                "horizon": int(horizon),
                "theoretical_cutoffs": int(group["theoretical_cutoffs"].max()),
                "median_mature_cutoffs": float(group["target_mature_cutoffs"].median()),
                "median_maturity_ratio": _optional_float(group["maturity_ratio"].median()),
                "signals": int(group["signal_id"].nunique()),
                "signals_evaluable": int(group["ic_mean"].notna().sum()),
            }
        )
    return result


def _audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# SPEC-006R — Stability Atlas audit",
        "",
        f"- Rule: `{audit['selection_rule_version']}`",
        f"- Target horizons: {audit['target_horizons'] or 'all'}",
        f"- Unique frozen signals: {audit['unique_signal_ids']}",
        "- Selection/validation leakage invariant: "
        f"`{audit['invariant_selection_period_differs_from_validation_period']}`",
        "",
        "## Periods and target maturity",
        "",
    ]
    for period in audit["periods"]:
        start = period.get(
            "observed_start_date", period.get("start_date", period.get("configured_start_date"))
        )
        end = period.get(
            "observed_end_date", period.get("end_date", period.get("configured_end_date"))
        )
        lines.append(
            f"- **{period['period_id']}** ({period['role']}): "
            f"{start} → {end}; "
            f"cutoffs={period.get('theoretical_cutoffs', period.get('cutoff_count_by_scope', {}))}"
        )
        if period.get("target_maturity_by_horizon"):
            for row in period["target_maturity_by_horizon"]:
                lines.append(
                    f"  - H{row['horizon']}: median {row['median_mature_cutoffs']:.1f}/"
                    f"{row['theoretical_cutoffs']} cutoffs mûrs "
                    f"({(row['median_maturity_ratio'] or 0) * 100:.1f} %); "
                    f"signaux évaluables={row['signals_evaluable']}/{row['signals']}"
                )
    lines.extend(["", "## Résultats principaux · scope equity", ""])
    for bucket, periods in audit["regression_results_primary_scope_equity"].items():
        lines.append(f"### {bucket}")
        for period_id, row in sorted(periods.items()):
            median_retention = row["median_impact_retention"]
            lines.append(
                f"- {period_id}: {row['sign_retained']}/{row['signals_evaluable']} "
                "signes conservés; "
                f"rétention médiane="
                f"{median_retention if median_retention is not None else 'n.c.'}; "
                f"IC discovery={row['mean_discovery_ic']}; IC période={row['mean_validation_ic']}; "
                f"inversions={row['sign_reversed']}; "
                f"sans IC={row['signals_missing_ic']}; "
                f"sous seuil d’évidence={row['insufficient_validation']}"
            )
    lines.extend(["", "## Classification descriptive", ""])
    lines.append(json.dumps(audit["classification_thresholds"], ensure_ascii=False, sort_keys=True))
    lines.append("")
    lines.append(
        "Les classes décrivent les observations disponibles ; elles ne constituent pas "
        "un verdict statistique ou financier."
    )
    lines.append("")
    return "\n".join(lines)
