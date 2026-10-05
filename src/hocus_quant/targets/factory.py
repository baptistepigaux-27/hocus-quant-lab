"""Point-in-time-safe future target construction, independent of SPEC-003 features."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from hocus_quant.features.snapshot import _load_entities
from hocus_quant.targets.registry import (
    BENCHMARK_MAPPINGS,
    COHORT_DEFINITION_VERSION,
    HORIZONS,
    benchmark_registry_document,
    target_registry,
    target_registry_document,
)
from hocus_quant.targets.research_contract import (
    CONTRACT_VERSION,
    freeze_eligibility,
    publish_contract_partition,
    refresh_contract_views,
)
from hocus_quant.validation.market_quality import (
    QUALITY_RULE_VERSION,
    QUALITY_RULES_SHA256,
    assess_series,
)

PARIS = ZoneInfo("Europe/Paris")
PIT_GRADE = "reconstructed"
_SCHEMA_VERSION = "target-factory/1.2"
_EXTREME_RETURN_ABS = 0.9

TARGET_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("entity_family", pa.string()),
        ("as_of_date", pa.date32()),
        ("target_id", pa.string()),
        ("target_family", pa.string()),
        ("target_value", pa.float64()),
        ("candidate_value", pa.float64()),
        ("target_status", pa.string()),
        ("unavailable_reason", pa.string()),
        ("is_end_of_sample_censored", pa.bool_()),
        ("horizon", pa.int16()),
        ("start_date", pa.date32()),
        ("target_end_date", pa.date32()),
        ("start_price", pa.float64()),
        ("end_price", pa.float64()),
        ("quality_status_at_cutoff", pa.string()),
        ("last_future_observation_date", pa.date32()),
        ("benchmark_id", pa.string()),
        ("benchmark_family", pa.string()),
        ("benchmark_mapping_version", pa.string()),
        ("benchmark_start_date", pa.date32()),
        ("benchmark_end_date", pa.date32()),
        ("benchmark_future_observation_count", pa.int16()),
        ("matching_method", pa.string()),
        ("cohort_id", pa.string()),
        ("cohort_size", pa.int32()),
        ("cohort_definition_version", pa.string()),
        ("future_observation_count", pa.int16()),
        ("future_quality_event_count", pa.int16()),
        ("future_quality_reason", pa.string()),
        ("quality_rules_version", pa.string()),
        ("quality_rules_fingerprint", pa.string()),
        ("event_id", pa.string()),
        ("extreme_classification", pa.string()),
        ("extreme_flags", pa.list_(pa.string())),
        ("research_ready", pa.bool_()),
        ("target_registry_version", pa.string()),
        ("target_registry_fingerprint", pa.string()),
        ("benchmark_registry_version", pa.string()),
        ("benchmark_registry_fingerprint", pa.string()),
        ("pit_grade", pa.string()),
        ("strict_pit_claimed", pa.bool_()),
        ("formula_version", pa.string()),
        ("run_id", pa.string()),
    ]
)


def build_target_snapshot(
    *,
    as_of_date: date,
    output_dir: Path,
    data_dir: Path = Path("data"),
    quality_scope: str = "approved",
    eligible_entity_ids: set[str] | None = None,
    apply_hardening: bool = True,
    global_future_session_count: int | None = None,
) -> dict[str, Any]:
    """Build one target snapshot at T, using daily observations after T for Y."""
    if quality_scope != "approved":
        raise ValueError("target factory requires quality_scope='approved'")
    started = time.perf_counter()
    db_path = data_dir / "research.duckdb"
    if not db_path.is_file():
        raise FileNotFoundError(f"research DuckDB does not exist: {db_path}")
    cutoff = datetime.combine(as_of_date + timedelta(days=1), datetime_time.min, tzinfo=PARIS)
    observed = _load_entities(db_path, as_of_date, cutoff)
    decisions = {entity["entity_id"]: assess_series(entity) for entity in observed}
    approved_at_cutoff = {
        entity["entity_id"]: entity
        for entity in observed
        if decisions[entity["entity_id"]]["quality_status"] == "approved"
    }
    historical = {
        entity_id: entity
        for entity_id, entity in approved_at_cutoff.items()
        if eligible_entity_ids is None or entity_id in eligible_entity_ids
    }
    eligibility = [
        freeze_eligibility(
            entity_id=entity["entity_id"],
            entity_family=entity["entity_family"],
            as_of_date=as_of_date,
            quality_status=decisions[entity["entity_id"]]["quality_status"],
            past_dates=[row["session_date"] for row in entity["observations"]],
            universe_admissible=(
                eligible_entity_ids is None or entity["entity_id"] in eligible_entity_ids
            ),
        )
        for entity in observed
    ]
    benchmark_by_family = {item["entity_family"]: item for item in BENCHMARK_MAPPINGS}
    benchmark_ids = {item["benchmark_id"] for item in BENCHMARK_MAPPINGS}
    needed_ids = set(historical) | benchmark_ids
    future_by_id = _load_future_observations(db_path, as_of_date, needed_ids)
    if global_future_session_count is None:
        global_future_session_count = _global_future_session_count(db_path, as_of_date)

    target_doc = target_registry_document()
    benchmark_doc = benchmark_registry_document()
    source_fingerprints = _source_fingerprints(db_path)
    code_sha = _git_value("rev-parse", "HEAD")
    contract = {
        "schema_version": _SCHEMA_VERSION,
        "quality_scope": "approved",
        "quality_rules_version": QUALITY_RULE_VERSION,
        "quality_rules_fingerprint": QUALITY_RULES_SHA256,
        "target_registry_version": target_doc["registry_version"],
        "target_registry_fingerprint": target_doc["sha256"],
        "target_count": target_doc["target_count"],
        "benchmark_registry_version": benchmark_doc["registry_version"],
        "benchmark_registry_fingerprint": benchmark_doc["sha256"],
        "pit_grade": PIT_GRADE,
        "strict_pit_claimed": False,
        "historical_price_contract": (
            "ABC close; session_date + 1 day availability; adjusted close excluded"
        ),
        "future_volatility_contract": (
            "sample std (ddof=1) of H-1 log returns from future closes only * sqrt(252)"
        ),
        "future_quality_policy": (
            "separate frozen eligibility from outcome quality; legacy research_ready retained; "
            "review candidates kept in ex_ante, hard source errors uninterpretable"
        ),
        "research_contract_version": CONTRACT_VERSION,
        "source_fingerprints": source_fingerprints,
        "code_commit_sha": code_sha,
        "working_tree_dirty": bool(_git_value("status", "--porcelain")),
    }
    contract_fingerprint = _sha256_json(contract)
    run_id = hashlib.sha256(
        _canonical_json(
            {
                "contract_fingerprint": contract_fingerprint,
                "as_of_date": as_of_date.isoformat(),
            }
        )
    ).hexdigest()[:24]

    benchmark_entities = {
        item["benchmark_id"]: approved_at_cutoff.get(item["benchmark_id"])
        for item in BENCHMARK_MAPPINGS
    }
    # Benchmarks are quality-screened at T even though they are not output as target entities.
    for mapping in BENCHMARK_MAPPINGS:
        if mapping["benchmark_id"] not in decisions:
            benchmark_entities[mapping["benchmark_id"]] = None

    outcome_by_entity: dict[str, dict[int, dict[str, Any]]] = {}
    benchmark_outcomes: dict[str, dict[int, dict[str, Any]]] = {}
    for entity_id, entity in historical.items():
        outcome_by_entity[entity_id] = _future_outcomes(
            entity,
            future_by_id.get(entity_id, []),
            as_of_date,
            global_future_session_count,
        )
    for benchmark_id, benchmark_entity in benchmark_entities.items():
        if benchmark_entity is not None:
            benchmark_outcomes[benchmark_id] = _future_outcomes(
                benchmark_entity,
                future_by_id.get(benchmark_id, []),
                as_of_date,
                global_future_session_count,
            )

    raw_rows: list[dict[str, Any]] = []
    abs_valid_by_cohort: dict[tuple[str, int], list[tuple[str, float]]] = defaultdict(list)
    for entity_id, entity in historical.items():
        family = entity["entity_family"]
        for horizon in HORIZONS:
            outcome = outcome_by_entity[entity_id][horizon]
            if outcome["status"] == "available":
                abs_valid_by_cohort[(family, horizon)].append((entity_id, outcome["return_abs"]))

    rank_by_entity_horizon: dict[tuple[str, int], tuple[float, int, str]] = {}
    for (family, horizon), values in abs_valid_by_cohort.items():
        rank_values = _average_percentile_ranks([value for _entity, value in values])
        cohort_id = f"family:{family}:{as_of_date.isoformat()}:h{horizon}"
        for (entity_id, _value), rank in zip(values, rank_values, strict=True):
            rank_by_entity_horizon[(entity_id, horizon)] = (rank, len(values), cohort_id)

    definitions_by_horizon = {
        horizon: [item for item in target_registry() if item.horizon == horizon]
        for horizon in HORIZONS
    }
    for entity_id, entity in sorted(historical.items()):
        family = entity["entity_family"]
        benchmark_mapping = benchmark_by_family.get(family)
        for horizon in HORIZONS:
            asset = outcome_by_entity[entity_id][horizon]
            benchmark = (
                benchmark_outcomes.get(benchmark_mapping["benchmark_id"], {}).get(horizon)
                if benchmark_mapping is not None
                else None
            )
            rel_status, rel_reason, rel_candidate = _relative_result(
                asset=asset,
                benchmark=benchmark,
                mapping=benchmark_mapping,
                benchmark_decision=(
                    decisions.get(benchmark_mapping["benchmark_id"])
                    if benchmark_mapping is not None
                    else None
                ),
            )
            rank_entry = rank_by_entity_horizon.get((entity_id, horizon))
            cohort_size = (
                rank_entry[1]
                if rank_entry is not None
                else len(abs_valid_by_cohort.get((family, horizon), []))
            )
            cohort_id = (
                rank_entry[2]
                if rank_entry is not None
                else f"family:{family}:{as_of_date.isoformat()}:h{horizon}"
            )
            values_by_family: dict[str, tuple[str, float | None, float | None, str | None]] = {
                "return_abs": (
                    asset["status"],
                    asset["return_abs"],
                    asset["return_abs"],
                    asset["reason"],
                ),
                "return_rel": (rel_status, rel_candidate, rel_candidate, rel_reason),
                "direction_abs": (
                    asset["status"],
                    _sign(asset["return_abs"]),
                    _sign(asset["return_abs"]),
                    asset["reason"],
                ),
                "direction_rel": (
                    rel_status,
                    _sign(rel_candidate),
                    _sign(rel_candidate),
                    rel_reason,
                ),
                "volatility": (
                    asset["status"],
                    asset["volatility"],
                    asset["volatility"],
                    asset["reason"],
                ),
                "max_drawdown": (
                    asset["status"],
                    asset["max_drawdown"],
                    asset["max_drawdown"],
                    asset["reason"],
                ),
                "max_upside": (
                    asset["status"],
                    asset["max_upside"],
                    asset["max_upside"],
                    asset["reason"],
                ),
                "max_downside": (
                    asset["status"],
                    asset["max_downside"],
                    asset["max_downside"],
                    asset["reason"],
                ),
                "rank_pct": (
                    asset["status"],
                    rank_entry[0] if rank_entry is not None else None,
                    rank_entry[0] if rank_entry is not None else None,
                    asset["reason"] if rank_entry is None else None,
                ),
            }
            for definition in definitions_by_horizon[horizon]:
                family_result = values_by_family[definition.family]
                status, candidate_value, _raw_value, reason = family_result
                # Relative rows also inherit the selected benchmark's future-window quality.
                target_value = candidate_value if status == "available" else None
                row = _target_row(
                    entity_id=entity_id,
                    entity_family=family,
                    as_of_date=as_of_date,
                    definition=definition,
                    candidate_value=candidate_value,
                    target_value=target_value,
                    target_status=status,
                    unavailable_reason=reason,
                    asset=asset,
                    benchmark=(benchmark if benchmark_mapping is not None else None),
                    mapping=benchmark_mapping,
                    cohort_id=cohort_id if definition.cohort_required else None,
                    cohort_size=cohort_size if definition.cohort_required else None,
                    target_doc=target_doc,
                    benchmark_doc=benchmark_doc,
                    run_id=run_id,
                    quality_status_at_cutoff="approved",
                )
                raw_rows.append(row)

    # A rank is only populated for entities with a valid absolute outcome.
    # Others retain an explicit status and null value, and are absent from cohort size.
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "targets.parquet"
    table = pa.Table.from_pylist(raw_rows, schema=TARGET_SCHEMA)
    temporary_target_path = target_path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary_target_path, compression="zstd")
    os.replace(temporary_target_path, target_path)
    audit = _audit_target_rows(raw_rows, as_of_date, len(historical), benchmark_by_family)
    audit_path = output_dir / "target_audit.json"
    _write_json(audit_path, audit)
    (output_dir / "target_audit.md").write_text(_render_target_audit(audit), encoding="utf-8")
    _refresh_target_catalog(output_dir, target_path)
    manifest = {
        **contract,
        "run_id": run_id,
        "contract_fingerprint": contract_fingerprint,
        "as_of_date": as_of_date.isoformat(),
        "cutoff_timestamp": cutoff.isoformat(),
        "quality_scope": "approved",
        "approved_entity_count": len(historical),
        "target_id_count": len(target_doc["targets"]),
        "target_row_count": len(raw_rows),
        "target_registry": target_doc,
        "benchmark_registry": benchmark_doc,
        "source_observation_count_as_of": sum(
            len(item["observations"]) for item in historical.values()
        ),
        "target_parquet_sha256": _sha256_file(target_path),
        "target_parquet_bytes": target_path.stat().st_size,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "audit_path": str(audit_path),
        "status": "complete",
    }
    _write_json(output_dir / "manifest.json", manifest)
    if apply_hardening:
        from hocus_quant.targets.hardening import harden_target_set

        hardening = harden_target_set(output_dir=output_dir, data_dir=data_dir)
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["target_hardening_summary"] = {
            key: hardening[key]
            for key in (
                "extreme_target_rows",
                "unique_events",
                "entities_with_extreme_targets",
                "research_ready_target_rows",
                "target_rows_excluded_from_research_ready",
            )
        }
        _write_json(output_dir / "manifest.json", manifest)
    publish_contract_partition(output_dir, eligibility)
    manifest["target_parquet_sha256"] = _sha256_file(target_path)
    manifest["target_parquet_bytes"] = target_path.stat().st_size
    manifest["research_contract_version"] = CONTRACT_VERSION
    _write_json(output_dir / "manifest.json", manifest)
    return {**manifest, "audit": audit}


def build_target_set(
    *,
    feature_cube_dir: Path,
    output_dir: Path,
    data_dir: Path = Path("data"),
    resume: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Build one daily-resolution target snapshot for each SPEC-004 cutoff."""
    cube_contract_path = feature_cube_dir / "contract.json"
    if not cube_contract_path.is_file():
        raise FileNotFoundError(f"feature cube has no contract.json: {cube_contract_path}")
    cube_contract_document = json.loads(cube_contract_path.read_text(encoding="utf-8"))
    cube_contract = cube_contract_document["contract"]
    if cube_contract.get("quality_scope") != "approved":
        raise ValueError("build-target-set requires an approved-only SPEC-004 cube")
    partitions = sorted(feature_cube_dir.glob("as_of_date=*/manifest.json"))
    if not partitions:
        raise ValueError(f"feature cube has no dated partitions: {feature_cube_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    root_contract = {
        "schema_version": _SCHEMA_VERSION,
        "quality_scope": "approved",
        "feature_cube_contract_fingerprint": cube_contract_document["contract_fingerprint"],
        "target_registry_fingerprint": target_registry_document()["sha256"],
        "benchmark_registry_fingerprint": benchmark_registry_document()["sha256"],
        "quality_rules_fingerprint": QUALITY_RULES_SHA256,
        "pit_grade": PIT_GRADE,
        "strict_pit_claimed": False,
        "source_fingerprints": _source_fingerprints(data_dir / "research.duckdb"),
        "code_commit_sha": _git_value("rev-parse", "HEAD"),
    }
    root_contract_fingerprint = _sha256_json(root_contract)
    contract_path = output_dir / "contract.json"
    if contract_path.exists():
        existing = json.loads(contract_path.read_text(encoding="utf-8"))
        if existing.get("contract_fingerprint") != root_contract_fingerprint:
            raise ValueError("target-set contract changed; use a new output directory")
    else:
        _write_json(
            contract_path,
            {"contract_fingerprint": root_contract_fingerprint, "contract": root_contract},
        )

    generated: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    set_started = time.perf_counter()
    for partition_manifest_path in partitions:
        partition = partition_manifest_path.parent
        cube_manifest = json.loads(partition_manifest_path.read_text(encoding="utf-8"))
        as_of = date.fromisoformat(cube_manifest["as_of_date"])
        target_partition = output_dir / f"as_of_date={as_of.isoformat()}"
        target_manifest_path = target_partition / "manifest.json"
        target_file = target_partition / "targets.parquet"
        if target_file.exists() or target_manifest_path.exists():
            is_valid = _valid_target_partition(
                target_file, target_manifest_path, root_contract_fingerprint
            )
            if is_valid and resume and not force:
                reused.append(json.loads(target_manifest_path.read_text(encoding="utf-8")))
                continue
            if not is_valid and not (resume or force):
                failed.append(
                    {"as_of_date": as_of.isoformat(), "error": "invalid/existing target partition"}
                )
                continue
            if force or (resume and not is_valid):
                for existing_file in target_partition.glob("*"):
                    if existing_file.is_file():
                        existing_file.unlink()

        try:
            cube_features = partition / "features.parquet"
            cube_quality = partition / "quality_status.parquet"
            if not cube_features.is_file() or not cube_quality.is_file():
                raise ValueError("SPEC-004 partition requires features and quality status Parquet")
            with duckdb.connect() as connection:
                feature_entities = {
                    row[0]
                    for row in connection.execute(
                        "SELECT DISTINCT entity_id FROM read_parquet(?)", [str(cube_features)]
                    ).fetchall()
                }
                approved_entities = {
                    row[0]
                    for row in connection.execute(
                        "SELECT entity_id FROM read_parquet(?) WHERE quality_status='approved'",
                        [str(cube_quality)],
                    ).fetchall()
                }
            snapshot_result = build_target_snapshot(
                as_of_date=as_of,
                output_dir=target_partition,
                data_dir=data_dir,
                quality_scope="approved",
                eligible_entity_ids=feature_entities & approved_entities,
                apply_hardening=False,
            )
            target_manifest = {
                **snapshot_result,
                "target_set_contract_fingerprint": root_contract_fingerprint,
                "feature_cube_run_id": cube_manifest.get("run_id"),
                "feature_cube_contract_fingerprint": cube_manifest.get("contract_fingerprint"),
                "status": "complete",
            }
            _write_json(target_manifest_path, target_manifest)
            generated.append(target_manifest)
        except Exception as exc:
            failed.append(
                {"as_of_date": as_of.isoformat(), "error": f"{type(exc).__name__}: {exc}"}
            )

    all_manifests = generated + reused
    root_manifest = {
        **root_contract,
        "run_id": hashlib.sha256(
            _canonical_json(
                {
                    "contract_fingerprint": root_contract_fingerprint,
                    "dates": [
                        json.loads(item.read_text(encoding="utf-8"))["as_of_date"]
                        for item in partitions
                    ],
                }
            )
        ).hexdigest()[:24],
        "contract_fingerprint": root_contract_fingerprint,
        "cutoff_count": len(partitions),
        "dates": [
            json.loads(item.read_text(encoding="utf-8"))["as_of_date"] for item in partitions
        ],
        "generated_slices": [item["as_of_date"] for item in generated],
        "reused_slices": [item["as_of_date"] for item in reused],
        "failed_slices": failed,
        "target_row_count": sum(item.get("target_row_count", 0) for item in all_manifests),
        "elapsed_seconds": round(time.perf_counter() - set_started, 3),
        "status": "failed" if failed else "complete",
    }
    hardening_audit: dict[str, Any] | None = None
    if any(output_dir.glob("as_of_date=*/targets.parquet")):
        from hocus_quant.targets.hardening import harden_target_set

        hardening_audit = harden_target_set(output_dir=output_dir, data_dir=data_dir)
    audit = _audit_target_set(output_dir, all_manifests, failed)
    root_manifest["audit_path"] = str(output_dir / "target_audit.json")
    if hardening_audit is not None:
        root_manifest["target_hardening_summary"] = {
            key: hardening_audit[key]
            for key in (
                "extreme_target_rows",
                "unique_events",
                "entities_with_extreme_targets",
                "research_ready_target_rows",
                "target_rows_excluded_from_research_ready",
            )
        }
    _write_json(output_dir / "manifests" / f"{root_manifest['run_id']}.json", root_manifest)
    if any(output_dir.glob("as_of_date=*/targets.parquet")):
        _refresh_target_set_catalog(output_dir)
    result = {**root_manifest, "audit": audit}
    if failed:
        raise RuntimeError(f"target set has {len(failed)} failed slice(s): {failed[0]}")
    return result


