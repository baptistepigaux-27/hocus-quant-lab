from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hocus_quant.model_lab.common_replay import augment, cohorts, concentration, selection
from hocus_quant.model_lab.portfolio_extensions import MarketTape, simulate_signed


@pytest.fixture
def tape():
    days = pd.bdate_range("2026-01-05", "2026-01-30").date.tolist()
    rows = [
        {
            "session_date": d,
            "entity_id": f"stock-{i}",
            "open": 100.0,
            "high": 111.0,
            "low": 90.0,
            "close": 100.0 + k,
            "volume": 1000.0,
        }
        for k, d in enumerate(days)
        for i in range(10)
    ]
    benchmark = pd.DataFrame({"session_date": days, "open": 100.0, "close": 100.0})
    return MarketTape.build(pd.DataFrame(rows), benchmark)


def choices():
    return [
        {
            "cutoff": date(2026, 1, 2),
            "long_ids": ["stock-0", "stock-1"],
            "short_ids": [],
            "eligible_n": 10,
            "selected_n_per_leg": 2,
        }
    ]


@pytest.mark.parametrize("hold", [1, 2, 3, 5, 10])
@pytest.mark.parametrize("cost", [0, 25, 45])
def test_native_exits_fees_equal_weights_and_nav(tape, hold, cost):
    eq, ledger, stats = simulate_signed(
        choices(), tape, hold, cost, 2, "long_only", 0.0, tape.calendar[-1]
    )
    eq, ledger, extra = augment(eq, ledger, tape)
    assert set(ledger.entry_date) == {tape.calendar[0]}
    assert set(ledger.exit_date) == {tape.calendar[hold - 1]}
    np.testing.assert_allclose(ledger.allocation, 0.25)
    np.testing.assert_allclose(ledger.entry_price, 100.0)
    np.testing.assert_allclose(ledger.return_gross, (100 + hold - 1) / 100 - 1)
    np.testing.assert_allclose(ledger.entry_fee, ledger.entry_nominal * cost / 20000)
    np.testing.assert_allclose(ledger.exit_fee, ledger.shares * ledger.exit_price * cost / 20000)
    np.testing.assert_allclose(
        ledger.pnl_net,
        ledger.shares * (ledger.exit_price - ledger.entry_price)
        - ledger.entry_fee
        - ledger.exit_fee,
    )
    np.testing.assert_allclose(eq.equity, 1 + eq.realized_pnl + eq.unrealized_pnl, atol=1e-12)
    np.testing.assert_allclose(eq.equity, eq.cash + eq.long_market_value, atol=1e-12)
    assert stats["sleeves"] == 2 and stats["negative_cash_days"] == 0
    assert extra["max_accounting_error"] < 1e-12
    if hold == 1:
        assert eq.gross_exposure.eq(0).all()
        assert eq.active_session_capital.iloc[0] > 0


def test_missing_open_cash_and_no_delayed_entry(tape):
    tape.quotes[tape.calendar[0]]["stock-0"]["open"] = np.nan
    eq, ledger, _ = simulate_signed(choices(), tape, 3, 25, 2, "long_only", 0.0, tape.calendar[-1])
    _, ledger, _ = augment(eq, ledger, tape)
    r = ledger[ledger.entity_id == "stock-0"].iloc[0]
    assert r.execution_warning == "missing_entry_open" and pd.isna(r.exit_date)
    assert r.shares == 0 and r.pnl_net == 0
    assert eq.cash.iloc[0] == pytest.approx(0.75)
    assert len(ledger) == 2


def test_suspension_delay_real_loss_and_warning(tape):
    for day in tape.calendar[4:8]:
        del tape.quotes[day]["stock-0"]
    tape.quotes[tape.calendar[8]]["stock-0"]["close"] = 40.0
    tape.quotes[tape.calendar[8]]["stock-0"]["low"] = 39.0
    eq, ledger, _ = simulate_signed(choices(), tape, 5, 0, 2, "long_only", 0.0, tape.calendar[-1])
    _, ledger, _ = augment(eq, ledger, tape)
    r = ledger[ledger.entity_id == "stock-0"].iloc[0]
    assert r.exit_date == tape.calendar[8] and r.status == "delayed_missing_exit"
    assert r.delay_sessions == 4 and r.return_gross == pytest.approx(-0.6)
    assert r.pnl_net == pytest.approx(-0.15) and r.future_quality == "review"
    assert eq.stale_holdings.max() == 1


