"""Build SPEC-006T locally; preserves all prior scans and performs no acquisition."""

from __future__ import annotations

import argparse
from pathlib import Path

from hocus_quant.analysis.ex_ante import run_research_contract

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/analysis/spec006t-ex-ante")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/research/spec006t.json")
    args = parser.parse_args()
    audit = run_research_contract(root=ROOT, output=args.output, config_path=args.config)
    print(audit["status"])


if __name__ == "__main__":
    main()
