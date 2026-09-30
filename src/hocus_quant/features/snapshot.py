"""Build and audit a point-in-time cross-sectional feature snapshot."""

from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from hocus_quant.features.factory import compute_entity_features
from hocus_quant.features.registry import FEATURE_REGISTRY

PARIS = ZoneInfo("Europe/Paris")
_LONG_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("entity_family", pa.string()),
        ("as_of_date", pa.date32()),
        ("feature_id", pa.string()),
        ("feature_value", pa.float64()),
        ("feature_status", pa.string()),
        ("unavailable_reason", pa.string()),
        ("window", pa.int32()),
        ("source_series", pa.string()),
        ("coverage_count", pa.int32()),
        ("coverage_ratio", pa.float64()),
        ("formula_version", pa.string()),
    ]
)


def build_feature_snapshot(
    *,
    as_of_date: date,
    output_dir: Path,
    data_dir: Path = Path("data"),
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate long/wide Parquet, an audit, and a small DuckDB catalog.

    Date D includes bars dated D when their `available_at` is no later than
    00:00 Europe/Paris on D+1. No labels, adjusted closes, or present-day index
    membership enter the computation.
    """
    started = time.perf_counter()
    db_path = data_dir / "research.duckdb"
    if not db_path.is_file():
        raise FileNotFoundError(f"research DuckDB does not exist: {db_path}")
    cutoff = datetime.combine(as_of_date + timedelta(days=1), datetime_time.min, tzinfo=PARIS)
    entities = _load_entities(db_path, as_of_date, cutoff)
    candidate_entity_count = len(entities)
    definitions = FEATURE_REGISTRY
    feature_index = {item.feature_id: index for index, item in enumerate(definitions)}
    matrix = np.full((len(entities), len(definitions)), np.nan, dtype=np.float64)
    counts = np.zeros((len(entities), len(definitions)), dtype=np.int32)
    ratios = np.zeros((len(entities), len(definitions)), dtype=np.float32)
    for entity_index, entity in enumerate(entities):
        computed = compute_entity_features(entity["observations"])
        for feature_id, (value, _status, count, ratio) in computed.items():
            column = feature_index[feature_id]
            if value is not None and math.isfinite(value):
                matrix[entity_index, column] = value
            counts[entity_index, column] = count
            ratios[entity_index, column] = ratio

    eligible = np.isfinite(matrix).any(axis=1)
    entities = [entity for index, entity in enumerate(entities) if eligible[index]]
    matrix = matrix[eligible]
    counts = counts[eligible]
    ratios = ratios[eligible]

    audit = _audit(
        entities,
        definitions,
        matrix,
        counts,
        ratios,
        as_of_date,
        cutoff,
        started,
        candidate_entity_count=candidate_entity_count,
    )
    if dry_run:
        audit["dry_run"] = True
        return audit

    output_dir.mkdir(parents=True, exist_ok=True)
    long_path = output_dir / "features_long.parquet"
    wide_path = output_dir / "features_wide.parquet"
    audit_path = output_dir / "audit.json"
    report_path = output_dir / "audit.md"
    _write_long(long_path, entities, definitions, matrix, counts, ratios, as_of_date)
    _write_wide(wide_path, entities, definitions, matrix, as_of_date)
    _write_catalog(output_dir / "features.duckdb", long_path, wide_path)
    audit["outputs"] = {
        "long_parquet": str(long_path),
        "wide_parquet": str(wide_path),
        "duckdb": str(output_dir / "features.duckdb"),
        "machine_audit": str(audit_path),
        "human_audit": str(report_path),
    }
    audit["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    _write_json(audit_path, audit)
    report_path.write_text(_render_report(audit), encoding="utf-8")
    return audit


def _load_entities(db_path: Path, as_of: date, cutoff: datetime) -> list[dict[str, Any]]:
    query = """
    WITH daily AS (
      SELECT 'abc-bourse-manual:equity:' || COALESCE(isin, instrument_id) AS entity_id,
             'equity' AS entity_family, 'market_daily' AS source_series,
             session_date, open, high, low, close, volume, available_at, retrieved_at,
             row_number() OVER (PARTITION BY instrument_id, session_date
               ORDER BY retrieved_at DESC, snapshot_id DESC) AS revision_rank
      FROM market_daily_history
      WHERE session_date <= ? AND available_at <= ?
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
      FROM market_series_history
      WHERE session_date <= ? AND available_at <= ?
    ), joined AS (
      SELECT * FROM daily WHERE revision_rank=1 AND close > 0
      UNION ALL
      SELECT * FROM supplemental WHERE revision_rank=1 AND close > 0
    )
    SELECT entity_id, entity_family, source_series, session_date, open, high, low,
           close, volume, available_at, retrieved_at
    FROM joined ORDER BY entity_id, session_date
    """
    entities: list[dict[str, Any]] = []
    current_id: str | None = None
    current: dict[str, Any] | None = None
    with duckdb.connect(str(db_path), read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.views"
            ).fetchall()
        }
        missing = {"market_daily_history", "market_series_history"} - tables
        if missing:
            raise ValueError(f"research DuckDB is missing market views: {sorted(missing)}")
        cursor = connection.execute(query, [as_of, cutoff, as_of, cutoff])
        names = [column[0] for column in cursor.description]
        while batch := cursor.fetchmany(20_000):
            for values in batch:
                row = dict(zip(names, values, strict=True))
                entity_id = str(row["entity_id"])
                if entity_id != current_id:
                    if current is not None:
                        entities.append(current)
                    current_id = entity_id
                    current = {
                        "entity_id": entity_id,
                        "entity_family": str(row["entity_family"]),
                        "source_series": str(row["source_series"]),
                        "observations": [],
                    }
                assert current is not None
                current["observations"].append(row)
        if current is not None:
            entities.append(current)
    return entities


def _audit(
    entities: list[dict[str, Any]],
    definitions: tuple[Any, ...],
    values: np.ndarray,
    counts: np.ndarray,
    ratios: np.ndarray,
    as_of: date,
    cutoff: datetime,
    started: float,
    *,
    candidate_entity_count: int,
) -> dict[str, Any]:
    available = np.isfinite(values)
    summaries: list[dict[str, Any]] = []
    constants: list[str] = []
    extreme: list[dict[str, Any]] = []
    for index, definition in enumerate(definitions):
        x = values[:, index]
        x = x[np.isfinite(x)]
        if not len(x):
            summaries.append(
                {
                    "feature_id": definition.feature_id,
                    "available_count": 0,
                    "min": None,
                    "p01": None,
                    "median": None,
                    "p99": None,
                    "max": None,
                }
            )
            continue
        q = np.quantile(x, [0, 0.01, 0.5, 0.99, 1])
        summaries.append(
            {
                "feature_id": definition.feature_id,
                "available_count": int(len(x)),
                "min": float(q[0]),
                "p01": float(q[1]),
                "median": float(q[2]),
                "p99": float(q[3]),
                "max": float(q[4]),
            }
        )
        if float(np.std(x)) <= 1e-12:
            constants.append(definition.feature_id)
        if len(x) >= 20 and (
            q[0] < q[1] - 20 * max(abs(q[1]), 1.0) or q[4] > q[3] + 20 * max(abs(q[3]), 1.0)
        ):
            extreme.append(
                {
                    "feature_id": definition.feature_id,
                    "min": float(q[0]),
                    "p01": float(q[1]),
                    "p99": float(q[3]),
                    "max": float(q[4]),
                }
            )
    windows: dict[str, dict[str, int]] = {}
    for window in sorted({item.window for item in definitions if item.window is not None}):
        columns = [i for i, item in enumerate(definitions) if item.window == window]
        block = available[:, columns]
        windows[str(window)] = {
            "cells": int(block.size),
            "available": int(block.sum()),
            "unavailable": int(block.size - block.sum()),
        }
    coverage_by_family: dict[str, int] = {}
    date_ranges_by_family: dict[str, dict[str, str]] = {}
    for entity in entities:
        fam = entity["entity_family"]
        coverage_by_family[fam] = coverage_by_family.get(fam, 0) + 1
        dates = [row["session_date"] for row in entity["observations"]]
        current_range = date_ranges_by_family.setdefault(
            fam, {"min": dates[0].isoformat(), "max": dates[-1].isoformat()}
        )
        current_range["min"] = min(current_range["min"], dates[0].isoformat())
        current_range["max"] = max(current_range["max"], dates[-1].isoformat())
    low_coverage = [
        {"entity_id": entity["entity_id"], "available_feature_ratio": float(np.mean(available[i]))}
        for i, entity in enumerate(entities)
        if np.mean(available[i]) < 0.15
    ]
    corr_pairs = _correlation_audit(values, definitions)
    status_counts = {
        "available": int(available.sum()),
        "unavailable": int(available.size - available.sum()),
    }
    late_retrievals = sum(
        1 for entity in entities for row in entity["observations"] if row["retrieved_at"] > cutoff
    )
    return {
        "spec": "SPEC-003",
        "as_of_date": as_of.isoformat(),
        "cutoff_timestamp": cutoff.isoformat(),
        "date_cutoff_semantics": "inclusive session date; cutoff is 00:00 Europe/Paris on D+1",
        "availability_filter": (
            "session_date <= as_of_date AND available_at <= next midnight Europe/Paris"
        ),
        "source_rows_retrieved_after_cutoff": late_retrievals,
        "historical_availability_assumption": (
            "Market bars use session-date + 1 day availability. ABC Bourse vintage/revision "
            "history is absent; later retrieval timestamps are reported and adjusted-price "
            "corporate-action PIT safety remains unverified."
        ),
        "excluded_inputs": [
            "adjusted_close (PIT status unverified)",
            "current labels",
            "current index membership",
        ],
        "entity_count": len(entities),
        "candidate_entity_count": candidate_entity_count,
        "ineligible_entity_count": candidate_entity_count - len(entities),
        "entity_count_by_family": coverage_by_family,
        "session_date_range_by_family": date_ranges_by_family,
        "feature_count": len(definitions),
        "feature_count_by_family": {
            family: sum(item.family == family for item in definitions)
            for family in sorted({item.family for item in definitions})
        },
        "total_cells": int(len(entities) * len(definitions)),
        "cell_status_counts": status_counts,
        "available_rate": float(available.mean()) if available.size else 0.0,
        "coverage_by_window": windows,
        "nan_count": 0,
        "infinity_count": 0,
        "null_feature_value_count": int(available.size - available.sum()),
        "constant_features": constants,
        "extreme_features": extreme,
        "duplicate_feature_ids": len(definitions) - len({item.feature_id for item in definitions}),
        "feature_distribution": summaries,
        "high_correlation_pairs": corr_pairs,
        "correlation_audit_note": (
            "Top 100 features by coverage, at most first 2,000 sorted entities; |r| >= 0.95."
        ),
        "low_coverage_entity_count": len(low_coverage),
        "low_coverage_entities_sample": low_coverage[:100],
        "source_observation_count": sum(len(entity["observations"]) for entity in entities),
        "source_observation_count_by_family": {
            family: sum(len(e["observations"]) for e in entities if e["entity_family"] == family)
            for family in sorted(coverage_by_family)
        },
        "elapsed_seconds_before_persist": round(time.perf_counter() - started, 3),
    }


def _correlation_audit(values: np.ndarray, definitions: tuple[Any, ...]) -> list[dict[str, Any]]:
    if values.shape[0] < 3:
        return []
    availability = np.isfinite(values).sum(axis=0)
    candidates = [i for i, count in enumerate(availability) if count >= 20]
    candidates.sort(key=lambda i: (-int(availability[i]), definitions[i].feature_id))
    candidates = candidates[:100]
    pairs: list[dict[str, Any]] = []
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            x = values[:2000, candidates[left]]
            y = values[:2000, candidates[right]]
            jointly_available = np.isfinite(x) & np.isfinite(y)
            if int(jointly_available.sum()) < 20:
                continue
            x_joint, y_joint = x[jointly_available], y[jointly_available]
            if float(np.std(x_joint)) <= 1e-12 or float(np.std(y_joint)) <= 1e-12:
                continue
            value = float(np.corrcoef(x_joint, y_joint)[0, 1])
            if math.isfinite(value) and abs(value) >= 0.95:
                pairs.append(
                    {
                        "feature_id_a": definitions[candidates[left]].feature_id,
                        "feature_id_b": definitions[candidates[right]].feature_id,
                        "correlation": value,
                    }
                )
    return sorted(pairs, key=lambda row: -abs(row["correlation"]))[:200]


def _write_long(
    path: Path,
    entities: list[dict[str, Any]],
    definitions: tuple[Any, ...],
    values: np.ndarray,
    counts: np.ndarray,
    ratios: np.ndarray,
    as_of: date,
) -> None:
    writer = pq.ParquetWriter(path, _LONG_SCHEMA, compression="zstd")
    try:
        chunk_size = max(1, 50_000 // max(len(definitions), 1))
        for start in range(0, len(entities), chunk_size):
            records: list[dict[str, Any]] = []
            stop = min(start + chunk_size, len(entities))
            for row_index in range(start, stop):
                entity = entities[row_index]
                for column, item in enumerate(definitions):
                    value = (
                        float(values[row_index, column])
                        if math.isfinite(values[row_index, column])
                        else None
                    )
                    reason = (
                        None
                        if value is not None
                        else (
                            "source_missing"
                            if (
                                item.family == "volume"
                                or item.metric
                                in {
                                    "obv_change_fraction",
                                    "mfi",
                                    "accumulation_distribution_fraction",
                                }
                            )
                            and counts[row_index, column] == 0
                            else "insufficient_history_or_undefined_formula"
                        )
                    )
                    records.append(
                        {
                            "entity_id": entity["entity_id"],
                            "entity_family": entity["entity_family"],
                            "as_of_date": as_of,
                            "feature_id": item.feature_id,
                            "feature_value": value,
                            "feature_status": "available" if value is not None else "unavailable",
                            "unavailable_reason": reason,
                            "window": item.window,
                            "source_series": item.source_series,
                            "coverage_count": int(counts[row_index, column]),
                            "coverage_ratio": float(ratios[row_index, column]),
                            "formula_version": item.formula_version,
                        }
                    )
            writer.write_table(pa.Table.from_pylist(records, schema=_LONG_SCHEMA))
    finally:
        writer.close()


def _write_wide(
    path: Path,
    entities: list[dict[str, Any]],
    definitions: tuple[Any, ...],
    values: np.ndarray,
    as_of: date,
) -> None:
    columns: dict[str, pa.Array] = {
        "entity_id": pa.array([item["entity_id"] for item in entities], type=pa.string()),
        "entity_family": pa.array([item["entity_family"] for item in entities], type=pa.string()),
        "as_of_date": pa.array([as_of] * len(entities), type=pa.date32()),
    }
    for column, definition in enumerate(definitions):
        x = values[:, column]
        columns[definition.feature_id] = pa.array(
            [float(item) if math.isfinite(item) else None for item in x], type=pa.float64()
        )
    pq.write_table(pa.table(columns), path, compression="zstd")


def _write_catalog(path: Path, long_path: Path, wide_path: Path) -> None:
    long_file = str(long_path.resolve()).replace("'", "''")
    wide_file = str(wide_path.resolve()).replace("'", "''")
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            f"CREATE OR REPLACE VIEW features_long AS SELECT * FROM read_parquet('{long_file}')"
        )
        connection.execute(
            f"CREATE OR REPLACE VIEW features_wide AS SELECT * FROM read_parquet('{wide_file}')"
        )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _render_report(audit: dict[str, Any]) -> str:
    lines = [
        "# SPEC-003 feature snapshot audit",
        "",
        f"- As-of date: `{audit['as_of_date']}`; cutoff instant `{audit['cutoff_timestamp']}`",
        f"- Entities: {audit['entity_count']}",
        f"- Features per entity: {audit['feature_count']}",
        f"- Cells: {audit['total_cells']:,}",
        f"- Available: {audit['cell_status_counts']['available']:,} "
        f"({audit['available_rate']:.2%})",
        f"- Unavailable: {audit['cell_status_counts']['unavailable']:,}",
        f"- NaN / infinite values: {audit['nan_count']} / {audit['infinity_count']}",
        f"- Duplicate feature IDs: {audit['duplicate_feature_ids']}",
        f"- Source observations: {audit['source_observation_count']:,}",
        f"- Rows retrieved after cutoff: {audit['source_rows_retrieved_after_cutoff']:,}",
        "",
        "## Entities by family",
        "",
        "| Family | Entities | Session start | Session end |",
        "| --- | ---: | --- | --- |",
    ]
    lines.extend(
        f"| {name} | {count:,} | {audit['session_date_range_by_family'][name]['min']} | "
        f"{audit['session_date_range_by_family'][name]['max']} |"
        for name, count in audit["entity_count_by_family"].items()
    )
    lines.extend(
        [
            "",
            "## Features by family",
            "",
            "| Family | Feature IDs |",
            "| --- | ---: |",
        ]
    )
    lines.extend(
        f"| {name} | {count:,} |" for name, count in audit["feature_count_by_family"].items()
    )
    lines.extend(
        [
            "",
            "## Coverage by window",
            "",
            "| Window | Available | Unavailable | Coverage |",
            "| ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {window} | {item['available']:,} | {item['unavailable']:,} | "
        f"{item['available'] / item['cells'] if item['cells'] else 0.0:.2%} |"
        for window, item in audit["coverage_by_window"].items()
    )
    lines.extend(
        [
            "",
            "## Feature distributions",
            "",
            "| Feature ID | n | Min | p01 | Median | p99 | Max |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in audit["feature_distribution"]:
        stats = [item[key] for key in ("min", "p01", "median", "p99", "max")]
        formatted = ["n/a" if value is None else f"{value:.8g}" for value in stats]
        lines.append(
            f"| `{item['feature_id']}` | {item['available_count']:,} | "
            + " | ".join(formatted)
            + " |"
        )
    lines.extend(["", f"## Constant features ({len(audit['constant_features'])})", ""])
    lines.extend(f"- `{feature_id}`" for feature_id in audit["constant_features"])
    lines.extend(
        [
            "",
            f"## Extreme features ({len(audit['extreme_features'])})",
            "",
            "Extremes are flagged when min/max lies more than 20× the larger of "
            "the corresponding 1st/99th percentile magnitude and 1 away from it.",
            "",
            "| Feature ID | Min | p01 | p99 | Max |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in audit["extreme_features"]:
        lines.append(
            f"| `{item['feature_id']}` | {item['min']:.8g} | {item['p01']:.8g} | "
            f"{item['p99']:.8g} | {item['max']:.8g} |"
        )
    lines.extend(
        [
            "",
            f"## High correlations ({len(audit['high_correlation_pairs'])})",
            "",
            "| Feature A | Feature B | r |",
            "| --- | --- | ---: |",
        ]
    )
    for pair in audit["high_correlation_pairs"]:
        lines.append(
            f"| `{pair['feature_id_a']}` | `{pair['feature_id_b']}` | {pair['correlation']:.6f} |"
        )
    lines.extend(
        [
            "",
            f"## Low-coverage entities ({audit['low_coverage_entity_count']})",
            "",
        ]
    )
    lines.extend(
        f"- `{item['entity_id']}`: {item['available_feature_ratio']:.2%} features available"
        for item in audit["low_coverage_entities_sample"]
    )
    lines.extend(
        [
            "",
            "## Limits",
            "",
            f"- Late-retrieved included rows: {audit['source_rows_retrieved_after_cutoff']:,}. "
            "D+1 availability is an unverified ABC Bourse backfill assumption.",
            "- Supplied ABC Bourse corporate-action adjustment vintages are unverified.",
            "- No point-in-time universe membership is inferred; current labels are excluded.",
            "- Technical formulas are documented in `docs/FEATURES.md`.",
            "",
        ]
    )
    return "\n".join(lines)
