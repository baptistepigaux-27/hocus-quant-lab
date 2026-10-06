"""Frozen-model common-date replay. Cohorts and selections never use outcomes."""

from __future__ import annotations

import json
from datetime import date
from itertools import combinations
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha
from hocus_quant.model_lab.context_data import normal_dates
from hocus_quant.model_lab.metrics import correlation
from hocus_quant.model_lab.models import predict_score
from hocus_quant.model_lab.portfolio_extensions import MarketTape, picks, simulate_signed


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def selection(scores: pd.DataFrame, fraction: float) -> tuple[list[dict], pd.DataFrame]:
    """Whitelist only observable fields, so poisoned future columns cannot select."""
    ordered = scores[["cutoff", "entity_id", "score"]].copy()
    selected = picks(ordered, fraction)
    ordered = ordered.sort_values(["cutoff", "score", "entity_id"], ascending=[True, False, True])
    ordered["score_rank"] = ordered.groupby("cutoff").cumcount() + 1
    records = []
    for s in selected:
        part = ordered[(ordered.cutoff == s["cutoff"]) & ordered.entity_id.isin(s["long_ids"])]
        records.extend(
            part.assign(eligible_n=s["eligible_n"], selected_n=len(part)).to_dict("records")
        )
    return selected, pd.DataFrame(records)


