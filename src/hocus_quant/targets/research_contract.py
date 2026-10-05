"""SPEC-006T: frozen past eligibility and separately annotated future outcomes.

The full ledger never loses entities because of an outcome. Observable and
interpretable samples are explicit projections of that ledger, not universes at T.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl

TargetPolicy = Literal["legacy_research_ready", "ex_ante", "clean_future"]
CONTRACT_VERSION = "SPEC-006T/1.0.0"
PRIMARY_TARGET = "future.direction_abs.h5.v1"


@dataclass(frozen=True)
class EligibilityAtCutoff:
    entity_id: str
    entity_family: str
    as_of_date: date
    quality_status_at_cutoff: str
    past_observation_count: int
    minimum_history: int
    universe_admissible: bool
    series_present: bool
    eligible_at_cutoff: bool
    eligibility_reason: str


def freeze_eligibility(
    *,
    entity_id: str,
    entity_family: str,
    as_of_date: date,
    quality_status: str,
    past_dates: list[date],
    minimum_history: int = 1,
    universe_admissible: bool = True,
) -> EligibilityAtCutoff:
    """This API deliberately accepts no future rows, outcomes or quality flags."""
    if minimum_history < 1 or any(day > as_of_date for day in past_dates):
        raise ValueError("eligibility requires positive minimum history and dates <= T")
    reasons = []
    if not past_dates:
        reasons.append("series_absent")
    if quality_status != "approved":
        reasons.append("quality_not_approved_at_T")
    if len(past_dates) < minimum_history:
        reasons.append("insufficient_past_history")
    if not universe_admissible:
        reasons.append("outside_frozen_universe")
    return EligibilityAtCutoff(
        entity_id,
        entity_family,
        as_of_date,
        quality_status,
        len(past_dates),
        minimum_history,
        universe_admissible,
        bool(past_dates),
        not reasons,
        ";".join(reasons) if reasons else "approved_at_T",
    )


def annotate_outcomes(targets: pl.DataFrame, eligibility: pl.DataFrame) -> pl.DataFrame:
    """Annotate legacy or freshly calculated candidates without redefining eligibility.

    Hard source-rule violations are uninterpretable in V1. Suspected corporate
    actions and large moves remain observable and interpretable, with flags.
    Neither rule changes the frozen eligibility decision.
    """
    keys = ["entity_id", "entity_family", "as_of_date"]
    if eligibility.select(keys).is_duplicated().any():
        raise ValueError("duplicate frozen eligibility decisions")
    if targets.select([*keys, "target_id"]).is_duplicated().any():
        raise ValueError("duplicate outcomes")
    fields = ["eligible_at_cutoff", "eligibility_reason", "past_observation_count"]
    frame = targets.drop([c for c in fields if c in targets.columns]).join(
        eligibility.select([*keys, *fields]), on=keys, how="left", validate="m:1"
    )
    if frame["eligible_at_cutoff"].null_count():
        raise ValueError("outcome has no past-only eligibility decision")
    if "legacy_target_value" not in frame.columns:
        frame = frame.with_columns(pl.col("target_value").alias("legacy_target_value"))
    reason = pl.col("future_quality_reason").fill_null("")
    flags = pl.col("extreme_flags").list.join(";").fill_null("")
    strong = (pl.col("target_status") == "future_quality_quarantined") | flags.str.contains(
        "confirmed_source_error"
    )
    corporate = reason.str.contains("split|corporate_action") | flags.str.contains("split")
    scale = reason.str.contains("scale") | flags.str.contains("scale")
    source_issue = flags.str.contains("source_quality_issue|benchmark_issue")
    observable = pl.col("candidate_value").is_not_null() & pl.col("candidate_value").is_finite()
    frame = frame.with_columns(
        observable.alias("target_observable"),
        (observable & ~strong).alias("target_interpretable"),
        pl.when(~observable)
        .then(pl.col("target_status"))
        .when(strong)
        .then(pl.lit("quarantined"))
        .when(scale)
        .then(pl.lit("scale_change"))
        .when(corporate)
        .then(pl.lit("suspected_corporate_action"))
        .when(source_issue)
        .then(pl.lit("source_issue"))
        .when((pl.col("target_status") == "future_quality_review") | (flags != ""))
        .then(pl.lit("review"))
        .otherwise(pl.lit("clean"))
        .alias("future_quality_status"),
        pl.when(strong)
        .then(pl.lit("hard_source_rule_or_confirmed_error"))
        .when(~observable)
        .then(pl.col("unavailable_reason"))
        .otherwise(pl.lit(None, dtype=pl.String))
        .alias("interpretability_reason"),
        pl.when(observable & ~strong)
        .then(pl.col("candidate_value"))
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("target_value"),
        pl.lit(CONTRACT_VERSION).alias("research_contract_version"),
    )
    return frame


def select_targets(targets: pl.DataFrame, policy: TargetPolicy) -> pl.DataFrame:
    """Return analysable outcomes; the full cohort ledger is always retained."""
    if policy == "legacy_research_ready":
        value = (
            "legacy_target_value" if "legacy_target_value" in targets.columns else "target_value"
        )
        return targets.filter(
            pl.col("research_ready")
            & (pl.col("target_status") == "available")
            & pl.col(value).is_not_null()
            & pl.col(value).is_finite()
        ).with_columns(pl.col(value).alias("target_value"))
    if policy not in {"ex_ante", "clean_future"}:
        raise ValueError(f"unknown target policy: {policy}")
    required = {
        "eligible_at_cutoff",
        "target_observable",
        "target_interpretable",
        "future_quality_status",
        "candidate_value",
    }
    if not required.issubset(targets.columns):
        raise ValueError("explicit research policy requires SPEC-006T annotated outcomes")
    predicate = pl.col("eligible_at_cutoff") & pl.col("target_observable")
    # V1 is deliberately limited to the sole target researched and locked here.
    # Legacy rank_pct cohorts are not advertised as repaired ex-ante rankings.
    predicate &= (pl.col("target_id") == PRIMARY_TARGET) & (pl.col("entity_family") == "equity")
    predicate &= pl.col("target_interpretable")
    if policy == "clean_future":
        predicate &= pl.col("future_quality_status") == "clean"
    return targets.filter(predicate).with_columns(pl.col("candidate_value").alias("target_value"))


def refresh_contract_views(db: duckdb.DuckDBPyConnection) -> None:
    """Both views retain explicit flags; ex ante includes uninterpretable rows.

    Such rows keep candidate_value but have null target_value. Analysis must also
    require target_interpretable, and count them as exclusions, never nonmembers.
    """
    db.execute(f"""CREATE OR REPLACE VIEW targets_ex_ante AS SELECT * FROM targets
        WHERE eligible_at_cutoff AND target_observable
        AND target_id='{PRIMARY_TARGET}' AND entity_family='equity'""")
    db.execute("""CREATE OR REPLACE VIEW targets_clean_future AS SELECT * FROM targets_ex_ante
        WHERE target_interpretable AND future_quality_status='clean'""")


def publish_contract_partition(
    output: Path,
    decisions: list[EligibilityAtCutoff] | None = None,
) -> None:
    """Called after hardening so final future flags enter the additive contract."""
    raw = output / "targets.parquet"
    frame = pl.read_parquet(raw)
    ledger_path = output / "eligibility_at_cutoff.parquet"
    if decisions is not None:
        pl.DataFrame([asdict(item) for item in decisions]).write_parquet(ledger_path)
    ledger = pl.read_parquet(ledger_path)
    annotated = annotate_outcomes(frame, ledger)
    annotated.write_parquet(raw)
    annotated.filter(
        pl.col("eligible_at_cutoff")
        & pl.col("target_observable")
        & (pl.col("target_id") == PRIMARY_TARGET)
        & (pl.col("entity_family") == "equity")
    ).write_parquet(output / "targets_ex_ante.parquet")
    select_targets(annotated, "clean_future").write_parquet(output / "targets_clean_future.parquet")
    path = str(raw.resolve()).replace("'", "''")
    with duckdb.connect(str(output / "target_catalog.duckdb")) as db:
        db.execute(f"CREATE OR REPLACE VIEW targets AS SELECT * FROM read_parquet('{path}')")
        refresh_contract_views(db)


def eligibility_document(decision: EligibilityAtCutoff) -> dict[str, Any]:
    return asdict(decision)
