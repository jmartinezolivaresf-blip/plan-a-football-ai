"""Claims: the only source of numbers for any text. LLM text references them as {claim_id.field}."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Contract, TeamCode

ClaimType = Literal[
    "observed_tendency",
    "observed_adaptation",
    "observed_mechanism",
    "sim_valuation",
    "sim_matrix_cell",
    "opponent_estimate",
    "regret",
    "kpi_status",
]

# Fields that text placeholders may reference ({c1.value}, {c1.n}, ...).
PLACEHOLDER_FIELDS = ("value", "league_ref", "n", "target", "minute", "label", "interval_low", "interval_high")


class Claim(Contract):
    claim_id: str = Field(pattern=r"^c[\w-]+$")
    type: ClaimType
    team: TeamCode | None = None
    player_id: str | None = None
    metric: str
    value: float | int | str
    unit: str | None = None
    league_ref: float | None = None
    n: int | None = Field(default=None, ge=0)
    interval_low: float | None = None
    interval_high: float | None = None
    target: str | None = None
    minute: int | None = Field(default=None, ge=0, le=130)
    label: str | None = None
    evidence: list[str] = Field(default_factory=list, description="event_ids / match refs that support it.")
    status: Literal["sufficient", "insufficient"] = "sufficient"
    illustrative: bool = Field(default=False, description="True for hand-written fixture data (not simulated).")


Z90 = 1.6449  # two-sided 90% normal quantile used by every claim interval


def evidence_z(claim: Claim | dict) -> float | None:
    """How far the claim's value sits from its reference, in standard errors read off its 90% interval.

    Positive means above the reference. None when the claim has no reference or no interval (e.g. a plain count).
    Pure function on claim fields, so agents can rank evidence without importing the engine (D-049)."""
    get = claim.get if isinstance(claim, dict) else (lambda k: getattr(claim, k))
    value, ref, lo, hi = get("value"), get("league_ref"), get("interval_low"), get("interval_high")
    if not isinstance(value, (int, float)) or ref is None or lo is None or hi is None or hi <= lo:
        return None
    return (float(value) - float(ref)) / ((float(hi) - float(lo)) / (2 * Z90))
