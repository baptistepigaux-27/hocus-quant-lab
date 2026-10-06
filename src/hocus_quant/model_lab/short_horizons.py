"""Additive short targets on frozen stock features; isolated unchanged model engine."""

from __future__ import annotations

import json
import multiprocessing
import shutil
import time
import tomllib
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_parallel import fit_task
from hocus_quant.model_lab.data import split_assignment
from hocus_quant.model_lab.targets import FAMILIES, rank_targets
from hocus_quant.validation.market_quality import assess_series

HORIZONS = (1, 2, 3)


def settings(root: Path) -> tuple[dict[str, Any], Path, Path]:
    path = root / "configs/experiments/srd_short_horizons_v1.toml"
    config = tomllib.loads(path.read_text())
    output = root / config["output_path"]
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "dataset_config.json"
    if frozen.exists():
        assert json.loads(frozen.read_text()) == config
    else:
        frozen.write_text(json.dumps(config, indent=2) + "\n")
    return config, output, path


def short_path(reference: float, closes: list[float], horizon: int) -> dict[str, Any]:
    p = np.asarray(closes, dtype=float)[:horizon]
    keys = [
        "return_abs",
        "direction_abs",
        "excursion_balance",
        "trend_tstat",
        "max_upside",
        "max_downside",
        "volatility",
    ]
    if len(p) != horizon or not np.isfinite(p).all() or (p <= 0).any() or reference <= 0:
        return dict.fromkeys(keys)
    r = p / reference - 1
    stat, vol = None, None
    if horizon >= 3:
        b = 100 * p / p[0]
        t = np.arange(1, horizon + 1, dtype=float)
        tc, bc = t - t.mean(), b - b.mean()
        sxx = float(tc @ tc)
        slope = float(tc @ bc / sxx)
        residual = bc - slope * tc
        se = float(np.sqrt((residual @ residual) / (horizon - 2) / sxx))
        tolerance = 1e-12 * max(1.0, float(np.max(np.abs(b))))
        stat = (
            0.0
            if np.ptp(b) <= tolerance
            else float(np.copysign(1e6, slope))
            if se <= tolerance
            else float(np.clip(slope / se, -1e6, 1e6))
        )
        vol = float(np.std(np.diff(np.log(p)), ddof=1) * np.sqrt(252))
    return {
        "return_abs": float(r[-1]),
        "direction_abs": float(np.sign(r[-1])),
        "excursion_balance": float(r.max() + r.min()),
        "trend_tstat": stat,
        "max_upside": float(r.max()),
        "max_downside": float(r.min()),
        "volatility": vol,
    }


