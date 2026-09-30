"""Frozen SPEC-005 target and broad-market benchmark registries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

TARGET_REGISTRY_VERSION = "SPEC-005/1.0.0"
BENCHMARK_REGISTRY_VERSION = "SPEC-005-benchmarks/1.0.0"
COHORT_DEFINITION_VERSION = "same_entity_family/1.0.0"
HORIZONS = (5, 10, 20, 60, 120)


@dataclass(frozen=True)
class TargetDefinition:
    target_id: str
    family: str
    horizon: int
    formula: str
    minimum_future_observations: int
    scale: str
    benchmark_required: bool
    cohort_required: bool
    formula_version: str = "v1"


TARGET_TEMPLATES: tuple[tuple[str, str, str, str, bool, bool], ...] = (
    (
        "future.return_abs.h{h}.v1",
        "return_abs",
        "P_H / P_0 - 1; P_H is the Hth close strictly after T",
        "decimal return",
        False,
        False,
    ),
    (
        "future.return_rel.h{h}.market.v1",
        "return_rel",
        "asset return_abs_H - mapped broad-market benchmark return_abs_H",
        "decimal excess return",
        True,
        False,
    ),
    (
        "future.direction_abs.h{h}.v1",
        "direction_abs",
        "sign(return_abs_H), with exact zero mapped to 0",
        "{-1, 0, +1}",
        False,
        False,
    ),
    (
        "future.direction_rel.h{h}.market.v1",
        "direction_rel",
        "sign(return_rel_H), with exact zero mapped to 0",
        "{-1, 0, +1}",
        True,
        False,
    ),
    (
        "future.volatility.h{h}.v1",
        "volatility",
        "sample std (ddof=1) of log returns between future closes T+1..T+H * sqrt(252)",
        "annualized decimal volatility",
        False,
        False,
    ),
    (
        "future.max_drawdown.h{h}.v1",
        "max_drawdown",
        "min(P_i / max(P_1..P_i) - 1), i=1..H, using future-window peaks only",
        "decimal drawdown",
        False,
        False,
    ),
    (
        "future.max_upside.h{h}.v1",
        "max_upside",
        "max(P_i / P_0 - 1), i=1..H",
        "decimal return",
        False,
        False,
    ),
    (
        "future.max_downside.h{h}.v1",
        "max_downside",
        "min(P_i / P_0 - 1), i=1..H",
        "decimal return",
        False,
        False,
    ),
    (
        "future.rank_pct.h{h}.family.v1",
        "rank_pct",
        "average ascending rank of valid return_abs_H / cohort_size, same family",
        "percentile in [0, 1]",
        False,
        True,
    ),
)


def target_registry() -> tuple[TargetDefinition, ...]:
    return tuple(
        TargetDefinition(
            target_id=target_id.format(h=horizon),
            family=family,
            horizon=horizon,
            formula=formula,
            minimum_future_observations=horizon,
            scale=scale,
            benchmark_required=benchmark_required,
            cohort_required=cohort_required,
        )
        for horizon in HORIZONS
        for (
            target_id,
            family,
            formula,
            scale,
            benchmark_required,
            cohort_required,
        ) in TARGET_TEMPLATES
    )


BENCHMARK_MAPPINGS: tuple[dict[str, Any], ...] = (
    {
        "entity_family": "equity",
        "scope": "ABC Bourse SRD / Paris equities",
        "benchmark_id": "abc-bourse-manual:market_indices:market_indices:QS0010989141",
        "benchmark_family": "index",
        "universe_id": "market_indices",
        "series_id": "market_indices:QS0010989141",
        "provider_instrument_id": "QS0010989141",
        "display_name": "CAC AllShares",
        "mapping_version": "benchmark-map/1.0.0",
        "justification": (
            "Broad French all-share index identified by the supplied ABC Bourse "
            "instrument-label workbook; selected over a sector index."
        ),
        "provenance": "data.silver/instrument_labels; market_series_history",
    },
    {
        "entity_family": "equity_de",
        "scope": "ABC Bourse German-equity universe",
        "benchmark_id": "abc-bourse-manual:market_indices:market_indices:DE0008469008",
        "benchmark_family": "index",
        "universe_id": "market_indices",
        "series_id": "market_indices:DE0008469008",
        "provider_instrument_id": "DE0008469008",
        "display_name": "DAX 40",
        "mapping_version": "benchmark-map/1.0.0",
        "justification": (
            "Explicit broad German large-cap market index present in the supplied "
            "ABC Bourse German-equity universe."
        ),
        "provenance": "data.silver/instrument_labels; market_series_history",
    },
    {
        "entity_family": "equity_us",
        "scope": "ABC Bourse US-equity universe",
        "benchmark_id": "abc-bourse-manual:market_indices:market_indices:ABC003500387",
        "benchmark_family": "index",
        "universe_id": "market_indices",
        "series_id": "market_indices:ABC003500387",
        "provider_instrument_id": "ABC003500387",
        "display_name": "S&P 500",
        "mapping_version": "benchmark-map/1.0.0",
        "justification": (
            "Explicit broad US large-cap market index present in the supplied "
            "ABC Bourse market-index universe."
        ),
        "provenance": "data.silver/instrument_labels; market_series_history",
    },
)


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def target_registry_document() -> dict[str, Any]:
    definitions = [asdict(item) for item in target_registry()]
    return {
        "registry_version": TARGET_REGISTRY_VERSION,
        "target_count": len(definitions),
        "targets": definitions,
        "sha256": _fingerprint(
            {"registry_version": TARGET_REGISTRY_VERSION, "targets": definitions}
        ),
    }


def benchmark_registry_document() -> dict[str, Any]:
    mappings = [dict(item) for item in BENCHMARK_MAPPINGS]
    return {
        "registry_version": BENCHMARK_REGISTRY_VERSION,
        "mapping_count": len(mappings),
        "mappings": mappings,
        "sha256": _fingerprint(
            {"registry_version": BENCHMARK_REGISTRY_VERSION, "mappings": mappings}
        ),
    }
