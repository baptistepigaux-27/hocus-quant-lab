"""Frozen index cohorts, as-of feature masks, and unchanged SPEC-008 target formulas."""

from __future__ import annotations

import json
import multiprocessing
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import polars as pl

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.features.factory import compute_entity_features
from hocus_quant.features.registry import FEATURE_REGISTRY
from hocus_quant.model_lab.data import refresh_views, split_assignment
from hocus_quant.model_lab.targets import (
    FAMILIES,
    HORIZONS,
    future_path,
    rank_targets,
    registry_document,
)
from hocus_quant.validation.market_quality import assess_series

AUXILIARY = {
    "ABC003500465",
    "ABC003500483",
    "ABC000000177",
    "ABC000000188",
    "ABC003500467",
    "ABC003500468",
    "ABC003500466",
    "ABC003500477",
    "ABC003500476",
    "DE000A0C3QF1",
    "ABC003500504",
    "ABC003500461",
    "ABC003500458",
}
DECREMENT = {
    "ABC003500486",
    "ABC003500505",
    "DE000SLA4ZB0",
    "DE000SL0G3R5",
    "DE000SL0G3V7",
    "DE000SL0BWG3",
    "DE000SL0FEY5",
    "DE000SL0KKE4",
    "DE000SLA8PK3",
}
VARIANTS = {
    "QS0011131834",
    "QS0011131826",
    "QS0011131842",
    "FRESG0002716",
    "FRESG0002708",
    "QS0011213756",
    "EU0009658632",
}
SECTOR_FROM_MARKET = {"XC0006170267", "ABC003500445"}
CLOSE_TECHNICAL = {
    "rsi",
    "macd_line_pct",
    "macd_signal_pct",
    "macd_hist_pct",
    "roc_pct",
    "momentum_pct",
    "bollinger_position",
    "bollinger_bandwidth_pct",
    "ema_distance_pct",
    "sma_distance_pct",
    "realized_volatility_pct",
}
VOLUME_TECHNICAL = {"obv_change_fraction", "mfi", "accumulation_distribution_fraction"}
_ROWS: dict[str, list[dict[str, Any]]] = {}
_CONFIG: dict[str, Any] = {}


def classify(code: str, universe: str) -> tuple[str | None, str]:
    if code in AUXILIARY:
        return None, "auxiliary_non_equity_signal"
    if code in DECREMENT:
        return None, "decrement_or_adjusted_return_product"
    if code in VARIANTS:
        return None, "alternate_variant_same_index_family"
    if universe == "sector_indices" or code in SECTOR_FROM_MARKET:
        return "sector", "equity_sector_index"
    return "market", "equity_market_index"


def initialize(rows: dict[str, list[dict[str, Any]]], config: dict[str, Any]) -> None:
    global _ROWS, _CONFIG
    _ROWS, _CONFIG = rows, config


def feature_row(task: tuple[date, str, str]) -> dict[str, Any]:
    day, entity, group = task
    available = datetime.combine(
        day + timedelta(days=1),
        datetime.min.time(),
        ZoneInfo(_CONFIG["cutoff_availability_timezone"]),
    )
    past = [r for r in _ROWS[entity] if r["session_date"] <= day and r["available_at"] <= available]
    flat = sum(r["open"] == r["high"] == r["low"] == r["close"] for r in past) / len(past)
    close_only = flat >= _CONFIG["close_only_flat_fraction"]
    # Aggregate index volumes are not comparable. Preserve raw snapshots separately.
    analysis_rows = [{**r, "volume": None} for r in past]
    calculated = compute_entity_features(analysis_rows)
    values = {}
    for definition in FEATURE_REGISTRY:
        value = calculated[definition.feature_id][0]
        if definition.family == "volume" or definition.metric in VOLUME_TECHNICAL:
            value = None
        if close_only:
            supported = (
                definition.source_series
                in {"close", "log_close", "close_return", "close_log_return"}
                or (definition.family == "technical" and definition.metric in CLOSE_TECHNICAL)
                or (
                    definition.family == "ohlc"
                    and any(
                        name in definition.feature_id
                        for name in ["positive_share", "negative_share"]
                    )
                )
            )
            if not supported:
                value = None
        values[definition.feature_id] = value
    return {
        "cutoff": day,
        "entity_id": entity,
        "research_group": group,
        "close_only_at_T": close_only,
        **values,
    }


