"""Review-oriented diagnostics for the SPEC-003 golden feature slice."""

from __future__ import annotations

import math
from collections import Counter
from datetime import date
from typing import Any, cast

import numpy as np

from hocus_quant.features.registry import FeatureDefinition

REPRESENTATIVE_FEATURES = (
    "close.level.mean_delta.w20.v1",
    "close.log.trend_pct.w20.v1",
    "close.log.trend_tstat.w20.v1",
    "close.level.std_pct.w20.v1",
    "close.log_return.realized_volatility_pct.w20.v1",
    "ohlc.technical.rsi.w15.v2",
    "ohlc.technical.atr_pct.w14.v1",
    "volume.relative.current_vs_mean.w20.v1",
)


def create_hardening_audit(
    *,
    entities: list[dict[str, Any]],
    definitions: tuple[FeatureDefinition, ...],
    values: np.ndarray,
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Describe feature-level extremes and family distributions without modifying data."""
    index_by_id = {definition.feature_id: index for index, definition in enumerate(definitions)}
    extreme_details: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for item in audit["extreme_features"]:
        index = index_by_id[item["feature_id"]]
        x = values[:, index]
        finite = np.flatnonzero(np.isfinite(x))
        if not len(finite):
            continue
        # Keep three distinct examples at each tail; source bars make this reviewable.
        low = sorted(finite, key=lambda i: float(x[i]))[:3]
        high = sorted(finite, key=lambda i: float(x[i]), reverse=True)[:3]
        samples: list[dict[str, Any]] = []
        feature_diagnoses: Counter[str] = Counter()
        seen: set[int] = set()
        for idx in low + high:
            if int(idx) in seen:
                continue
            seen.add(int(idx))
            entity = entities[int(idx)]
            observations = entity["observations"]
            horizon = definitions[index].window or len(observations)
            diagnostic_window = observations[-horizon:]
            diagnosis, action, evidence = _diagnose(
                float(x[idx]), item["feature_id"], diagnostic_window
            )
            feature_diagnoses[diagnosis] += 1
            samples.append(
                {
                    "entity_id": entity["entity_id"],
                    "entity_family": entity["entity_family"],
                    "value": float(x[idx]),
                    "classification": diagnosis,
                    "evidence": evidence,
                    "action": action,
                    "source_values_near_cutoff": [
                        {
                            "session_date": _iso(row["session_date"]),
                            **{
                                field: _number(row.get(field))
                                for field in ("open", "high", "low", "close", "volume")
                            },
                        }
                        for row in observations[-5:]
                    ],
                }
            )
        primary_diagnosis = feature_diagnoses.most_common(1)[0][0]
        counts[primary_diagnosis] += 1
        extreme_details.append(
            {
                "feature_id": item["feature_id"],
                "feature_family": definitions[index].family,
                "horizon_observations": definitions[index].window,
                "p01": item["p01"],
                "p50": item["median"],
                "p99": item["p99"],
                "min": item["min"],
                "max": item["max"],
                "primary_classification": primary_diagnosis,
                "samples": samples,
            }
        )

    family_distributions: dict[str, list[dict[str, Any]]] = {}
    families = np.asarray([entity["entity_family"] for entity in entities], dtype=object)
    for feature_id in REPRESENTATIVE_FEATURES:
        column_index = index_by_id.get(feature_id)
        if column_index is None:
            continue
        for family in sorted(set(families)):
            sample = values[families == family, column_index]
            sample = sample[np.isfinite(sample)]
            if not len(sample):
                continue
            q = np.quantile(sample, [0.01, 0.5, 0.99])
            family_distributions.setdefault(str(family), []).append(
                {
                    "feature_id": feature_id,
                    "available_count": int(len(sample)),
                    "mean": float(np.mean(sample)),
                    "std": float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0,
                    "p01": float(q[0]),
                    "p50": float(q[1]),
                    "p99": float(q[2]),
                }
            )

    family_correlations: list[dict[str, Any]] = []
    for pair in audit["high_correlation_pairs"]:
        left = index_by_id[pair["feature_id_a"]]
        right = index_by_id[pair["feature_id_b"]]
        for family in sorted(set(families)):
            mask = families == family
            x, y = values[mask, left], values[mask, right]
            valid = np.isfinite(x) & np.isfinite(y)
            if int(valid.sum()) < 20 or np.std(x[valid]) <= 1e-12 or np.std(y[valid]) <= 1e-12:
                continue
            correlation = float(np.corrcoef(x[valid], y[valid])[0, 1])
            if math.isfinite(correlation) and abs(correlation) >= 0.95:
                family_correlations.append(
                    {
                        "entity_family": str(family),
                        "feature_id_a": pair["feature_id_a"],
                        "feature_id_b": pair["feature_id_b"],
                        "n": int(valid.sum()),
                        "correlation": correlation,
                    }
                )

    return {
        "as_of_date": audit["as_of_date"],
        "pit_grade": audit["pit_grade"],
        "extreme_feature_count": len(extreme_details),
        "extreme_classification_sample_counts": dict(sorted(counts.items())),
        "extreme_features": extreme_details,
        "family_distributions": family_distributions,
        "source_quality": _source_quality(entities),
        "correlation_interpretation": [
            {
                **pair,
                "interpretation": _correlation_interpretation(
                    pair["feature_id_a"], pair["feature_id_b"]
                ),
            }
            for pair in audit["high_correlation_pairs"]
        ],
        "high_correlations_by_family": family_correlations,
        "policy": "diagnostic only: no clipping, winsorization, suppression or feature removal",
    }


def _diagnose(
    value: float, feature_id: str, observations: list[dict[str, Any]]
) -> tuple[str, str, str]:
    close = [float(row["close"]) for row in observations if _is_positive(row.get("close"))]
    bad_ohlc = any(_has_ohlc_envelope_violation(row) for row in observations)
    if bad_ohlc:
        return (
            "ohlc_incoherence_candidate",
            "Check source OHLC rows and provider corrections before use.",
            "bars inside this feature's observation window violate the OHLC envelope",
        )
    if len(close) > 1 and close[-1] <= float(np.median(close)) * 0.01:
        return (
            "relative_denominator_collapse",
            "Inspect for discontinuity or data-quality issues. Nominal price "
            "units alone do not trigger this check.",
            "cutoff close is less than 1% of the window median "
            f"({close[-1]:.8g} vs {float(np.median(close)):.8g})",
        )
    returns = [b / a - 1 for a, b in zip(close, close[1:], strict=False) if a > 0]
    if returns and max(abs(item) for item in returns) >= 0.30:
        return (
            "discontinuity_or_corporate_action_candidate",
            "Verify split/action history and source continuity; no automatic adjustment.",
            "window absolute close return max="
            f"{max(abs(item) for item in returns):.4g}; cause is unverified",
        )
    parts = feature_id.split(".")
    metric = parts[-3] if parts[-2].startswith("w") else parts[-2]
    bounded = {
        "rsi": (0, 100),
        "stochastic_k": (0, 100),
        "stochastic_d": (0, 100),
        "williams_r": (-100, 0),
        "bollinger_position": (0, 1),
        "close_location": (-1, 1),
        "positive_share": (0, 1),
        "negative_share": (0, 1),
        "gap_frequency": (0, 1),
    }
    if metric in bounded and bounded[metric][0] - 1e-8 <= value <= bounded[metric][1] + 1e-8:
        return (
            "normal_indicator_range",
            "No correction; retain the bounded indicator value.",
            f"value is within expected [{bounded[metric][0]}, {bounded[metric][1]}] range",
        )
    if abs(value) > 500 and ".w3." in feature_id:
        return (
            "short_window_formula_instability",
            "Review bar continuity and the three-observation denominator; "
            "retain pending diagnosis.",
            f"absolute normalized value={abs(value):.6g} on a 3-row window",
        )
    if abs(value) > 30:
        return (
            "heavy_tail_or_discontinuity_review",
            "Inspect the listed source bars; no winsorization applied.",
            f"tail magnitude={abs(value):.6g}; OHLC alone cannot identify a corporate action",
        )
    return (
        "family_or_sample_tail_review",
        "Compare within-family distribution and source history before changing the formula.",
        "feature-level threshold flagged this value; listed source bars are available for review",
    )


def _has_ohlc_envelope_violation(row: dict[str, Any]) -> bool:
    values = [row.get(field) for field in ("open", "high", "low", "close")]
    if not all(_is_positive(value) for value in values):
        return False
    open_value, high, low, close_value = (float(cast(float, value)) for value in values)
    return (
        low > high
        or low > min(open_value, close_value) * 1.02
        or high < max(open_value, close_value) * 0.98
    )


def _source_quality(entities: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, dict[str, int]] = {}
    candidates: list[dict[str, Any]] = []
    for entity in entities:
        family = str(entity["entity_family"])
        stats = result.setdefault(
            family,
            {
                "entity_count": 0,
                "bar_count": 0,
                "ohlc_incoherent_bars": 0,
                "ohlc_incoherent_entities": 0,
                "wide_range_bars_gt_50pct": 0,
                "wide_range_entities_gt_50pct": 0,
                "close_jump_bars_gt_30pct": 0,
                "close_jump_entities_gt_30pct": 0,
            },
        )
        stats["entity_count"] += 1
        rows = entity["observations"]
        stats["bar_count"] += len(rows)
        invalid_count = 0
        wide_count = 0
        jump_count = 0
        max_range = 0.0
        prior: float | None = None
        for row in rows:
            invalid_count += int(_has_ohlc_envelope_violation(row))
            high, low, close_value = row.get("high"), row.get("low"), row.get("close")
            if (
                _is_positive(close_value)
                and high is not None
                and low is not None
                and float(cast(float, high)) > float(cast(float, low))
            ):
                range_ratio = (float(cast(float, high)) - float(cast(float, low))) / float(
                    cast(float, close_value)
                )
                wide_count += int(range_ratio > 0.5)
                max_range = max(max_range, range_ratio)
            if _is_positive(prior) and _is_positive(close_value):
                jump_count += int(
                    abs(float(cast(float, close_value)) / float(cast(float, prior)) - 1) >= 0.30
                )
            prior = float(close_value) if _is_positive(close_value) else None
        stats["ohlc_incoherent_bars"] += invalid_count
        stats["wide_range_bars_gt_50pct"] += wide_count
        stats["close_jump_bars_gt_30pct"] += jump_count
        stats["ohlc_incoherent_entities"] += int(invalid_count > 0)
        stats["wide_range_entities_gt_50pct"] += int(wide_count > 0)
        stats["close_jump_entities_gt_30pct"] += int(jump_count > 0)
        if invalid_count or wide_count or jump_count:
            candidates.append(
                {
                    "entity_id": entity["entity_id"],
                    "entity_family": family,
                    "ohlc_incoherent_bars": invalid_count,
                    "wide_range_bars_gt_50pct": wide_count,
                    "close_jump_bars_gt_30pct": jump_count,
                    "max_intraday_range_over_close": max_range,
                }
            )
    candidates.sort(
        key=lambda row: (
            -row["ohlc_incoherent_bars"],
            -row["wide_range_bars_gt_50pct"],
            -row["close_jump_bars_gt_30pct"],
        )
    )
    return {"by_family": result, "candidate_entities_top_30": candidates[:30]}


def _correlation_interpretation(left: str, right: str) -> str:
    a, b = left.split("."), right.split(".")
    if left == right:
        return "quasi_duplicate_math"
    same_window = a[-2] == b[-2]
    same_series_transform = a[:2] == b[:2]
    metric_a = a[-3] if a[-2].startswith("w") else a[-2]
    metric_b = b[-3] if b[-2].startswith("w") else b[-2]
    mean_metrics = {"mean_delta", "median_delta", "mean", "median"}
    if same_series_transform and same_window and {metric_a, metric_b} <= mean_metrics:
        return "quasi_duplicate_math"
    if same_series_transform and same_window:
        return "expected_redundancy_same_series_window"
    if same_window:
        return "technically_distinct_but_near"
    return "sample_correlation_requires_review"


def render_hardening_report(report: dict[str, Any]) -> str:
    lines = [
        "# SPEC-003R — feature hardening audit",
        "",
        f"- Cutoff: `{report['as_of_date']}`",
        f"- PIT grade: **{report['pit_grade']}** "
        "(ABC backfill convention; not strict/observed PIT)",
        f"- Feature IDs flagged extreme: **{report['extreme_feature_count']}**",
        "- Interpretations are triage heuristics over the available bars, "
        "not verified corporate-action diagnoses.",
        "- No features or values were removed, clipped or winsorized.",
        "",
        "## Source quality across included history",
        "",
        "Screening counts only: large moves and ranges need source review and "
        "do not alone prove an error.",
        "",
        "| Family | Entities | Bars | Invalid OHLC bars/entities | "
        "Range >50% bars/entities | Close jump ≥30% bars/entities |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for family, stats in report["source_quality"]["by_family"].items():
        lines.append(
            f"| {family} | {stats['entity_count']} | {stats['bar_count']} | "
            f"{stats['ohlc_incoherent_bars']} / {stats['ohlc_incoherent_entities']} | "
            f"{stats['wide_range_bars_gt_50pct']} / {stats['wide_range_entities_gt_50pct']} | "
            f"{stats['close_jump_bars_gt_30pct']} / {stats['close_jump_entities_gt_30pct']} |"
        )
    lines.extend(
        [
            "",
            "Highest-count source candidates (screen only; verify raw source before correction):",
            "",
            "| Entity | Family | OHLC violations | Range >50% | Close jumps ≥30% | "
            "Max range / close |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["source_quality"]["candidate_entities_top_30"]:
        lines.append(
            f"| `{row['entity_id']}` | {row['entity_family']} | "
            f"{row['ohlc_incoherent_bars']} | {row['wide_range_bars_gt_50pct']} | "
            f"{row['close_jump_bars_gt_30pct']} | "
            f"{row['max_intraday_range_over_close']:.6g} |"
        )
    lines.extend(
        [
            "",
            "## Primary classification of the 348 flagged feature IDs",
            "",
            "Classification uses up to six tail entities per feature. It is a "
            "review priority, not a causal determination.",
            "",
        ]
    )
    lines.extend(
        f"- `{category}`: {count} feature IDs"
        for category, count in report["extreme_classification_sample_counts"].items()
    )
    lines.extend(
        [
            "",
            "## Extreme feature inventory",
            "",
            "Each row records p01/p50/p99 plus up to three lowest and three "
            "highest entities, with the final five source bars.",
            "",
        ]
    )
    for feature in report["extreme_features"]:
        lines.extend(
            [
                f"### `{feature['feature_id']}` — {feature['feature_family']}, "
                f"H={feature['horizon_observations']}",
                "",
                f"Primary classification: **{feature['primary_classification']}**. "
                f"p01 `{feature['p01']:.8g}` · p50 `{feature['p50']:.8g}` "
                f"· p99 `{feature['p99']:.8g}` · min `{feature['min']:.8g}` "
                f"· max `{feature['max']:.8g}`",
                "",
                "| Entity | Family | Value | Classification | Evidence / action | "
                "Last five source bars (date O/H/L/C/V) |",
                "| --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for sample in feature["samples"]:
            bars = "<br>".join(
                " ".join(
                    str(row[key])
                    for key in ("session_date", "open", "high", "low", "close", "volume")
                )
                for row in sample["source_values_near_cutoff"]
            )
            cells: tuple[str, ...] = (
                f"`{sample['entity_id']}`",
                sample["entity_family"],
                f"{sample['value']:.8g}",
                sample["classification"],
                f"{sample['evidence']}; {sample['action']}",
                bars,
            )
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines.extend(
        [
            "## Per-family representative distributions",
            "",
            "Mean, sample standard deviation, p01/p50/p99 are computed "
            "independently by family. This is descriptive only.",
            "",
        ]
    )
    for family, rows in report["family_distributions"].items():
        lines.extend(
            [
                f"### {family}",
                "",
                "| Feature | n | Mean | Std | p01 | p50 | p99 |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in rows:
            cells = (
                f"`{row['feature_id']}`",
                str(row["available_count"]),
                f"{row['mean']:.8g}",
                f"{row['std']:.8g}",
                f"{row['p01']:.8g}",
                f"{row['p50']:.8g}",
                f"{row['p99']:.8g}",
            )
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    lines.extend(
        [
            "## High-correlation review",
            "",
            "| Feature A | Feature B | r | Interpretation |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for row in report["correlation_interpretation"]:
        cells = (
            f"`{row['feature_id_a']}`",
            f"`{row['feature_id_b']}`",
            f"{row['correlation']:.6f}",
            row["interpretation"],
        )
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "Family-specific high correlations (n ≥ 20, |r| ≥ 0.95):",
            "",
            "| Family | Feature A | Feature B | n | r |",
            "| --- | --- | --- | ---: | ---: |",
        ]
    )
    for row in report["high_correlations_by_family"]:
        cells = (
            row["entity_family"],
            f"`{row['feature_id_a']}`",
            f"`{row['feature_id_b']}`",
            str(row["n"]),
            f"{row['correlation']:.6f}",
        )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _is_positive(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float | None:
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _iso(value: date | Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