def test_selection_ignores_outcomes_and_deterministic():
    f = pd.DataFrame(
        {
            "cutoff": [date(2026, 1, 2)] * 100,
            "entity_id": [f"id-{i:03}" for i in range(100)],
            "score": np.arange(100, dtype=float),
        }
    )
    a, rows = selection(f, 0.03)
    poisoned = f.assign(target_value=-f.score, return_abs=-1.0, future_quality="quarantined")
    b, other = selection(poisoned.sample(frac=1, random_state=8), 0.03)
    assert a == b and len(rows) == 3
    assert a[0]["long_ids"] == ["id-099", "id-098", "id-097"]
    pd.testing.assert_frame_equal(rows.reset_index(drop=True), other.reset_index(drop=True))


def test_cohorts_eligibility_not_target_outcomes():
    day = date(2026, 1, 2)
    frames = {
        h: pd.DataFrame(
            {
                "cutoff": [day] * 3,
                "entity_id": ["a", "b", "c"],
                "eligible_at_T": [True, True, h != 10],
            }
        )
        for h in [1, 2, 3, 5, 10]
    }
    rows, counts = cohorts(frames, [day])
    assert set(rows[rows.in_common].entity_id) == {"a", "b"}
    assert counts.common_n.eq(2).all()
    assert counts.loc[counts.score_horizon == 1, "coverage_loss"].iloc[0] == pytest.approx(1 / 3)


def test_attribution_not_strategy_exclusion():
    result = concentration(pd.DataFrame({"pnl_net": [0.1, 0.05, -0.04, -0.02]}))
    assert result["total_pnl"] == pytest.approx(0.09)
    assert result["top1_contribution"] == pytest.approx(0.1)
    assert result["top_1_share"] > 1
    assert result["absolute_contribution_hhi"] is not None


def test_replay_code_has_no_fit_or_tuning():
    p = Path("src/hocus_quant/model_lab/common_replay.py")
    tree = ast.parse(p.read_text())
    forbidden = {"fit", "fit_transform", "partial_fit", "fit_model", "make_model", "choose_trial"}
    calls = [
        n.func.attr
        if isinstance(n.func, ast.Attribute)
        else n.func.id
        if isinstance(n.func, ast.Name)
        else ""
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    ]
    assert not forbidden.intersection(calls)


