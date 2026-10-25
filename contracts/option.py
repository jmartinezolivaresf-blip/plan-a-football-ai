"""Half-time option: a validated set of lever and/or player changes for one bench."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import Field

from .common import Contract, I18nText, TeamCode
from .plan import LeverChanges, Sub

# Small shared vocabulary so the evaluator can match an ESTIMATED opponent option to the REAL one (E7)
# without the estimator ever seeing the real options.
Intent = Literal[
    "stay_the_course",
    "press_higher",
    "drop_block",
    "go_direct",
    "short_build_up",
    "attacking_subs",
    "protect_lead",
    "target_weak_side",
]


class Option(Contract):
    option_id: str
    team: TeamCode
    label: I18nText
    intent: Intent
    lever_changes: LeverChanges = Field(default_factory=LeverChanges)
    subs: list[Sub] = Field(default_factory=list, max_length=3)
    evidence: list[str] = Field(default_factory=list, description="claim_ids that justify the option.")
    estimated: bool = Field(default=False, description="True when this is an analyst's guess of the OPPONENT.")


def tactics(levers: Mapping[str, Any], changes: LeverChanges, subs: Iterable[Sub] = ()) -> tuple:
    """What a team plays with after an option: the levers in force with the option's changes applied (the levers it
    does not set are kept) and its substitutions. Options with the same tactics are the same option (D-055)."""
    after = {**dict(levers), **changes.model_dump(exclude_none=True)}
    after = {k: None if v == "none" else v for k, v in after.items()}
    return tuple(sorted(after.items())), tuple(sorted((s.out, s.into) for s in subs))


def changes_nothing(levers: Mapping[str, Any], changes: LeverChanges, subs: Iterable[Sub] = ()) -> bool:
    """True when an option only sets levers that are already in force and makes no substitution."""
    return tactics(levers, changes, subs) == tactics(levers, LeverChanges())
