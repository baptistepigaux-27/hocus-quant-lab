"""Prepare a confirmation request against the immutable lock; compute no results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hocus_quant.analysis.candidate_lock import prepare_confirmation
from hocus_quant.features.registry import registry_document

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-cutoff", required=True)
    parser.add_argument(
        "--lock", type=Path, default=ROOT / "configs/research/candidate_lock_v1.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text())
    request = prepare_confirmation(
        lock,
        first_cutoff=args.first_cutoff,
        feature_registry_sha256=str(registry_document()["sha256"]),
        last_development_outcome_date=lock["contract"]["data_observed_through"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, indent=2) + "\n")
    print(request["status"])


if __name__ == "__main__":
    main()
