"""Build the H0 fixtures: a HAND-SCRIPTED fake match (not the simulator) plus plans, duel and canned tools.

Every number here is ILLUSTRATIVE. The match is scripted to tell the v6 demo story (KES 0-1 at half-time,
HAR switches to long goal kicks at 27', the duel, KES wins 2-1) so that agents and UI can be built before
the real simulator exists. Counts that can be derived from the scripted events (score, KPI values,
goal-kick shares) ARE derived from them, so the fixtures are internally consistent.

    python -m fixtures.build_fixtures          # write fixtures/*.json
    python -m fixtures.build_fixtures --check  # fail if committed fixtures are stale
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from contracts import (
    AttackDirection,
    Attributes,
    Cell,
    Claim,
    Cue,
    Duel,
    DuelBroadcast,
    EstimatedOption,
    Event,
    I18nText,
    Kpi,
    KpiStatus,
    LeverChanges,
    Levers,
    MatchBundle,
    MatchMeta,
    Matrix,
    OpponentOptionsEstimate,
    Option,
    Plan,
    PlanBAction,
    PlanBCondition,
    PlanBRule,
    Player,
    Regret,
    RenderFrame,
    RevealedChoice,
    Seal,
    SealedChoice,
    Snapshot,
    Squad,
    Squads,
    Sub,
    TeamDuelPrivate,
    TraceStep,
    zone_index,
)
from contracts.eval_only import HiddenTrait, TeamTruth, Truth
from contracts.sealing import choice_digest, plan_digest
from engine import duel as duel_math

FIXTURE_DIR = Path(__file__).parent
MATCH_ID = "m-demo-001"
HOME, AWAY = "KES", "HAR"
HALF_T = 2700.0
FULL_T = 5400.0
INVALID_SUB_ERROR = "KES-14 is not on the pitch (bench player cannot be subbed off)"

# --------------------------------------------------------------------------------------------- squads

ROLES = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "ST", "LW"]
BENCH = ["GK", "CB", "LB", "CM", "RW", "LW", "ST"]
# Formation template in the attacking frame (x from own goal), used only for the visual layer.
TEMPLATE = {
    "GK": (5, 34), "RB": (30, 60), "CB": (24, 42), "LB": (30, 8), "DM": (42, 34), "CM": (52, 46),
    "RW": (70, 60), "ST": (78, 34), "LW": (70, 8),
}
NAMES = {
    HOME: ["Aldous Venn", "Rory Tamsin", "Ezra Halloway", "Milo Quarrie", "Theo Brannock", "Jasper Lund",
           "Callum Reave", "Ilan Mercer", "Dorian Faulk", "Silas Okoro", "Wren Castell", "Bram Ellery",
           "Otis Harrow", "Lev Dunmore", "Fenn Asquith", "Rafe Selden", "Kit Morrow", "Ansel Prior"],
    AWAY: ["Hugo Marsh", "Ned Calloway", "Ivo Strand", "Gideon Peake", "Lorcan Vey", "Tobin Ashgrove",
           "Emmett Rook", "Ciaran Holt", "Jules Penrose", "Abel Northcott", "Rhys Tallow", "Basil Wren",
           "Oren Pike", "Linus Garrow", "Teo Calder", "Monty Sable", "Ash Fairlie", "Quin Dorsey"],
}


def build_squads() -> Squads:
    rng = random.Random(11)
    teams = {}
    for code, name, short in ((HOME, "Kestrel Athletic", "Kestrel"), (AWAY, "Harbourside United", "Harbourside")):
        players = []
        for k, role in enumerate(ROLES + BENCH):
            def a(base: int) -> int:
                return max(30, min(95, base + rng.randint(-8, 8)))
            players.append(Player(
                player_id=f"{code}-{k + 1}", name=NAMES[code][k], shirt=k + 1, position=role, starter=k < 11,
                attributes=Attributes(
                    pace=a(72 if role in ("RW", "LW", "ST", "RB", "LB") else 62),
                    passing=a(74 if role in ("DM", "CM") else 64),
                    stamina=a(70), press_resistance=a(68 if role != "GK" else 55),
                    aerial=a(76 if role in ("CB", "ST", "GK") else 58),
                    finishing=a(76 if role in ("ST", "RW", "LW") else 45),
                ),
            ))
        teams[code] = Squad(team=code, name=name, short_name=short, players=players)
    return Squads(teams=teams)


# ------------------------------------------------------------------------------------- scripted match

class MatchScript:
    """Writes coherent events: possession continuity, increasing time, absolute coordinates."""

    def __init__(self, squads: Squads):
        self.rng = random.Random(7)
        self.squads = squads
        self.events: list[Event] = []
        self.t = 0.0
        self.possession = 0
        self.score = {HOME: 0, AWAY: 0}

    # -- helpers
    def period(self) -> int:
        return 1 if self.t < HALF_T else 2

    def positive_x(self, team: str) -> bool:
        return (team == HOME) == (self.period() == 1)

    def abs_x(self, team: str, rel_x: float) -> float:
        rel_x = max(0.5, min(104.5, rel_x))
        return round(rel_x if self.positive_x(team) else 105.0 - rel_x, 1)

    def player(self, team: str, role: str, nth: int = 0) -> str:
        ids = [p.player_id for p in self.squads.teams[team].players if p.starter and p.position == role]
        return ids[nth % len(ids)]

    def outfield(self, team: str) -> list[str]:
        return [p.player_id for p in self.squads.teams[team].players if p.starter and p.position != "GK"]

    def emit(self, type_: str, team: str, player: str | None, rel: tuple[float, float],
             end_rel: tuple[float, float] | None = None, dt: tuple[float, float] = (2.5, 4.5), **kw: Any) -> Event:
        self.t += self.rng.uniform(*dt)
        if self.events:  # strictly increasing clock after rounding
            self.t = max(self.t, self.events[-1].t + 0.1)
        x, y = self.abs_x(team, rel[0]), round(max(0.5, min(67.5, rel[1])), 1)
        ev = Event(
            event_id=f"e{len(self.events) + 1:04d}", match_id=MATCH_ID, t=round(self.t, 1), period=self.period(),
            minute=int(self.t // 60), possession_id=self.possession, type=type_, team=team, player_id=player,
            zone=zone_index(x, y), x=x, y=y,
            end_x=self.abs_x(team, end_rel[0]) if end_rel else None,
            end_y=round(max(0.5, min(67.5, end_rel[1])), 1) if end_rel else None, **kw,
        )
        self.events.append(ev)
        return ev

    def other(self, team: str) -> str:
        return AWAY if team == HOME else HOME

    # -- building blocks
    def passes(self, team: str, carrier: str, rel: list[float], n: int, pressed: bool = False) -> str:
        for _ in range(n):
            receiver = self.rng.choice([p for p in self.outfield(team) if p != carrier])
            end = (rel[0] + self.rng.uniform(4, 14), self.rng.uniform(8, 60))
            if pressed and self.rng.random() < 0.5:
                self.emit("pressure", self.other(team), self.rng.choice(self.outfield(self.other(team))),
                          (105 - rel[0], 68 - rel[1]), dt=(0.8, 1.5))
            self.emit("pass", team, carrier, (rel[0], rel[1]), end, receiver_id=receiver, outcome="success",
                      under_pressure=pressed)
            carrier, rel[0], rel[1] = receiver, end[0], end[1]
        return carrier

    def lose_ball(self, team: str, carrier: str, rel: list[float], winner: str | None = None,
                  pressed: bool = False, kind: str = "interception") -> tuple[str, str, list[float]]:
        end = (rel[0] + self.rng.uniform(5, 12), self.rng.uniform(8, 60))
        self.emit("pass", team, carrier, (rel[0], rel[1]), end, outcome="fail", under_pressure=pressed)
        defender_team = self.other(team)
        winner = winner or self.rng.choice(self.outfield(defender_team))
        drel = [105 - end[0], 68 - end[1]]
        self.emit(kind, defender_team, winner, (drel[0], drel[1]), outcome="won", dt=(0.5, 1.2))
        self.possession += 1
        self.emit("possession_change", defender_team, winner, (drel[0], drel[1]), dt=(0.1, 0.4))
        return defender_team, winner, drel

    def shoot(self, team: str, carrier: str, rel: list[float], outcome: str, body: str = "right_foot",
              set_piece_ref: str | None = None) -> None:
        self.emit("shot", team, carrier, (rel[0], rel[1]), (105, 34), outcome=outcome, body_part=body,
                  set_piece_ref=set_piece_ref)
        if outcome == "goal":
            self.score[team] += 1
            self.emit("goal", team, carrier, (rel[0], rel[1]), dt=(0.1, 0.3), outcome="goal", body_part=body,
                      set_piece_ref=set_piece_ref)

    def kick_off(self, team: str) -> tuple[str, str, list[float]]:
        self.possession += 1
        st = self.player(team, "ST")
        self.emit("kick_off", team, st, (52.5, 34), dt=(20, 40) if self.events else (0, 0.1))
        return team, st, [52.5, 34.0]

    def generic(self, team: str, carrier: str, rel: list[float]) -> tuple[str, str, list[float]]:
        """Open-play possession: a few passes, then lost, or a saved/off-target shot."""
        self.t += self.rng.uniform(45, 75)  # open play is sparse on purpose: only key moments are detailed
        pressed = team == AWAY and self.t < HALF_T and rel[0] < 40  # KES presses high in the first half
        carrier = self.passes(team, carrier, rel, self.rng.randint(2, 4), pressed=pressed)
        while rel[0] < 45:  # open-play losses happen in midfield; high turnovers are the scripted ones
            carrier = self.passes(team, carrier, rel, 1)
        if rel[0] > 75 and self.rng.random() < 0.35:
            self.shoot(team, carrier, rel, "off_target")
            opp = self.other(team)
            gk = self.player(opp, "GK")
            self.possession += 1
            self.emit("goal_kick", opp, gk, (6, 34), (25, 20), outcome="success", dt=(15, 25))
            return opp, self.player(opp, "CB"), [25.0, 20.0]
        return self.lose_ball(team, carrier, rel, pressed=pressed)

    def goal_kick(self, team: str, long: bool) -> tuple[str, str, list[float]]:
        self.possession += 1
        gk = self.player(team, "GK")
        if long:
            target = self.player(team, "ST")
            end = (62.0, self.rng.uniform(20, 48))
            self.emit("goal_kick", team, gk, (6, 34), end, receiver_id=target, outcome="success", dt=(12, 20))
            return team, target, [end[0], end[1]]
        cb = self.player(team, "CB", self.rng.randint(0, 1))
        end = (18.0, self.rng.uniform(15, 53))
        self.emit("goal_kick", team, gk, (6, 34), end, receiver_id=cb, outcome="success", dt=(12, 20))
        return team, cb, [end[0], end[1]]

    def high_turnover_on_lb(self) -> tuple[str, str, list[float]]:
        """HAR builds short, the ball goes to their left-back HAR-5 under pressure, KES wins it high."""
        team, carrier, rel = self.goal_kick(AWAY, long=False)
        lb = self.player(AWAY, "LB")
        self.emit("pressure", HOME, self.player(HOME, "RW"), (105 - rel[0], 68 - rel[1]), dt=(1, 2))
        self.emit("pass", AWAY, carrier, (rel[0], rel[1]), (24, 6), receiver_id=lb, outcome="success",
                  under_pressure=True)
        return self.lose_ball(AWAY, lb, [24.0, 6.0], winner=self.player(HOME, "RW"), pressed=True, kind="tackle")

    def corner(self, team: str, delivery: str, outcome: str, scorer_role: str = "CB") -> None:
        self.possession += 1
        y_post = 40.0 if delivery == "far_post" else 28.0
        c = self.emit("corner", team, self.player(team, "RW"), (104.5, 67.5), (99.5, y_post), outcome="success",
                      dt=(20, 30))
        header = self.player(team, scorer_role)
        self.shoot(team, header, [99.0, y_post], outcome, body="head", set_piece_ref=c.event_id)

    # -- the story
    def run(self) -> list[Event]:
        keys1 = [(240, "gk_short"), (480, "ht_lb"), (780, "gk_short"), (840, "ht_lb"), (1080, "gk_short"),
                 (1140, "ht_lb"), (1320, "corner_kes_miss"), (1440, "ht_lb"), (1500, "gk_short"),
                 (1640, "gk_long"), (1740, "gk_long"), (1980, "gk_long"), (2160, "gk_short"),
                 (2340, "har_goal"), (2520, "gk_long")]
        keys2 = [(3000, "gk_long"), (3300, "gk_long"), (3480, "kes_corner_goal"), (3900, "gk_long"),
                 (4300, "gk_long"), (4700, "gk_long"), (5040, "kes_goal"), (5250, "gk_long")]
        state = self.kick_off(HOME)
        for end_t, keys in ((HALF_T, keys1), (FULL_T, keys2)):
            queue = list(keys)
            while self.t < end_t - 180:  # leave room so no scripted sequence crosses half-time
                if queue and self.t >= queue[0][0]:
                    _, key = queue.pop(0)
                    state = self.key_moment(key, state)
                else:
                    state = self.generic(*state)
            if end_t == HALF_T:
                assert self.t < HALF_T, "first half overran"
                self.t = HALF_T
                state = self.kick_off(AWAY)
        return self.events

    def kes_attack(self, state: tuple[str, str, list[float]]) -> tuple[str, list[float]]:
        """Bring the current possession to a KES attack near HAR's box, keeping continuity."""
        team, carrier, rel = state
        if team == AWAY:
            while rel[0] < 45:  # HAR loses it in midfield, not as a scripted high turnover
                carrier = self.passes(AWAY, carrier, rel, 1)
            team, carrier, rel = self.lose_ball(AWAY, carrier, rel)
        while rel[0] < 80:
            carrier = self.passes(HOME, carrier, rel, 1)
        return carrier, rel

    def to_har_goal_kick(self, state: tuple[str, str, list[float]]) -> None:
        carrier, rel = self.kes_attack(state)
        self.shoot(HOME, carrier, rel, "off_target")

    def to_kes_corner(self, state: tuple[str, str, list[float]]) -> None:
        carrier, rel = self.kes_attack(state)
        self.shoot(HOME, carrier, rel, "blocked")

    def key_moment(self, key: str, state: tuple[str, str, list[float]]) -> tuple[str, str, list[float]]:
        if key in ("gk_short", "gk_long", "ht_lb", "har_goal"):
            self.to_har_goal_kick(state)
        if key in ("corner_kes_miss", "kes_corner_goal"):
            self.to_kes_corner(state)
        if key == "gk_short":
            return self.goal_kick(AWAY, long=False)
        if key == "gk_long":
            team, carrier, rel = self.goal_kick(AWAY, long=True)
            return self.lose_ball(team, carrier, rel)
        if key == "ht_lb":
            return self.high_turnover_on_lb()
        if key == "corner_kes_miss":
            self.corner(HOME, "far_post", "off_target")
            return self.goal_kick(AWAY, long=False)
        if key == "har_goal":
            team, carrier, rel = self.goal_kick(AWAY, long=True)
            self.emit("long_ball", AWAY, carrier, (rel[0], rel[1]), (88, 30),
                      receiver_id=self.player(AWAY, "ST"), outcome="success")
            self.shoot(AWAY, self.player(AWAY, "ST"), [90.0, 31.0], "goal")
            return self.kick_off(HOME)
        if key == "kes_corner_goal":
            self.corner(HOME, "far_post", "goal")
            return self.kick_off(AWAY)
        if key == "kes_goal":
            carrier, rel = self.kes_attack(state)
            self.emit("cross", HOME, carrier, (92, 62), (97, 36), receiver_id=self.player(HOME, "ST"),
                      outcome="success")
            self.shoot(HOME, self.player(HOME, "ST"), [97.0, 36.0], "goal")
            return self.kick_off(AWAY)
        raise ValueError(key)


