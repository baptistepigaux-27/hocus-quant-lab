"""Initialize, register prospectively, or advance the frozen SPEC-007 confirmation."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from hocus_quant.analysis.confirmation import mature_pending, rebuild_monitor, register_cutoff

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "register", "advance", "monitor"])
    parser.add_argument("--cutoff", type=date.fromisoformat)
    parser.add_argument("--database", type=Path, default=ROOT / "data/research.duckdb")
    parser.add_argument("--output", type=Path, default=ROOT / "data/analysis/spec007-confirmation")
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs/research/confirmation_protocol_v1.toml"
    )
    args = parser.parse_args()
    common = {"root": ROOT, "config": args.config, "output": args.output}
    if args.action == "register":
        if args.cutoff is None:
            parser.error("register requires --cutoff")
        result = register_cutoff(**common, database=args.database, cutoff=args.cutoff)
    elif args.action == "advance":
        result = {"completed_cutoffs": mature_pending(**common, database=args.database)}
    else:
        result = rebuild_monitor(**common)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
