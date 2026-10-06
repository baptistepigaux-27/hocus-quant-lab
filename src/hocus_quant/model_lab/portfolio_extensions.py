"""Signed stock ledger: collateralized shorts and fixed-score holding extensions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from hocus_quant.model_lab.backtest import execution_dates, summarize
from hocus_quant.validation.market_quality import assess_series


@dataclass
class MarketTape:
    calendar: list[date]
    quotes: dict[date, dict[str, dict[str, Any]]]
    benchmark: dict[date, dict[str, Any]]
    quality_cache: dict[tuple[str, date, date], dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def build(cls, market: pd.DataFrame, benchmark: pd.DataFrame) -> MarketTape:
        assert not market.duplicated(["session_date", "entity_id"]).any()
        return cls(
            sorted(market.session_date.unique()),
            {
                d: part.set_index("entity_id").to_dict("index")
                for d, part in market.groupby("session_date")
            },
            benchmark.set_index("session_date").to_dict("index"),
        )

    def quality(self, holding: dict[str, Any], exit_day: date) -> dict[str, Any]:
        key = holding["entity_id"], holding["entry_date"], exit_day
        if key not in self.quality_cache:
            self.quality_cache[key] = assess_series(
                {
                    "entity_id": holding["entity_id"],
                    "entity_family": "equity",
                    "observations": holding["path"],
                }
            )
        return self.quality_cache[key]


def picks(predictions: pd.DataFrame, fraction: float) -> list[dict[str, Any]]:
    """One total order; tail selects a disjoint bottom even when all scores tie."""
    result = []
    for cutoff, part in predictions.groupby("cutoff", sort=True):
        ranked = part[np.isfinite(part.score)].sort_values(
            ["score", "entity_id"], ascending=[False, True], kind="stable"
        )
        n = max(1, math.ceil(len(ranked) * fraction))
        assert len(ranked) >= 2 * n
        top, flop = ranked.head(n), ranked.tail(n)
        assert set(top.entity_id).isdisjoint(flop.entity_id)
        result.append(
            {
                "cutoff": cutoff,
                "eligible_n": len(ranked),
                "selected_n_per_leg": n,
                "long_ids": top.entity_id.tolist(),
                "short_ids": flop.entity_id.tolist(),
                "constant_scores": ranked.score.nunique() <= 1,
                "long_boundary_ties": int((ranked.score == top.score.iloc[-1]).sum()),
                "short_boundary_ties": int((ranked.score == flop.score.iloc[0]).sum()),
            }
        )
    return result


def simulate_signed(
    selection: list[dict[str, Any]],
    tape: MarketTape,
    holding_horizon: int,
    cost_bp: int,
    sleeves: int,
    strategy: str,
    borrow_rate: float,
    end: date,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    assert strategy in {"long_only", "long_short"}
    assert borrow_rate >= 0
    schedule: dict[date, list[dict[str, Any]]] = {}
    for selected in selection:
        dates = execution_dates(selected["cutoff"], tape.calendar, holding_horizon)
        if dates is None:
            raise ValueError("Execution source too short; never silently drop a decision")
        entry, exit_day = dates
        assert exit_day <= end
        schedule.setdefault(entry, []).append({**selected, "scheduled_exit": exit_day})
    start = min(schedule)
    fee = cost_bp / 20000
    cash = nav = 1.0
    holdings, trades, daily = [], [], []
    benchmark_entry = tape.benchmark.get(start, {}).get("open")
    benchmark_value = 1.0
    for day in [d for d in tape.calendar if start <= d <= end]:
        quotes = tape.quotes[day]
        previous_nav = nav
        traded = transaction_fees = borrowed = 0.0
        leg_gross = {"long": 0.0, "short": 0.0}
        leg_fees = {"long": 0.0, "short": 0.0}
        for holding in holdings:
            if holding["side"] == "short":
                elapsed = (day - holding["borrow_last_date"]).days
                charge = holding["shares"] * holding["last_price"] * borrow_rate * elapsed / 365
                cash -= charge
                borrowed += charge
                holding["borrow_fees"] += charge
                holding["borrow_last_date"] = day
        for vintage in schedule.get(day, []):
            budget = min(max(0.0, cash), max(0.0, previous_nav / sleeves))
            legs = (
                [("long", vintage["long_ids"], 1.0)]
                if strategy == "long_only"
                else [("long", vintage["long_ids"], 0.5), ("short", vintage["short_ids"], 0.5)]
            )
            for side, ids, weight in legs:
                # A reserved slot stays in cash when a gated basket has <N names.
                slots = int(vintage.get("allocation_slots", len(ids)))
                if ids and slots < len(ids):
                    raise ValueError("Allocation slots cannot be fewer than selected names")
                allocation = budget * weight / slots if ids else 0.0
                for entity in ids:
                    row = quotes.get(entity, {})
                    price = row.get("open")
                    base = {
                        "cutoff": vintage["cutoff"],
                        "entity_id": entity,
                        "side": side,
                        "entry_date": day,
                        "scheduled_exit": vintage["scheduled_exit"],
                        "cost_round_trip_bp": cost_bp,
                        "allocation": allocation,
                    }
                    if price is None or not np.isfinite(price) or price <= 0 or allocation <= 0:
                        trades.append(
                            {
                                **base,
                                "status": "missing_entry_or_no_cash",
                                "shares": 0.0,
                                "entry_price": None,
                                "exit_date": None,
                                "exit_price": None,
                                "return_gross": None,
                                "return_net": None,
                                "entry_fee": 0.0,
                                "exit_fee": 0.0,
                                "borrow_fees": 0.0,
                                "pnl_gross": 0.0,
                                "pnl_net": 0.0,
                                "future_quality": None,
                            }
                        )
                        continue
                    shares = allocation / (price * (1 + fee))
                    nominal = shares * price
                    entry_fee = nominal * fee
                    holdings.append(
                        {
                            **base,
                            "shares": shares,
                            "entry_price": price,
                            "entry_nominal": nominal,
                            "entry_fee": entry_fee,
                            "borrow_fees": 0.0,
                            "borrow_last_date": day,
                            "path": [],
                            "last_price": price,
                        }
                    )
                    cash -= allocation
                    traded += nominal
                    transaction_fees += entry_fee
                    leg_fees[side] += entry_fee
        remaining = []
        for holding in holdings:
            row = quotes.get(holding["entity_id"], {})
            close = row.get("close")
            valid = close is not None and np.isfinite(close) and close > 0
            sign = 1 if holding["side"] == "long" else -1
            if valid:
                leg_gross[holding["side"]] += (
                    sign * holding["shares"] * (close - holding["last_price"])
                )
                holding["last_price"] = close
                holding["path"].append(
                    {
                        "session_date": day,
                        **{k: row.get(k) for k in ["open", "high", "low", "close", "volume"]},
                    }
                )
            if day >= holding["scheduled_exit"] and valid:
                exit_nominal = holding["shares"] * close
                exit_fee = exit_nominal * fee
                payout = exit_nominal if sign == 1 else 2 * holding["entry_nominal"] - exit_nominal
                cash += payout - exit_fee
                transaction_fees += exit_fee
                leg_fees[holding["side"]] += exit_fee
                traded += exit_nominal
                quality = tape.quality(holding, day)
                gross_pnl = sign * holding["shares"] * (close - holding["entry_price"])
                net_pnl = gross_pnl - holding["entry_fee"] - exit_fee - holding["borrow_fees"]
                trades.append(
                    {
                        **{
                            k: v
                            for k, v in holding.items()
                            if k not in {"path", "last_price", "borrow_last_date"}
                        },
                        "exit_date": day,
                        "exit_price": close,
                        "exit_fee": exit_fee,
                        "return_gross": sign * (close / holding["entry_price"] - 1),
                        "return_net": net_pnl / holding["allocation"],
                        "pnl_gross": gross_pnl,
                        "pnl_net": net_pnl,
                        "holding_calendar_days": (day - holding["entry_date"]).days,
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
        longs = sum(h["shares"] * h["last_price"] for h in holdings if h["side"] == "long")
        shorts = sum(h["shares"] * h["last_price"] for h in holdings if h["side"] == "short")
        collateral = sum(h["entry_nominal"] for h in holdings if h["side"] == "short")
        nav = cash + longs + 2 * collateral - shorts
        pnl_long = leg_gross["long"] - leg_fees["long"]
        pnl_short = leg_gross["short"] - leg_fees["short"] - borrowed
        assert abs(nav - previous_nav - pnl_long - pnl_short) < 1e-10
        quote_b = tape.benchmark.get(day, {}).get("close")
        if benchmark_entry and quote_b and np.isfinite(quote_b):
            benchmark_value = quote_b / benchmark_entry
        stale = sum(
            not np.isfinite(quotes.get(h["entity_id"], {}).get("close", np.nan)) for h in holdings
        )
        netted: dict[str, list[float]] = {}
        for holding in holdings:
            nominal = holding["shares"] * holding["last_price"]
            amounts = netted.setdefault(holding["entity_id"], [0.0, 0.0])
            amounts[0 if holding["side"] == "long" else 1] += nominal
        daily.append(
            {
                "session_date": day,
                "equity": nav,
                "daily_return": nav / previous_nav - 1 if previous_nav > 0 else np.nan,
                "cash": cash,
                "long_market_value": longs,
                "short_liability": shorts,
                "short_collateral": collateral,
                "blocked_short_proceeds": collateral,
                "gross_exposure": (longs + shorts) / nav if nav > 0 else np.nan,
                "net_exposure": (longs - shorts) / nav if nav > 0 else np.nan,
                "long_exposure": longs / nav if nav > 0 else np.nan,
                "short_exposure": shorts / nav if nav > 0 else np.nan,
                "offsetting_vintage_nominal": sum(min(amounts) for amounts in netted.values()),
                "holding_count": len(holdings),
                "turnover": traded / previous_nav if previous_nav > 0 else np.nan,
                "fees": transaction_fees,
                "borrow_fees": borrowed,
                "pnl_long_net": pnl_long,
                "pnl_short_net": pnl_short,
                "benchmark_equity": benchmark_value if benchmark_entry else None,
                "stale_holdings": stale,
            }
        )
    for holding in holdings:
        sign = 1 if holding["side"] == "long" else -1
        pnl_gross = sign * holding["shares"] * (holding["last_price"] - holding["entry_price"])
        trades.append(
            {
                **{
                    k: v
                    for k, v in holding.items()
                    if k not in {"path", "last_price", "borrow_last_date"}
                },
                "status": "unresolved_exit",
                "exit_date": None,
                "exit_price": None,
                "return_gross": None,
                "return_net": None,
                "exit_fee": 0.0,
                "pnl_gross": pnl_gross,
                "pnl_net": pnl_gross - holding["entry_fee"] - holding["borrow_fees"],
                "future_quality": None,
            }
        )
    equity, ledger = pd.DataFrame(daily), pd.DataFrame(trades)
    if ledger.empty:
        ledger = pd.DataFrame(
            columns=[
                "cutoff",
                "entity_id",
                "side",
                "entry_date",
                "scheduled_exit",
                "allocation",
                "shares",
                "entry_price",
                "entry_nominal",
                "entry_fee",
                "borrow_fees",
                "exit_date",
                "exit_price",
                "exit_fee",
                "return_gross",
                "return_net",
                "pnl_gross",
                "pnl_net",
                "holding_calendar_days",
                "status",
                "future_quality",
                "future_reason",
            ]
        )
    assert abs(ledger.pnl_net.sum() - (equity.equity.iloc[-1] - 1)) < 1e-10
    stats = summarize(equity, ledger)
    stats.update(
        {
            "holding_horizon": holding_horizon,
            "cost_bp": cost_bp,
            "sleeves": sleeves,
            "strategy": strategy,
            "borrow_rate_annual": borrow_rate,
            "annualized_return": None,
            "start_date": str(start),
            "end_date": str(end),
            "average_net_exposure": float(equity.net_exposure.mean()),
            "average_long_exposure": float(equity.long_exposure.mean()),
            "average_short_exposure": float(equity.short_exposure.mean()),
            "borrow_fees": float(equity.borrow_fees.sum()),
            "long_contribution": float(equity.pnl_long_net.sum()),
            "short_contribution": float(equity.pnl_short_net.sum()),
            "stale_position_days": int(equity.stale_holdings.sum()),
            "offsetting_vintage_days": int((equity.offsetting_vintage_nominal > 0).sum()),
            "negative_cash_days": int((equity.cash < 0).sum()),
            "nonpositive_nav_days": int((equity.equity <= 0).sum()),
            "development_only": True,
            "status": "unresolved_positions" if holdings else "development_raw_prices",
        }
    )
    if (equity.equity <= 0).any():
        stats.update(status="insolvent_without_margin_simulation", sharpe=None, volatility=None)
    return equity, ledger, stats
