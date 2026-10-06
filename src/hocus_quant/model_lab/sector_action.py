"""Frozen stock scores gated by existing sector predictions; no training or tuning."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.common_replay import augment, concentration, write_json
from hocus_quant.model_lab.context_data import normal_dates
from hocus_quant.model_lab.metrics import correlation
from hocus_quant.model_lab.models import predict_score
from hocus_quant.model_lab.portfolio_extensions import MarketTape, simulate_signed

STRATEGIES = {
    "S0": "Action-only top 5",
    "S1": "Modèle secteurs → actions",
    "S2": "Momentum W20 secteurs → actions",
}


def rank_sectors(frame: pd.DataFrame, value: str, decision_at: pd.Timestamp) -> pd.DataFrame:
    """Gate reads only known score values/timestamps; never future outcomes."""
    allowed = frame[["sector_id", value, "source_available_at"]].copy()
    allowed = allowed[allowed.source_available_at.le(decision_at) & np.isfinite(allowed[value])]
    allowed = allowed.sort_values([value, "sector_id"], ascending=[False, True], kind="stable")
    allowed["sector_rank"] = np.arange(1, len(allowed) + 1)
    return allowed


def choose_actions(
    scores: pd.DataFrame,
    mapping: pd.DataFrame,
    sectors: list[str] | None,
    action_first: bool = False,
) -> pd.DataFrame:
    """Stable top five; filtering and ranking commute when ties use the same ID."""
    known = scores[["entity_id", "score"]].merge(
        mapping[["action_id", "sector_id"]],
        left_on="entity_id",
        right_on="action_id",
        how="left",
        validate="one_to_one",
    )
    if action_first:
        known = known.sort_values(["score", "entity_id"], ascending=[False, True], kind="stable")
    if sectors is not None:
        known = known[known.sector_id.isin(sectors)]
    known = known[np.isfinite(known.score)].sort_values(
        ["score", "entity_id"], ascending=[False, True], kind="stable"
    )
    selected = known.head(5).copy()
    selected["selected_rank"] = np.arange(1, len(selected) + 1)
    return selected


def score_inputs(config: dict, root: Path):
    source = Path(config["sector_root"])
    registry = json.loads((source / "model_registry.json").read_text())
    entry = next(x for x in registry if x["model_id"] == config["sector_model"]["model_id"])
    artifact_path = source / "models" / f"{entry['model_id']}.joblib"
    assert file_sha(artifact_path) == config["sector_model"]["model_sha256"]
    artifact = joblib.load(artifact_path)
    inputs = normal_dates(pd.read_parquet(source / "features.parquet"), ["cutoff"])
    scores = normal_dates(pd.read_parquet(source / "predictions.parquet"), ["cutoff"])
    cutoffs = [date.fromisoformat(x) for x in config["common_cutoffs"]]
    scores = scores[(scores.model_id == entry["model_id"]) & scores.cutoff.isin(cutoffs)]
    aligned = scores[["entity_id", "cutoff", "score"]].merge(
        inputs, on=["entity_id", "cutoff"], validate="one_to_one"
    )
    replay = predict_score(
        artifact["estimator"], aligned[entry["feature_ids"]].to_numpy(float), False
    )
    np.testing.assert_allclose(replay, aligned.score, rtol=1e-12, atol=1e-12)
    sector_source = normal_dates(
        pd.read_parquet(source / "source_market.parquet"), ["session_date"]
    )
    rows = []
    for day in cutoffs:
        decision = pd.Timestamp(day + timedelta(days=1), tz="UTC")
        for code in config["sector_candidates"]:
            sid = "abc-bourse-manual:index:" + code
            pred = scores[(scores.cutoff == day) & (scores.entity_id == sid)]
            past = sector_source[
                (sector_source.entity_id == sid)
                & (sector_source.session_date <= day)
                & (sector_source.available_at <= decision)
            ].sort_values("session_date")
            past = past[past.close.notna() & (past.close > 0)]
            recent = len(past) > 0 and (day - past.session_date.iloc[-1]).days <= 3
            momentum = (
                past.close.iloc[-1] / past.close.iloc[-21] - 1
                if len(past) >= 21 and recent
                else None
            )
            rows.append(
                {
                    "cutoff": day,
                    "sector_id": sid,
                    "sector_code": code,
                    "model_score": float(pred.score.iloc[0]) if len(pred) else np.nan,
                    "momentum": momentum,
                    "source_available_at": decision,
                    "last_quote_date": past.session_date.iloc[-1] if len(past) else None,
                    "momentum_history_n": len(past),
                    "model_status": "available" if len(pred) else "missing_score",
                    "model_id": entry["model_id"],
                    "target_id": entry["target_id"],
                    "historical_pit_grade": "reconstructed",
                    "mapping_historical_pit": False,
                }
            )
    data = pd.DataFrame(rows)
    data.to_parquet(root / "sector_scores.parquet", index=False)
    write_json(root / "sector_model_metadata.json", entry)
    return data, sector_source, float(np.max(np.abs(replay - aligned.score)))


def future_returns(tape: MarketTape, day: date, ids: list[str], hold: int) -> dict:
    future = [d for d in tape.calendar if d > day][:hold]
    results = {}
    for entity in ids:
        a = tape.quotes[future[0]].get(entity, {}).get("open", np.nan)
        b = tape.quotes[future[-1]].get(entity, {}).get("close", np.nan)
        results[entity] = (
            b / a - 1 if np.isfinite(a) and a > 0 and np.isfinite(b) and b > 0 else np.nan
        )
    return results


def diagnostic_ic(scores, mapping, sectors, tape, day):
    joined = scores[["entity_id", "score"]].merge(
        mapping[["action_id", "sector_id"]],
        left_on="entity_id",
        right_on="action_id",
        how="left",
        validate="one_to_one",
    )
    joined["future_return"] = joined.entity_id.map(
        future_returns(tape, day, list(joined.entity_id), 10)
    )
    rows = []
    for group, part in {
        "full": joined,
        "top2_model": joined[joined.sector_id.isin(sectors)],
        "other_mapped_sectors": joined[joined.sector_id.notna() & ~joined.sector_id.isin(sectors)],
        "unmapped": joined[joined.sector_id.isna()],
    }.items():
        valid = part[np.isfinite(part.future_return)]
        rows.append(
            {
                "cutoff": day,
                "group": group,
                "n": len(valid),
                "eligible_n": len(part),
                "missing_outcomes": len(part) - len(valid),
                "ic": correlation(valid.score.to_numpy(), valid.future_return.to_numpy())
                if len(valid) >= 5
                else None,
            }
        )
    return rows, joined


def run(config_path: Path, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    config = json.loads(config_path.read_text())
    write_json(root / "contract.json", config)
    common = Path(config["common_root"])
    base = Path(config["action_root"])
    mapping = pd.read_parquet(root / "action_sector_mapping.parquet")
    manifest = json.loads((root / "mapping_manifest.json").read_text())
    assert file_sha(root / "action_sector_mapping.parquet") == manifest["mapping_sha256"]
    paths = [
        config_path,
        root / "action_sector_mapping.parquet",
        root / "industry_bridge.json",
        common / "common_universe.parquet",
        common / "scores.parquet",
        common / "metrics.parquet",
        base / "source_market.parquet",
        base / "source_benchmark.parquet",
        Path(config["sector_root"]) / "model_registry.json",
        Path(config["sector_root"]) / "features.parquet",
        Path(config["sector_root"]) / "predictions.parquet",
        Path(config["sector_root"]) / "source_market.parquet",
    ]
    before = {str(p): file_sha(p) for p in paths}
    assert before[str(common / "common_universe.parquet")] == config["common_universe_sha256"]
    assert before[str(common / "scores.parquet")] == config["action_scores_sha256"]
    sector_scores, sector_source, error = score_inputs(config, root)
    action = normal_dates(pd.read_parquet(common / "scores.parquet"), ["cutoff"])
    action = action[action.model_id == config["action_model"]["model_id"]].copy()
    universe = normal_dates(pd.read_parquet(common / "common_universe.parquet"), ["cutoff"])
    universe = universe[(universe.score_horizon == 5) & universe.in_common]
    assert set(zip(action.cutoff, action.entity_id, strict=True)) == set(
        zip(universe.cutoff, universe.entity_id, strict=True)
    )
    action.to_parquet(root / "action_scores.parquet", index=False)
    tape = MarketTape.build(
        normal_dates(pd.read_parquet(base / "source_market.parquet"), ["session_date"]),
        normal_dates(pd.read_parquet(base / "source_benchmark.parquet"), ["session_date"]),
    )
    schedules = {key: [] for key in STRATEGIES}
    chosen = []
    ranking = []
    coverage = []
    overlap = []
    rejections = []
    conditional = []
    interactions = []
    sector_outcomes = []
    for day, part in action.groupby("cutoff", sort=True):
        decision = pd.Timestamp(day + timedelta(days=1), tz="UTC")
        sectors = sector_scores[sector_scores.cutoff == day]
        model = rank_sectors(sectors, "model_score", decision)
        mom = rank_sectors(sectors, "momentum", decision)
        top = {
            "S0": None,
            "S1": model.head(2).sector_id.tolist(),
            "S2": mom.head(2).sector_id.tolist(),
        }
        for kind, frame in [("model", model), ("momentum", mom)]:
            ranking.extend(frame.assign(cutoff=day, kind=kind).to_dict("records"))
        baskets = {s: choose_actions(part, mapping, top[s]) for s in STRATEGIES}
        check = choose_actions(part, mapping, top["S1"], action_first=True)
        assert list(check.entity_id) == list(baskets["S1"].entity_id)
        for strategy, frame in baskets.items():
            schedules[strategy].append(
                {
                    "cutoff": day,
                    "long_ids": list(frame.entity_id),
                    "short_ids": [],
                    "eligible_n": len(part),
                    "selected_n_per_leg": len(frame),
                    "allocation_slots": 5,
                }
            )
            chosen.extend(frame.assign(cutoff=day, strategy_id=strategy).to_dict("records"))
        names = part.merge(
            mapping[["action_id", "sector_id"]],
            left_on="entity_id",
            right_on="action_id",
            how="left",
            validate="one_to_one",
        )
        coverage.append(
            {
                "cutoff": day,
                "universe_n": len(part),
                "mapped_n": int(names.sector_id.notna().sum()),
                "unmapped_n": int(names.sector_id.isna().sum()),
                "model_sectors_n": len(model),
                "momentum_sectors_n": len(mom),
                "model_top2": json.dumps(top["S1"]),
                "momentum_top2": json.dumps(top["S2"]),
                "s1_actions_n": len(baskets["S1"]),
                "s2_actions_n": len(baskets["S2"]),
                "s1_cash_slots": 5 - len(baskets["S1"]),
                "s2_cash_slots": 5 - len(baskets["S2"]),
            }
        )
        for sector, g in names.groupby("sector_id", dropna=False):
            coverage[-1].setdefault("counts_by_sector", {})[str(sector)] = len(g)
        coverage[-1]["counts_by_sector"] = json.dumps(coverage[-1]["counts_by_sector"])
        a = set(baskets["S0"].entity_id)
        for strategy in ["S1", "S2"]:
            b = set(baskets[strategy].entity_id)
            removed = a - b
            added = b - a
            overlap.append(
                {
                    "cutoff": day,
                    "strategy_id": strategy,
                    "jaccard": len(a & b) / len(a | b) if a | b else 1.0,
                    "overlap_fraction": len(a & b) / 5,
                    "substitutions": len(added),
                    "removed_n": len(removed),
                    "basket_changed": a != b,
                    "identical": a == b,
                    "sector_jaccard_model_momentum": len(set(top["S1"]) & set(top["S2"]))
                    / len(set(top["S1"]) | set(top["S2"]))
                    if set(top["S1"]) | set(top["S2"])
                    else 1.0,
                    "mean_removed_action_score": part[part.entity_id.isin(removed)].score.mean(),
                    "mean_retained_action_score": part[part.entity_id.isin(a & b)].score.mean(),
                    "mean_added_action_score": part[part.entity_id.isin(added)].score.mean(),
                }
            )
            for label, ids in [("removed", removed), ("added", added), ("retained", a & b)]:
                rejections.extend(
                    names[names.entity_id.isin(ids)]
                    .assign(cutoff=day, strategy_id=strategy, change=label)
                    .to_dict("records")
                )
        rows, diag = diagnostic_ic(part, mapping, top["S1"], tape, day)
        conditional.extend(rows)
        diag = diag.merge(
            sectors[["sector_id", "model_score"]],
            on="sector_id",
            how="left",
            validate="many_to_one",
        )
        diag["action_rank_normalized"] = diag.score.rank(pct=True, method="average")
        rank_map = model.set_index("sector_id").model_score.rank(pct=True, method="average")
        diag["sector_rank_normalized"] = diag.sector_id.map(rank_map)
        diag["interaction_score"] = diag.action_rank_normalized * diag.sector_rank_normalized
        diag["cutoff"] = day
        interactions.extend(diag.to_dict("records"))
        end = [d for d in tape.calendar if d > day][9]
        for r in sectors.itertuples():
            price = sector_source[sector_source.entity_id == r.sector_id].sort_values(
                "session_date"
            )
            old = price[price.session_date <= day]
            future = price[price.session_date <= end]
            valid = (
                len(old) > 0
                and len(future) > 0
                and (day - old.session_date.iloc[-1]).days <= 3
                and (end - future.session_date.iloc[-1]).days <= 3
            )
            actual = future.close.iloc[-1] / old.close.iloc[-1] - 1 if valid else np.nan
            sector_outcomes.append(
                {
                    "cutoff": day,
                    "sector_id": r.sector_id,
                    "model_score": r.model_score,
                    "sector_future_return": actual,
                    "target_end": end,
                    "selected_model": r.sector_id in top["S1"],
                    "selected_momentum": r.sector_id in top["S2"],
                }
            )
    allmetrics = []
    alltrades = []
    daily = []
    cutoff_rows = []
    attrs = []
    contribution_daily = []
    names = mapping.set_index("action_id")
    baseline = pd.read_parquet(common / "metrics.parquet")
    for strategy, decisions in schedules.items():
        for cost in config["costs_bp"]:
            eq, trades, stats = simulate_signed(
                decisions, tape, 10, cost, 2, "long_only", 0.0, date(2026, 7, 31)
            )
            if len(trades):
                eq, trades, extra = augment(eq, trades, tape)
            else:
                eq = eq.assign(
                    active_session_capital=0.0,
                    active_position_count=0,
                    realized_pnl=0.0,
                    unrealized_pnl=0.0,
                    cash_fraction=1.0,
                )
                trades = trades.assign(
                    holding_sessions=0, delay_sessions=0, contribution_points=0.0
                )
                extra = {
                    "median_trade_return": None,
                    "median_exposure": 0.0,
                    "max_exposure": 0.0,
                    "average_active_session_capital": 0.0,
                    "max_active_session_capital": 0.0,
                    "average_cash_fraction": 1.0,
                    "average_capital_engaged": 0.0,
                    "average_holding_sessions": 0.0,
                    "average_holding_calendar_days": 0.0,
                    "max_simultaneous_positions": 0,
                    "average_active_positions": 0.0,
                    "delay_mean_sessions": 0.0,
                    "delay_max_sessions": 0,
                    "delayed_pnl": 0.0,
                    "max_accounting_error": float(np.max(np.abs(eq.equity - 1))),
                }
            trades["sector_id"] = trades.entity_id.map(names.sector_id).fillna("UNMAPPED")
            trades["instrument"] = trades.entity_id.map(names.instrument)
            trades["ISIN"] = trades.entity_id.str.rsplit(":", n=1).str[-1]
            trades = trades.merge(
                action[["entity_id", "cutoff", "score"]],
                on=["entity_id", "cutoff"],
                validate="one_to_one",
            )
            meta = {
                "strategy_id": strategy,
                "strategy_name": STRATEGIES[strategy],
                "cost_bp": cost,
                "action_model_id": config["action_model"]["model_id"],
                "sector_model_id": config["sector_model"]["model_id"],
                "holding_horizon": 10,
                "sleeves": 2,
                "action_slots": 5,
                "volume_definition_not_certified": True,
            }
            for k, v in meta.items():
                trades[k] = v
                eq[k] = v
            cp = trades.groupby("cutoff", as_index=False).agg(
                pnl=("pnl_net", "sum"),
                trades=("entry_price", "count"),
                allocated=("allocation", "sum"),
                selected_n=("entity_id", "size"),
            )
            cp = (
                cp.set_index("cutoff")
                .reindex([date.fromisoformat(x) for x in config["common_cutoffs"]])
                .fillna(0)
                .reset_index()
            )
            cp["basket_budget"] = cp.allocated * 5 / cp.selected_n.replace(0, np.nan)
            cp["basket_return"] = (cp.pnl / cp.basket_budget).fillna(0.0)
            cp["contribution_points"] = cp.pnl * 100
            sectors_pnl = (
                trades.fillna({"sector_id": "UNMAPPED"})
                .groupby("sector_id", as_index=False)
                .agg(
                    pnl=("pnl_net", "sum"),
                    trades=("entry_price", "count"),
                    hit_rate=("return_net", lambda x: float((x.dropna() > 0).mean())),
                    allocated_capital=("allocation", "sum"),
                )
            )
            # Sector exposure from the same executed shares, marks and dates as NAV.
            weights = []
            for e in eq.itertuples():
                active = trades[
                    trades.entry_price.notna()
                    & (trades.entry_date <= e.session_date)
                    & (trades.exit_date.isna() | (trades.exit_date > e.session_date))
                ]
                amounts = {}
                for t in active.itertuples():
                    last = max(
                        d
                        for d in tape.calendar
                        if t.entry_date <= d <= e.session_date
                        and np.isfinite(tape.quotes[d].get(t.entity_id, {}).get("close", np.nan))
                    )
                    amounts[t.sector_id] = (
                        amounts.get(t.sector_id, 0)
                        + t.shares * tape.quotes[last][t.entity_id]["close"]
                    )
                for sec in sectors_pnl.sector_id:
                    weights.append(
                        {
                            "session_date": e.session_date,
                            "sector_id": sec,
                            "weight": amounts.get(sec, 0) / e.equity,
                        }
                    )
            weights = pd.DataFrame(weights)
            if weights.empty:
                weights = pd.DataFrame(columns=["session_date", "sector_id", "weight"])
                sectors_pnl["average_weight"] = 0.0
            else:
                sectors_pnl = sectors_pnl.merge(
                    weights.groupby("sector_id").weight.mean().rename("average_weight"),
                    on="sector_id",
                )
            sectors_pnl["contribution_points"] = sectors_pnl.pnl * 100
            attrs.extend(sectors_pnl.assign(**meta).to_dict("records"))
            contribution_daily.append(weights.assign(**meta))
            cc = concentration(trades)
            metric = (
                meta
                | stats
                | extra
                | cc
                | {
                    "cutoff_count": 22,
                    "average_actions_per_basket": len(trades) / 22,
                    "positive_cutoff_fraction": float((cp.pnl > 0).mean()),
                    "best_cutoff": str(cp.loc[cp.pnl.idxmax(), "cutoff"]),
                    "best_cutoff_pnl": float(cp.pnl.max()),
                    "worst_cutoff": str(cp.loc[cp.pnl.idxmin(), "cutoff"]),
                    "worst_cutoff_pnl": float(cp.pnl.min()),
                    "top_sector_contribution": float(sectors_pnl.pnl.max())
                    if len(sectors_pnl)
                    else 0.0,
                    "top2_sector_contribution": float(sectors_pnl.pnl.nlargest(2).sum()),
                }
            )
            if strategy == "S0":
                old = baseline[
                    (baseline.model_id == config["action_model"]["model_id"])
                    & (baseline.exit_horizon == 10)
                    & (baseline.cost_bp == cost)
                    & (baseline.universe_policy == "common")
                    & (baseline.top_fraction == 0.03)
                ].iloc[0]
                for key in ["cumulative_return", "max_drawdown", "turnover", "average_exposure"]:
                    assert abs(metric[key] - old[key]) < 1e-12, (key, metric[key], old[key])
            allmetrics.append(metric)
            alltrades.append(trades)
            daily.append(eq)
            cutoff_rows.append(cp.assign(**meta))
            print("SECTOR REPLAY", strategy, cost, flush=True)
    for name, frame in {
        "selections": pd.DataFrame(chosen),
        "sector_rankings": pd.DataFrame(ranking),
        "coverage": pd.DataFrame(coverage),
        "rejections": pd.DataFrame(rejections),
        "selection_overlap": pd.DataFrame(overlap),
        "conditional_ic": pd.DataFrame(conditional),
        "interaction_diagnostics": pd.DataFrame(interactions),
        "sector_outcomes": pd.DataFrame(sector_outcomes),
        "metrics": pd.DataFrame(allmetrics),
        "trades": pd.concat(alltrades),
        "portfolio_daily": pd.concat(daily),
        "portfolio_cutoff": pd.concat(cutoff_rows),
        "sector_attribution": pd.DataFrame(attrs),
        "sector_daily_weights": pd.concat(contribution_daily),
    }.items():
        frame.to_parquet(root / f"{name}.parquet", index=False)
    audit = {
        "development_only": True,
        "fit_calls": 0,
        "tuning_calls": 0,
        "input_sha256": before,
        "inputs_unchanged": all(file_sha(Path(p)) == s for p, s in before.items()),
        "sector_score_replay_error": error,
        "original_action_scores_preserved": True,
        "gate_uses_outcomes": False,
        "s1_equals_s1b": True,
        "mapping_grade": "current snapshot projected backward; not historical PIT",
        "volume_definition_not_certified": True,
        "S0_matches_common_replay": True,
        "source_code_sha256": file_sha(Path(__file__)),
        "config_sha256": file_sha(config_path),
        "max_accounting_error": max(x["max_accounting_error"] for x in allmetrics),
    }
    assert audit["inputs_unchanged"]
    write_json(root / "audit.json", audit)
    summary = {
        "cutoffs": 22,
        "models_reused": 2,
        "strategies": 3,
        "simulations": 9,
        "s1b_duplicate": True,
        "mapped_actions": manifest["mapped"],
        "total_actions": manifest["actions"],
        "development_only": True,
    }
    write_json(root / "summary.json", summary)
    return summary
