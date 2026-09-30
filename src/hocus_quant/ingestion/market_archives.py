"""Import manually delivered ABC Bourse multi-universe ZIP archives."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import uuid
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

SOURCE_URL = "https://www.abcbourse.com/download/historiques"
PROVIDER = "abc-bourse-manual"
PARIS = ZoneInfo("Europe/Paris")
_IDENTIFIER = re.compile(r"^[A-Z0-9]{1,32}$")
_UNIVERSES = {
    "Crypto_monnaies": "crypto",
    "Devises_et_taux": "fx_rates",
    "Indices_de_marche": "market_indices",
    "Indices_sectoriels": "sector_indices",
    "Matieres_premieres": "commodities",
    "Obligations": "bonds",
    "SRD": "srd",
    "Valeurs_allemandes": "german_equities",
    "Valeurs_americaines": "us_equities",
}

_BRONZE_SCHEMA = pa.schema(
    [
        ("universe_id", pa.string()),
        ("provider_instrument_id", pa.string()),
        ("source_member", pa.string()),
        ("source_date_text", pa.string()),
        ("open_raw", pa.string()),
        ("high_raw", pa.string()),
        ("low_raw", pa.string()),
        ("close_raw", pa.string()),
        ("volume_raw", pa.string()),
        ("snapshot_checksum", pa.string()),
        ("member_checksum", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
    ]
)

_SILVER_SCHEMA = pa.schema(
    [
        ("universe_id", pa.string()),
        ("series_id", pa.string()),
        ("provider_instrument_id", pa.string()),
        ("isin", pa.string()),
        ("session_date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("currency", pa.string()),
        ("mic", pa.string()),
        ("provider", pa.string()),
        ("source_member", pa.string()),
        ("snapshot_checksum", pa.string()),
        ("member_checksum", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("available_at", pa.timestamp("us", tz="Europe/Paris")),
    ]
)


def ingest_market_archives(
    archive_dir: Path,
    *,
    data_dir: Path,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    """Archive the original ZIPs and normalize supplemental universes to Parquet.

    SRD is left to the existing Gremlin ``market-data`` snapshot adapter. Its
    complete ZIP is retained here, while SRD observations are imported through
    that adapter to preserve the established equity/ISIN contract.
    """
    captured_at = retrieved_at or datetime.now(UTC)
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)
    archives = sorted(path for path in archive_dir.glob("*.zip") if path.is_file())
    if not archives:
        raise ValueError(f"no ZIP archives found in {archive_dir}")

    raw_dir = data_dir / "raw" / "market_archives" / "sha256"
    captures_dir = data_dir / "raw" / "market_archives" / "captures"
    bronze_root = data_dir / "bronze" / "market_series"
    silver_root = data_dir / "silver" / "market_series"
    for directory in (raw_dir, captures_dir, bronze_root, silver_root):
        directory.mkdir(parents=True, exist_ok=True)

    archive_reports: list[dict[str, Any]] = []
    for archive_path in archives:
        universe_id = _universe_for(archive_path.name)
        archive_bytes = archive_path.read_bytes()
        checksum_hex = hashlib.sha256(archive_bytes).hexdigest()
        checksum = f"sha256:{checksum_hex}"
        raw_path = raw_dir / f"{checksum_hex}.zip"
        _store_immutable(archive_bytes, raw_path, checksum_hex)

        capture_id = f"capture-{uuid.uuid4().hex}"
        capture = {
            "source_id": PROVIDER,
            "source_url": SOURCE_URL,
            "retrieved_at": captured_at.isoformat(),
            "content_type": "application/zip",
            "checksum": checksum,
            "payload_path": str(raw_path.relative_to(data_dir)),
            "original_filename": archive_path.name,
            "capture_id": capture_id,
            "metadata": {"acquisition_mode": "manual_local_archive"},
        }
        _write_json(captures_dir / f"{capture_id}.json", capture)

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = _safe_members(archive)
            text_members = [
                name for name in members if name.startswith("Cotations") and name.endswith(".txt")
            ]
            inventory_name = next((name for name in members if name.lower().endswith(".csv")), None)
            inventory = _read_inventory(archive, inventory_name) if inventory_name else {}
            member_audit = _audit_inventory(inventory, text_members)

            is_partial_srd = universe_id == "srd" and "partiel" in archive_path.stem.lower()
            is_srd = universe_id == "srd"
            report: dict[str, Any] = {
                "archive": archive_path.name,
                "universe_id": universe_id,
                "archive_checksum": checksum,
                "raw_path": str(raw_path.relative_to(data_dir)),
                "capture_id": capture_id,
                "text_member_count": len(text_members),
                "inventory": member_audit,
                "status": "archived_only",
                "reason": None,
            }
            if is_partial_srd:
                report["reason"] = (
                    "partial SRD package retained as raw; complete package is imported"
                )
            elif is_srd:
                report["reason"] = (
                    "SRD observations use the existing Gremlin market snapshot adapter"
                )
            elif not text_members:
                raise ValueError(f"{archive_path.name}: no Cotations*.txt members found")
            else:
                report.update(
                    _normalize_archive(
                        archive,
                        archive_path=archive_path,
                        text_members=text_members,
                        universe_id=universe_id,
                        checksum=checksum,
                        checksum_hex=checksum_hex,
                        captured_at=captured_at,
                        data_dir=data_dir,
                        bronze_root=bronze_root,
                        silver_root=silver_root,
                        inventory=inventory,
                    )
                )
            archive_reports.append(report)

    combined = _combined_audit(archive_reports)
    audit_path = data_dir / "silver" / "market_series" / "archive_audit.json"
    _write_json(audit_path, combined)
    _refresh_series_views(data_dir / "research.duckdb", silver_root)
    combined["audit_path"] = str(audit_path)
    _write_json(audit_path, combined)
    return combined


def _normalize_archive(
    archive: zipfile.ZipFile,
    *,
    archive_path: Path,
    text_members: list[str],
    universe_id: str,
    checksum: str,
    checksum_hex: str,
    captured_at: datetime,
    data_dir: Path,
    bronze_root: Path,
    silver_root: Path,
    inventory: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    bronze_dir = bronze_root / universe_id
    silver_dir = silver_root / universe_id
    bronze_dir.mkdir(parents=True, exist_ok=True)
    silver_dir.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_dir / f"{checksum_hex}.parquet"
    silver_path = silver_dir / f"{checksum_hex}.parquet"
    audit_path = silver_dir / f"audit-{checksum_hex}.json"
    if bronze_path.exists() and silver_path.exists() and audit_path.exists():
        previous = cast(dict[str, Any], json.loads(audit_path.read_text(encoding="utf-8")))
        previous["status"] = "already_ingested"
        return previous

    bronze_tmp = bronze_path.with_suffix(".parquet.tmp")
    silver_tmp = silver_path.with_suffix(".parquet.tmp")
    bronze_writer = pq.ParquetWriter(bronze_tmp, _BRONZE_SCHEMA, compression="zstd")
    silver_writer = pq.ParquetWriter(silver_tmp, _SILVER_SCHEMA, compression="zstd")
    bronze_batch: list[dict[str, Any]] = []
    silver_batch: list[dict[str, Any]] = []
    actual_rows_by_member: Counter[str] = Counter()
    identifier_rows: Counter[str] = Counter()
    valid_isin_rows = 0
    missing_ohlc_rows = 0
    zero_volume_rows = 0
    session_dates: list[date] = []
    price_closes: list[float] = []
    total_rows = 0

    try:
        for member_name in text_members:
            member_bytes = archive.read(member_name)
            member_checksum = "sha256:" + hashlib.sha256(member_bytes).hexdigest()
            decoded = member_bytes.decode("utf-8-sig", errors="strict")
            reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=";")
            for line_number, cells in enumerate(reader, start=1):
                if not cells or (len(cells) == 1 and not cells[0].strip()):
                    continue
                if len(cells) != 7:
                    raise ValueError(
                        f"{archive_path.name}:{member_name}:{line_number}: "
                        f"expected 7 fields, got {len(cells)}"
                    )
                source_id = cells[0].strip().upper()
                if not _IDENTIFIER.fullmatch(source_id):
                    raise ValueError(
                        f"{archive_path.name}:{member_name}:{line_number}: "
                        "invalid source identifier"
                    )
                try:
                    session_date = datetime.strptime(cells[1].strip(), "%d/%m/%y").date()
                except ValueError as exc:
                    raise ValueError(
                        f"{archive_path.name}:{member_name}:{line_number}: "
                        f"invalid date {cells[1]!r}"
                    ) from exc
                numbers = [
                    _parse_number(
                        value, archive=archive_path.name, member=member_name, line=line_number
                    )
                    for value in cells[2:]
                ]
                isin = source_id if _valid_isin(source_id) else None
                valid_isin_rows += int(isin is not None)
                identifier_rows[source_id] += 1
                missing_ohlc_rows += int(all(value is None for value in numbers[:4]))
                zero_volume_rows += int(numbers[4] == 0)
                session_dates.append(session_date)
                if numbers[3] is not None:
                    price_closes.append(numbers[3])
                actual_rows_by_member[member_name] += 1
                total_rows += 1

                bronze_batch.append(
                    {
                        "universe_id": universe_id,
                        "provider_instrument_id": source_id,
                        "source_member": member_name,
                        "source_date_text": cells[1],
                        "open_raw": cells[2],
                        "high_raw": cells[3],
                        "low_raw": cells[4],
                        "close_raw": cells[5],
                        "volume_raw": cells[6],
                        "snapshot_checksum": checksum,
                        "member_checksum": member_checksum,
                        "retrieved_at": captured_at,
                    }
                )
                silver_batch.append(
                    {
                        "universe_id": universe_id,
                        "series_id": f"{universe_id}:{source_id}",
                        "provider_instrument_id": source_id,
                        "isin": isin,
                        "session_date": session_date,
                        "open": numbers[0],
                        "high": numbers[1],
                        "low": numbers[2],
                        "close": numbers[3],
                        "volume": numbers[4],
                        "currency": None,
                        "mic": None,
                        "provider": PROVIDER,
                        "source_member": member_name,
                        "snapshot_checksum": checksum,
                        "member_checksum": member_checksum,
                        "retrieved_at": captured_at,
                        "available_at": datetime.combine(
                            session_date + timedelta(days=1), time.min, tzinfo=PARIS
                        ),
                    }
                )
                if len(silver_batch) >= 20_000:
                    _write_batch(bronze_writer, bronze_batch, _BRONZE_SCHEMA)
                    _write_batch(silver_writer, silver_batch, _SILVER_SCHEMA)
                    bronze_batch.clear()
                    silver_batch.clear()

        _write_batch(bronze_writer, bronze_batch, _BRONZE_SCHEMA)
        _write_batch(silver_writer, silver_batch, _SILVER_SCHEMA)
    except Exception:
        bronze_writer.close()
        silver_writer.close()
        bronze_tmp.unlink(missing_ok=True)
        silver_tmp.unlink(missing_ok=True)
        raise
    else:
        bronze_writer.close()
        silver_writer.close()

    missing_inventory_members: list[dict[str, Any]] = []
    row_count_mismatches: list[dict[str, Any]] = []
    for member, declared in inventory.items():
        actual = actual_rows_by_member.get(member, 0)
        expected = declared["row_count"]
        if member not in actual_rows_by_member:
            missing_inventory_members.append(
                {
                    "filename": member,
                    "declared_rows": expected,
                    "requested_start": declared["start"],
                    "requested_end": declared["end"],
                }
            )
        if actual != expected:
            row_count_mismatches.append(
                {"filename": member, "declared_rows": expected, "actual_rows": actual}
            )
    if row_count_mismatches:
        bronze_tmp.unlink(missing_ok=True)
        silver_tmp.unlink(missing_ok=True)
        raise ValueError(
            f"{archive_path.name}: source inventory row counts differ: {row_count_mismatches[:5]}"
        )

    bronze_tmp.replace(bronze_path)
    silver_tmp.replace(silver_path)
    duplicates, conflicts = _duplicate_report(silver_path)
    if conflicts:
        raise ValueError(
            f"{archive_path.name}: {conflicts} conflicting observations share a series/date"
        )
    sorted_closes = sorted(price_closes)
    audit = {
        "archive": archive_path.name,
        "universe_id": universe_id,
        "provider": PROVIDER,
        "snapshot_checksum": checksum,
        "source_row_count": total_rows,
        "observation_count": total_rows,
        "distinct_series_count": len(identifier_rows),
        "valid_isin_observation_count": valid_isin_rows,
        "non_isin_observation_count": total_rows - valid_isin_rows,
        "session_date_min": min(session_dates).isoformat() if session_dates else None,
        "session_date_max": max(session_dates).isoformat() if session_dates else None,
        "member_count": len(text_members),
        "duplicate_series_date_rows": duplicates,
        "conflicting_series_date_groups": conflicts,
        "missing_ohlc_rows": missing_ohlc_rows,
        "zero_volume_rows": zero_volume_rows,
        "currency_unknown_rows": total_rows,
        "mic_unknown_rows": total_rows,
        "close_distribution": _distribution(sorted_closes),
        "missing_inventory_members": missing_inventory_members,
        "retrieved_at": captured_at.isoformat(),
        "bronze_path": str(bronze_path.relative_to(data_dir)),
        "silver_path": str(silver_path.relative_to(data_dir)),
        "status": "ingested",
    }
    _write_json(audit_path, audit)
    return audit


def _universe_for(filename: str) -> str:
    stem = Path(filename).stem
    for prefix, universe in _UNIVERSES.items():
        if stem.startswith(prefix):
            return universe
    raise ValueError(f"unsupported ABC Bourse archive name: {filename}")


def _safe_members(archive: zipfile.ZipFile) -> list[str]:
    if len(archive.infolist()) > 256:
        raise ValueError("archive has an unexpected number of members")
    names: list[str] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = Path(info.filename)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError(f"archive contains an unsafe member path: {info.filename!r}")
        if info.file_size > 100 * 1024 * 1024:
            raise ValueError(f"archive member is too large: {info.filename!r}")
        names.append(info.filename)
    return names


def _read_inventory(
    archive: zipfile.ZipFile, inventory_name: str | None
) -> dict[str, dict[str, Any]]:
    if inventory_name is None:
        return {}
    text = archive.read(inventory_name).decode("utf-8-sig", errors="strict")
    rows = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        filename = (row.get("Fichier") or "").strip()
        if not filename:
            continue
        result[filename] = {
            "row_count": int(row.get("Lignes") or 0),
            "start": row.get("Début demandé"),
            "end": row.get("Fin demandée"),
            "first_observation": row.get("Première cotation"),
            "last_observation": row.get("Dernière cotation"),
        }
    return result


def _audit_inventory(
    inventory: dict[str, dict[str, Any]], text_members: list[str]
) -> dict[str, Any]:
    member_set = set(text_members)
    missing = [
        {"filename": name, **details}
        for name, details in inventory.items()
        if name not in member_set
    ]
    return {
        "inventory_file_count": len(inventory),
        "text_member_count": len(text_members),
        "missing_members": missing,
        "declared_rows": sum(item["row_count"] for item in inventory.values()),
    }


def _parse_number(value: str, *, archive: str, member: str, line: int) -> float | None:
    raw = value.strip().replace("\u00a0", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raise ValueError(f"{archive}:{member}:{line}: ambiguous number {value!r}")
    try:
        number = Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"{archive}:{member}:{line}: invalid number {value!r}") from exc
    result = float(number)
    if not number.is_finite() or not math.isfinite(result):
        raise ValueError(f"{archive}:{member}:{line}: non-finite number {value!r}")
    return result


def _valid_isin(value: str) -> bool:
    if (
        len(value) != 12
        or not value[:2].isalpha()
        or not value[-1].isdigit()
        or not value.isalnum()
    ):
        return False
    expanded = "".join(str(int(char, 36)) if char.isalpha() else char for char in value.upper())
    total = 0
    for index, char in enumerate(reversed(expanded)):
        digit = int(char)
        if index % 2:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return total % 10 == 0


def _write_batch(
    writer: pq.ParquetWriter,
    rows: list[dict[str, Any]],
    schema: pa.Schema,
) -> None:
    if rows:
        writer.write_table(pa.Table.from_pylist(rows, schema=schema))


def _duplicate_report(path: Path) -> tuple[int, int]:
    quoted = "'" + path.as_posix().replace("'", "''") + "'"
    query = f"""
        SELECT count(*) - count(DISTINCT (series_id, session_date)) AS duplicates
        FROM read_parquet({quoted})
    """
    conflicts_query = f"""
        SELECT count(*) FROM (
            SELECT series_id, session_date
            FROM read_parquet({quoted})
            GROUP BY series_id, session_date
            HAVING count(DISTINCT struct_pack(
                open := open, high := high, low := low, close := close, volume := volume
            )) > 1
        )
    """
    with duckdb.connect(":memory:") as connection:
        duplicate_row = connection.execute(query).fetchone()
        conflict_row = connection.execute(conflicts_query).fetchone()
        assert duplicate_row is not None and conflict_row is not None
        duplicates = int(duplicate_row[0])
        conflicts = int(conflict_row[0])
    return duplicates, conflicts


def _distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p50": None, "p95": None, "max": None}
    return {
        "min": values[0],
        "p50": values[round((len(values) - 1) * 0.5)],
        "p95": values[round((len(values) - 1) * 0.95)],
        "max": values[-1],
    }


def _combined_audit(archives: list[dict[str, Any]]) -> dict[str, Any]:
    universes: dict[str, dict[str, int]] = {}
    for row in archives:
        universe = row["universe_id"]
        group = universes.setdefault(universe, {"archive_count": 0, "observations": 0})
        group["archive_count"] += 1
        group["observations"] += int(row.get("observation_count", 0))
    return {
        "provider": PROVIDER,
        "source_url": SOURCE_URL,
        "archive_count": len(archives),
        "ingested_archive_count": sum(row.get("status") == "ingested" for row in archives),
        "archived_only_count": sum(row.get("status") == "archived_only" for row in archives),
        "observation_count": sum(int(row.get("observation_count", 0)) for row in archives),
        "universes": universes,
        "archives": archives,
        "availability_rule": "session date + 1 day at 00:00 Europe/Paris",
        "unknown_metadata_policy": "currency and MIC remain null unless explicitly supplied",
    }


def _refresh_series_views(db_path: Path, silver_root: Path) -> None:
    parquet_paths = sorted(path.resolve() for path in silver_root.glob("*/*.parquet"))
    if not parquet_paths:
        return
    values = ", ".join("'" + path.as_posix().replace("'", "''") + "'" for path in parquet_paths)
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            f"CREATE OR REPLACE VIEW market_series_history AS "
            f"SELECT * FROM read_parquet([{values}], union_by_name=true)"
        )
        connection.execute("""
            CREATE OR REPLACE VIEW market_series AS
            SELECT * EXCLUDE (revision_rank)
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY universe_id, series_id, session_date
                    ORDER BY retrieved_at DESC, snapshot_checksum DESC
                ) AS revision_rank
                FROM market_series_history
            ) WHERE revision_rank = 1
        """)


def _store_immutable(payload: bytes, path: Path, checksum_hex: str) -> None:
    if path.exists():
        existing_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing_checksum != checksum_hex:
            raise ValueError(f"content-addressed raw archive conflicts: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)
