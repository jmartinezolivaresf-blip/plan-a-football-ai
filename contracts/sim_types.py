"""Types crossing the simulator <-> engine boundary (see contracts/sim_api.md). Owner: person A.

MatchState is everything needed to continue (fork) a match EXACTLY. It holds public match information
(plans, squads, score, levers) plus sim-internal dynamics (fatigue, counters, RNG position). It never holds
hidden truth (`contracts.eval_only`): the simulator receives truth separately (D-019).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, TeamCode
from .events import Event
from .plan import Levers, Plan
from .snapshot import Snapshot
from .squads import Squads


class TeamDynamics(Contract):
    """Sim-internal per-team state needed for an exact continuation."""

    used_players: list[str] = Field(default_factory=list, description="Everyone who has been on the pitch.")
    plan_b_fired: list[int] = Field(default_factory=list, description="Indices of Plan B rules already fired.")
    subs_plan_done: list[int] = Field(default_factory=list, description="Indices of subs_plan entries executed.")
    pending_subs: list[tuple[str, str]] = Field(default_factory=list, description="(out, in) at next stoppage.")
    pending_window: bool = Field(default=False, description="Pending subs consume an in-play window.")
    counters: dict[str, float] = Field(default_factory=dict, description="Sim-side KPI counters.")


class MatchState(Contract):
    """Everything needed to fork a match: score, clock, levers, players, fatigue and the RNG position."""

    match_id: str
    minute: int = Field(ge=0, le=90)
    snapshot: Snapshot
    levers: dict[TeamCode, Levers]
    fatigue: dict[str, float] = Field(description="player_id -> simulator stamina 0..1 (sim-internal).")
    rng_step: int = Field(ge=0, description="Step counter so forks consume the same uniforms (CRN).")
    # Added by D-019 (all sim-internal, needed for an exact continuation)
    home: TeamCode
    away: TeamCode
    plans: dict[TeamCode, Plan]
    squads: Squads
    t: float = Field(ge=0, le=5400)
    period: Literal[1, 2]
    possession: TeamCode
    carrier: str = Field(description="player_id on the ball.")
    ball: tuple[float, float]
    counter_until: float = Field(default=0.0, description="Counter-attack window end (match seconds).")
    after_cross: bool = False
    dynamics: dict[TeamCode, TeamDynamics]
    events_emitted: int = Field(default=0, ge=0, description="So event ids stay unique after a fork.")
    possession_id: int = Field(default=0, ge=0, description="Last possession id emitted (event log continuity).")
    last_event_t: float = Field(default=0.0, ge=0, description="Clock of the last emitted event.")


class Outcomes(Contract):
    """Aggregates over R replicas. Per-replica goals are kept so deltas can be paired across forks."""

    R: int = Field(ge=1)
    seed: int
    goals: dict[TeamCode, list[int]]
    xpts: dict[TeamCode, float]
    ci90: dict[TeamCode, tuple[float, float]]
    kpi_trajectories: dict[str, list[float]] = Field(
        default_factory=dict, description="'<team>:<metric>' -> mean value at each minute from the start minute."
    )


class SimResult(Contract):
    outcomes: Outcomes
    events: list[Event] = Field(default_factory=list, description="Only when R == 1 and log=True.")
    snapshots: list[Snapshot] = Field(default_factory=list, description="Only when R == 1 and log=True.")
    final_state: MatchState | None = Field(default=None, description="Only when R == 1.")
