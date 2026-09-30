"""Point-in-time future outcome construction."""

from hocus_quant.targets.factory import build_target_set, build_target_snapshot
from hocus_quant.targets.registry import HORIZONS, target_registry

__all__ = ["HORIZONS", "build_target_set", "build_target_snapshot", "target_registry"]
