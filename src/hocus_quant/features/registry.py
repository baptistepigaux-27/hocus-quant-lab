"""Stable, dimensionless feature identities for SPEC-003."""

from __future__ import annotations

from dataclasses import dataclass

WINDOWS = (3, 5, 10, 20, 30, 60, 120, 252, 504)
FORMULA_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_id: str
    family: str
    source_series: str
    metric: str
    window: int | None
    minimum_observations: int
    formula_version: str = FORMULA_VERSION


def _id(series: str, transform: str, metric: str, window: int | None) -> str:
    horizon = f".w{window}" if window is not None else ""
    return f"{series}.{transform}.{metric}{horizon}.{FORMULA_VERSION}"


def build_registry() -> tuple[FeatureDefinition, ...]:
    definitions: list[FeatureDefinition] = []
    level_metrics = (
        "base100",
        "mean_delta",
        "median_delta",
        "std_pct",
        "var_rel",
        "min_delta",
        "max_delta",
        "q10_delta",
        "q25_delta",
        "q75_delta",
        "q90_delta",
        "range_pct",
        "skewness",
        "kurtosis",
    )
    return_metrics = (
        "mean",
        "median",
        "std",
        "variance",
        "min",
        "max",
        "q10",
        "q25",
        "q75",
        "q90",
        "skewness",
        "kurtosis",
    )
    for series in ("open", "high", "low", "close"):
        for window in WINDOWS:
            for metric in level_metrics:
                definitions.append(
                    FeatureDefinition(
                        _id(series, "level", metric, window),
                        "distribution",
                        series,
                        metric,
                        window,
                        max(2, window),
                    )
                )
            for metric in ("trend_pct", "trend_tstat", "trend_r2", "residual_pct", "autocorr1"):
                definitions.append(
                    FeatureDefinition(
                        _id(series, "log", metric, window),
                        "trend",
                        f"log_{series}",
                        metric,
                        window,
                        max(3, window),
                    )
                )
    for series in ("close_return", "close_log_return"):
        for window in WINDOWS:
            for metric in return_metrics:
                definitions.append(
                    FeatureDefinition(
                        _id(
                            "close",
                            "return"
                            if series.endswith("return") and not series.endswith("log_return")
                            else "log_return",
                            metric,
                            window,
                        ),
                        "returns",
                        series,
                        metric,
                        window,
                        max(2, window),
                    )
                )
    structure = (
        "high_low_rel",
        "close_open_return",
        "overnight_gap",
        "candle_body",
        "upper_wick",
        "lower_wick",
        "close_location",
        "true_range_pct",
        "atr_pct",
        "positive_share",
        "negative_share",
        "gap_frequency",
    )
    for window in WINDOWS:
        for metric in structure:
            definitions.append(
                FeatureDefinition(
                    _id("ohlc", "relation", metric, window),
                    "ohlc",
                    "ohlc",
                    "mean",
                    window,
                    max(2, window),
                )
            )
        definitions.append(
            FeatureDefinition(
                _id("volume", "relative", "current_vs_mean", window),
                "volume",
                "volume",
                "current_vs_mean",
                window,
                max(2, window),
            )
        )
        definitions.append(
            FeatureDefinition(
                _id("close", "log_return", "realized_volatility_pct", window),
                "technical",
                "close_log_return",
                "realized_volatility_pct",
                window,
                max(3, window - 1),
            )
        )
    indicators = (
        ("rsi", 14),
        ("macd_line_pct", 34),
        ("macd_signal_pct", 34),
        ("macd_hist_pct", 34),
        ("stochastic_k", 14),
        ("stochastic_d", 16),
        ("williams_r", 14),
        ("cci", 20),
        ("adx", 28),
        ("plus_di", 14),
        ("minus_di", 14),
        ("roc_pct", 13),
        ("momentum_pct", 21),
        ("bollinger_position", 20),
        ("bollinger_bandwidth_pct", 20),
        ("atr_pct", 14),
        ("obv_change_fraction", 20),
        ("mfi", 14),
        ("accumulation_distribution_fraction", 20),
        ("ema_distance_pct", 20),
        ("sma_distance_pct", 20),
    )
    for metric, minimum in indicators:
        definitions.append(
            FeatureDefinition(
                _id("ohlc", "technical", metric, minimum),
                "technical",
                "ohlc_volume",
                metric,
                minimum,
                minimum,
            )
        )
    ids = [item.feature_id for item in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("feature registry contains duplicate IDs")
    return tuple(definitions)


FEATURE_REGISTRY = build_registry()
