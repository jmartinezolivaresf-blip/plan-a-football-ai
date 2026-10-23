"""Types crossing the simulator <-> engine boundary (see contracts/sim_api.md). Owner: person A."""

from __future__ import annotations

from pydantic import Field

from .common import Contract, TeamCode
from .events import Event
from .plan import Levers
from .snapshot import Snapshot


class MatchState(Contract):
    """Everything needed to fork a match: score, clock, levers, players, fatigue and the RNG position."""

    match_id: str
    minute: int = Field(ge=0, le=90)
    snapshot: Snapshot
    levers: dict[TeamCode, Levers]
    fatigue: dict[str, float] = Field(description="player_id -> simulator stamina 0..1 (sim-internal).")
    rng_step: int = Field(ge=0, description="Step counter so forks consume the same uniforms (CRN).")


class Outcomes(Contract):
    """Aggregates over R replicas. Per-replica goals are kept so deltas can be paired across forks."""

    R: int = Field(ge=1)
    seed: int
    goals: dict[TeamCode, list[int]]
    xpts: dict[TeamCode, float]
    ci90: dict[TeamCode, tuple[float, float]]
    kpi_trajectories: dict[str, list[float]] = Field(default_factory=dict)


class SimResult(Contract):
    outcomes: Outcomes
    events: list[Event] = Field(default_factory=list, description="Only when R == 1 and log=True.")
    snapshots: list[Snapshot] = Field(default_factory=list, description="Only when R == 1 and log=True.")
    final_state: MatchState | None = None
