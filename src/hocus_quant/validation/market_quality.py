"""Deterministic, point-in-time quality screening for market series.

Quality decisions describe source observations. They never mutate or repair them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any

QUALITY_RULE_VERSION = "SPEC-003Q/1.0.0"
QUALITY_RULES: dict[str, dict[str, Any]] = {
    "hard": {
        "ohlc_envelope_tolerance_fraction_of_close": 0.02,
        "non_finite_numeric": True,
        "high_below_low": True,
        "negative_volume": True,
    },
    "review": {
        "absolute_close_move_fraction": 0.30,
        "intraday_range_fraction_of_close": 0.50,
        "scale_ratio_targets": [0.01, 0.1, 10.0, 100.0],
        "scale_ratio_relative_tolerance": 0.02,
        "probable_split_factors": [2.0, 3.0, 4.0, 5.0, 10.0],
        "split_volume_relative_tolerance": 0.25,
    },
}
QUALITY_RULES_SHA256 = hashlib.sha256(
    json.dumps(QUALITY_RULES, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


def assess_series(entity: dict[str, Any]) -> dict[str, Any]:
    """Return a stable decision using only observations already available to the caller."""
    observations = sorted(entity["observations"], key=lambda row: row["session_date"])
    hard_evidence: list[dict[str, Any]] = []
    review_evidence: list[dict[str, Any]] = []
    types: set[str] = set()
    prior_close: float | None = None
    prior_volume: float | None = None
    prior_date: Any = None
    for row in observations:
        day = row["session_date"]
        ohlc = {name: _number(row.get(name)) for name in ("open", "high", "low", "close")}
        volume = _number(row.get("volume"))
        if any(row.get(name) is not None and ohlc[name] is None for name in ohlc):
            hard_evidence.append({"date": day.isoformat(), "rule": "non_finite_numeric"})
            types.add("possible_parse_error")
        if volume is not None and volume < 0:
            hard_evidence.append(
                {"date": day.isoformat(), "rule": "negative_volume", "volume": volume}
            )
            types.add("possible_parse_error")
        high, low, open_value, close = (
            ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
        )
        if high is not None and low is not None and high < low:
            hard_evidence.append(
                {"date": day.isoformat(), "rule": "high_below_low", "high": high, "low": low}
            )
            types.add("ohlc_inconsistent")
        if close is not None and close > 0:
            tolerance = close * QUALITY_RULES["hard"]["ohlc_envelope_tolerance_fraction_of_close"]
            gaps = {
                "open_above_high": max(0.0, (open_value or 0.0) - high)
                if open_value is not None and high is not None
                else 0.0,
                "open_below_low": max(0.0, low - open_value)
                if open_value is not None and low is not None
                else 0.0,
                "close_above_high": max(0.0, close - high) if high is not None else 0.0,
                "close_below_low": max(0.0, low - close) if low is not None else 0.0,
            }
            bad = {field: gap for field, gap in gaps.items() if gap > tolerance}
            if bad:
                hard_evidence.append(
                    {
                        "date": day.isoformat(),
                        "rule": "ohlc_envelope_exceeded_2pct",
                        "ohlc": ohlc,
                        "gaps": bad,
                        "tolerance": tolerance,
                    }
                )
                types.add("ohlc_inconsistent")
        if close is not None and close > 0 and high is not None and low is not None:
            range_fraction = (high - low) / close
            if range_fraction > QUALITY_RULES["review"]["intraday_range_fraction_of_close"]:
                review_evidence.append(
                    {
                        "date": day.isoformat(),
                        "rule": "intraday_range_over_50pct",
                        "range_fraction": range_fraction,
                    }
                )
                types.add("large_move_plausible")
        if prior_close is not None and close is not None and prior_close > 0 and close > 0:
            ratio = close / prior_close
            move = abs(ratio - 1.0)
            if move >= QUALITY_RULES["review"]["absolute_close_move_fraction"]:
                inverse_volume_match = False
                if prior_volume and volume and volume > 0:
                    volume_ratio = volume / prior_volume
                    candidate_factor = max(ratio, 1.0 / ratio)
                    inverse_volume_match = abs(volume_ratio * ratio - 1.0) <= QUALITY_RULES[
                        "review"
                    ]["split_volume_relative_tolerance"]
                    split_match = any(
                        abs(candidate_factor / factor - 1.0)
                        <= QUALITY_RULES["review"]["scale_ratio_relative_tolerance"]
                        for factor in QUALITY_RULES["review"]["probable_split_factors"]
                    )
                else:
                    split_match = False
                kind = (
                    "probable_split_or_corporate_action"
                    if split_match and inverse_volume_match
                    else "large_move_plausible"
                )
                types.add(kind)
                evidence = {
                    "date": day.isoformat(),
                    "previous_date": prior_date.isoformat() if prior_date else None,
                    "rule": "close_move_over_30pct",
                    "close_ratio": ratio,
                    "absolute_move_fraction": move,
                }
                if volume is not None and prior_volume is not None and prior_volume != 0:
                    evidence["volume_ratio"] = volume / prior_volume
                review_evidence.append(evidence)
            scale_ratio = next(
                (
                    target
                    for target in QUALITY_RULES["review"]["scale_ratio_targets"]
                    if abs(ratio / target - 1.0)
                    <= QUALITY_RULES["review"]["scale_ratio_relative_tolerance"]
                ),
                None,
            )
            if scale_ratio is not None:
                review_evidence.append(
                    {
                        "date": day.isoformat(),
                        "previous_date": prior_date.isoformat() if prior_date else None,
                        "rule": "possible_scale_change",
                        "close_ratio": ratio,
                        "matched_target": scale_ratio,
                    }
                )
                types.add("probable_scale_change")
        prior_close = close if close is not None else prior_close
        prior_volume = volume if volume is not None else prior_volume
        prior_date = day

    status = "quarantined" if hard_evidence else "review" if review_evidence else "approved"
    if not types:
        types.add("no_issue_found")
    evidence_rows: list[dict[str, Any]] = (
        hard_evidence if hard_evidence else review_evidence[:50]
    )
    if len(review_evidence) > 50:
        evidence_rows.append(
            {"rule": "evidence_truncated", "omitted": len(review_evidence) - 50}
        )
    reasons = sorted(types)
    return {
        "entity_id": entity["entity_id"],
        "entity_family": entity["entity_family"],
        "quality_status": status,
        "quality_reason": "; ".join(reasons),
        "diagnostic_types": reasons,
        "quality_evidence": evidence_rows,
        "evidence_count": len(hard_evidence) + len(review_evidence),
        "review_rule_version": QUALITY_RULE_VERSION,
        "review_rule_sha256": QUALITY_RULES_SHA256,
        "observations_as_of": (
            observations[-1]["session_date"].isoformat() if observations else None
        ),
    }


def summarize_decisions(decisions: list[dict[str, Any]], as_of_date: str) -> dict[str, Any]:
    by_status = Counter(item["quality_status"] for item in decisions)
    by_family: dict[str, dict[str, int]] = {}
    for item in decisions:
        family = item["entity_family"]
        status = item["quality_status"]
        bucket = by_family.setdefault(family, {"approved": 0, "review": 0, "quarantined": 0})
        bucket[status] += 1
    return {
        "spec": "SPEC-003Q",
        "as_of_date": as_of_date,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "quality_rule_sha256": QUALITY_RULES_SHA256,
        "quality_rules": QUALITY_RULES,
        "series_count": len(decisions),
        "quality_status_counts": {
            name: by_status.get(name, 0) for name in ("approved", "review", "quarantined")
        },
        "quality_status_by_family": by_family,
        "decisions": decisions,
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
