"""Every calibrated constant equals the committed result of the script that chose it on DEV data.

If a calibration is re-run and picks something else, these tests fail until the constant is updated (and the change
is recorded in docs/DECISIONS.md). The scripts never read the evaluation seasons.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RESULTS = Path(__file__).resolve().parents[1] / "eval" / "results"


def _load(name: str) -> dict:
    path = RESULTS / name
    assert path.exists(), f"{name} missing: run the calibration that writes it"
    return json.loads(path.read_text())


def test_press_balance_knobs():
    from sim.model import DEFAULT_COEFFICIENTS
    chosen = _load("press_calibration.json")["chosen"]
    for knob in ("long_vs_high_line", "high_press_fatigue_mult", "high_press_cover_scale",
                 "low_block_pressure_scale"):
        assert DEFAULT_COEFFICIENTS[knob] == pytest.approx(chosen[knob]), knob


def test_shot_volume_knob():
    from sim.model import DEFAULT_COEFFICIENTS
    assert DEFAULT_COEFFICIENTS["shot_logit_offset"] == pytest.approx(
        _load("sim_calibration.json")["chosen"]["shot_logit_offset"])


def test_scouting_thresholds():
    from engine.beliefs import RULES
    rules = _load("dev/scouting_thresholds.json")["rules"]
    assert {m: (k, pytest.approx(z)) for m, (k, z) in rules.items()} == dict(RULES)


def test_lever_observation_thresholds():
    from engine import tracker
    t = _load("dev/lever_observation.json")["thresholds"]
    assert list(tracker.PRESS_HIGH_SHARE) == pytest.approx(t["PRESS_HIGH_SHARE"])
    assert list(tracker.LONG_SHARE) == pytest.approx(t["LONG_SHARE"])


def test_opponent_estimate_probabilities():
    from engine.api import ESTIMATE_PROBS
    probs = _load("estimate_calibration.json")["probabilities"]
    for situation, values in probs.items():
        assert ESTIMATE_PROBS[situation] == pytest.approx(values), situation
        assert sum(values) == pytest.approx(1.0, abs=0.01)
