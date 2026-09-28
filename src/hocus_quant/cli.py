"""Command-line entry points."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from hocus_quant.ingestion.pipeline import ingest_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(prog="hocus-quant")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest-fixture")
    ingest_parser.add_argument("snapshot", type=Path)
    ingest_parser.add_argument(
        "--data-dir", type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    amf_parser = subparsers.add_parser("ingest-amf")
    amf_parser.add_argument("snapshot", type=Path)
    amf_parser.add_argument(
        "--data-dir", type=Path,
        default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data")),
    )
    args = parser.parse_args()
    if args.command == "ingest-fixture":
        for stage, path in ingest_snapshot(args.snapshot, args.data_dir).items():
            print(f"{stage}: {path}")
    elif args.command == "ingest-amf":
        from hocus_quant.ingestion.amf import ingest_amf_snapshot

        for stage, path in ingest_amf_snapshot(args.snapshot, args.data_dir).items():
            print(f"{stage}: {path}")


if __name__ == "__main__":
    main()