def build_index_dataset(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    if (output / "dataset_manifest.json").exists():
        raise ValueError("Completed dataset exists; preserve the frozen snapshot")
    (output / "dataset_config.json").write_text(json.dumps(config, indent=2) + "\n")
    with duckdb.connect(str(root / "data/research.duckdb"), read_only=True) as db:
        raw = db.execute("""SELECT m.*, l.display_name, l.ticker FROM market_series m
            LEFT JOIN instrument_labels_by_code l
            ON m.provider_instrument_id=l.provider_instrument_id
            WHERE m.universe_id IN ('market_indices','sector_indices')
            ORDER BY m.universe_id,m.provider_instrument_id,m.session_date""").pl()
    raw.write_parquet(output / "source_indices_raw.parquet")
    inventory = []
    chosen = {}
    for part in raw.partition_by(["universe_id", "provider_instrument_id"]):
        item = part.row(0, named=True)
        code, universe = item["provider_instrument_id"], item["universe_id"]
        group, reason = classify(code, universe)
        inventory.append(
            {
                "code": code,
                "source_universe": universe,
                "name": item["display_name"],
                "research_group": group,
                "reason": reason,
                "first_date": part["session_date"].min(),
                "last_date": part["session_date"].max(),
            }
        )
        if group is not None and code not in chosen:
            chosen[code] = (group, part)
    pl.DataFrame(inventory).write_parquet(output / "universe_inventory.parquet")
    parts = [
        part.with_columns(
            pl.lit(f"abc-bourse-manual:index:{code}").alias("entity_id"),
            pl.lit(group).alias("research_group"),
        )
        for code, (group, part) in chosen.items()
    ]
    bars = pl.concat(parts, how="vertical_relaxed").sort(["entity_id", "session_date"])
    bars.write_parquet(output / "source_market.parquet")
    benchmark = raw.filter(pl.col("provider_instrument_id") == "ABC000000189")
    benchmark.write_parquet(output / "source_benchmark.parquet")
    calendar = sorted(
        raw.filter(pl.col("provider_instrument_id") == "FR0003500008")["session_date"]
        .unique()
        .to_list()
    )
    cutoffs = [
        d
        for d in calendar
        if d.weekday() == config["cutoff_weekday"]
        and any(
            date.fromisoformat(config[f"{s}_start"]) <= d <= date.fromisoformat(config[f"{s}_end"])
            for s in ["train", "validation", "test"]
        )
    ]
    series = {p["entity_id"][0]: p.to_dicts() for p in bars.partition_by("entity_id")}
    b_rows = benchmark.to_dicts()
    features, targets, eligibility, audit = [], [], [], []
    cache = output / "feature_partitions"
    cache.mkdir(exist_ok=True)
    with multiprocessing.get_context("spawn").Pool(
        min(config["threads"], 4), initializer=initialize, initargs=(series, config)
    ) as pool:
        for day in cutoffs:
            available = datetime.combine(
                day + timedelta(days=1),
                datetime.min.time(),
                ZoneInfo(config["cutoff_availability_timezone"]),
            )
            calendar_position = calendar.index(day)
            tasks, cohort = [], []
            for entity, rows in series.items():
                past = [
                    r for r in rows if r["session_date"] <= day and r["available_at"] <= available
                ]
                if not past:
                    continue
                group = past[-1]["research_group"]
                q = assess_series(
                    {"entity_id": entity, "entity_family": "index", "observations": past}
                )
                stale = (day - past[-1]["session_date"]).days
                eligible = (
                    q["quality_status"] == "approved"
                    and stale <= config["maximum_stale_calendar_days"]
                    and len(past) >= 3
                )
                eligibility.append(
                    {
                        "cutoff": day,
                        "entity_id": entity,
                        "research_group": group,
                        "eligible_at_T": eligible,
                        "quality_at_T": q["quality_status"],
                        "past_n": len(past),
                        "stale_calendar_days": stale,
                    }
                )
                if not eligible:
                    continue
                tasks.append((day, entity, group))
                future = [r for r in rows if r["session_date"] > day]
                b_past = [
                    r for r in b_rows if r["session_date"] <= day and r["available_at"] <= available
                ]
                for h in HORIZONS:
                    reference_days = calendar[calendar_position + 1 : calendar_position + h + 1]
                    end = reference_days[-1] if len(reference_days) == h else None
                    path = [r for r in future if end is not None and r["session_date"] <= end]
                    aligned_closes = []
                    quote_end = None
                    calendar_complete = len(reference_days) == h
                    for reference_day in reference_days:
                        known = [r for r in [past[-1], *path] if r["session_date"] <= reference_day]
                        quote = known[-1]
                        quote_end = quote["session_date"]
                        if (reference_day - quote_end).days > config["maximum_stale_calendar_days"]:
                            calendar_complete = False
                        aligned_closes.append(quote["close"])
                    split, reason = split_assignment(day, end, h, calendar, config)
                    if reason == "accepted" and not calendar_complete:
                        reason = "future_calendar_quote_missing"
                    future_q = assess_series(
                        {
                            "entity_id": entity,
                            "entity_family": "index",
                            "observations": [past[-1], *path],
                        }
                    )
                    interpretable = (
                        future_q["quality_status"] != "quarantined" and calendar_complete
                    )
                    candidate = future_path(
                        past[-1]["close"], aligned_closes if calendar_complete else [], h
                    )
                    b_end = [
                        r for r in b_rows if end is not None and day < r["session_date"] <= end
                    ]
                    br = b_end[-1]["close"] / b_past[-1]["close"] - 1 if b_past and b_end else None
                    ret = candidate["return_abs"]
                    cohort.append(
                        {
                            "cutoff": day,
                            "entity_id": entity,
                            "horizon": h,
                            "split": split,
                            "purge_reason": reason,
                            "target_end": end,
                            "reference_quote_date": past[-1]["session_date"],
                            "index_quote_end": quote_end,
                            "calendar_complete": calendar_complete,
                            "benchmark_end": b_end[-1]["session_date"] if b_end else None,
                            "future_quality": future_q["quality_status"],
                            "future_reason": future_q["quality_reason"],
                            "interpretable": interpretable,
                            "direction_rel": float(np.sign(ret - br))
                            if ret is not None and br is not None
                            else None,
                            "group": group,
                            **candidate,
                        }
                    )
                    audit.append(
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
                for group in config["research_groups"]:
                    subset = [r for r in cohort if r["horizon"] == h and r["group"] == group]
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
                        for family in FAMILIES:
                            row[f"candidate_{family}"] = row.get(family)
                            if not row["interpretable"] or row["purge_reason"] != "accepted":
                                row[family] = None
                    targets.extend(subset)
            expanded = pool.map(feature_row, tasks)
            partition = pl.DataFrame(expanded, infer_schema_length=None)
            partition.write_parquet(cache / f"{day}.parquet")
            features.append(partition)
            print(f"INDEX FEATURES {day}: {len(expanded)} series", flush=True)
    pl.concat(features, how="vertical_relaxed").write_parquet(output / "features.parquet")
    for name, rows in [("targets", targets), ("eligibility", eligibility), ("split_audit", audit)]:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(output / f"{name}.parquet")
    definitions = [asdict(r) for r in FEATURE_REGISTRY]
    registry_hash = fingerprint(definitions)
    (output / "feature_registry.json").write_text(
        json.dumps({"sha256": registry_hash, "definitions": definitions}, indent=2) + "\n"
    )
    (output / "feature_sets.json").write_text(
        json.dumps(
            {
                "ids": {
                    g: [r.feature_id for r in FEATURE_REGISTRY] for g in config["research_groups"]
                },
                "lock_sha256": config["lock_sha256"],
                "feature_registry_sha256": registry_hash,
                "metadata": definitions,
                "selection": "all registry entries; availability masks use only past data",
            },
            indent=2,
        )
        + "\n"
    )
    formula_registry = registry_document()
    target_contract = {
        **{k: v for k, v in formula_registry.items() if k != "sha256"},
        "formula_registry_parent_sha256": formula_registry["sha256"],
        "horizon_basis": config["target_calendar"],
        "availability_timezone": config["cutoff_availability_timezone"],
    }
    target_contract["sha256"] = fingerprint(target_contract)
    (output / "target_registry.json").write_text(json.dumps(target_contract, indent=2) + "\n")
    manifest = {
        "dataset_kind": "indices",
        "lock_sha256": config["lock_sha256"],
        "lock_role": "lineage reference only; SRD candidate membership is not used",
        "target_registry_sha256": target_contract["sha256"],
        "feature_registry_sha256": registry_hash,
        "feature_count": len(FEATURE_REGISTRY),
        "source_sha256": {
            f"{n}.parquet": file_sha(output / f"{n}.parquet")
            for n in [
                "source_indices_raw",
                "source_market",
                "source_benchmark",
                "universe_inventory",
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
            "2024-2026 previously examined in exploration; retrospective development only"
        ),
        "research_groups": {
            g: sum(group == g for group, _ in chosen.values()) for g in config["research_groups"]
        },
        "benchmark": "MSCI World ABC000000189, last observed close through the common target end",
        "reference_calendar": config["target_calendar"],
        "availability_timezone": config["cutoff_availability_timezone"],
    }
    (output / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    refresh_views(output)
    return manifest
