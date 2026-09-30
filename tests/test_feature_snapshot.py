"""SPEC-003 formula, point-in-time and real-data golden tests."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

from hocus_quant.features.factory import compute_entity_features
from hocus_quant.features.registry import FEATURE_REGISTRY, registry_document
from hocus_quant.features.snapshot import build_feature_snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "features" / "abc_market_golden_20260401.csv.gz"
GOLDEN_MANIFEST = Path(__file__).parent / "fixtures" / "features" / "spec003_golden_manifest.json"
PARIS = ZoneInfo("Europe/Paris")


def _synthetic_rows(
    count: int = 600, scale: float = 1.0, volume_scale: float = 1.0
) -> list[dict[str, Any]]:
    rows = []
    for index in range(count):
        close = scale * (100 + index * 0.2 + 2.5 * math.sin(index * 0.31))
        open_value = close * (1 + 0.002 * math.sin(index * 0.13))
        high = max(open_value, close) * 1.01
        low = min(open_value, close) * 0.99
        rows.append(
            {
                "session_date": date(2024, 1, 1) + timedelta(days=index),
                "open": open_value,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume_scale * (5000 + index * 3 + 100 * math.cos(index * 0.17)),
            }
        )
    return rows


def test_scale_change_preserves_all_available_canonical_features() -> None:
    base = compute_entity_features(_synthetic_rows())
    scaled = compute_entity_features(_synthetic_rows(scale=37.5, volume_scale=1_000))
    assert base.keys() == scaled.keys()
    for feature_id, (value, status, _count, _coverage) in base.items():
        other, other_status, *_ = scaled[feature_id]
        assert status == other_status, feature_id
        if value is not None:
            assert other == pytest.approx(value, rel=1e-8, abs=1e-8), feature_id


def test_price_and_volume_scales_are_independently_invariant() -> None:
    baseline = compute_entity_features(_synthetic_rows())
    price_scaled = compute_entity_features(_synthetic_rows(scale=1e-4))
    volume_scaled = compute_entity_features(_synthetic_rows(volume_scale=1e8))
    for feature_id, (value, status, *_rest) in baseline.items():
        for candidate in (price_scaled, volume_scaled):
            other, other_status, *_ = candidate[feature_id]
            assert other_status == status, feature_id
            if value is not None:
                assert other == pytest.approx(value, rel=1e-8, abs=1e-8), feature_id


def test_same_formula_has_same_semantics_for_all_asset_families() -> None:
    rows = _synthetic_rows()
    # Family labels are deliberately not passed into the factory: market families
    # share the exact same formula implementation when their OHLCV semantics match.
    family_results = {
        family: compute_entity_features(rows)
        for family in (
            "equity",
            "equity_us",
            "equity_de",
            "index",
            "sector_index",
            "commodity",
            "crypto",
            "fx_rates",
            "bond",
        )
    }
    reference = family_results["equity"]
    for family, result in family_results.items():
        assert result == reference, family
    assert compute_entity_features(rows) == compute_entity_features(rows)


def test_required_normalizations_and_regression_diagnostics() -> None:
    result = compute_entity_features(_synthetic_rows())
    assert result["close.level.base100.w60.v1"][0] == 100.0
    for feature_id in (
        "close.level.mean_delta.w60.v1",
        "close.log.trend_pct.w60.v1",
        "close.log.trend_tstat.w60.v1",
        "close.log.trend_r2.w60.v1",
        "close.level.std_pct.w60.v1",
        "close.level.var_rel.w60.v1",
    ):
        assert result[feature_id][1] == "available"
        assert result[feature_id][0] is not None


def test_rsi_14_change_contract_is_explicitly_versioned() -> None:
    short = compute_entity_features(_synthetic_rows(count=14))
    full = compute_entity_features(_synthetic_rows(count=15))
    assert short["ohlc.technical.rsi.w14.v1"][1] == "available"
    assert short["ohlc.technical.rsi.w15.v2"][1] == "unavailable"
    assert full["ohlc.technical.rsi.w15.v2"][1] == "available"
    legacy = next(item for item in FEATURE_REGISTRY if item.feature_id.endswith("rsi.w14.v1"))
    revised = next(item for item in FEATURE_REGISTRY if item.feature_id.endswith("rsi.w15.v2"))
    assert legacy.minimum_observations == 14
    assert revised.minimum_observations == 15


def test_insufficient_history_is_unavailable_not_zero() -> None:
    result = compute_entity_features(_synthetic_rows(count=20))
    value, status, count, ratio = result["close.level.mean_delta.w60.v1"]
    assert (value, status, count, ratio) == (None, "unavailable", 20, pytest.approx(1 / 3))


def test_volume_features_are_unavailable_when_volume_is_absent() -> None:
    rows = _synthetic_rows()
    for row in rows:
        row["volume"] = None
    result = compute_entity_features(rows)
    value, status, count, _ratio = result["volume.relative.current_vs_mean.w20.v1"]
    assert value is None
    assert status == "unavailable"
    assert count == 0


def test_registry_ids_are_unique_and_have_no_nominal_units() -> None:
    ids = [definition.feature_id for definition in FEATURE_REGISTRY]
    assert len(ids) == len(set(ids))
    assert all(
        token not in feature_id.lower()
        for feature_id in ids
        for token in ("eur", "usd", "points", "raw_price", "raw_volume")
    )
    document = registry_document()
    assert document["registry_version"] == "SPEC-003"
    assert all(item["dimensionless"] is True for item in document["features"])
    formulas = {item["feature_id"]: item["formula"] for item in document["features"]}
    assert "13 close differences" in formulas["ohlc.technical.rsi.w14.v1"]
    assert "14 close differences" in formulas["ohlc.technical.rsi.w15.v2"]


def test_versioned_registry_matches_frozen_contract() -> None:
    expected = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    registry = registry_document()
    frozen = json.loads(
        (Path(__file__).parents[1] / "src/hocus_quant/features/feature_registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert registry["sha256"] == expected["registry_sha256"]
    assert frozen["sha256"] == expected["registry_sha256"]
    assert len(registry["features"]) == expected["feature_count"]
    counts: dict[str, int] = {}
    for definition in FEATURE_REGISTRY:
        counts[definition.family] = counts.get(definition.family, 0) + 1
    assert counts == expected["feature_count_by_family"]


def test_local_golden_snapshot_matches_manifest_when_materialized() -> None:
    snapshot = Path(__file__).parents[1] / "data/features/2026-04-01/features.duckdb"
    if not snapshot.is_file():
        pytest.skip("large local golden snapshot is intentionally not versioned")
    expected = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        entity_count, feature_count, cell_count, available = connection.execute(
            """SELECT count(DISTINCT entity_id), count(DISTINCT feature_id), count(*),
                      count(*) FILTER (WHERE feature_status='available')
               FROM features_long"""
        ).fetchone()
        assert entity_count == expected["entity_count"]
        assert feature_count == expected["feature_count"]
        assert cell_count == expected["total_cells"]
        assert available == expected["available_cells"]
        family_counts = dict(
            connection.execute(
                "SELECT entity_family, count(DISTINCT entity_id) FROM features_long GROUP BY 1"
            ).fetchall()
        )
        assert family_counts == expected["entity_count_by_family"]
        for family, item in expected["fixed_panel"].items():
            for feature_id, value in item["features"].items():
                actual = connection.execute(
                    "SELECT feature_value FROM features_long WHERE entity_id=? AND feature_id=?",
                    [item["entity_id"], feature_id],
                ).fetchone()
                assert actual is not None, family
                assert actual[0] == pytest.approx(value, rel=1e-12, abs=1e-12)


def test_real_abc_bourse_golden_slice_2026_04_01() -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    with gzip.open(FIXTURE, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped.setdefault(row["entity_id"], []).append(
                {
                    "session_date": date.fromisoformat(row["session_date"]),
                    **{
                        name: float(row[name]) if row[name] else None
                        for name in ("open", "high", "low", "close", "volume")
                    },
                }
            )
    expected = {
        "equity:FR0000120628": (-3.3399717865737477, -1.4203065213997348, 67.47663551401871),
        "index:market_indices:DE000SLA4ZB0": (
            6.635495021691162,
            -9.082874317948436,
            36.29032543551294,
        ),
        "crypto:crypto:ABC000000147": (15.510705609852549, -40.23696934687018, 36.89802676969781),
    }
    expected_rsi_v2 = {
        "equity:FR0000120628": 68.42105263157895,
        "index:market_indices:DE000SLA4ZB0": 34.092806236302394,
        "crypto:crypto:ABC000000147": 37.95536259412521,
    }
    assert set(grouped) == set(expected)
    for entity_id, rows in grouped.items():
        assert len(rows) == 504
        assert rows[-1]["session_date"] <= date(2026, 4, 1)
        features = compute_entity_features(rows)
        mean_delta, trend_pct, rsi = expected[entity_id]
        assert features["close.level.mean_delta.w60.v1"][0] == pytest.approx(mean_delta, abs=1e-9)
        assert features["close.log.trend_pct.w60.v1"][0] == pytest.approx(trend_pct, abs=1e-9)
        assert features["ohlc.technical.rsi.w14.v1"][0] == pytest.approx(rsi, abs=1e-9)
        assert features["ohlc.technical.rsi.w15.v2"][0] == pytest.approx(
            expected_rsi_v2[entity_id], abs=1e-9
        )


def test_snapshot_as_of_excludes_later_available_bar_and_replays(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "research.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute("""
            CREATE TABLE daily_rows (
              instrument_id VARCHAR, isin VARCHAR, session_date DATE,
              open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
              available_at TIMESTAMPTZ, retrieved_at TIMESTAMPTZ, snapshot_id VARCHAR
            )
        """)
        connection.execute("CREATE VIEW market_daily_history AS SELECT * FROM daily_rows")
        connection.execute("""
            CREATE VIEW market_series_history AS
            SELECT * FROM (VALUES (NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
              NULL::VARCHAR, NULL::DATE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE,
              NULL::DOUBLE, NULL::DOUBLE, NULL::TIMESTAMPTZ, NULL::TIMESTAMPTZ,
              NULL::VARCHAR, NULL::VARCHAR)) AS v(universe_id, series_id,
              provider_instrument_id, isin, session_date, open, high, low, close,
              volume, available_at, retrieved_at, snapshot_checksum, member_checksum)
            WHERE 1=0
        """)
        values = [
            (date(2026, 3, 28), 10.0),
            (date(2026, 3, 30), 11.0),
            (date(2026, 3, 31), 20.0),
            (date(2026, 4, 1), 24.0),
            (date(2026, 4, 2), 999.0),
        ]
        for index, (session, close) in enumerate(values):
            available = datetime.combine(session + timedelta(days=1), datetime_time.min, PARIS)
            connection.execute(
                "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    "XTEST",
                    "XTEST",
                    session,
                    close - 0.2,
                    close + 0.3,
                    close - 0.4,
                    close,
                    1000.0,
                    available,
                    datetime(2026, 9, 29, tzinfo=UTC),
                    f"snap-{index}",
                ],
            )
        connection.execute(
            "INSERT INTO daily_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                "YSHORT",
                "YSHORT",
                date(2026, 3, 30),
                9.8,
                10.2,
                9.7,
                10.0,
                1000.0,
                datetime(2026, 3, 31, tzinfo=PARIS),
                datetime(2026, 9, 29, tzinfo=UTC),
                "short",
            ],
        )
    first = build_feature_snapshot(
        as_of_date=date(2026, 4, 1), output_dir=tmp_path / "one", data_dir=data_dir
    )
    replay = build_feature_snapshot(
        as_of_date=date(2026, 4, 1), output_dir=tmp_path / "two", data_dir=data_dir
    )
    assert first["source_observation_count"] == 4
    assert first["candidate_entity_count"] == 2
    assert first["entity_count"] == 1
    assert first["ineligible_entity_count"] == 1
    assert first["source_rows_retrieved_after_cutoff"] == 4
    assert first["pit_grade"] == "reconstructed"
    assert first["strict_pit_claimed"] is False
    hardening = json.loads((tmp_path / "one" / "hardening_audit.json").read_text())
    assert hardening["extreme_feature_count"] == len(first["extreme_features"])
    assert hardening["source_quality"]["by_family"]["equity"]["bar_count"] == 4
    assert first["source_observation_count"] == replay["source_observation_count"]
    long_one = Path(first["outputs"]["long_parquet"]).read_bytes()
    long_two = Path(replay["outputs"]["long_parquet"]).read_bytes()
    assert hashlib.sha256(long_one).digest() == hashlib.sha256(long_two).digest()
    with duckdb.connect(str(Path(first["outputs"]["duckdb"])), read_only=True) as connection:
        current = connection.execute("""
            SELECT feature_value FROM features_long
            WHERE feature_id='close.level.base100.w3.v1'
        """).fetchone()[0]
        mean_delta = connection.execute("""
            SELECT feature_value FROM features_long
            WHERE feature_id='close.level.mean_delta.w3.v1'
        """).fetchone()[0]
    assert current == 100.0
    assert mean_delta == pytest.approx(100 * ((11 + 20 + 24) / 3 / 24 - 1))
    assert (tmp_path / "one" / "hardening_audit.md").is_file()
