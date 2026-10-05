"""Frozen SPEC-007 protocol, development boundary and runtime identity."""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb

from hocus_quant.analysis.candidate_lock import fingerprint, verify_lock
from hocus_quant.features.registry import registry_document
from hocus_quant.targets.registry import target_registry_document

SCIENTIFIC_FILES = (
    "features/factory.py",
    "features/registry.py",
    "features/snapshot.py",
    "targets/registry.py",
    "targets/factory.py",
    "targets/hardening.py",
    "targets/research_contract.py",
    "validation/market_quality.py",
    "analysis/candidate_lock.py",
    "analysis/ex_ante.py",
    "analysis/confirmation_protocol.py",
    "analysis/confirmation_metrics.py",
    "analysis/confirmation.py",
)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_identity(root: Path) -> dict[str, Any]:
    return {
        "feature_registry_sha256": registry_document()["sha256"],
        "target_registry_sha256": target_registry_document()["sha256"],
        "python_version": sys.version,
        "package_versions": {
            name: version(name)
            for name in ["numpy", "scipy", "pandas", "polars", "duckdb", "pyarrow", "scikit-learn"]
        },
        "uv_lock_sha256": file_sha(root / "uv.lock"),
        "scientific_source_sha256": {
            name: file_sha(root / "src/hocus_quant" / name) for name in SCIENTIFIC_FILES
        },
    }


def derive_boundary(root: Path, lock: dict[str, Any], frozen_on: date) -> dict[str, Any]:
    """Read previously examined artefacts once; never rederive after collecting starts."""
    names = ["spec006-weekly-demo", "spec006-2025-matched", "spec006-2026-matched"]
    paths = sorted(
        p
        for name in names
        for p in (root / "data/targets" / name).glob("as_of_date=*/targets.parquet")
    )
    if not paths:
        raise ValueError("development targets are required to derive the boundary")
    with duckdb.connect() as db:
        maxima = db.execute(
            "SELECT max(as_of_date), max(target_end_date), max(last_future_observation_date) "
            "FROM read_parquet(?, union_by_name=true)",
            [list(map(str, paths))],
        ).fetchone()
    assert maxima is not None
    observed = date.fromisoformat(lock["contract"]["data_observed_through"])
    development_end = max(observed, *(value for value in maxima if value is not None))
    # Also forbid historical backfilling between development and prospective registration.
    first = max(development_end, frozen_on) + timedelta(days=1)
    return {
        "development_observed_through": development_end.isoformat(),
        "protocol_frozen_on": frozen_on.isoformat(),
        "confirmation_start_date": first.isoformat(),
        "derivation": "day after max(development observations/outcomes, protocol freeze date)",
        "development_target_files": [
            {"path": str(p.relative_to(root)), "sha256": file_sha(p)} for p in paths
        ],
    }


