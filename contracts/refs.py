"""Small tool-result contracts used by the engine API and the MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, TeamCode


class MatchRef(Contract):
    match_id: str
    home: TeamCode
    away: TeamCode
    score: dict[TeamCode, int]
    source: Literal["season", "demo"] = "season"


class ValidationResult(Contract):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class ToolError(Contract):
    error: Literal["forbidden_scope", "not_sealed_yet", "not_ready", "not_found", "invalid_args"]
    detail: str = ""
