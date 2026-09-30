"""Command-line entry points."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path
from typing import Literal

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
    features_parser.add_argument(
        "--quality-scope",
        choices=("all", "approved"),
        default="all",
        help="include every technically usable series or only quality-approved series",
    )
    cube_parser = subparsers.add_parser(
        "build-feature-cube", help="build a PIT historical cube from SPEC-003 slices"
    )
    cube_parser.add_argument("--output", type=Path, required=True)
    cube_parser.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data"))
    )
    cube_parser.add_argument("--dates", type=str)
    cube_parser.add_argument("--start", type=date.fromisoformat)
    cube_parser.add_argument("--end", type=date.fromisoformat)
    cube_parser.add_argument("--cadence", choices=("explicit", "weekly", "daily"), default="weekly")
    cube_parser.add_argument("--quality-scope", choices=("approved", "all"), default="approved")
    cube_parser.add_argument("--resume", action="store_true")
    cube_parser.add_argument("--force", action="store_true")
    cube_parser.add_argument("--dry-run", action="store_true")
    cube_audit_parser = subparsers.add_parser(
        "audit-feature-cube", help="rebuild the temporal audit for an existing cube"
    )
    cube_audit_parser.add_argument("cube_dir", type=Path)
    export_parser = subparsers.add_parser(
        "export-feature-panel", help="export a filtered wide feature matrix from the cube"
    )
    export_parser.add_argument("cube_dir", type=Path)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--start", type=date.fromisoformat)
    export_parser.add_argument("--end", type=date.fromisoformat)
    export_parser.add_argument("--family", action="append", dest="families")
    export_parser.add_argument("--feature", action="append", dest="feature_ids")
    export_parser.add_argument("--entity", action="append", dest="entity_ids")
    export_parser.add_argument("--minimum-coverage", type=float)
    target_parser = subparsers.add_parser(
        "build-target-snapshot", help="build future outcomes for one point-in-time cutoff"
    )
    target_parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    target_parser.add_argument("--output", type=Path, required=True)
    target_parser.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data"))
    )
    target_parser.add_argument("--quality-scope", choices=("approved",), default="approved")
    target_parser.add_argument("--entity", action="append", dest="entity_ids")
    target_set_parser = subparsers.add_parser(
        "build-target-set", help="build targets for each cutoff in a SPEC-004 feature cube"
    )
    target_set_parser.add_argument("--feature-cube", type=Path, required=True)
    target_set_parser.add_argument("--output", type=Path, required=True)
    target_set_parser.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("HOCUS_QUANT_DATA_DIR", "data"))
    )
    target_set_parser.add_argument("--resume", action="store_true")
    target_set_parser.add_argument("--force", action="store_true")
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
            quality_scope=args.quality_scope,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.command == "build-feature-cube":
        import json

        from hocus_quant.features.cube import build_feature_cube

        explicit_dates = (
            [date.fromisoformat(item.strip()) for item in args.dates.split(",")]
            if args.dates
            else None
        )
        cadence: Literal["explicit", "weekly", "daily"] = (
            "explicit" if explicit_dates is not None else args.cadence
        )
        report = build_feature_cube(
            output_dir=args.output,
            data_dir=args.data_dir,
            dates=explicit_dates,
            start=args.start,
            end=args.end,
            cadence=cadence,
            quality_scope=args.quality_scope,
            resume=args.resume,
            force=args.force,
            dry_run=args.dry_run,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.command == "audit-feature-cube":
        import json

        from hocus_quant.features.cube import audit_feature_cube

        print(
            json.dumps(
                audit_feature_cube(args.cube_dir), ensure_ascii=False, sort_keys=True, indent=2
            )
        )
    elif args.command == "export-feature-panel":
        from hocus_quant.features.cube import export_feature_panel

        frame = export_feature_panel(
            args.cube_dir,
            start=args.start,
            end=args.end,
            families=args.families,
            feature_ids=args.feature_ids,
            minimum_coverage=args.minimum_coverage,
            entity_ids=args.entity_ids,
            output_path=args.output,
        )
        print(f"rows={frame.height} columns={frame.width} output={args.output}")
    elif args.command == "build-target-snapshot":
        import json

        from hocus_quant.targets.factory import build_target_snapshot

        report = build_target_snapshot(
            as_of_date=args.as_of,
            output_dir=args.output,
            data_dir=args.data_dir,
            quality_scope=args.quality_scope,
            eligible_entity_ids=set(args.entity_ids) if args.entity_ids else None,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    elif args.command == "build-target-set":
        import json

        from hocus_quant.targets.factory import build_target_set

        report = build_target_set(
            feature_cube_dir=args.feature_cube,
            output_dir=args.output,
            data_dir=args.data_dir,
            resume=args.resume,
            force=args.force,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
