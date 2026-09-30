"""Import ABC Bourse's code-to-label workbook as versioned reference data."""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SOURCE_ID = "abc_bourse_instrument_labels"
_SCHEMA = pa.schema(
    [
        ("provider_instrument_id", pa.string()),
        ("display_name", pa.string()),
        ("ticker", pa.string()),
        ("variants_for_code", pa.int32()),
        ("historical_selections", pa.string()),
        ("first_session_date", pa.date32()),
        ("last_session_date", pa.date32()),
        ("historical_row_count", pa.int64()),
        ("label_status", pa.string()),
        ("source_sheet", pa.string()),
        ("source_identifier_header", pa.string()),
        ("source_url", pa.string()),
        ("source_download_date", pa.date32()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("snapshot_checksum", pa.string()),
    ]
)


def ingest_instrument_labels(
    workbook_path: Path,
    *,
    data_dir: Path,
    retrieved_at: datetime | None = None,
) -> dict[str, Any]:
    """Archive, parse and expose the supplied ABC Bourse label workbook."""
    captured_at = retrieved_at or datetime.now(UTC)
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)
    payload = workbook_path.read_bytes()
    checksum_hex = hashlib.sha256(payload).hexdigest()
    checksum = f"sha256:{checksum_hex}"

    raw_path = data_dir / "raw" / "instrument_labels" / "sha256" / f"{checksum_hex}.xlsx"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != checksum_hex:
            raise ValueError(f"content-addressed workbook conflicts: {raw_path}")
    else:
        _write_bytes_immutable(raw_path, payload)

    tables = _read_workbook(payload)
    summary = _key_value_rows(tables["Bilan"])
    source_url = summary.get("Source des libellés", "https://www.abcbourse.com/download/libelles")
    source_download_date = _as_date(summary.get("Téléchargement des libellés"))
    correspondence_rows = _records(
        tables["Correspondances"],
        [
            "ISIN",
            "Nom ABC Bourse",
            "Ticker",
            "Variantes pour ISIN",
            "Sélections historiques",
            "Première cotation",
            "Dernière cotation",
            "Lignes historiques",
        ],
    )
    unlabeled_rows = _records(
        tables["Sans libellé"],
        [
            "ISIN",
            "Sélections historiques",
            "Première cotation",
            "Dernière cotation",
            "Lignes historiques",
        ],
    )

    variant_counts: dict[str, int] = {}
    for record in correspondence_rows:
        code = _required(record, "ISIN")
        variant_counts[code] = variant_counts.get(code, 0) + 1

    silver_rows: list[dict[str, Any]] = []
    for record in correspondence_rows:
        code = _required(record, "ISIN")
        silver_rows.append(
            {
                "provider_instrument_id": code,
                "display_name": _optional(record, "Nom ABC Bourse"),
                "ticker": _optional(record, "Ticker"),
                "variants_for_code": variant_counts[code],
                "historical_selections": _optional(record, "Sélections historiques"),
                "first_session_date": _as_date(_optional(record, "Première cotation")),
                "last_session_date": _as_date(_optional(record, "Dernière cotation")),
                "historical_row_count": _as_int(_optional(record, "Lignes historiques")),
                "label_status": "labeled",
                "source_sheet": "Correspondances",
                "source_identifier_header": "ISIN",
                "source_url": source_url,
                "source_download_date": source_download_date,
                "retrieved_at": captured_at,
                "snapshot_checksum": checksum,
            }
        )
    for record in unlabeled_rows:
        silver_rows.append(
            {
                "provider_instrument_id": _required(record, "ISIN"),
                "display_name": None,
                "ticker": None,
                "variants_for_code": 0,
                "historical_selections": _optional(record, "Sélections historiques"),
                "first_session_date": _as_date(_optional(record, "Première cotation")),
                "last_session_date": _as_date(_optional(record, "Dernière cotation")),
                "historical_row_count": _as_int(_optional(record, "Lignes historiques")),
                "label_status": "no_current_label",
                "source_sheet": "Sans libellé",
                "source_identifier_header": "ISIN",
                "source_url": source_url,
                "source_download_date": source_download_date,
                "retrieved_at": captured_at,
                "snapshot_checksum": checksum,
            }
        )

    declared_codes = _as_int(summary.get("Codes distincts dans les cotations"))
    label_codes = len(variant_counts)
    missing_codes = len(
        {
            row["provider_instrument_id"]
            for row in silver_rows
            if row["label_status"] == "no_current_label"
        }
    )
    all_codes = {row["provider_instrument_id"] for row in silver_rows}
    if declared_codes is not None and len(all_codes) != declared_codes:
        raise ValueError(
            "label workbook code coverage mismatch: "
            f"declared {declared_codes}, found {len(all_codes)}"
        )

    bronze_root = data_dir / "bronze" / "instrument_labels"
    silver_root = data_dir / "silver" / "instrument_labels"
    bronze_root.mkdir(parents=True, exist_ok=True)
    silver_root.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_root / f"{checksum_hex}.parquet"
    silver_path = silver_root / f"{checksum_hex}.parquet"
    _write_parquet_once(bronze_path, silver_rows)
    _write_parquet_once(silver_path, silver_rows)

    capture_id = f"capture-{uuid.uuid4().hex}"
    capture = {
        "source_id": SOURCE_ID,
        "source_url": source_url,
        "retrieved_at": captured_at.isoformat(),
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "checksum": checksum,
        "payload_path": str(raw_path.relative_to(data_dir)),
        "original_filename": workbook_path.name,
        "capture_id": capture_id,
        "metadata": {
            "acquisition_mode": "user_supplied_workbook",
            "source_download_date": source_download_date.isoformat()
            if source_download_date
            else None,
        },
    }
    _write_json(data_dir / "raw" / "instrument_labels" / "captures" / f"{capture_id}.json", capture)

    audit = {
        "source_id": SOURCE_ID,
        "source_url": source_url,
        "source_download_date": source_download_date.isoformat() if source_download_date else None,
        "snapshot_checksum": checksum,
        "declared_distinct_codes": declared_codes,
        "distinct_codes_in_workbook": len(all_codes),
        "codes_with_labels": label_codes,
        "codes_without_current_label": missing_codes,
        "label_variants": len(correspondence_rows),
        "codes_with_multiple_variants": sum(count > 1 for count in variant_counts.values()),
        "unlabeled_rows": len(unlabeled_rows),
        "source_sheets": sorted(tables),
        "bronze_path": str(bronze_path.relative_to(data_dir)),
        "silver_path": str(silver_path.relative_to(data_dir)),
        "raw_path": str(raw_path.relative_to(data_dir)),
        "capture_id": capture_id,
        "status": "ingested",
    }
    audit_path = silver_root / f"audit-{checksum_hex}.json"
    _write_json(audit_path, audit)
    _refresh_label_views(data_dir / "research.duckdb", silver_root)
    return {**audit, "audit_path": str(audit_path)}


