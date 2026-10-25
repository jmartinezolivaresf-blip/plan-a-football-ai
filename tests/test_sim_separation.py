"""The simulator uses hidden truth internally but never leaks it."""

from __future__ import annotations

import json

import numpy as np

from contracts.eval_only import TRAIT_KINDS, SimConfig
from contracts.sim_types import MatchState, Outcomes, SimResult
from sim import fork, simulate
from sim.model import DEFAULT_COEFFICIENTS

from .sim_helpers import batch, plain_plans, plans, squads, truth

FORBIDDEN_FIELDS = {"truth", "traits", "trait", "archetype", "coefficients", "strength", "hidden"}


def _blob(obj) -> str:
    return json.dumps(obj.model_dump(mode="json"))


def test_public_sim_types_have_no_truth_fields():
    for model in (MatchState, Outcomes, SimResult):
        schema = json.dumps(model.model_json_schema())
        for name in FORBIDDEN_FIELDS:
            assert f'"{name}"' not in schema, (model.__name__, name)


def test_outputs_never_contain_traits_or_config():
    config = SimConfig(season_id="s", seed=1, coefficients={"slow_cb_bonus": 0.913579})
    res = simulate(plans(), squads(), seed=3, R=1, log=True, truth=truth(), config=config)
    blob = _blob(res)
    for kind in TRAIT_KINDS:
        assert kind not in blob
    assert "0.913579" not in blob
    for key in DEFAULT_COEFFICIENTS:
        assert f'"{key}"' not in blob
    ht = simulate(plans(), squads(), seed=3, R=1, log=True, until_minute=45, truth=truth()).final_state
    out = fork(ht, {}, R=20, seed=1, truth=truth())
    for kind in TRAIT_KINDS:
        assert kind not in _blob(out) and kind not in _blob(ht)


def test_truth_changes_the_simulation():
    """Hidden traits are really used: the weak left-back loses the ball more often with truth than without."""
    p = plain_plans(kes={"press_height": "high", "press_target": "HAR-5"}, har={"build_up": "short"})
    _, with_t = batch(p, 400, 2, with_truth=True)
    _, without = batch(p, 400, 2, with_truth=False)
    lb = 4  # HAR-5 roster index
    assert with_t.losses_by_player[:, 1, lb].mean() > 1.2 * without.losses_by_player[:, 1, lb].mean()


def test_events_carry_no_secret_parameters():
    res = simulate(plans(), squads(), seed=4, R=1, log=True, truth=truth())
    allowed = set(type(res.events[0]).model_fields)
    for e in res.events:
        assert set(e.model_dump()) <= allowed
    assert not np.isnan([e.x for e in res.events]).any()