def _future_outcomes(
    entity: dict[str, Any],
    future_rows: list[dict[str, Any]],
    as_of_date: date,
    global_future_session_count: int,
) -> dict[int, dict[str, Any]]:
    past_rows = entity["observations"]
    start_price = _finite(past_rows[-1].get("close")) if past_rows else None
    outcomes: dict[int, dict[str, Any]] = {}
    for horizon in HORIZONS:
        rows = future_rows[:horizon]
        closes = [_finite(row.get("close")) for row in rows]
        usable = [item for item in closes if item is not None and item > 0]
        count = len(rows)
        last_date = rows[-1]["session_date"] if rows else None
        result: dict[str, Any] = {
            "horizon": horizon,
            "status": "insufficient_future_history",
            "reason": f"required_{horizon}_future_sessions_observed_{count}",
            "future_observation_count": count,
            "target_end_date": None,
            "start_price": start_price,
            "end_price": None,
            "start_date": past_rows[-1]["session_date"] if past_rows else None,
            "last_future_observation_date": last_date,
            "return_abs": None,
            "volatility": None,
            "max_drawdown": None,
            "max_upside": None,
            "max_downside": None,
            "future_quality_event_count": 0,
            "future_quality_reason": None,
            "future_quality_evidence": [],
        }
        if count < horizon:
            if global_future_session_count < horizon:
                result["status"] = "right_censored_end_of_sample"
                result["reason"] = (
                    f"global_future_sessions_observed_{global_future_session_count}_before_horizon_{horizon}"
                )
            outcomes[horizon] = result
            continue
        if start_price is None or start_price <= 0 or len(usable) != horizon:
            result["status"] = "undefined"
            result["reason"] = "nonpositive_or_nonfinite_close"
            outcomes[horizon] = result
            continue

        future_close = np.asarray(usable, dtype=np.float64)
        log_returns = np.diff(np.log(future_close))
        if len(log_returns) < 2:
            result["status"] = "undefined"
            result["reason"] = "fewer_than_two_future_to_future_log_returns"
            outcomes[horizon] = result
            continue
        peaks = np.maximum.accumulate(future_close)
        drawdowns = future_close / peaks - 1.0
        values = {
            "return_abs": float(future_close[-1] / start_price - 1.0),
            "volatility": float(np.std(log_returns, ddof=1) * math.sqrt(252.0)),
            "max_drawdown": float(np.min(drawdowns)),
            "max_upside": float(np.max(future_close / start_price - 1.0)),
            "max_downside": float(np.min(future_close / start_price - 1.0)),
        }
        if not all(math.isfinite(value) for value in values.values()):
            result["status"] = "undefined"
            result["reason"] = "nonfinite_target_value"
            outcomes[horizon] = result
            continue

        full_rows = past_rows + rows
        assessment = assess_series({**entity, "observations": full_rows})
        future_quality = assessment["quality_status"]
        evidence = [
            item
            for item in assessment["quality_evidence"]
            if item.get("date") and date.fromisoformat(item["date"]) > as_of_date
        ]
        if future_quality == "quarantined":
            result["status"] = "future_quality_quarantined"
            result["reason"] = "future_window_contains_hard_quality_rule"
        elif future_quality == "review":
            result["status"] = "future_quality_review"
            result["reason"] = "future_window_contains_review_quality_rule"
        else:
            result["status"] = "available"
            result["reason"] = None
        result.update(values)
        result["end_price"] = float(future_close[-1])
        result["start_date"] = past_rows[-1]["session_date"]
        result["target_end_date"] = rows[-1]["session_date"]
        result["last_future_observation_date"] = rows[-1]["session_date"]
        result["future_quality_event_count"] = min(len(evidence), 32767)
        result["future_quality_reason"] = (
            assessment["quality_reason"] if future_quality != "approved" else None
        )
        result["future_quality_evidence"] = evidence
        outcomes[horizon] = result
    return outcomes