# ----------------------------------------------------------------------------------- plans and claims

def C(claim_id: str, type_: str, metric: str, value: float | int | str, **kw: Any) -> Claim:
    return Claim(claim_id=claim_id, type=type_, metric=metric, value=value, illustrative=True, **kw)


def goal_kick_long_share(events: list[Event], team: str, t0: float, t1: float) -> tuple[float, int]:
    gks = [e for e in events if e.type == "goal_kick" and e.team == team and t0 <= e.t < t1]
    long = [e for e in gks if e.end_x is not None and abs(e.end_x - e.x) > 40]
    return (round(len(long) / len(gks), 2) if gks else 0.0), len(gks)


def build_plans() -> dict[str, Plan]:
    kes = Plan(
        plan_id="KES-A", team=HOME, opponent=AWAY,
        name=I18nText(en="Squeeze the left-back", es="Asfixiar a su lateral izquierdo"),
        levers=Levers(press_height="high", press_target="HAR-5", build_up="mixed", attack_channel="right",
                      corner_delivery="far_post"),
        lever_evidence={"press_height": ["c_sc_01"], "press_target": ["c_sc_03"], "attack_channel": ["c_sc_05"],
                        "corner_delivery": ["c_sp_02"]},
        kpis=[Kpi(id="k1", metric="high_turnovers", target=">=6", by_minute=45),
              Kpi(id="k2", metric="final_third_entries_share", params={"channel": "right"}, target=">=0.40"),
              Kpi(id="k3", metric="set_piece_xg", target=">=0.30", by_minute=90)],
        plan_b=[PlanBRule(if_=PlanBCondition(kpi="k1", status="failing", after_minute=30),
                          then=PlanBAction(levers=LeverChanges(press_height="mid")))],
        subs_plan=[Sub(window="60-65", out="KES-11", into="KES-17")],
        valuation="c_sim_21",
    )
    har = Plan(
        plan_id="HAR-A", team=AWAY, opponent=HOME,
        name=I18nText(en="Go over the press", es="Saltar la presión"),
        levers=Levers(press_height="mid", build_up="short", attack_channel="center"),
        lever_evidence={"build_up": ["c_sc_11"], "attack_channel": ["c_sc_12"]},
        kpis=[Kpi(id="h1", metric="final_third_entries_share", params={"channel": "center"}, target=">=0.35"),
              Kpi(id="h2", metric="balls_in_behind_conceded", target="<=3", by_minute=90)],
        plan_b=[PlanBRule(if_=PlanBCondition(kpi="h1", status="failing", after_minute=25),
                          then=PlanBAction(levers=LeverChanges(build_up="direct")))],
        valuation="c_sim_22",
    )
    for plan in (kes, har):
        plan.sealed = Seal(at="14:58:03", sha256=plan_digest(plan))
    return {HOME: kes, AWAY: har}


