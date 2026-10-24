"""Deterministic scouting over past matches (events only). Every output is a claim with n, a reference and a 90%
interval, so how strong the evidence is can be read off the claim itself (contracts.claim.evidence_z).

Hidden traits are never read; they can only show up as observed deviations from the league. Where a raw volume
depends on who a team played (balls in behind, entries down a channel) there is also an exposure-controlled rate
(success of the attempts made against the team), and goal-kick length is compared with the team's own open-play
build-up so a possession side is not flagged for being a possession side (D-049).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from contracts import Claim, Event
from contracts.claim import Z90

from .eventsx import (
    ON_BALL,
    corner_delivery,
    entry_lane,
    goal_kick_is_long,
    is_ball_in_behind,
    is_entry,
    lane_rel,
    rel_x,
)
from .xg import XGModel

MIN_N = {"rate": 15, "goal_kicks": 10, "corners": 8, "entries": 20, "matches": 4, "shots": 8, "attempts": 20}
FINAL_THIRD = 70.0
LANE_NAME = {0: "left", 2: "right"}


@dataclass
class MatchLog:
    match_id: str
    home: str
    away: str
    events: list[Event]


def wilson(k: float, n: float, scale: float = 1.0) -> tuple[float, float] | None:
    """90% Wilson interval of a share k/n (times `scale`, e.g. 100 for per-100 rates)."""
    if n <= 0:
        return None
    p, z2 = k / n, Z90 * Z90
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z90 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return scale * max(centre - half, 0.0), scale * min(centre + half, 1.0)


def poisson_rate(count: float, exposure: float) -> tuple[float, float] | None:
    """90% score interval of a Poisson rate count/exposure (e.g. per match)."""
    if exposure <= 0:
        return None
    z2 = Z90 * Z90
    half = Z90 * math.sqrt(count + z2 / 4)
    return max(count + z2 / 2 - half, 0.0) / exposure, (count + z2 / 2 + half) / exposure


def _claim(cid: str, metric: str, value: float, team: str, n: int, league: float | None, kind: str,
           evidence: list[str], player_id: str | None = None, label: str | None = None,
           interval: tuple[float, float] | None = None) -> Claim:
    lo, hi = interval if interval else (None, None)
    return Claim(claim_id=cid, type="observed_tendency", team=team, player_id=player_id, metric=metric,
                 value=round(value, 3), league_ref=None if league is None else round(league, 3), n=n, label=label,
                 interval_low=None if lo is None else round(lo, 3), interval_high=None if hi is None else round(hi, 3),
                 evidence=evidence[:12], status="sufficient" if n >= MIN_N[kind] else "insufficient")


class Scout:
    """Pre-computes league references once; then answers per team/player."""

    def __init__(self, matches: list[MatchLog], positions: dict[str, str]):
        self.matches = matches
        self.positions = positions  # player_id -> position
        shots = [(e, m.home, e.outcome == "goal") for m in matches for e in m.events if e.type == "shot"]
        self.xg = XGModel.fit(shots)
        self._index()

    # ------------------------------------------------------------------ aggregation
    def _index(self) -> None:
        self.gk = defaultdict(lambda: [0, 0, []])            # team -> [short, total, ev ids]
        self.press = defaultdict(lambda: [0, 0, []])         # player -> [losses, pressured actions, ev ids]
        self.entries_conc = defaultdict(lambda: [[0, 0, 0], []])  # defending team -> [by defender lane], ev ids
        self.corners_conc = defaultdict(lambda: {"near_post": [0, 0], "far_post": [0, 0], "ids": []})
        self.bib_conc = defaultdict(lambda: [0, set()])      # defending team -> [count, matches]
        self.late_xg = defaultdict(lambda: [0.0, 0.0, 0, set(), 0])  # defending team -> [xg 75+, xg <75, shots 75+,
        #                                                                   matches, shots <75]
        self.fwd_conc = defaultdict(lambda: [[0, 0], [0, 0], [0, 0]])  # defending team -> by its lane [succ, att]
        self.deep_conc = defaultdict(lambda: [0, 0, []])     # defending team -> [succ, att, ids] deep balls
        self.style = defaultdict(lambda: [0, 0])             # team -> [own-half long balls, own-half actions]
        for m in self.matches:
            for e in m.events:
                opp = m.away if e.team == m.home else m.home
                if e.type == "goal_kick":
                    s = self.gk[e.team]
                    s[0] += 0 if goal_kick_is_long(e, m.home) else 1
                    s[1] += 1
                    s[2].append(e.event_id)
                elif e.type in ON_BALL and e.under_pressure and e.player_id:
                    s = self.press[e.player_id]
                    s[1] += 1
                    if e.outcome == "fail":
                        s[0] += 1
                        s[2].append(e.event_id)
                if is_entry(e, m.home):
                    lane = 2 - entry_lane(e, m.home)  # attacker's left is the defender's right
                    self.entries_conc[opp][0][lane] += 1
                    self.entries_conc[opp][1].append(e.event_id)
                if e.type == "corner":
                    d = corner_delivery(e)
                    if d in ("near_post", "far_post"):
                        c = self.corners_conc[opp][d]
                        c[1] += 1
                        c[0] += 1 if e.outcome == "first_contact_won" else 0
                        self.corners_conc[opp]["ids"].append(e.event_id)
                if is_ball_in_behind(e, m.home):
                    self.bib_conc[opp][0] += 1
                if e.type == "shot":
                    x = self.xg(e, m.home)
                    s = self.late_xg[opp]
                    if e.minute >= 75:
                        s[0] += x
                        s[2] += 1
                    else:
                        s[1] += x
                        s[4] += 1
                if e.type in ("pass", "long_ball", "carry", "cross") and e.end_x is not None:
                    x0, x1 = rel_x(e, e.team, m.home), rel_x(e, e.team, m.home, e.end_x)
                    ok = e.outcome == "success"
                    if x1 - x0 >= 10 or e.type in ("carry", "cross"):  # forward actions, by the defender's lane
                        f = self.fwd_conc[opp][2 - lane_rel(e, e.team, m.home, e.end_y)]
                        f[0] += ok
                        f[1] += 1
                    if e.type in ("pass", "long_ball") and x1 >= FINAL_THIRD > x0 and x1 - x0 >= 20:
                        d = self.deep_conc[opp]  # long forward balls into the final third: in behind or not
                        d[0] += ok
                        d[1] += 1
                        if ok:
                            d[2].append(e.event_id)
                if e.type in ("pass", "long_ball", "carry") and rel_x(e, e.team, m.home) < 52.5:
                    self.style[e.team][0] += e.type == "long_ball"
                    self.style[e.team][1] += 1
            for team in (m.home, m.away):
                self.bib_conc[team][1].add(m.match_id)
                self.late_xg[team][3].add(m.match_id)
        # league references
        gk_tot = sum(v[1] for v in self.gk.values())
        self.ref_gk_short = sum(v[0] for v in self.gk.values()) / max(gk_tot, 1)
        by_pos = defaultdict(lambda: [0, 0])
        for pid, (loss, n, _) in self.press.items():
            pos = self.positions.get(pid, "CM")
            by_pos[pos][0] += loss
            by_pos[pos][1] += n
        self.ref_press = {pos: 100.0 * a / max(b, 1) for pos, (a, b) in by_pos.items()}
        lanes = [0, 0, 0]
        for v in self.entries_conc.values():
            for k in range(3):
                lanes[k] += v[0][k]
        self.ref_lane = [x / max(sum(lanes), 1) for x in lanes]
        far = [sum(v["far_post"][0] for v in self.corners_conc.values()),
               sum(v["far_post"][1] for v in self.corners_conc.values())]
        near = [sum(v["near_post"][0] for v in self.corners_conc.values()),
                sum(v["near_post"][1] for v in self.corners_conc.values())]
        self.ref_far = far[0] / max(far[1], 1)
        self.ref_near = near[0] / max(near[1], 1)
        conceded = sum(len(v[1]) for v in self.bib_conc.values())
        self.ref_bib = sum(v[0] for v in self.bib_conc.values()) / max(conceded, 1)
        late_ratio = [self._late_ratio(t) for t in self.late_xg]
        self.ref_late = sum(late_ratio) / max(len(late_ratio), 1)
        self.ref_fwd = [sum(v[k][0] for v in self.fwd_conc.values()) / max(sum(v[k][1] for v in self.fwd_conc.values()),
                                                                        1) for k in range(3)]
        self.ref_deep = sum(v[0] for v in self.deep_conc.values()) / max(sum(v[1] for v in self.deep_conc.values()), 1)
        excess = [self._gk_excess(t) for t in self.gk if self.gk[t][1]]
        self.ref_gk_excess = sum(excess) / max(len(excess), 1)

    def _gk_excess(self, team: str) -> float:
        """Goal-kick short share minus the team's own open-play short share in its half."""
        short, n, _ = self.gk[team]
        long_balls, actions = self.style[team]
        return short / max(n, 1) - (1 - long_balls / max(actions, 1))

    def _late_ratio(self, team: str) -> float:
        late, early, _, _, _ = self.late_xg[team]
        # xG per 15 minutes late (75-90) vs before (0-75)
        return (late / 15.0) / max(early / 75.0, 1e-6)

    # ------------------------------------------------------------------ claims
    def build_up(self, team: str) -> list[Claim]:
        short, n, ids = self.gk[team]
        share_ci = wilson(short, n)
        excess = self._gk_excess(team)
        half = Z90 * math.sqrt(max(short / max(n, 1) * (1 - short / max(n, 1)), 1e-4) / max(n, 1))
        return [_claim(f"c_sc_{team}_gk_short", "goal_kick_short_share", short / max(n, 1), team, n,
                       self.ref_gk_short, "goal_kicks", ids, interval=share_ci),
                _claim(f"c_sc_{team}_gk_vs_play", "goal_kick_short_vs_open_play", excess, team, n,
                       self.ref_gk_excess, "goal_kicks", ids, label="goal kicks short minus open-play short share",
                       interval=(excess - half, excess + half))]

    def _expected_rate(self, player_id: str) -> float | None:
        """Position- and team-adjusted reference: league rate at the player's position times the team factor
        (teammates' rate / league rate). A full-back of a press-resistant team is compared with that team's level."""
        team = player_id.split("-")[0]
        pos = self.positions.get(player_id, "CM")
        t_loss = t_n = l_loss = l_n = 0
        for pid, (lo, k, _) in self.press.items():
            if self.positions.get(pid) == "GK":
                continue
            l_loss += lo
            l_n += k
            if pid != player_id and pid.startswith(f"{team}-"):
                t_loss += lo
                t_n += k
        if not t_n or not l_n or pos not in self.ref_press:
            return None
        return self.ref_press[pos] * ((t_loss / t_n) / (l_loss / l_n))

    def player_pressure(self, player_id: str) -> list[Claim]:
        """Losses per 100 pressured receptions vs a position- and team-adjusted reference (league_ref)."""
        loss, n, ids = self.press[player_id]
        team = player_id.split("-")[0]
        pos = self.positions.get(player_id, "CM")
        return [_claim(f"c_sc_{player_id}_press", "losses_per_100_pressured_receptions", 100.0 * loss / max(n, 1),
                       team, n, self._expected_rate(player_id), "rate", ids, player_id=player_id,
                       label=f"{pos}, adjusted for position and team", interval=wilson(loss, n, 100.0))]

    def _press_z(self, pid: str) -> float:
        loss, n, _ = self.press[pid]
        p0 = (self._expected_rate(pid) or 1.0) / 100.0
        return (loss - n * p0) / math.sqrt(max(n * p0 * (1 - p0), 1e-9))

    def pressure_outliers(self, team: str, top: int = 3) -> list[Claim]:
        """The `top` outfield players whose losses under pressure deviate most, measured in standard errors."""
        players = [pid for pid in self.press if pid.startswith(f"{team}-") and self.press[pid][1] >= MIN_N["rate"]
                   and self.positions.get(pid) != "GK"]
        return [c for pid in sorted(players, key=lambda p: (-self._press_z(p), p))[:top]
                for c in self.player_pressure(pid)]

    def channels(self, team: str) -> list[Claim]:
        lanes, ids = self.entries_conc[team]
        total = sum(lanes)
        shares = [_claim(f"c_sc_{team}_entries_{LANE_NAME[k]}", "entries_conceded_share", lanes[k] / max(total, 1),
                         team, total, self.ref_lane[k], "entries", ids, label=f"{LANE_NAME[k]} channel",
                         interval=wilson(lanes[k], total)) for k in (0, 2)]
        fwd = self.fwd_conc[team]
        success = [_claim(f"c_sc_{team}_fwd_{LANE_NAME[k]}", "forward_success_conceded_share",
                          fwd[k][0] / max(fwd[k][1], 1), team, fwd[k][1], self.ref_fwd[k], "attempts", [],
                          label=f"{LANE_NAME[k]} channel", interval=wilson(fwd[k][0], fwd[k][1])) for k in (0, 2)]
        return shares + success

    def set_pieces(self, team: str) -> list[Claim]:
        c = self.corners_conc[team]
        out = []
        for d, ref, label in (("far_post", self.ref_far, "back post"), ("near_post", self.ref_near, "near post")):
            won, n = c[d]
            out.append(_claim(f"c_sp_{team}_{d}", "first_contact_conceded_share", won / max(n, 1), team, n, ref,
                              "corners", c["ids"], label=label, interval=wilson(won, n)))
        return out

    def balls_in_behind(self, team: str) -> list[Claim]:
        count, matches = self.bib_conc[team]
        n = len(matches)
        succ, att, ids = self.deep_conc[team]
        return [_claim(f"c_sc_{team}_bib", "balls_in_behind_conceded_per_match", count / max(n, 1), team, n,
                       self.ref_bib, "matches", [], interval=poisson_rate(count, n)),
                _claim(f"c_sc_{team}_deep", "deep_ball_success_conceded_share", succ / max(att, 1), team, att,
                       self.ref_deep, "attempts", ids, label="long forward balls into the final third that arrive",
                       interval=wilson(succ, att))]

    def fade(self, team: str) -> list[Claim]:
        _, _, shots, _, early = self.late_xg[team]
        ratio = self._late_ratio(team)
        spread = math.exp(Z90 * math.sqrt(1 / max(shots, 1) + 1 / max(early, 1)))  # log-normal approximation
        return [_claim(f"c_sc_{team}_late", "late_xg_conceded_ratio", ratio, team, shots, self.ref_late, "shots", [],
                       interval=(ratio / spread, ratio * spread))]

    def tendencies(self, team: str, aspect: str = "all") -> list[Claim]:
        groups = {
            "build_up": self.build_up, "pressure": self.pressure_outliers, "channels": self.channels,
            "set_pieces": self.set_pieces, "behind": self.balls_in_behind, "fade": self.fade,
        }
        if aspect in groups:
            return groups[aspect](team)
        return [c for fn in groups.values() for c in fn(team)]