def _global_future_session_count(db_path: Path, as_of_date: date) -> int:
    with duckdb.connect(str(db_path), read_only=True) as connection:
        row = connection.execute(
            """SELECT count(DISTINCT session_date) FROM (
                 SELECT session_date FROM market_daily_history WHERE session_date > ?
                 UNION ALL
                 SELECT session_date FROM market_series_history WHERE session_date > ?
               )""",
            [as_of_date, as_of_date],
        ).fetchone()
        if row is None:
            raise RuntimeError("global future session count query returned no row")
        return int(row[0])


def _relative_result(
    *,
    asset: dict[str, Any],
    benchmark: dict[str, Any] | None,
    mapping: dict[str, Any] | None,
    benchmark_decision: dict[str, Any] | None,
) -> tuple[str, str | None, float | None]:
    if asset["status"] == "insufficient_future_history":
        return asset["status"], asset["reason"], None
    if asset["status"] == "right_censored_end_of_sample":
        return asset["status"], asset["reason"], None
    if asset["status"] == "undefined":
        return asset["status"], asset["reason"], None
    if mapping is None:
        return "benchmark_not_defined", "no_defensible_v1_mapping_for_entity_family", None
    if benchmark is None or benchmark_decision is None:
        return "benchmark_defined_but_unavailable", "mapped_benchmark_missing_at_cutoff", None
    if benchmark_decision["quality_status"] != "approved":
        return "benchmark_defined_but_unavailable", "mapped_benchmark_not_approved_at_cutoff", None
    if benchmark["status"] == "insufficient_future_history":
        return (
            "benchmark_defined_but_unavailable",
            "mapped_benchmark_future_history_incomplete",
            None,
        )
    if benchmark["status"] == "right_censored_end_of_sample":
        return (
            "right_censored_end_of_sample",
            "mapped_benchmark_future_horizon_right_censored",
            None,
        )
    if benchmark["status"] == "undefined":
        return "benchmark_defined_but_unavailable", "mapped_benchmark_target_undefined", None
    candidate = float(asset["return_abs"] - benchmark["return_abs"])
    if (
        asset["status"] == "future_quality_quarantined"
        or benchmark["status"] == "future_quality_quarantined"
    ):
        return (
            "future_quality_quarantined",
            "asset_or_benchmark_future_window_quarantined",
            candidate,
        )
    if asset["status"] == "future_quality_review" or benchmark["status"] == "future_quality_review":
        return "future_quality_review", "asset_or_benchmark_future_window_review", candidate
    return "available", None, candidate


