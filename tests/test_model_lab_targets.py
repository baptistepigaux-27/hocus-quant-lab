from __future__ import annotations

import numpy as np
import pytest

from hocus_quant.model_lab.targets import future_path, registry_document
from hocus_quant.targets.registry import target_registry_document


@pytest.mark.parametrize(
    "moves,expected",
    [
        ([0.07, -0.03, 0, 0, 0], 0.04),
        ([0.04, -0.09, 0, 0, 0], -0.05),
        ([0.10, -0.10, 0, 0, 0], 0),
        ([0.10, -0.01, 0, 0, 0], 0.09),
    ],
)
def test_excursion_examples(moves, expected):
    result = future_path(100, 100 * (1 + np.array(moves)), 5)
    assert result["excursion_balance"] == pytest.approx(expected)


@pytest.mark.parametrize("h", [5, 10])
def test_monotone_scaling_horizon(h):
    up = np.arange(101, 101 + h, dtype=float)
    down = np.arange(99, 99 - h, -1, dtype=float)
    a, b = future_path(100, up, h), future_path(100, down, h)
    assert a["excursion_balance"] > 0 and b["excursion_balance"] < 0
    assert a["trend_tstat"] == 1e6 and b["trend_tstat"] == -1e6
    assert future_path(1000, up * 10, h) == pytest.approx(a)
    assert future_path(100, np.r_[up, 99999], h) == a
    assert future_path(100, [100] * h, h)["trend_tstat"] == 0
    assert future_path(100, up[:-1], h)["return_abs"] is None


def test_oscillating_and_non_amplitude():
    r = future_path(100, [110, 90, 110, 90, 110], 5)
    assert abs(r["trend_tstat"]) < 1e-10
    assert r["excursion_balance"] == pytest.approx(0)
    assert r["max_upside"] - r["max_downside"] == pytest.approx(0.2)


def test_additive_registry_keeps_legacy():
    old = target_registry_document()
    new = registry_document()
    assert new["parent_sha256"] == old["sha256"]
    ids = {r["target_id"] for r in new["definitions"]}
    assert len(ids) == 49
    for family in ["excursion_balance", "trend_tstat"]:
        assert {f"future.{family}.h{h}.v1" for h in [5, 10]} <= ids
    assert old == target_registry_document()
