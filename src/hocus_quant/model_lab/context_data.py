"""Historical inputs for market context, with an additional 2023 warmup."""

from __future__ import annotations

import json
import math
import multiprocessing
from bisect import bisect_right
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.analysis.index_series_models import features as close_features
from hocus_quant.features.registry import FEATURE_REGISTRY
from hocus_quant.model_lab.indices import feature_row, initialize
from hocus_quant.model_lab.targets import future_path, rank_targets
from hocus_quant.validation.market_quality import assess_series


def normal_dates(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for name in columns:
        if name in frame:
            frame[name] = pd.to_datetime(frame[name]).dt.date
    return frame


def utc_available(day: date) -> pd.Timestamp:
    return pd.Timestamp(day + timedelta(days=1), tz="UTC")


def aligned_quotes(source: pd.DataFrame, calendar: list[date], maximum_age: int) -> pd.DataFrame:
    ordered = source.sort_values("session_date")
    days, prices = ordered.session_date.tolist(), ordered.close.tolist()
    rows = []
    for day in calendar:
        i = bisect_right(days, day) - 1
        quote_day = days[i] if i >= 0 else None
        age = (day - quote_day).days if quote_day else None
        value = float(prices[i]) if i >= 0 else np.nan
        valid = age is not None and age <= maximum_age and np.isfinite(value) and value > 0
        rows.append(
            {
                "cutoff": day,
                "reference_quote_date": quote_day,
                "quote_age_days": age,
                "reference_close": value if valid else np.nan,
                "eligible_at_T": bool(valid),
            }
        )
    return pd.DataFrame(rows)


def prepare_context_inputs(root: Path, config: dict[str, Any], output: Path) -> dict[str, Any]:
    directory = output / "context_inputs"
    if (directory / "complete.json").exists():
        receipt = json.loads((directory / "complete.json").read_text())
        for name, sha in receipt["artifacts"].items():
            assert file_sha(directory / name) == sha
        return receipt
    directory.mkdir(parents=True, exist_ok=True)
    parent = root / config["indices_path"]
    manifest = json.loads((parent / "dataset_manifest.json").read_text())
    for name in ["source_market.parquet", "source_benchmark.parquet", "features.parquet"]:
        assert file_sha(parent / name) == manifest["source_sha256"][name]
    bars = normal_dates(pd.read_parquet(parent / "source_market.parquet"), ["session_date"])
    benchmark = normal_dates(pd.read_parquet(parent / "source_benchmark.parquet"), ["session_date"])
    old_features = normal_dates(pd.read_parquet(parent / "features.parquet"), ["cutoff"])
    sector_bars = bars[bars.research_group == "sector"].copy()
    codes = sorted(sector_bars.provider_instrument_id.unique().tolist())
    assert len(codes) == 27
    inventory = sector_bars.groupby("provider_instrument_id").display_name.first().reset_index()
    inventory.to_parquet(directory / "sector_inventory.parquet", index=False)
    calendar = sorted(
        bars[bars.provider_instrument_id == config["major_codes"][0]].session_date.unique()
    )
    (directory / "calendar.json").write_text(json.dumps(list(map(str, calendar))) + "\n")
    warmup = [
        d
        for d in calendar
        if date.fromisoformat(config["warmup_start"])
        <= d
        <= date.fromisoformat(config["cluster_fit_end"])
        and d.weekday() == 4
    ]
    series = {
        entity: part.sort_values("session_date").to_dict("records")
        for entity, part in sector_bars.groupby("entity_id")
    }
    worker_config = {"cutoff_availability_timezone": "UTC", "close_only_flat_fraction": 0.9}
    cache = directory / "warmup_partitions"
    cache.mkdir(exist_ok=True)
    with multiprocessing.get_context("spawn").Pool(
        config["threads"], initializer=initialize, initargs=(series, worker_config)
    ) as pool:
        for day in warmup:
            saved = cache / f"{day}.parquet"
            if saved.exists():
                continue
            tasks = []
            available = datetime.combine(
                day + timedelta(days=1), datetime.min.time(), ZoneInfo("UTC")
            )
            for entity, native in series.items():
                past = [
                    r for r in native if r["session_date"] <= day and r["available_at"] <= available
                ]
                if not past or len(past) < 3 or (day - past[-1]["session_date"]).days > 3:
                    continue
                quality = assess_series(
                    {"entity_id": entity, "entity_family": "index", "observations": past}
                )
                if quality["quality_status"] == "approved":
                    tasks.append((day, entity, "sector"))
            pd.DataFrame(pool.map(feature_row, tasks)).to_parquet(saved, index=False)
            print(f"CONTEXT WARMUP {day}: {len(tasks)} sectors", flush=True)
    sector_features = pd.concat(
        [
            *[pd.read_parquet(cache / f"{d}.parquet") for d in warmup],
            old_features[old_features.research_group == "sector"],
        ],
        ignore_index=True,
    ).sort_values(["cutoff", "entity_id"])
    assert not sector_features.duplicated(["cutoff", "entity_id"]).any()
    sector_features.to_parquet(directory / "sector_features.parquet", index=False)
    aligned = {
        entity: aligned_quotes(part, calendar, config["maximum_quote_age_days"])
        for entity, part in sector_bars.groupby("entity_id")
    }
    world = aligned_quotes(benchmark, calendar, config["maximum_quote_age_days"])
    positions = {d: i for i, d in enumerate(calendar)}
    targets = []
    for row in sector_features[["cutoff", "entity_id"]].itertuples(index=False):
        i = positions[row.cutoff]
        quotes = aligned[row.entity_id]
        for h in config["horizons"]:
            path = quotes.reference_close.iloc[i : i + h + 1].to_numpy(dtype=float)
            complete = len(path) == h + 1 and np.isfinite(path).all() and (path > 0).all()
            end = calendar[i + h] if i + h < len(calendar) else None
            values = future_path(float(path[0]), path[1:] if complete else [], h)
            world_path = world.reference_close.iloc[i : i + h + 1].to_numpy(dtype=float)
            world_valid = len(world_path) == h + 1 and np.isfinite(world_path).all()
            relative = (
                values["return_abs"] - (world_path[-1] / world_path[0] - 1)
                if values["return_abs"] is not None and world_valid
                else None
            )
            targets.append(
                {
                    "cutoff": row.cutoff,
                    "entity_id": row.entity_id,
                    "horizon": h,
                    "target_end": end,
                    "direction_rel": float(np.sign(relative)) if relative is not None else None,
                    **values,
                }
            )
    sector_targets = pd.DataFrame(targets)
    sector_targets["rank_pct"] = sector_targets.groupby(["cutoff", "horizon"]).return_abs.transform(
        lambda x: rank_targets(x.to_numpy())
    )
    sector_targets.to_parquet(directory / "sector_targets.parquet", index=False)
    major_features, major_targets = [], []
    for code in config["major_codes"]:
        quotes = aligned_quotes(
            bars[bars.provider_instrument_id == code], calendar, config["maximum_quote_age_days"]
        )
        calculated = close_features(quotes.reference_close)
        matrix = pd.concat([quotes, calculated], axis=1)
        matrix["index_code"] = code
        matrix = matrix[matrix.cutoff >= date.fromisoformat(config["warmup_start"])]
        major_features.append(matrix)
        for row in matrix.itertuples():
            i = positions[row.cutoff]
            for h in config["horizons"]:
                path = quotes.reference_close.iloc[i : i + h + 1].to_numpy(dtype=float)
                complete = len(path) == h + 1 and np.isfinite(path).all() and (path > 0).all()
                end = calendar[i + h] if i + h < len(calendar) else None
                ret = float(path[-1] / path[0] - 1) if complete else np.nan
                vol = (
                    float(np.std(np.diff(np.log(path)), ddof=1) * math.sqrt(252))
                    if complete
                    else np.nan
                )
                major_targets.append(
                    {
                        "index_code": code,
                        "cutoff": row.cutoff,
                        "horizon": h,
                        "target_end": end,
                        "return": ret,
                        "direction": float(np.sign(ret)),
                        "volatility": vol,
                    }
                )
    pd.concat(major_features, ignore_index=True).to_parquet(
        directory / "major_features.parquet", index=False
    )
    pd.DataFrame(major_targets).to_parquet(directory / "major_targets.parquet", index=False)
    ids = [d.feature_id for d in FEATURE_REGISTRY]
    receipt = {
        "sector_codes": codes,
        "sector_feature_ids": ids,
        "major_feature_ids": list(close_features(pd.Series([1.0, 2.0, 3.0])).columns),
        "sector_warmup_rows": int((sector_features.cutoff < date(2024, 1, 1)).sum()),
        "parent_sha256": {n: file_sha(parent / n) for n in manifest["source_sha256"]},
        "generator_sha256": file_sha(Path(__file__)),
        "artifacts": {p.name: file_sha(p) for p in directory.glob("*.parquet")},
    }
    (directory / "complete.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
