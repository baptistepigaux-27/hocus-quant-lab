from __future__ import annotations

import ast
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hocus_quant.model_lab.common_replay import augment
from hocus_quant.model_lab.portfolio_extensions import MarketTape, simulate_signed
from hocus_quant.model_lab.sector_action import choose_actions, rank_sectors


@pytest.fixture
def data():
    stocks = pd.DataFrame({"entity_id": [f"a{i}" for i in range(12)], "score": np.arange(12.0)})
    mapping = pd.DataFrame(
        {"action_id": stocks.entity_id, "sector_id": ["X"] * 4 + ["Y"] * 4 + ["Z"] * 4}
    )
    sectors = pd.DataFrame(
        {
            "sector_id": ["X", "Y", "Z"],
            "model_score": [0.9, 0.8, 0.1],
            "momentum": [0.1, 0.2, 0.9],
            "source_available_at": pd.Timestamp("2026-01-03", tz="UTC"),
        }
    )
    return stocks, mapping, sectors


def test_top2_and_top5_total_not_per_sector(data):
    stocks, mapping, sectors = data
    ranked = rank_sectors(sectors, "model_score", pd.Timestamp("2026-01-03", tz="UTC"))
    assert list(ranked.head(2).sector_id) == ["X", "Y"]
    picked = choose_actions(stocks, mapping, list(ranked.head(2).sector_id))
    assert len(picked) == 5 and set(picked.sector_id) <= {"X", "Y"}
    assert set(picked.entity_id) == {"a7", "a6", "a5", "a4", "a3"}


def test_s0_unfiltered_and_action_first_equivalence(data):
    s, m, _ = data
    assert list(choose_actions(s, m, None).entity_id) == ["a11", "a10", "a9", "a8", "a7"]
    pd.testing.assert_frame_equal(
        choose_actions(s, m, ["X", "Y"]), choose_actions(s, m, ["X", "Y"], action_first=True)
    )


def test_gate_ignores_future_and_rejects_future_timestamps(data):
    s, m, t = data
    at = pd.Timestamp("2026-01-03", tz="UTC")
    ranks = rank_sectors(t, "model_score", at)
    changed = t.assign(future_return=[-999, 999, 100], target_value=[1, 0, 1])
    pd.testing.assert_frame_equal(ranks, rank_sectors(changed, "model_score", at))
    t.loc[t.sector_id == "X", "source_available_at"] = pd.Timestamp("2026-01-04", tz="UTC")
    assert "X" not in set(rank_sectors(t, "model_score", at).sector_id)
    a = choose_actions(s, m, ["X", "Y"])
    pd.testing.assert_frame_equal(
        a, choose_actions(s.assign(future_return=-s.score), m, ["X", "Y"])
    )


def test_missing_mapping_and_score_do_not_fabricate_sector(data):
    s, m, t = data
    m.loc[m.action_id == "a7", "sector_id"] = None
    picked = choose_actions(s, m, ["X", "Y"])
    assert "a7" not in picked.entity_id.tolist() and len(picked) == 5
    assert "a7" in choose_actions(s, m, None).entity_id.tolist()
    t.loc[t.sector_id == "X", "model_score"] = np.nan
    r = rank_sectors(t, "model_score", pd.Timestamp("2026-01-03", tz="UTC"))
    assert list(r.sector_id) == ["Y", "Z"]
    assert choose_actions(s, m, []).empty


def test_s2_uses_momentum_not_model_score(data):
    _, _, t = data
    at = pd.Timestamp("2026-01-03", tz="UTC")
    first = rank_sectors(t, "momentum", at)
    second = rank_sectors(
        t.assign(model_score=[1e9, -1e9, 0], future_return=[3, 2, 1]), "momentum", at
    )
    pd.testing.assert_frame_equal(first, second)
    assert list(first.head(2).sector_id) == ["Z", "Y"]


def test_ties_and_input_order_deterministic(data):
    s, m, t = data
    s["score"] = 1.0
    t["model_score"] = 1.0
    a = choose_actions(s, m, ["X", "Y"])
    b = choose_actions(s.sample(frac=1, random_state=7), m, ["X", "Y"])
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
    at = pd.Timestamp("2026-01-03", tz="UTC")
    assert list(rank_sectors(t.sample(frac=1, random_state=8), "model_score", at).sector_id) == [
        "X",
        "Y",
        "Z",
    ]


@pytest.fixture
def tape():
    days = pd.bdate_range("2026-01-05", "2026-01-30").date.tolist()
    rows = [
        {
            "session_date": d,
            "entity_id": f"a{i}",
            "open": 100.0,
            "close": 101.0,
            "high": 102.0,
            "low": 99.0,
            "volume": 1000.0,
        }
        for d in days
        for i in range(5)
    ]
    return MarketTape.build(
        pd.DataFrame(rows), pd.DataFrame({"session_date": days, "open": 100.0, "close": 101.0})
    )


