from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import polars as pl
import pytest
from scipy.stats import spearmanr

from hocus_quant.analysis.candidate_lock import (
    TARGET,
    build_lock_document,
    prepare_confirmation,
    rank_signature_groups,
    verify_lock,
    write_lock_once,
)
from hocus_quant.analysis.ex_ante import draw_means, measure_h5
from hocus_quant.analysis.research_ui import load_research_contract_artifacts
from hocus_quant.targets.research_contract import (
    annotate_outcomes,
    freeze_eligibility,
    refresh_contract_views,
    select_targets,
)

DAY = date(2024, 4, 5)


def _ledger(n: int = 3) -> pl.DataFrame:
    return pl.DataFrame(
        [
            asdict(
                freeze_eligibility(
                    entity_id=f"e{i}",
                    entity_family="equity",
                    as_of_date=DAY,
                    quality_status="approved",
                    past_dates=[DAY - timedelta(days=1), DAY],
                )
            )
            for i in range(n)
        ]
    )


def _outcomes(n: int = 3) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "entity_id": [f"e{i}" for i in range(n)],
            "entity_family": ["equity"] * n,
            "as_of_date": [DAY] * n,
            "target_id": [TARGET] * n,
            "candidate_value": [1.0] * n,
            "target_value": [1.0] * n,
            "target_status": ["available"] * n,
            "research_ready": [True] * n,
            "future_quality_reason": [None] * n,
            "unavailable_reason": [None] * n,
            "extreme_flags": [None] * n,
        },
        schema_overrides={
            "future_quality_reason": pl.String,
            "unavailable_reason": pl.String,
            "extreme_flags": pl.List(pl.String),
        },
    )


@pytest.mark.parametrize(
    "status,quality,interpretable",
    [
        ("available", "clean", True),
        ("future_quality_review", "review", True),
        ("future_quality_quarantined", "quarantined", False),
        ("right_censored_end_of_sample", "right_censored_end_of_sample", False),
    ],
)
def test_future_never_changes_frozen_eligibility(status, quality, interpretable) -> None:
    ledger = _ledger()
    future = _outcomes().with_columns(pl.lit(status).alias("target_status"))
    if status == "right_censored_end_of_sample":
        future = future.with_columns(pl.lit(None, dtype=pl.Float64).alias("candidate_value"))
    result = annotate_outcomes(future, ledger)
    assert result["eligible_at_cutoff"].to_list() == [True] * 3
    assert result["future_quality_status"].to_list() == [quality] * 3
    assert result["target_interpretable"].to_list() == [interpretable] * 3
    assert ledger.equals(_ledger())


def test_review_target_is_kept_and_strong_error_is_separate() -> None:
    source = _outcomes().with_columns(
        pl.Series(
            "target_status", ["available", "future_quality_review", "future_quality_quarantined"]
        ),
        pl.Series("research_ready", [True, False, False]),
    )
    targets = annotate_outcomes(source, _ledger())
    assert select_targets(targets, "ex_ante").height == 2
    assert select_targets(targets, "clean_future").height == 1
    assert select_targets(targets, "legacy_research_ready").height == 1
    assert targets.row(2, named=True)["target_value"] is None
    assert targets.row(2, named=True)["candidate_value"] == 1.0
    with duckdb.connect() as db:
        db.register("targets", targets)
        refresh_contract_views(db)
        assert db.execute("SELECT count(*) FROM targets_ex_ante").fetchone() == (3,)
        assert db.execute("SELECT count(*) FROM targets_clean_future").fetchone() == (1,)
        assert db.execute(
            "SELECT bool_and(eligible_at_cutoff) FROM targets_ex_ante"
        ).fetchone() == (True,)


@pytest.mark.parametrize(
    "flag,status",
    [
        ("likely_split_or_reverse_split", "suspected_corporate_action"),
        ("likely_scale_change", "scale_change"),
        ("source_quality_issue", "source_issue"),
        ("confirmed_source_error", "quarantined"),
    ],
)
def test_future_flags_are_explicit_without_retroactive_exclusion(flag, status) -> None:
    targets = annotate_outcomes(
        _outcomes().with_columns(pl.Series("extreme_flags", [[flag]] * 3)), _ledger()
    )
    assert targets["future_quality_status"].to_list() == [status] * 3
    assert targets["eligible_at_cutoff"].all()
    assert targets["target_observable"].all()


def test_eligibility_refuses_future_information_and_unknown_outcome_entity() -> None:
    with pytest.raises(ValueError, match="<= T"):
        freeze_eligibility(
            entity_id="e",
            entity_family="equity",
            as_of_date=DAY,
            quality_status="approved",
            past_dates=[DAY + timedelta(days=1)],
        )
    with pytest.raises(ValueError, match="no past-only"):
        annotate_outcomes(_outcomes(4), _ledger(3))


def _features() -> pl.DataFrame:
    rows = []
    for day in [DAY, DAY + timedelta(days=7)]:
        for i in range(40):
            for name, value in [
                ("x.std", float(i)),
                ("x.variance", float(i * i)),
                ("x.reverse", float(40 - i)),
            ]:
                rows.append(
                    {
                        "as_of_date": day,
                        "entity_id": f"e{i:02d}",
                        "feature_id": name,
                        "feature_value": value,
                    }
                )
    return pl.DataFrame(rows)


def test_rank_groups_deterministic_and_monotone_aliases() -> None:
    first = rank_signature_groups(_features())
    assert first.equals(rank_signature_groups(_features().reverse()))
    assert first.height == 2
    group = first.filter(pl.col("canonical_feature") == "x.std").row(0, named=True)
    assert group["aliases"] == ["x.variance"]
    assert group["group_size"] == 2


