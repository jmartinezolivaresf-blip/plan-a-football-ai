"""The Duel: per-bench PRIVATE half-time data, plus the broadcast-only reveal, true matrix and regret.

Separation rule (tested): a bench's TeamDuelPrivate never contains the opponent's real options, the
opponent's choice or the true matrix. Those only exist in DuelBroadcast, built after both choices are sealed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import Contract, TeamCode
from .matrix import Matrix
from .option import Option

ChoiceRule = Literal["safe_pick", "best_guess", "gamble"]


class EstimatedOption(Contract):
    option: Option
    probability: float = Field(ge=0, le=1)


class OpponentOptionsEstimate(Contract):
    estimator: TeamCode
    opponent: TeamCode
    options: list[EstimatedOption] = Field(min_length=2, max_length=3)
    claims: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _probs(self) -> OpponentOptionsEstimate:
        total = sum(o.probability for o in self.options)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"estimated probabilities must sum to 1, got {total}")
        if any(o.option.team != self.opponent or not o.option.estimated for o in self.options):
            raise ValueError("estimated options must belong to the opponent and be flagged estimated")
        return self


class SealedChoice(Contract):
    """Commit only: the option and salt stay hidden until the reveal (see contracts.sealing)."""

    team: TeamCode
    sealed_at: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RevealedChoice(Contract):
    team: TeamCode
    option_id: str
    salt: str = Field(min_length=16)
    rule: ChoiceRule


class Regret(Contract):
    team: TeamCode
    chosen: str
    opponent_chosen: str
    best_response: str
    regret_xpts: float = Field(description="xPts(best response) - xPts(chosen) on the true matrix; >= 0.")
    claim_id: str | None = None


class TeamDuelPrivate(Contract):
    team: TeamCode
    options: list[Option] = Field(min_length=2, max_length=3, description="options[0] is Stay the course.")
    opponent_estimate: OpponentOptionsEstimate
    believed_matrix: Matrix
    choice: SealedChoice


class DuelBroadcast(Contract):
    revealed: dict[TeamCode, RevealedChoice]
    true_matrix: Matrix
    regret: dict[TeamCode, Regret]


class Duel(Contract):
    match_id: str
    minute: int = 45
    private: dict[TeamCode, TeamDuelPrivate]
    broadcast: DuelBroadcast
    illustrative: bool = False
