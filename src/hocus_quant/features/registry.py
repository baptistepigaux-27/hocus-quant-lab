"""Stable, dimensionless feature identities for SPEC-003."""

from __future__ import annotations

import hashlib
import json
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
    # Keep the 13-change RSI v1 output stable; expose the conventional
    # 14-change calculation under an explicit v2 identity.
    definitions.append(
        FeatureDefinition(
            "ohlc.technical.rsi.w15.v2",
            "technical",
            "ohlc_volume",
            "rsi",
            15,
            15,
            "v2",
        )
    )
    ids = [item.feature_id for item in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("feature registry contains duplicate IDs")
    return tuple(definitions)


FEATURE_REGISTRY = build_registry()


def registry_document() -> dict[str, object]:
    """Return the frozen, serializable v1 contract and its stable fingerprint."""
    families = (
        "equity",
        "equity_us",
        "equity_de",
        "index",
        "sector_index",
        "commodity",
        "crypto",
        "fx_rates",
        "bond",
    )
    features: list[dict[str, object]] = []
    for item in FEATURE_REGISTRY:
        if item.family == "distribution":
            formula = _distribution_formula(item.metric, item.source_series)
            inputs = [item.source_series]
            scale = "percent_or_ratio_or_statistic"
        elif item.family == "trend":
            formula = {
                "trend_pct": "100 * OLS_slope(log(price), index 0..H-1) * (H-1)",
                "trend_tstat": "OLS slope / OLS slope standard error",
                "trend_r2": "OLS coefficient of determination",
                "residual_pct": "100 * (exp(last log-price OLS residual) - 1)",
                "autocorr1": "Pearson correlation(x[:-1], x[1:])",
            }[item.metric]
            inputs = [item.source_series]
            scale = "dimensionless_statistic_or_percent"
        elif item.family == "returns":
            formula = f"sample distribution statistic of {item.source_series} over H observations"
            inputs = [item.source_series]
            scale = "natural_return_or_statistic"
        elif item.family == "ohlc":
            formula = f"mean({item.metric} calculated from daily OHLC bars) over H observations"
            inputs = ["open", "high", "low", "close"]
            scale = "dimensionless_ratio_or_percent"
        elif item.family == "volume":
            formula = "latest volume / mean(volume over H observations) - 1"
            inputs = ["volume"]
            scale = "ratio"
        else:
            formula = _technical_formula(item.metric, item.formula_version)
            inputs = ["open", "high", "low", "close", "volume"]
            scale = "dimensionless_ratio_or_percent_or_statistic"
        features.append(
            {
                "feature_id": item.feature_id,
                "family": item.family,
                "formula": formula,
                "inputs": inputs,
                "horizon_observations": item.window,
                "minimum_history": item.minimum_observations,
                "output_scale": scale,
                "dimensionless": True,
                "formula_version": item.formula_version,
                "applicable_entity_families": list(families),
                "availability_condition": (
                    "requires a meaningful source volume series"
                    if item.family == "volume"
                    or item.metric
                    in {"obv_change_fraction", "mfi", "accumulation_distribution_fraction"}
                    else "requires positive finite OHLC prices"
                ),
            }
        )
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {
        "contract": "SPEC-003 feature registry",
        "registry_version": "SPEC-003",
        "freeze_policy": "formula or semantic change requires a new feature_id with v2",
        "feature_count": len(features),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "features": features,
    }


def _distribution_formula(metric: str, source: str) -> str:
    formulas = {
        "base100": "100 * x_t / x_t (= 100)",
        "mean_delta": "100 * (mean(x) / x_t - 1)",
        "median_delta": "100 * (median(x) / x_t - 1)",
        "std_pct": "100 * sample_std(x) / x_t",
        "var_rel": "sample_variance(x) / x_t^2",
        "min_delta": "100 * (min(x) / x_t - 1)",
        "max_delta": "100 * (max(x) / x_t - 1)",
        "q10_delta": "100 * (q10(x) / x_t - 1)",
        "q25_delta": "100 * (q25(x) / x_t - 1)",
        "q75_delta": "100 * (q75(x) / x_t - 1)",
        "q90_delta": "100 * (q90(x) / x_t - 1)",
        "range_pct": "100 * (max(x) - min(x)) / x_t",
    }
    return formulas.get(metric, f"{metric}(log({source})) over H observations")


def _technical_formula(metric: str, formula_version: str = "v1") -> str:
    formulas = {
        "rsi": (
            "simple-mean gain/loss RSI over 13 close differences (14 closes)"
            if formula_version == "v1"
            else "simple-mean gain/loss RSI over 14 close differences (15 closes)"
        ),
        "macd_line_pct": "100 * (EMA12(close) - EMA26(close)) / close_t",
        "macd_signal_pct": "100 * EMA9(MACD line) / close_t",
        "macd_hist_pct": "100 * (MACD line - signal) / close_t",
        "stochastic_k": "100 * (close_t - low14) / (high14 - low14)",
        "stochastic_d": "mean of last 3 stochastic K values",
        "williams_r": "-100 * (high14 - close_t) / (high14 - low14)",
        "cci": "(typical_price - SMA20) / (0.015 * mean_absolute_deviation20)",
        "adx": "mean of last 14 directional-index values",
        "plus_di": "100 * smoothed_positive_DM14 / smoothed_true_range14",
        "minus_di": "100 * smoothed_negative_DM14 / smoothed_true_range14",
        "roc_pct": "100 * (close_t / close[t-12] - 1)",
        "momentum_pct": "100 * (close_t / close[t-20] - 1)",
        "bollinger_position": "(close_t - lower20) / (upper20 - lower20)",
        "bollinger_bandwidth_pct": "100 * (upper20 - lower20) / mean(close20)",
        "atr_pct": "100 * mean(true_range14) / close_t",
        "obv_change_fraction": "signed volume over 20 intervals / total volume",
        "mfi": "money-flow ratio over 14 typical-price intervals",
        "accumulation_distribution_fraction": (
            "20-row close-location weighted volume / total volume"
        ),
        "ema_distance_pct": "100 * (close_t / EMA20(close) - 1)",
        "sma_distance_pct": "100 * (close_t / mean(close20) - 1)",
        "realized_volatility_pct": "100 * sample_std(log returns) * sqrt(252)",
        "volume.current_vs_mean": "latest volume / mean(volume over H observations) - 1",
    }
    return formulas.get(metric, f"documented v1 formula for {metric}; see docs/FEATURES.md")