def scouting_claims() -> list[Claim]:
    return [
        C("c_sc_01", "observed_tendency", "goal_kick_short_share", 0.78, team=AWAY, n=64, league_ref=0.55,
          evidence=["season:HAR:goal_kicks"]),
        C("c_sc_03", "observed_tendency", "losses_per_100_pressured_receptions", 31.7, team=AWAY,
          player_id="HAR-5", n=41, league_ref=15.2, evidence=["season:HAR-5:pressured_receptions"]),
        C("c_sc_05", "observed_tendency", "crosses_conceded_share", 0.46, team=AWAY, label="left channel", n=88,
          league_ref=0.33, evidence=["season:HAR:crosses_conceded"]),
        C("c_sp_02", "observed_tendency", "first_contact_conceded_share", 0.58, team=AWAY, label="back post",
          n=19, league_ref=0.41, evidence=["season:HAR:corners_conceded"]),
        C("c_sc_11", "observed_tendency", "high_turnovers_conceded_per_match", 9.1, team=HOME, n=8,
          league_ref=11.4, evidence=["season:KES:press"]),
        C("c_sc_12", "observed_tendency", "central_entries_conceded_share", 0.41, team=HOME, n=96,
          league_ref=0.36, evidence=["season:KES:entries_conceded"]),
        C("c_sim_21", "sim_valuation", "delta_xpts_vs_default_plan", 0.21, team=HOME, n=500, interval_low=0.13,
          interval_high=0.29),
        C("c_sim_22", "sim_valuation", "delta_xpts_vs_default_plan", 0.09, team=AWAY, n=500, interval_low=0.01,
          interval_high=0.17),
    ]


