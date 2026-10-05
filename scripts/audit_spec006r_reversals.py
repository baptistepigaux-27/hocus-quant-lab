"""Independent spot checks for the SPEC-006R return/direction sign reversals.

Run from the repository root with ``uv run python scripts/audit_spec006r_reversals.py``.
Outputs are written under ignored ``data/analysis/spec006r-reversal-audit/``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "data/analysis/spec006r-stability-atlas-top500"
OUTPUT = ROOT / "data/analysis/spec006r-reversal-audit"
MARKET_DB = ROOT / "data/research.duckdb"


def _select_relations(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    frozen = ATLAS / "frozen_top_signals.parquet"
    return connection.execute(
        """SELECT signal_id, feature_id, target_id, target_family, horizon,
                  discovery_rank, discovery_ic_mean, feature_family
           FROM read_parquet(?)
           WHERE scope='equity' AND selection_bucket='return_direction'
           QUALIFY row_number() OVER (
               PARTITION BY target_family
               ORDER BY discovery_rank
           ) <= 4
           ORDER BY target_family, discovery_rank""",
        [str(frozen)],
    ).df()


def _periods() -> dict[str, tuple[Path, Path, date, date]]:
    return {
        "2024_discovery": (
            ROOT / "data/feature_cube/spec006-weekly-demo",
            ROOT / "data/targets/spec006-weekly-demo",
            date(2024, 4, 5),
            date(2024, 10, 4),
        ),
        "2025_validation": (
            ROOT / "data/feature_cube/spec006-2025-matched",
            ROOT / "data/targets/spec006-2025-matched",
            date(2025, 4, 5),
            date(2025, 10, 4),
        ),
    }


def _spot_rows(
    frame: pd.DataFrame, period_id: str, day: str, signal_id: str
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    ranked = frame.assign(
        feature_rank=rankdata(frame["feature_value"], method="average"),
        target_rank=rankdata(frame["target_value"], method="average"),
    ).sort_values("feature_rank")
    rows: list[dict[str, Any]] = []
    for quantile in (0.1, 0.3, 0.5, 0.7, 0.9):
        index = min(len(ranked) - 1, round(quantile * (len(ranked) - 1)))
        row = ranked.iloc[index]
        rows.append(
            {
                "period_id": period_id,
                "as_of_date": day,
                "signal_id": signal_id,
                "feature_id": row["feature_id"],
                "target_id": row["target_id"],
                "entity_id": row["entity_id"],
                "feature_value": float(row["feature_value"]),
                "future_target": float(row["target_value"]),
                "feature_rank": float(row["feature_rank"]),
                "target_rank": float(row["target_rank"]),
                "cross_section_n": int(len(ranked)),
            }
        )
    return rows


def _raw_h120_checks(
    market: duckdb.DuckDBPyConnection,
    targets: pd.DataFrame,
    as_of: date,
) -> list[dict[str, Any]]:
    sample = targets.loc[
        (targets["target_family"] == "return_abs")
        & (targets["horizon"] == 120)
        & targets["research_ready"].fillna(False)
    ].head(10)
    checks: list[dict[str, Any]] = []
    available_cutoff = datetime.combine(
        as_of + timedelta(days=1), time.min, tzinfo=ZoneInfo("Europe/Paris")
    )
    for row in sample.itertuples(index=False):
        isin = str(row.entity_id).rsplit(":", maxsplit=1)[-1]
        bars = market.execute(
            """WITH revisions AS (
                   SELECT session_date, close,
                          row_number() OVER (
                              PARTITION BY instrument_id, session_date
                              ORDER BY retrieved_at DESC, snapshot_id DESC
                          ) AS revision_rank
                   FROM market_daily_history
                   WHERE isin=? AND session_date>?
               ), future AS (
                   SELECT session_date, close,
                          row_number() OVER (ORDER BY session_date) AS future_rank
                   FROM revisions WHERE revision_rank=1 AND close>0
               )
               SELECT session_date, close FROM future
               WHERE future_rank<=120 ORDER BY future_rank""",
            [isin, as_of],
        ).fetchall()
        past = market.execute(
            """WITH revisions AS (
                   SELECT session_date, close,
                          row_number() OVER (
                              PARTITION BY instrument_id, session_date
                              ORDER BY retrieved_at DESC, snapshot_id DESC
                          ) AS revision_rank
                   FROM market_daily_history
                   WHERE isin=? AND session_date<=?
                     AND available_at<=?
               )
               SELECT session_date, close FROM revisions
               WHERE revision_rank=1 AND close>0
               ORDER BY session_date DESC LIMIT 1""",
            [isin, as_of, available_cutoff],
        ).fetchone()
        if len(bars) != 120 or past is None:
            checks.append(
                {
                    "entity_id": row.entity_id,
                    "status": "insufficient_raw_bars",
                    "raw_future_rows": len(bars),
                }
            )
            continue
        raw_return = float(bars[-1][1] / past[1] - 1.0)
        stored_end_date = str(row.target_end_date)[:10]
        stored_start_date = str(row.start_date)[:10]
        checks.append(
            {
                "entity_id": row.entity_id,
                "status": "checked",
                "as_of_date": as_of.isoformat(),
                "stored_start_date": stored_start_date,
                "raw_start_date": str(past[0]),
                "stored_end_date": stored_end_date,
                "raw_120th_date": str(bars[-1][0]),
                "future_observation_count": int(row.future_observation_count),
                "stored_start_price": float(row.start_price),
                "raw_start_price": float(past[1]),
                "stored_end_price": float(row.end_price),
                "raw_120th_close": float(bars[-1][1]),
                "stored_return": float(row.target_value),
                "independent_raw_return": raw_return,
                "return_abs_error": abs(float(row.target_value) - raw_return),
                "start_is_last_close_at_or_before_T": str(past[0]) == stored_start_date,
                "first_and_120th_sessions_after_T": bars[0][0] > as_of and bars[-1][0] > as_of,
                "120th_session_matches_target_end": str(bars[-1][0]) == stored_end_date,
            }
        )
    return checks


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    analytical = duckdb.connect()
    market = duckdb.connect(str(MARKET_DB), read_only=True)
    relations = _select_relations(analytical)
    if len(relations) != 20:
        raise RuntimeError(f"expected 20 spot-check relations, selected {len(relations)}")
    feature_ids = sorted(relations["feature_id"].unique().tolist())
    target_ids = sorted(relations["target_id"].unique().tolist())
    pair_to_signal = {
        (row.feature_id, row.target_id): row.signal_id for row in relations.itertuples()
    }
    selected_pairs = set(pair_to_signal)
    stored = pd.read_parquet(ATLAS / "signal_period_ic_history.parquet")
    stored = stored.loc[
        stored["selection_bucket"].eq("return_direction")
        & stored["evaluation_scope"].eq("equity")
        & stored["signal_id"].isin(relations["signal_id"])
    ]
    stored = stored.set_index(["period_id", "signal_id", "as_of_date"])

    independent: list[dict[str, Any]] = []
    spot_samples: list[dict[str, Any]] = []
    formula_checks: list[dict[str, Any]] = []
    for period_id, (feature_root, target_root, start, end) in _periods().items():
        partitions = sorted(feature_root.glob("as_of_date=*/features.parquet"))
        selected_days: set[str] = set()
        in_window: list[tuple[date, Path]] = []
        for feature_path in partitions:
            day = date.fromisoformat(feature_path.parent.name.split("=", maxsplit=1)[1])
            if (
                start <= day <= end
                and (
                    target_root / f"as_of_date={day.isoformat()}" / "targets_research_ready.parquet"
                ).is_file()
            ):
                in_window.append((day, feature_path))
        if in_window:
            selected_days = {
                in_window[index][0].isoformat()
                for index in (0, len(in_window) // 2, len(in_window) - 1)
            }
        for day, feature_path in in_window:
            target_path = (
                target_root / f"as_of_date={day.isoformat()}" / "targets_research_ready.parquet"
            )
            feature_rows = analytical.execute(
                """SELECT entity_id, entity_family, as_of_date, feature_id,
                          feature_value, feature_status
                   FROM read_parquet(?)
                   WHERE feature_id IN (SELECT unnest(?)) AND entity_family='equity'""",
                [str(feature_path), feature_ids],
            ).df()
            target_rows = analytical.execute(
                """SELECT entity_id, entity_family, as_of_date, target_id, target_family, horizon,
                          target_value, target_status, research_ready, start_date, target_end_date,
                          start_price, end_price, future_observation_count
                   FROM read_parquet(?)
                   WHERE target_id IN (SELECT unnest(?)) AND entity_family='equity'""",
                [str(target_path), target_ids],
            ).df()
            joined = feature_rows.merge(
                target_rows,
                on=["entity_id", "entity_family", "as_of_date"],
                how="inner",
                suffixes=("_feature", "_target"),
            )
            joined = joined.loc[
                joined["feature_status"].eq("available")
                & joined["target_status"].eq("available")
                & joined["research_ready"].fillna(False)
                & np.isfinite(joined["feature_value"])
                & np.isfinite(joined["target_value"])
            ]
            for (feature_id, target_id), frame in joined.groupby(
                ["feature_id", "target_id"], sort=False
            ):
                if (feature_id, target_id) not in selected_pairs:
                    continue
                signal_id = pair_to_signal[(feature_id, target_id)]
                rho = float(
                    spearmanr(
                        frame["feature_value"].to_numpy(), frame["target_value"].to_numpy()
                    ).statistic
                )
                key = (period_id, signal_id, day.isoformat())
                pipeline_row = stored.loc[key] if key in stored.index else None
                pipeline_rho = (
                    float(pipeline_row["spearman_ic"]) if pipeline_row is not None else float("nan")
                )
                independent.append(
                    {
                        "period_id": period_id,
                        "as_of_date": day.isoformat(),
                        "signal_id": signal_id,
                        "feature_id": feature_id,
                        "target_id": target_id,
                        "target_family": str(frame["target_family"].iloc[0]),
                        "horizon": int(frame["horizon"].iloc[0]),
                        "n": int(len(frame)),
                        "scipy_spearman": rho,
                        "pipeline_spearman": pipeline_rho,
                        "absolute_delta": abs(rho - pipeline_rho)
                        if np.isfinite(pipeline_rho)
                        else None,
                    }
                )
                if day.isoformat() in selected_days:
                    spot_samples.extend(_spot_rows(frame, period_id, day.isoformat(), signal_id))

            if day.month == 4 and day.day in (5, 6):
                formula_checks.extend(_raw_h120_checks(market, target_rows, day))

    independent_frame = pd.DataFrame(independent)
    if independent_frame.empty:
        raise RuntimeError("the independent cross-sectional check produced no rows")
    independent_frame.to_csv(OUTPUT / "independent_20_relation_ics.csv", index=False)
    pd.DataFrame(spot_samples).to_parquet(OUTPUT / "spot_check_observations.parquet", index=False)
    formula_frame = pd.DataFrame(formula_checks)
    formula_frame.to_csv(OUTPUT / "h120_raw_formula_checks.csv", index=False)
    relations.to_csv(OUTPUT / "selected_20_relations.csv", index=False)

    print("SELECTED RELATIONS BY TARGET FAMILY")
    print(relations.groupby("target_family").size().to_string())
    print("\nINDEPENDENT SCIPY VS PIPELINE IC")
    print(
        independent_frame.groupby("period_id")
        .agg(
            cutoff_relation_rows=("scipy_spearman", "size"),
            distinct_relations=("signal_id", "nunique"),
            pipeline_values=("pipeline_spearman", "count"),
            max_absolute_error=("absolute_delta", "max"),
            mean_absolute_error=("absolute_delta", "mean"),
        )
        .to_string()
    )
    print("\nINDEPENDENT IC SIGN COUNTS BY FAMILY AND PERIOD")
    print(
        independent_frame.groupby(["period_id", "target_family"])
        .agg(
            cutoffs=("scipy_spearman", "size"),
            negative=("scipy_spearman", lambda values: int((values < 0).sum())),
            positive=("scipy_spearman", lambda values: int((values > 0).sum())),
            median_ic=("scipy_spearman", "median"),
            mean_ic=("scipy_spearman", "mean"),
        )
        .to_string()
    )
    if not formula_frame.empty:
        checked = formula_frame.loc[formula_frame["status"].eq("checked")]
        valid_columns = [
            "start_is_last_close_at_or_before_T",
            "first_and_120th_sessions_after_T",
            "120th_session_matches_target_end",
        ]
        all_dates_match = bool(checked[valid_columns].all().all()) if not checked.empty else False
        print("\nRAW H120 TARGET-FORMULA CHECKS")
        print(
            f"rows={len(formula_frame)}, checked={len(checked)}, "
            f"max |stored - independently calculated return|="
            f"{checked['return_abs_error'].max() if not checked.empty else 'n/a'}, "
            f"all dates/counts correct={all_dates_match}"
        )
    print(f"\nDetailed local rows and CSVs: {OUTPUT}")


if __name__ == "__main__":
    main()
