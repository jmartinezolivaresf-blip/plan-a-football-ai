"""Agent trace step, shown in the analyst desk (tools, args, claims, duration, rejections, retries)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import Contract, Scope

AgentRole = Literal["analyst", "manager", "director", "chronicler", "localizer", "validator"]


class TraceStep(Contract):
    trace_id: str
    workflow: Literal["prematch", "live", "duel", "final"]
    agent: AgentRole
    scope: Scope
    step: int = Field(ge=0)
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result_claims: list[str] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)
    status: Literal["ok", "rejected", "retried", "fallback"]
    message: str | None = None
