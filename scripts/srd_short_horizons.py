"""Prepare and train the isolated stock-only H1/H2/H3 experiment."""

import argparse
import json
from pathlib import Path

from hocus_quant.model_lab.short_horizons import build_data, run_models, settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["data", "run", "publish"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config, output, path = settings(root)
    if args.action == "data":
        result = build_data(root, output, config)
    elif args.action == "run":
        result = run_models(root, output, path)
    else:
        from hocus_quant.model_lab.short_horizon_report import publish

        result = publish(root, output, config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
