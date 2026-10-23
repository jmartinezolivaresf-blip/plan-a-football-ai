"""Shared primitives used by every contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Team codes are short upper-case strings ("KES", "HAR"). The season has 6 clubs, so this is not an enum.
TeamCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

# Scope header set by the agent host (never by the LLM): a team code or the broadcast desk.
Scope = Annotated[str, Field(pattern=r"^([A-Z]{3}|broadcast)$")]
BROADCAST_SCOPE = "broadcast"

Lang = Literal["en", "es"]
Mode = Literal["casual", "analyst"]

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
N_BANDS = 6
N_LANES = 3


class Contract(BaseModel):
    """Base for all contracts: strict field names, no silent extras."""

    # Exported schemas describe files on disk (serialization), where defaulted fields are always present.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class I18nText(Contract):
    en: str
    es: str


def zone_index(x: float, y: float) -> int:
    """Absolute zone 0..17 = band * 3 + lane. Bands split x (0..105) in 6; lanes split y (0..68) in 3.

    Zones are absolute (pitch frame). Use `relative_band` to get the band from a team's attacking view.
    """
    band = min(int(x / (PITCH_LENGTH_M / N_BANDS)), N_BANDS - 1)
    lane = min(int(y / (PITCH_WIDTH_M / N_LANES)), N_LANES - 1)
    return band * N_LANES + lane


def relative_band(zone: int, attacking_positive_x: bool) -> int:
    """Band 0..5 counted from the team's own goal (0 = own third, 5 = final band)."""
    band = zone // N_LANES
    return band if attacking_positive_x else N_BANDS - 1 - band
