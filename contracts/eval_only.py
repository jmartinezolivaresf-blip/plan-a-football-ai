"""EVALUATOR-ONLY contracts: hidden truth and simulator configuration.

Never imported by `contracts/__init__.py`, the engine, the MCP server or the agents (tested).
Only `sim/` (to generate) and `eval/` (to score) may import this module.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import Contract, TeamCode

TraitKind = Literal[
    "fb_low_press_resistance",
    "cb_low_pace",
    "back_post_weak",
    "gk_short_bias",
    "late_fade",
    "weak_channel",
]
TRAIT_KINDS: tuple[str, ...] = TraitKind.__args__  # type: ignore[attr-defined]


class HiddenTrait(Contract):
    kind: TraitKind
    player_id: str | None = None
    side: Literal["left", "right"] | None = None
    strength: float = Field(ge=0, le=1)


class TeamTruth(Contract):
    team: TeamCode
    archetype: Literal["pressing", "possession", "direct", "low_block"]
    split: Literal["dev", "test"]
    traits: list[HiddenTrait] = Field(min_length=1, max_length=4)


class Truth(Contract):
    season_id: str
    teams: dict[TeamCode, TeamTruth]


class SimConfig(Contract):
    season_id: str
    seed: int
    coefficients: dict[str, float]
    archetype_ranges: dict[str, dict[str, Any]] = Field(default_factory=dict)
