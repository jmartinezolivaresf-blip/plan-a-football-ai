"""Timed overlay cue (cue sheet). Text uses {claim_id.field} placeholders filled by code, never by the LLM."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, I18nText, Mode, TeamCode

CueTemplate = Literal[
    "plan_card", "plan_sealed", "plan_tracker_lt", "plan_alert", "adaptation_detected", "plan_b_fired",
    "duel_rooms", "duel_sealed", "duel_reveal", "duel_matrix", "plan_scorecard", "bench_regret",
    "option_not_taken",
]


class Cue(Contract):
    cue_id: str
    t_match: str = Field(pattern=r"^\d{1,3}:[0-5]\d$")
    template: CueTemplate
    priority: int = Field(ge=1, le=3)
    ttl_s: int = Field(ge=1, le=120)
    team: TeamCode | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    text: I18nText
    mode: list[Mode] = Field(min_length=1)
    claims: list[str] = Field(default_factory=list)