def test_real_replay_invariants():
    root = Path("data/analysis/srd-horizon-common-replay-v1")
    if not (root / "summary.json").exists():
        pytest.skip("Local research data are not versioned")
    contract = json.loads((root / "contract.json").read_text())
    audit = json.loads((root / "audit.json").read_text())
    dates = {date.fromisoformat(x) for x in contract["common_cutoffs"]}
    assert (
        len(dates) == 22
        and contract["sleeves"] == 2
        and audit["fit_calls"] == audit["tuning_calls"] == 0
    )
    assert audit["input_files_unchanged"] and not audit["volumes_modified"]
    inventory = json.loads(Path("data/analysis/srd-price-audit-v1/common_cutoffs.json").read_text())
    assert dates == {date.fromisoformat(x) for x in inventory["common_cutoffs"]}
    universe = pd.read_parquet(root / "common_universe.parquet")
    for _, part in universe[universe.in_common].groupby("cutoff"):
        sets = [set(g.entity_id) for _, g in part.groupby("score_horizon")]
        assert len(sets) == 5 and all(s == sets[0] for s in sets)
    scores = pd.read_parquet(root / "scores.parquet")
    sels = pd.read_parquet(root / "selections.parquet")
    metrics = pd.read_parquet(root / "metrics.parquet")
    trades = pd.read_parquet(root / "trades.parquet")
    assert len(metrics) == 375 and metrics.cutoff_count.eq(22).all()
    for _, g in scores.groupby("model_id"):
        assert set(g.cutoff) == dates
    for _, g in sels.groupby(["model_id", "universe_policy", "top_fraction"]):
        assert set(g.cutoff) == dates
    assert set(sels.cutoff) == dates and set(trades.cutoff) == dates
    for _, g in sels.groupby(["model_id", "universe_policy", "top_fraction", "cutoff"]):
        assert len(g) == int(np.ceil(g.eligible_n.iloc[0] * g.top_fraction.iloc[0]))
    for _, g in trades.groupby(["simulation_id", "cutoff"]):
        np.testing.assert_allclose(g.allocation, g.allocation.iloc[0], atol=1e-14)
    valid = trades[trades.entry_price.notna() & trades.exit_price.notna()]
    np.testing.assert_allclose(
        valid.return_gross, valid.exit_price / valid.entry_price - 1, atol=1e-12
    )
    np.testing.assert_allclose(
        valid.pnl_net,
        valid.shares * (valid.exit_price - valid.entry_price) - valid.entry_fee - valid.exit_fee,
        atol=1e-12,
    )
    daily = pd.read_parquet(root / "portfolio_daily.parquet")
    np.testing.assert_allclose(
        daily.equity, 1 + daily.realized_pnl + daily.unrealized_pnl, atol=1e-12, rtol=0
    )
    np.testing.assert_allclose(
        daily.equity, daily.cash + daily.long_market_value, atol=1e-12, rtol=0
    )
    sums = trades.groupby("simulation_id").pnl_net.sum()
    matched = metrics.set_index("simulation_id").cumulative_return
    np.testing.assert_allclose(sums.sort_index(), matched.sort_index(), atol=1e-12, rtol=0)
    assert metrics.max_accounting_error.max() < 1e-10
    assert trades.volume_definition_not_certified.all()
    for row in audit["models_replayed"]:
        assert row["max_score_error"] < 1e-10


def test_financial_replay_deterministic(tape):
    args = (choices(), tape, 10, 45, 2, "long_only", 0.0, tape.calendar[-1])
    first = simulate_signed(*args)
    second = simulate_signed(*args)
    pd.testing.assert_frame_equal(first[0], second[0])
    pd.testing.assert_frame_equal(first[1], second[1])
    assert first[2] == second[2]


def test_real_original_scores_exact_and_native_equals_common():
    root = Path("data/analysis/srd-horizon-common-replay-v1")
    if not (root / "summary.json").exists():
        pytest.skip("Local research data are not versioned")
    saved = pd.read_parquet(root / "scores.parquet")
    from hocus_quant.model_lab.context_data import normal_dates

    contract = json.loads((root / "contract.json").read_text())
    for source in {m["root"] for m in contract["models"]}:
        originals = normal_dates(pd.read_parquet(Path(source) / "predictions.parquet"), ["cutoff"])
        merged = saved.merge(
            originals[["model_id", "cutoff", "entity_id", "score"]],
            on=["model_id", "cutoff", "entity_id"],
            suffixes=("", "_original"),
        )
        np.testing.assert_array_equal(merged.score, merged.score_original)
    m = pd.read_parquet(root / "metrics.parquet")
    a = m[m.universe_policy == "native"]
    b = m[(m.universe_policy == "common") & (m.target != "universe")]
    paired = a.merge(b, on=["model_id", "exit_horizon", "cost_bp", "top_fraction"])
    for metric in [
        "cumulative_return",
        "max_drawdown",
        "turnover",
        "average_active_session_capital",
    ]:
        np.testing.assert_array_equal(paired[metric + "_x"], paired[metric + "_y"])
    daily = pd.read_parquet(root / "portfolio_daily.parquet")
    # Floating sums may leave about 1e-15 negative cash; no material borrowing.
    assert daily.cash.min() >= -1e-12
    assert m.max_exposure.le(1 + 1e-12).all()
