"""Unlevered cash-and-share ledger, fixed capital sleeves and next-open execution."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from hocus_quant.validation.market_quality import assess_series


def execution_dates(cutoff: Any, calendar: list[Any], horizon: int) -> tuple[Any, Any] | None:
    future = [d for d in calendar if d > cutoff]
    return (future[0], future[horizon - 1]) if len(future) >= horizon else None


def simulate(
    predictions: pd.DataFrame,
    market: pd.DataFrame,
    benchmark: pd.DataFrame,
    horizon: int,
    cost_bp: int,
    sleeves: int,
    *,
    universe: bool = False,
    fraction: float = 0.1,
    end: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Selection depends ONLY on score/IDs at T; future anomalies never remove a pick.

    Entry costs half round-trip bp, exit the other half. Each vintage gets at most
    current NAV/sleeves, equally divided across selected IDs. Unused cash earns zero.
    Exit at Hth common-session close; a missing exit waits for the next real close,
    explicitly flagged. No fabricated fills or unadjusted split repairs.
    """
    if predictions.empty:
        return pd.DataFrame(), pd.DataFrame(), {"status": "empty_cutoff"}
    predictions = predictions.sort_values(["cutoff", "entity_id"]).copy()
    market = market.sort_values(["session_date", "entity_id"])
    calendar = sorted(market.session_date.unique())
    end = end or predictions.cutoff.max()
    schedule: dict[Any, list[dict[str, Any]]] = {}
    for cutoff, part in predictions.groupby("cutoff", sort=True):
        dates = execution_dates(cutoff, calendar, horizon)
        if dates is None:
            continue
        entry, exit_day = dates
        part = part[np.isfinite(part.score)].sort_values(
            ["score", "entity_id"], ascending=[False, True], kind="stable"
        )
        chosen = part if universe else part.head(max(1, math.ceil(len(part) * fraction)))
        schedule.setdefault(entry, []).append(
            {"cutoff": cutoff, "scheduled_exit": exit_day, "ids": chosen.entity_id.tolist()}
        )
    if not schedule:
        return pd.DataFrame(), pd.DataFrame(), {"status": "missing_execution_calendar"}
    start = min(schedule)
    daily_rows = {
        d: part.set_index("entity_id").to_dict("index")
        for d, part in market.groupby("session_date")
    }
    bench = benchmark.set_index("session_date").to_dict("index")
    cash, nav, fee = 1.0, 1.0, cost_bp / 20000
    holdings: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []
    last_close: dict[str, float] = {}
    benchmark_entry = bench.get(start, {}).get("open")
    benchmark_value = 1.0
    for day in [d for d in calendar if start <= d <= end]:
        quotes = daily_rows.get(day, {})
        previous_nav = nav
        traded, fees = 0.0, 0.0
        for vintage in schedule.get(day, []):
            budget = min(cash, max(0.0, previous_nav / sleeves))
            allocation = budget / max(1, len(vintage["ids"]))
            for entity in vintage["ids"]:
                row = quotes.get(entity, {})
                price = row.get("open")
                base = {
                    "cutoff": vintage["cutoff"],
                    "entity_id": entity,
                    "entry_date": day,
                    "scheduled_exit": vintage["scheduled_exit"],
                    "cost_round_trip_bp": cost_bp,
                }
                if price is None or not np.isfinite(price) or price <= 0 or allocation <= 0:
                    trades.append(
                        {
                            **base,
                            "status": "missing_entry_or_no_cash",
                            "entry_price": None,
                            "exit_date": None,
                            "return_gross": None,
                            "return_net": None,
                            "entry_fee": 0.0,
                            "exit_fee": 0.0,
                        }
                    )
                    continue
                shares = allocation / (price * (1 + fee))
                entry_fee = shares * price * fee
                holdings.append(
                    {
                        **base,
                        "shares": shares,
                        "entry_price": price,
                        "allocation": allocation,
                        "entry_fee": entry_fee,
                        "path": [],
                        "last_price": price,
                    }
                )
                cash -= allocation
                traded += shares * price
                fees += entry_fee
        remaining: list[dict[str, Any]] = []
        for holding in holdings:
            row = quotes.get(holding["entity_id"], {})
            close = row.get("close")
            valid = close is not None and np.isfinite(close) and close > 0
            if valid:
                holding["last_price"] = close
                last_close[holding["entity_id"]] = close
                holding["path"].append(
                    {
                        "session_date": day,
                        **{k: row.get(k) for k in ["open", "high", "low", "close", "volume"]},
                    }
                )
            if day >= holding["scheduled_exit"] and valid:
                gross = holding["shares"] * close
                exit_fee = gross * fee
                cash += gross - exit_fee
                fees += exit_fee
                traded += gross
                quality = assess_series(
                    {
                        "entity_id": holding["entity_id"],
                        "entity_family": "equity",
                        "observations": holding["path"],
                    }
                )
                trades.append(
                    {k: v for k, v in holding.items() if k not in {"path", "last_price"}}
                    | {
                        "exit_date": day,
                        "exit_price": close,
                        "exit_fee": exit_fee,
                        "return_gross": close / holding["entry_price"] - 1,
                        "return_net": (close / holding["entry_price"]) * (1 - fee) / (1 + fee) - 1,
                        "status": "closed"
                        if day == holding["scheduled_exit"]
                        else "delayed_missing_exit",
                        "future_quality": quality["quality_status"],
                        "future_reason": quality["quality_reason"],
                    }
                )
            else:
                remaining.append(holding)
        holdings = remaining
        invested = sum(r["shares"] * r["last_price"] for r in holdings)
        nav = cash + invested
        quote_b = bench.get(day, {}).get("close")
        if benchmark_entry and quote_b and np.isfinite(quote_b):
            benchmark_value = quote_b / benchmark_entry
        daily.append(
            {
                "session_date": day,
                "equity": nav,
                "daily_return": nav / previous_nav - 1,
                "cash": cash,
                "gross_exposure": invested / max(nav, 1e-12),
                "holding_count": len(holdings),
                "turnover": traded / max(previous_nav, 1e-12),
                "fees": fees,
                "benchmark_equity": benchmark_value if benchmark_entry else None,
                "stale_holdings": sum(r["entity_id"] not in quotes for r in holdings),
            }
        )
    for h in holdings:
        trades.append(
            {k: v for k, v in h.items() if k not in {"path", "last_price"}}
            | {
                "status": "unresolved_exit",
                "exit_date": None,
                "return_gross": None,
                "return_net": None,
                "exit_fee": 0.0,
            }
        )
    equity = pd.DataFrame(daily)
    trades_frame = pd.DataFrame(trades)
    stats = summarize(equity, trades_frame)
    stats.update(
        {
            "horizon": horizon,
            "cost_round_trip_bp": cost_bp,
            "sleeves": sleeves,
            "start_date": str(start),
            "end_date": str(end),
            "development_only": True,
            "status": "unresolved_positions" if holdings else "development_raw_prices",
        }
    )
    return equity, trades_frame, stats


