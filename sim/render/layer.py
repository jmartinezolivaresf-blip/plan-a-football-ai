"""Visual layer for the demo match: ball-anchored team shapes (v6 §9.8). Visualisation only, never analysed.

Each on-ball event gives a frame: the ball sits at the event; each team keeps a role template that shifts with the
ball, sits higher when it presses high or has the ball, and narrows towards the ball's lane. The player on the ball
is drawn at the ball.
"""

from __future__ import annotations

from contracts import Event, RenderFrame, Snapshot, Squads

ON_BALL = {"pass", "long_ball", "carry", "cross", "shot", "goal_kick", "corner", "kick_off", "throw_in"}
TEMPLATE = {  # attacking frame: x from own goal, y across (0..68)
    "GK": (5.0, 34.0), "RB": (30.0, 60.0), "LB": (30.0, 8.0), "CB": (22.0, 34.0), "DM": (40.0, 34.0),
    "CM": (50.0, 34.0), "AM": (60.0, 34.0), "RW": (68.0, 60.0), "LW": (68.0, 8.0), "ST": (76.0, 34.0),
}
SPREAD = {"CB": 13.0, "CM": 12.0}
PRESS_SHIFT = {"high": 9.0, "mid": 0.0, "low": -8.0}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def frames(events: list[Event], snapshots: list[Snapshot], squads: Squads, home: str) -> list[RenderFrame]:
    roles = {p.player_id: p.position for sq in squads.teams.values() for p in sq.players}
    by_minute = {s.minute: s for s in snapshots}
    out: list[RenderFrame] = []
    possession = None
    for e in events:
        if e.type in ON_BALL or e.type == "possession_change":
            possession = e.team
        if e.type not in ON_BALL:
            continue
        snap = by_minute.get(e.minute) or snapshots[min(e.minute, len(snapshots) - 1)]
        players: dict[str, tuple[float, float]] = {}
        for team, ids in snap.on_pitch.items():
            positive = (team == home) == (e.period == 1)
            ball_rel = e.x if positive else 105.0 - e.x
            press = snap.active_levers[team].press_height
            has_ball = team == possession
            lift = (6.0 if has_ball else PRESS_SHIFT[press])
            seen: dict[str, int] = {}
            same = [p for p in ids if roles[p] in SPREAD]
            for pid in ids:
                role = roles[pid]
                bx, by = TEMPLATE[role]
                if role in SPREAD:
                    group = [p for p in same if roles[p] == role]
                    k = seen.get(role, 0)
                    seen[role] = k + 1
                    by = 34.0 + SPREAD[role] * (k - (len(group) - 1) / 2)
                if role == "GK":
                    rx = bx + max(0.0, (ball_rel - 52.5) * 0.12)
                else:
                    rx = bx + lift + (ball_rel - 52.5) * 0.45
                ry = by + (e.y - 34.0) * 0.25
                rx, ry = _clamp(rx, 1.0, 104.0), _clamp(ry, 1.0, 67.0)
                players[pid] = (round(rx if positive else 105.0 - rx, 1), round(ry, 1))
        if e.player_id in players:
            players[e.player_id] = (e.x, e.y)
        out.append(RenderFrame(t=e.t, ball=(e.x, e.y), players=players))
    return out
