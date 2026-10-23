"""Turn scouting claims into SUSPECTED weaknesses for a bench's world model (never reads hidden truth).

Each rule maps an observed deviation from the league to a belief with a strength that grows with the deviation.
The same mapping defines which traits a scouting report "flags" for evaluation E1.
"""

from __future__ import annotations

from contracts import Claim

DEFENSIVE_ROLES = ("LB", "RB", "CB", "DM")


def _ratio(c: Claim) -> float | None:
    if not isinstance(c.value, (int, float)) or not c.league_ref:
        return None
    return float(c.value) / float(c.league_ref)


def belief_from_claim(c: Claim) -> dict | None:
    """One claim -> one belief dict (team, kind, strength[, player_id | side]) or None."""
    r = _ratio(c)
    if r is None or c.status != "sufficient" or c.team is None:
        return None

    def strength(threshold: float, scale: float) -> float:
        return round(min(0.85, max(0.0, (r - threshold) * scale + 0.3)), 2)

    m = c.metric
    if m == "losses_per_100_pressured_receptions" and r >= 1.15 and c.label and \
            c.label.split(",")[0] in DEFENSIVE_ROLES:
        return {"team": c.team, "kind": "fb_low_press_resistance", "player_id": c.player_id,
                "strength": strength(1.15, 1.5)}
    if m == "goal_kick_short_share" and r >= 1.3:
        return {"team": c.team, "kind": "gk_short_bias", "strength": strength(1.3, 1.0)}
    if m == "first_contact_conceded_share" and (c.label or "").startswith("back") and r >= 1.2:
        return {"team": c.team, "kind": "back_post_weak", "strength": strength(1.2, 1.0)}
    if m == "entries_conceded_share" and r >= 1.2 and c.label:
        return {"team": c.team, "kind": "weak_channel", "side": c.label.split()[0], "strength": strength(1.2, 1.5)}
    if m == "balls_in_behind_conceded_per_match" and r >= 1.2:
        return {"team": c.team, "kind": "cb_low_pace", "strength": strength(1.2, 1.5)}
    if m == "late_xg_conceded_ratio" and r >= 1.25:
        return {"team": c.team, "kind": "late_fade", "strength": strength(1.25, 1.0)}
    return None


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
