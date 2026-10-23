"""Pure reading of a Duel payoff matrix (owner: person A). No simulation here: input is a Matrix.

All functions work for either team: for the column team the matrix is read transposed.
"""

from __future__ import annotations

from contracts import Matrix, MatrixReading

# A gamble must have a worst case at least this much below the safe pick's worst case (xPts).
GAMBLE_MARGIN = 0.02


def payoffs(matrix: Matrix, team: str) -> tuple[list[str], list[str], list[list[float]]]:
    """Return (own_options, opponent_options, P) with P[own][opp] = team's xPts."""
    if team == matrix.row_team:
        return matrix.rows, matrix.cols, [[c.xpts[team] for c in row] for row in matrix.cells]
    if team == matrix.col_team:
        p = [[matrix.cells[i][j].xpts[team] for i in range(len(matrix.rows))] for j in range(len(matrix.cols))]
        return matrix.cols, matrix.rows, p
    raise ValueError(f"{team} is not in this matrix")


def best_response(matrix: Matrix, team: str) -> dict[str, str]:
    own, opp, p = payoffs(matrix, team)
    return {opp[j]: own[max(range(len(own)), key=lambda i: p[i][j])] for j in range(len(opp))}


def safe_pick(matrix: Matrix, team: str) -> str:
    own, _, p = payoffs(matrix, team)
    return own[max(range(len(own)), key=lambda i: min(p[i]))]


def best_guess(matrix: Matrix, team: str, opponent_probs: list[float]) -> str:
    own, opp, p = payoffs(matrix, team)
    if len(opponent_probs) != len(opp):
        raise ValueError("one probability per opponent option")
    return own[max(range(len(own)), key=lambda i: sum(pr * v for pr, v in zip(opponent_probs, p[i], strict=True)))]


def gamble(matrix: Matrix, team: str) -> str | None:
    """An option that gives up floor for a HIGHER ceiling than the safe pick; none when the safe pick is also the
    best case (e.g. a dominant option), so a dominated option is never labelled a gamble."""
    own, _, p = payoffs(matrix, team)
    safe = own.index(safe_pick(matrix, team))
    candidates = [i for i in range(len(own)) if i != safe and min(p[i]) <= min(p[safe]) - GAMBLE_MARGIN
                  and max(p[i]) >= max(p[safe]) + GAMBLE_MARGIN]
    if not candidates:
        return None
    return own[max(candidates, key=lambda i: max(p[i]))]


def dominant(matrix: Matrix, team: str) -> str | None:
    picks = set(best_response(matrix, team).values())
    return picks.pop() if len(picks) == 1 else None


def reading(matrix: Matrix, team: str, opponent_probs: list[float] | None = None) -> MatrixReading:
    return MatrixReading(
        team=team,
        best_response=best_response(matrix, team),
        safe_pick=safe_pick(matrix, team),
        best_guess=best_guess(matrix, team, opponent_probs) if opponent_probs is not None else None,
        gamble=gamble(matrix, team),
        dominant=dominant(matrix, team),
    )


def regret(true_matrix: Matrix, team: str, chosen: str, opponent_chosen: str) -> tuple[str, float]:
    """(best response to the opponent's real choice, regret in xPts). Always >= 0 by construction."""
    own, opp, p = payoffs(true_matrix, team)
    j = opp.index(opponent_chosen)
    best = max(range(len(own)), key=lambda i: p[i][j])
    return own[best], p[best][j] - p[own.index(chosen)][j]