def known_groups(root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """Preserve existing development correlation evidence; no confirmation-based clustering."""
    rows = lock["candidates"]
    ids = {r["canonical_feature"] for r in rows}
    alias = {
        a: r["canonical_feature"] for r in rows for a in [r["canonical_feature"], *r["aliases"]]
    }
    parent = {i: i for i in ids}

    def find(i: str) -> str:
        while parent[i] != i:
            i = parent[i]
        return i

    path = root / "data/features/2026-04-01/audit.json"
    if not path.exists():
        raise ValueError("known development correlation audit is required")
    evidence = json.loads(path.read_text())
    edges = []
    for row in evidence["high_correlation_pairs"]:
        a, b = alias.get(row["feature_id_a"]), alias.get(row["feature_id_b"])
        if a and b and a != b:
            x, y = sorted([find(a), find(b)])
            parent[y] = x
            edges.append(row)
    return {
        "source_path": str(path.relative_to(root)),
        "source_sha256": file_sha(path),
        "interpretation": "known all-asset development snapshot correlations; diagnostic only",
        "edges": edges,
        "correlation_group": {i: find(i) for i in sorted(ids)},
    }


def initialize_protocol(root: Path, config: Path, output: Path) -> dict[str, Any]:
    settings = tomllib.loads(config.read_text())
    for name, expected in settings.get("development_source_sha256", {}).items():
        if file_sha(root / "src/hocus_quant" / name) != expected:
            raise ValueError("development feature/target/eligibility source changed")
    if (
        settings["target_id"] != "future.direction_abs.h5.v1"
        or settings["scope"] != "equity"
        or settings["primary_cohort"] != "strict_candidates"
        or settings["retuning_allowed"]
        or settings["checkpoints"] != [8, 13, 26]
        or settings["target_mature_cutoffs"] != 26
    ):
        raise ValueError("unsupported V1 protocol; create a new protocol version")
    frozen_path = config.with_suffix(".freeze.json")
    protocol: dict[str, Any]
    if frozen_path.exists():
        protocol = json.loads(frozen_path.read_text())
        verify_protocol(root, config, protocol)
    else:
        lock = json.loads((root / settings["lock_path"]).read_text())
        verify_lock(lock)
        if lock["contract"]["feature_registry_sha256"] != registry_document()["sha256"]:
            raise ValueError("feature registry differs from development lock")
        if lock["lock_sha256"] != settings["candidate_lock_sha256"]:
            raise ValueError("unexpected candidate lock fingerprint")
        actual = {
            tier: sum(bool(r[tier]) for r in lock["candidates"])
            for tier in ["broad_candidates", "strong_sign_candidates", "strict_candidates"]
        }
        if actual != {
            "broad_candidates": 504,
            "strong_sign_candidates": 138,
            "strict_candidates": 85,
        }:
            raise ValueError("the original 504/138/85 lock is required")
        payload = {
            "protocol_version": "SPEC-007/1.0.0",
            "settings": settings,
            "boundary": derive_boundary(root, lock, date.fromisoformat(settings["frozen_on"])),
            "runtime_identity": runtime_identity(root),
            "known_groups": known_groups(root, lock),
            "expected_signs": {
                r["canonical_feature"]: r["locked_direction"] for r in lock["candidates"]
            },
            "pit_grade": "reconstructed",
            "strict_pit_claimed": False,
        }
        protocol = {**payload, "protocol_sha256": fingerprint(payload)}
        _write_once(frozen_path, protocol)
    output.mkdir(parents=True, exist_ok=True)
    _write_once(output / "protocol.json", protocol)
    return protocol


def _write_once(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError("immutable protocol differs; create a new protocol version")
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def verify_protocol(root: Path, config: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    if fingerprint(payload) != protocol["protocol_sha256"]:
        raise ValueError("protocol fingerprint mismatch")
    if tomllib.loads(config.read_text()) != protocol["settings"]:
        raise ValueError("statistical settings changed; a new protocol version is required")
    if runtime_identity(root) != protocol["runtime_identity"]:
        raise ValueError("feature/target/eligibility/statistical implementation changed")
    lock: dict[str, Any] = json.loads((root / protocol["settings"]["lock_path"]).read_text())
    verify_lock(lock)
    if lock["lock_sha256"] != protocol["settings"]["candidate_lock_sha256"]:
        raise ValueError("candidate lock changed")
    signs = {r["canonical_feature"]: r["locked_direction"] for r in lock["candidates"]}
    if signs != protocol["expected_signs"] or set(signs.values()) - {-1, 1}:
        raise ValueError("expected signs changed or undefined")
    return lock


def checkpoint_state(n: int, *, complete: bool = False) -> str:
    if n >= 26 and complete:
        return "confirmation_complete"
    if n >= 26:
        return "checkpoint_26"
    if n >= 13:
        return "checkpoint_13"
    if n >= 8:
        return "checkpoint_8"
    return "collecting" if n else "awaiting_new_data"


def verdict(
    n: int, mean: float | None, median: float | None, positive_fraction: float | None
) -> str:
    if n < 8 or mean is None or median is None or positive_fraction is None:
        return "insufficient_data"
    if positive_fraction > 0.6 and mean > 0 and median > 0:
        return "supportive"
    if positive_fraction < 0.4 and mean < 0 and median < 0:
        return "unsupportive"
    return "mixed"