# ------------------------------------------------------------------------------------------- the duel

# Illustrative KES gain (xPts) vs the Stay/Stay cell. Rows = KES options, cols = HAR options.
TRUE_DELTA = [[0.00, 0.12, -0.03], [0.14, 0.04, 0.05], [-0.04, 0.08, 0.10]]
KES_BELIEVED_DELTA = [[0.01, 0.11, -0.02], [0.13, 0.05, 0.06], [-0.03, 0.07, 0.09]]
HAR_BELIEVED_DELTA = [[0.00, 0.15, -0.03], [0.11, 0.05, 0.07], [-0.02, 0.06, 0.09]]  # rows HAR, cols KES est.
BASE_XPTS = {HOME: 0.80, AWAY: 2.00}  # Stay/Stay at 0-1 down; HAR value is mirrored for illustration only.
CI_HALF = 0.05


def cell(kes_delta: float, claim_id: str) -> Cell:
    k, h = round(BASE_XPTS[HOME] + kes_delta, 2), round(BASE_XPTS[AWAY] - kes_delta, 2)
    return Cell(xpts={HOME: k, AWAY: h},
                ci90={HOME: (round(k - CI_HALF, 2), round(k + CI_HALF, 2)),
                      AWAY: (round(h - CI_HALF, 2), round(h + CI_HALF, 2))},
                claim_id=claim_id)


def option(option_id: str, team: str, en: str, es: str, intent: str, estimated: bool = False,
           evidence: list[str] | None = None, **changes: Any) -> Option:
    subs = changes.pop("subs", [])
    return Option(option_id=option_id, team=team, label=I18nText(en=en, es=es), intent=intent,
                  lever_changes=LeverChanges(**changes), subs=subs, evidence=evidence or [], estimated=estimated)


