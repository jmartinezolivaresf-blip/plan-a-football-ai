"""Payoff matrices for The Duel.

M[i][j] = second half played with row option i (row_team) and column option j (col_team), forked from the
half-time snapshot with the SAME seeds in every cell. Cells store absolute xPts per team (not zero-sum: a
draw gives 1 point each). Deltas vs the Stay/Stay cell (0, 0) are derived, never stored.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import Contract, TeamCode


class Cell(Contract):
    xpts: dict[TeamCode, float]
    ci90: dict[TeamCode, tuple[float, float]]
    claim_id: str | None = None


class MatrixReading(Contract):
    """How one team reads the matrix (computed in code, see engine.duel)."""

    team: TeamCode
    best_response: dict[str, str] = Field(description="Opponent option_id -> this team's best option_id.")
    safe_pick: str
    best_guess: str | None = Field(default=None, description="Only when column probabilities are known.")
    gamble: str | None = None
    dominant: str | None = None


class Matrix(Contract):
    matrix_id: str
    match_id: str
    kind: Literal["believed", "true"]
    believer: TeamCode | None = Field(default=None, description="Owner of a believed matrix; null for true.")
    row_team: TeamCode
    col_team: TeamCode
    rows: list[str] = Field(min_length=2, max_length=3, description="Row option_ids; rows[0] is Stay.")
    cols: list[str] = Field(min_length=2, max_length=3, description="Column option_ids; cols[0] is Stay.")
    col_probs: list[float] | None = Field(
        default=None, description="Believed matrices: the believer's probabilities over the opponent options."
    )
    cells: list[list[Cell]]
    R: int = Field(ge=1)
    seed: int
    readings: dict[TeamCode, MatrixReading] = Field(default_factory=dict)
    illustrative: bool = False

    @model_validator(mode="after")
    def _shape(self) -> Matrix:
        if len(self.cells) != len(self.rows) or any(len(r) != len(self.cols) for r in self.cells):
            raise ValueError("cells must be len(rows) x len(cols)")
        for row in self.cells:
            for cell in row:
                if set(cell.xpts) != {self.row_team, self.col_team}:
                    raise ValueError("each cell needs xpts for row_team and col_team")
        if self.kind == "believed":
            if self.believer not in (self.row_team, self.col_team):
                raise ValueError("believed matrix needs a believer that is row_team or col_team")
            if self.col_probs is None or len(self.col_probs) != len(self.cols):
                raise ValueError("believed matrix needs col_probs over the opponent options")
        if self.kind == "true" and (self.believer is not None or self.col_probs is not None):
            raise ValueError("true matrix has no believer and no probabilities")
        if self.col_probs is not None and abs(sum(self.col_probs) - 1.0) > 1e-6:
            raise ValueError("col_probs must sum to 1")
        return self
