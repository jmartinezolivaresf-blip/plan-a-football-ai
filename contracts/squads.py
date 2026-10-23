"""Fictional squads with VISIBLE attributes only. Hidden traits live in contracts.eval_only.Truth.

Visibility rule: each staff sees its own squad's attributes; of the opponent it only sees events.
The MCP server enforces this; the broadcast bundle may contain both squads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, TeamCode

Position = Literal["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]


class Attributes(Contract):
    pace: int = Field(ge=0, le=100)
    passing: int = Field(ge=0, le=100)
    stamina: int = Field(ge=0, le=100)
    press_resistance: int = Field(ge=0, le=100)
    aerial: int = Field(ge=0, le=100)
    finishing: int = Field(ge=0, le=100)


class Player(Contract):
    player_id: str = Field(pattern=r"^[A-Z]{3}-\d{1,2}$")
    name: str
    shirt: int = Field(ge=1, le=99)
    position: Position
    starter: bool
    attributes: Attributes


class Squad(Contract):
    team: TeamCode
    name: str
    short_name: str
    players: list[Player] = Field(min_length=11)


class Squads(Contract):
    teams: dict[TeamCode, Squad]
