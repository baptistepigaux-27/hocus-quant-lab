"""Read-only, precomputed SPEC-006T surfaces shared by Marimo and tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from hocus_quant.analysis.candidate_lock import verify_lock


@dataclass(frozen=True)
class ResearchContractArtifacts:
    audit: dict[str, Any]
    lock: dict[str, Any]
    candidates: pl.DataFrame
    sensitivity: pl.DataFrame
    summaries: pl.DataFrame
    history: pl.DataFrame
    regimes: pl.DataFrame


def load_research_contract_artifacts(directory: Path) -> ResearchContractArtifacts:
    """Only local JSON/Parquet reads: no scans, bootstrap or lock mutation."""
    lock = json.loads((directory / "candidate_lock_v1.json").read_text())
    audit = json.loads((directory / "audit.json").read_text())
    verify_lock(lock)
    if audit["lock_sha256"] != lock["lock_sha256"]:
        raise ValueError("UI audit and candidate lock differ")
    return ResearchContractArtifacts(
        audit,
        lock,
        pl.read_parquet(directory / "candidate_explorer.parquet"),
        pl.read_parquet(directory / "ex_ante_filter_sensitivity.parquet"),
        pl.read_parquet(directory / "ic_summary.parquet"),
        pl.read_parquet(directory / "ic_history.parquet"),
        pl.read_parquet(directory / "market_regimes.parquet"),
    )
