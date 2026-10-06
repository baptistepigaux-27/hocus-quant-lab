"""Prepare, fit and publish the additive SRD context experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hocus_quant.model_lab.context_data import prepare_context_inputs
from hocus_quant.model_lab.context_experiment import build_enriched_dataset, settings
from hocus_quant.model_lab.context_parallel import run_parallel
from hocus_quant.model_lab.context_producers import produce_context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inputs", "context", "data", "run", "publish"])
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/srd_context_v1.toml")
    )
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config, output = settings(root, args.config)
    if args.action == "inputs":
        result = prepare_context_inputs(root, config, output)
    elif args.action == "context":
        result = produce_context(root, output, config)
    elif args.action == "data":
        result = build_enriched_dataset(root, config, output)
    elif args.action == "run":
        if (output / "summary.json").exists():
            raise ValueError("Completed SRD benchmark exists; use a new experiment version")
        result = run_parallel(root, output / "srd_benchmark.toml", output, args.workers)
    else:
        from hocus_quant.model_lab.context_report import publish

        result = publish(root, output, config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
