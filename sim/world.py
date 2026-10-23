"""Compile public inputs (squads, plans) and hidden truth into static numpy arrays for the core loop.

Truth enters here and only here; nothing compiled from it is ever written into events, snapshots, outcomes
or MatchState.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from contracts import Option, Plan, Squads
from contracts.eval_only import SimConfig, Truth

from .model import BUILD, CHANNEL, CORNER, DEFAULT_COEFFICIENTS, PRESS, ROLE_IDX

ATTR_KEYS = ("pace", "passing", "stamina", "press_resistance", "aerial", "finishing")
A_PACE, A_PASS, A_STAM, A_PRES, A_AER, A_FIN = range(6)
L_PRESS, L_TARGET, L_BUILD, L_CHANNEL, L_CORNER = range(5)
KPI_METRICS = ("high_turnovers", "entries_total", "entries_left", "entries_center", "entries_right",
               "set_piece_xg", "balls_in_behind_conceded")
K_HT, K_ENT, K_ENT_L, K_ENT_C, K_ENT_R, K_SPXG, K_BIB = range(len(KPI_METRICS))
STATUS = {"on_track": 0, "at_risk": 1, "failing": 2, "insufficient_evidence": 3}
MAX_SUBS, MAX_WINDOWS = 5, 3


class PlanError(ValueError):
    """A plan that cannot be simulated (unknown players, too many subs, malformed windows)."""


@dataclass
class SubEntry:
    out: int
    into: int
    start: int | None  # minute window start; None for "HT"
    end: int | None
    source: str        # "plan" | "plan_b" | "override"


@dataclass
class RuleCondition:
    kpi_metric: str | None
    kpi_params: dict[str, str]
    kpi_op: str | None
    kpi_target: float | None
    kpi_by: int
    status: int | None
    after_minute: int | None
    score_op: str | None
    score_value: int | None


@dataclass
class Rule:
    cond: RuleCondition
    levers: dict[int, int]
    subs: list[int]  # indices into the team's sub catalogue


@dataclass
class TeamStatic:
    code: str
    player_ids: list[str]
    roles: np.ndarray        # (P,)
    attrs: np.ndarray        # (P, 6)
    starters: np.ndarray     # (11,)
    levers0: np.ndarray      # (5,)
    catalogue: list[SubEntry] = field(default_factory=list)
    plan_subs: list[int] = field(default_factory=list)  # catalogue indices from subs_plan
    rules: list[Rule] = field(default_factory=list)
    # hidden-trait effects (zeros without truth)
    pr_penalty: np.ndarray | None = None  # (P,)
    slow_cb: float = 0.0
    back_post_weak: float = 0.0
    gk_short_bias: float = 0.0
    late_fade: float = 0.0
    weak_lane: np.ndarray | None = None   # (3,) team-relative lanes of this team as defender


@dataclass
class World:
    teams: list[TeamStatic]  # [home, away]
    coef: dict[str, float]
    plans: dict[str, Plan]
    squads: Squads

    @property
    def codes(self) -> list[str]:
        return [t.code for t in self.teams]

    def index(self, code: str) -> int:
        return self.codes.index(code)


_WINDOW = re.compile(r"^(\d{1,2})-(\d{1,2})$")
_TARGET = re.compile(r"^(>=|<=|>|<)(\d+(?:\.\d+)?)$")
_SCORE = re.compile(r"^(>=|<=|>|<|==)(-?\d+)$")


def _window(w: str) -> tuple[int | None, int | None]:
    if w == "HT":
        return None, None
    m = _WINDOW.match(w)
    if not m or int(m.group(1)) > int(m.group(2)) or int(m.group(2)) > 90:
        raise PlanError(f"bad sub window {w!r}")
    return int(m.group(1)), int(m.group(2))


def lever_changes_to_codes(changes, opponent_ids: list[str]) -> dict[int, int]:
    out: dict[int, int] = {}
    if changes.press_height is not None:
        out[L_PRESS] = PRESS[changes.press_height]
    if changes.press_target is not None:
        out[L_TARGET] = _target(changes.press_target, opponent_ids)
    if changes.build_up is not None:
        out[L_BUILD] = BUILD[changes.build_up]
    if changes.attack_channel is not None:
        out[L_CHANNEL] = CHANNEL[changes.attack_channel]
    if changes.corner_delivery is not None:
        out[L_CORNER] = CORNER[changes.corner_delivery]
    return out


def _target(player_id: str | None, opponent_ids: list[str]) -> int:
    if player_id in (None, "none"):
        return -1
    if player_id not in opponent_ids:
        raise PlanError(f"press_target {player_id} is not in the opponent squad")
    return opponent_ids.index(player_id)


def _add_sub(team: TeamStatic, out: str, into: str, window: str, source: str) -> int:
    ids = team.player_ids
    if out not in ids or into not in ids:
        raise PlanError(f"sub {out}->{into}: unknown player for {team.code}")
    if out == into:
        raise PlanError(f"sub {out}->{into}: same player")
    start, end = _window(window)
    team.catalogue.append(SubEntry(ids.index(out), ids.index(into), start, end, source))
    return len(team.catalogue) - 1


def _condition(plan: Plan, c) -> RuleCondition:
    metric = params = op = target = None
    by = 90
    if c.kpi is not None:
        kpi = next((k for k in plan.kpis if k.id == c.kpi), None)
        if kpi is None:
            raise PlanError(f"plan_b references unknown KPI {c.kpi}")
        m = _TARGET.match(kpi.target)
        metric, params, op, target, by = kpi.metric, dict(kpi.params), m.group(1), float(m.group(2)), kpi.by_minute
    sop = sval = None
    if c.score_diff is not None:
        m = _SCORE.match(c.score_diff)
        sop, sval = m.group(1), int(m.group(2))
    return RuleCondition(metric, params or {}, op, target, by, STATUS[c.status] if c.status else None,
                         c.after_minute, sop, sval)


def compile_world(plans: dict[str, Plan], squads: Squads, truth: Truth | None = None,
                  config: SimConfig | None = None) -> World:
    codes = list(plans)
    if len(codes) != 2:
        raise PlanError("exactly two plans are required (home first)")
    for code in codes:
        if code not in squads.teams:
            raise PlanError(f"no squad for {code}")
    teams = []
    for code in codes:
        squad = squads.teams[code]
        ids = [p.player_id for p in squad.players]
        starters = [i for i, p in enumerate(squad.players) if p.starter]
        if len(starters) != 11:
            raise PlanError(f"{code} must have exactly 11 starters")
        roles = np.array([ROLE_IDX[p.position] for p in squad.players])
        attrs = np.array([[getattr(p.attributes, k) for k in ATTR_KEYS] for p in squad.players], dtype=float)
        teams.append(TeamStatic(code=code, player_ids=ids, roles=roles, attrs=attrs, starters=np.array(starters),
                                levers0=np.zeros(5, dtype=np.int64), pr_penalty=np.zeros(len(ids)),
                                weak_lane=np.zeros(3)))
    coef = dict(DEFAULT_COEFFICIENTS)
    if config is not None:
        unknown = set(config.coefficients) - set(coef)
        if unknown:
            raise PlanError(f"unknown coefficients: {sorted(unknown)}")
        coef.update(config.coefficients)
    for t, code in enumerate(codes):
        team, opp, plan = teams[t], teams[1 - t], plans[code]
        if plan.team != code:
            raise PlanError(f"plan {plan.plan_id} is for {plan.team}, keyed as {code}")
        lv = plan.levers
        team.levers0[:] = [PRESS[lv.press_height], _target(lv.press_target, opp.player_ids), BUILD[lv.build_up],
                           CHANNEL[lv.attack_channel], CORNER[lv.corner_delivery]]
        if len(plan.subs_plan) > MAX_SUBS:
            raise PlanError(f"{code}: more than {MAX_SUBS} planned subs")
        team.plan_subs = [_add_sub(team, s.out, s.into, s.window, "plan") for s in plan.subs_plan]
        for rule in plan.plan_b:
            subs = [_add_sub(team, s.out, s.into, "1-90", "plan_b") for s in rule.then.subs]
            team.rules.append(Rule(_condition(plan, rule.if_),
                                   lever_changes_to_codes(rule.then.levers, opp.player_ids), subs))
    if truth is not None:
        _apply_truth(teams, truth)
    return World(teams=teams, coef=coef, plans=dict(plans), squads=squads)


def add_override_subs(world: World, overrides: dict[str, Option]) -> dict[int, list[int]]:
    """Register override subs in each team's catalogue; returns team index -> catalogue indices."""
    out: dict[int, list[int]] = {}
    for code, option in overrides.items():
        t = world.index(code)
        if option.team != code:
            raise PlanError(f"option {option.option_id} belongs to {option.team}, not {code}")
        out[t] = [_add_sub(world.teams[t], s.out, s.into, "HT" if s.window == "HT" else s.window, "override")
                  for s in option.subs]
    return out


def _apply_truth(teams: list[TeamStatic], truth: Truth) -> None:
    for team in teams:
        tt = truth.teams.get(team.code)
        if tt is None:
            continue
        for tr in tt.traits:
            if tr.kind == "fb_low_press_resistance" and tr.player_id in team.player_ids:
                team.pr_penalty[team.player_ids.index(tr.player_id)] = tr.strength
            elif tr.kind == "cb_low_pace":
                team.slow_cb = max(team.slow_cb, tr.strength)
            elif tr.kind == "back_post_weak":
                team.back_post_weak = tr.strength
            elif tr.kind == "gk_short_bias":
                team.gk_short_bias = tr.strength
            elif tr.kind == "late_fade":
                team.late_fade = tr.strength
            elif tr.kind == "weak_channel" and tr.side is not None:
                team.weak_lane[0 if tr.side == "left" else 2] = tr.strength
