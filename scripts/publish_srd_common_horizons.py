from pathlib import Path

from hocus_quant.model_lab.common_replay_report import publish

if __name__ == "__main__":
    publish(Path("data/analysis/srd-horizon-common-replay-v1"))
