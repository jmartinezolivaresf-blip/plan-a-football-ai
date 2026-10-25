"""Event helpers in a team's attacking frame (engine side; works on any provider's events)."""

from __future__ import annotations

from contracts import Event

ON_BALL = ("pass", "long_ball", "carry", "cross")
FINAL_THIRD_X = 70.0
HIGH_TURNOVER_X = 65.0  # D-015: ball won within 40 m of the opponent's goal


def attacks_positive(team: str, period: int, home: str) -> bool:
    return (team == home) == (period == 1)


def rel_x(e: Event, team: str, home: str, x: float | None = None) -> float:
    """x of the event (or a given x) in `team`'s attacking frame (0 = own goal line)."""
    x = e.x if x is None else x
    return x if attacks_positive(team, e.period, home) else 105.0 - x


def lane_rel(e: Event, team: str, home: str, y: float | None = None) -> int:
    """Team-relative lane: 0 = the team's left, 1 = centre, 2 = its right."""
    y = e.y if y is None else y
    lane_abs = min(int(y / (68.0 / 3)), 2)
    return 2 - lane_abs if attacks_positive(team, e.period, home) else lane_abs


def is_entry(e: Event, home: str) -> bool:
    """Successful action that brings the ball into the team's final third."""
    if e.type not in ON_BALL or e.outcome != "success" or e.end_x is None:
        return False
    return rel_x(e, e.team, home) < FINAL_THIRD_X <= rel_x(e, e.team, home, e.end_x)


def entry_lane(e: Event, home: str) -> int:
    return lane_rel(e, e.team, home, e.end_y)


def is_high_turnover(e: Event, home: str) -> bool:
    return e.type in ("tackle", "interception") and rel_x(e, e.team, home) >= HIGH_TURNOVER_X


def is_ball_in_behind(e: Event, home: str) -> bool:
    return (e.type == "long_ball" and e.outcome == "success" and e.end_x is not None
            and rel_x(e, e.team, home, e.end_x) >= FINAL_THIRD_X)


def goal_kick_is_long(e: Event, home: str) -> bool:
    return e.end_x is not None and rel_x(e, e.team, home, e.end_x) >= 35.0


def corner_delivery(e: Event) -> str:
    """near_post / far_post / short from the corner's start and end y (absolute frame)."""
    if e.end_y is None:
        return "short"
    if e.end_y < 12 or e.end_y > 56:
        return "short"
    return "near_post" if (e.end_y < 34) == (e.y < 34) else "far_post"
