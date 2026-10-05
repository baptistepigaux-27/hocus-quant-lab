from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from hocus_quant.model_lab.backtest import execution_dates, simulate


def fixture():
    days = [
        date(2026, 1, 2) + timedelta(days=i)
        for i in range(24)
        if (date(2026, 1, 2) + timedelta(days=i)).weekday() < 5
    ]
    rows = [
        {
            "session_date": d,
            "entity_id": e,
            "open": 100.0,
            "close": 100.0,
            "high": 101.0,
            "low": 99.0,
            "volume": 1000.0,
        }
        for d in days
        for e in ["a", "b"]
    ]
    market = pd.DataFrame(rows)
    benchmark = market[market.entity_id == "a"].copy()
    predictions = pd.DataFrame(
        [
            {"cutoff": days[0], "entity_id": e, "score": score}
            for e, score in [("a", 0.9), ("b", 0.1)]
        ]
    )
    return days, market, benchmark, predictions


@pytest.mark.parametrize("h", [5, 10])
def test_execution_fees_weight_replay(h):
    days, market, benchmark, pred = fixture()
    eq, tr, s = simulate(pred, market, benchmark, h, 50, 1, end=days[-1], universe=True)
    assert tr.entry_date.min() > pred.cutoff.max()
    assert tr.exit_date.tolist() == [days[h]] * 2
    assert tr.shares.iloc[0] == pytest.approx(tr.shares.iloc[1])
    fee = 0.0025
    assert s["cumulative_return"] == pytest.approx((1 - fee) / (1 + fee) - 1)
    assert s["benchmark_return"] == 0
    assert tr.entry_fee.sum() + tr.exit_fee.sum() == pytest.approx(s["fees"])
    eq2, tr2, s2 = simulate(pred, market, benchmark, h, 50, 1, end=days[-1], universe=True)
    assert eq.equals(eq2) and tr.equals(tr2) and s == s2
    assert execution_dates(days[0], days, h) == (days[1], days[h])


def test_overlap_and_no_future_selection():
    days, market, benchmark, pred = fixture()
    second = pred.copy()
    second["cutoff"] = days[5]
    pred = pd.concat([pred, second], ignore_index=True)
    eq, tr, _ = simulate(pred, market, benchmark, 10, 0, 3, end=days[-1])
    assert eq.holding_count.max() == 2
    assert eq.cash.min() >= -1e-12
    # Future error on selected stock remains a trade annotation, never removes the pick.
    bad = market.copy()
    bad.loc[(bad.entity_id == "a") & (bad.session_date == days[3]), "high"] = 50
    _, bad_tr, s = simulate(pred, bad, benchmark, 10, 0, 3, end=days[-1])
    assert bad_tr.entity_id.tolist() == tr.entity_id.tolist()
    assert s["flagged_closed_positions"] > 0


def test_missing_entry_and_exit():
    days, market, benchmark, pred = fixture()
    missing = market.copy()
    missing.loc[(missing.entity_id == "a") & (missing.session_date == days[1]), "open"] = np.nan
    _, tr, s = simulate(pred, missing, benchmark, 5, 0, 2, end=days[-1])
    assert s["missing_entries"] == 1 and tr.status.iloc[0] == "missing_entry_or_no_cash"
    missing = market.copy()
    missing.loc[(missing.entity_id == "a") & (missing.session_date == days[5]), "close"] = np.nan
    _, tr, s = simulate(pred, missing, benchmark, 5, 0, 2, end=days[-1])
    assert s["delayed_exits"] == 1 and tr.exit_date.iloc[0] == days[6]
    assert simulate(pred.iloc[:0], market, benchmark, 5, 0, 2)[2]["status"] == "empty_cutoff"
