"""Replay preserved SRD forecasts on the fixed common cutoff inventory."""

from pathlib import Path

from hocus_quant.model_lab.common_replay import run

if __name__ == "__main__":
    print(
        run(
            Path("configs/experiments/srd_horizon_common_replay_v1.json"),
            Path("data/analysis/srd-horizon-common-replay-v1"),
        )
    )
