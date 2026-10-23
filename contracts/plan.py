"""Game plan: the pre-match contract each manager agent produces and seals."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, I18nText, TeamCode

PressHeight = Literal["high", "mid", "low"]
BuildUp = Literal["short", "mixed", "direct"]
AttackChannel = Literal["left", "center", "right", "balanced"]
CornerDelivery = Literal["near_post", "far_post", "short"]
KpiMetric = Literal["high_turnovers", "final_third_entries_share", "set_piece_xg", "balls_in_behind_conceded"]
KpiStatusValue = Literal["on_track", "at_risk", "failing", "insufficient_evidence"]


class Levers(Contract):
    press_height: PressHeight = "mid"
    press_target: str | None = Field(default=None, description="Opponent player_id, or null for none.")
    build_up: BuildUp = "mixed"
    attack_channel: AttackChannel = "balanced"
    corner_delivery: CornerDelivery = "near_post"


class LeverChanges(Contract):
    """Partial levers: only the fields an option or a Plan B rule changes."""

    press_height: PressHeight | None = None
    press_target: str | None = None
    build_up: BuildUp | None = None
    attack_channel: AttackChannel | None = None
    corner_delivery: CornerDelivery | None = None


class Kpi(Contract):
    id: str
    metric: KpiMetric
    params: dict[str, str] = Field(default_factory=dict)
    target: str = Field(pattern=r"^(>=|<=|>|<)\d+(\.\d+)?$")
    by_minute: int = Field(default=90, ge=1, le=90)


class Sub(Contract):
    window: str = Field(pattern=r"^(HT|\d{1,2}-\d{1,2})$", description="'HT' or a minute window like '60-65'.")
    out: str
    into: str = Field(alias="in")

    model_config = {"populate_by_name": True, "extra": "forbid", "json_schema_serialization_defaults_required": True}


class PlanBCondition(Contract):
    kpi: str | None = None
    status: KpiStatusValue | None = None
    after_minute: int | None = Field(default=None, ge=0, le=90)
    score_diff: str | None = Field(default=None, pattern=r"^(>=|<=|>|<|==)-?\d+$")


class PlanBAction(Contract):
    levers: LeverChanges = Field(default_factory=LeverChanges)
    subs: list[Sub] = Field(default_factory=list)


class PlanBRule(Contract):
    if_: PlanBCondition = Field(alias="if")
    then: PlanBAction

    model_config = {"populate_by_name": True, "extra": "forbid", "json_schema_serialization_defaults_required": True}


class Seal(Contract):
    """Commit of the canonical plan JSON (everything except `sealed`). See contracts.sealing."""

    at: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OpponentPlanEstimate(Contract):
    """Pre-match: the analyst's guess of the opponent's levers (never the opponent's real plan)."""

    estimator: TeamCode
    opponent: TeamCode
    levers: Levers
    confidence: float = Field(ge=0, le=1)
    claims: list[str] = Field(default_factory=list)


class Plan(Contract):
    plan_id: str
    team: TeamCode
    opponent: TeamCode
    name: I18nText
    levers: Levers
    lever_evidence: dict[str, list[str]] = Field(
        default_factory=dict, description="Lever name -> claim_ids. Every non-default lever needs one."
    )
    kpis: list[Kpi] = Field(min_length=1, max_length=6)
    plan_b: list[PlanBRule] = Field(default_factory=list)
    subs_plan: list[Sub] = Field(default_factory=list, max_length=5)
    valuation: str | None = Field(default=None, description="claim_id of the sim_valuation claim.")
    sealed: Seal | None = None
