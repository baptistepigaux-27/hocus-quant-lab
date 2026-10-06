"""Audit existing short-horizon winner ledgers; never refit or change eligibility.

External price tables are cached public Euronext UI responses. This command
reconciles evidence already acquired; it does not fetch or repair market data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from hocus_quant.validation.market_quality import assess_series


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def numeric(value: str) -> float | None:
    try:
        return float(value.replace(",", "").replace("\xa0", "").strip())
    except ValueError:
        return None


def audit(source: Path, raw_root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    market = pl.read_parquet(source / "source_market.parquet")
    winners = pl.read_parquet(source / "comparison_winners.parquet").filter(pl.col("cost_bp") == 0)
    trades = (
        pl.read_parquet(source / "backtest_trades.parquet")
        .join(winners.select("model_id"), on="model_id", how="semi")
        .filter(pl.col("cost_bp") == 0)
    )
    if market.select(pl.struct("entity_id", "session_date").n_unique()).item() != len(market):
        raise ValueError("Duplicate source quotes")
    quotes = {(r["entity_id"], r["session_date"]): r for r in market.to_dicts()}

    # Full delivered source, not just the favorable observations selected later.
    raw_checks, raw_mismatches, raw_lines = [], [], {}
    for checksum, rows in market.partition_by("snapshot_checksum", as_dict=True).items():
        checksum = checksum[0]
        payload = raw_root / checksum.removeprefix("sha256:") / "payload"
        actual_sha = sha256(payload)
        if actual_sha != checksum.removeprefix("sha256:"):
            raise ValueError(f"Raw payload checksum mismatch: {payload}")
        lookup = {}
        with payload.open(encoding="utf-8-sig", newline="") as stream:
            for line_no, cells in enumerate(csv.reader(stream, delimiter=";"), start=1):
                if len(cells) != 7:
                    raise ValueError(f"Unexpected raw row {payload}:{line_no}")
                isin, day, *values = cells
                d = datetime.strptime(day, "%d/%m/%y").date()
                key = isin, d
                values = tuple(float(x) for x in values)
                if key in lookup and lookup[key][1] != values:
                    raise ValueError(f"Conflicting raw rows: {key}")
                lookup[key] = line_no, values
        for row in rows.to_dicts():
            original = lookup.get((row["isin"], row["session_date"]))
            if original is not None:
                raw_lines[row["entity_id"], row["session_date"]] = {
                    "raw_path": str(payload),
                    "raw_line_number": original[0],
                }
            actual = tuple(row[k] for k in ("open", "high", "low", "close", "volume"))
            if original is None or original[1] != actual:
                raw_mismatches.append({"isin": row["isin"], "date": row["session_date"]})
        raw_checks.append({"path": str(payload), "sha256": actual_sha, "matched_rows": len(rows)})

    checked, max_price_error, max_return_error, max_pnl_error = [], 0.0, 0.0, 0.0
    for trade in trades.to_dicts():
        entered = trade["entry_price"] is not None
        if not entered:
            checked.append({**trade, "source_reconciled": None})
            continue
        entry = quotes[trade["entity_id"], trade["entry_date"]]
        exit_row = quotes[trade["entity_id"], trade["exit_date"]]
        price_error = max(
            abs(entry["open"] - trade["entry_price"]),
            abs(exit_row["close"] - trade["exit_price"]),
        )
        return_error = abs(exit_row["close"] / entry["open"] - 1 - trade["return_gross"])
        pnl_error = abs(trade["shares"] * (exit_row["close"] - entry["open"]) - trade["pnl_gross"])
        max_price_error = max(max_price_error, price_error)
        max_return_error = max(max_return_error, return_error)
        max_pnl_error = max(max_pnl_error, pnl_error)
        checked.append({**trade, "source_reconciled": price_error <= 1e-12 and pnl_error <= 1e-12})
    pl.DataFrame(checked).write_parquet(output / "winner_ledger_audit.parquet")

    # Materiality identifies cases for investigation, never admissibility or a new top.
    material = trades.filter(
        (pl.col("pnl_gross").abs() >= 0.01)
        | (pl.col("future_quality") != "approved")
        | (pl.col("status") != "closed")
    )
    keys = ["entity_id", "cutoff", "entry_date", "exit_date", "holding_horizon"]
    cases, case_quotes = [], []
    for index, part in enumerate(material.sort(keys).partition_by(keys), start=1):
        t = part.row(0, named=True)
        case_id = f"case-{index:04d}"
        path = (
            market.filter(
                (pl.col("entity_id") == t["entity_id"])
                & pl.col("session_date").is_between(t["entry_date"], t["exit_date"])
            )
            if t["exit_date"]
            else market.head(0)
        )
        qa = (
            assess_series(
                {
                    "entity_id": t["entity_id"],
                    "entity_family": "equity",
                    "observations": path.to_dicts(),
                }
            )
            if len(path)
            else None
        )
        for row in path.to_dicts():
            case_quotes.append(
                {"case_id": case_id, **row, **raw_lines[row["entity_id"], row["session_date"]]}
            )
        cases.append(
            {
                **{key: t[key] for key in keys},
                "case_id": case_id,
                "isin": t["entity_id"].rsplit(":", 1)[1],
                "scheduled_exit": t["scheduled_exit"],
                "entry_price": t["entry_price"],
                "exit_price": t["exit_price"],
                "return_gross": t["return_gross"],
                "status": t["status"],
                "future_quality": t["future_quality"],
                "occurrences": len(part),
                "max_abs_contribution": part.get_column("pnl_gross").abs().max(),
                "quality_evidence": json.dumps(qa, default=str),
                "primary_price_status": "not_crosschecked",
            }
        )

    receipts = []
    for receipt_file in sorted(output.glob("primary*/euronext_histories.json")):
        receipts.extend(json.loads(receipt_file.read_text()))
    primary, comparisons = {}, []
    for receipt in receipts:
        if sha256(Path(receipt["html_path"])) != receipt["sha256"]:
            raise ValueError("External cached table changed")
        expected = ["Date", "Open", "High", "Low", "Last", "Close", "Number of shares"]
        if receipt["table"]["headers"][:7] != expected:
            raise ValueError("Primary table schema changed; review before comparing")
        for cells in receipt["table"]["rows"]:
            if len(cells) < 7:
                continue
            try:
                day = datetime.strptime(cells[0], "%d/%m/%Y").date()
            except ValueError:
                continue
            values = dict(
                zip(
                    ("open", "high", "low", "last", "close", "volume"),
                    map(numeric, cells[1:7]),
                    strict=True,
                )
            )
            primary_key = receipt["isin"], day
            if primary_key in primary and primary[primary_key] != values:
                raise ValueError(f"Conflicting primary vintages for {primary_key}")
            primary[primary_key] = values
            local = quotes.get((f"abc-bourse-manual:equity:{receipt['isin']}", day))
            for field in ("open", "high", "low", "close", "volume"):
                external = values[field]
                comparisons.append(
                    {
                        "episode": receipt["episode"],
                        "isin": receipt["isin"],
                        "session_date": day,
                        "field": field,
                        "local_value": local[field] if local else None,
                        "primary_value": external,
                        "absolute_error": abs(local[field] - external)
                        if local and external is not None
                        else None,
                        "url": receipt["url"],
                    }
                )
    for case in cases:
        a = primary.get((case["isin"], case["entry_date"]), {})
        z = primary.get((case["isin"], case["exit_date"]), {})
        if case["entry_price"] is None:
            if a and (a.get("open") is None or a.get("volume") == 0):
                case["primary_price_status"] = "entry_not_traded_in_primary_table"
            continue
        if a.get("open") is not None and z.get("close") is not None:
            same = (
                abs(a["open"] - case["entry_price"]) <= 1e-12
                and abs(z["close"] - case["exit_price"]) <= 1e-12
            )
            case["primary_price_status"] = "entry_exit_matched" if same else "entry_exit_difference"
    pl.DataFrame(cases).sort("max_abs_contribution", descending=True).write_csv(
        output / "material_cases.csv"
    )
    pl.DataFrame(case_quotes).write_parquet(output / "material_quote_paths.parquet")
    comparisons_frame = pl.DataFrame(comparisons).unique(
        subset=["isin", "session_date", "field"], maintain_order=True
    )
    comparisons_frame.write_csv(output / "primary_price_comparison.csv")
    field_summary = (
        comparisons_frame.group_by("field")
        .agg(
            pl.col("absolute_error").is_not_null().sum().alias("comparable"),
            (pl.col("absolute_error") > 1e-12).sum().alias("differences"),
            pl.col("absolute_error").max().alias("max_absolute_error"),
        )
        .sort("field")
    )
    field_summary.write_csv(output / "primary_field_summary.csv")
    comparisons_frame.filter(pl.col("absolute_error") > 1e-12).write_csv(
        output / "primary_differences.csv"
    )

    attribution = []
    summaries = pl.read_parquet(source / "backtest_summary.parquet")
    for part in trades.partition_by("simulation_id"):
        t = part.row(0, named=True)
        ordered = part.sort("pnl_gross", descending=True)
        total = part.get_column("pnl_gross").sum()
        top1 = ordered.get_column("pnl_gross")[0]
        top5 = ordered.head(5).get_column("pnl_gross").sum()
        attribution.append(
            {
                "simulation_id": t["simulation_id"],
                "model_id": t["model_id"],
                "target": t["target"],
                "horizon": t["horizon"],
                "holding_horizon": t["holding_horizon"],
                "gross_return": total,
                "top1_contribution": top1,
                "top5_contribution": top5,
                "top5_share_of_net_gross_pnl": top5 / total if total else None,
                "other_trades_contribution": total - top5,
                "review_contribution": part.filter(pl.col("future_quality") == "review")
                .get_column("pnl_gross")
                .sum(),
                "missing_entries": part.filter(pl.col("entry_price").is_null()).height,
                "delayed_exits": part.filter(pl.col("status") == "delayed_missing_exit").height,
                "warning": (
                    "Accounting attribution at original sizes; never a rerun excluding top trades"
                ),
            }
        )
        s = summaries.filter(pl.col("simulation_id") == t["simulation_id"])
        if len(s) != 1 or abs(s.get_column("cumulative_return").item() - total) > 1e-10:
            raise ValueError("Gross NAV/ledger mismatch")
    pl.DataFrame(attribution).write_csv(output / "winner_attribution.csv")

    # Discovery-time common date inventory: no ranking or model re-selection.
    grids = []
    for label, file in [
        ("short", source / "predictions.parquet"),
        ("baseline", Path("data/analysis/spec008-model-lab-all-features/predictions.parquet")),
    ]:
        predictions = pl.read_parquet(file).filter(pl.col("split") == "test")
        for horizon, part in predictions.partition_by("horizon", as_dict=True).items():
            days = sorted(part.get_column("cutoff").unique().to_list())
            grids.append(
                {"experiment": label, "horizon": horizon[0], "cutoffs": [str(x) for x in days]}
            )
    common = sorted(set.intersection(*(set(g["cutoffs"]) for g in grids)))
    save_json(
        output / "common_cutoffs.json",
        {"grids": grids, "common_cutoffs": common, "status": "inventory_only_not_a_new_evaluation"},
    )
    result = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_commit": "76629a6",
        "scope": (
            "16 validation winner models, 32 gross long-only native/H5 portfolios; no new fits"
        ),
        "source_rows": len(market),
        "raw_payloads": len(raw_checks),
        "raw_mismatches": raw_mismatches,
        "winner_trade_rows": len(trades),
        "entered_trade_rows": sum(x["entry_price"] is not None for x in checked),
        "max_endpoint_price_error": max_price_error,
        "max_return_error": max_return_error,
        "max_pnl_error": max_pnl_error,
        "material_cases": len(cases),
        "primary_episodes": len(receipts),
        "primary_numeric_fields": comparisons_frame.get_column("absolute_error")
        .is_not_null()
        .sum(),
        "primary_field_summary": field_summary.to_dicts(),
        "case_primary_status": pl.DataFrame(cases)
        .group_by("primary_price_status")
        .len()
        .to_dicts(),
        "common_h1_to_h10_cutoffs": len(common),
        "raw_checks": raw_checks,
        "input_sha256": {
            str(source / name): sha256(source / name)
            for name in [
                "source_market.parquet",
                "comparison_winners.parquet",
                "backtest_trades.parquet",
                "backtest_summary.parquet",
                "predictions.parquet",
            ]
        },
    }
    save_json(output / "audit.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/analysis/srd-short-horizons-v1"))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/market"))
    parser.add_argument("--output", type=Path, default=Path("data/analysis/srd-price-audit-v1"))
    args = parser.parse_args()
    report = audit(args.source, args.raw_root, args.output)
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"raw_checks", "input_sha256"}
            },
            indent=2,
        )
    )