def cohorts(
    eligibilities: dict[int, pd.DataFrame], cutoffs: list[date]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, counts = [], []
    for day in cutoffs:
        native = {
            h: set(e.loc[(e.cutoff == day) & e.eligible_at_T, "entity_id"])
            for h, e in eligibilities.items()
        }
        common = set.intersection(*native.values())
        if not common:
            raise ValueError(f"Empty ex ante common universe {day}")
        for h, ids in native.items():
            counts.append(
                {
                    "cutoff": day,
                    "score_horizon": h,
                    "native_n": len(ids),
                    "common_n": len(common),
                    "coverage_loss": 1 - len(common) / len(ids),
                    "excluded_ids": json.dumps(sorted(ids - common)),
                }
            )
            rows.extend(
                {
                    "cutoff": day,
                    "entity_id": entity,
                    "score_horizon": h,
                    "in_common": entity in common,
                }
                for entity in sorted(ids)
            )
    return pd.DataFrame(rows), pd.DataFrame(counts)


def augment(
    eq: pd.DataFrame, ledger: pd.DataFrame, tape: MarketTape
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Accounting and intraday exposure at original fills, including suspensions."""
    ledger = ledger.copy()
    executed = ledger.entry_price.notna()
    ledger["execution_warning"] = ""
    for i, r in ledger.loc[~executed].iterrows():
        price = tape.quotes[r.entry_date].get(r.entity_id, {}).get("open", np.nan)
        ledger.loc[i, "execution_warning"] = (
            "missing_entry_open" if not np.isfinite(price) or price <= 0 else "no_available_budget"
        )
    ledger["holding_sessions"] = [
        sum(a <= day <= b for day in tape.calendar) if pd.notna(a) and pd.notna(b) else 0
        for a, b in zip(ledger.entry_date, ledger.exit_date, strict=True)
    ]
    ledger["delay_sessions"] = [
        sum(a < day <= b for day in tape.calendar) if pd.notna(b) else 0
        for a, b in zip(ledger.scheduled_exit, ledger.exit_date, strict=True)
    ]
    ledger["contribution_points"] = ledger.pnl_net * 100
    eq = eq.copy()
    active_capital, active_n, realized, unrealized = [], [], [], []
    maximum_error = 0.0
    previous_nav = 1.0
    for r in eq.itertuples(index=False):
        active = ledger[
            executed
            & (ledger.entry_date <= r.session_date)
            & (ledger.exit_date.isna() | (ledger.exit_date >= r.session_date))
        ]
        active_capital.append(float(active.entry_nominal.sum() / previous_nav))
        active_n.append(len(active))
        closed = ledger[executed & ledger.exit_date.notna() & (ledger.exit_date <= r.session_date)]
        rpnl = float(closed.pnl_net.sum())
        open_positions = ledger[
            executed
            & (ledger.entry_date <= r.session_date)
            & (ledger.exit_date.isna() | (ledger.exit_date > r.session_date))
        ]
        upnl = 0.0
        for t in open_positions.itertuples(index=False):
            day = max(
                d
                for d in tape.calendar
                if t.entry_date <= d <= r.session_date
                and np.isfinite(tape.quotes[d].get(t.entity_id, {}).get("close", np.nan))
            )
            mark = tape.quotes[day][t.entity_id]["close"]
            upnl += t.shares * (mark - t.entry_price) - t.entry_fee
        error = max(abs(1 + rpnl + upnl - r.equity), abs(r.cash + r.long_market_value - r.equity))
        maximum_error = max(maximum_error, error)
        if error > 1e-10:
            raise ValueError("Daily NAV reconciliation failed")
        realized.append(rpnl)
        unrealized.append(upnl)
        previous_nav = r.equity
    eq["active_session_capital"] = active_capital
    eq["active_position_count"] = active_n
    eq["realized_pnl"] = realized
    eq["unrealized_pnl"] = unrealized
    eq["cash_fraction"] = eq.cash / eq.equity
    completed = ledger[executed & ledger.exit_date.notna()]
    attrs = {
        "median_trade_return": float(completed.return_net.median()),
        "median_exposure": float(eq.gross_exposure.median()),
        "max_exposure": float(eq.gross_exposure.max()),
        "average_active_session_capital": float(eq.active_session_capital.mean()),
        "max_active_session_capital": float(eq.active_session_capital.max()),
        "average_cash_fraction": float(eq.cash_fraction.mean()),
        "average_capital_engaged": float(eq.long_market_value.mean()),
        "average_holding_sessions": float(completed.holding_sessions.mean()),
        "average_holding_calendar_days": float(completed.holding_calendar_days.mean()),
        "max_simultaneous_positions": int(eq.active_position_count.max()),
        "average_active_positions": float(eq.active_position_count.mean()),
        "delay_mean_sessions": float(
            completed.loc[completed.delay_sessions > 0, "delay_sessions"].mean()
        )
        if (completed.delay_sessions > 0).any()
        else 0.0,
        "delay_max_sessions": int(completed.delay_sessions.max()),
        "delayed_pnl": float(completed.loc[completed.delay_sessions > 0, "pnl_net"].sum()),
        "max_accounting_error": maximum_error,
    }
    return eq, ledger, attrs


def concentration(ledger: pd.DataFrame) -> dict:
    pnl = ledger.pnl_net.sort_values(ascending=False)
    total = float(pnl.sum())
    positive = pnl[pnl > 0]
    absolute = pnl.abs()
    out = {
        "total_pnl": total,
        "negative_top5_contribution": float(pnl.tail(5).sum()),
        "absolute_contribution_hhi": float(((absolute / absolute.sum()) ** 2).sum())
        if absolute.sum()
        else None,
        "positive_contribution_hhi": float(((positive / positive.sum()) ** 2).sum())
        if positive.sum()
        else None,
    }
    for n in [1, 3, 5, 10]:
        out[f"top{n}_contribution"] = float(pnl.head(n).sum())
        out[f"top_{n}_share"] = float(pnl.head(n).sum() / total) if abs(total) > 1e-15 else None
    return out


def load_scores(
    contract: dict, days: list[date], audit: dict
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    roots = sorted({e["root"] for e in contract["models"]})
    frames, roots_elig, score_frames, replay = {}, {}, [], []
    before = {}
    for root in roots:
        p = Path(root)
        for name in [
            "features.parquet",
            "eligibility.parquet",
            "predictions.parquet",
            "source_market.parquet",
            "source_benchmark.parquet",
            "model_registry.json",
        ]:
            before[str(p / name)] = file_sha(p / name)
        frames[root] = normal_dates(pd.read_parquet(p / "features.parquet"), ["cutoff"])
        roots_elig[root] = normal_dates(pd.read_parquet(p / "eligibility.parquet"), ["cutoff"])
    elig = {e["horizon"]: roots_elig[e["root"]] for e in contract["models"]}
    universe, counts = cohorts(elig, days)
    for e in contract["models"]:
        root = Path(e["root"])
        registry = json.loads((root / "model_registry.json").read_text())
        entry = next(x for x in registry if x["model_id"] == e["model_id"])
        best = max(
            (
                x
                for x in registry
                if x["target"] == e["target"]
                and x["horizon"] == e["horizon"]
                and x["validation_metric"] is not None
            ),
            key=lambda x: x["validation_metric"],
        )
        assert best["model_id"] == entry["model_id"] and entry["model_sha256"] == e["model_sha256"]
        model_file = root / "models" / f"{entry['model_id']}.joblib"
        assert file_sha(model_file) == entry["model_sha256"]
        before[str(model_file)] = file_sha(model_file)
        original = normal_dates(pd.read_parquet(root / "predictions.parquet"), ["cutoff"])
        original = original[
            (original.model_id == e["model_id"])
            & (original.split == "test")
            & original.cutoff.isin(days)
        ]
        observed = original[["cutoff", "entity_id", "score"]].copy()
        native = universe[universe.score_horizon == e["horizon"]][
            ["cutoff", "entity_id", "in_common"]
        ]
        part = native.merge(observed, on=["cutoff", "entity_id"], validate="one_to_one", how="left")
        matrix = part[["cutoff", "entity_id"]].merge(
            frames[str(root)], on=["cutoff", "entity_id"], validate="one_to_one"
        )
        artifact = joblib.load(model_file)
        regenerated = predict_score(
            artifact["estimator"],
            matrix[entry["feature_ids"]].to_numpy(float),
            artifact["classification"],
        )
        present = part.score.notna()
        assert np.allclose(regenerated[present], part.loc[present, "score"], rtol=1e-12, atol=1e-12)
        maximum = float(
            np.max(np.abs(regenerated[present] - part.loc[present, "score"].to_numpy()))
        )
        missing = int((~present).sum())
        part.loc[~present, "score"] = regenerated[~present]
        part["score_origin"] = np.where(present, "original_export", "saved_model_inference")
        assert np.isfinite(part.score).all()
        for key in ["model_id", "target", "target_id", "model"]:
            part[key] = e[key]
        part["score_horizon"] = e["horizon"]
        score_frames.append(part)
        replay.append(
            {
                "model_id": e["model_id"],
                "original_scores": int(present.sum()),
                "additional_inference_scores": missing,
                "max_score_error": maximum,
            }
        )
    audit.update(
        {
            "models_replayed": replay,
            "fit_calls": 0,
            "tuning_calls": 0,
            "input_sha256": before,
            "cohort_source": "eligibility at T, independent of future targets",
            "source_features_identical": len(
                {before[str(Path(r) / "features.parquet")] for r in roots}
            )
            == 1,
        }
    )
    return pd.concat(score_frames, ignore_index=True), universe, counts, before


def overlap(scores: pd.DataFrame, chosen: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scope, top, day), group in chosen.groupby(["universe_policy", "top_fraction", "cutoff"]):
        for a, b in combinations(sorted(group.model_id.unique()), 2):
            sa = set(group.loc[group.model_id == a, "entity_id"])
            sb = set(group.loc[group.model_id == b, "entity_id"])
            pool = scores[scores.cutoff == day]
            left = pool[pool.model_id == a][["entity_id", "score"]]
            right = pool[pool.model_id == b][["entity_id", "score"]]
            pair = left.merge(right, on="entity_id", suffixes=("_a", "_b"), validate="one_to_one")
            rows.append(
                {
                    "universe_policy": scope,
                    "top_fraction": top,
                    "cutoff": day,
                    "model_a": a,
                    "model_b": b,
                    "jaccard": len(sa & sb) / len(sa | sb),
                    "overlap_fraction": len(sa & sb) / min(len(sa), len(sb)),
                    "score_correlation": float(pair.score_a.corr(pair.score_b)),
                    "rank_correlation": correlation(
                        pair.score_a.to_numpy(), pair.score_b.to_numpy()
                    ),
                    "common_n": len(pair),
                }
            )
    return pd.DataFrame(rows)


def run(config: Path, output: Path) -> dict:
    contract = json.loads(config.read_text())
    days = [date.fromisoformat(d) for d in contract["common_cutoffs"]]
    original_inventory = json.loads(
        Path("data/analysis/srd-price-audit-v1/common_cutoffs.json").read_text()
    )
    assert len(days) == 22 and contract["common_cutoffs"] == original_inventory["common_cutoffs"]
    assert contract["sleeves"] == 2 and contract["top_fractions"] == [0.03, 0.10]
    assert contract["costs_round_trip_bp"] == [0, 25, 45]
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "contract.json", contract)
    write_json(output / "common_cutoffs.json", {"common_cutoffs": contract["common_cutoffs"]})
    audit = {
        "development_only": True,
        "config_sha256": file_sha(config),
        "source_code_sha256": file_sha(Path(__file__)),
        "cutoffs": 22,
    }
    scores, universe, counts, before = load_scores(contract, days, audit)
    scores.to_parquet(output / "scores.parquet", index=False)
    universe.to_parquet(output / "common_universe.parquet", index=False)
    counts.to_parquet(output / "cohort_counts.parquet", index=False)
    root = Path(contract["models"][0]["root"])
    market = normal_dates(pd.read_parquet(root / "source_market.parquet"), ["session_date"])
    benchmark = normal_dates(pd.read_parquet(root / "source_benchmark.parquet"), ["session_date"])
    tape = MarketTape.build(market, benchmark)
    calendar = [
        d
        for d in tape.calendar
        if date(2026, 1, 1) <= d <= date.fromisoformat(contract["end_date"])
    ]
    bench_calendar = set(benchmark.session_date) & set(calendar)
    audit["calendar_sessions"] = len(calendar)
    audit["equity_only_calendar_dates"] = [str(x) for x in sorted(set(calendar) - bench_calendar)]
    audit["calendar_grade"] = (
        "observed equity union reconciled to preserved benchmark, not independently certified"
    )
    old_audit = json.loads(Path("data/analysis/srd-price-audit-v1/audit.json").read_text())
    source_sha = old_audit["input_sha256"][
        "data/analysis/srd-short-horizons-v1/source_market.parquet"
    ]
    assert file_sha(root / "source_market.parquet") == source_sha
    cases = normal_dates(
        pd.read_csv("data/analysis/srd-price-audit-v1/material_cases.csv"),
        ["cutoff", "entry_date", "exit_date"],
    )
    reused = {
        (r.entity_id, r.entry_date, r.exit_date): r.primary_price_status for r in cases.itertuples()
    }
    names = json.loads(Path("docs/RANK_PORTFOLIO_LABELS.json").read_text())["labels"]
    schedules = []
    selections = []
    all_metrics = []
    daily = []
    ledgers = []
    cutoff_rows = []
    cons = []
    diagnostics = []
    for (mid, scope, top), part in [
        ((mid, scope, top), part if scope == "native" else part[part.in_common])
        for mid, part in scores.groupby("model_id", sort=True)
        for scope in contract["universes"]
        for top in contract["top_fractions"]
    ]:
        chosen, frame = selection(part, top)
        meta = part.iloc[0]
        frame = frame.assign(
            model_id=mid,
            target=meta.target,
            target_id=meta.target_id,
            score_horizon=int(meta.score_horizon),
            model=meta.model,
            universe_policy=scope,
            top_fraction=top,
        )
        selections.append(frame)
        schedules.append(
            (
                chosen,
                frame,
                meta.target,
                int(meta.score_horizon),
                meta.model,
                mid,
                scope,
                top,
                meta.target_id,
            )
        )
    common = universe[(universe.score_horizon == 1) & universe.in_common]
    bench_selection = [
        {
            "cutoff": d,
            "long_ids": sorted(p.entity_id),
            "short_ids": [],
            "selected_n_per_leg": len(p),
            "eligible_n": len(p),
        }
        for d, p in common.groupby("cutoff")
    ]
    for h in contract["exit_horizons"]:
        schedules.append(
            (
                bench_selection,
                None,
                "universe",
                h,
                "universe",
                f"universe-h{h}",
                "common",
                1.0,
                "universe",
            )
        )
    for task, (chosen, frame, target, h, model, mid, scope, top, tid) in enumerate(schedules, 1):
        for hold in (
            [x for x in contract["exit_horizons"] if x >= h] if target != "universe" else [h]
        ):
            for cost in contract["costs_round_trip_bp"]:
                sid = f"{mid}-{scope}-top{int(top * 100)}-exit{hold}-cost{cost}"
                meta = {
                    "simulation_id": sid,
                    "model_id": mid,
                    "target": target,
                    "target_id": tid,
                    "score_horizon": h if target != "universe" else 0,
                    "exit_horizon": hold,
                    "model": model,
                    "universe_policy": scope,
                    "top_fraction": top,
                    "cost_bp": cost,
                }
                eq, ledger, stats = simulate_signed(
                    chosen,
                    tape,
                    hold,
                    cost,
                    2,
                    "long_only",
                    0.0,
                    date.fromisoformat(contract["end_date"]),
                )
                eq, ledger, extra = augment(eq, ledger, tape)
                for k, v in meta.items():
                    eq[k] = v
                    ledger[k] = v
                if frame is not None:
                    ledger = ledger.merge(
                        frame[["cutoff", "entity_id", "score", "score_rank"]],
                        on=["cutoff", "entity_id"],
                        validate="one_to_one",
                    )
                else:
                    ledger["score"] = np.nan
                    ledger["score_rank"] = np.nan
                ledger["ISIN"] = ledger.entity_id.str.rsplit(":", n=1).str[-1]
                ledger["instrument"] = ledger.ISIN.map(
                    lambda isin: names.get(isin, {}).get("name", isin)
                )
                ledger["volume_definition_not_certified"] = True
                ledger["price_audit_status"] = [
                    reused.get((r.entity_id, r.entry_date, r.exit_date), "pending_new_case")
                    for r in ledger.itertuples()
                ]
                ledger["entry_volume"] = [
                    tape.quotes[r.entry_date].get(r.entity_id, {}).get("volume", np.nan)
                    for r in ledger.itertuples()
                ]
                ledger["exit_volume"] = [
                    tape.quotes.get(r.exit_date, {}).get(r.entity_id, {}).get("volume", np.nan)
                    for r in ledger.itertuples()
                ]
                ledger["documented_event"] = [
                    "Nacon suspension 20 Feb, resumption 4 Mar 2026"
                    if r.ISIN == "FR0013482791"
                    and date(2026, 2, 16) <= r.entry_date <= date(2026, 3, 3)
                    else "MaaT negative CHMP trend released 20 May 2026"
                    if r.ISIN == "FR0012634822"
                    and r.entry_date <= date(2026, 5, 21)
                    and pd.notna(r.exit_date)
                    and r.exit_date >= date(2026, 5, 21)
                    else ""
                    for r in ledger.itertuples()
                ]
                cp = ledger.groupby("cutoff", as_index=False).agg(
                    pnl=("pnl_net", "sum"),
                    gross_pnl=("pnl_gross", "sum"),
                    trades=("entry_price", "count"),
                    selected_positions=("entity_id", "size"),
                    allocation=("allocation", "sum"),
                )
                cp["basket_net_return"] = cp.pnl / cp.allocation
                cp["contribution_points"] = cp.pnl * 100
                concentration_row = concentration(ledger)
                result = (
                    meta
                    | stats
                    | extra
                    | concentration_row
                    | {
                        "cutoff_count": len(chosen),
                        "selected_positions": len(ledger),
                        "average_positions_per_basket": len(ledger) / len(chosen),
                        "positive_cutoff_fraction": float((cp.pnl > 0).mean()),
                        "mean_cutoff_pnl": float(cp.pnl.mean()),
                        "median_cutoff_pnl": float(cp.pnl.median()),
                        "best_cutoff": str(cp.loc[cp.pnl.idxmax(), "cutoff"]),
                        "best_cutoff_pnl": float(cp.pnl.max()),
                        "worst_cutoff": str(cp.loc[cp.pnl.idxmin(), "cutoff"]),
                        "worst_cutoff_pnl": float(cp.pnl.min()),
                        "top3_cutoff_contribution": float(cp.pnl.nlargest(3).sum()),
                        "return_per_average_exposure": float(
                            stats["cumulative_return"] / extra["average_active_session_capital"]
                        )
                        if extra["average_active_session_capital"]
                        else None,
                        "return_per_eod_exposure": float(
                            stats["cumulative_return"] / stats["average_exposure"]
                        )
                        if stats["average_exposure"]
                        else None,
                        "volume_definition_not_certified": True,
                    }
                )
                all_metrics.append(result)
                cons.append(meta | concentration_row)
                daily.append(eq)
                ledgers.append(ledger)
                cutoff_rows.append(cp.assign(**meta))
        if task % 10 == 0:
            print(f"COMMON REPLAY {task}/{len(schedules)}", flush=True)
    metrics = pd.DataFrame(all_metrics).sort_values(
        ["target", "score_horizon", "exit_horizon", "cost_bp", "universe_policy", "top_fraction"]
    )
    trades = pd.concat(ledgers, ignore_index=True)
    sels = pd.concat(selections, ignore_index=True)
    for name, df in {
        "metrics": metrics,
        "portfolio_daily": pd.concat(daily, ignore_index=True),
        "trades": trades,
        "portfolio_cutoff": pd.concat(cutoff_rows, ignore_index=True),
        "selections": sels,
        "concentration": pd.DataFrame(cons),
        "horizon_matrix": metrics[metrics.target != "universe"],
        "overlap": overlap(scores, sels),
    }.items():
        df.to_parquet(output / f"{name}.parquet", index=False)
    event = trades[
        (trades.return_gross.abs() > 0.10)
        | (trades.pnl_net.abs() > 0.01)
        | (trades.future_quality != "approved")
        | (trades.status != "closed")
    ].copy()
    for threshold in [0.10, 0.20, 0.30]:
        event[f"abs_return_gt_{int(threshold * 100)}"] = event.return_gross.abs() > threshold
    event["abs_contribution_gt_1point"] = event.pnl_net.abs() > 0.01
    event.to_parquet(output / "event_concentration.parquet", index=False)
    event[event.price_audit_status == "pending_new_case"].to_parquet(
        output / "new_price_audit_cases.parquet", index=False
    )
    # Date-level execution IC: compute after selection has been frozen and persisted.
    for (mid, day), part in scores.groupby(["model_id", "cutoff"]):
        for hold in contract["exit_horizons"]:
            future = [d for d in tape.calendar if d > day][:hold]
            pair = []
            for r in part.itertuples():
                a = tape.quotes[future[0]].get(r.entity_id, {}).get("open", np.nan)
                z = tape.quotes[future[-1]].get(r.entity_id, {}).get("close", np.nan)
                if np.isfinite(a) and a > 0 and np.isfinite(z):
                    pair.append((r.score, z / a - 1))
            diagnostics.append(
                {
                    "model_id": mid,
                    "cutoff": day,
                    "exit_horizon": hold,
                    "pairs": len(pair),
                    "ic": correlation(
                        np.asarray([p[0] for p in pair]), np.asarray([p[1] for p in pair])
                    )
                    if len(pair) >= 30
                    else None,
                }
            )
    pd.DataFrame(diagnostics).to_parquet(output / "execution_ic.parquet", index=False)
    audit.update(
        {
            "input_files_unchanged": all(file_sha(Path(p)) == s for p, s in before.items()),
            "scores_original_export_unchanged": True,
            "quality_never_removes_selected_trades": True,
            "price_audit_reused_source_sha256": source_sha,
            "max_accounting_error": float(metrics.max_accounting_error.max()),
            "price_audit_reused_trade_rows": int(
                (event.price_audit_status != "pending_new_case").sum()
            ),
            "pending_event_rows": int((event.price_audit_status == "pending_new_case").sum()),
            "volumes_modified": False,
            "exact_common_universes": bool((counts.native_n == counts.common_n).all()),
            "simulation_count": len(metrics),
        }
    )
    assert audit["input_files_unchanged"] and metrics.cutoff_count.eq(22).all()
    write_json(output / "audit.json", audit)
    summary = {
        "development_only": True,
        "cutoffs": 22,
        "models": len(contract["models"]),
        "strategy_simulations": int((metrics.target != "universe").sum()),
        "benchmark_simulations": int((metrics.target == "universe").sum()),
        "native_n_min": int(counts.native_n.min()),
        "native_n_max": int(counts.native_n.max()),
        "common_n_min": int(counts.common_n.min()),
        "common_n_max": int(counts.common_n.max()),
        "all_native_common_identical": audit["exact_common_universes"],
        "source_code_sha256": file_sha(Path(__file__)),
        "config_sha256": file_sha(config),
    }
    write_json(output / "summary.json", summary)
    return summary
