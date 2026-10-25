"""Structured outputs of the pre-match agents.

`*Draft` models are what the LLM returns (it chooses claims, words and levers, never numbers). Code turns drafts
into `ScoutingReport` and contract `Plan`s, copying every number from claims.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from contracts import I18nText, Kpi, Levers, Plan, PlanBRule, TraceStep
from contracts.plan import AttackChannel, BuildUp, CornerDelivery, OpponentPlanEstimate, PressHeight

Confidence = Literal["high", "medium", "low", "insufficient"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------- LLM drafts
class FindingDraft(_Strict):
    claim_id: str
    headline: str = Field(description="One sentence. Numbers only as {claim_id.field} placeholders.")


class LeverGuess(_Strict):
    press_height: PressHeight = "mid"
    build_up: BuildUp = "mixed"
    attack_channel: AttackChannel = "balanced"
    corner_delivery: CornerDelivery = "near_post"


class ScoutingDraft(_Strict):
    findings: list[FindingDraft] = Field(max_length=5)
    opponent_levers: LeverGuess
    opponent_evidence: list[str] = Field(default_factory=list)
    opponent_confidence: Literal["high", "medium", "low"] = "low"


class CandidateDraft(_Strict):
    name_en: str
    name_es: str
    press_height: PressHeight = "mid"
    press_target: str | None = None
    build_up: BuildUp = "mixed"
    attack_channel: AttackChannel = "balanced"
    corner_delivery: CornerDelivery = "near_post"
    lever_evidence: dict[str, list[str]] = Field(default_factory=dict)
    kpis: list[Kpi] = Field(min_length=1, max_length=4)
    plan_b: list[PlanBRule] = Field(default_factory=list)
    rationale: str = Field(description="Why this plan, citing claims; numbers only as placeholders.")


class CandidateSetDraft(_Strict):
    candidates: list[CandidateDraft] = Field(default_factory=list, max_length=3)


# ---------------------------------------------------------------------------- results built by code
class Finding(_Strict):
    claim_id: str
    headline: str
    metric: str
    player_id: str | None
    value: float | int | str
    league_ref: float | None
    n: int | None
    confidence: Confidence


class ScoutingReport(_Strict):
    team: str
    opponent: str
    findings: list[Finding] = Field(max_length=5)
    opponent_plan_estimate: OpponentPlanEstimate
    model: str
    attempts: int
    fallback: bool


class CandidateResult(_Strict):
    plan: Plan
    rationale: str
    validation: list[list[str]] = Field(description="Validator errors per attempt (empty list = valid).")
    valuation_claims: list[str] = Field(default_factory=list)
    valid: bool


class PrematchResult(_Strict):
    team: str
    opponent: str
    report: ScoutingReport
    candidates: list[CandidateResult]
    chosen: Plan
    chosen_reason: str
    used_template: bool
    traces: list[TraceStep]
    model: str


def default_levers() -> Levers:
    return Levers()


def name(en: str, es: str) -> I18nText:
    return I18nText(en=en, es=es)
