"""Ingest provider-neutral Gremlin market snapshots into Parquet and DuckDB."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import duckdb
import pandera.polars as pa
import polars as pl

from hocus_quant.schemas.market import MarketDataSnapshot

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_OHLC_COLUMNS = ("open", "high", "low", "close")

MARKET_DAILY_SCHEMA = pa.DataFrameSchema(
    {
        "snapshot_id": pa.Column(str, nullable=False),
        "instrument_id": pa.Column(str, nullable=False),
        "isin": pa.Column(str, nullable=False),
        "session_date": pa.Column(pl.Date, nullable=False),
        "open": pa.Column(float, nullable=True),
        "high": pa.Column(float, nullable=True),
        "low": pa.Column(float, nullable=True),
        "close": pa.Column(float, nullable=True),
        "adjusted_close": pa.Column(float, nullable=True),
        "volume": pa.Column(float, nullable=True),
        "currency": pa.Column(str, nullable=True),
        "mic": pa.Column(str, nullable=False),
        "provider": pa.Column(str, nullable=False),
        "provider_symbol": pa.Column(str, nullable=False),
        "retrieved_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "available_at": pa.Column(pl.Datetime("us", "UTC"), nullable=False),
        "snapshot_checksum": pa.Column(str, nullable=False),
        "adjustment_basis": pa.Column(str, nullable=True),
        "adjusted_close_available_at": pa.Column(pl.Datetime("us", "UTC"), nullable=True),
        "adjusted_close_point_in_time_safe": pa.Column(bool, nullable=False),
        "quality_issues": pa.Column(list, nullable=False),
    },
    strict=True,
)


def ingest_market_snapshot(
    snapshot_path: Path,
    *,
    gremlin_artifact_root: Path,
    data_dir: Path,
) -> dict[str, Path]:
    """Verify a canonical Gremlin manifest, copy raw blobs, and build the dataset."""
    snapshot = MarketDataSnapshot.model_validate_json(snapshot_path.read_bytes())
    if not _SAFE_ID.fullmatch(snapshot.snapshot_id):
        raise ValueError("snapshot_id contains unsafe path characters")

    raw_paths: dict[str, Path] = {}
    raw_capture_dir = data_dir / "raw" / "market" / "captures"
    raw_capture_dir.mkdir(parents=True, exist_ok=True)
    for raw_ref in snapshot.raw_snapshots:
        checksum_hex = raw_ref.checksum.partition(":")[2]
        expected_id = f"raw-{checksum_hex}"
        if raw_ref.artifact_id != expected_id:
            raise ValueError("raw artifact_id must match its content checksum")
        gremlin_path = gremlin_artifact_root / f"{raw_ref.artifact_id}.bin"
        if not gremlin_path.is_file():
            raise FileNotFoundError(f"Gremlin raw artifact is missing: {raw_ref.artifact_id}")
        payload = gremlin_path.read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != checksum_hex
            or len(payload) != raw_ref.size_bytes
        ):
            raise ValueError(
                f"Gremlin raw artifact failed checksum/size validation: {raw_ref.artifact_id}"
            )
        target_dir = data_dir / "raw" / "market" / checksum_hex
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "payload"
        if target_path.exists() and target_path.read_bytes() != payload:
            raise ValueError("content-addressed market raw payload conflicts with existing bytes")
        if not target_path.exists():
            shutil.copyfile(gremlin_path, target_path)
        raw_paths[raw_ref.checksum] = target_path

        capture_manifest = {
            "provider": snapshot.provider,
            "capture_id": raw_ref.capture_id,
            "artifact_id": raw_ref.artifact_id,
            "checksum": raw_ref.checksum,
            "content_type": raw_ref.content_type,
            "source_url": raw_ref.source_url,
            "provider_symbol": raw_ref.provider_symbol,
            "retrieved_at": raw_ref.retrieved_at.isoformat(),
            "metadata": raw_ref.metadata,
        }
        capture_path = raw_capture_dir / f"{raw_ref.capture_id}.json"
        serialized = (
            json.dumps(capture_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        if capture_path.exists() and capture_path.read_text(encoding="utf-8") != serialized:
            raise ValueError("capture_id already exists with different provenance")
        if not capture_path.exists():
            capture_path.write_text(serialized, encoding="utf-8")

    daily_rows = [_market_row(snapshot.snapshot_id, row) for row in snapshot.market_daily]
    instrument_rows = [
        {"snapshot_id": snapshot.snapshot_id, **mapping.model_dump(mode="json")}
        for mapping in snapshot.instruments
    ]
    action_rows = [
        {"snapshot_id": snapshot.snapshot_id, **action.model_dump(mode="json")}
        for action in snapshot.corporate_actions
    ]

    bronze_dir = data_dir / "bronze" / "market_daily"
    silver_market_dir = data_dir / "silver" / "market_daily"
    silver_instruments_dir = data_dir / "silver" / "instruments"
    silver_actions_dir = data_dir / "silver" / "corporate_actions"
    for directory in (bronze_dir, silver_market_dir, silver_instruments_dir, silver_actions_dir):
        directory.mkdir(parents=True, exist_ok=True)

    bronze_path = bronze_dir / f"{snapshot.snapshot_id}.parquet"
    silver_path = silver_market_dir / f"{snapshot.snapshot_id}.parquet"
    instrument_path = silver_instruments_dir / f"{snapshot.snapshot_id}.parquet"
    action_path = silver_actions_dir / f"{snapshot.snapshot_id}.parquet"

    if daily_rows:
        bronze = pl.DataFrame(
            [row.model_dump(mode="json") for row in snapshot.market_daily], infer_schema_length=None
        )
        if not bronze_path.exists():
            bronze.write_parquet(bronze_path)
        silver = _market_frame(daily_rows)
        silver = MARKET_DAILY_SCHEMA.validate(silver)
        if not silver_path.exists():
            silver.write_parquet(silver_path)
    else:
        silver = pl.DataFrame()

    if instrument_rows and not instrument_path.exists():
        pl.DataFrame(instrument_rows, infer_schema_length=None).write_parquet(instrument_path)
    if action_rows and not action_path.exists():
        pl.DataFrame(action_rows, infer_schema_length=None).write_parquet(action_path)

    audit = _audit_market_snapshot(snapshot, daily_rows, instrument_rows, action_rows)
    audit_path = silver_market_dir / f"audit-{snapshot.snapshot_id}.json"
    unresolved_path = data_dir / "unresolved_instruments.json"
    suspicious_path = data_dir / "suspicious_observations.json"
    coverage_path = data_dir / "provider_coverage.json"
    _write_json(audit_path, audit)
    _write_json(unresolved_path, audit["unresolved_instruments"])
    _write_json(suspicious_path, audit["suspicious_observations"])
    _write_json(coverage_path, audit["provider_coverage"])

    db_path = data_dir / "research.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _refresh_duckdb_views(db_path, data_dir)
    return {
        "raw": next(iter(raw_paths.values())) if raw_paths else data_dir / "raw" / "market",
        "bronze": bronze_path,
        "silver": silver_path,
        "instruments": instrument_path,
        "corporate_actions": action_path,
        "audit": audit_path,
        "unresolved": unresolved_path,
        "suspicious": suspicious_path,
        "coverage": coverage_path,
        "duckdb": db_path,
    }


def query_market_as_of(db_path: Path, as_of: datetime) -> list[dict[str, Any]]:
    """Return the latest raw-bar revision known at cutoff; unsafe adjusted values are null."""
    cutoff = _require_aware(as_of)
    query = """
        WITH known AS (
            SELECT *, row_number() OVER (
                PARTITION BY instrument_id, session_date
                ORDER BY
                    CASE WHEN retrieved_at <= ? THEN 0 ELSE 1 END,
                    CASE WHEN retrieved_at <= ? THEN retrieved_at END DESC,
                    CASE WHEN retrieved_at > ? THEN retrieved_at END ASC,
                    snapshot_id DESC
            ) AS revision_rank
            FROM market_daily_history
            WHERE available_at <= ?
        )
        SELECT snapshot_id, instrument_id, isin, session_date,
               open, high, low, close,
               CASE WHEN adjusted_close_point_in_time_safe
                         AND adjusted_close_available_at <= ?
                    THEN adjusted_close ELSE NULL END AS adjusted_close,
               volume, currency, mic, provider, provider_symbol,
               retrieved_at, available_at, snapshot_checksum,
               adjustment_basis, adjusted_close_available_at,
               adjusted_close_point_in_time_safe, quality_issues
        FROM known WHERE revision_rank = 1 ORDER BY session_date, instrument_id
    """
    with duckdb.connect(str(db_path), read_only=True) as connection:
        cursor = connection.execute(query, [cutoff, cutoff, cutoff, cutoff, cutoff])
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def query_market_amf_as_of(db_path: Path, as_of: datetime) -> list[dict[str, Any]]:
    """Join market bars to each holder's latest known AMF record without multiplying rows."""
    cutoff = _require_aware(as_of)
    query = """
        WITH market_known AS (
            SELECT *, row_number() OVER (
                PARTITION BY instrument_id, session_date
                ORDER BY
                    CASE WHEN retrieved_at <= ? THEN 0 ELSE 1 END,
                    CASE WHEN retrieved_at <= ? THEN retrieved_at END DESC,
                    CASE WHEN retrieved_at > ? THEN retrieved_at END ASC,
                    snapshot_id DESC
            ) AS revision_rank
            FROM market_daily_history
            WHERE available_at <= ?
        ), market AS (
            SELECT * FROM market_known WHERE revision_rank = 1
        ), candidates AS (
            SELECT
                m.session_date, m.instrument_id, m.isin, m.close, m.adjusted_close,
                m.volume, m.available_at AS market_available_at,
                s.holder, s.net_short_position_pct, s.available_at AS short_available_at,
                row_number() OVER (
                    PARTITION BY m.instrument_id, m.session_date, s.holder
                    ORDER BY s.available_at DESC, s.publication_date DESC, s.retrieved_at DESC
                ) AS short_rank
            FROM market m
            LEFT JOIN amf_short_positions s
              ON m.isin = s.isin AND s.available_at <= m.available_at AND s.available_at <= ?
        )
        SELECT * EXCLUDE (short_rank) FROM candidates WHERE short_rank = 1
        ORDER BY session_date, instrument_id, holder
    """
    with duckdb.connect(str(db_path), read_only=True) as connection:
        cursor = connection.execute(query, [cutoff, cutoff, cutoff, cutoff, cutoff])
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _market_row(snapshot_id: str, row: Any) -> dict[str, Any]:
    values = row.model_dump(mode="json")
    issues: list[dict[str, Any]] = []
    for name in _OHLC_COLUMNS:
        value = values[name]
        if value is not None and value <= 0:
            issues.append({"code": "non_positive_price", "field": name, "observed_value": value})
    low, high = values["low"], values["high"]
    if low is not None and high is not None:
        for name in ("open", "close"):
            value = values[name]
            if value is not None and not low <= value <= high:
                issues.append({"code": "ohlc_inconsistent", "field": name, "observed_value": value})
    if values["volume"] is not None and values["volume"] < 0:
        issues.append(
            {"code": "negative_volume", "field": "volume", "observed_value": values["volume"]}
        )
    values["snapshot_id"] = snapshot_id
    values["session_date"] = date.fromisoformat(values["session_date"])
    values["retrieved_at"] = _parse_datetime(values["retrieved_at"])
    values["available_at"] = _parse_datetime(values["available_at"])
    values["adjusted_close_available_at"] = (
        _parse_datetime(values["adjusted_close_available_at"])
        if values["adjusted_close_available_at"]
        else None
    )
    values["quality_issues"] = issues
    return cast(dict[str, Any], values)


