"""New development matrices; read-only market source, past-only features and eligibility."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import polars as pl

from hocus_quant.analysis.candidate_lock import verify_lock
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.features import factory as f
from hocus_quant.features.registry import FEATURE_REGISTRY
from hocus_quant.model_lab.targets import (
    FAMILIES,
    HORIZONS,
    future_path,
    rank_targets,
    registry_document,
)
from hocus_quant.validation.market_quality import assess_series


def feature_sets(lock: dict[str, Any]) -> dict[str, list[str]]:
    verify_lock(lock)
    return {
        tier: [r["canonical_feature"] for r in lock["candidates"] if r[flag]]
        for tier, flag in [("strict", "strict_candidates"), ("strong", "strong_sign_candidates")]
    }


def locked_features(rows: list[dict[str, Any]], ids: list[str]) -> dict[str, float | None]:
    """Evaluate a subset using the unchanged original formula helpers; parity tested."""
    rows = sorted(
        [r for r in rows if f._valid_close(r.get("close"))], key=lambda r: r["session_date"]
    )
    if not rows:
        return dict.fromkeys(ids)
    close = np.asarray([r["close"] for r in rows], dtype=float)
    levels = {n: f._array(rows, n) for n in ["open", "high", "low"]}
    levels["close"] = close
    volumes = f._array(rows, "volume")
    logs = {n: np.log(np.where(x > 0, x, np.nan)) for n, x in levels.items()}
    simple, log = f._returns(close, logarithmic=False), f._returns(close, logarithmic=True)
    structure = f._ohlc_series(levels["open"], levels["high"], levels["low"], close)
    result: dict[str, float | None] = {}
    definitions = {r.feature_id: r for r in FEATURE_REGISTRY}
    for name in ids:
        item = definitions[name]
        w = item.window or len(rows)
        count = 0
        value: float | None
        if item.family == "distribution":
            sample = f._tail(levels[item.source_series], w)
            value, count = f._level_stat(item.metric, sample), int(np.isfinite(sample).sum())
        elif item.family == "trend":
            sample = f._tail(logs[item.source_series.removeprefix("log_")], w)
            value, count = (
                f._trend_stat(item.metric, sample, logarithmic=True),
                int(np.isfinite(sample).sum()),
            )
        elif item.family == "returns":
            sample = f._tail(log if item.source_series == "close_log_return" else simple, w)
            value, count = f._return_stat(item.metric, sample), int(np.isfinite(sample).sum())
        elif item.family == "ohlc":
            metric = item.feature_id.split(".relation.", 1)[1].split(".w", 1)[0]
            sample = f._tail(structure[metric], w)
            if metric in {"positive_share", "negative_share"}:
                sample = simple[-w:]
                value = f._finite_mean(
                    (sample > 0 if metric == "positive_share" else sample < 0).astype(float)
                )
            elif metric == "gap_frequency":
                value = f._finite_mean((np.abs(sample) > 0.1).astype(float))
            else:
                value = f._finite_mean(sample)
            count = int(np.isfinite(sample).sum())
        elif item.family == "volume":
            sample = f._tail(volumes, w)
            x = sample[np.isfinite(sample) & (sample >= 0)]
            count = len(x)
            value = float(x[-1] / x.mean() - 1) if count == w and x.mean() > 0 else None
        else:
            value, count = f._technical(
                item.metric,
                levels["open"],
                levels["high"],
                levels["low"],
                close,
                volumes,
                item.window or 1,
            )
        result[name] = (
            float(value)
            if value is not None and count >= item.minimum_observations and math.isfinite(value)
            else None
        )
    return result


def split_assignment(
    cutoff: date, end: date | None, horizon: int, calendar: list[date], config: dict[str, Any]
) -> tuple[str, str]:
    """H-session embargo plus actual outcome-end test; no boundary crossing accepted."""
    for split in ["train", "validation", "test"]:
        lo, hi = (
            date.fromisoformat(config[f"{split}_start"]),
            date.fromisoformat(config[f"{split}_end"]),
        )
        if lo <= cutoff <= hi:
            position = calendar.index(cutoff)
            boundary = sum(d <= hi for d in calendar) - 1
            if position + horizon > boundary:
                return "purged", f"{split}:H{horizon}_session_embargo"
            if end is None:
                return split, "future_missing"
            if end > hi:
                # The entity remains predictable/tradable at T. Only its label is censored.
                return split, f"{split}:outcome_crosses_boundary"
            return split, "accepted"
    return "outside", "outside_declared_period"


def build_dataset(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    if config.get("dataset_kind") == "indices":
        from hocus_quant.model_lab.indices import build_index_dataset

        return build_index_dataset(root, output, config)
    if config.get("feature_sets") == ["all"]:
        from hocus_quant.model_lab.all_features import expand_dataset

        return expand_dataset(root, output, config)
    output.mkdir(parents=True, exist_ok=True)
    lock = json.loads((root / config["lock_path"]).read_text())
    sets = feature_sets(lock)
    if (
        lock["lock_sha256"] != config["lock_sha256"]
        or len(sets["strict"]) != 85
        or len(sets["strong"]) != 138
    ):
        raise ValueError("original strict/strong lock required")
    with duckdb.connect(str(root / "data/research.duckdb"), read_only=True) as db:
        bars = db.execute(
            "SELECT *, 'abc-bourse-manual:equity:'||coalesce(isin,instrument_id) "
            "AS entity_id FROM market_daily ORDER BY entity_id,session_date"
        ).pl()
        benchmark = db.execute("""SELECT * FROM market_series_history WHERE
        series_id='market_indices:QS0010989141' QUALIFY row_number() OVER
        (PARTITION BY series_id,session_date ORDER BY retrieved_at DESC,snapshot_checksum DESC)=1
        ORDER BY session_date""").pl()
    # Store exactly the source read, so later imports cannot silently change this experiment.
    bars.write_parquet(output / "source_market.parquet")
    benchmark.write_parquet(output / "source_benchmark.parquet")
    calendar = sorted(bars["session_date"].unique().to_list())
    cutoffs = [
        d
        for d in calendar
        if d.weekday() == config["cutoff_weekday"]
        and any(
            date.fromisoformat(config[f"{s}_start"]) <= d <= date.fromisoformat(config[f"{s}_end"])
            for s in ["train", "validation", "test"]
        )
    ]
    series = {part["entity_id"][0]: part.to_dicts() for part in bars.partition_by("entity_id")}
    index_rows = benchmark.to_dicts()
    matrix_rows: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    split_audit: list[dict[str, Any]] = []
    for day in cutoffs:
        available = datetime.combine(
            day + timedelta(days=1), datetime.min.time(), ZoneInfo("Europe/Paris")
        )
        bench_past = [
            r for r in index_rows if r["session_date"] <= day and r["available_at"] <= available
        ]
        bench_future = [r for r in index_rows if r["session_date"] > day]
        cohort: list[dict[str, Any]] = []
        for entity, rows in series.items():
            past = [r for r in rows if r["session_date"] <= day and r["available_at"] <= available]
            if not past:
                continue
            quality = assess_series(
                {"entity_id": entity, "entity_family": "equity", "observations": past}
            )
            eligible = quality["quality_status"] == "approved"
            values = locked_features(past, sets["strong"]) if eligible else {}
            eligible = eligible and any(v is not None for v in values.values())
            ledger.append(
                {
                    "cutoff": day,
                    "entity_id": entity,
                    "eligible_at_T": eligible,
                    "quality_at_T": quality["quality_status"],
                    "past_n": len(past),
                    "feature_present": sum(v is not None for v in values.values()),
                }
            )
            if not eligible:
                continue
            matrix_rows.append({"cutoff": day, "entity_id": entity, **values})
            future = [r for r in rows if r["session_date"] > day]
            for h in HORIZONS:
                path = future[:h]
                end = path[-1]["session_date"] if len(path) == h else None
                split, reason = split_assignment(day, end, h, calendar, config)
                # Reference + future path only: keep warnings, flag hard source errors.
                q = assess_series(
                    {
                        "entity_id": entity,
                        "entity_family": "equity",
                        "observations": [past[-1], *path],
                    }
                )
                candidate = future_path(past[-1]["close"], [r["close"] for r in path], h)
                interpretable = q["quality_status"] != "quarantined"
                bpath = (
                    future_path(bench_past[-1]["close"], [r["close"] for r in bench_future[:h]], h)
                    if bench_past
                    else {}
                )
                br = bpath.get("return_abs")
                ret = candidate["return_abs"]
                rel = float(np.sign(ret - br)) if ret is not None and br is not None else None
                cohort.append(
                    {
                        "cutoff": day,
                        "entity_id": entity,
                        "horizon": h,
                        "split": split,
                        "purge_reason": reason,
                        "target_end": end,
                        "benchmark_end": bench_future[h - 1]["session_date"]
                        if len(bench_future) >= h
                        else None,
                        "future_quality": q["quality_status"],
                        "future_reason": q["quality_reason"],
                        "interpretable": interpretable,
                        "direction_rel": rel,
                        **candidate,
                    }
                )
                split_audit.append(
                    {
                        "cutoff": day,
                        "entity_id": entity,
                        "horizon": h,
                        "split": split,
                        "reason": reason,
                        "target_end": end,
                    }
                )
        for h in HORIZONS:
            subset = [r for r in cohort if r["horizon"] == h]
            ranks = rank_targets(
                [
                    r["return_abs"]
                    if r["interpretable"] and r["purge_reason"] == "accepted"
                    else np.nan
                    for r in subset
                ]
            )
            for row, rank in zip(subset, ranks, strict=True):
                row["rank_pct"] = float(rank) if np.isfinite(rank) else None
                if not row["interpretable"] or row["purge_reason"] != "accepted":
                    for family in FAMILIES:
                        row[f"candidate_{family}"] = row.get(family)
                        row[family] = None
                else:
                    for family in FAMILIES:
                        row[f"candidate_{family}"] = row.get(family)
            outcomes.extend(subset)
        print(f"dataset {day}: {len(cohort) // 2} eligible", flush=True)
    for name, rows_out in [
        ("features", matrix_rows),
        ("targets", outcomes),
        ("eligibility", ledger),
        ("split_audit", split_audit),
    ]:
        pl.DataFrame(rows_out, infer_schema_length=None).write_parquet(output / f"{name}.parquet")
    (output / "target_registry.json").write_text(json.dumps(registry_document(), indent=2) + "\n")
    (output / "feature_sets.json").write_text(
        json.dumps(
            {
                "ids": sets,
                "lock_sha256": lock["lock_sha256"],
                "metadata": [r for r in lock["candidates"] if r["strong_sign_candidates"]],
            },
            indent=2,
        )
        + "\n"
    )
    manifest = {
        "lock_sha256": lock["lock_sha256"],
        "target_registry_sha256": registry_document()["sha256"],
        "source_sha256": {
            f"{n}.parquet": file_sha(output / f"{n}.parquet")
            for n in [
                "source_market",
                "source_benchmark",
                "features",
                "targets",
                "eligibility",
                "split_audit",
            ]
        },
        "cutoffs": list(map(str, cutoffs)),
        "pit_grade": "reconstructed",
        "strict_pit_claimed": False,
        "development_only": True,
        "selection_contamination": (
            "strict/strong membership used 2025 AND 2026 outcomes before SPEC-008; "
            "S1 2026 not independent"
        ),
    }
    (output / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    refresh_views(output)
    return manifest


def refresh_views(output: Path) -> None:
    """Dedicated SPEC-008 DuckDB; never replace research or confirmation views."""
    with duckdb.connect(str(output / "model_lab.duckdb")) as db:
        for name in ["features", "targets", "eligibility", "split_audit"]:
            p = str((output / f"{name}.parquet").resolve()).replace("'", "''")
            db.execute(
                f"CREATE OR REPLACE VIEW spec008_{name} AS SELECT * FROM read_parquet('{p}')"
            )
        for family in FAMILIES:
            db.execute(
                f"CREATE OR REPLACE VIEW spec008_{family} AS SELECT cutoff,entity_id,"
                f"horizon,split,{family} AS target_value,target_end,future_quality "
                "FROM spec008_targets"
            )
