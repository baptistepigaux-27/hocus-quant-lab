"""Prospective registration and append-only outcome partitions for SPEC-007."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import polars as pl

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_metrics import (
    cumulative_tables,
    cutoff_metrics,
    oriented_scores,
    prediction_metrics,
)
from hocus_quant.analysis.confirmation_protocol import (
    checkpoint_state,
    file_sha,
    initialize_protocol,
    verify_protocol,
)
from hocus_quant.features.factory import compute_entity_features
from hocus_quant.targets.factory import _future_outcomes
from hocus_quant.targets.research_contract import (
    PRIMARY_TARGET,
    annotate_outcomes,
    freeze_eligibility,
)
from hocus_quant.validation.market_quality import assess_series

PARIS = ZoneInfo("Europe/Paris")


def code_sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def code_dirty(root: Path) -> bool:
    return bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
    )


def _json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False) + "\n"
    )


def _seal(directory: Path, metadata: dict[str, Any], name: str) -> None:
    metadata = {
        **metadata,
        "files": {p.name: file_sha(p) for p in sorted(directory.iterdir()) if p.is_file()},
    }
    _json(directory / name, metadata)


def _verify_seal(directory: Path, name: str) -> dict[str, Any]:
    seal: dict[str, Any] = json.loads((directory / name).read_text())
    actual = {p.name for p in directory.iterdir() if p.is_file() and p.name != name}
    if actual != set(seal["files"]):
        raise ValueError("append-only partition files were added or removed")
    if any(file_sha(directory / name) != digest for name, digest in seal["files"].items()):
        raise ValueError("append-only partition was modified")
    return seal


@contextmanager
def _exclusive(output: Path) -> Iterator[None]:
    with (output / ".writer.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def verify_store(output: Path, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    if json.loads((output / "protocol.json").read_text()) != protocol:
        raise ValueError("store protocol differs from the frozen contract")
    records = []
    previous = (
        json.loads((output / "confirmation_manifest.json").read_text())
        if (output / "confirmation_manifest.json").exists()
        else {}
    )
    seals = previous.get("partition_fingerprints", {})
    for partition in sorted((output / "cutoffs").glob("as_of_date=*")):
        record = _verify_seal(partition, "registration.json")
        if record["cutoff"] in seals and (
            file_sha(partition / "registration.json") != seals[record["cutoff"]]["registration"]
        ):
            raise ValueError("append-only registration metadata was modified")
        if record["protocol_sha256"] != protocol["protocol_sha256"]:
            raise ValueError("partition protocol mismatch")
        if partition.name != f"as_of_date={record['cutoff']}":
            raise ValueError("partition cutoff mismatch")
        if record["cutoff"] < protocol["boundary"]["confirmation_start_date"]:
            raise ValueError("development date in confirmation store")
        if (partition / "outcome").exists():
            outcome = _verify_seal(partition / "outcome", "outcome_manifest.json")
            if outcome["registration_sha256"] != file_sha(partition / "registration.json"):
                raise ValueError("outcome is not bound to the frozen registration")
            if outcome["protocol_sha256"] != protocol["protocol_sha256"]:
                raise ValueError("outcome protocol mismatch")
            record["mature"] = True
            old_outcome = seals.get(record["cutoff"], {}).get("outcome")
            if old_outcome and file_sha(partition / "outcome/outcome_manifest.json") != old_outcome:
                raise ValueError("append-only outcome metadata was modified")
        else:
            record["mature"] = False
        records.append(record)
    if set(seals) - {r["cutoff"] for r in records}:
        raise ValueError("append-only cutoff partition was removed")
    if any(seals.get(r["cutoff"], {}).get("outcome") and not r["mature"] for r in records):
        raise ValueError("append-only outcome partition was removed")
    return records


def _equity_rows(
    database: Path, *, day: date, available_by: datetime, future: bool = False
) -> list[dict[str, Any]]:
    """The past query cannot read a row dated after T. Every chosen row is captured."""
    comparator = ">" if future else "<="
    with duckdb.connect(str(database), read_only=True) as db:
        cursor = db.execute(
            f"""
            WITH selected AS (
              SELECT 'abc-bourse-manual:equity:' || COALESCE(isin,instrument_id) AS entity_id,
                     'equity' AS entity_family, 'market_daily' AS source_series,
                     session_date,open,high,low,close,volume,available_at,retrieved_at,snapshot_id,
                     row_number() OVER (PARTITION BY instrument_id,session_date
                       ORDER BY retrieved_at DESC,snapshot_id DESC) AS revision
              FROM market_daily_history
              WHERE session_date {comparator} ? AND available_at <= ?
            ) SELECT * EXCLUDE(revision) FROM selected
              WHERE revision=1 AND close>0 ORDER BY entity_id,session_date
        """,
            [day, available_by],
        )
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def register_cutoff(
    *,
    root: Path,
    config: Path,
    output: Path,
    database: Path,
    cutoff: date,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    protocol = initialize_protocol(root, config, output)
    lock = verify_protocol(root, config, protocol)
    if cutoff.isoformat() < protocol["boundary"]["confirmation_start_date"]:
        raise ValueError("development or pre-freeze cutoff is forbidden")
    if cutoff.weekday() != 4:
        raise ValueError("protocol V1 registers Friday equity cutoffs only")
    available_by = datetime.combine(cutoff + timedelta(days=1), datetime.min.time(), PARIS)
    if available_by > now:
        raise ValueError("cutoff prices are not available yet")
    with _exclusive(output):
        records = verify_store(output, protocol)
        if records and cutoff.isoformat() <= records[-1]["cutoff"]:
            raise ValueError("duplicate or out-of-order cutoff")
        if len(records) >= protocol["settings"]["target_mature_cutoffs"]:
            raise ValueError("predeclared confirmation depth reached; no automatic extension")
        # Prevent an after-the-fact registration once any future equity session is visible.
        future = _equity_rows(database, day=cutoff, available_by=now, future=True)
        if future:
            raise ValueError("prospective registration must precede the first future observation")
        rows = _equity_rows(database, day=cutoff, available_by=available_by)
        if not rows or max(r["session_date"] for r in rows) != cutoff:
            raise ValueError("no new equity session for the requested cutoff")
        by_id: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_id.setdefault(row["entity_id"], []).append(row)
        ledger, features, majority_targets = [], [], []
        for entity_id, observations in by_id.items():
            quality = assess_series(
                {"entity_id": entity_id, "entity_family": "equity", "observations": observations}
            )
            computed = compute_entity_features(observations)
            decision = freeze_eligibility(
                entity_id=entity_id,
                entity_family="equity",
                as_of_date=cutoff,
                quality_status=quality["quality_status"],
                past_dates=[r["session_date"] for r in observations],
                universe_admissible=any(v[1] == "available" for v in computed.values()),
            )
            ledger.append({**asdict(decision), "quality_reason": quality["quality_reason"]})
            if not decision.eligible_at_cutoff:
                continue
            if len(observations) >= 6:
                majority_targets.append(observations[-1]["close"] > observations[-6]["close"])
            for candidate in lock["candidates"]:
                feature_id = candidate["canonical_feature"]
                value, status, count, coverage = computed[feature_id]
                features.append(
                    {
                        "entity_id": entity_id,
                        "feature_id": feature_id,
                        "feature_value": value,
                        "feature_status": status,
                        "coverage_count": count,
                        "coverage_ratio": coverage,
                    }
                )
        if not features:
            raise ValueError(
                "no eligible entities; report/import source issues before registration"
            )
        ledger_frame = pl.DataFrame(ledger)
        feature_frame = pl.DataFrame(features, schema_overrides={"feature_value": pl.Float64})
        eligible = ledger_frame.filter(pl.col("eligible_at_cutoff")).height
        previous = records[-1]["eligible_entities"] if records else None
        coverage = 1 - feature_frame["feature_value"].null_count() / feature_frame.height
        alerts = []
        if eligible < protocol["settings"]["minimum_pairs"]:
            alerts.append("insufficient_eligible_entities")
        if coverage < protocol["settings"]["feature_coverage_warning"]:
            alerts.append("low_feature_coverage")
        if (
            previous
            and abs(eligible / previous - 1) > protocol["settings"]["universe_change_warning"]
        ):
            alerts.append("unusual_universe_change")
        destination = output / "cutoffs" / f"as_of_date={cutoff}"
        destination.parent.mkdir(exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=destination.parent))
        try:
            pl.DataFrame(rows).write_parquet(temporary / "past_observations.parquet")
            ledger_frame.write_parquet(temporary / "eligibility.parquet")
            feature_frame.write_parquet(temporary / "features.parquet")
            oriented_scores(
                feature_frame, lock, protocol["settings"]["aggregate_minimum_feature_fraction"]
            ).write_parquet(temporary / "scores.parquet")
            _seal(
                temporary,
                {
                    "cutoff": str(cutoff),
                    "registered_at": now.isoformat(),
                    "available_by": available_by.isoformat(),
                    "protocol_sha256": protocol["protocol_sha256"],
                    "candidate_lock_sha256": lock["lock_sha256"],
                    "feature_registry_sha256": protocol["runtime_identity"][
                        "feature_registry_sha256"
                    ],
                    "target_registry_sha256": protocol["runtime_identity"][
                        "target_registry_sha256"
                    ],
                    "code_sha": code_sha(root),
                    "working_tree_dirty": code_dirty(root),
                    "pit_grade": "reconstructed",
                    "source_database": str(database),
                    "eligible_entities": eligible,
                    "observed_entities": len(by_id),
                    "feature_coverage": coverage,
                    "past_quality_exclusions": len(by_id) - eligible,
                    "data_quality_alerts": alerts,
                    "past_majority_direction": 1
                    if not majority_targets or np.mean(majority_targets) >= 0.5
                    else -1,
                },
                "registration.json",
            )
            os.rename(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        rebuild_monitor(root=root, config=config, output=output)
        registration: dict[str, Any] = json.loads((destination / "registration.json").read_text())
        return registration


def mature_pending(
    *, root: Path, config: Path, output: Path, database: Path, now: datetime | None = None
) -> list[str]:
    """Close a cutoff once five common equity sessions are observable; never revise it."""
    now = now or datetime.now(UTC)
    protocol = initialize_protocol(root, config, output)
    lock = verify_protocol(root, config, protocol)
    completed = []
    pending_progress = []
    with _exclusive(output):
        for record in verify_store(output, protocol):
            if record["mature"]:
                continue
            cutoff = date.fromisoformat(record["cutoff"])
            future = _equity_rows(database, day=cutoff, available_by=now, future=True)
            sessions = sorted({r["session_date"] for r in future})
            if len(sessions) < 5:
                pending_progress.append(
                    {
                        "cutoff": str(cutoff),
                        "observed_future_sessions": len(sessions),
                        "missing_sessions": 5 - len(sessions),
                        "expected_date": None,
                    }
                )
                break
            # Stop at the first globally mature snapshot. Local missing horizons remain explicit.
            end = sessions[4]
            future = [r for r in future if r["session_date"] <= end]
            partition = output / "cutoffs" / f"as_of_date={cutoff}"
            past = pl.read_parquet(partition / "past_observations.parquet")
            ledger = pl.read_parquet(partition / "eligibility.parquet")
            by_id: dict[str, list[dict[str, Any]]] = {}
            for row in future:
                by_id.setdefault(row["entity_id"], []).append(row)
            outcomes = []
            for entity in ledger.filter(pl.col("eligible_at_cutoff")).to_dicts():
                entity_id = entity["entity_id"]
                observations = past.filter(pl.col("entity_id") == entity_id).to_dicts()
                raw = _future_outcomes(
                    {**entity, "observations": observations}, by_id.get(entity_id, []), cutoff, 5
                )[5]
                candidate = (
                    float(np.sign(raw["return_abs"])) if raw["return_abs"] is not None else None
                )
                outcomes.append(
                    {
                        "entity_id": entity_id,
                        "entity_family": "equity",
                        "as_of_date": cutoff,
                        "target_id": PRIMARY_TARGET,
                        "candidate_value": candidate,
                        "target_value": candidate,
                        "target_status": raw["status"],
                        "research_ready": raw["status"] == "available",
                        "future_quality_reason": raw["future_quality_reason"],
                        "unavailable_reason": raw["reason"],
                        "extreme_flags": [],
                        "future_observation_count": raw["future_observation_count"],
                        "start_price": raw["start_price"],
                        "end_price": raw["end_price"],
                        "target_end_date": raw["target_end_date"],
                        "future_quality_evidence": json.dumps(
                            raw["future_quality_evidence"], default=str
                        ),
                    }
                )
            target = annotate_outcomes(
                pl.DataFrame(
                    outcomes,
                    schema_overrides={
                        "candidate_value": pl.Float64,
                        "target_value": pl.Float64,
                        "future_quality_reason": pl.String,
                        "unavailable_reason": pl.String,
                        "extreme_flags": pl.List(pl.String),
                        "end_price": pl.Float64,
                    },
                ),
                ledger,
            )
            temporary = Path(tempfile.mkdtemp(prefix=".outcome-", dir=partition))
            try:
                pl.DataFrame(future).write_parquet(temporary / "future_observations.parquet")
                target.write_parquet(temporary / "targets.parquet")
                metrics = cutoff_metrics(
                    pl.read_parquet(partition / "features.parquet"),
                    target,
                    lock,
                    protocol,
                    str(cutoff),
                )
                metrics.write_parquet(temporary / "cutoff_metrics.parquet")
                prediction_metrics(
                    pl.read_parquet(partition / "scores.parquet"),
                    target,
                    record["past_majority_direction"],
                    str(cutoff),
                ).write_parquet(temporary / "prediction_metrics.parquet")
                _seal(
                    temporary,
                    {
                        "cutoff": str(cutoff),
                        "mature_at": now.isoformat(),
                        "closed_through": str(end),
                        "registration_sha256": file_sha(partition / "registration.json"),
                        "protocol_sha256": protocol["protocol_sha256"],
                        "candidate_lock_sha256": lock["lock_sha256"],
                        "feature_registry_sha256": protocol["runtime_identity"][
                            "feature_registry_sha256"
                        ],
                        "target_registry_sha256": protocol["runtime_identity"][
                            "target_registry_sha256"
                        ],
                        "code_sha": code_sha(root),
                        "working_tree_dirty": code_dirty(root),
                        "pit_grade": "reconstructed",
                        "future_clean": target.filter(
                            pl.col("future_quality_status") == "clean"
                        ).height,
                        "future_warning": target.filter(
                            pl.col("target_observable")
                            & (pl.col("future_quality_status") != "clean")
                            & pl.col("target_interpretable")
                        ).height,
                        "uninterpretable": target.filter(
                            pl.col("target_observable") & ~pl.col("target_interpretable")
                        ).height,
                        "unobservable": target.filter(~pl.col("target_observable")).height,
                    },
                    "outcome_manifest.json",
                )
                os.rename(temporary, partition / "outcome")
                completed.append(str(cutoff))
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        _json(output / "pending_progress.json", {"pending": pending_progress})
        rebuild_monitor(root=root, config=config, output=output)
    return completed


EMPTY_METRICS = {
    "cutoff": pl.String,
    "policy": pl.String,
    "feature_id": pl.String,
    "expected_sign": pl.Int64,
    "spearman_ic": pl.Float64,
    "oriented_ic": pl.Float64,
    "n": pl.Int64,
    "coverage": pl.Float64,
    "mean_target": pl.Float64,
    "positive_target_rate": pl.Float64,
    "decile_spread": pl.Float64,
}


def rebuild_monitor(*, root: Path, config: Path, output: Path) -> dict[str, Any]:
    """Replace small derived projections, preserving every sealed source/metric partition."""
    protocol = initialize_protocol(root, config, output)
    verify_protocol(root, config, protocol)
    records = verify_store(output, protocol)
    mature = [r for r in records if r["mature"]]
    n = len(mature)
    if mature:
        paths = [
            output / "cutoffs" / f"as_of_date={r['cutoff']}" / "outcome/cutoff_metrics.parquet"
            for r in mature
        ]
        history = pl.concat([pl.read_parquet(p) for p in paths]).sort(
            ["cutoff", "policy", "feature_id"]
        )
        candidates, cohorts, groups, intervals = cumulative_tables(history, protocol)
        predictions = pl.concat(
            [pl.read_parquet(p.parent / "prediction_metrics.parquet") for p in paths]
        )
        alert_dates = [r["cutoff"] for r in records if r["data_quality_alerts"]]
        if alert_dates:
            affected = pl.col("cutoff") >= min(alert_dates)
            cohorts = cohorts.with_columns(
                pl.when(affected)
                .then(pl.lit("insufficient_data"))
                .otherwise(pl.col("verdict"))
                .alias("verdict"),
                pl.when(affected)
                .then(pl.lit("data_quality_alert"))
                .otherwise(pl.col("inference_status"))
                .alias("inference_status"),
                *[
                    pl.when(affected)
                    .then(pl.lit(None, dtype=pl.Float64))
                    .otherwise(pl.col(c))
                    .alias(c)
                    for c in ["ci90_lower", "ci90_upper"]
                ],
            )
    else:
        history = pl.DataFrame(schema=EMPTY_METRICS)
        candidates = pl.DataFrame(
            schema={
                "feature_id": pl.String,
                "cutoff": pl.String,
                "policy": pl.String,
                "mature_cutoffs": pl.Int64,
                "mean_oriented_ic": pl.Float64,
            }
        )
        cohorts = pl.DataFrame(
            schema={
                "tier": pl.String,
                "cutoff": pl.String,
                "policy": pl.String,
                "mature_cutoffs": pl.Int64,
                "mean_oriented_ic": pl.Float64,
            }
        )
        groups = pl.DataFrame(schema={"group_type": pl.String, "group_id": pl.String})
        intervals = pl.DataFrame(schema={"tier": pl.String, "ci90_lower": pl.Float64})
        predictions = pl.DataFrame(schema={"method": pl.String, "cutoff": pl.String})
    exported = {}
    for name, frame in {
        "confirmation_cutoff_metrics": history,
        "confirmation_candidate_metrics": candidates,
        "confirmation_cohort_metrics": cohorts,
        "confirmation_group_metrics": groups,
        "confirmation_intervals": intervals,
        "confirmation_prediction_metrics": predictions,
    }.items():
        path = output / f"{name}.parquet"
        temporary = path.with_suffix(".tmp")
        frame.write_parquet(temporary)
        os.replace(temporary, path)
        exported[path.name] = file_sha(path)
    quality: dict[str, Any] = {
        "cutoffs": records,
        "scientific_interpretation_allowed": not any(r["data_quality_alerts"] for r in records),
        "future_outcomes": [],
    }
    for record in mature:
        quality["future_outcomes"].append(
            json.loads(
                (
                    output
                    / "cutoffs"
                    / f"as_of_date={record['cutoff']}"
                    / "outcome/outcome_manifest.json"
                ).read_text()
            )
        )
    _json(output / "confirmation_data_quality.json", quality)
    progress = (
        json.loads((output / "pending_progress.json").read_text()).get("pending", [])
        if (output / "pending_progress.json").exists()
        else []
    )
    pending_records = [r for r in records if not r["mature"]]
    next_maturity = (
        progress[0]
        if progress
        else (
            {"cutoff": pending_records[0]["cutoff"], "expected_date": None}
            if pending_records
            else None
        )
    )
    manifest = {
        "status": checkpoint_state(n, complete=n >= protocol["settings"]["target_mature_cutoffs"])
        if n or not records
        else "collecting",
        "checkpoint": checkpoint_state(n),
        "protocol_version": protocol["protocol_version"],
        "protocol_sha256": protocol["protocol_sha256"],
        "candidate_lock_version": "candidate_lock_v1",
        "candidate_lock_sha256": protocol["settings"]["candidate_lock_sha256"],
        "feature_registry_sha256": protocol["runtime_identity"]["feature_registry_sha256"],
        "target_registry_sha256": protocol["runtime_identity"]["target_registry_sha256"],
        "confirmation_start_date": protocol["boundary"]["confirmation_start_date"],
        "development_observed_through": protocol["boundary"]["development_observed_through"],
        "mature_cutoffs": n,
        "registered_cutoffs": len(records),
        "next_target_maturity": next_maturity,
        "next_target_maturity_note": "requires five observed future equity sessions; date unknown",
        "counts": {"broad": 504, "strong": 138, "strict": 85},
        "code_sha": code_sha(root),
        "working_tree_dirty": code_dirty(root),
        "pit_grade": "reconstructed",
        "strict_pit_claimed": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "projection_files": exported,
        "source_fingerprints": {r["cutoff"]: r["files"] for r in records},
        "partition_fingerprints": {
            r["cutoff"]: {
                "registration": file_sha(
                    output / "cutoffs" / f"as_of_date={r['cutoff']}" / "registration.json"
                ),
                "outcome": file_sha(
                    output
                    / "cutoffs"
                    / f"as_of_date={r['cutoff']}"
                    / "outcome/outcome_manifest.json"
                )
                if r["mature"]
                else None,
            }
            for r in records
        },
        "retuning_allowed": False,
        "results_available": bool(mature),
    }
    database = root / "data/research.duckdb"
    if database.exists():
        with duckdb.connect(str(database), read_only=True) as db:
            latest, new_dates = db.execute(
                "SELECT max(session_date),count(DISTINCT session_date) FILTER "
                "(WHERE session_date >= ? AND extract(isodow FROM session_date)=5) "
                "FROM market_daily_history",
                [protocol["boundary"]["confirmation_start_date"]],
            ).fetchone() or (None, 0)
        manifest.update(
            current_corpus_latest_observation=str(latest), available_new_source_cutoffs=new_dates
        )
    _json(output / "confirmation_manifest.json", manifest)
    output.chmod(0o755)
    for p in output.iterdir():
        if p.is_file():
            p.chmod(0o644)
    return manifest


def load_monitor(directory: Path) -> dict[str, Any]:
    """Read precomputed monitoring only, with projection checksum verification."""
    manifest = json.loads((directory / "confirmation_manifest.json").read_text())
    protocol = json.loads((directory / "protocol.json").read_text())
    if (
        fingerprint({k: v for k, v in protocol.items() if k != "protocol_sha256"})
        != protocol["protocol_sha256"]
        or manifest["protocol_sha256"] != protocol["protocol_sha256"]
    ):
        raise ValueError("monitor protocol fingerprint mismatch")
    for name, digest in manifest["projection_files"].items():
        if file_sha(directory / name) != digest:
            raise ValueError("confirmation monitor projection checksum mismatch")
    return {
        "manifest": manifest,
        "protocol": protocol,
        "candidates": pl.read_parquet(directory / "confirmation_candidate_metrics.parquet"),
        "cohorts": pl.read_parquet(directory / "confirmation_cohort_metrics.parquet"),
        "history": pl.read_parquet(directory / "confirmation_cutoff_metrics.parquet"),
        "groups": pl.read_parquet(directory / "confirmation_group_metrics.parquet"),
    }
