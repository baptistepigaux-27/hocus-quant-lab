"""Independent source/calendar reconciliation for the index research experiment."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from hocus_quant.analysis.confirmation_protocol import file_sha


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-models", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "data/analysis/spec008-index-model-lab"
    manifest = json.loads((output / "dataset_manifest.json").read_text())
    for name, sha in manifest["source_sha256"].items():
        assert file_sha(output / name) == sha, name
    bars = pd.read_parquet(output / "source_market.parquet")
    expected_availability = (
        pd.to_datetime(bars.session_date) + pd.Timedelta(days=1)
    ).dt.tz_localize("UTC")
    assert (pd.to_datetime(bars.available_at) == expected_availability).all()
    series = {
        entity: (part.session_date.tolist(), part.close.tolist())
        for entity, part in bars.sort_values("session_date").groupby("entity_id")
    }
    calendar = sorted(bars[bars.provider_instrument_id == "FR0003500008"].session_date.unique())
    targets = pd.read_parquet(output / "targets.parquet")
    errors = []
    for row in targets[targets.return_abs.notna()].itertuples():
        dates, closes = series[row.entity_id]
        initial = bisect_right(dates, row.cutoff) - 1
        assert dates[initial] == row.reference_quote_date
        position = calendar.index(row.cutoff)
        future_days = calendar[position + 1 : position + row.horizon + 1]
        assert future_days[-1] == row.target_end
        future_positions = [bisect_right(dates, day) - 1 for day in future_days]
        assert all(
            day - dates[i] <= timedelta(days=3)
            for day, i in zip(future_days, future_positions, strict=True)
        )
        assert dates[future_positions[-1]] == row.index_quote_end
        expected = closes[future_positions[-1]] / closes[initial] - 1
        errors.append(abs(expected - row.return_abs))
    assert errors and max(errors) < 1e-12
    for split, end in [
        ("train", "2024-12-31"),
        ("validation", "2025-06-30"),
        ("test", "2026-06-30"),
    ]:
        observed = targets[(targets.split == split) & targets.return_abs.notna()]
        assert (pd.to_datetime(observed.target_end) <= pd.Timestamp(end)).all()
    assert targets[~targets.calendar_complete].return_abs.isna().all()
    for _, part in targets.groupby(["cutoff", "group", "horizon"]):
        observed = part[part.rank_pct.notna()]
        assert np.allclose(observed.rank_pct, observed.return_abs.rank(method="average", pct=True))
    receipt = {
        "status": "independent_source_calendar_reconciliation_complete",
        "return_rows_recomputed": len(errors),
        "max_return_difference": max(errors),
        "availability_timezone": "UTC",
        "common_calendar": "CAC40",
        "dataset_manifest_sha256": file_sha(output / "dataset_manifest.json"),
        "generator_sha256": file_sha(Path(__file__)),
    }
    if args.include_models:
        run = json.loads((output / "summary.json").read_text())
        assert (run["model_count"], run["tuning_fits"], run["tasks"], run["backtest_count"]) == (
            112,
            160,
            24,
            0,
        )
        for name, sha in run["artifact_sha256"].items():
            assert file_sha(output / name) == sha, name
        for name, sha in run["source_sha256"].items():
            assert file_sha(root / name) == sha, name
        registry = pd.DataFrame(json.loads((output / "model_registry.json").read_text()))
        for model in registry.itertuples():
            assert file_sha(output / "models" / f"{model.model_id}.joblib") == model.model_sha256
        winners = registry[registry.validation_winner_within_feature_set].model_id
        assert len(winners) == 24
        predictions = pd.read_parquet(output / "predictions.parquet")
        cutoffs = pd.read_parquet(output / "cutoff_metrics.parquet")
        ic_errors = []
        for (mid, day), part in predictions[
            (predictions.split == "test") & predictions.model_id.isin(winners)
        ].groupby(["model_id", "cutoff"]):
            good = part[part.score.notna() & part.target_value.notna()]
            if len(good) >= 10 and good.score.nunique() > 1 and good.target_value.nunique() > 1:
                expected_ic = np.corrcoef(good.score.rank(), good.target_value.rank())[0, 1]
                actual = cutoffs[
                    (cutoffs.model_id == mid) & (cutoffs.split == "test") & (cutoffs.cutoff == day)
                ].ic.iloc[0]
                ic_errors.append(abs(expected_ic - actual))
        assert ic_errors and max(ic_errors) < 1e-12
        export = pd.read_parquet(output / "historical_index_score_features.parquet")
        assert not any(
            c in export for c in ["target_value", "return_abs", "target_end", "future_quality"]
        )
        assert (pd.to_datetime(export.cutoff) > pd.Timestamp("2025-06-30")).all()
        assert export.historical_calendar_harmonized.all()
        assert (~export.ready_for_srd_integration).all()
        source_scores = predictions[
            (predictions.split == "test") & predictions.model_id.isin(winners)
        ][["model_id", "entity_id", "cutoff", "score"]]
        aligned = export.merge(
            source_scores,
            on=["model_id", "entity_id", "cutoff"],
            suffixes=("_export", "_prediction"),
            validate="one_to_one",
        )
        assert len(aligned) == len(source_scores) == len(export)
        assert np.allclose(aligned.score_export, aligned.score_prediction)
        score_availability = (pd.to_datetime(export.cutoff) + pd.Timedelta(days=1)).dt.tz_localize(
            "UTC"
        )
        assert (pd.to_datetime(export.available_at_modeled, utc=True) == score_availability).all()
        receipt.update(
            models=112,
            validation_fits=160,
            winners=24,
            independent_ic_checks=len(ic_errors),
            max_ic_difference=max(ic_errors),
            score_export_rows=len(export),
        )
    (output / "runtime_parity_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if args.include_models:
        ready = json.loads((output / "index_report_ready.json").read_text())
        for name, sha in ready["artifacts"].items():
            assert file_sha(output / name) == sha, name
        assert (
            file_sha(output / "historical_index_score_features.parquet")
            == ready["score_export_sha256"]
        )
        assert file_sha(root / "docs/SPEC_008_INDICES_RESULTS.md") == ready["report_sha256"]
        ready["independent_parity_sha256"] = file_sha(output / "runtime_parity_receipt.json")
        temporary = output / "index_report_complete.json.tmp"
        temporary.write_text(json.dumps(ready, indent=2) + "\n")
        temporary.replace(output / "index_report_complete.json")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
