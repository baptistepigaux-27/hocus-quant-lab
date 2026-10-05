"""Deterministic discovery rank groups and immutable H5 candidate locks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy.stats import rankdata

TARGET = "future.direction_abs.h5.v1"


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def rank_signature_groups(discovery: pl.DataFrame) -> pl.DataFrame:
    """Exact date-local average ranks plus entity/missingness identity, no targets.

    Twice the average rank is an integer, so signatures use lossless integers,
    rather than rounded floating point ranks. Opposite ranks remain distinct.
    """
    keys = ["as_of_date", "entity_id", "feature_id"]
    if discovery.select(keys).is_duplicated().any():
        raise ValueError("duplicate discovery feature keys")
    ids = sorted(discovery["feature_id"].unique().to_list())
    hashes = {feature: hashlib.sha256(b"date-local-average-rank/1") for feature in ids}
    counts = dict.fromkeys(ids, 0)
    for partition in discovery.sort("as_of_date").partition_by("as_of_date", maintain_order=True):
        day = str(partition["as_of_date"][0])
        matrix = partition.pivot(on="feature_id", index="entity_id", values="feature_value")
        matrix = matrix.sort("entity_id")
        identity = json.dumps([day, matrix["entity_id"].to_list()], separators=(",", ":"))
        for feature in ids:
            values = (
                matrix[feature].to_numpy().astype(float)
                if feature in matrix.columns
                else np.full(matrix.height, np.nan)
            )
            finite = np.isfinite(values)
            ranks = np.full(matrix.height, -1, dtype="<i8")
            ranks[finite] = (2 * rankdata(values[finite], method="average")).astype("<i8")
            hashes[feature].update(identity.encode())
            hashes[feature].update(ranks.tobytes())
            counts[feature] += int(finite.sum())
    groups: dict[str, list[str]] = {}
    for feature in ids:
        if counts[feature] == 0:
            continue
        groups.setdefault(hashes[feature].hexdigest(), []).append(feature)
    return pl.DataFrame(
        [
            {
                "rank_signature": signature,
                "canonical_feature": aliases[0],
                "aliases": aliases[1:],
                "group_size": len(aliases),
                "discovery_observations": counts[aliases[0]],
                "signature_period": "2024_discovery",
                "canonical_rule": "lexicographic_feature_id",
            }
            for signature, aliases in sorted(groups.items())
        ]
    )


def build_lock_document(
    candidates: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """No timestamp or mutable validation lookup enters lock identity."""
    if contract.get("target_id") != TARGET or contract.get("horizon") != 5:
        raise ValueError("candidate lock V1 accepts only absolute direction H5")
    ordered = sorted(candidates, key=lambda row: (row["discovery_rank"], row["canonical_feature"]))
    if len({row["rank_signature"] for row in ordered}) != len(ordered):
        raise ValueError("duplicate rank signatures in lock")
    if any(row.get("target_id") != TARGET for row in ordered):
        raise ValueError("non-H5 target in lock")
    payload = {"lock_version": "candidate_lock_v1", "contract": contract, "candidates": ordered}
    return {**payload, "lock_sha256": fingerprint(payload)}


def write_lock_once(path: Path, document: dict[str, Any]) -> None:
    """A changed input requires a new lock/version, never silent overwriting."""
    verify_lock(document)
    if path.exists():
        if json.loads(path.read_text()) != document:
            raise ValueError("candidate lock already exists; create an explicitly new version")
        return
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def verify_lock(document: dict[str, Any]) -> None:
    digest = document["lock_sha256"]
    if fingerprint({k: v for k, v in document.items() if k != "lock_sha256"}) != digest:
        raise ValueError("candidate lock checksum mismatch")
    if document["contract"]["target_id"] != TARGET:
        raise ValueError("candidate lock target mismatch")


def prepare_confirmation(
    document: dict[str, Any],
    *,
    first_cutoff: str,
    feature_registry_sha256: str,
    last_development_outcome_date: str,
) -> dict[str, Any]:
    """Prepare an unretuned confirmation request; does not read future outcomes."""
    from datetime import date

    verify_lock(document)
    contract = document["contract"]
    if feature_registry_sha256 != contract["feature_registry_sha256"]:
        raise ValueError("confirmation feature registry differs from candidate lock")
    boundary = max(contract["data_observed_through"], last_development_outcome_date)
    if date.fromisoformat(first_cutoff) <= date.fromisoformat(boundary):
        raise ValueError("confirmation must start beyond consulted data and outcome windows")
    return {
        "status": "pending_new_unconsulted_data",
        "first_cutoff": first_cutoff,
        "lock_sha256": document["lock_sha256"],
        "feature_registry_sha256": feature_registry_sha256,
        "target_id": TARGET,
        "retuning_allowed": False,
        "last_development_outcome_date": last_development_outcome_date,
        "execution_price_for_future_strategy": "next_open",
        "results": None,
    }
