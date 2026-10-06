"""CLI for independent single-index time-series models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hocus_quant.analysis.index_series_models import prepare, publish, run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "publish"])
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/index_series_v1.toml")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    action = {"prepare": prepare, "run": run, "publish": publish}[args.action]
    print(json.dumps(action(root, args.config), indent=2))


if __name__ == "__main__":
    main()
