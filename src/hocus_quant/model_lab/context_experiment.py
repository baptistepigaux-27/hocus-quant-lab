"""Additive SRD context experiment on the unchanged all-feature action cohort."""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_data import normal_dates, prepare_context_inputs, utc_available
from hocus_quant.model_lab.context_producers import produce_context
from hocus_quant.model_lab.data import refresh_views


def settings(root: Path, config_path: Path) -> tuple[dict[str, Any], Path]:
    config = tomllib.loads((root / config_path).read_text())
    output = root / config["output_path"]
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "context_config.json"
    if frozen.exists():
        assert json.loads(frozen.read_text()) == config, "Use a new version for a changed config"
    else:
        frozen.write_text(json.dumps(config, indent=2) + "\n")
    return config, output


def build_enriched_dataset(root: Path, config: dict[str, Any], output: Path) -> dict[str, Any]:
    if (output / "dataset_manifest.json").exists():
        receipt = json.loads((output / "dataset_manifest.json").read_text())
        for name, sha in receipt["source_sha256"].items():
            assert file_sha(output / name) == sha
        return receipt
    prepare_context_inputs(root, config, output)
    produce_context(root, output, config)
    baseline = root / config["baseline_path"]
    original = json.loads((baseline / "dataset_manifest.json").read_text())
    for name, sha in original["source_sha256"].items():
        assert file_sha(baseline / name) == sha
    fs = json.loads((baseline / "feature_sets.json").read_text())
    own_ids = fs["ids"]["all"]
    actions = normal_dates(pd.read_parquet(baseline / "features.parquet"), ["cutoff"])
    contexts = normal_dates(pd.read_parquet(output / "context/features.parquet"), ["cutoff"])
    context_ids = sorted(c for c in contexts if c.startswith("ctx."))
    assert len(context_ids) == 356 and len(own_ids) == 1048
    contexts = contexts.rename(columns={"cutoff": "context_cutoff"})
    contexts["context_available_at"] = contexts.context_cutoff.map(utc_available)
    actions["decision_at"] = actions.cutoff.map(utc_available)
    combined = (
        pd.merge_asof(
            actions.sort_values("decision_at"),
            contexts.sort_values("context_available_at"),
            left_on="decision_at",
            right_on="context_available_at",
            direction="backward",
            allow_exact_matches=True,
            tolerance=pd.Timedelta(days=7),
        )
        .sort_values(["cutoff", "entity_id"])
        .reset_index(drop=True)
    )
    expected = actions.sort_values(["cutoff", "entity_id"]).reset_index(drop=True)
    assert combined[["cutoff", "entity_id"]].equals(expected[["cutoff", "entity_id"]])
    assert np.allclose(
        combined[own_ids].to_numpy(dtype=float),
        expected[own_ids].to_numpy(dtype=float),
        equal_nan=True,
    )
    assert (combined.context_available_at <= combined.decision_at).all()
    assert (combined.context_cutoff == combined.cutoff).all()
    assert (combined.groupby("cutoff")[context_ids].nunique(dropna=False) == 1).all().all()
    combined.to_parquet(output / "features.parquet", index=False)
    for name in ["source_market", "source_benchmark", "targets", "eligibility", "split_audit"]:
        shutil.copyfile(baseline / f"{name}.parquet", output / f"{name}.parquet")
    shutil.copyfile(baseline / "target_registry.json", output / "target_registry.json")
    shutil.copyfile(baseline / "feature_registry.json", output / "stock_feature_registry.json")
    definitions = [
        {
            "feature_id": name,
            "family": "market_context",
            "formula_version": "v1",
            "source": "expanding historical context",
            "pit_grade": "reconstructed",
        }
        for name in context_ids
    ]
    registry_hash = fingerprint(
        {"stock_registry": fs["feature_registry_sha256"], "context": definitions}
    )
    (output / "feature_registry.json").write_text(
        json.dumps(
            {
                "sha256": registry_hash,
                "parent_registry_sha256": fs["feature_registry_sha256"],
                "context_definitions": definitions,
            },
            indent=2,
        )
        + "\n"
    )
    (output / "feature_sets.json").write_text(
        json.dumps(
            {
                **fs,
                "ids": {"context": [*own_ids, *context_ids]},
                "context_feature_ids": context_ids,
                "feature_registry_sha256": registry_hash,
                "context_metadata": definitions,
                "selection": "all stock features plus frozen-context definitions",
            },
            indent=2,
        )
        + "\n"
    )
    receipt = {
        **original,
        "feature_count": len(own_ids) + len(context_ids),
        "feature_registry_sha256": registry_hash,
        "baseline_manifest_sha256": file_sha(baseline / "dataset_manifest.json"),
        "context_producers_sha256": file_sha(output / "context/complete.json"),
        "cohort_and_labels_unchanged": True,
        "stock_feature_values_unchanged": True,
        "context_join": "as-of at session date + 1 day midnight UTC; age tolerance 7 days",
        "context_missing_drops_action": False,
        "selection_contamination": (
            "Retrospective development on previously explored 2024-2026; "
            "context producers use only earlier information"
        ),
        "source_sha256": {
            f"{name}.parquet": file_sha(output / f"{name}.parquet")
            for name in [
                "source_market",
                "source_benchmark",
                "features",
                "targets",
                "eligibility",
                "split_audit",
            ]
        },
    }
    (output / "dataset_manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    audit = {
        "action_rows": len(combined),
        "action_dates": combined.cutoff.nunique(),
        "stock_features": len(own_ids),
        "context_features": len(context_ids),
        "no_row_removed": True,
        "stock_values_identical": True,
        "context_missing_fraction": float(combined[context_ids].isna().mean().mean()),
        "decisions_after_context_availability": True,
        "all_contexts_broadcast_without_sector_mapping": True,
    }
    (output / "integration_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    text = (root / "configs/experiments/model_lab_all_features_v1.toml").read_text()
    text = text.replace('version = "SPEC-008-ALL/1.0.0"', 'version = "SRD-CONTEXT/1.0.0"')
    text = text.replace('feature_sets = ["all"]', 'feature_sets = ["context"]')
    text = text.replace(
        'report_stem = "SPEC_008_ALL_FEATURES_RESULTS"', 'report_stem = "SRD_CONTEXT_RESULTS"'
    )
    text = text.replace("portfolio_top_fraction = 0.1", "portfolio_top_fraction = 0.03")
    text = text.replace("costs_round_trip_bp = [0, 10, 25, 50]", "costs_round_trip_bp = [25, 45]")
    text = text.replace(
        "permutation_repeats = 1", "permutation_enabled = false\npermutation_repeats = 0"
    )
    (output / "srd_benchmark.toml").write_text(text)
    (output / "dataset_config.json").write_text(json.dumps(tomllib.loads(text), indent=2) + "\n")
    refresh_views(output)
    return receipt
