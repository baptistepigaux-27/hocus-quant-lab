"""Run independent SRD tasks in separate processes with unchanged fit semantics."""

from __future__ import annotations

import json
import multiprocessing
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.targets import FAMILIES, HORIZONS


def fit_task(arguments: tuple[str, str, str, int, str]) -> dict[str, Any]:
    root_s, config_s, folder_s, h, family = arguments
    from hocus_quant.model_lab import run as engine

    folder = Path(folder_s)
    if (folder / "summary.json").exists():
        result = json.loads((folder / "summary.json").read_text())
        for name, sha in result["artifact_sha256"].items():
            assert file_sha(folder / name) == sha
        return result
    # Independent tasks from the original Cartesian loop, with identical fits and seeds.
    engine.HORIZONS, engine.FAMILIES = (h,), (family,)
    return engine.run_benchmark(Path(root_s), Path(config_s), folder)


def run_parallel(root: Path, config_path: Path, output: Path, workers: int = 2) -> dict[str, Any]:
    if (output / "summary.json").exists():
        raise ValueError("Completed experiment exists")
    started = time.monotonic()
    folders, tasks = [], []
    for h in HORIZONS:
        for family in FAMILIES:
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
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        futures = {pool.submit(fit_task, task): task for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            summaries.append(result)
            print(
                f"SRD TASK COMPLETE {futures[future][4]} H{futures[future][3]} "
                f"({len(summaries)}/12)",
                flush=True,
            )
    registry = []
    for folder in folders:
        entries = json.loads((folder / "model_registry.json").read_text())
        registry.extend(entries)
        (output / "models").mkdir(exist_ok=True)
        for entry in entries:
            shutil.copyfile(
                folder / "models" / f"{entry['model_id']}.joblib",
                output / "models" / f"{entry['model_id']}.joblib",
            )
    assert len(registry) == 56
    names = [
        "hyperparameter_results",
        "metrics",
        "predictions",
        "cutoff_metrics",
        "decile_metrics",
        "calibration",
        "feature_importances",
        "coverage",
        "trajectory_diagnostics",
        "backtest_summary",
        "backtest_equity",
        "backtest_trades",
    ]
    for name in names:
        frames, universe_h = [], set()
        for folder in folders:
            frame = pd.read_parquet(folder / f"{name}.parquet")
            if name.startswith("backtest"):
                h = int(frame.horizon.iloc[0])
                if h in universe_h:
                    frame = frame[frame.model != "universe"]
                universe_h.add(h)
            frames.append(frame)
        pd.concat(frames, ignore_index=True).to_parquet(output / f"{name}.parquet", index=False)
    config = json.loads((folders[0] / "experiment_config.json").read_text())
    (output / "experiment_config.json").write_text(json.dumps(config, indent=2) + "\n")
    (output / "model_registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    summary = {
        **summaries[0],
        "tasks": 12,
        "target_horizon_tasks": 12,
        "model_count": len(registry),
        "tuning_fits": sum(s["tuning_fits"] for s in summaries),
        "final_retrain_fits": len(registry),
        "backtest_count": len(pd.read_parquet(output / "backtest_summary.parquet")),
        "elapsed_seconds": time.monotonic() - started,
        "parallel_task_workers": workers,
        "independent_task_sharding": True,
        "artifact_sha256": {p.name: file_sha(p) for p in output.glob("*.parquet")},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
