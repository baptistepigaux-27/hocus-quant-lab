"""SPEC-007 tests use only synthetic isolated data, never a real confirmation period."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import polars as pl
import pytest

from hocus_quant.analysis.candidate_lock import fingerprint
from hocus_quant.analysis.confirmation import (
    load_monitor,
    mature_pending,
    rebuild_monitor,
    register_cutoff,
    verify_store,
)
from hocus_quant.analysis.confirmation_metrics import (
    cumulative_tables,
    cutoff_metrics,
    oriented_scores,
    prediction_metrics,
)
from hocus_quant.analysis.confirmation_protocol import (
    SCIENTIFIC_FILES,
    checkpoint_state,
    file_sha,
    initialize_protocol,
    verdict,
    verify_protocol,
)

REPO = Path(__file__).resolve().parents[1]
T = date(2026, 10, 9)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    root.mkdir()
    for name in SCIENTIFIC_FILES:
        destination = root / "src/hocus_quant" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "src/hocus_quant" / name, destination)
    shutil.copyfile(REPO / "uv.lock", root / "uv.lock")
    config = root / "configs/research/confirmation_protocol_v1.toml"
    config.parent.mkdir(parents=True)
    shutil.copyfile(REPO / config.relative_to(root), config)
    shutil.copyfile(
        REPO / "configs/research/candidate_lock_v1.json", config.parent / "candidate_lock_v1.json"
    )
    target = root / "data/targets/spec006-weekly-demo/as_of_date=2026-09-28"
    target.mkdir(parents=True)
    pl.DataFrame(
        {
            "as_of_date": [date(2026, 9, 28)],
            "target_end_date": [date(2026, 9, 28)],
            "last_future_observation_date": [date(2026, 9, 28)],
        }
    ).write_parquet(target / "targets.parquet")
    audit = root / "data/features/2026-04-01/audit.json"
    audit.parent.mkdir(parents=True)
    audit.write_text(json.dumps({"high_correlation_pairs": []}))
    monkeypatch.setattr(
        "hocus_quant.analysis.confirmation.code_sha", lambda _: "synthetic-test-sha"
    )
    monkeypatch.setattr("hocus_quant.analysis.confirmation.code_dirty", lambda _: False)
    output = root / "data/confirmation"
    protocol = initialize_protocol(root, config, output)
    lock = verify_protocol(root, config, protocol)
    return root, config, output, protocol, lock


def test_protocol_deterministic_boundary_and_no_development(env):
    root, config, output, protocol, _ = env
    assert initialize_protocol(root, config, output) == protocol
    assert protocol["boundary"]["development_observed_through"] == "2026-09-28"
    assert protocol["boundary"]["confirmation_start_date"] == "2026-10-06"
    for old in [date(2024, 4, 5), date(2025, 5, 2), date(2026, 9, 28), date(2026, 10, 5)]:
        with pytest.raises(ValueError, match="forbidden"):
            register_cutoff(
                root=root, config=config, output=output, database=root / "absent.duckdb", cutoff=old
            )
    manifest = rebuild_monitor(root=root, config=config, output=output)
    assert manifest["status"] == "awaiting_new_data"
    assert manifest["mature_cutoffs"] == 0
    assert load_monitor(output)["history"].height == 0


@pytest.mark.parametrize(
    "kind", ["lock", "sign", "feature", "target", "eligibility", "statistics", "settings"]
)
def test_changes_invalidate_protocol(env, kind):
    root, config, _, protocol, lock = env
    if kind in {"lock", "sign"}:
        if kind == "sign":
            lock["candidates"][0]["locked_direction"] *= -1
        else:
            lock["candidates"].pop()
        lock["lock_sha256"] = fingerprint({k: v for k, v in lock.items() if k != "lock_sha256"})
        (config.parent / "candidate_lock_v1.json").write_text(json.dumps(lock))
    elif kind == "settings":
        config.write_text(config.read_text().replace("minimum_pairs = 30", "minimum_pairs = 31"))
    else:
        names = {
            "feature": "features/factory.py",
            "target": "targets/registry.py",
            "eligibility": "targets/research_contract.py",
            "statistics": "analysis/confirmation_metrics.py",
        }
        p = root / "src/hocus_quant" / names[kind]
        p.write_text(p.read_text() + "\n# changed scientific definition\n")
    with pytest.raises(ValueError):
        verify_protocol(root, config, protocol)


@pytest.mark.parametrize(
    "n,state",
    [
        (0, "awaiting_new_data"),
        (1, "collecting"),
        (4, "collecting"),
        (8, "checkpoint_8"),
        (13, "checkpoint_13"),
        (26, "checkpoint_26"),
    ],
)
def test_checkpoint_states(n, state):
    assert checkpoint_state(n) == state
    assert checkpoint_state(26, complete=True) == "confirmation_complete"


def test_verdict_thresholds_and_no_early_claims():
    assert verdict(2, 0.1, 0.1, 1) == "insufficient_data"
    assert verdict(8, 0.1, 0.1, 0.61) == "supportive"
    assert verdict(13, -0.1, -0.1, 0.39) == "unsupportive"
    assert verdict(26, 0.1, 0.1, 0.60) == "mixed"
    assert verdict(13, None, 0.1, 0.8) == "insufficient_data"


def _bars(day, i, close, *, bad=False):
    return {
        "instrument_id": f"e{i:02}",
        "isin": f"e{i:02}",
        "session_date": day,
        "open": close,
        "high": close * (0.98 if bad else 1.01),
        "low": close * (1.02 if bad else 0.99),
        "close": close,
        "volume": 1000.0,
        "available_at": datetime.combine(
            day + timedelta(days=1), datetime.min.time(), ZoneInfo("Europe/Paris")
        ),
        "retrieved_at": datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC),
        "snapshot_id": "explicitly-synthetic-test",
    }


def _database(root, rows):
    path = root / "synthetic.parquet"
    pl.DataFrame(rows).write_parquet(path)
    database = root / "synthetic.duckdb"
    with duckdb.connect(str(database)) as db:
        db.execute(
            f"CREATE OR REPLACE VIEW market_daily_history AS SELECT * FROM read_parquet('{path}')"
        )
    return database


def test_incremental_maturity_append_only_and_future_quality(env):
    root, config, output, protocol, _ = env
    days = []
    day = T - timedelta(days=780)
    while day <= T:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    rows = [
        _bars(day, i, 100 + i + 0.025 * j * (1 + i / 100))
        for i in range(40)
        for j, day in enumerate(days)
    ]
    database = _database(root, rows)
    registered = register_cutoff(
        root=root,
        config=config,
        output=output,
        database=database,
        cutoff=T,
        now=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )
    assert registered["eligible_entities"] == 40
    partition = output / "cutoffs" / f"as_of_date={T}"
    ledger_sha = file_sha(partition / "eligibility.parquet")
    with pytest.raises(ValueError, match="duplicate"):
        register_cutoff(
            root=root,
            config=config,
            output=output,
            database=database,
            cutoff=T,
            now=datetime(2026, 10, 10, 12, tzinfo=UTC),
        )
    future_days = [date(2026, 10, d) for d in [12, 13, 14, 15, 16]]
    starts = {
        i: next(r["close"] for r in reversed(rows) if r["isin"] == f"e{i:02}") for i in range(40)
    }
    future = []
    for i in range(40):
        for j, day in enumerate(future_days):
            close = starts[i] * (1 + (0.002 if i % 2 else -0.002) * (j + 1))
            if i == 0 and j == 4:
                close = starts[i] * 1.5
            future.append(_bars(day, i, close, bad=i == 1 and j == 4))
    _database(root, rows + [r for r in future if r["session_date"] < future_days[-1]])
    assert (
        mature_pending(
            root=root,
            config=config,
            output=output,
            database=database,
            now=datetime(2026, 10, 16, 12, tzinfo=UTC),
        )
        == []
    )
    assert pl.read_parquet(output / "confirmation_cutoff_metrics.parquet").height == 0
    _database(root, rows + future)
    assert mature_pending(
        root=root,
        config=config,
        output=output,
        database=database,
        now=datetime(2026, 10, 17, 12, tzinfo=UTC),
    ) == [str(T)]
    assert file_sha(partition / "eligibility.parquet") == ledger_sha
    target = pl.read_parquet(partition / "outcome/targets.parquet")
    assert target["eligible_at_cutoff"].all()
    assert target.filter(pl.col("future_quality_status") == "quarantined").height == 1
    assert target.filter(pl.col("future_quality_status") == "review").height == 1
    assert (
        target.filter(pl.col("future_quality_status") == "review")["target_value"].null_count() == 0
    )
    old_sha = file_sha(partition / "outcome/cutoff_metrics.parquet")
    prefix = pl.read_parquet(output / "confirmation_candidate_metrics.parquet")
    assert (
        mature_pending(
            root=root,
            config=config,
            output=output,
            database=database,
            now=datetime(2026, 10, 17, 12, tzinfo=UTC),
        )
        == []
    )
    assert file_sha(partition / "outcome/cutoff_metrics.parquet") == old_sha
    assert load_monitor(output)["manifest"]["mature_cutoffs"] == 1
    # A second prospective registration cannot rewrite the already published first prefix.
    register_cutoff(
        root=root,
        config=config,
        output=output,
        database=database,
        cutoff=date(2026, 10, 16),
        now=datetime(2026, 10, 17, 12, tzinfo=UTC),
    )
    assert prefix.equals(pl.read_parquet(output / "confirmation_candidate_metrics.parquet"))
    assert file_sha(partition / "outcome/cutoff_metrics.parquet") == old_sha
    assert pl.read_parquet(partition / "outcome/cutoff_metrics.parquet").height == 1008
    (partition / "features.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="append-only"):
        verify_store(output, protocol)


def test_posthoc_registration_is_rejected(env):
    root, config, output, _, _ = env
    rows = [_bars(day, 0, 100.0) for day in [T, date(2026, 10, 12)]]
    database = _database(root, rows)
    with pytest.raises(ValueError, match="prospective"):
        register_cutoff(
            root=root,
            config=config,
            output=output,
            database=database,
            cutoff=T,
            now=datetime(2026, 10, 13, 12, tzinfo=UTC),
        )


def test_oriented_IC_and_group_aggregation(env):
    _, _, _, protocol, lock = env
    selected = lock["candidates"][:3]
    small = {**lock, "candidates": selected}
    features = pl.DataFrame(
        [
            {
                "entity_id": str(i),
                "feature_id": r["canonical_feature"],
                "feature_value": float(i * r["locked_direction"]),
            }
            for r in selected
            for i in range(40)
        ]
    )
    outcomes = pl.DataFrame(
        {
            "entity_id": list(map(str, range(40))),
            "eligible_at_cutoff": [True] * 40,
            "target_observable": [True] * 40,
            "target_interpretable": [True] * 40,
            "future_quality_status": ["clean"] * 40,
            "target_value": [-1.0] * 20 + [1.0] * 20,
        }
    )
    metrics = cutoff_metrics(features, outcomes, small, protocol, str(T))
    assert (metrics["oriented_ic"] > 0).all()
    assert np.allclose(metrics["oriented_ic"], metrics["spearman_ic"] * metrics["expected_sign"])
    # Synthetic cohorts for aggregate mechanics; the production lock is never altered.
    metrics = metrics.with_columns(
        *[
            pl.lit(True).alias(t)
            for t in ["broad_candidates", "strong_sign_candidates", "strict_candidates"]
        ]
    )
    history = pl.concat(
        [
            metrics.with_columns(pl.lit(str(T + timedelta(days=7 * k))).alias("cutoff"))
            for k in range(8)
        ]
    )
    candidates, cohorts, groups, intervals = cumulative_tables(history, protocol)
    assert candidates.filter(pl.col("mature_cutoffs") == 8).height == 6
    last = cohorts.filter(pl.col("mature_cutoffs") == 8)
    assert last["sign_conforming"].to_list() == [3] * 6
    assert (last["mean_oriented_ic"] > 0).all()
    assert intervals.height == 18
    assert {"rank_signature", "feature_family", "historical_window", "correlation_group"} == set(
        groups["group_type"]
    )
    again = cumulative_tables(history, protocol)
    assert intervals.equals(again[3])
    assert cohorts.filter(pl.col("mature_cutoffs") < 8)["ci90_lower"].null_count() == 42


def test_strict_scores_fixed_orientation_and_prediction_baselines(env):
    _, _, _, _, lock = env
    strict = [r for r in lock["candidates"] if r["strict_candidates"]][:2]
    small = {**lock, "candidates": strict}
    feature = pl.DataFrame(
        [
            {
                "entity_id": str(i),
                "feature_id": r["canonical_feature"],
                "feature_value": float(i * r["locked_direction"]),
            }
            for r in strict
            for i in range(40)
        ]
    )
    score = oriented_scores(feature, small)
    assert score["equal_weight_oriented_rank"][0] < 0.1
    assert score.filter(pl.col("entity_id") == "39")["equal_weight_oriented_rank"][0] > 0.9
    target = pl.DataFrame(
        {
            "entity_id": list(map(str, range(40))),
            "eligible_at_cutoff": [True] * 40,
            "target_observable": [True] * 40,
            "target_interpretable": [True] * 40,
            "future_quality_status": ["clean"] * 40,
            "target_value": [-1.0] * 20 + [1.0] * 20,
        }
    )
    metrics = prediction_metrics(score, target, 1, str(T))
    ensemble = metrics.filter(pl.col("method") == "equal_weight_oriented_rank")
    assert ensemble["auc"].to_list() == [1.0, 1.0]
    assert ensemble["accuracy"].to_list() == [1.0, 1.0]
    assert metrics.filter(pl.col("method") == "baseline_population")["accuracy"].to_list() == [
        0.5,
        0.5,
    ]


def test_known_rank_alias_groups_are_preserved(env):
    _, _, _, _, lock = env
    signatures = [r["rank_signature"] for r in lock["candidates"]]
    assert len(set(signatures)) == 504
    assert any(r["aliases"] and r["group_size"] > 1 for r in lock["candidates"])


def test_monitor_contains_no_development_average(env):
    root, config, output, _, _ = env
    rebuild_monitor(root=root, config=config, output=output)
    monitor = load_monitor(output)
    assert monitor["manifest"]["results_available"] is False
    assert monitor["manifest"]["pit_grade"] == "reconstructed"
    assert monitor["candidates"].is_empty() and monitor["cohorts"].is_empty()
    notebook = (REPO / "notebooks/srd_research_lab.py").read_text()
    # UI must expose distinct surfaces; numerical confirmation loader contains no development IC.
    assert "Research Contract" in notebook
    assert "Confirmation Monitor" in notebook
    assert "Development seulement" in notebook
    assert "Independent confirmation seulement" in notebook


def test_registration_metadata_and_removed_partitions_rejected(env):
    root, config, output, protocol, _ = env
    rows = [
        _bars(day, i, 100.0 + i + 0.01 * j)
        for i in range(32)
        for j, day in enumerate([T - timedelta(days=k) for k in range(7, -1, -1)])
    ]
    database = _database(root, rows)
    register_cutoff(
        root=root,
        config=config,
        output=output,
        database=database,
        cutoff=T,
        now=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )
    path = output / "cutoffs" / f"as_of_date={T}" / "registration.json"
    original = path.read_text()
    record = json.loads(original)
    record["eligible_entities"] = 999
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="metadata"):
        verify_store(output, protocol)
    path.write_text(original)
    shutil.rmtree(path.parent)
    with pytest.raises(ValueError, match="removed"):
        verify_store(output, protocol)


def test_dependency_or_registry_fingerprint_modified_rejected(env):
    root, config, _, protocol, _ = env
    (root / "uv.lock").write_text("changed dependency lock")
    with pytest.raises(ValueError, match="implementation"):
        verify_protocol(root, config, protocol)
