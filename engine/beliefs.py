"""Turn scouting claims into SUSPECTED weaknesses for a bench's world model (never reads hidden truth).

A claim becomes a belief when its evidence (contracts.claim.evidence_z: distance from the reference in standard
errors) passes the threshold for its statistic. The statistics are the exposure- and style-controlled ones
(engine/scouting.py, D-049); raw volumes that depend on the opponents faced are reported but not turned into
beliefs. The same mapping defines which traits a scouting report "flags" for evaluation E1.
"""

from __future__ import annotations

from contracts import Claim
from contracts.claim import evidence_z

FULL_BACKS = ("LB", "RB")
# statistic -> (trait kind, z threshold). Selected on DEV seasons only by eval/select_scouting.py (best F1 per
# statistic); a test keeps them equal to eval/results/dev/scouting_thresholds.json.
RULES: dict[str, tuple[str, float]] = {
    "losses_per_100_pressured_receptions": ("fb_low_press_resistance", 1.0),
    "goal_kick_short_vs_open_play": ("gk_short_bias", 0.0),
    "first_contact_conceded_share": ("back_post_weak", 0.75),
    "forward_success_conceded_share": ("weak_channel", 0.0),
    "deep_ball_success_conceded_share": ("cb_low_pace", 1.0),
    "late_xg_conceded_ratio": ("late_fade", 0.0),
}


def belief_from_claim(c: Claim) -> dict | None:
    """One claim -> one belief dict (team, kind, strength[, player_id | side]) or None."""
    if c.status != "sufficient" or c.team is None or c.metric not in RULES:
        return None
    kind, threshold = RULES[c.metric]
    z = evidence_z(c)
    if z is None or z < threshold:
        return None
    strength = round(min(0.85, 0.3 + 0.1 * (z - threshold)), 2)
    if kind == "fb_low_press_resistance":
        if not c.player_id or (c.label or "").split(",")[0] not in FULL_BACKS:
            return None  # the trait is a full-back's; a centre-back losing balls is reported but not this belief
        return {"team": c.team, "kind": kind, "player_id": c.player_id, "strength": strength}
    if kind == "back_post_weak" and not (c.label or "").startswith("back"):
        return None
    if kind == "weak_channel":
        if not c.label:
            return None
        return {"team": c.team, "kind": kind, "side": c.label.split()[0], "strength": strength}
    return {"team": c.team, "kind": kind, "strength": strength}


def beliefs_from_claims(claims: list[Claim]) -> list[dict]:
    seen, out = set(), []
    for c in claims:
        b = belief_from_claim(c)
        if b is None:
            continue
        key = (b["team"], b["kind"], b.get("player_id"), b.get("side"))
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out
