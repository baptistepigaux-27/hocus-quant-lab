"""Point-in-time historical feature cube built from the frozen SPEC-003 engine."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from hocus_quant.features.registry import FEATURE_REGISTRY, registry_document
from hocus_quant.features.snapshot import build_feature_snapshot
from hocus_quant.validation.market_quality import QUALITY_RULE_VERSION, QUALITY_RULES_SHA256

CADENCES = ("explicit", "weekly", "daily")
PIT_GRADE = "reconstructed"
_CUBE_SCHEMA_VERSION = "feature-cube/1.0"
_DISTRIBUTION_FEATURES = (
    "close.log.trend_pct.w60.v1",
    "close.return.std.w20.v1",
    "close.log_return.std.w20.v1",
    "ohlc.technical.rsi.w14.v1",
    "ohlc.technical.atr_pct.w14.v1",
    "volume.relative.current_vs_mean.w20.v1",
)


def resolve_date_grid(
    *,
    data_dir: Path,
    cadence: Literal["explicit", "weekly", "daily"] = "weekly",
    dates: list[date] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[date]:
    """Resolve requested cutoffs to actual session dates in the available corpus.

    Explicit non-session dates roll back to the latest session on or before the
    request. Weekly uses the last corpus session in each ISO week; daily uses
    every distinct corpus session. Weekly/daily boundaries are inclusive.
    """
    sessions = _market_session_dates(data_dir / "research.duckdb")
    if not sessions:
        raise ValueError("market history contains no session dates")
    if cadence == "explicit":
        if not dates:
            raise ValueError("explicit cadence requires at least one date")
        resolved: set[date] = set()
        for requested in dates:
            previous = [session for session in sessions if session <= requested]
            if not previous:
                raise ValueError(f"no market session exists on or before {requested.isoformat()}")
            resolved.add(previous[-1])
        return sorted(resolved)
    if dates is not None:
        raise ValueError("dates can only be used with explicit cadence")
    if start is None or end is None or end < start:
        raise ValueError("weekly/daily cadence requires start <= end")
    selected = [session for session in sessions if start <= session <= end]
    if cadence == "daily":
        return selected
    if cadence != "weekly":
        raise ValueError(f"unsupported cadence: {cadence}")
    last_by_iso_week: dict[tuple[int, int], date] = {}
    for session in selected:
        iso = session.isocalendar()
        last_by_iso_week[(iso.year, iso.week)] = session
    return sorted(last_by_iso_week.values())


def build_feature_cube(
    *,
    output_dir: Path,
    data_dir: Path = Path("data"),
    dates: list[date] | None = None,
    start: date | None = None,
    end: date | None = None,
    cadence: Literal["explicit", "weekly", "daily"] = "weekly",
    quality_scope: str = "approved",
    resume: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Materialize approved SPEC-003 slices into independent date partitions."""
    if quality_scope != "approved":
        raise ValueError("feature cubes are research-only and require quality_scope='approved'")
    grid = resolve_date_grid(data_dir=data_dir, cadence=cadence, dates=dates, start=start, end=end)
    if not grid:
        raise ValueError("the requested period contains no market sessions")
    contract = _build_contract(data_dir / "research.duckdb")
    contract_bytes = _canonical_json(contract)
    contract_fingerprint = hashlib.sha256(contract_bytes).hexdigest()
    run_id = hashlib.sha256(
        _canonical_json(
            {"contract_fingerprint": contract_fingerprint, "dates": [d.isoformat() for d in grid]}
        )
    ).hexdigest()[:24]
    if dry_run:
        return {
            "run_id": run_id,
            "status": "planned",
            "cadence": cadence,
            "dates": [item.isoformat() for item in grid],
            "slice_count": len(grid),
            "contract_fingerprint": contract_fingerprint,
            **contract,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir = output_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    contract_path = output_dir / "contract.json"
    _establish_contract(contract_path, contract, contract_fingerprint, output_dir)

    started = time.perf_counter()
    generated: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifest_path = manifests_dir / f"{run_id}.json"
    run_manifest: dict[str, Any] = {
        "schema_version": _CUBE_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "start": grid[0].isoformat(),
        "end": grid[-1].isoformat(),
        "cadence": cadence,
        "cutoff_count": len(grid),
        "dates": [item.isoformat() for item in grid],
        "quality_scope": "approved",
        "pit_grade": PIT_GRADE,
        "feature_count": len(FEATURE_REGISTRY),
        "contract_fingerprint": contract_fingerprint,
        "contract": contract,
        "generated_slices": generated,
        "reused_slices": reused,
        "failed_slices": failed,
    }
    _write_json(manifest_path, run_manifest)

    for as_of in grid:
        partition = output_dir / f"as_of_date={as_of.isoformat()}"
        feature_path = partition / "features.parquet"
        slice_manifest_path = partition / "manifest.json"
        if feature_path.exists() or slice_manifest_path.exists():
            valid_existing = _valid_partition(
                feature_path, slice_manifest_path, contract_fingerprint
            )
            if valid_existing and not force:
                if not resume:
                    failed.append(
                        {
                            "as_of_date": as_of.isoformat(),
                            "error": "partition exists; pass --resume or --force",
                        }
                    )
                    continue
                reused.append(json.loads(slice_manifest_path.read_text(encoding="utf-8")))
                _write_json(manifest_path, run_manifest)
                continue
            if resume and not valid_existing:
                for stale_path in partition.iterdir():
                    if stale_path.is_file():
                        stale_path.unlink()
            elif not force and not valid_existing:
                failed.append(
                    {
                        "as_of_date": as_of.isoformat(),
                        "error": "existing partition is invalid; pass --force",
                    }
                )
                continue
        try:
            slice_result = _build_slice(
                as_of=as_of,
                data_dir=data_dir,
                output_dir=output_dir,
                contract=contract,
                contract_fingerprint=contract_fingerprint,
            )
            generated.append(slice_result)
        except Exception as exc:
            failed.append(
                {"as_of_date": as_of.isoformat(), "error": f"{type(exc).__name__}: {exc}"}
            )
        _write_json(manifest_path, run_manifest)

    elapsed = time.perf_counter() - started
    run_manifest["elapsed_seconds"] = round(elapsed, 3)
    run_manifest["status"] = "failed" if failed else "complete"
    run_manifest["generated_cells"] = sum(item["cell_count"] for item in generated)
    run_manifest["total_cells"] = sum(item["cell_count"] for item in generated + reused)
    run_manifest["generated_seconds"] = round(sum(item["elapsed_seconds"] for item in generated), 3)
    run_manifest["disk_bytes"] = sum(item["bytes"] for item in generated + reused)
    run_manifest["cells_per_second"] = round(
        run_manifest["generated_cells"] / max(elapsed, 1e-9), 1
    )
    _write_json(manifest_path, run_manifest)
    audit = audit_feature_cube(output_dir, expected_dates=grid)
    if list(output_dir.glob("as_of_date=*/features.parquet")):
        _refresh_cube_catalog(output_dir)
    run_manifest["audit_path"] = str(output_dir / "cube_audit.json")
    _write_json(manifest_path, run_manifest)
    result = {**run_manifest, "manifest_path": str(manifest_path), "audit": audit}
    if failed:
        raise RuntimeError(f"feature cube has {len(failed)} failed slice(s): {failed[0]}")
    return result


def audit_feature_cube(
    output_dir: Path, *, expected_dates: list[date] | None = None
) -> dict[str, Any]:
    """Create a temporal coverage, universe-change and quality-status audit."""
    expected = sorted(expected_dates or [])
    partitions = sorted(output_dir.glob("as_of_date=*/manifest.json"))
    slices: list[dict[str, Any]] = []
    missing: list[str] = []
    for path in partitions:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not _valid_partition(
            path.parent / "features.parquet",
            path,
            manifest.get("contract_fingerprint", ""),
        ):
            missing.append(manifest.get("as_of_date", path.parent.name))
            continue
        slices.append(manifest)
    by_date = {item["as_of_date"]: item for item in slices}
    missing.extend(item.isoformat() for item in expected if item.isoformat() not in by_date)
    previous_entities: set[str] = set()
    previous_status: dict[str, str] = {}
    arrivals: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []
    for manifest in sorted(slices, key=lambda item: item["as_of_date"]):
        as_of = manifest["as_of_date"]
        quality_path = output_dir / f"as_of_date={as_of}" / "quality_status.parquet"
        quality = pq.read_table(quality_path).to_pylist() if quality_path.exists() else []
        current_entities = {
            str(row["entity_id"]) for row in quality if row["quality_status"] == "approved"
        }
        current_status = {str(row["entity_id"]): str(row["quality_status"]) for row in quality}
        arrivals.append(
            {
                "as_of_date": as_of,
                "arrived": len(current_entities - previous_entities),
                "disappeared": len(previous_entities - current_entities),
                "approved_entities": len(current_entities),
            }
        )
        for entity, status in current_status.items():
            old_status = previous_status.get(entity)
            if old_status is not None and old_status != status:
                status_changes.append(
                    {
                        "as_of_date": as_of,
                        "entity_id": entity,
                        "from": old_status,
                        "to": status,
                    }
                )
        previous_entities = current_entities
        previous_status = current_status
    result = {
        "schema_version": _CUBE_SCHEMA_VERSION,
        "slice_count": len(slices),
        "expected_slice_count": len(expected) if expected else len(slices),
        "missing_partitions": sorted(set(missing)),
        "error_count": len(missing),
        "entity_count_min": min((item["entity_count"] for item in slices), default=0),
        "entity_count_median": _median([item["entity_count"] for item in slices]),
        "entity_count_max": max((item["entity_count"] for item in slices), default=0),
        "total_cells": sum(item["cell_count"] for item in slices),
        "available_cells": sum(item["available_cells"] for item in slices),
        "unavailable_cells": sum(item["unavailable_cells"] for item in slices),
        "availability_rate": (
            sum(item["available_cells"] for item in slices)
            / max(sum(item["cell_count"] for item in slices), 1)
        ),
        "cells_by_date": [
            {
                "as_of_date": item["as_of_date"],
                "entity_count": item["entity_count"],
                "cell_count": item["cell_count"],
                "available_cells": item["available_cells"],
                "unavailable_cells": item["unavailable_cells"],
                "availability_rate": item["availability_rate"],
                "coverage_by_window": item["coverage_by_window"],
                "quality_status_counts": item["quality_status_counts"],
                "distribution_summary": item["distribution_summary"],
            }
            for item in slices
        ],
        "entity_arrivals_disappearances": arrivals,
        "quality_status_changes": status_changes,
        "partition_errors": [item["as_of_date"] for item in slices if item.get("partition_error")],
    }
    _write_json(output_dir / "cube_audit.json", result)
    (output_dir / "cube_audit.md").write_text(_render_cube_audit(result), encoding="utf-8")
    return result


def export_feature_panel(
    cube_dir: Path,
    *,
    start: date | None = None,
    end: date | None = None,
    families: list[str] | None = None,
    feature_ids: list[str] | None = None,
    minimum_coverage: float | None = None,
    entity_ids: list[str] | None = None,
    output_path: Path | None = None,
) -> Any:
    """Return a Polars wide panel; missing feature values remain null."""
    import polars as pl

    glob = str((cube_dir / "as_of_date=*/features.parquet").resolve()).replace("'", "''")
    filters = ["TRUE"]
    if start is not None:
        filters.append(f"as_of_date >= DATE '{start.isoformat()}'")
    if end is not None:
        filters.append(f"as_of_date <= DATE '{end.isoformat()}'")
    if minimum_coverage is not None:
        if not 0 <= minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be in [0, 1]")
        filters.append(f"coverage_ratio >= {minimum_coverage!r}")
    for column, values in (
        ("entity_family", families),
        ("feature_id", feature_ids),
        ("entity_id", entity_ids),
    ):
        if values is not None:
            if not values:
                return pl.DataFrame()
            literals = ",".join(_sql_string(value) for value in values)
            filters.append(f"{column} IN ({literals})")
    query = f"""
      PIVOT (
        SELECT entity_id, as_of_date, feature_id, feature_value
        FROM read_parquet('{glob}') WHERE {" AND ".join(filters)}
      ) ON feature_id USING first(feature_value) GROUP BY entity_id, as_of_date
    """
    with duckdb.connect() as connection:
        arrow = connection.execute(query).to_arrow_table()
    frame = cast(pl.DataFrame, pl.from_arrow(arrow))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(output_path)
    return frame


def _build_slice(
    *,
    as_of: date,
    data_dir: Path,
    output_dir: Path,
    contract: dict[str, Any],
    contract_fingerprint: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    partition = output_dir / f"as_of_date={as_of.isoformat()}"
    partition.mkdir(parents=True, exist_ok=True)
    slice_id = hashlib.sha256(f"{contract_fingerprint}:{as_of.isoformat()}".encode()).hexdigest()[
        :24
    ]
    with tempfile.TemporaryDirectory(prefix="hocus-cube-") as tmp:
        snapshot_dir = Path(tmp) / "snapshot"
        audit = build_feature_snapshot(
            as_of_date=as_of,
            output_dir=snapshot_dir,
            data_dir=data_dir,
            quality_scope="approved",
        )
        source_long = pq.ParquetFile(snapshot_dir / "features_long.parquet")
        destination = partition / "features.parquet"
        temp_destination = partition / "features.parquet.tmp"
        schema = source_long.schema_arrow.append(pa.field("run_id", pa.string(), nullable=True))
        writer = pq.ParquetWriter(temp_destination, schema=schema, compression="zstd")
        try:
            for batch in source_long.iter_batches(batch_size=100_000):
                table = pa.Table.from_batches([batch])
                table = table.append_column("run_id", pa.array([slice_id] * table.num_rows))
                writer.write_table(table)
        finally:
            writer.close()
        os.replace(temp_destination, destination)
        quality_source = json.loads(
            (snapshot_dir / "market_quality_audit.json").read_text(encoding="utf-8")
        )
        qrows = [
            {
                "entity_id": item["entity_id"],
                "entity_family": item["entity_family"],
                "quality_status": item["quality_status"],
                "quality_reason": item["quality_reason"],
            }
            for item in quality_source["decisions"]
        ]
        pq.write_table(
            pa.Table.from_pylist(qrows), partition / "quality_status.parquet", compression="zstd"
        )
        selected_distribution = [
            {key: item[key] for key in ("feature_id", "available_count", "p01", "median", "p99")}
            for item in audit["feature_distribution"]
            if item["feature_id"] in _DISTRIBUTION_FEATURES
        ]
        partition_manifest = {
            "schema_version": _CUBE_SCHEMA_VERSION,
            "as_of_date": as_of.isoformat(),
            "run_id": slice_id,
            "contract_fingerprint": contract_fingerprint,
            "quality_scope": "approved",
            "quality_rules_version": contract["quality_rules_version"],
            "quality_rules_fingerprint": contract["quality_rules_fingerprint"],
            "feature_registry_fingerprint": contract["feature_registry_fingerprint"],
            "pit_grade": contract["pit_grade"],
            "feature_count": audit["feature_count"],
            "entity_count": audit["entity_count"],
            "cell_count": audit["total_cells"],
            "available_cells": audit["cell_status_counts"]["available"],
            "unavailable_cells": audit["cell_status_counts"]["unavailable"],
            "availability_rate": audit["available_rate"],
            "coverage_by_window": audit["coverage_by_window"],
            "entity_count_by_family": audit["entity_count_by_family"],
            "quality_status_counts": audit["quality_status_counts_before_scope"],
            "distribution_summary": selected_distribution,
            "source_observation_count": audit["source_observation_count"],
            "source_rows_retrieved_after_cutoff": audit["source_rows_retrieved_after_cutoff"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "cells_per_second": round(
                audit["total_cells"] / max(time.perf_counter() - started, 1e-9), 1
            ),
            "bytes": destination.stat().st_size
            + (partition / "quality_status.parquet").stat().st_size,
            "partition_sha256": _sha256_file(destination),
            "status": "complete",
        }
        _write_json(partition / "manifest.json", partition_manifest)
    return partition_manifest


def _build_contract(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        raise FileNotFoundError(f"research DuckDB does not exist: {db_path}")
    registry = registry_document()
    source_fingerprints = _source_fingerprints(db_path)
    code_sha = _git_value("rev-parse", "HEAD")
    dirty = bool(_git_value("status", "--porcelain"))
    return {
        "quality_scope": "approved",
        "quality_rules_version": QUALITY_RULE_VERSION,
        "quality_rules_fingerprint": QUALITY_RULES_SHA256,
        "feature_registry_version": registry["registry_version"],
        "feature_registry_fingerprint": registry["sha256"],
        "feature_count": len(FEATURE_REGISTRY),
        "pit_grade": PIT_GRADE,
        "pit_grade_by_source": {"abc-bourse-manual": PIT_GRADE},
        "strict_pit_claimed": False,
        "historical_availability_assumption": "session_date + 1 day; vintage history unavailable",
        "code_commit_sha": code_sha,
        "working_tree_dirty": dirty,
        "source_fingerprints": source_fingerprints,
    }


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
            fingerprints: set[str] = set()
            for field in fields:
                fingerprints.update(
                    str(row[0])
                    for row in connection.execute(
                        f"SELECT DISTINCT {field} FROM {view} WHERE {field} IS NOT NULL"
                    ).fetchall()
                )
            values[view] = sorted(fingerprints)
    return {
        name: hashlib.sha256(_canonical_json(fingerprints)).hexdigest()
        for name, fingerprints in values.items()
    }


def _refresh_cube_catalog(output_dir: Path) -> None:
    feature_glob = str((output_dir / "as_of_date=*/features.parquet").resolve()).replace("'", "''")
    quality_glob = str((output_dir / "as_of_date=*/quality_status.parquet").resolve()).replace(
        "'", "''"
    )
    feature_ids = ", ".join(
        "'" + item.feature_id.replace("'", "''") + "'" for item in FEATURE_REGISTRY
    )
    with duckdb.connect(str(output_dir / "feature_cube.duckdb")) as connection:
        connection.execute(
            f"CREATE OR REPLACE VIEW features_long AS "
            f"SELECT * FROM read_parquet('{feature_glob}', union_by_name=true)"
        )
        connection.execute(
            f"CREATE OR REPLACE VIEW quality_status AS "
            f"SELECT * FROM read_parquet('{quality_glob}', union_by_name=true)"
        )
        connection.execute(
            f"""CREATE OR REPLACE VIEW features_wide AS
               PIVOT (SELECT entity_id, as_of_date, feature_id, feature_value
                      FROM features_long)
               ON feature_id IN ({feature_ids}) USING first(feature_value)
               GROUP BY entity_id, as_of_date"""
        )


def _market_session_dates(db_path: Path) -> list[date]:
    if not db_path.is_file():
        raise FileNotFoundError(f"research DuckDB does not exist: {db_path}")
    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.execute(
            """SELECT DISTINCT session_date FROM (
                 SELECT session_date FROM market_daily_history
                 UNION ALL SELECT session_date FROM market_series_history
               ) WHERE session_date IS NOT NULL ORDER BY session_date"""
        ).fetchall()
    return [row[0] for row in rows]


def _establish_contract(
    path: Path, contract: dict[str, Any], fingerprint: str, output_dir: Path
) -> None:
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("contract_fingerprint") != fingerprint:
            raise ValueError(
                "cube contract changed (registry, quality rules, source or code); "
                "build into a new directory to avoid mixing contracts"
            )
        return
    existing = list(output_dir.glob("as_of_date=*/features.parquet"))
    if existing:
        raise ValueError("partitions exist without a contract manifest; use a new output directory")
    _write_json(path, {"contract_fingerprint": fingerprint, "contract": contract})


def _valid_partition(feature_path: Path, manifest_path: Path, contract_fp: str) -> bool:
    if not feature_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(
            manifest.get("status") == "complete"
            and manifest.get("contract_fingerprint") == contract_fp
            and manifest.get("partition_sha256") == _sha256_file(feature_path)
            and manifest.get("quality_scope") == "approved"
            and manifest.get("pit_grade") == PIT_GRADE
        )
    except (OSError, ValueError, KeyError):
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_value(*args: str) -> str | None:
    try:
        return (
            subprocess.run(
                ["git", *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            or None
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_json(value) + b"\n")
    os.replace(temporary, path)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _render_cube_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# Historical feature cube audit",
        "",
        f"- Slices: {audit['slice_count']:,}; errors/missing: {audit['error_count']:,}",
        f"- Cells: {audit['total_cells']:,}; available: {audit['available_cells']:,}; "
        f"unavailable: {audit['unavailable_cells']:,}; "
        f"availability {audit['availability_rate']:.2%}",
        f"- Entities per slice: min {audit['entity_count_min']:,}; "
        f"median {audit['entity_count_median']:,.1f}; max {audit['entity_count_max']:,}",
        "",
        "| As of | Entities | Cells | Availability |",
        "| --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {item['as_of_date']} | {item['entity_count']:,} | {item['cell_count']:,} | "
        f"{item['availability_rate']:.2%} |"
        for item in audit["cells_by_date"]
    )
    lines.extend(["", "## Entity arrivals and disappearances", ""])
    lines.extend(
        f"- {item['as_of_date']}: +{item['arrived']}, -{item['disappeared']}"
        for item in audit["entity_arrivals_disappearances"]
    )
    lines.extend(["", f"## Quality status changes ({len(audit['quality_status_changes'])})", ""])
    lines.extend(
        f"- {item['as_of_date']}: `{item['entity_id']}` {item['from']} → {item['to']}"
        for item in audit["quality_status_changes"]
    )
    lines.append("")
    return "\n".join(lines)