def test_signature_includes_missingness_and_entity_identity() -> None:
    frame = _features().filter(
        ~((pl.col("feature_id") == "x.variance") & (pl.col("entity_id") == "e02"))
    )
    assert rank_signature_groups(frame).height == 3


def test_corrected_h5_and_legacy_match_independent_scipy() -> None:
    features = _features().filter(pl.col("as_of_date") == DAY)
    source = _outcomes(40).with_columns(
        pl.Series("entity_id", [f"e{i:02d}" for i in range(40)]),
        pl.Series("candidate_value", [float(np.sign(i - 20)) for i in range(40)]),
        pl.Series("target_value", [float(np.sign(i - 20)) for i in range(40)]),
        pl.Series("research_ready", [i > 1 for i in range(40)]),
        pl.Series("target_status", ["future_quality_review"] * 2 + ["available"] * 38),
    )
    ledger = _ledger(40).with_columns(pl.Series("entity_id", [f"e{i:02d}" for i in range(40)]))
    targets = annotate_outcomes(source, ledger)
    for policy, first in [("legacy_research_ready", 2), ("ex_ante", 0), ("clean_future", 2)]:
        observed = measure_h5(features, select_targets(targets, policy))
        x = np.arange(first, 40, dtype=float)
        expected = spearmanr(x, np.sign(x - 20)).statistic
        assert observed.filter(pl.col("feature_id") == "x.std")["spearman_ic"][0] == pytest.approx(
            expected
        )
    empty = measure_h5(features, select_targets(targets.head(0), "ex_ante"))
    assert empty.height == 0 and empty.schema["feature_id"] == pl.String


def _lock() -> dict:
    return build_lock_document(
        [
            {
                "canonical_feature": "x.std",
                "rank_signature": "abc",
                "target_id": TARGET,
                "discovery_rank": 1,
                "ic_mean_2025": 0.04,
                "ic_mean_2026": 0.03,
            }
        ],
        contract={
            "target_id": TARGET,
            "horizon": 5,
            "feature_registry_sha256": "registry",
            "data_observed_through": "2026-09-28",
        },
    )


def test_lock_deterministic_immutable_and_development_cannot_retune(tmp_path: Path) -> None:
    first = _lock()
    assert first == _lock()
    path = tmp_path / "lock.json"
    write_lock_once(path, first)
    write_lock_once(path, _lock())
    changed = first["candidates"][0].copy()
    changed["ic_mean_2026"] = -0.9
    second = build_lock_document([changed], contract=first["contract"])
    with pytest.raises(ValueError, match="already exists"):
        write_lock_once(path, second)
    assert json.loads(path.read_text()) == first
    corrupt = {**first, "lock_sha256": "wrong"}
    with pytest.raises(ValueError, match="checksum"):
        verify_lock(corrupt)


def test_no_h120_and_confirmation_has_fixed_registry_no_results() -> None:
    with pytest.raises(ValueError, match="only absolute direction H5"):
        build_lock_document(
            [], contract={"target_id": "future.direction_abs.h120.v1", "horizon": 120}
        )
    with pytest.raises(ValueError, match="beyond consulted"):
        prepare_confirmation(
            _lock(),
            first_cutoff="2026-09-28",
            feature_registry_sha256="registry",
            last_development_outcome_date="2026-09-28",
        )
    with pytest.raises(ValueError, match="registry differs"):
        prepare_confirmation(
            _lock(),
            first_cutoff="2027-01-01",
            feature_registry_sha256="changed",
            last_development_outcome_date="2026-09-28",
        )
    request = prepare_confirmation(
        _lock(),
        first_cutoff="2027-01-01",
        feature_registry_sha256="registry",
        last_development_outcome_date="2026-09-28",
    )
    assert request["results"] is None and request["retuning_allowed"] is False
    assert _lock()["lock_sha256"] == request["lock_sha256"]


def test_bootstrap_repeatable_and_constant_panels() -> None:
    values = np.full((27, 2), 0.05)
    first = draw_means(values, block=4, replicates=1000, seed=42)
    assert np.array_equal(first, draw_means(values, block=4, replicates=1000, seed=42))
    assert np.allclose(first, 0.05)


def test_sandbox_reads_precomputed_cohorts_without_analysis(tmp_path: Path, monkeypatch) -> None:
    import hocus_quant.analysis.ex_ante as analysis

    def forbidden(*args, **kwargs):
        raise AssertionError("UI must not recalculate scientific outputs")

    monkeypatch.setattr(analysis, "run_research_contract", forbidden)
    monkeypatch.setattr(analysis, "measure_h5", forbidden)
    lock = _lock()
    (tmp_path / "candidate_lock_v1.json").write_text(json.dumps(lock))
    (tmp_path / "audit.json").write_text(json.dumps({"lock_sha256": lock["lock_sha256"]}))
    for name in [
        "candidate_explorer",
        "ex_ante_filter_sensitivity",
        "ic_summary",
        "ic_history",
        "market_regimes",
    ]:
        pl.DataFrame(
            {"policy": ["ex_ante", "clean_future"], "ic_mean": [0.04, 0.03]}
        ).write_parquet(tmp_path / f"{name}.parquet")
    artifacts = load_research_contract_artifacts(tmp_path)
    assert artifacts.summaries["policy"].to_list() == ["ex_ante", "clean_future"]
    assert artifacts.lock == lock