def build_duel() -> tuple[Duel, list[Claim]]:
    kes_opts = [
        option("KES-HT-A", HOME, "Stay the course", "Mantener el plan", "stay_the_course"),
        option("KES-HT-B", HOME, "Mid block + back post corners", "Bloque medio + córners al segundo palo",
               "drop_block", evidence=["c201", "c_sp_02"], press_height="mid"),
        option("KES-HT-C", HOME, "Double attacking change", "Doble cambio ofensivo", "attacking_subs",
               evidence=["c_kpi_k1_45"], attack_channel="balanced",
               subs=[Sub(window="HT", out="KES-11", into="KES-17"), Sub(window="HT", out="KES-8", into="KES-16")]),
    ]
    har_opts = [
        option("HAR-HT-X", AWAY, "Stay the course (keep going long)", "Mantener el plan (seguir en largo)",
               "stay_the_course"),
        option("HAR-HT-Y", AWAY, "Back to short build-up", "Volver a salir en corto", "short_build_up",
               build_up="short"),
        option("HAR-HT-Z", AWAY, "Low block to protect the lead", "Bloque bajo para proteger el 1-0",
               "protect_lead", press_height="low"),
    ]
    kes_est = [  # KES analyst's guess of HAR (never sees HAR's real options)
        (option("KES-EST-HAR-1", AWAY, "They keep going long", "Siguen en largo", "stay_the_course", True), 0.50),
        (option("KES-EST-HAR-2", AWAY, "They go back to short", "Vuelven al corto", "short_build_up", True,
                build_up="short"), 0.15),
        (option("KES-EST-HAR-3", AWAY, "They sit deep", "Se encierran", "protect_lead", True,
                press_height="low"), 0.35),
    ]
    har_est = [
        (option("HAR-EST-KES-1", HOME, "They keep pressing high", "Siguen presionando arriba", "stay_the_course",
                True), 0.55),
        (option("HAR-EST-KES-2", HOME, "They drop into a mid block", "Bajan a bloque medio", "drop_block", True,
                press_height="mid"), 0.30),
        (option("HAR-EST-KES-3", HOME, "They throw on attackers", "Meten atacantes", "attacking_subs", True,
                attack_channel="balanced"), 0.15),
    ]
    claims: list[Claim] = []

    def make_matrix(mid: str, kind: str, believer: str | None, row_team: str, rows: list[Option],
                    cols: list[Option], deltas: list[list[float]], probs: list[float] | None,
                    kes_is_row: bool) -> Matrix:
        cells = []
        for i, r in enumerate(rows):
            row = []
            for j, c in enumerate(cols):
                cid = f"cm_{mid}_{i}{j}"
                cl = cell(deltas[i][j], cid)
                row.append(cl)
                kes_opt, har_opt = (r, c) if kes_is_row else (c, r)
                claims.append(C(cid, "sim_matrix_cell", "xpts_delta_vs_stay_stay", deltas[i][j], team=HOME,
                                n=300 if kind == "believed" else 500,
                                interval_low=round(deltas[i][j] - CI_HALF, 2),
                                interval_high=round(deltas[i][j] + CI_HALF, 2),
                                label=f"{kes_opt.option_id} x {har_opt.option_id}"))
            cells.append(row)
        m = Matrix(matrix_id=mid, match_id=MATCH_ID, kind=kind, believer=believer, row_team=row_team,
                   col_team=AWAY if row_team == HOME else HOME, rows=[o.option_id for o in rows],
                   cols=[o.option_id for o in cols], col_probs=probs, cells=cells,
                   R=300 if kind == "believed" else 500, seed=4501, illustrative=True)
        if kind == "believed":
            m.readings = {believer: duel_math.reading(m, believer, probs)}
        else:
            m.readings = {t: duel_math.reading(m, t) for t in (HOME, AWAY)}
        return m

    kes_believed = make_matrix("mx-believed-KES", "believed", HOME, HOME, kes_opts, [o for o, _ in kes_est],
                               KES_BELIEVED_DELTA, [p for _, p in kes_est], kes_is_row=True)
    har_believed = make_matrix("mx-believed-HAR", "believed", AWAY, AWAY, har_opts, [o for o, _ in har_est],
                               HAR_BELIEVED_DELTA, [p for _, p in har_est], kes_is_row=False)
    true = make_matrix("mx-true", "true", None, HOME, kes_opts, har_opts, TRUE_DELTA, None, kes_is_row=True)

    choices = {HOME: ("KES-HT-B", "a3f1c09e5b7d2468a3f1c09e5b7d2468", "safe_pick"),
               AWAY: ("HAR-HT-Z", "9c2e7b4a1d6f38059c2e7b4a1d6f3805", "best_guess")}
    # The fixture's choices must be what each rule picks on each bench's OWN believed matrix.
    assert kes_believed.readings[HOME].safe_pick == choices[HOME][0]
    assert har_believed.readings[AWAY].best_guess == choices[AWAY][0]

    private = {}
    for team, opts, est, believed in ((HOME, kes_opts, kes_est, kes_believed), (AWAY, har_opts, har_est, har_believed)):
        opp = AWAY if team == HOME else HOME
        est_claim = f"c_est_{team}"
        claims.append(C(est_claim, "opponent_estimate", "opponent_option_probabilities",
                        " / ".join(f"{o.label.en} {p:.0%}" for o, p in est), team=team,
                        evidence=["c201"] if team == HOME else ["c_kpi_k1_45"]))
        option_id, salt, _ = choices[team]
        private[team] = TeamDuelPrivate(
            team=team, options=opts,
            opponent_estimate=OpponentOptionsEstimate(
                estimator=team, opponent=opp, claims=[est_claim],
                options=[EstimatedOption(option=o, probability=p) for o, p in est]),
            believed_matrix=believed,
            choice=SealedChoice(team=team, sealed_at="15:47:10",
                                sha256=choice_digest(MATCH_ID, team, option_id, salt)),
        )
    regrets = {}
    for team in (HOME, AWAY):
        opp = AWAY if team == HOME else HOME
        best, value = duel_math.regret(true, team, choices[team][0], choices[opp][0])
        cid = f"c_rg_{team}"
        claims.append(C(cid, "regret", "regret_xpts", round(value, 2), team=team, n=500,
                        label=f"best response {best}"))
        regrets[team] = Regret(team=team, chosen=choices[team][0], opponent_chosen=choices[opp][0],
                               best_response=best, regret_xpts=round(value, 2), claim_id=cid)
    duel = Duel(
        match_id=MATCH_ID, private=private, illustrative=True,
        broadcast=DuelBroadcast(
            revealed={t: RevealedChoice(team=t, option_id=o, salt=s, rule=r) for t, (o, s, r) in choices.items()},
            true_matrix=true, regret=regrets),
    )
    return duel, claims


