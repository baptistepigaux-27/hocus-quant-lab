"""Fit and document the fixed seven-state SBF120 experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hocus_quant.analysis.sbf120_kmeans import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/experiments/sbf120_kmeans7_v1.toml")
    )
    args = parser.parse_args()
    print(json.dumps(run(Path(__file__).resolve().parents[1], args.config), indent=2))


if __name__ == "__main__":
    main()