def _target_row(
    *,
    entity_id: str,
    entity_family: str,
    as_of_date: date,
    definition: Any,
    candidate_value: float | None,
    target_value: float | None,
    target_status: str,
    unavailable_reason: str | None,
    asset: dict[str, Any],
    benchmark: dict[str, Any] | None,
    mapping: dict[str, Any] | None,
    cohort_id: str | None,
    cohort_size: int | None,
    target_doc: dict[str, Any],
    benchmark_doc: dict[str, Any],
    run_id: str,
    quality_status_at_cutoff: str,
) -> dict[str, Any]:
    future_quality_event_count = int(asset["future_quality_event_count"])
    future_quality_reason = asset["future_quality_reason"]
    if definition.benchmark_required and benchmark is not None:
        future_quality_event_count += int(benchmark["future_quality_event_count"])
        if benchmark["future_quality_reason"]:
            future_quality_reason = "; ".join(
                item for item in (future_quality_reason, benchmark["future_quality_reason"]) if item
            )
    return {
        "entity_id": entity_id,
        "entity_family": entity_family,
        "as_of_date": as_of_date,
        "target_id": definition.target_id,
        "target_family": definition.family,
        "target_value": target_value,
        "candidate_value": candidate_value,
        "target_status": target_status,
        "unavailable_reason": unavailable_reason,
        "is_end_of_sample_censored": target_status == "right_censored_end_of_sample",
        "horizon": definition.horizon,
        "start_date": asset["start_date"],
        "target_end_date": asset["target_end_date"],
        "start_price": asset["start_price"],
        "end_price": asset["end_price"],
        "quality_status_at_cutoff": quality_status_at_cutoff,
        "last_future_observation_date": asset["last_future_observation_date"],
        "benchmark_id": mapping["benchmark_id"] if mapping is not None else None,
        "benchmark_family": mapping["benchmark_family"] if mapping is not None else None,
        "benchmark_mapping_version": mapping["mapping_version"] if mapping is not None else None,
        "benchmark_start_date": benchmark["start_date"] if benchmark is not None else None,
        "benchmark_end_date": (benchmark["target_end_date"] if benchmark is not None else None),
        "benchmark_future_observation_count": (
            benchmark["future_observation_count"] if benchmark is not None else 0
        ),
        "matching_method": "independent_hth_observed_close_per_entity",
        "cohort_id": cohort_id,
        "cohort_size": cohort_size,
        "cohort_definition_version": (
            COHORT_DEFINITION_VERSION if definition.cohort_required else None
        ),
        "future_observation_count": asset["future_observation_count"],
        "future_quality_event_count": min(future_quality_event_count, 32767),
        "future_quality_reason": future_quality_reason,
        "quality_rules_version": QUALITY_RULE_VERSION,
        "quality_rules_fingerprint": QUALITY_RULES_SHA256,
        "event_id": None,
        "extreme_classification": None,
        "extreme_flags": None,
        "research_ready": target_status == "available",
        "target_registry_version": target_doc["registry_version"],
        "target_registry_fingerprint": target_doc["sha256"],
        "benchmark_registry_version": benchmark_doc["registry_version"],
        "benchmark_registry_fingerprint": benchmark_doc["sha256"],
        "pit_grade": PIT_GRADE,
        "strict_pit_claimed": False,
        "formula_version": definition.formula_version,
        "run_id": run_id,
    }