# ------------------------------------------------------------------------------- snapshots and extras

HIGH_TURNOVER_REL_X = 65.0  # ball won within 40 m of the opponent's goal


def high_turnovers(events: list[Event], team: str, upto_t: float) -> int:
    """Ball won by `team` within 40 m of the opponent's goal (absolute frame -> team frame)."""
    n = 0
    for e in events:
        if e.t > upto_t or e.team != team or e.type not in ("tackle", "interception"):
            continue
        pos_x = (team == HOME) == (e.period == 1)
        if (e.x if pos_x else 105 - e.x) >= HIGH_TURNOVER_REL_X:
            n += 1
    return n


def build_snapshots(events: list[Event], squads: Squads, plans: dict[str, Plan]) -> list[Snapshot]:
    snaps = []
    on_pitch = {t: [p.player_id for p in squads.teams[t].players if p.starter] for t in (HOME, AWAY)}
    for minute in range(0, 91):
        t = minute * 60.0 + (0.0 if minute < 90 else 1e9)
        period = 1 if minute <= 45 else 2
        score = {HOME: 0, AWAY: 0}
        for e in events:
            if e.type == "goal" and e.t <= t:
                score[e.team] += 1
        levers = {HOME: plans[HOME].levers.model_copy(), AWAY: plans[AWAY].levers.model_copy()}
        if minute >= 27:
            levers[AWAY].build_up = "direct"  # HAR Plan B fired
        if minute > 45:
            levers[HOME].press_height = "mid"  # KES chose option B
            levers[AWAY].press_height = "low"  # HAR chose option Z
        ht = high_turnovers(events, HOME, t)
        expected = round(6 * min(minute, 45) / 45, 1)
        status = ("insufficient_evidence" if minute < 10 else
                  "on_track" if ht >= expected - 0.75 else "at_risk" if ht >= expected - 2 else "failing")
        kpis = [KpiStatus(plan_id="KES-A", kpi_id="k1", team=HOME, value=ht, expected=expected,
                          band_low=max(0.0, expected - 1.5), band_high=expected + 1.5,
                          n=sum(1 for e in events if e.type == "pressure" and e.team == HOME and e.t <= t),
                          status=status)] if minute <= 45 else []
        cond = {}
        for team in (HOME, AWAY):
            drop = (0.0035 if team == HOME and minute <= 45 else 0.0025) * minute
            for pid in on_pitch[team]:
                cond[pid] = round(max(0.0, 1.0 - drop), 3)
        snaps.append(Snapshot(match_id=MATCH_ID, minute=minute, period=period, score=score,
                              subs_used={HOME: 0, AWAY: 0}, sub_windows_used={HOME: 0, AWAY: 0},
                              on_pitch=on_pitch, condition_est=cond, active_levers=levers, kpis=kpis))
    return snaps


def build_render_frames(events: list[Event], squads: Squads) -> list[RenderFrame]:
    """Very rough visual layer for UI development: template shape shifted toward the ball."""
    frames = []
    starters = {t: [p for p in squads.teams[t].players if p.starter] for t in (HOME, AWAY)}
    for e in events:
        players = {}
        for team in (HOME, AWAY):
            pos_x = (team == HOME) == (e.period == 1)
            ball_rel = e.x if pos_x else 105 - e.x
            seen: dict[str, int] = {}
            for p in starters[team]:
                bx, by = TEMPLATE[p.position]
                k = seen.get(p.position, 0)
                seen[p.position] = k + 1
                if p.position == "CB":
                    by = 42 - 16 * k
                if p.position == "CM":
                    by = 46 - 24 * k
                rx = bx if p.position == "GK" else bx + (ball_rel - 52.5) * 0.45
                rx = max(1.0, min(104.0, rx))
                players[p.player_id] = (round(rx if pos_x else 105 - rx, 1), float(by))
        frames.append(RenderFrame(t=e.t, ball=(e.x, e.y), players=players))
    return frames


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def build_live_claims(events: list[Event], snaps: list[Snapshot]) -> list[Claim]:
    before, n_before = goal_kick_long_share(events, AWAY, 0, 1620)
    after, n_after = goal_kick_long_share(events, AWAY, 1620, HALF_T)
    k1 = snaps[45].kpis[0]
    k1_36 = snaps[36].kpis[0]
    return [
        C("c201", "observed_adaptation", "goal_kick_long_share", after, team=AWAY, minute=27, n=n_after,
          label=f"before 27': {before:.0%} (n={n_before})",
          evidence=[e.event_id for e in events if e.type == "goal_kick" and e.team == AWAY and e.t < HALF_T]),
        C("c_kpi_k1_36", "kpi_status", "high_turnovers", k1_36.value, team=HOME, minute=36, n=k1_36.n,
          target=">=6 by HT", label=k1_36.status),
        C("c_kpi_k1_45", "kpi_status", "high_turnovers", k1.value, team=HOME, minute=45, n=k1.n,
          target=">=6 by HT", label=k1.status),
    ]


