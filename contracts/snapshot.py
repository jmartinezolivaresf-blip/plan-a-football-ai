"""Match state snapshot (every minute and on key events). Physical condition is the ENGINE's estimate from
observable load, never the simulator's internal stamina."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, TeamCode
from .plan import KpiStatusValue, Levers


class KpiStatus(Contract):
    plan_id: str
    kpi_id: str
    team: TeamCode
    value: float
    expected: float | None = Field(default=None, description="Mean of pre-match sims at this minute.")
    band_low: float | None = None
    band_high: float | None = None
    n: int = Field(ge=0)
    status: KpiStatusValue
    claim_id: str | None = None


class Snapshot(Contract):
    match_id: str
    minute: int = Field(ge=0, le=130)
    period: Literal[1, 2]
    score: dict[TeamCode, int]
    subs_used: dict[TeamCode, int]
    sub_windows_used: dict[TeamCode, int]
    on_pitch: dict[TeamCode, list[str]]
    condition_est: dict[str, float] = Field(default_factory=dict, description="player_id -> 0..1 (estimate).")
    active_levers: dict[TeamCode, Levers]
    kpis: list[KpiStatus] = Field(default_factory=list)
