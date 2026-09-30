"""Deterministic, scale-invariant cross-sectional feature formulas."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from hocus_quant.features.registry import FEATURE_REGISTRY

_EPS = 1e-12


def compute_entity_features(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[float | None, str, int, float]]:
    """Return feature_id -> (value, status, coverage_count, coverage_ratio).

    Input must already be sorted by session date and filtered to the as-of cut.
    All exposed level statistics are normalized to the current level. Log-level
    deltas use exp(log(x)-log(x_T)), preserving invariance to unit changes.
    """
    rows = [row for row in observations if _valid_close(row.get("close"))]
    rows.sort(key=lambda row: row["session_date"])
    close = np.asarray([float(row["close"]) for row in rows], dtype=np.float64)
    if not len(close):
        return {item.feature_id: (None, "unavailable", 0, 0.0) for item in FEATURE_REGISTRY}
    opens = _array(rows, "open")
    highs = _array(rows, "high")
    lows = _array(rows, "low")
    volumes = _array(rows, "volume")
    logs: dict[str, np.ndarray] = {}
    levels: dict[str, np.ndarray] = {"open": opens, "high": highs, "low": lows, "close": close}
    for name, values in levels.items():
        valid = (values > 0) & np.isfinite(values)
        logs[name] = np.full(len(values), np.nan, dtype=np.float64)
        logs[name][valid] = np.log(values[valid])
    logs["log1p_volume"] = np.log1p(np.where(volumes >= 0, volumes, np.nan))
    close_returns = _returns(close, logarithmic=False)
    close_log_returns = _returns(close, logarithmic=True)
    structure = _ohlc_series(opens, highs, lows, close)
    results: dict[str, tuple[float | None, str, int, float]] = {}

    for item in FEATURE_REGISTRY:
        window = item.window or len(rows)
        if item.family == "distribution":
            values = levels[item.source_series]
            sample = _tail(values, window)
            value = _level_stat(item.metric, sample)
            count = int(np.isfinite(sample).sum())
        elif item.family == "trend":
            series_name = item.source_series.removeprefix("log_")
            sample = _tail(logs[series_name], window)
            value = _trend_stat(item.metric, sample, logarithmic=True)
            count = int(np.isfinite(sample).sum())
        elif item.family == "returns":
            values = (
                close_log_returns if item.source_series == "close_log_return" else close_returns
            )
            sample = _tail(values, window)
            value = _return_stat(item.metric, sample)
            count = int(np.isfinite(sample).sum())
        elif item.family == "ohlc":
            metric = item.feature_id.split(".relation.", maxsplit=1)[1].split(".w", maxsplit=1)[0]
            sample = _tail(structure[metric], window)
            if metric == "atr_pct":
                value = _finite_mean(sample)
            elif metric == "positive_share":
                value = _finite_mean((close_returns[-window:] > 0).astype(float))
                sample = close_returns[-window:]
            elif metric == "negative_share":
                value = _finite_mean((close_returns[-window:] < 0).astype(float))
                sample = close_returns[-window:]
            elif metric == "gap_frequency":
                value = _finite_mean((np.abs(sample) > 0.1).astype(float))
            else:
                value = _finite_mean(sample)
            count = int(np.isfinite(sample).sum())
        elif item.family == "volume":
            sample = _tail(volumes, window)
            finite = sample[np.isfinite(sample) & (sample >= 0)]
            value = (
                float(finite[-1] / np.mean(finite) - 1.0)
                if len(finite) == window and np.mean(finite) > 0
                else None
            )
            count = len(finite)
        else:
            metric = item.metric
            value, count = _technical(metric, opens, highs, lows, close, volumes, item.window or 1)
        coverage = min(1.0, count / window) if window else 0.0
        if count < item.minimum_observations or value is None or not math.isfinite(value):
            results[item.feature_id] = (None, "unavailable", count, coverage)
        else:
            results[item.feature_id] = (float(value), "available", count, coverage)
    return results


def _level_stat(metric: str, sample: np.ndarray) -> float | None:
    x = sample[np.isfinite(sample)]
    if not len(x) or x[-1] <= 0:
        return None
    current = float(x[-1])
    if metric == "base100":
        return 100.0 * current / current
    if metric == "mean_delta":
        return 100.0 * (float(np.mean(x)) / current - 1.0)
    if metric == "median_delta":
        return 100.0 * (float(np.median(x)) / current - 1.0)
    if metric == "std_pct":
        return 100.0 * float(np.std(x, ddof=1)) / current if len(x) > 1 else None
    if metric == "var_rel":
        return float(np.var(x, ddof=1)) / current**2 if len(x) > 1 else None
    if metric == "min_delta":
        return 100.0 * (float(np.min(x)) / current - 1.0)
    if metric == "max_delta":
        return 100.0 * (float(np.max(x)) / current - 1.0)
    if metric.endswith("_delta") and metric[0] == "q":
        quantile = int(metric[1 : metric.index("_")]) / 100
        return 100.0 * (float(np.quantile(x, quantile)) / current - 1.0)
    if metric == "range_pct":
        return 100.0 * float(np.ptp(x)) / current
    return _moment(metric, x)


def _return_stat(metric: str, sample: np.ndarray) -> float | None:
    x = sample[np.isfinite(sample)]
    if not len(x):
        return None
    if metric == "mean":
        return float(np.mean(x))
    if metric == "median":
        return float(np.median(x))
    if metric == "std":
        return float(np.std(x, ddof=1)) if len(x) > 1 else None
    if metric == "variance":
        return float(np.var(x, ddof=1)) if len(x) > 1 else None
    if metric == "min":
        return float(np.min(x))
    if metric == "max":
        return float(np.max(x))
    if metric.startswith("q"):
        return float(np.quantile(x, int(metric[1:]) / 100))
    return _moment(metric, x)


def _trend_stat(metric: str, sample: np.ndarray, *, logarithmic: bool) -> float | None:
    x = sample[np.isfinite(sample)]
    if len(x) < 3:
        return None
    t = np.arange(len(x), dtype=np.float64)
    slope, intercept = np.polyfit(t, x, 1)
    fitted = slope * t + intercept
    residuals = x - fitted
    ss_res = float(np.sum(residuals**2))
    ss_total = float(np.sum((x - np.mean(x)) ** 2))
    r2 = 1.0 - ss_res / ss_total if ss_total > _EPS else 1.0
    if metric == "trend_pct":
        return float(100.0 * slope * (len(x) - 1)) if logarithmic else None
    if metric == "trend_r2":
        return r2
    if metric == "residual_pct":
        return 100.0 * (math.exp(float(residuals[-1])) - 1.0) if logarithmic else None
    if metric == "trend_tstat":
        df = len(x) - 2
        se = math.sqrt(ss_res / df / float(np.sum((t - np.mean(t)) ** 2))) if df > 0 else 0.0
        return (
            float(slope / se)
            if se > _EPS
            else (0.0 if abs(slope) <= _EPS else math.copysign(math.inf, slope))
        )
    if metric == "autocorr1":
        return _correlation(x[:-1], x[1:])
    return None


def _technical(
    metric: str,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    period: int,
) -> tuple[float | None, int]:
    n = len(close)
    minimum = {
        "rsi": 14,
        "macd_line_pct": 34,
        "macd_signal_pct": 34,
        "macd_hist_pct": 34,
        "stochastic_k": 14,
        "stochastic_d": 16,
        "williams_r": 14,
        "cci": 20,
        "adx": 28,
        "plus_di": 14,
        "minus_di": 14,
        "roc_pct": 13,
        "momentum_pct": 21,
        "bollinger_position": 20,
        "bollinger_bandwidth_pct": 20,
        "atr_pct": 14,
        "obv_change_fraction": 21,
        "mfi": 15,
        "accumulation_distribution_fraction": 20,
        "ema_distance_pct": 20,
        "sma_distance_pct": 20,
    }.get(metric, period)
    if n < minimum:
        return None, n
    if metric == "realized_volatility_pct":
        r = _returns(close, logarithmic=True)[-period:]
        x = r[np.isfinite(r)]
        return (
            (100.0 * float(np.std(x, ddof=1)) * math.sqrt(252), len(x))
            if len(x) >= period
            else (None, len(x))
        )
    if metric == "volume.current_vs_mean":
        x = volume[-period:]
        x = x[np.isfinite(x) & (x >= 0)]
        return (
            (float(x[-1] / np.mean(x) - 1), len(x))
            if len(x) == period and np.mean(x) > 0
            else (None, len(x))
        )
    if metric.startswith("obv") or metric.startswith("mfi") or metric.startswith("accumulation"):
        valid = np.isfinite(volume) & (volume >= 0)
        if not valid[-period:].all() or n < period + 1:
            return None, int(valid[-period:].sum())
    if metric == "rsi":
        d = np.diff(close)[-(period - 1) :]
        gains, losses = np.maximum(d, 0), np.maximum(-d, 0)
        value = (
            100.0
            if np.sum(losses) == 0 and np.sum(gains) > 0
            else 50.0
            if np.sum(losses) == 0
            else 100.0 - 100.0 / (1.0 + np.mean(gains) / np.mean(losses))
        )
        return (float(value), period) if len(d) >= period - 1 else (None, len(d))
    if metric.startswith("macd"):
        if n < 34:
            return None, n
        line = _ema(close, 12) - _ema(close, 26)
        signal = _ema(line, 9)
        component = (
            line[-1]
            if metric == "macd_line_pct"
            else signal[-1]
            if metric == "macd_signal_pct"
            else line[-1] - signal[-1]
        )
        return 100.0 * float(component) / close[-1], 34
    if metric.startswith("stochastic"):
        look = 14
        hh, ll = float(np.max(highs[-look:])), float(np.min(lows[-look:]))
        k = 100 * (close[-1] - ll) / (hh - ll) if hh > ll else 50.0
        if metric == "stochastic_k":
            return float(k), look
        if n < 16:
            return None, n
        ks: list[float] = []
        for end in range(n - 3, n):
            hh_d = float(np.max(highs[end - look + 1 : end + 1]))
            ll_d = float(np.min(lows[end - look + 1 : end + 1]))
            ks.append(100 * (close[end] - ll_d) / (hh_d - ll_d) if hh_d > ll_d else 50.0)
        return float(np.mean(ks)), 16
    if metric == "williams_r":
        hh, ll = float(np.max(highs[-14:])), float(np.min(lows[-14:]))
        return (float(-100 * (hh - close[-1]) / (hh - ll)), 14) if hh > ll else (None, 14)
    if metric == "cci":
        tp = (highs + lows + close) / 3
        x = tp[-20:]
        dev = float(np.mean(np.abs(x - np.mean(x))))
        return (float((x[-1] - np.mean(x)) / (0.015 * dev)), 20) if dev > _EPS else (0.0, 20)
    if metric in {"plus_di", "minus_di", "adx"}:
        tr = _true_range(highs, lows, close)
        up, down = np.diff(highs), -np.diff(lows)
        plus_dm = np.r_[0.0, np.where((up > down) & (up > 0), up, 0.0)]
        minus_dm = np.r_[0.0, np.where((down > up) & (down > 0), down, 0.0)]
        p = 14
        trs = _rolling_mean(tr, p)
        pdi = np.divide(
            100 * _rolling_mean(plus_dm, p), trs, out=np.full_like(trs, np.nan), where=trs > _EPS
        )
        mdi = np.divide(
            100 * _rolling_mean(minus_dm, p), trs, out=np.full_like(trs, np.nan), where=trs > _EPS
        )
        denom = pdi + mdi
        dx = np.divide(
            100 * np.abs(pdi - mdi), denom, out=np.full_like(denom, np.nan), where=denom > _EPS
        )
        needed = 2 * p if metric == "adx" else p + 1
        if n < needed or not np.isfinite(dx).any():
            return None, n
        if metric == "adx":
            recent_dx = dx[-p:]
            finite_dx = recent_dx[np.isfinite(recent_dx)]
            return (float(np.mean(finite_dx)), n) if len(finite_dx) else (None, n)
        return float(pdi[-1] if metric == "plus_di" else mdi[-1]), n
    if metric == "roc_pct":
        return (
            (float(100 * (close[-1] / close[-13] - 1)), 13)
            if n >= 13 and close[-13]
            else (None, min(n, 13))
        )
    if metric == "momentum_pct":
        return (
            (float(100 * (close[-1] / close[-21] - 1)), 21)
            if n >= 21 and close[-21]
            else (None, min(n, 21))
        )
    if metric.startswith("bollinger"):
        x = close[-20:]
        mean, std = float(np.mean(x)), float(np.std(x))
        upper, lower = mean + 2 * std, mean - 2 * std
        if metric == "bollinger_position":
            return ((close[-1] - lower) / (upper - lower), 20) if upper > lower else (0.5, 20)
        return (100 * (upper - lower) / mean, 20) if mean else (None, 20)
    if metric == "atr_pct":
        tr = _true_range(highs, lows, close)[-14:]
        return (
            (float(100 * np.mean(tr) / close[-1]), len(tr))
            if len(tr) == 14 and close[-1]
            else (None, len(tr))
        )
    if metric == "obv_change_fraction":
        signed = np.sign(np.diff(close[-21:])) * volume[-20:]
        denom = float(np.sum(volume[-20:]))
        return (float(np.sum(signed) / denom), 20) if denom > 0 else (None, 20)
    if metric == "mfi":
        tp = (highs + lows + close) / 3
        flow = tp * volume
        delta = np.diff(tp[-15:])
        positive = float(np.sum(flow[-14:][delta > 0]))
        negative = float(np.sum(flow[-14:][delta < 0]))
        return (
            100.0
            if negative == 0 and positive > 0
            else 50.0
            if negative == 0
            else 100 - 100 / (1 + positive / negative),
            15,
        )
    if metric == "accumulation_distribution_fraction":
        spread = highs[-20:] - lows[-20:]
        multiplier = np.divide(
            2 * close[-20:] - highs[-20:] - lows[-20:],
            spread,
            out=np.zeros(20),
            where=spread > _EPS,
        )
        denom = float(np.sum(volume[-20:]))
        return (float(np.sum(multiplier * volume[-20:]) / denom), 20) if denom > 0 else (None, 20)
    if metric == "ema_distance_pct":
        ema = float(_ema(close, 20)[-1])
        return (float(100 * (close[-1] / ema - 1)), 20) if ema else (None, 20)
    if metric == "sma_distance_pct":
        sma = float(np.mean(close[-20:]))
        return (float(100 * (close[-1] / sma - 1)), 20) if sma else (None, 20)
    return None, 0


def _ohlc_series(
    opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, close: np.ndarray
) -> dict[str, np.ndarray]:
    prev = np.roll(close, 1)
    prev[0] = np.nan
    safe_prev = np.where(prev != 0, prev, np.nan)
    span = highs - lows
    return {
        "high_low_rel": 100 * (highs - lows) / safe_prev,
        "close_open_return": 100 * (close - opens) / opens,
        "overnight_gap": 100 * (opens - prev) / safe_prev,
        "candle_body": 100 * np.abs(close - opens) / safe_prev,
        "upper_wick": 100 * (highs - np.maximum(opens, close)) / safe_prev,
        "lower_wick": 100 * (np.minimum(opens, close) - lows) / safe_prev,
        "close_location": np.divide(
            2 * close - highs - lows, span, out=np.full_like(close, np.nan), where=span > _EPS
        ),
        "true_range_pct": 100 * _true_range(highs, lows, close) / safe_prev,
        "atr_pct": 100 * _true_range(highs, lows, close) / safe_prev,
        "positive_share": np.where(np.isfinite(prev), (close > prev).astype(float), np.nan),
        "negative_share": np.where(np.isfinite(prev), (close < prev).astype(float), np.nan),
        "gap_frequency": 100 * (opens - prev) / safe_prev,
    }


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev = np.roll(close, 1)
    prev[0] = np.nan
    candidates = np.vstack((high - low, np.abs(high - prev), np.abs(low - prev)))
    finite = np.isfinite(candidates)
    result = np.max(np.where(finite, candidates, -np.inf), axis=0)
    result[~finite.any(axis=0)] = np.nan
    return result


def _returns(values: np.ndarray, *, logarithmic: bool) -> np.ndarray:
    previous, current = values[:-1], values[1:]
    valid = (previous > 0) & (current > 0)
    result = np.full(max(len(values) - 1, 0), np.nan)
    result[valid] = (
        np.log(current[valid] / previous[valid])
        if logarithmic
        else current[valid] / previous[valid] - 1
    )
    return result


def _array(rows: Sequence[Mapping[str, Any]], key: str) -> np.ndarray:
    return np.asarray(
        [float(row[key]) if _is_finite(row.get(key)) else np.nan for row in rows], dtype=np.float64
    )


def _tail(values: np.ndarray, window: int | None) -> np.ndarray:
    return values[-window:] if window else values


def _moment(metric: str, x: np.ndarray) -> float | None:
    if metric not in {"skewness", "kurtosis"} or len(x) < (3 if metric == "skewness" else 4):
        return None
    centered = x - np.mean(x)
    scale = float(np.mean(centered**2))
    if scale <= _EPS:
        return 0.0
    return (
        float(np.mean(centered**3) / scale**1.5)
        if metric == "skewness"
        else float(np.mean(centered**4) / scale**2 - 3.0)
    )


def _finite_mean(x: np.ndarray) -> float | None:
    values = x[np.isfinite(x)]
    return float(np.mean(values)) if len(values) else None


def _correlation(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2 or float(np.std(x)) <= _EPS or float(np.std(y)) <= _EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.empty(len(values), dtype=np.float64)
    alpha = 2.0 / (period + 1)
    result[0] = values[0]
    for index in range(1, len(values)):
        result[index] = alpha * values[index] + (1 - alpha) * result[index - 1]
    return result


def _rolling_mean(values: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) >= period:
        cumulative = np.r_[0.0, np.cumsum(values, dtype=np.float64)]
        result[period - 1 :] = (cumulative[period:] - cumulative[:-period]) / period
    return result


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float, np.number)) and math.isfinite(float(value))


def _valid_close(value: Any) -> bool:
    return _is_finite(value) and float(value) > 0