def _read_workbook(payload: bytes) -> dict[str, list[list[str | None]]]:
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as archive:
        names = set(archive.namelist())
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation_targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
        }
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(text.text or "" for text in item.findall(f".//{{{_MAIN_NS}}}t"))
                for item in strings.findall(f"{{{_MAIN_NS}}}si")
            ]
        result: dict[str, list[list[str | None]]] = {}
        for sheet in workbook.findall(f".//{{{_MAIN_NS}}}sheet"):
            title = sheet.attrib["name"]
            relation_id = sheet.attrib[f"{{{_DOC_REL_NS}}}id"]
            target = relation_targets[relation_id]
            path = (
                target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
            )
            path = str(PurePosixPath(path))
            root = ET.fromstring(archive.read(path))
            rows: list[list[str | None]] = []
            for row in root.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"):
                values: dict[int, str | None] = {}
                for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                    column = _column_index(cell.attrib["r"])
                    kind = cell.attrib.get("t")
                    value: str | None
                    if kind == "inlineStr":
                        value = "".join(
                            text.text or "" for text in cell.findall(f".//{{{_MAIN_NS}}}t")
                        )
                    else:
                        value = cell.findtext(f"{{{_MAIN_NS}}}v")
                        if value is not None and kind == "s":
                            value = shared_strings[int(value)]
                    values[column] = value
                width = max(values, default=-1) + 1
                rows.append([values.get(index) for index in range(width)])
            result[title] = rows
        for expected in ("Bilan", "Correspondances", "Sans libellé"):
            if expected not in result:
                raise ValueError(f"label workbook is missing sheet {expected!r}")
        return result


