"""Command-line entry points."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from hocus_quant.ingestion.pipeline import ingest_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(prog="hocus-quant")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest-fixture")
    ingest_parser.add_argument("snapshot", type=Path)
    ingest_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    amf_parser = subparsers.add_parser("ingest-amf")
    amf_parser.add_argument("snapshot", type=Path)
    amf_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    market_parser = subparsers.add_parser("ingest-market")
    market_parser.add_argument("snapshot", type=Path)
    market_parser.add_argument("--gremlin-artifact-root", type=Path, required=True)
    market_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    archive_parser = subparsers.add_parser(
        "ingest-market-archives",
        help="archive and normalize manually delivered ABC Bourse universe ZIPs",
    )
    archive_parser.add_argument("archive_dir", type=Path)
    archive_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    labels_parser = subparsers.add_parser(
        "ingest-instrument-labels",
        help="ingest the ABC Bourse instrument label workbook",
    )
    labels_parser.add_argument("workbook", type=Path)
    labels_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    features_parser = subparsers.add_parser(
        "build-feature-snapshot", help="build a point-in-time cross-sectional feature snapshot"
    )
    features_parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    features_parser.add_argument("--output", type=Path, required=True)
    features_parser.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data"))
    )
    features_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "ingest-fixture":
        for stage, path in ingest_snapshot(args.snapshot, args.data_dir).items():
            print(f"{stage}: {path}")
    elif args.command == "ingest-amf":
        from hocus_quant.ingestion.amf import ingest_amf_snapshot

        for stage, path in ingest_amf_snapshot(args.snapshot, args.data_dir).items():
            print(f"{stage}: {path}")
    elif args.command == "ingest-market":
        from hocus_quant.ingestion.market import ingest_market_snapshot

        outputs = ingest_market_snapshot(
            args.snapshot,
            gremlin_artifact_root=args.gremlin_artifact_root,
            data_dir=args.data_dir,
        )
        for stage, path in outputs.items():
            print(f"{stage}: {path}")
    elif args.command == "ingest-market-archives":
        import json

        from hocus_quant.ingestion.market_archives import ingest_market_archives

        report = ingest_market_archives(args.archive_dir, data_dir=args.data_dir)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.command == "ingest-instrument-labels":
        import json

        from hocus_quant.ingestion.instrument_labels import ingest_instrument_labels

        report = ingest_instrument_labels(args.workbook, data_dir=args.data_dir)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.command == "build-feature-snapshot":
        import json

        from hocus_quant.features.snapshot import build_feature_snapshot

        report = build_feature_snapshot(
            as_of_date=args.as_of,
            output_dir=args.output,
            data_dir=args.data_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