def build_cues() -> list[Cue]:
    def cue(cid, t, template, prio, ttl, team, en, es, claims, mode=("casual", "analyst"), **fields):
        return Cue(cue_id=cid, t_match=t, template=template, priority=prio, ttl_s=ttl, team=team, fields=fields,
                   text=I18nText(en=en, es=es), mode=list(mode), claims=claims)
    return [
        cue("q-000-sealed", "0:00", "plan_sealed", 1, 10, None, "Both plans sealed before kick-off.",
            "Los dos planes, sellados antes del pitido inicial.", ["c_sim_21", "c_sim_22"]),
        cue("q-036-kes-risk", "36:04", "plan_alert", 2, 12, HOME,
            "At risk: HAR stopped playing short. High turnovers stuck at {c_kpi_k1_36.value}.",
            "En riesgo: HAR ha dejado de salir en corto. Robos altos estancados en {c_kpi_k1_36.value}.",
            ["c_kpi_k1_36", "c201"], plan="Squeeze the left-back", kpi="high_turnovers", status="{c_kpi_k1_36.label}",
            value="{c_kpi_k1_36.value}", target="{c_kpi_k1_36.target}"),
        cue("q-028-adapt", "28:10", "adaptation_detected", 2, 12, AWAY,
            "HAR now go long from goal kicks: {c201.value} since minute {c201.minute}.",
            "HAR saca ahora en largo: {c201.value} desde el minuto {c201.minute}.", ["c201"]),
        cue("q-045-reveal", "45:00", "duel_reveal", 1, 20, None, "Both benches have sealed their call.",
            "Los dos banquillos han sellado su decisión.", ["c_est_KES", "c_est_HAR"]),
        cue("q-045-matrix", "45:00", "duel_matrix", 1, 30, HOME,
            "KES's best move depends on HAR. The mid-block is the safe pick: it never loses value.",
            "La mejor jugada de KES depende de HAR. El bloque medio es la opción segura: nunca pierde valor.",
            ["cm_mx-true_10", "cm_mx-true_11", "cm_mx-true_12"]),
        cue("q-090-regret", "90:00", "bench_regret", 1, 20, HOME,
            "KES's safe pick left {c_rg_KES.value} xPts on the table.",
            "La opción segura de KES dejó {c_rg_KES.value} xPts sobre la mesa.", ["c_rg_KES"],
            mode=("analyst",)),
    ]


def build_traces() -> list[TraceStep]:
    def tr(i, wf, agent, scope, tool, args, claims, ms, status="ok", msg=None):
        return TraceStep(trace_id=f"tr-{i:03d}", workflow=wf, agent=agent, scope=scope, step=i, tool=tool,
                         args=args, result_claims=claims, duration_ms=ms, status=status, message=msg)
    return [
        tr(1, "prematch", "analyst", HOME, "get_team_tendencies", {"team": AWAY, "aspect": "build_up"},
           ["c_sc_01"], 410),
        tr(2, "prematch", "analyst", HOME, "get_player_profile", {"player_id": "HAR-5"}, ["c_sc_03"], 220),
        tr(3, "prematch", "manager", HOME, "simulate_plan", {"plan_id": "KES-A", "R": 500}, ["c_sim_21"], 3100),
        tr(4, "duel", "manager", HOME, "validate_plan", {"option_id": "KES-HT-C"}, [], 35, "rejected",
           INVALID_SUB_ERROR),
        tr(5, "duel", "manager", HOME, "validate_plan", {"option_id": "KES-HT-C"}, [], 31, "ok"),
        tr(6, "duel", "manager", HOME, "price_matrix", {"R": 300}, ["cm_mx-believed-KES_10"], 2800),
    ]


def build_truth() -> Truth:
    return Truth(season_id="s-fixture", teams={
        AWAY: TeamTruth(team=AWAY, archetype="possession", split="test", traits=[
            HiddenTrait(kind="fb_low_press_resistance", player_id="HAR-5", strength=0.7),
            HiddenTrait(kind="back_post_weak", strength=0.6),
            HiddenTrait(kind="gk_short_bias", strength=0.5)]),
        HOME: TeamTruth(team=HOME, archetype="pressing", split="dev", traits=[
            HiddenTrait(kind="late_fade", strength=0.4),
            HiddenTrait(kind="cb_low_pace", player_id="KES-4", strength=0.5),
            HiddenTrait(kind="weak_channel", side="left", strength=0.3)]),
    })


# ------------------------------------------------------------------------------------- canned tools

def canned(tool: str, scope: str, args: dict, response: Any) -> dict:
    return {"tool": tool, "scope": scope, "args": args, "response": response, "illustrative": True}