def _column_index(reference: str) -> int:
    result = 0
    for char in reference:
        if not char.isalpha():
            break
        result = result * 26 + ord(char.upper()) - ord("A") + 1
    return result - 1


def _records(
    rows: list[list[str | None]], expected_headers: list[str]
) -> list[dict[str, str | None]]:
    if not rows:
        raise ValueError("label workbook sheet is empty")
    headers = rows[0]
    if headers[: len(expected_headers)] != expected_headers:
        raise ValueError(f"unexpected label workbook headers: {headers}")
    return [
        {
            header: row[index] if index < len(row) else None
            for index, header in enumerate(expected_headers)
        }
        for row in rows[1:]
        if row and any(value not in (None, "") for value in row)
    ]


def _key_value_rows(rows: list[list[str | None]]) -> dict[str, str]:
    return {row[0]: row[1] for row in rows[1:] if len(row) > 1 and row[0] and row[1]}


def _required(row: dict[str, str | None], key: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        raise ValueError(f"label workbook row has an empty {key!r}")
    return value.strip()


def _optional(row: dict[str, str | None], key: str) -> str | None:
    value = row.get(key)
    return value.strip() if value and value.strip() else None


def _as_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _as_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(float(value))


def _write_parquet_once(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        return
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=_SCHEMA), temporary, compression="zstd")
    temporary.replace(path)


def _refresh_label_views(db_path: Path, silver_root: Path) -> None:
    paths = sorted(path.resolve() for path in silver_root.glob("*.parquet"))
    values = ", ".join("'" + path.as_posix().replace("'", "''") + "'" for path in paths)
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            "CREATE OR REPLACE VIEW instrument_labels_history AS "
            f"SELECT * FROM read_parquet([{values}], union_by_name=true)"
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW instrument_labels_by_code AS
            WITH latest_snapshot AS (
                SELECT max(retrieved_at) AS retrieved_at
                FROM instrument_labels_history
            )
            SELECT history.provider_instrument_id,
                   string_agg(DISTINCT display_name, ' / ' ORDER BY display_name)
                       FILTER (WHERE history.display_name IS NOT NULL) AS display_name,
                   string_agg(DISTINCT history.ticker, ' / ' ORDER BY history.ticker)
                       FILTER (WHERE history.ticker IS NOT NULL) AS ticker,
                   string_agg(
                       DISTINCT history.historical_selections,
                       ', ' ORDER BY history.historical_selections
                   ) FILTER (WHERE history.historical_selections IS NOT NULL)
                       AS historical_selections,
                   count(*) FILTER (WHERE history.label_status = 'labeled')
                       AS label_variant_count,
                   bool_or(history.label_status = 'labeled') AS has_current_label,
                   min(history.first_session_date) AS first_session_date,
                   max(history.last_session_date) AS last_session_date
            FROM instrument_labels_history AS history
            JOIN latest_snapshot USING (retrieved_at)
            GROUP BY history.provider_instrument_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW market_series_with_labels AS
            SELECT series.*, labels.display_name, labels.ticker,
                   labels.historical_selections, labels.label_variant_count,
                   labels.has_current_label, labels.first_session_date,
                   labels.last_session_date AS label_last_session_date
            FROM market_series AS series
            LEFT JOIN instrument_labels_by_code AS labels
              ON labels.provider_instrument_id = series.provider_instrument_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW market_daily_with_labels AS
            SELECT market.*, labels.display_name, labels.ticker,
                   labels.historical_selections, labels.label_variant_count,
                   labels.has_current_label
            FROM market_daily AS market
            LEFT JOIN instrument_labels_by_code AS labels
              ON labels.provider_instrument_id = market.isin
            """
        )


def _write_bytes_immutable(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(path)