def _load_future_observations(
    db_path: Path, as_of_date: date, entity_ids: set[str]
) -> dict[str, list[dict[str, Any]]]:
    if not entity_ids:
        return {}
    ordered_ids = sorted(entity_ids)
    placeholders = ",".join("?" for _ in ordered_ids)
    query = f"""
    WITH daily AS (
      SELECT 'abc-bourse-manual:equity:' || COALESCE(isin, instrument_id) AS entity_id,
             'equity' AS entity_family, 'market_daily' AS source_series,
             session_date, open, high, low, close, volume, available_at, retrieved_at,
             row_number() OVER (PARTITION BY instrument_id, session_date
               ORDER BY retrieved_at DESC, snapshot_id DESC) AS revision_rank
      FROM market_daily_history WHERE session_date > ?
    ), supplemental AS (
      SELECT 'abc-bourse-manual:' || universe_id || ':' || series_id AS entity_id,
             CASE universe_id
               WHEN 'us_equities' THEN 'equity_us'
               WHEN 'german_equities' THEN 'equity_de'
               WHEN 'market_indices' THEN 'index'
               WHEN 'sector_indices' THEN 'sector_index'
               WHEN 'commodities' THEN 'commodity'
               WHEN 'crypto' THEN 'crypto'
               WHEN 'fx_rates' THEN 'fx_rates'
               WHEN 'bonds' THEN 'bond'
               ELSE 'other:' || universe_id END AS entity_family,
             'market_series' AS source_series, session_date, open, high, low, close, volume,
             available_at, retrieved_at,
             row_number() OVER (PARTITION BY universe_id, series_id, session_date
               ORDER BY retrieved_at DESC, snapshot_checksum DESC) AS revision_rank
      FROM market_series_history WHERE session_date > ?
    ), candidates AS (
      SELECT * FROM daily WHERE revision_rank=1 AND close > 0
      UNION ALL
      SELECT * FROM supplemental WHERE revision_rank=1 AND close > 0
    ), selected AS (
      SELECT *, row_number() OVER (PARTITION BY entity_id ORDER BY session_date) AS future_rank
      FROM candidates WHERE entity_id IN ({placeholders})
    )
    SELECT entity_id, entity_family, source_series, session_date, open, high, low,
           close, volume, available_at, retrieved_at
    FROM selected WHERE future_rank <= 120 ORDER BY entity_id, session_date
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with duckdb.connect(str(db_path), read_only=True) as connection:
        cursor = connection.execute(query, [as_of_date, as_of_date, *ordered_ids])
        names = [column[0] for column in cursor.description]
        while batch := cursor.fetchmany(50_000):
            for values in batch:
                row = dict(zip(names, values, strict=True))
                grouped[str(row["entity_id"])].append(row)
    return dict(grouped)


def _average_percentile_ranks(values: list[float]) -> list[float]:
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index + 1
        while stop < len(order) and values[order[stop]] == values[order[index]]:
            stop += 1
        # One-based average rank divided by cohort size, matching rank(method="average", pct=True).
        average_rank = ((index + 1) + stop) / 2
        percentile = average_rank / len(values)
        for ordered_index in order[index:stop]:
            ranks[ordered_index] = percentile
        index = stop
    return ranks


def _audit_target_rows(
    rows: list[dict[str, Any]],
    as_of_date: date,
    approved_entity_count: int,
    mappings_by_family: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses: Counter[tuple[str, str]] = Counter()
    by_family: Counter[tuple[str, str, str]] = Counter()
    directions: Counter[tuple[str, int]] = Counter()
    values_by_target: dict[str, list[float]] = defaultdict(list)
    candidate_values: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    cohort_sizes: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        target_id = row["target_id"]
        status = row["target_status"]
        statuses[(target_id, status)] += 1
        by_family[(row["entity_family"], target_id, status)] += 1
        if row["target_value"] is not None:
            values_by_target[target_id].append(float(row["target_value"]))
            if row["target_family"] in {"direction_abs", "direction_rel"}:
                directions[(row["target_family"], int(row["target_value"]))] += 1
        if row["candidate_value"] is not None and row["target_family"] in {
            "return_abs",
            "return_rel",
        }:
            candidate_values[target_id].append(
                (row["entity_id"], float(row["candidate_value"]), status)
            )
        if row["cohort_id"] and row["cohort_size"] is not None:
            cohort_sizes[row["target_id"]].add(int(row["cohort_size"]))

    target_coverage = []
    for definition in target_registry():
        total = sum(
            value
            for (target_id, _status), value in statuses.items()
            if target_id == definition.target_id
        )
        available = statuses[(definition.target_id, "available")]
        all_statuses = {
            status: count
            for (target_id, status), count in statuses.items()
            if target_id == definition.target_id
        }
        right_censored = all_statuses.get("right_censored_end_of_sample", 0)
        mapped_benchmark_unavailable = all_statuses.get("benchmark_defined_but_unavailable", 0)
        unavailable = total - available
        observable = total - right_censored
        target_coverage.append(
            {
                "target_id": definition.target_id,
                "family": definition.family,
                "horizon": definition.horizon,
                "rows": total,
                "available": available,
                "unavailable_total": unavailable,
                "right_censored_end_of_sample": right_censored,
                "insufficient_future_history": all_statuses.get("insufficient_future_history", 0),
                "future_quality_review": all_statuses.get("future_quality_review", 0),
                "future_quality_quarantined": all_statuses.get("future_quality_quarantined", 0),
                "benchmark_not_defined": all_statuses.get("benchmark_not_defined", 0),
                "benchmark_defined_but_unavailable": mapped_benchmark_unavailable,
                "benchmark_incomplete": sum(
                    count
                    for reason, count in Counter(
                        row["unavailable_reason"]
                        for row in rows
                        if row["target_id"] == definition.target_id
                    ).items()
                    if reason and "benchmark_future_history_incomplete" in reason
                ),
                "undefined_or_other": max(
                    0,
                    unavailable
                    - right_censored
                    - all_statuses.get("insufficient_future_history", 0)
                    - all_statuses.get("future_quality_review", 0)
                    - all_statuses.get("future_quality_quarantined", 0)
                    - all_statuses.get("benchmark_not_defined", 0)
                    - mapped_benchmark_unavailable,
                ),
                "availability_global": available / total if total else 0.0,
                "coverage": available / total if total else 0.0,
                "observable_candidates": observable,
                "availability_excluding_right_censoring": (
                    available / observable if observable else 0.0
                ),
                "statuses": all_statuses,
                "value_distribution": _distribution(values_by_target.get(definition.target_id, [])),
                "rank_cohort_sizes": sorted(cohort_sizes.get(definition.target_id, set())),
            }
        )

    benchmark_coverage = []
    for family, mapping in sorted(mappings_by_family.items()):
        family_rows = [row for row in rows if row["entity_family"] == family]
        entity_ids = {row["entity_id"] for row in family_rows}
        benchmark_coverage.append(
            {
                "entity_family": family,
                "benchmark_id": mapping["benchmark_id"],
                "mapping_version": mapping["mapping_version"],
                "eligible_entities": len(entity_ids),
                "mapped_entities": len(entity_ids),
                "relative_rows": sum(
                    1
                    for row in family_rows
                    if row["target_family"] in {"return_rel", "direction_rel"}
                ),
                "relative_available_rows": sum(
                    1
                    for row in family_rows
                    if row["target_family"] in {"return_rel", "direction_rel"}
                    and row["target_status"] == "available"
                ),
            }
        )

    extremes: dict[str, Any] = {}
    for family in ("return_abs", "return_rel"):
        candidate_items = [
            item
            for target_id, values in candidate_values.items()
            if next(
                definition.family
                for definition in target_registry()
                if definition.target_id == target_id
            )
            == family
            for item in values
        ]
        flagged = [item for item in candidate_items if abs(item[1]) >= _EXTREME_RETURN_ABS]
        extremes[family] = {
            "review_threshold_abs_value": _EXTREME_RETURN_ABS,
            "flagged_count": len(flagged),
            "largest_positive": [
                {"entity_id": entity, "candidate_value": value, "target_status": status}
                for entity, value, status in sorted(
                    candidate_items, key=lambda item: item[1], reverse=True
                )[:20]
            ],
            "largest_negative": [
                {"entity_id": entity, "candidate_value": value, "target_status": status}
                for entity, value, status in sorted(candidate_items, key=lambda item: item[1])[:20]
            ],
        }

    return {
        "schema_version": _SCHEMA_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "quality_scope": "approved",
        "approved_entity_count": approved_entity_count,
        "target_row_count": len(rows),
        "target_ids": len(target_registry()),
        "target_coverage": target_coverage,
        "coverage_by_entity_family": [
            {
                "entity_family": family,
                "target_id": target_id,
                "target_status": status,
                "count": count,
            }
            for (family, target_id, status), count in sorted(by_family.items())
        ],
        "benchmark_coverage": benchmark_coverage,
        "direction_balance": {
            target_family: {
                str(direction): count
                for (family, direction), count in sorted(directions.items())
                if family == target_family
            }
            for target_family in ("direction_abs", "direction_rel")
        },
        "future_quality_exclusions": {
            status: sum(
                count
                for (_target, target_status), count in statuses.items()
                if target_status == status
            )
            for status in ("future_quality_review", "future_quality_quarantined")
        },
        "end_of_sample_attrition": {
            str(horizon): {
                "right_censored_end_of_sample": sum(
                    count
                    for (target_id, status), count in statuses.items()
                    if status == "right_censored_end_of_sample"
                    and _definition_by_id(target_id).horizon == horizon
                )
            }
            for horizon in HORIZONS
        },
        "unavailable_reasons": dict(
            Counter(row["unavailable_reason"] for row in rows if row["unavailable_reason"])
        ),
        "extreme_return_candidates": extremes,
        "rank_coverage": [item for item in target_coverage if item["family"] == "rank_pct"],
        "cohort_sizes": {
            target_id: sorted(values) for target_id, values in sorted(cohort_sizes.items())
        },
        "pit_grade": PIT_GRADE,
        "strict_pit_claimed": False,
    }


def _audit_target_set(
    output_dir: Path, manifests: list[dict[str, Any]], failed: list[dict[str, Any]]
) -> dict[str, Any]:
    dates = [item["as_of_date"] for item in manifests]
    target_glob = str((output_dir / "as_of_date=*/targets.parquet").resolve()).replace("'", "''")
    if dates:
        with duckdb.connect() as connection:
            by_target = connection.execute(
                f"""SELECT target_id, target_family, horizon, target_status, count(*) AS rows,
                    count(*) FILTER (WHERE target_value IS NOT NULL) AS available,
                    min(target_value), quantile_cont(target_value, .01),
                    quantile_cont(target_value, .5), quantile_cont(target_value, .99),
                    max(target_value)
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  GROUP BY ALL ORDER BY target_id, target_status"""
            ).fetchall()
            by_target_horizon = connection.execute(
                f"""SELECT target_id, target_family, horizon, count(*) AS candidates,
                    count(*) FILTER (WHERE target_status='available') AS available,
                    count(*) FILTER (
                      WHERE target_status='right_censored_end_of_sample') AS censored,
                    count(*) FILTER (
                      WHERE target_status='insufficient_future_history') AS insufficient,
                    count(*) FILTER (WHERE target_status='future_quality_review') AS quality_review,
                    count(*) FILTER (
                      WHERE target_status='future_quality_quarantined') AS quarantined,
                    count(*) FILTER (
                      WHERE target_status='benchmark_not_defined') AS benchmark_not_defined,
                    count(*) FILTER (
                      WHERE target_status='benchmark_defined_but_unavailable')
                      AS benchmark_defined_unavailable,
                    count(*) FILTER (WHERE target_status='undefined') AS undefined
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  GROUP BY ALL ORDER BY target_id"""
            ).fetchall()
            by_benchmark = connection.execute(
                f"""SELECT entity_family, benchmark_id,
                    count(DISTINCT entity_id) AS entity_count,
                    count(*) FILTER (WHERE target_family='return_rel') AS relative_return_rows,
                    count(*) FILTER (WHERE target_family='return_rel'
                                      AND target_status='available') AS available_rows
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family='return_rel' GROUP BY ALL ORDER BY ALL"""
            ).fetchall()
            direction_balance = connection.execute(
                f"""SELECT target_family, horizon, target_value, count(*) AS rows
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family IN ('direction_abs','direction_rel')
                    AND target_value IS NOT NULL
                  GROUP BY ALL ORDER BY ALL"""
            ).fetchall()
            quality_exclusions = connection.execute(
                f"""SELECT target_status, count(*) AS rows
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_status IN ('future_quality_review','future_quality_quarantined')
                  GROUP BY ALL ORDER BY ALL"""
            ).fetchall()
            cohorts = connection.execute(
                f"""SELECT target_id, list(DISTINCT cohort_size ORDER BY cohort_size)
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE cohort_size IS NOT NULL GROUP BY target_id ORDER BY target_id"""
            ).fetchall()
            extreme_counts = connection.execute(
                f"""SELECT target_family, count(*) AS flagged
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family IN ('return_abs','return_rel')
                    AND candidate_value IS NOT NULL
                    AND abs(candidate_value) >= {_EXTREME_RETURN_ABS}
                  GROUP BY target_family ORDER BY target_family"""
            ).fetchall()
            extreme_positive = connection.execute(
                f"""SELECT target_family, entity_id, target_id, candidate_value, target_status
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family IN ('return_abs','return_rel') AND candidate_value IS NOT NULL
                  ORDER BY candidate_value DESC LIMIT 20"""
            ).fetchall()
            extreme_negative = connection.execute(
                f"""SELECT target_family, entity_id, target_id, candidate_value, target_status
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family IN ('return_abs','return_rel') AND candidate_value IS NOT NULL
                  ORDER BY candidate_value LIMIT 20"""
            ).fetchall()
            cutoff_coverage = connection.execute(
                f"""SELECT as_of_date, horizon, count(DISTINCT entity_id) AS entities,
                    count(*) AS candidates,
                    count(*) FILTER (WHERE target_status='available') AS available,
                    count(*) FILTER (
                      WHERE target_status='right_censored_end_of_sample') AS censored,
                    count(*) FILTER (WHERE target_status='future_quality_review') AS quality_review,
                    count(*) FILTER (
                      WHERE target_status='future_quality_quarantined') AS quarantined,
                    count(*) FILTER (
                      WHERE target_status='insufficient_future_history') AS insufficient,
                    count(*) FILTER (
                      WHERE target_status IN ('benchmark_not_defined',
                        'benchmark_defined_but_unavailable')) AS benchmark_unavailable
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family='return_abs' GROUP BY ALL ORDER BY ALL"""
            ).fetchall()
            family_coverage = connection.execute(
                f"""SELECT entity_family, horizon, count(DISTINCT entity_id) AS entities,
                    count(*) AS candidates,
                    count(*) FILTER (WHERE target_status='available') AS available,
                    count(*) FILTER (
                      WHERE target_status='right_censored_end_of_sample') AS censored,
                    count(*) FILTER (WHERE target_status='future_quality_review') AS quality_review,
                    count(*) FILTER (
                      WHERE target_status='future_quality_quarantined') AS quarantined,
                    count(*) FILTER (
                      WHERE target_status='insufficient_future_history') AS insufficient
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family='return_abs' GROUP BY ALL ORDER BY ALL"""
            ).fetchall()
            relative_coverage = connection.execute(
                f"""SELECT horizon, count(*) AS candidates,
                    count(*) FILTER (WHERE target_status='available') AS available,
                    count(*) FILTER (WHERE benchmark_id IS NOT NULL) AS benchmark_mapped,
                    count(*) FILTER (WHERE benchmark_id IS NULL) AS benchmark_not_defined,
                    count(*) FILTER (
                      WHERE target_status='right_censored_end_of_sample') AS censored,
                    count(*) FILTER (
                      WHERE target_status='benchmark_defined_but_unavailable')
                      AS benchmark_defined_unavailable
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family='return_rel' GROUP BY horizon ORDER BY horizon"""
            ).fetchall()
            usable_cohorts = connection.execute(
                f"""SELECT horizon, min(as_of_date), max(as_of_date),
                    count(DISTINCT as_of_date), count(*)
                  FROM read_parquet('{target_glob}', union_by_name=true)
                  WHERE target_family='return_abs' AND target_status='available'
                  GROUP BY horizon ORDER BY horizon"""
            ).fetchall()
    else:
        by_target = []
        by_target_horizon = []
        by_benchmark = []
        direction_balance = []
        quality_exclusions = []
        cohorts = []
        extreme_counts = []
        extreme_positive = []
        extreme_negative = []
        cutoff_coverage = []
        family_coverage = []
        relative_coverage = []
        usable_cohorts = []
    audit = {
        "schema_version": _SCHEMA_VERSION,
        "slice_count": len(manifests),
        "cutoffs": dates,
        "target_row_count": sum(item.get("target_row_count", 0) for item in manifests),
        "target_coverage_by_status": [
            dict(
                zip(
                    (
                        "target_id",
                        "target_family",
                        "horizon",
                        "target_status",
                        "rows",
                        "available",
                        "min",
                        "p01",
                        "median",
                        "p99",
                        "max",
                    ),
                    row,
                    strict=True,
                )
            )
            for row in by_target
        ],
        "availability_by_target_and_horizon": [
            {
                "target_id": row[0],
                "target_family": row[1],
                "horizon": row[2],
                "candidate_rows": row[3],
                "available": row[4],
                "unavailable_total": row[3] - row[4],
                "right_censored_end_of_sample": row[5],
                "insufficient_future_history": row[6],
                "future_quality_review": row[7],
                "future_quality_quarantined": row[8],
                "benchmark_not_defined": row[9],
                "benchmark_defined_but_unavailable": row[10],
                "undefined_or_other": row[11],
                "availability_global": row[4] / row[3] if row[3] else 0.0,
                "availability_excluding_censoring": row[4] / (row[3] - row[5])
                if row[3] > row[5]
                else 0.0,
            }
            for row in by_target_horizon
        ],
        "benchmark_mapping_coverage": [
            dict(
                zip(
                    (
                        "entity_family",
                        "benchmark_id",
                        "entity_count",
                        "relative_return_rows",
                        "available_rows",
                    ),
                    row,
                    strict=True,
                )
            )
            for row in by_benchmark
        ],
        "direction_balance": [
            dict(zip(("target_family", "horizon", "direction", "rows"), row, strict=True))
            for row in direction_balance
        ],
        "future_quality_exclusions": dict(quality_exclusions),
        "availability_by_cutoff_and_horizon": [
            {
                **dict(
                    zip(
                        (
                            "as_of_date",
                            "horizon",
                            "entities",
                            "candidates",
                            "available",
                            "right_censored_end_of_sample",
                            "future_quality_review",
                            "future_quality_quarantined",
                            "insufficient_future_history",
                            "benchmark_unavailable",
                        ),
                        row,
                        strict=True,
                    )
                ),
                "as_of_date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            }
            | {
                "availability_global": row[4] / row[3] if row[3] else 0.0,
                "availability_excluding_censoring": row[4] / (row[3] - row[5])
                if row[3] > row[5]
                else 0.0,
            }
            for row in cutoff_coverage
        ],
        "availability_by_family_and_horizon": [
            dict(
                zip(
                    (
                        "entity_family",
                        "horizon",
                        "entities",
                        "candidates",
                        "available",
                        "right_censored_end_of_sample",
                        "future_quality_review",
                        "future_quality_quarantined",
                        "insufficient_future_history",
                    ),
                    row,
                    strict=True,
                )
            )
            | {
                "availability_global": row[4] / row[3] if row[3] else 0.0,
                "availability_excluding_censoring": row[4] / (row[3] - row[5])
                if row[3] > row[5]
                else 0.0,
            }
            for row in family_coverage
        ],
        "relative_availability_by_horizon": [
            {
                "horizon": row[0],
                "candidates": row[1],
                "available": row[2],
                "benchmark_mapped": row[3],
                "benchmark_not_defined": row[4],
                "right_censored_end_of_sample": row[5],
                "benchmark_defined_but_unavailable": row[6],
                "global_availability": row[2] / row[1] if row[1] else 0.0,
                "benchmark_mapped_population_rate": row[3] / row[1] if row[1] else 0.0,
                "availability_among_mapped_observable": row[2] / (row[3] - row[5])
                if row[3] > row[5]
                else 0.0,
            }
            for row in relative_coverage
        ],
        "usable_cutoff_cohorts_by_horizon": [
            {
                "horizon": row[0],
                "first_usable_cutoff": row[1].isoformat(),
                "last_usable_cutoff": row[2].isoformat(),
                "cutoff_count": row[3],
                "available_entity_cutoff_rows": row[4],
            }
            for row in usable_cohorts
        ],
        "rank_cohort_sizes": {target_id: sizes for target_id, sizes in cohorts},
        "extreme_return_review": {
            "absolute_threshold": _EXTREME_RETURN_ABS,
            "flagged_counts": dict(extreme_counts),
            "largest_positive": [
                dict(
                    zip(
                        (
                            "target_family",
                            "entity_id",
                            "target_id",
                            "candidate_value",
                            "target_status",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in extreme_positive
            ],
            "largest_negative": [
                dict(
                    zip(
                        (
                            "target_family",
                            "entity_id",
                            "target_id",
                            "candidate_value",
                            "target_status",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in extreme_negative
            ],
        },
        "failed_slices": failed,
        "error_count": len(failed),
        "pit_grade": PIT_GRADE,
        "strict_pit_claimed": False,
    }
    _write_json(output_dir / "target_audit.json", audit)
    (output_dir / "target_audit.md").write_text(_render_target_audit(audit), encoding="utf-8")
    return audit


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "p01": None, "median": None, "p99": None, "max": None}
    quantiles = np.quantile(np.asarray(values), [0.01, 0.5, 0.99])
    return {
        "count": len(values),
        "min": min(values),
        "p01": float(quantiles[0]),
        "median": float(quantiles[1]),
        "p99": float(quantiles[2]),
        "max": max(values),
    }


def _definition_by_id(target_id: str) -> Any:
    for item in target_registry():
        if item.target_id == target_id:
            return item
    raise KeyError(target_id)


def _refresh_target_catalog(output_dir: Path, target_path: Path) -> None:
    path = output_dir / "target_catalog.duckdb"
    parquet = str(target_path.resolve()).replace("'", "''")
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            f"CREATE OR REPLACE VIEW targets AS SELECT * FROM read_parquet('{parquet}')"
        )


def _refresh_target_set_catalog(output_dir: Path) -> None:
    parquet = str((output_dir / "as_of_date=*/targets.parquet").resolve()).replace("'", "''")
    ready_parquet = str(
        (output_dir / "as_of_date=*/targets_research_ready.parquet").resolve()
    ).replace("'", "''")
    with duckdb.connect(str(output_dir / "target_catalog.duckdb")) as connection:
        connection.execute(
            "CREATE OR REPLACE VIEW targets AS SELECT * FROM "
            f"read_parquet('{parquet}', union_by_name=true)"
        )
        connection.execute(
            "CREATE OR REPLACE VIEW targets_research_ready AS SELECT * FROM "
            f"read_parquet('{ready_parquet}', union_by_name=true)"
        )
        columns = {row[0] for row in connection.execute("DESCRIBE targets").fetchall()}
        if "eligible_at_cutoff" in columns:
            refresh_contract_views(connection)


def _valid_target_partition(
    target_path: Path, manifest_path: Path, contract_fingerprint: str
) -> bool:
    if not target_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(
            manifest.get("status") == "complete"
            and manifest.get("target_set_contract_fingerprint") == contract_fingerprint
            and manifest.get("target_parquet_sha256") == _sha256_file(target_path)
            and manifest.get("pit_grade") == PIT_GRADE
        )
    except (OSError, ValueError):
        return False


def _source_fingerprints(db_path: Path) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    with duckdb.connect(str(db_path), read_only=True) as connection:
        for view in ("market_daily_history", "market_series_history"):
            columns = {row[0] for row in connection.execute(f"DESCRIBE {view}").fetchall()}
            fields = [
                name
                for name in ("snapshot_checksum", "member_checksum", "snapshot_id")
                if name in columns
            ]
            identifiers: set[str] = set()
            for field in fields:
                identifiers.update(
                    str(row[0])
                    for row in connection.execute(
                        f"SELECT DISTINCT {field} FROM {view} WHERE {field} IS NOT NULL"
                    ).fetchall()
                )
            values[view] = sorted(identifiers)
    return {view: _sha256_json(items) for view, items in values.items()}


def _git_value(*args: str) -> str | None:
    try:
        return (
            subprocess.run(
                ["git", *args], check=True, capture_output=True, text=True, timeout=5
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) else None


def _sign(value: float | None) -> int | None:
    if value is None:
        return None
    return 1 if value > 0 else -1 if value < 0 else 0


def _render_target_audit(audit: dict[str, Any]) -> str:
    if "target_coverage" in audit:
        lines = [
            f"# Target audit — {audit['as_of_date']}",
            "",
            f"- Approved entities: {audit['approved_entity_count']:,}",
            f"- Target rows: {audit['target_row_count']:,} across {audit['target_ids']} target IDs",
            f"- PIT: `{PIT_GRADE}` (strict: false)",
            "",
            "| Target | H | Rows | Available | Coverage | Status counts |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
        lines.extend(
            f"| `{item['target_id']}` | {item['horizon']} | {item['rows']:,} | "
            f"{item['available']:,} | {item['coverage']:.2%} | `{item['statuses']}` |"
            for item in audit["target_coverage"]
        )
        lines.extend(["", "## Future quality exclusions", ""])
        lines.extend(
            f"- {key}: {value:,}" for key, value in audit["future_quality_exclusions"].items()
        )
        lines.extend(["", "## Extreme return candidates (review only)", ""])
        for family, summary in audit["extreme_return_candidates"].items():
            lines.append(
                f"- {family}: {summary['flagged_count']:,} values with absolute return "
                f"≥ {summary['review_threshold_abs_value']:.0%}; values are retained."
            )
        return "\n".join(lines) + "\n"
    lines = [
        "# Target set audit",
        "",
        f"- Cutoffs: {audit['slice_count']:,}",
        f"- Target rows: {audit['target_row_count']:,}",
        f"- Failed slices: {audit['error_count']:,}",
        f"- PIT: `{PIT_GRADE}` (strict: false)",
        "",
        "| Target | H | Status | Rows | Available | Min | P01 | Median | P99 | Max |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in audit["target_coverage_by_status"]:
        lines.append(
            f"| `{item['target_id']}` | {item['horizon']} | {item['target_status']} | "
            f"{item['rows']:,} | {item['available']:,} | {item['min']} | {item['p01']} | "
            f"{item['median']} | {item['p99']} | {item['max']} |"
        )
    return "\n".join(lines) + "\n"