def summarize(equity: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Any]:
    if equity.empty:
        return {"status": "empty"}
    r = equity.daily_return.to_numpy()
    nav = equity.equity.to_numpy()
    dd = nav / np.maximum.accumulate(np.r_[1.0, nav])[1:] - 1
    vol = float(np.std(r, ddof=1) * np.sqrt(252)) if len(r) > 1 else None
    closed = (
        trades[trades.status.isin(["closed", "delayed_missing_exit"])] if len(trades) else trades
    )
    benchmark_return = (
        equity.benchmark_equity.iloc[-1] - 1 if equity.benchmark_equity.notna().any() else None
    )
    return {
        "cumulative_return": float(nav[-1] - 1),
        "annualized_return": float(nav[-1] ** (252 / len(r)) - 1)
        if len(r) >= 126 and nav[-1] > 0
        else None,
        "volatility": vol,
        "sharpe": float(np.mean(r) / np.std(r, ddof=1) * np.sqrt(252))
        if len(r) >= 30 and np.std(r, ddof=1) > 0
        else None,
        "max_drawdown": float(dd.min()),
        "turnover": float(equity.turnover.sum()),
        "hit_rate": float((closed.return_net > 0).mean()) if len(closed) else None,
        "average_trade_return": float(closed.return_net.mean()) if len(closed) else None,
        "benchmark_return": float(benchmark_return) if benchmark_return is not None else None,
        "excess_return": float(nav[-1] - 1 - benchmark_return)
        if benchmark_return is not None
        else None,
        "positions": len(closed),
        "average_holding_count": float(equity.holding_count.mean()),
        "average_exposure": float(equity.gross_exposure.mean()),
        "fees": float(equity.fees.sum()),
        "missing_entries": int((trades.status == "missing_entry_or_no_cash").sum())
        if len(trades)
        else 0,
        "flagged_closed_positions": int((closed.future_quality != "approved").sum())
        if len(closed)
        else 0,
        "delayed_exits": int((trades.status == "delayed_missing_exit").sum()) if len(trades) else 0,
        "unresolved_exits": int((trades.status == "unresolved_exit").sum()) if len(trades) else 0,
    }