@pytest.mark.parametrize("count", [0, 1, 2, 5])
@pytest.mark.parametrize("cost", [0, 25, 45])
def test_reserved_five_slots_next_open_h10_and_cash(tape, count, cost):
    choices = [
        {
            "cutoff": date(2026, 1, 2),
            "long_ids": [f"a{i}" for i in range(count)],
            "short_ids": [],
            "allocation_slots": 5,
            "eligible_n": 5,
        }
    ]
    eq, t, stats = simulate_signed(choices, tape, 10, cost, 2, "long_only", 0.0, tape.calendar[-1])
    assert stats["sleeves"] == 2 and stats["holding_horizon"] == 10
    if count:
        np.testing.assert_allclose(t.allocation, 0.1)
        assert set(t.entry_date) == {tape.calendar[0]} and set(t.exit_date) == {tape.calendar[9]}
        assert eq.cash.iloc[0] == pytest.approx(1 - 0.1 * count)
        np.testing.assert_allclose(t.entry_fee, t.entry_nominal * cost / 20000)
        np.testing.assert_allclose(t.exit_fee, t.shares * t.exit_price * cost / 20000)
        q, _, _ = augment(eq, t, tape)
        np.testing.assert_allclose(q.equity, 1 + q.realized_pnl + q.unrealized_pnl, atol=1e-12)
    else:
        assert t.empty and eq.equity.eq(1.0).all() and eq.cash.eq(1.0).all()
    assert eq.cash.min() >= -1e-12
    # Same replay, same results; no stochastic portfolio operations.
    again = simulate_signed(choices, tape, 10, cost, 2, "long_only", 0.0, tape.calendar[-1])
    pd.testing.assert_frame_equal(eq, again[0])


def test_no_fit_or_tuning_calls():
    tree = ast.parse(Path("src/hocus_quant/model_lab/sector_action.py").read_text())
    forbidden = {"fit", "fit_transform", "partial_fit", "fit_model", "make_model", "choose_trial"}
    attrs = {
        n.func.attr
        if isinstance(n.func, ast.Attribute)
        else n.func.id
        if isinstance(n.func, ast.Name)
        else ""
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
    }
    assert not attrs.intersection(forbidden)


def test_real_replay_contract():
    root = Path("data/analysis/srd-sector-action-v1")
    if not (root / "summary.json").exists():
        pytest.skip("Local research artefacts are not versioned")
    config = json.loads((root / "contract.json").read_text())
    audit = json.loads((root / "audit.json").read_text())
    dates = {date.fromisoformat(x) for x in config["common_cutoffs"]}
    old = json.loads(
        Path("data/analysis/srd-horizon-common-replay-v1/common_cutoffs.json").read_text()
    )
    assert dates == {date.fromisoformat(x) for x in old["common_cutoffs"]} and len(dates) == 22
    assert audit["fit_calls"] == audit["tuning_calls"] == 0 and audit["inputs_unchanged"]
    assert audit["s1_equals_s1b"] and audit["S0_matches_common_replay"]
    selections = pd.read_parquet(root / "selections.parquet")
    coverage = pd.read_parquet(root / "coverage.parquet")
    metrics = pd.read_parquet(root / "metrics.parquet")
    assert set(coverage.cutoff) == dates and len(metrics) == 9 and metrics.cutoff_count.eq(22).all()
    action = pd.read_parquet(root / "action_scores.parquet")
    for row in coverage.itertuples():
        allowed = json.loads(row.model_top2)
        s1 = selections[(selections.cutoff == row.cutoff) & (selections.strategy_id == "S1")]
        assert len(s1) <= 5 and set(s1.sector_id) <= set(allowed) and len(allowed) == 2
    joined = selections.merge(
        action[["entity_id", "cutoff", "score"]],
        on=["entity_id", "cutoff"],
        suffixes=("", "_original"),
    )
    np.testing.assert_array_equal(joined.score, joined.score_original)
    daily = pd.read_parquet(root / "portfolio_daily.parquet")
    trades = pd.read_parquet(root / "trades.parquet")
    np.testing.assert_allclose(
        daily.equity, 1 + daily.realized_pnl + daily.unrealized_pnl, atol=1e-12, rtol=0
    )
    np.testing.assert_allclose(
        daily.equity, daily.cash + daily.long_market_value, atol=1e-12, rtol=0
    )
    for _, g in trades.groupby(["strategy_id", "cost_bp", "cutoff"]):
        np.testing.assert_allclose(g.allocation, g.allocation.iloc[0])
    assert daily.cash.min() >= -1e-12 and trades.holding_horizon.eq(10).all()
    assert trades.cost_bp.isin([0, 25, 45]).all()
    assert audit["mapping_grade"].startswith("current snapshot")


def test_real_sector_attribution_and_availability():
    root = Path("data/analysis/srd-sector-action-v1")
    if not (root / "summary.json").exists():
        pytest.skip("Local research artefacts are not versioned")
    m = pd.read_parquet(root / "metrics.parquet").set_index(["strategy_id", "cost_bp"])
    attribution = (
        pd.read_parquet(root / "sector_attribution.parquet")
        .groupby(["strategy_id", "cost_bp"])
        .agg(pnl=("pnl", "sum"), weight=("average_weight", "sum"))
    )
    np.testing.assert_allclose(attribution.pnl, m.cumulative_return, atol=1e-12, rtol=0)
    np.testing.assert_allclose(attribution.weight, m.average_exposure, atol=1e-12, rtol=0)
    sectors = pd.read_parquet(root / "sector_scores.parquet")
    cutoff = pd.to_datetime(sectors.cutoff, utc=True) + pd.Timedelta(days=1)
    assert sectors.source_available_at.le(cutoff).all()
    config = json.loads((root / "contract.json").read_text())
    assert max(config["sector_model"]["final_training_dates"]) < "2025-07-01"
    mapping = pd.read_parquet(root / "action_sector_mapping.parquet")
    assert not mapping.historical_pit.any()  # Current mapping is an explicit assumption.
    assert (mapping.ISIN == mapping.quote_identity_isin).all()
    assert set(mapping.sector_id) <= set(sectors.sector_id)