def build_data(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    manifest_path = output / "dataset_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        assert all(
            file_sha(output / name) == sha for name, sha in manifest["source_sha256"].items()
        )
        return manifest
    source = root / config["source_path"]
    parent = json.loads((source / "dataset_manifest.json").read_text())
    assert all(file_sha(source / name) == sha for name, sha in parent["source_sha256"].items())
    for name in [
        "features.parquet",
        "source_market.parquet",
        "source_benchmark.parquet",
        "eligibility.parquet",
        "feature_sets.json",
        "feature_registry.json",
    ]:
        shutil.copyfile(source / name, output / name)
    features = pd.read_parquet(output / "features.parquet")
    features["cutoff"] = pd.to_datetime(features.cutoff).dt.date
    market = pd.read_parquet(output / "source_market.parquet")
    bench = pd.read_parquet(output / "source_benchmark.parquet")
    for frame in [market, bench]:
        frame["session_date"] = pd.to_datetime(frame.session_date).dt.date
    calendar = sorted(market.session_date.unique())
    source_rows = {
        entity: part.sort_values("session_date").to_dict("records")
        for entity, part in market.groupby("entity_id")
    }
    quotes = {(r.entity_id, r.session_date): r._asdict() for r in market.itertuples(index=False)}
    benchmark_rows = bench.sort_values("session_date").to_dict("records")
    benchmark = {r["session_date"]: r for r in benchmark_rows}
    outcomes, splits = [], []
    for day, part in features.groupby("cutoff", sort=True):
        availability = datetime.combine(
            day + timedelta(days=1), datetime.min.time(), ZoneInfo("UTC")
        )
        future_days = [d for d in calendar if d > day]
        bpast = [
            r
            for r in benchmark_rows
            if r["session_date"] <= day and r["available_at"] <= availability
        ]
        cohort = []
        for entity in part.entity_id:
            past = [
                r
                for r in source_rows[entity]
                if r["session_date"] <= day and r["available_at"] <= availability
            ]
            assert past
            ref = past[-1]
            for h in HORIZONS:
                days = future_days[:h]
                path = [quotes.get((entity, d)) for d in days]
                end = days[-1] if len(days) == h else None
                split, reason = split_assignment(day, end, h, calendar, config)
                complete = len(path) == h and all(r is not None for r in path)
                q = assess_series(
                    {
                        "entity_id": entity,
                        "entity_family": "equity",
                        "observations": [ref, *[r for r in path if r is not None]],
                    }
                )
                candidate = short_path(
                    ref["close"], [r["close"] if r is not None else np.nan for r in path], h
                )
                br = None
                if bpast and end in benchmark and benchmark[end]["close"] > 0:
                    br = benchmark[end]["close"] / bpast[-1]["close"] - 1
                ret = candidate["return_abs"]
                interpretable = (
                    complete and ret is not None and q["quality_status"] != "quarantined"
                )
                row = {
                    "cutoff": day,
                    "entity_id": entity,
                    "horizon": h,
                    "split": split,
                    "purge_reason": reason,
                    "target_end": end,
                    "benchmark_end": end,
                    "reference_quote_date": ref["session_date"],
                    "reference_close": ref["close"],
                    "future_quality": q["quality_status"],
                    "future_reason": q["quality_reason"],
                    "interpretable": interpretable,
                    "direction_rel": float(np.sign(ret - br))
                    if ret is not None and br is not None
                    else None,
                    **candidate,
                }
                cohort.append(row)
                splits.append(
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
            scoped = [r for r in cohort if r["horizon"] == h]
            ranks = rank_targets(
                [
                    r["return_abs"]
                    if r["interpretable"] and r["purge_reason"] == "accepted"
                    else np.nan
                    for r in scoped
                ]
            )
            for row, rank in zip(scoped, ranks, strict=True):
                row["rank_pct"] = float(rank) if np.isfinite(rank) else None
                for family in FAMILIES:
                    row[f"candidate_{family}"] = row.get(family)
                    if not row["interpretable"] or row["purge_reason"] != "accepted":
                        row[family] = None
            outcomes.extend(scoped)
        print(f"SHORT DATA {day}: {len(part)} actions", flush=True)
    pd.DataFrame(outcomes).to_parquet(output / "targets.parquet", index=False)
    pd.DataFrame(splits).to_parquet(output / "split_audit.parquet", index=False)
    parent_registry = json.loads((source / "target_registry.json").read_text())
    definitions = [
        {
            "target_id": f"future.{family}.h{h}."
            + (
                "market.v1"
                if family == "direction_rel"
                else "family.v1"
                if family == "rank_pct"
                else "v1"
            ),
            "family": family,
            "horizon": h,
            "calendar": "common observed sessions",
            "formula": {
                "return_abs": "P_H/P_T-1",
                "direction_abs": "sign(P_H/P_T-1)",
                "direction_rel": "sign(return_abs-benchmark_return)",
                "rank_pct": "average ascending rank/N",
                "excursion_balance": "max(r)+min(r)",
                "trend_tstat": "OLS slope/SE, df=H-2",
            }[family],
        }
        for h in HORIZONS
        for family in FAMILIES
        if h >= 3 or family != "trend_tstat"
    ]
    registry = {
        "version": "SRD-SHORT-targets/1.0.0",
        "parent_sha256": parent_registry["sha256"],
        "definitions": definitions,
        "disabled": {"trend_tstat": [1, 2]},
        "redundancy": "excursion_balance H1 equals 2*return_abs H1",
    }
    registry["sha256"] = fingerprint(registry)
    (output / "target_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    manifest = {
        **parent,
        "target_registry_sha256": registry["sha256"],
        "parent_manifest_sha256": file_sha(source / "dataset_manifest.json"),
        "features_unchanged": True,
        "model_horizons": list(HORIZONS),
        "target_calendar": "common observed sessions, missing quote not forward-filled",
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
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def run_models(root: Path, output: Path, config_path: Path) -> dict[str, Any]:
    if (output / "summary.json").exists():
        raise ValueError("Complete models exist; publish them or use a new version")
    started = time.monotonic()
    folders, tasks = [], []
    for h in HORIZONS:
        for family in FAMILIES:
            if family == "trend_tstat" and h < 3:
                continue
            folder = output / "task_runs" / f"{family}-h{h}"
            folder.mkdir(parents=True, exist_ok=True)
            for name in [
                "features.parquet",
                "targets.parquet",
                "source_market.parquet",
                "source_benchmark.parquet",
                "eligibility.parquet",
                "split_audit.parquet",
                "dataset_manifest.json",
                "feature_sets.json",
                "feature_registry.json",
                "target_registry.json",
            ]:
                path = folder / name
                if not path.exists():
                    path.symlink_to(output / name)
            folders.append(folder)
            tasks.append((str(root), str(config_path), str(folder), h, family))
    summaries = []
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        jobs = {pool.submit(fit_task, task): task for task in tasks}
        for job in as_completed(jobs):
            summaries.append(job.result())
            print(
                f"SHORT COMPLETE {jobs[job][4]} H{jobs[job][3]} ({len(summaries)}/16)", flush=True
            )
    registry = []
    (output / "models").mkdir(exist_ok=True)
    for folder in folders:
        entries = json.loads((folder / "model_registry.json").read_text())
        registry.extend(entries)
        for entry in entries:
            shutil.copyfile(
                folder / "models" / f"{entry['model_id']}.joblib",
                output / "models" / f"{entry['model_id']}.joblib",
            )
    assert len(registry) == 74
    for name in [
        "hyperparameter_results",
        "metrics",
        "predictions",
        "cutoff_metrics",
        "decile_metrics",
        "calibration",
        "feature_importances",
        "coverage",
        "trajectory_diagnostics",
    ]:
        pd.concat(
            [pd.read_parquet(folder / f"{name}.parquet") for folder in folders], ignore_index=True
        ).to_parquet(output / f"{name}.parquet", index=False)
    (output / "model_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    shutil.copyfile(folders[0] / "experiment_config.json", output / "experiment_config.json")
    summary = {
        **summaries[0],
        "tasks": 16,
        "target_horizon_tasks": 16,
        "model_count": 74,
        "tuning_fits": sum(s["tuning_fits"] for s in summaries),
        "final_retrain_fits": 74,
        "elapsed_seconds": time.monotonic() - started,
        "backtest_count": 0,
        "parallel_task_workers": 2,
        "artifact_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
