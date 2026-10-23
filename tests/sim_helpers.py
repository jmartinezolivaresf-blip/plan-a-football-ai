"""Shared helpers for simulator tests."""

from __future__ import annotations

import json
from functools import cache

import numpy as np

from contracts import Levers, Plan, Squads
from contracts.eval_only import Truth
from sim import simulate
from sim.core import Batch
from sim.world import compile_world

from .conftest import FIXTURES

ON_BALL = {"pass", "long_ball", "cross", "carry", "shot", "goal_kick", "corner", "kick_off", "throw_in"}


@cache
def squads() -> Squads:
    return Squads.model_validate(json.loads((FIXTURES / "squads_fixture.json").read_text()))


@cache
def fixture_plans_json() -> dict:
    return json.loads((FIXTURES / "plans_fixture.json").read_text())["plans"]


def plans(**overrides) -> dict[str, Plan]:
    """Fixture plans (KES home). overrides: {"KES": {...plan fields...}}."""
    out = {}
    for code, data in fixture_plans_json().items():
        plan = Plan.model_validate(data)
        if code in overrides:
            plan = plan.model_copy(update=overrides[code])
        out[code] = plan
    return out


def plain_plans(kes: dict | None = None, har: dict | None = None) -> dict[str, Plan]:
    """Fixture plans with given levers and no Plan B / subs (for clean statistical comparisons)."""
    base = {"plan_b": [], "subs_plan": [], "lever_evidence": {}}
    return plans(KES={**base, "levers": Levers(**(kes or {}))}, HAR={**base, "levers": Levers(**(har or {}))})


@cache
def truth() -> Truth:
    return Truth.model_validate(json.loads((FIXTURES / "eval_only" / "truth_fixture.json").read_text()))


@cache
def logged_match(seed: int):
    return simulate(plans(), squads(), seed=seed, R=1, log=True, truth=truth())


def batch(p: dict[str, Plan], R: int, seed: int, with_truth: bool = True, debug: bool = False):
    b = Batch(compile_world(p, squads(), truth() if with_truth else None), R, seed, debug=debug).fresh()
    return b, b.run(90)


def points(score: np.ndarray, team: int) -> np.ndarray:
    a, b = score[:, team], score[:, 1 - team]
    return np.where(a > b, 3.0, np.where(a == b, 1.0, 0.0))
