"""Match events. Absolute 105 x 68 m pitch, origin at a fixed corner; attack direction per period lives in
MatchMeta. xG is NOT part of the event: the engine computes it, as it would with a real provider."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import PITCH_LENGTH_M, PITCH_WIDTH_M, Contract, TeamCode

EventType = Literal[
    "pass", "long_ball", "cross", "carry", "shot", "goal", "pressure", "tackle", "interception",
    "clearance", "foul", "corner", "goal_kick", "throw_in", "kick_off", "sub", "possession_change",
    "recovery",
]

Outcome = Literal[
    "success", "fail", "goal", "saved", "off_target", "blocked", "won", "lost", "first_contact_won",
    "first_contact_lost",
]

BodyPart = Literal["right_foot", "left_foot", "head", "other"]


class Event(Contract):
    event_id: str
    match_id: str
    t: float = Field(ge=0, description="Match clock in seconds since kick-off (second half starts at 2700).")
    period: Literal[1, 2]
    minute: int = Field(ge=0, le=130)
    possession_id: int = Field(ge=0)
    type: EventType
    team: TeamCode
    player_id: str | None = None
    zone: int = Field(ge=0, le=17, description="Absolute zone = band * 3 + lane (see contracts.common).")
    x: float = Field(ge=0, le=PITCH_LENGTH_M)
    y: float = Field(ge=0, le=PITCH_WIDTH_M)
    end_x: float | None = Field(default=None, ge=0, le=PITCH_LENGTH_M)
    end_y: float | None = Field(default=None, ge=0, le=PITCH_WIDTH_M)
    receiver_id: str | None = None
    outcome: Outcome | None = None
    under_pressure: bool = False
    body_part: BodyPart | None = None
    set_piece_ref: str | None = Field(default=None, description="Links shots/goals to the corner that created them.")
    sub_in: str | None = Field(default=None, description="Only for type == 'sub'.")
    sub_out: str | None = Field(default=None, description="Only for type == 'sub'.")
