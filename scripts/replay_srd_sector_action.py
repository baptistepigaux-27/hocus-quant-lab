"""Replay fixed sector gates with preserved stock/sector models."""

from pathlib import Path

from hocus_quant.model_lab.sector_action import run

if __name__ == "__main__":
    print(
        run(
            Path("configs/experiments/srd_sector_action_v1.json"),
            Path("data/analysis/srd-sector-action-v1"),
        )
    )
