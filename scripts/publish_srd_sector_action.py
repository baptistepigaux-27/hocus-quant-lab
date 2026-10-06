from pathlib import Path

from hocus_quant.model_lab.sector_action_report import publish

if __name__ == "__main__":
    publish(Path("data/analysis/srd-sector-action-v1"))
