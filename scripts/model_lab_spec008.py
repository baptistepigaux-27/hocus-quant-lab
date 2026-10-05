"""SPEC-008 CLI; all outputs live outside SPEC-007."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

from hocus_quant.model_lab.data import build_dataset
from hocus_quant.model_lab.run import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["data", "run", "report"])
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/model_lab_v1.toml")
    )
    parser.add_argument("--output", type=Path, default=Path("data/analysis/spec008-model-lab"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.action == "data":
        result = build_dataset(root, args.output, tomllib.loads(args.config.read_text()))
    elif args.action == "run":
        result = run_benchmark(root, args.config, args.output)
    else:
        from hocus_quant.model_lab.report import render_report

        result = render_report(root, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