def build_tools(bundle: MatchBundle) -> dict[str, dict]:
    claims = {c.claim_id: c.model_dump(mode="json") for c in bundle.claims}
    duel = bundle.duel
    assert duel is not None
    dump = lambda m: m.model_dump(mode="json", by_alias=True)  # noqa: E731
    kes_squad = bundle.squads.teams[HOME]
    return {
        "list_matches.KES": canned("list_matches", HOME, {"team": AWAY},
                                   [{"match_id": f"s-fixture-{k:02d}", "opponent": "XXX"} for k in range(1, 9)]),
        "get_team_tendencies.KES": canned("get_team_tendencies", HOME, {"team": AWAY, "aspect": "build_up"},
                                          [claims["c_sc_01"], claims["c_sc_05"]]),
        "get_player_profile.KES": canned("get_player_profile", HOME, {"player_id": "HAR-5"}, [claims["c_sc_03"]]),
        "get_set_piece_profile.KES": canned("get_set_piece_profile", HOME, {"team": AWAY}, [claims["c_sp_02"]]),
        "get_squad_condition.KES": canned("get_squad_condition", HOME, {"minute": 45},
                                          {"squad": dump(kes_squad), "condition_est": {
                                              k: v for k, v in bundle.snapshots[45].condition_est.items()
                                              if k.startswith("KES-")}}),
        "simulate_plan.KES": canned("simulate_plan", HOME, {"plan_id": "KES-A", "R": 500}, [claims["c_sim_21"]]),
        "estimate_opponent_options.KES": canned("estimate_opponent_options", HOME, {"match_id": MATCH_ID},
                                                dump(duel.private[HOME].opponent_estimate)),
        "estimate_opponent_options.HAR": canned("estimate_opponent_options", AWAY, {"match_id": MATCH_ID},
                                                dump(duel.private[AWAY].opponent_estimate)),
        "price_matrix.KES": canned("price_matrix", HOME, {"match_id": MATCH_ID, "R": 300},
                                   dump(duel.private[HOME].believed_matrix)),
        "price_matrix.HAR": canned("price_matrix", AWAY, {"match_id": MATCH_ID, "R": 300},
                                   dump(duel.private[AWAY].believed_matrix)),
        "seal_choice.KES": canned("seal_choice", HOME, {"match_id": MATCH_ID, "option_id": "KES-HT-B"},
                                  dump(duel.private[HOME].choice)),
        "validate_plan.KES": canned("validate_plan", HOME, {"option_id": "KES-HT-C"},
                                    {"ok": False, "errors": [INVALID_SUB_ERROR]}),
        "get_plan_status.KES": canned("get_plan_status", HOME, {"match_id": MATCH_ID, "minute": 36},
                                      [claims["c_kpi_k1_36"]]),
        "get_true_matrix.KES": canned("get_true_matrix", HOME, {"match_id": MATCH_ID},
                                      {"error": "forbidden_scope", "detail": "broadcast scope only"}),
        "get_true_matrix.broadcast": canned("get_true_matrix", "broadcast", {"match_id": MATCH_ID},
                                            dump(duel.broadcast)),
        "get_match_state.broadcast": canned("get_match_state", "broadcast", {"match_id": MATCH_ID, "minute": 45},
                                            dump(bundle.snapshots[45])),
        "get_events.broadcast": canned("get_events", "broadcast", {"match_id": MATCH_ID, "filter": {"limit": 5}},
                                       [dump(e) for e in bundle.events[:5]]),
        "get_claim.broadcast": canned("get_claim", "broadcast", {"claim_id": "c201"}, claims["c201"]),
    }


# --------------------------------------------------------------------------------------------- output

def build_all() -> dict[Path, str]:
    squads = build_squads()
    events = MatchScript(squads).run()
    plans = build_plans()
    snaps = build_snapshots(events, squads, plans)
    duel, duel_claims = build_duel()
    claims = scouting_claims() + build_live_claims(events, snaps) + duel_claims
    meta = MatchMeta(match_id=MATCH_ID, home=HOME, away=AWAY, kickoff_label="Sat 15:00 (fictional)",
                     attack=[AttackDirection(period=1, positive_x=HOME), AttackDirection(period=2, positive_x=AWAY)])
    bundle = MatchBundle(meta=meta, squads=squads, events=events, snapshots=snaps,
                         render_frames=build_render_frames(events, squads), plans=plans, duel=duel, claims=claims,
                         cues=build_cues(), traces=build_traces(), illustrative=True,
                         eval={"note": "placeholder: E1-E8 are produced by eval/ from H2 on", "illustrative": True})
    dump = lambda m: m.model_dump(mode="json", by_alias=True)  # noqa: E731
    out: dict[Path, Any] = {
        FIXTURE_DIR / "squads_fixture.json": dump(squads),
        FIXTURE_DIR / "match_fixture.json": {"meta": dump(meta), "events": [dump(e) for e in events],
                                             "snapshots": [dump(s) for s in snaps], "illustrative": True},
        FIXTURE_DIR / "plans_fixture.json": {"plans": {t: dump(p) for t, p in plans.items()},
                                             "claims": [dump(c) for c in scouting_claims()], "illustrative": True},
        FIXTURE_DIR / "duel_fixture.json": {"duel": dump(duel), "claims": [dump(c) for c in duel_claims],
                                            "illustrative": True},
        FIXTURE_DIR / "match_bundle_fixture.json": dump(bundle),
        FIXTURE_DIR / "eval_only" / "truth_fixture.json": dump(build_truth()),
    }
    out |= {FIXTURE_DIR / "tools_canned" / f"{name}.json": data for name, data in build_tools(bundle).items()}
    return {p: json.dumps(d, indent=1, ensure_ascii=False) + "\n" for p, d in out.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build_all()
    stale = [p for p, text in files.items() if not p.exists() or p.read_text() != text] if args.check else []
    if not args.check:
        for p, text in files.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
    if stale:
        print("Stale fixtures (run `make fixtures`):", *map(str, stale), sep="\n  ")
        return 1
    print("fixtures OK" if args.check else f"wrote {len(files)} fixture files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
