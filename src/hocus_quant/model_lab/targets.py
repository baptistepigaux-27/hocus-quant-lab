"""Additive target registry and exact future-path formulas for SPEC-008."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
from scipy.stats import rankdata

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.targets.registry import TargetDefinition, target_registry, target_registry_document

FAMILIES = (
    "direction_abs",
    "return_abs",
    "direction_rel",
    "rank_pct",
    "excursion_balance",
    "trend_tstat",
)
HORIZONS = (5, 10)
REGISTRY_VERSION = "SPEC-008-targets/1.0.0"


def registry_document() -> dict[str, Any]:
    added = [
        TargetDefinition(f"future.{family}.h{h}.v1", family, h, formula, h, scale, False, False)
        for h in HORIZONS
        for family, formula, scale in [
            (
                "excursion_balance",
                "max(P_h/P_0-1)+min(P_h/P_0-1), h=1..H; no zero anchoring",
                "decimal return",
            ),
            (
                "trend_tstat",
                "OLS slope/SE(slope) of B_h=100*P_h/P_1, h=1..H; df=H-2",
                "t statistic",
            ),
        ]
    ]
    payload = {
        "version": REGISTRY_VERSION,
        "parent_sha256": target_registry_document()["sha256"],
        "definitions": [asdict(t) for t in (*target_registry(), *added)],
        "numerical_limit": (
            "flat=0; exact nonflat linear=sign(slope)*1e6; finite t clipped to +/-1e6"
        ),
        "rank_cohort": "eligible at T, interpretable observable return_abs; avg ascending rank/N",
    }
    return {**payload, "sha256": fingerprint(payload)}


def target_id(family: str, horizon: int) -> str:
    suffix = (
        "market.v1" if family == "direction_rel" else "family.v1" if family == "rank_pct" else "v1"
    )
    return f"future.{family}.h{horizon}.{suffix}"


def future_path(reference: float, closes: Any, horizon: int) -> dict[str, float | None]:
    """Use exactly H closes, strictly after T. Extras cannot change a target."""
    p = np.asarray(closes, dtype=float)[:horizon]
    if horizon not in HORIZONS:
        raise ValueError("only H5/H10")
    if len(p) != horizon or not np.isfinite(p).all() or np.any(p <= 0) or reference <= 0:
        return dict.fromkeys(
            [
                "return_abs",
                "direction_abs",
                "excursion_balance",
                "trend_tstat",
                "max_upside",
                "max_downside",
                "volatility",
            ]
        )
    r = p / reference - 1
    b = 100 * p / p[0]
    t = np.arange(1, horizon + 1, dtype=float)
    tc, bc = t - t.mean(), b - b.mean()
    sxx = float(tc @ tc)
    slope = float(tc @ bc / sxx)
    residual = bc - slope * tc
    se = float(np.sqrt((residual @ residual) / (horizon - 2) / sxx))
    tolerance = 1e-12 * max(1.0, float(np.max(np.abs(b))))
    if float(np.ptp(b)) <= tolerance:
        stat = 0.0
    elif se <= tolerance:
        stat = float(np.copysign(1e6, slope))
    else:
        stat = float(np.clip(slope / se, -1e6, 1e6))
    return {
        "return_abs": float(r[-1]),
        "direction_abs": float(np.sign(r[-1])),
        "excursion_balance": float(r.max() + r.min()),
        "trend_tstat": stat,
        "max_upside": float(r.max()),
        "max_downside": float(r.min()),
        "volatility": float(np.std(np.diff(np.log(p)), ddof=1) * np.sqrt(252)),
    }


def rank_targets(values: Any) -> Any:
    values = np.asarray(values, dtype=float)
    good = np.isfinite(values)
    out = np.full(len(values), np.nan)
    if good.any():
        out[good] = rankdata(values[good], method="average") / good.sum()
    return out
