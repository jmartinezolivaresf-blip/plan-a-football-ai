"""Fixture loaders for person B's tests (independent of the simulator branch)."""

from __future__ import annotations

import json
from functools import cache

from contracts import Plan, Squads

from .conftest import FIXTURES


@cache
def squads() -> Squads:
    return Squads.model_validate(json.loads((FIXTURES / "squads_fixture.json").read_text()))


def plans() -> dict[str, Plan]:
    raw = json.loads((FIXTURES / "plans_fixture.json").read_text())["plans"]
    return {k: Plan.model_validate(v) for k, v in raw.items()}