def _market_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    frame = pl.DataFrame(rows, infer_schema_length=None)
    for name in ("session_date",):
        frame = frame.with_columns(pl.col(name).cast(pl.Date))
    for name in ("retrieved_at", "available_at", "adjusted_close_available_at"):
        frame = frame.with_columns(pl.col(name).cast(pl.Datetime("us", "UTC")))
    for name in (*_OHLC_COLUMNS, "adjusted_close", "volume"):
        frame = frame.with_columns(pl.col(name).cast(pl.Float64))
    return frame


def _audit_market_snapshot(
    snapshot: MarketDataSnapshot,
    daily_rows: list[dict[str, Any]],
    instrument_rows: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    mappings_by_isin = {row["isin"]: row for row in instrument_rows}
    status_counts = Counter(row["status"] for row in instrument_rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        grouped[row["isin"]].append(row)
    coverage: dict[str, Any] = {}
    suspicious: list[dict[str, Any]] = []
    for isin, rows in grouped.items():
        ordered = sorted(rows, key=lambda row: row["session_date"])
        years = Counter(row["session_date"].year for row in rows)
        issues = [item for row in rows for item in row["quality_issues"]]
        for row in rows:
            if row["quality_issues"]:
                suspicious.append(
                    {
                        "isin": isin,
                        "session_date": row["session_date"].isoformat(),
                        "issues": row["quality_issues"],
                    }
                )
        daily_returns: list[float] = []
        previous: float | None = None
        for row in ordered:
            close = row["close"]
            if close is not None and previous is not None and previous > 0:
                daily_returns.append(close / previous - 1)
                if abs(close / previous - 1) >= 0.30:
                    suspicious.append(
                        {
                            "isin": isin,
                            "session_date": row["session_date"].isoformat(),
                            "code": "extreme_daily_return",
                            "return_pct": round((close / previous - 1) * 100, 4),
                            "corporate_action_review": True,
                        }
                    )
            if close is not None and close > 0:
                previous = close
        coverage[isin] = {
            "instrument_id": mappings_by_isin.get(isin, {}).get("instrument_id"),
            "row_count": len(rows),
            "date_min": ordered[0]["session_date"].isoformat(),
            "date_max": ordered[-1]["session_date"].isoformat(),
            "sessions": len({row["session_date"] for row in rows}),
            "rows_per_year": dict(sorted(years.items())),
            "missing_ohlc_count": sum(
                any(row[name] is None for name in _OHLC_COLUMNS) for row in rows
            ),
            "missing_volume_count": sum(row["volume"] is None for row in rows),
            "missing_adjusted_close_count": sum(row["adjusted_close"] is None for row in rows),
            "quality_issue_count": len(issues),
            "currency": sorted({row["currency"] for row in rows if row["currency"]}),
            "mic": sorted({row["mic"] for row in rows}),
            "extreme_daily_return_count": sum(abs(value) >= 0.30 for value in daily_returns),
        }
    unresolved = [
        {
            "isin": row["isin"],
            "instrument_id": row["instrument_id"],
            "status": row["status"],
            "mapping_source": row["mapping_source"],
            "candidates": row["candidates"],
        }
        for row in instrument_rows
        if row["status"] != "resolved"
    ]
    expected = int(snapshot.metadata.get("requested_isin_count", len(instrument_rows)))
    actual = len(instrument_rows)
    dates_by_instrument: dict[str, set[date]] = defaultdict(set)
    for row in daily_rows:
        dates_by_instrument[row["instrument_id"]].add(row["session_date"])
    duplicate_sessions = sum(
        len(rows) - len({row["session_date"] for row in rows}) for rows in grouped.values()
    )
    return {
        "provider": snapshot.provider,
        "snapshot_id": snapshot.snapshot_id,
        "acquisition_timestamp": snapshot.retrieved_at.isoformat(),
        "universe_id": snapshot.universe_id,
        "requested_isin_count": expected,
        "instrument_mappings_returned": actual,
        "mapping_status_counts": dict(status_counts),
        "resolved_isin_count": status_counts["resolved"],
        "ambiguous_isin_count": status_counts["ambiguous"],
        "not_found_isin_count": status_counts["not_found"],
        "invalid_isin_count": status_counts["invalid"],
        "mapping_coverage_rate": status_counts["resolved"] / expected if expected else 0.0,
        "mapping_response_complete": actual == expected,
        "market_row_count": len(daily_rows),
        "session_date_min": min((row["session_date"] for row in daily_rows), default=None),
        "session_date_max": max((row["session_date"] for row in daily_rows), default=None),
        "missing_ohlc_count": sum(
            any(row[name] is None for name in _OHLC_COLUMNS) for row in daily_rows
        ),
        "missing_volume_count": sum(row["volume"] is None for row in daily_rows),
        "missing_adjusted_close_count": sum(
            row["adjusted_close"] is None for row in daily_rows
        ),
        "duplicate_sessions_in_snapshot": duplicate_sessions,
        "instrument_coverage": coverage,
        "currency_distribution": dict(
            Counter(row["currency"] for row in daily_rows if row["currency"])
        ),
        "mic_distribution": dict(Counter(row["mic"] for row in daily_rows)),
        "corporate_action_count": len(action_rows),
        "adjustment_basis_distribution": dict(
            Counter(row["adjustment_basis"] for row in daily_rows if row["adjustment_basis"])
        ),
        "unresolved_instruments": unresolved,
        "suspicious_observations": suspicious,
        "provider_coverage": {
            "provider": snapshot.provider,
            "universe_id": snapshot.universe_id,
            "requested": expected,
            "mapping_results_returned": actual,
            "rows": len(daily_rows),
            "history_min": min((row["session_date"] for row in daily_rows), default=None),
            "history_max": max((row["session_date"] for row in daily_rows), default=None),
            "per_instrument": coverage,
        },
        "calendar_gap_policy": (
            "No calendar-day gap is called missing: only an explicit market calendar "
            "or observed sessions can establish expected sessions."
        ),
    }


def _refresh_duckdb_views(db_path: Path, data_dir: Path) -> None:
    with duckdb.connect(str(db_path)) as connection:
        for view, folder in (
            ("market_daily_history", data_dir / "silver" / "market_daily"),
            ("instruments_history", data_dir / "silver" / "instruments"),
            ("corporate_actions_history", data_dir / "silver" / "corporate_actions"),
        ):
            files = sorted(folder.glob("*.parquet"))
            if not files:
                continue
            parquet_list = ", ".join(
                "'" + path.as_posix().replace("'", "''") + "'" for path in files
            )
            connection.execute(
                f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM "
                f"read_parquet([{parquet_list}], union_by_name=true)"
            )
        if _view_exists(connection, "market_daily_history"):
            connection.execute("""
                CREATE OR REPLACE VIEW market_daily AS
                SELECT * EXCLUDE (revision_rank)
                FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY instrument_id, session_date
                        ORDER BY retrieved_at DESC, snapshot_id DESC
                    ) AS revision_rank
                    FROM market_daily_history
                ) WHERE revision_rank = 1
            """)
        if _view_exists(connection, "instruments_history"):
            connection.execute("""
                CREATE OR REPLACE VIEW instruments AS
                SELECT * EXCLUDE (revision_rank)
                FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY instrument_id, provider, valid_from, valid_to
                        ORDER BY retrieved_at DESC, snapshot_id DESC
                    ) AS revision_rank
                    FROM instruments_history
                ) WHERE revision_rank = 1
            """)
        if _view_exists(connection, "corporate_actions_history"):
            connection.execute(
                "CREATE OR REPLACE VIEW corporate_actions AS "
                "SELECT * FROM corporate_actions_history"
            )


def _view_exists(connection: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM information_schema.views WHERE table_name=?", [name]
    ).fetchone()
    return row is not None and row[0] > 0


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
