"""Event and snapshot logging for replica 0. Reads batch state only; never consumes randomness."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from contracts import Event, Levers, Snapshot, zone_index

from . import model as M

if TYPE_CHECKING:
    from .core import Batch

SHOT_OUTCOME = {8: "goal", 9: "saved", 10: "off_target", 11: "blocked", 12: "blocked"}


def _clamp(x: float, y: float) -> tuple[float, float]:
    return round(min(max(x, 0.5), 104.5), 1), round(min(max(y, 0.5), 67.5), 1)


def decode_levers(lev, opponent_ids: list[str]) -> Levers:
    target = int(lev[1])
    return Levers(press_height=M.INV_PRESS[int(lev[0])], press_target=opponent_ids[target] if target >= 0 else None,
                  build_up=M.INV_BUILD[int(lev[2])], attack_channel=M.INV_CHANNEL[int(lev[3])],
                  corner_delivery=M.INV_CORNER[int(lev[4])])


class Logger:
    def __init__(self, match_id: str, events_emitted: int = 0, possession_id: int = 0):
        self.match_id = match_id
        self.events: list[dict[str, Any]] = []
        self.snapshots: list[Snapshot] = []
        self.n = events_emitted
        self.possession_id = possession_id
        self.last_t = -1.0
        self.last_body_part: str | None = None
        self.last_set_piece: str | None = None
        self._pending_receiver: dict[str, Any] | None = None

    def _ids(self, b: Batch, team: int) -> list[str]:
        return b.w.teams[team].player_ids

    def event(self, type_: str, b: Batch, *, team: int, player: int | None, x: float, y: float,
              end: tuple[float, float] | None = None, receiver: int | None = None, outcome: str | None = None,
              new_possession: bool = False, under_pressure: bool = False, body_part: str | None = None,
              set_piece_ref: str | None = None, sub_in: int | None = None, sub_out: int | None = None) -> str:
        if new_possession:
            self.possession_id += 1
        t = max(round(float(b.t[0]), 1), round(self.last_t + 0.1, 1))
        self.last_t = t
        self.n += 1
        ids = self._ids(b, team)
        x, y = _clamp(x, y)
        ev: dict[str, Any] = {
            "event_id": f"{self.match_id}-e{self.n:05d}", "match_id": self.match_id, "t": t,
            "period": int(b.period[0]), "minute": int(t // 60), "possession_id": self.possession_id, "type": type_,
            "team": b.w.teams[team].code, "player_id": ids[player] if player is not None else None,
            "zone": zone_index(x, y), "x": x, "y": y, "outcome": outcome, "under_pressure": under_pressure,
            "body_part": body_part, "set_piece_ref": set_piece_ref,
        }
        if end is not None:
            ev["end_x"], ev["end_y"] = _clamp(*end)
        if receiver is not None:
            ev["receiver_id"] = ids[receiver]
        if sub_in is not None:
            ev["sub_in"], ev["sub_out"] = ids[sub_in], ids[sub_out]
        self.events.append(ev)
        return ev["event_id"]

    def action(self, b: Batch, *, action: int, team: int, player: int, x: float, y: float, tx: float, ty: float,
               success: bool, pz: float, cat: int, band: int, lane: int, header: bool) -> None:
        pressed = pz > 0.6
        if pressed:
            opp = 1 - team
            # deterministic presser: the opponent most involved at this zone in their own frame
            roles = b.ROLES[opp, b.on[0, opp]]
            w = M.ROLE_W[roles, 5 - band, 2 - lane]
            presser = int(b.on[0, opp, int(np.argmax(w))])
            self.event("pressure", b, team=opp, player=presser, x=x, y=y)
        self._pending_receiver = None
        if action == M.SHOT:
            body = "head" if header else "right_foot"
            gx = 105.0 if b._dir(b.poss)[0] > 0 else 0.0
            self.event("shot", b, team=team, player=player, x=x, y=y, end=(gx, 34.0), outcome=SHOT_OUTCOME[cat],
                       under_pressure=pressed, body_part=body)
            self.last_body_part, self.last_set_piece = body, None
            return
        self.event(_TYPE[action], b, team=team, player=player, x=x, y=y, end=(tx, ty),
                   outcome="success" if success else "fail", under_pressure=pressed)
        if success and action != M.CARRY:
            self._pending_receiver = self.events[-1]

    def patch_receiver(self, receiver: int) -> None:
        """The receiver is sampled after the action is logged; store its roster index until finish()."""
        if self._pending_receiver is not None:
            self._pending_receiver["_receiver_idx"] = receiver

    def snapshot(self, b: Batch, minute: int) -> None:
        teams = b.w.teams
        codes = [t.code for t in teams]
        self.snapshots.append(Snapshot(
            match_id=self.match_id, minute=minute, period=1 if minute < 45 or b.period[0] == 1 else 2,
            score={codes[i]: int(b.score[0, i]) for i in range(2)},
            subs_used={codes[i]: int(b.subs_used[0, i]) for i in range(2)},
            sub_windows_used={codes[i]: int(b.windows_used[0, i]) for i in range(2)},
            on_pitch={codes[i]: [teams[i].player_ids[p] for p in b.on[0, i]] for i in range(2)},
            condition_est={}, kpis=[],
            active_levers={codes[i]: decode_levers(b.lev[0, i], teams[1 - i].player_ids) for i in range(2)},
        ))

    def finish(self, b: Batch) -> list[Event]:
        out = []
        for ev in self.events:
            idx = ev.pop("_receiver_idx", None)
            if idx is not None:
                team = b.w.index(ev["team"])
                ev["receiver_id"] = b.w.teams[team].player_ids[idx]
            if ev.get("receiver_id") is None:
                ev.pop("receiver_id", None)
            out.append(Event.model_validate(ev))
        return out


_TYPE = {M.SHORT: "pass", M.PROG: "pass", M.LONG: "long_ball", M.CARRY: "carry", M.CROSS: "cross"}
