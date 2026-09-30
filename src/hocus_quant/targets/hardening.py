"""Coverage hardening, extreme-return diagnostics and research-ready target export."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

EXTREME_RETURN_ABS = 0.9
SPLIT_FACTORS = (2.0, 3.0, 4.0, 5.0, 10.0)
SCALE_FACTORS = (0.01, 0.1, 10.0, 100.0)
UNRESOLVED_CLASSES = {
    "likely_split_or_reverse_split",
    "likely_scale_change",
    "source_quality_issue",
    "benchmark_issue",
    "thin_or_discontinuous_series",
    "insufficient_evidence",
}


def harden_target_set(*, output_dir: Path, data_dir: Path = Path("data")) -> dict[str, Any]:
    """Annotate extreme target rows, classify events and export research-ready labels."""
    db_path = data_dir / "research.duckdb"
    target_paths = sorted(output_dir.glob("as_of_date=*/targets.parquet"))
    if not target_paths and (output_dir / "targets.parquet").is_file():
        target_paths = [output_dir / "targets.parquet"]
    if not target_paths:
        raise FileNotFoundError(f"no target Parquet files in {output_dir}")

    target_glob = str((output_dir / "as_of_date=*/targets.parquet").resolve())
    if len(target_paths) == 1 and target_paths[0].parent == output_dir:
        target_glob = str(target_paths[0].resolve())
    with duckdb.connect() as connection:
        extreme_rows = _fetch_extreme_rows(connection, target_glob)
        coverage_rows = _coverage_by_horizon(connection, target_glob)
        cutoff_rows = _cutoff_coverage(connection, target_glob)
        cohort_rows = _usable_cohorts(connection, target_glob)
    weekly_limits = _last_possible_weekly_cutoffs(db_path)
    paths = _load_price_paths(db_path, extreme_rows)

    event_rows, links = _classify_extremes(extreme_rows, paths)
    research_ready_count = 0
    raw_count = 0
    excluded_available = 0
    by_cutoff: list[dict[str, Any]] = []
    for target_path in target_paths:
        table = pq.read_table(target_path)
        columns = {name: table[name].to_pylist() for name in table.column_names}
        event_ids: list[str | None] = []
        classifications: list[str | None] = []
        flags_column: list[list[str] | None] = []
        research_ready: list[bool] = []
        for entity_id, cutoff, horizon, status in zip(
            columns["entity_id"],
            columns["as_of_date"],
            columns["horizon"],
            columns["target_status"],
            strict=True,
        ):
            metadata = links.get((entity_id, cutoff, horizon), {})
            flags = sorted(metadata.get("flags", set()))
            event_ids.append(";".join(sorted(metadata.get("event_ids", set()))) or None)
            classifications.append(";".join(sorted(metadata.get("classifications", set()))) or None)
            flags_column.append(flags or None)
            ready = _is_research_ready(status, set(flags))
            research_ready.append(ready)
            raw_count += 1
            research_ready_count += int(ready)
            excluded_available += int(status == "available" and not ready)

        for name, values, arrow_type in (
            ("event_id", event_ids, pa.string()),
            ("extreme_classification", classifications, pa.string()),
            ("extreme_flags", flags_column, pa.list_(pa.string())),
            ("research_ready", research_ready, pa.bool_()),
        ):
            index = table.schema.get_field_index(name)
            table = table.set_column(index, name, pa.array(values, type=arrow_type))
        temporary = target_path.with_suffix(".parquet.tmp")
        pq.write_table(table, temporary, compression="zstd")
        os.replace(temporary, target_path)
        ready_path = target_path.parent / "targets_research_ready.parquet"
        ready_table = table.filter(pa.array(research_ready, type=pa.bool_()))
        ready_temporary = ready_path.with_suffix(".parquet.tmp")
        pq.write_table(ready_table, ready_temporary, compression="zstd")
        os.replace(ready_temporary, ready_path)

        manifest_path = target_path.parent / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["target_parquet_sha256"] = _sha256_file(target_path)
            manifest["target_parquet_bytes"] = target_path.stat().st_size
            manifest["research_ready_parquet_sha256"] = _sha256_file(ready_path)
            manifest["research_ready_target_row_count"] = ready_table.num_rows
            _write_json(manifest_path, manifest)
        if target_path.parent == output_dir:
            _refresh_catalog(output_dir, target_path, ready_path)
        by_cutoff.append(
            {
                "as_of_date": _cutoff_from_path(target_path).isoformat(),
                "raw_target_rows": table.num_rows,
                "research_ready_rows": ready_table.num_rows,
                "available_rows_excluded_for_unresolved_extremes": sum(
                    1
                    for index, status in enumerate(columns["target_status"])
                    if status == "available" and not research_ready[index]
                ),
            }
        )

    events = _merge_event_rows(event_rows)
    classification_counts = Counter(event["classification"] for event in events)
    target_row_count = len(extreme_rows)
    unique_entities = {row["entity_id"] for row in extreme_rows}
    unresolved_events = [
        event for event in events if UNRESOLVED_CLASSES.intersection(event["flags"])
    ]
    audit = {
        "schema_version": "SPEC-005R/1.0.0",
        "target_paths": [str(path) for path in target_paths],
        "extreme_threshold_abs_return": EXTREME_RETURN_ABS,
        "extreme_target_rows": target_row_count,
        "extreme_target_rows_by_family": dict(
            Counter(row["target_family"] for row in extreme_rows)
        ),
        "unique_events": len(events),
        "entities_with_extreme_targets": len(unique_entities),
        "events_by_classification": dict(classification_counts),
        "events_classified_plausible": classification_counts.get("plausible_market_move", 0),
        "events_suspected_split_or_scale_or_source": sum(
            classification_counts.get(name, 0)
            for name in (
                "likely_split_or_reverse_split",
                "likely_scale_change",
                "source_quality_issue",
            )
        ),
        "unresolved_event_count": len(unresolved_events),
        "available_target_rows_excluded_for_unresolved_extremes": excluded_available,
        "raw_target_rows": raw_count,
        "research_ready_target_rows": research_ready_count,
        "target_rows_excluded_from_research_ready": raw_count - research_ready_count,
        "research_ready_rules": {
            "must_be_available": True,
            "right_censored_excluded": True,
            "future_quality_review_or_quarantine_excluded": True,
            "unresolved_extreme_classes": sorted(UNRESOLVED_CLASSES),
            "plausible_market_move_retained": True,
            "winsorization": False,
        },
        "availability_by_horizon": coverage_rows,
        "availability_by_cutoff_and_horizon": cutoff_rows,
        "usable_cutoff_cohorts_by_horizon": cohort_rows,
        "last_possible_weekly_cutoff_by_horizon": weekly_limits,
        "relative_benchmark_coverage_by_horizon": [
            item for item in coverage_rows if item["target_family"] == "return_rel"
        ],
        "cutoffs": by_cutoff,
        "events": events,
        "pit_grade": "reconstructed",
        "strict_pit_claimed": False,
    }
    _write_json(output_dir / "target_hardening_audit.json", audit)
    (output_dir / "target_hardening_audit.md").write_text(_render_audit(audit), encoding="utf-8")
    _refresh_root_catalog(output_dir)
    return audit


def _fetch_extreme_rows(
    connection: duckdb.DuckDBPyConnection, target_glob: str
) -> list[dict[str, Any]]:
    escaped = target_glob.replace("'", "''")
    cursor = connection.execute(
        f"""SELECT entity_id, entity_family, as_of_date, target_id, target_family,
            horizon, candidate_value, target_status, unavailable_reason, start_date,
            target_end_date, start_price, end_price, benchmark_id, benchmark_start_date,
            benchmark_end_date, benchmark_future_observation_count,
            quality_status_at_cutoff, future_quality_reason
          FROM read_parquet('{escaped}', union_by_name=true)
          WHERE target_family IN ('return_abs','return_rel')
            AND candidate_value IS NOT NULL AND abs(candidate_value) >= {EXTREME_RETURN_ABS}
          ORDER BY entity_id, as_of_date, horizon, target_family"""
    )
    names = [field[0] for field in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _coverage_by_horizon(
    connection: duckdb.DuckDBPyConnection, target_glob: str
) -> list[dict[str, Any]]:
    escaped = target_glob.replace("'", "''")
    rows = connection.execute(
        f"""SELECT target_family, horizon, count(*) AS candidates,
            count(*) FILTER (WHERE target_status='available') AS available,
            count(*) FILTER (WHERE target_status='right_censored_end_of_sample') AS censored,
            count(*) FILTER (WHERE target_status='insufficient_future_history') AS insufficient,
            count(*) FILTER (WHERE target_status='future_quality_review') AS quality_review,
            count(*) FILTER (WHERE target_status='future_quality_quarantined') AS quarantined,
            count(*) FILTER (WHERE target_status='benchmark_not_defined') AS benchmark_not_defined,
            count(*) FILTER (
              WHERE target_status='benchmark_defined_but_unavailable')
              AS benchmark_defined_unavailable,
            count(*) FILTER (WHERE benchmark_id IS NOT NULL) AS benchmark_mapped,
            count(*) FILTER (WHERE benchmark_id IS NOT NULL AND
              target_status='right_censored_end_of_sample') AS mapped_censored
          FROM read_parquet('{escaped}', union_by_name=true)
          WHERE target_family IN ('return_abs','return_rel') GROUP BY ALL ORDER BY ALL"""
    ).fetchall()
    result = []
    for row in rows:
        (
            family,
            horizon,
            candidates,
            available,
            censored,
            insufficient,
            review,
            quarantine,
            not_defined,
            defined_unavailable,
            mapped,
            mapped_censored,
        ) = row
        observable = candidates - censored
        mapped_observable = mapped - mapped_censored if family == "return_rel" else 0
        result.append(
            {
                "target_family": family,
                "horizon": horizon,
                "candidate_rows": candidates,
                "available": available,
                "unavailable_total": candidates - available,
                "right_censored_end_of_sample": censored,
                "insufficient_future_history": insufficient,
                "future_quality_review": review,
                "future_quality_quarantined": quarantine,
                "benchmark_not_defined": not_defined,
                "benchmark_defined_but_unavailable": defined_unavailable,
                "benchmark_mapped_candidates": mapped,
                "availability_global": available / candidates if candidates else 0.0,
                "observable_candidate_rows": observable,
                "availability_excluding_censoring": available / observable if observable else 0.0,
                "mapped_observable_candidate_rows": mapped_observable,
                "availability_among_mapped_observable": (
                    available / mapped_observable if mapped_observable else 0.0
                ),
            }
        )
    return result


def _cutoff_coverage(
    connection: duckdb.DuckDBPyConnection, target_glob: str
) -> list[dict[str, Any]]:
    escaped = target_glob.replace("'", "''")
    rows = connection.execute(
        f"""SELECT as_of_date,horizon,count(DISTINCT entity_id),count(*),
            count(*) FILTER (WHERE target_status='available'),
            count(*) FILTER (WHERE target_status='right_censored_end_of_sample'),
            count(*) FILTER (WHERE target_status='future_quality_review'),
            count(*) FILTER (WHERE target_status='future_quality_quarantined'),
            count(*) FILTER (WHERE target_status='insufficient_future_history'),
            count(*) FILTER (WHERE target_status IN
              ('benchmark_not_defined','benchmark_defined_but_unavailable'))
          FROM read_parquet('{escaped}',union_by_name=true)
          WHERE target_family='return_abs' GROUP BY ALL ORDER BY ALL"""
    ).fetchall()
    return [
        {
            "as_of_date": row[0].isoformat(),
            "horizon": row[1],
            "entities": row[2],
            "candidate_rows": row[3],
            "available": row[4],
            "availability_pct": row[4] / row[3] if row[3] else 0.0,
            "right_censored_end_of_sample": row[5],
            "future_quality_review": row[6],
            "future_quality_quarantined": row[7],
            "insufficient_future_history": row[8],
            "benchmark_unavailable": row[9],
        }
        for row in rows
    ]


def _usable_cohorts(
    connection: duckdb.DuckDBPyConnection, target_glob: str
) -> list[dict[str, Any]]:
    escaped = target_glob.replace("'", "''")
    rows = connection.execute(
        f"""SELECT horizon,min(as_of_date),max(as_of_date),count(DISTINCT as_of_date),count(*)
          FROM read_parquet('{escaped}',union_by_name=true)
          WHERE target_family='return_abs' AND target_status='available'
          GROUP BY horizon ORDER BY horizon"""
    ).fetchall()
    return [
        {
            "horizon": row[0],
            "first_usable_cutoff": row[1].isoformat(),
            "last_usable_cutoff": row[2].isoformat(),
            "cutoff_count": row[3],
            "available_entity_cutoff_rows": row[4],
        }
        for row in rows
    ]


def _last_possible_weekly_cutoffs(db_path: Path) -> list[dict[str, Any]]:
    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.execute(
            """SELECT session_date FROM (
                 SELECT session_date FROM market_daily_history
                 UNION
                 SELECT session_date FROM market_series_history
               ) ORDER BY session_date"""
        ).fetchall()
    sessions = [row[0] for row in rows]
    result = []
    for horizon in (5, 10, 20, 60, 120):
        index = len(sessions) - horizon - 1
        possible_session_cutoff = sessions[index] if index >= 0 else None
        weekly_cutoff = None
        if possible_session_cutoff is not None:
            days_since_friday = (possible_session_cutoff.weekday() - 4) % 7
            weekly_cutoff = possible_session_cutoff.fromordinal(
                possible_session_cutoff.toordinal() - days_since_friday
            )
        result.append(
            {
                "horizon": horizon,
                "last_possible_weekly_cutoff": (
                    weekly_cutoff.isoformat() if weekly_cutoff is not None else None
                ),
                "cutoff_basis": "latest_global_session_date_with_h_future_sessions",
            }
        )
    return result


def _load_price_paths(
    db_path: Path,
    extreme_rows: list[dict[str, Any]],
) -> dict[tuple[str, date, date], list[dict[str, Any]]]:
    windows: set[tuple[str, date, date]] = set()
    for row in extreme_rows:
        if row["start_date"] and row["target_end_date"]:
            windows.add((row["entity_id"], row["start_date"], row["target_end_date"]))
        if row["benchmark_id"] and row["benchmark_start_date"] and row["benchmark_end_date"]:
            windows.add(
                (
                    row["benchmark_id"],
                    row["benchmark_start_date"],
                    row["benchmark_end_date"],
                )
            )
    if not windows:
        return {}
    window_table = pa.table(
        {
            "entity_id": [item[0] for item in sorted(windows)],
            "start_date": [item[1] for item in sorted(windows)],
            "end_date": [item[2] for item in sorted(windows)],
        },
        schema=pa.schema(
            [
                ("entity_id", pa.string()),
                ("start_date", pa.date32()),
                ("end_date", pa.date32()),
            ]
        ),
    )
    with duckdb.connect(str(db_path), read_only=True) as source:
        source.register("extreme_windows", window_table)
        query = """WITH bars AS (
            SELECT 'abc-bourse-manual:equity:' || COALESCE(isin, instrument_id) AS entity_id,
                   session_date, open, high, low, close, volume, available_at, retrieved_at,
                   row_number() OVER (PARTITION BY instrument_id, session_date
                     ORDER BY retrieved_at DESC, snapshot_id DESC) AS revision_rank
            FROM market_daily_history
            UNION ALL
            SELECT 'abc-bourse-manual:' || universe_id || ':' || series_id AS entity_id,
                   session_date, open, high, low, close, volume, available_at, retrieved_at,
                   row_number() OVER (PARTITION BY universe_id, series_id, session_date
                     ORDER BY retrieved_at DESC, snapshot_checksum DESC) AS revision_rank
            FROM market_series_history
          )
          SELECT w.entity_id AS requested_entity_id, w.start_date, w.end_date,
                 b.session_date, b.open, b.high, b.low, b.close, b.volume,
                 b.available_at, b.retrieved_at
          FROM extreme_windows w JOIN bars b USING(entity_id)
          WHERE b.revision_rank=1 AND b.session_date BETWEEN w.start_date AND w.end_date
          ORDER BY w.entity_id, w.start_date, w.end_date, b.session_date"""
        cursor = source.execute(query)
        names = [field[0] for field in cursor.description]
        result: dict[tuple[str, date, date], list[dict[str, Any]]] = defaultdict(list)
        for raw in cursor.fetchall():
            row = dict(zip(names, raw, strict=True))
            key = (row.pop("requested_entity_id"), row.pop("start_date"), row.pop("end_date"))
            result[key].append(row)
    return dict(result)


def _classify_extremes(
    extreme_rows: list[dict[str, Any]],
    paths: dict[tuple[str, date, date], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, date, int], dict[str, set[str]]]]:
    events: list[dict[str, Any]] = []
    links: dict[tuple[str, date, int], dict[str, set[str]]] = defaultdict(
        lambda: {"event_ids": set(), "flags": set(), "classifications": set()}
    )
    for row in extreme_rows:
        asset_path = _path_for(
            row["entity_id"], row.get("start_date"), row.get("target_end_date"), paths
        )
        benchmark_path = _path_for(
            row.get("benchmark_id"),
            row.get("benchmark_start_date"),
            row.get("benchmark_end_date"),
            paths,
        )
        transitions = _transitions(asset_path)
        flags: set[str] = set()
        structural = [
            item for item in transitions if item["near_split_factor"] or item["near_scale_factor"]
        ]
        hard_source_issue = any(
            item["high"] is not None and item["low"] is not None and item["high"] < item["low"]
            for item in asset_path
        )
        if hard_source_issue or row["target_status"] == "future_quality_quarantined":
            flags.add("source_quality_issue")
        if any(item["near_scale_factor"] for item in structural):
            flags.add("likely_scale_change")
        if any(item["near_split_factor"] and item["inverse_volume_match"] for item in structural):
            flags.add("likely_split_or_reverse_split")
        if row["target_family"] == "return_rel" and row.get("benchmark_id") and not benchmark_path:
            flags.add("benchmark_issue")
        if len(asset_path) < int(row["horizon"]) + 1:
            flags.add("thin_or_discontinuous_series")
        gaps = [
            (right["session_date"] - left["session_date"]).days
            for left, right in zip(asset_path, asset_path[1:], strict=False)
        ]
        if gaps and max(gaps) > 14:
            flags.add("thin_or_discontinuous_series")
        annualized = _annualized_volatility(asset_path)
        if row["entity_family"] == "crypto" and annualized is not None and annualized >= 1.0:
            flags.add("high_volatility_asset")
        if not flags.intersection(UNRESOLVED_CLASSES):
            if row["target_status"] == "available":
                flags.add("plausible_market_move")
            else:
                flags.add("insufficient_evidence")
        driver = _event_driver(row, transitions, asset_path)
        event_id = f"{driver[0]}:{driver[1]}:{driver[2]}"
        primary = _primary_classification(flags)
        link_key = (row["entity_id"], row["as_of_date"], int(row["horizon"]))
        links[link_key]["event_ids"].add(event_id)
        links[link_key]["flags"].update(flags)
        links[link_key]["classifications"].add(primary)
        events.append(
            {
                "event_id": event_id,
                "entity_id": row["entity_id"],
                "entity_family": row["entity_family"],
                "as_of_date": row["as_of_date"].isoformat(),
                "horizon": int(row["horizon"]),
                "target_id": row["target_id"],
                "target_family": row["target_family"],
                "return_abs": row["candidate_value"]
                if row["target_family"] == "return_abs"
                else None,
                "return_rel": row["candidate_value"]
                if row["target_family"] == "return_rel"
                else None,
                "start_price": row["start_price"],
                "end_price": row["end_price"],
                "price_path": [_clean_bar(item) for item in asset_path],
                "benchmark_id": row.get("benchmark_id"),
                "benchmark_price_path": [_clean_bar(item) for item in benchmark_path],
                "quality_status_at_cutoff": row.get("quality_status_at_cutoff"),
                "future_quality_status": row["target_status"],
                "future_quality_reason": row.get("future_quality_reason"),
                "source_transitions": transitions,
                "flags": sorted(flags),
                "classification": primary,
            }
        )
    return events, links


def _path_for(
    entity_id: str | None,
    start_date: date | None,
    end_date: date | None,
    paths: dict[tuple[str, date, date], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if entity_id is None or start_date is None or end_date is None:
        return []
    return paths.get((entity_id, start_date, end_date), [])


def _transitions(path: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for left, right in zip(path, path[1:], strict=False):
        left_close = _number(left.get("close"))
        right_close = _number(right.get("close"))
        if not left_close or not right_close or left_close <= 0 or right_close <= 0:
            continue
        ratio = right_close / left_close
        volume_left, volume_right = _number(left.get("volume")), _number(right.get("volume"))
        volume_ratio = (
            volume_right / volume_left if volume_left and volume_right is not None else None
        )
        split = _near_factor(ratio, SPLIT_FACTORS)
        scale = _near_factor(ratio, SCALE_FACTORS)
        transitions.append(
            {
                "from_date": left["session_date"].isoformat(),
                "to_date": right["session_date"].isoformat(),
                "from_close": left_close,
                "to_close": right_close,
                "close_ratio": ratio,
                "absolute_return": ratio - 1.0,
                "volume_ratio": volume_ratio,
                "near_split_factor": split,
                "near_scale_factor": scale,
                "inverse_volume_match": (
                    volume_ratio is not None and abs(volume_ratio * ratio - 1.0) <= 0.25
                ),
            }
        )
    return transitions


def _event_driver(
    row: dict[str, Any], transitions: list[dict[str, Any]], path: list[dict[str, Any]]
) -> tuple[str, str, str]:
    candidates = [item for item in transitions if abs(item["absolute_return"]) >= 0.2]
    if not candidates:
        candidates = transitions
    if candidates:
        largest = max(candidates, key=lambda item: abs(item["absolute_return"]))
        return row["entity_id"], largest["from_date"], largest["to_date"]
    if path:
        return (
            row["entity_id"],
            path[0]["session_date"].isoformat(),
            path[-1]["session_date"].isoformat(),
        )
    return row["entity_id"], row["as_of_date"].isoformat(), f"h{row['horizon']}"


def _near_factor(ratio: float, factors: tuple[float, ...]) -> float | None:
    candidates = (ratio, 1.0 / ratio)
    for candidate in candidates:
        for factor in factors:
            if abs(candidate / factor - 1.0) <= 0.02:
                return factor
    return None


def _annualized_volatility(path: list[dict[str, Any]]) -> float | None:
    closes = [_number(item.get("close")) for item in path]
    valid = [value for value in closes if value is not None and value > 0]
    if len(valid) < 3:
        return None
    import numpy as np

    returns = np.diff(np.log(valid))
    return float(np.std(returns, ddof=1) * math.sqrt(252.0))


def _primary_classification(flags: set[str]) -> str:
    priority = (
        "likely_split_or_reverse_split",
        "likely_scale_change",
        "source_quality_issue",
        "benchmark_issue",
        "thin_or_discontinuous_series",
        "high_volatility_asset",
        "plausible_market_move",
        "insufficient_evidence",
    )
    return next((item for item in priority if item in flags), "insufficient_evidence")


def _is_research_ready(status: str, flags: set[str]) -> bool:
    return status == "available" and not UNRESOLVED_CLASSES.intersection(flags)


def _merge_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = merged.setdefault(
            row["event_id"],
            {
                "event_id": row["event_id"],
                "entity_id": row["entity_id"],
                "entity_family": row["entity_family"],
                "flags": set(),
                "classifications": set(),
                "cutoffs": set(),
                "horizons": set(),
                "target_rows": [],
                "price_path": row["price_path"],
                "benchmark_id": row["benchmark_id"],
                "benchmark_price_path": row["benchmark_price_path"],
                "source_transitions": row["source_transitions"],
            },
        )
        current["flags"].update(row["flags"])
        current["classifications"].add(row["classification"])
        current["cutoffs"].add(row["as_of_date"])
        current["horizons"].add(row["horizon"])
        current["target_rows"].append(
            {
                "target_id": row["target_id"],
                "target_family": row["target_family"],
                "cutoff": row["as_of_date"],
                "horizon": row["horizon"],
                "return_abs": row["return_abs"],
                "return_rel": row["return_rel"],
                "start_price": row["start_price"],
                "end_price": row["end_price"],
                "future_quality_status": row["future_quality_status"],
                "quality_status_at_cutoff": row["quality_status_at_cutoff"],
                "future_quality_reason": row["future_quality_reason"],
            }
        )
    results = []
    for value in merged.values():
        flags = sorted(value["flags"])
        results.append(
            {
                **value,
                "flags": flags,
                "classifications": sorted(value["classifications"]),
                "classification": _primary_classification(set(flags)),
                "cutoffs": sorted(value["cutoffs"]),
                "horizons": sorted(value["horizons"]),
                "target_rows": value["target_rows"],
            }
        )
    return sorted(results, key=lambda item: item["event_id"])


def _clean_bar(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in row.items()
    }


def _cutoff_from_path(path: Path) -> date:
    name = path.parent.name
    return date.fromisoformat(name.split("=", 1)[1]) if name.startswith("as_of_date=") else date.min


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _refresh_catalog(root: Path, raw_path: Path, ready_path: Path) -> None:
    with duckdb.connect(str(root / "target_catalog.duckdb")) as connection:
        raw = str(raw_path.resolve()).replace("'", "''")
        ready = str(ready_path.resolve()).replace("'", "''")
        connection.execute(f"CREATE OR REPLACE VIEW targets AS SELECT * FROM read_parquet('{raw}')")
        connection.execute(
            "CREATE OR REPLACE VIEW targets_research_ready AS SELECT * FROM "
            f"read_parquet('{ready}')"
        )


def _refresh_root_catalog(root: Path) -> None:
    with duckdb.connect(str(root / "target_catalog.duckdb")) as connection:
        raw = str((root / "as_of_date=*/targets.parquet").resolve()).replace("'", "''")
        ready = str((root / "as_of_date=*/targets_research_ready.parquet").resolve()).replace(
            "'", "''"
        )
        if any(root.glob("as_of_date=*/targets.parquet")):
            connection.execute(
                "CREATE OR REPLACE VIEW targets AS SELECT * FROM "
                f"read_parquet('{raw}', union_by_name=true)"
            )
            connection.execute(
                "CREATE OR REPLACE VIEW targets_research_ready AS SELECT * FROM "
                f"read_parquet('{ready}', union_by_name=true)"
            )


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# SPEC-005R target hardening audit",
        "",
        f"- Extreme target rows (>|{EXTREME_RETURN_ABS:.0%}|): {audit['extreme_target_rows']:,}",
        f"- Unique logical events: {audit['unique_events']:,}",
        f"- Entities with extreme targets: {audit['entities_with_extreme_targets']:,}",
        f"- Research-ready rows: {audit['research_ready_target_rows']:,} / "
        f"{audit['raw_target_rows']:,}",
        f"- Available rows excluded for unresolved extremes: "
        f"{audit['available_target_rows_excluded_for_unresolved_extremes']:,}",
        "",
        "## Extreme-event classifications",
        "",
    ]
    lines.extend(
        f"- {name}: {count:,}" for name, count in audit["events_by_classification"].items()
    )
    lines.extend(
        [
            "",
            "## Absolute-return availability",
            "",
            "| H | Global | Excluding censoring | Quality review | Quarantined | "
            "Insufficient series | Last usable cutoff |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    absolute_by_horizon = {
        item["horizon"]: item
        for item in audit["availability_by_horizon"]
        if item["target_family"] == "return_abs"
    }
    cohorts = {item["horizon"]: item for item in audit["usable_cutoff_cohorts_by_horizon"]}
    lines.extend(
        f"| {horizon} | {absolute_by_horizon[horizon]['availability_global']:.2%} | "
        f"{absolute_by_horizon[horizon]['availability_excluding_censoring']:.2%} | "
        f"{absolute_by_horizon[horizon]['future_quality_review']:,} | "
        f"{absolute_by_horizon[horizon]['future_quality_quarantined']:,} | "
        f"{absolute_by_horizon[horizon]['insufficient_future_history']:,} | "
        f"{cohorts[horizon]['last_usable_cutoff'] if horizon in cohorts else 'none'} |"
        for horizon in sorted(absolute_by_horizon)
    )
    lines.extend(
        [
            "",
            "Weekly cutoff boundary from the latest global session (theoretical; "
            "not materialized in this sparse run):",
            "",
            "| H | Last possible weekly cutoff |",
            "| ---: | --- |",
        ]
    )
    lines.extend(
        f"| {item['horizon']} | {item['last_possible_weekly_cutoff'] or 'none'} |"
        for item in audit["last_possible_weekly_cutoff_by_horizon"]
    )
    lines.extend(
        [
            "",
            "## Relative-return benchmark coverage",
            "",
            "| H | Global | Benchmark mapped | Mapped + observable availability | "
            "Benchmark not defined | Defined, unavailable |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    relative_by_horizon = {
        item["horizon"]: item for item in audit["relative_benchmark_coverage_by_horizon"]
    }
    lines.extend(
        f"| {horizon} | {item['availability_global']:.2%} | "
        f"{item['benchmark_mapped_candidates'] / item['candidate_rows']:.2%} | "
        f"{item['availability_among_mapped_observable']:.2%} | "
        f"{item['benchmark_not_defined']:,} | {item['benchmark_defined_but_unavailable']:,} |"
        for horizon, item in sorted(relative_by_horizon.items())
    )
    lines.extend(
        [
            "",
            "## Horizon cohorts",
            "",
            "| H | First usable | Last usable | Cutoffs | Available entity-cutoff rows |",
            "| ---: | --- | --- | ---: | ---: |",
        ]
    )
    lines.extend(
        f"| {item['horizon']} | {item['first_usable_cutoff']} | {item['last_usable_cutoff']} | "
        f"{item['cutoff_count']} | {item['available_entity_cutoff_rows']:,} |"
        for item in audit.get("usable_cutoff_cohorts_by_horizon", [])
    )
    return "\n".join(lines) + "\n"
