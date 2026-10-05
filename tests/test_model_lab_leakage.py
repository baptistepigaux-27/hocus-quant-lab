from __future__ import annotations

import json
import subprocess
import tomllib
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from hocus_quant.analysis.confirmation_protocol import SCIENTIFIC_FILES
from hocus_quant.features.factory import compute_entity_features
from hocus_quant.model_lab.data import feature_sets, locked_features, split_assignment

ROOT = Path(__file__).resolve().parents[1]


def test_spec007_and_lock_byte_identical():
    paths = [
        "configs/research/candidate_lock_v1.json",
        "configs/research/confirmation_protocol_v1.toml",
        "configs/research/confirmation_protocol_v1.freeze.json",
        "uv.lock",
        *["src/hocus_quant/" + p for p in SCIENTIFIC_FILES],
    ]
    for path in paths:
        expected = subprocess.check_output(["git", "show", f"429f12e:{path}"], cwd=ROOT)
        assert (ROOT / path).read_bytes() == expected, path


@pytest.mark.parametrize("h", [5, 10])
def test_purge_and_boundary_label_not_universe(h):
    config = tomllib.loads((ROOT / "configs/experiments/model_lab_v1.toml").read_text())
    first = date(2024, 1, 1)
    calendar = [
        first + timedelta(days=i) for i in range(1100) if (first + timedelta(days=i)).weekday() < 5
    ]
    hi = date(2024, 12, 31)
    cutoff = [d for d in calendar if d <= hi][-h - 1]
    assert split_assignment(cutoff, hi, h, calendar, config) == ("train", "accepted")
    later = calendar[calendar.index(cutoff) + 1]
    assert split_assignment(later, hi, h, calendar, config)[0] == "purged"
    split, reason = split_assignment(cutoff, date(2025, 1, 2), h, calendar, config)
    assert split == "train" and "crosses_boundary" in reason
    assert split_assignment(date(2026, 1, 2), date(2026, 1, 20), h, calendar, config)[0] == "test"


def test_locked_subset_formula_parity_and_future_independence():
    lock = json.loads((ROOT / "configs/research/candidate_lock_v1.json").read_text())
    sets = feature_sets(lock)
    assert len(sets["strict"]) == 85 and len(sets["strong"]) == 138
    first = date(2022, 1, 3)
    rng = np.random.default_rng(7)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, 600)))
    rows = [
        {
            "session_date": first + timedelta(days=i),
            "open": v * 0.999,
            "high": v * 1.01,
            "low": v * 0.99,
            "close": v,
            "volume": 1000 + i,
        }
        for i, v in enumerate(closes)
    ]
    full = compute_entity_features(rows)
    subset = locked_features(rows, sets["strong"])
    for feature, value in subset.items():
        if value is None:
            assert full[feature][0] is None
        else:
            assert value == pytest.approx(full[feature][0], abs=1e-12)
    assert len(subset) == 138
    # Caller supplies only past rows: no label parameter exists in this API.
    assert list(__import__("inspect").signature(locked_features).parameters) == ["rows", "ids"]
