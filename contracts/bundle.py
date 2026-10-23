"""match_bundle.json: everything the frontend needs to play the demo with no backend."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .claim import Claim
from .common import Contract, TeamCode
from .cue import Cue
from .duel import Duel
from .events import Event
from .plan import Plan
from .snapshot import Snapshot
from .squads import Squads
from .trace import TraceStep

SCHEMA_VERSION = "0.1.0"


class AttackDirection(Contract):
    period: Literal[1, 2]
    positive_x: TeamCode = Field(description="Team attacking towards x = 105 in this period.")


class MatchMeta(Contract):
    match_id: str
    competition: str = "Synthetic League (fictional)"
    home: TeamCode
    away: TeamCode
    kickoff_label: str
    attack: list[AttackDirection] = Field(min_length=2, max_length=2)
    synthetic: Literal[True] = True
    precomputed: bool = Field(default=True, description="The demo bundle is precomputed; the UI must say so.")


class RenderFrame(Contract):
    """Visual layer only (ball-anchored shapes). No metric is computed from these positions."""

    t: float = Field(ge=0)
    ball: tuple[float, float]
    players: dict[str, tuple[float, float]]


class MatchBundle(Contract):
    schema_version: str = SCHEMA_VERSION
    meta: MatchMeta
    squads: Squads
    events: list[Event]
    snapshots: list[Snapshot]
    render_frames: list[RenderFrame] = Field(default_factory=list)
    plans: dict[TeamCode, Plan]
    duel: Duel | None = None
    claims: list[Claim] = Field(default_factory=list)
    cues: list[Cue] = Field(default_factory=list)
    traces: list[TraceStep] = Field(default_factory=list)
    eval: dict[str, Any] = Field(default_factory=dict, description="Aggregated E1..E8 results for the panel.")
    illustrative: bool = Field(default=False, description="True for fixture bundles (hand-made, not simulated).")
