"""Expand the original decision cohort to the full historical feature registry.

The baseline's membership, labels, purge rules and execution inputs are preserved.
No feature is selected by a validation or test outcome in this extension.
"""

from __future__ import annotations

import json
import multiprocessing
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.features.factory import compute_entity_features
from hocus_quant.features.registry import FEATURE_REGISTRY
from hocus_quant.model_lab.data import refresh_views

_SERIES: dict[str, list[dict[str, Any]]] = {}


def _initialize_worker(series: dict[str, list[dict[str, Any]]]) -> None:
    global _SERIES
    _SERIES = series


def _expand_row(task: tuple[Any, str]) -> dict[str, Any]:
    day, entity = task
    available = datetime.combine(
        day + timedelta(days=1), datetime.min.time(), ZoneInfo("Europe/Paris")
    )
    past = [
        r for r in _SERIES[entity] if r["session_date"] <= day and r["available_at"] <= available
    ]
    values = compute_entity_features(past)
    return {"cutoff": day, "entity_id": entity, **{k: v[0] for k, v in values.items()}}


def expand_dataset(root: Path, output: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Recompute all features at T, retaining byte-identical outcome/source artefacts."""
    baseline = root / config["comparison_baseline"]
    if baseline.resolve() == output.resolve():
        raise ValueError("the full-registry experiment requires a new output directory")
    original = json.loads((baseline / "dataset_manifest.json").read_text())
    for name, expected in original["source_sha256"].items():
        if file_sha(baseline / name) != expected:
            raise ValueError(f"baseline input changed: {name}")
    if original["lock_sha256"] != config["lock_sha256"]:
        raise ValueError("candidate lock differs from the baseline")
    old_config = json.loads((baseline / "experiment_config.json").read_text())
    permitted = {
        "version",
        "feature_sets",
        "comparison_baseline",
        "report_stem",
        "permutation_scope",
    }
    for key in set(old_config) | set(config):
        if key not in permitted and old_config.get(key) != config.get(key):
            raise ValueError(f"comparison must preserve the baseline rule: {key}")
    output.mkdir(parents=True, exist_ok=True)
    config_file = output / "dataset_config.json"
    if config_file.exists() and json.loads(config_file.read_text()) != config:
        raise ValueError("expansion config changed; use a new output directory")
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    names = [r.feature_id for r in FEATURE_REGISTRY]
    definitions = [asdict(r) for r in FEATURE_REGISTRY]
    registry_hash = fingerprint(definitions)
    captured_registry = output / "feature_registry.json"
    registry = {"sha256": registry_hash, "definitions": definitions}
    if captured_registry.exists() and json.loads(captured_registry.read_text()) != registry:
        raise ValueError("full feature registry changed during expansion")
    captured_registry.write_text(json.dumps(registry, indent=2) + "\n")
    # Copy the originals: neither their labels nor their future-quality flags are rebuilt.
    copied = ["source_market", "source_benchmark", "targets", "eligibility", "split_audit"]
    for name in copied:
        shutil.copyfile(baseline / f"{name}.parquet", output / f"{name}.parquet")
    shutil.copyfile(baseline / "target_registry.json", output / "target_registry.json")
    old_sets = json.loads((baseline / "feature_sets.json").read_text())
    (output / "feature_sets.json").write_text(
        json.dumps(
            {
                "ids": {"all": names},
                "lock_sha256": original["lock_sha256"],
                "feature_registry_sha256": registry_hash,
                "selection": "all registry entries, no outcome-based feature selection",
                "metadata": definitions,
                "original_lock_metadata": old_sets["metadata"],
                "eligibility": "identical to the original SPEC-008 decision cohort",
            },
            indent=2,
        )
        + "\n"
    )
    old_features = pl.read_parquet(baseline / "features.parquet")
    bars = pl.read_parquet(output / "source_market.parquet")
    series = {part["entity_id"][0]: part.to_dicts() for part in bars.partition_by("entity_id")}
    cache = output / "feature_partitions"
    cache.mkdir(exist_ok=True)
    # Spawn keeps Polars' parent thread pool out of the numerical workers.
    with multiprocessing.get_context("spawn").Pool(
        min(int(config["threads"]), 4), initializer=_initialize_worker, initargs=(series,)
    ) as pool:
        for part in old_features.sort(["cutoff", "entity_id"]).partition_by("cutoff"):
            day = part["cutoff"][0]
            path = cache / f"{day}.parquet"
            if path.exists():
                continue
            expanded = pool.map(_expand_row, [(day, entity) for entity in part["entity_id"]])
            pl.DataFrame(expanded, infer_schema_length=None).write_parquet(path)
            print(f"ALL FEATURES {day}: {len(expanded)} rows, {len(names)} variables", flush=True)
    features = pl.concat(
        [
            pl.read_parquet(cache / f"{day}.parquet")
            for day in old_features["cutoff"].unique().sort()
        ],
        how="vertical_relaxed",
    ).sort(["cutoff", "entity_id"])
    # Check every previously used value, not merely row counts or a few samples.
    aligned = old_features.sort(["cutoff", "entity_id"])
    if not features.select("cutoff", "entity_id").equals(aligned.select("cutoff", "entity_id")):
        raise ValueError("decision cohort changed")
    for name in old_sets["ids"]["strong"]:
        if not np.allclose(
            features[name].to_numpy(),
            aligned[name].to_numpy(),
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        ):
            raise ValueError(f"canonical/locked feature formula differs: {name}")
    features.write_parquet(output / "features.parquet")
    manifest = {
        **original,
        "source_sha256": {
            f"{n}.parquet": file_sha(output / f"{n}.parquet") for n in [*copied, "features"]
        },
        "feature_registry_sha256": registry_hash,
        "feature_count": len(names),
        "baseline_manifest_sha256": file_sha(baseline / "dataset_manifest.json"),
        "baseline_input_fingerprints": original["source_sha256"],
        "cohort_and_labels_unchanged": True,
        "all_strong_feature_values_match": True,
        "selection_contamination": (
            "Full registry is unfiltered by outcomes; original development cohort retained. "
            "2024/2025/2026 were previously examined; S1 2026 is not independent confirmation."
        ),
    }
    (output / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    refresh_views(output)
    return manifest
