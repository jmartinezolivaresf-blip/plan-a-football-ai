"""RealEngine: the EngineAPI over a synthetic season and one demo match (person A, H2).

The engine never imports hidden truth. It receives two opaque simulator handles from the pipeline:
- `public_world`: the simulator without hidden traits (what any bench can model), used for every staff valuation;
- `true_world`: the real world (traits inside), used only to play the demo match and the broadcast true matrix.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from contracts import (
    Claim,
    DuelBroadcast,
    Event,
    I18nText,
    LeverChanges,
    MatchMeta,
    Matrix,
    Option,
    Plan,
    Regret,
    RevealedChoice,
    SealedChoice,
    Snapshot,
    Squad,
    Squads,
)
from contracts.duel import EstimatedOption, OpponentOptionsEstimate
from contracts.engine_api import NotReady, NotSealedYet
from contracts.option import changes_nothing
from contracts.plan import OpponentPlanEstimate
from contracts.refs import MatchRef, ValidationResult
from contracts.sealing import choice_digest, new_salt
from contracts.sim_types import MatchState

from . import duel as dm
from .beliefs import beliefs_from_claims
from .scouting import MatchLog, Scout
from .tracker import PlanTracker, detect_adaptation, observed_levers
from .valuation import default_plan, estimate_plan, matrix_from_outcomes, paired_ci, points


def _tactics(plan: Plan) -> str:
    """Everything in a plan that changes what the simulator does (KPIs too: Plan B rules can trigger on them)."""
    return plan.model_dump_json(include={"levers", "plan_b", "subs_plan", "kpis"}, by_alias=True)


# P(keep the plan, situational move, build-up switch) for the OTHER bench, by its score situation at half-time:
# Laplace-smoothed frequencies of dev duels (eval/calibrate_estimates.py, D-048); a test pins them to the file.
ESTIMATE_PROBS: dict[str, list[float]] = {"leading": [0.4, 0.16, 0.44], "level": [0.258, 0.29, 0.452],
                                          "trailing": [0.2, 0.68, 0.12]}


@dataclass
class Seeds:
    prematch: int = 101
    match: int = 202
    believed: int = 303
    true: int = 404


@dataclass
class RealEngine:
    matches: list[MatchLog]
    squads: Squads                       # all clubs (public, visible attributes)
    meta: MatchMeta                      # the demo match
    public_world: Any
    true_world: Any | None = None
    belief_world: Any | None = None  # factory: list[belief dict] -> world model (sim.bind_beliefs)
    seeds: Seeds = field(default_factory=Seeds)
    R_value: int = 300
    R_matrix: int = 300
    R_true: int = 500
    claims: dict[str, Claim] = field(default_factory=dict)
    plans: dict[str, Plan] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    snapshots: list[Snapshot] = field(default_factory=list)
    ht_state: MatchState | None = None
    trajectories: dict[str, list[float]] = field(default_factory=dict)
    declared: dict[str, list[Option]] = field(default_factory=dict)
    sealed: dict[str, tuple[str, str, str]] = field(default_factory=dict)  # team -> (option_id, salt, rule)
    broadcast: DuelBroadcast | None = None
    estimates: dict[str, OpponentOptionsEstimate] = field(default_factory=dict)
    planb_fired: list[tuple[str, int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        positions = {p.player_id: p.position for sq in self.squads.teams.values() for p in sq.players}
        self.scout = Scout(self.matches, positions)
        self.xg = self.scout.xg
        self._value_cache: dict[str, tuple[np.ndarray, dict]] = {}
        self._worlds: dict[str, Any] = {}

    def world_for(self, team: str):
        """The bench's world model: public simulator + weaknesses its scouting suspects in the opponent (D-033)."""
        if self.belief_world is None:
            return self.public_world
        if team not in self._worlds:
            beliefs = beliefs_from_claims(self.scout.tendencies(self.opponent(team)))
            self.beliefs = getattr(self, "beliefs", {})
            self.beliefs[team] = beliefs
            self._worlds[team] = self.belief_world(beliefs)
        return self._worlds[team]

    # ------------------------------------------------------------------ helpers
    @property
    def match_id(self) -> str:
        return self.meta.match_id

    @property
    def home(self) -> str:
        return self.meta.home

    @property
    def away(self) -> str:
        return self.meta.away

    def opponent(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def _keep(self, claims: list[Claim]) -> list[Claim]:
        for c in claims:
            self.claims[c.claim_id] = c
        return claims

    def match_squads(self) -> Squads:
        return Squads(teams={self.home: self.squads.teams[self.home], self.away: self.squads.teams[self.away]})

    # ------------------------------------------------------------------ scouting
    def list_matches(self, team: str) -> list[MatchRef]:
        out = []
        for m in self.matches:
            if team in (m.home, m.away):
                score = {m.home: 0, m.away: 0}
                for e in m.events:
                    if e.type == "goal":
                        score[e.team] += 1
                out.append(MatchRef(match_id=m.match_id, home=m.home, away=m.away, score=score))
        return out

    def get_team_tendencies(self, team: str, aspect: str) -> list[Claim]:
        return self._keep(self.scout.tendencies(team, aspect))

    def get_player_profile(self, player_id: str) -> list[Claim]:
        return self._keep(self.scout.player_pressure(player_id))

    def get_set_piece_profile(self, team: str) -> list[Claim]:
        return self._keep(self.scout.set_pieces(team))

    # ------------------------------------------------------------------ own squad
    def get_squad(self, team: str) -> Squad:
        return self.squads.teams[team]

    def condition_estimate(self, minute: int) -> dict[str, float]:
        """Engine estimate from observable load: minutes on the pitch, faster under a high press."""
        out: dict[str, float] = {}
        if not self.snapshots:
            return out
        snaps = self.snapshots[: minute + 1]
        for team in (self.home, self.away):
            on_minutes: dict[str, float] = {}
            for s in snaps[1:]:
                press = s.active_levers[team].press_height == "high"
                for pid in s.on_pitch[team]:
                    on_minutes[pid] = on_minutes.get(pid, 0.0) + (1.25 if press else 1.0)
            for pid in snaps[-1].on_pitch[team]:
                out[pid] = round(max(0.0, 1.0 - 0.0035 * on_minutes.get(pid, 0.0)), 3)
        return out

    def get_squad_condition(self, match_id: str, team: str, minute: int) -> list[Claim]:
        cond = self.condition_estimate(minute)
        return self._keep([Claim(claim_id=f"c_cond_{pid}_{minute}", type="observed_tendency", team=team,
                                 player_id=pid, metric="condition_est", value=v, minute=minute, n=minute)
                           for pid, v in cond.items() if pid.startswith(f"{team}-")])

    # ------------------------------------------------------------------ pre-match valuation
    def _sim_points(self, plans: dict[str, Plan], team: str, R: int, seed: int) -> tuple[np.ndarray, dict]:
        key = f"{team}|{R}|{seed}|" + "|".join(f"{t}:{_tactics(p)}" for t, p in sorted(plans.items()))
        if key not in self._value_cache:
            res = self.world_for(team).simulate(plans, self.match_squads(), seed=seed, R=R, home=self.home)
            opp = self.opponent(team)
            pts = points(res.outcomes.goals[team], res.outcomes.goals[opp])
            self._value_cache[key] = (pts, res.outcomes.kpi_trajectories)
        return self._value_cache[key]

    def simulate_plan(self, plan: Plan, opponent_estimate: OpponentPlanEstimate, R: int) -> list[Claim]:
        R = min(R, self.R_value)
        team, opp = plan.team, plan.opponent
        opp_plan = estimate_plan(opponent_estimate)
        cand, _ = self._sim_points({team: plan, opp: opp_plan}, team, R, self.seeds.prematch)
        base, _ = self._sim_points({team: default_plan(plan), opp: opp_plan}, team, R, self.seeds.prematch)
        diff = cand - base
        lo, hi = paired_ci(diff, seed=self.seeds.prematch)
        digest = hashlib.sha256((_tactics(plan) + _tactics(opp_plan)).encode()).hexdigest()[:8]
        return self._keep([Claim(claim_id=f"c_sim_{team}_{digest}", type="sim_valuation", team=team,
                                 metric="delta_xpts_vs_default_plan", value=round(float(diff.mean()), 3), n=R,
                                 interval_low=round(lo, 3), interval_high=round(hi, 3),
                                 label="in our simulator, against the estimated opponent plan")])

    # ------------------------------------------------------------------ match lifecycle (pipeline)
    def set_plans(self, plans: dict[str, Plan]) -> None:
        """Both sealed plans; computes the expected KPI trajectories (public world, both real plans)."""
        self.plans = {self.home: plans[self.home], self.away: plans[self.away]}
        res = self.public_world.simulate(self.plans, self.match_squads(), seed=self.seeds.prematch, R=200,
                                         home=self.home)
        self.trajectories = res.outcomes.kpi_trajectories
        self.trackers = {t: PlanTracker(p, self.home, self.xg, self.trajectories) for t, p in self.plans.items()}
        self.kpi_by_minute: dict[int, dict[str, Any]] = {}

    def _augment(self, snaps: list[Snapshot]) -> None:
        for s in snaps:
            if s.minute in self.kpi_by_minute:
                s.kpis = self.kpi_by_minute[s.minute]
                continue
            kpis = []
            for tracker in self.trackers.values():
                st, cl = tracker.at(s.minute, self.events)
                kpis += st
                self._keep(cl)
            self.kpi_by_minute[s.minute] = kpis
            s.kpis = kpis

    def play_first_half(self) -> MatchState:
        if self.true_world is None:
            raise NotReady("the demo match needs the real world (pipeline)")
        res = self.true_world.simulate(self.plans, self.match_squads(), seed=self.seeds.match, R=1, log=True,
                                       until_minute=45, match_id=self.match_id, home=self.home)
        self.events = list(res.events)
        self.snapshots = list(res.snapshots)
        self._augment(self.snapshots)
        for s in self.snapshots:
            s.condition_est = self.condition_estimate(s.minute)
        self.ht_state = res.final_state
        return self.ht_state

    def play_second_half(self) -> MatchState:
        if self.broadcast is None:
            raise NotSealedYet("reveal both choices first")
        overrides = {t: self._option(t, r.option_id) for t, r in self.broadcast.revealed.items()}
        _, res = self.true_world.fork_detailed(self.ht_state, overrides, R=1, seed=self.seeds.match, log=True)
        self.events += res.events
        new = [s for s in res.snapshots if s.minute > 45]
        self.snapshots += new
        self._augment(new)
        for s in new:
            s.condition_est = self.condition_estimate(s.minute)
        return res.final_state

    def adaptation(self, team: str, minute: int) -> list[Claim]:
        """What the detector says at `minute`, using only events up to then."""
        found = detect_adaptation(team, self.events, self.home, upto=minute)
        return self._keep(list(found)) if found else []

    def first_adaptation(self, team: str, upto: int = 90) -> tuple[int, list[Claim]] | None:
        """The first minute at which the online detector fires (what a live broadcast could have shown)."""
        for minute in range(1, upto + 1):
            found = detect_adaptation(team, self.events, self.home, upto=minute)
            if found:
                return minute, self._keep(list(found))
        return None

    # ------------------------------------------------------------------ the duel
    def estimate_opponent_options(self, match_id: str, team: str) -> OpponentOptionsEstimate:
        if self.ht_state is None:
            raise NotReady("estimates exist at half-time")
        if team in self.estimates:
            return self.estimates[team]
        opp = self.opponent(team)
        score = self.ht_state.snapshot.score
        diff = score[opp] - score[team]
        adapted = self.adaptation(opp, 45)
        went_long = bool(adapted) and adapted[1].label == "short to long"
        # what this bench can see of the other team's levers, never their sealed plan (D-048)
        observed, seen = observed_levers(opp, self.events, self.home, 45)
        self._keep(seen)
        seen_press, seen_build = observed["press_height"], observed["build_up"]
        stay = Option(option_id=f"{team}-EST-{opp}-1", team=opp, intent="stay_the_course", estimated=True,
                      label=I18nText(en="They keep their plan", es="Mantienen su plan"))
        if diff > 0:
            second = Option(option_id=f"{team}-EST-{opp}-2", team=opp, intent="protect_lead", estimated=True,
                            label=I18nText(en="They sit deep", es="Se encierran"),
                            lever_changes=LeverChanges(press_height="low"))
            probs = ESTIMATE_PROBS["leading"]
        elif diff < 0:
            second = Option(option_id=f"{team}-EST-{opp}-2", team=opp, intent="attacking_subs", estimated=True,
                            label=I18nText(en="They push for a goal", es="Van a por el gol"),
                            lever_changes=LeverChanges(press_height="high", attack_channel="balanced"))
            probs = ESTIMATE_PROBS["trailing"]
        else:
            higher = seen_press != "high"
            second = Option(option_id=f"{team}-EST-{opp}-2", team=opp, estimated=True,
                            intent="press_higher" if higher else "drop_block",
                            label=I18nText(en="They press higher" if higher else "They drop deeper",
                                           es="Presionan más arriba" if higher else "Bajan el bloque"),
                            lever_changes=LeverChanges(press_height="high" if higher else "mid"))
            probs = ESTIMATE_PROBS["level"]
        if went_long or seen_build == "direct":
            third = Option(option_id=f"{team}-EST-{opp}-3", team=opp, intent="short_build_up", estimated=True,
                           label=I18nText(en="They go back to short", es="Vuelven al corto"),
                           lever_changes=LeverChanges(build_up="short"))
        else:
            third = Option(option_id=f"{team}-EST-{opp}-3", team=opp, intent="go_direct", estimated=True,
                           label=I18nText(en="They go direct", es="Juegan directo"),
                           lever_changes=LeverChanges(build_up="direct"))
        evidence = [c.claim_id for c in adapted] + [c.claim_id for c in seen]
        # guesses that are the same tactics on top of what was seen are one guess, never two columns (D-055)
        options, probs = dm.merge_equivalent([stay, second, third], list(probs), observed)
        total = sum(probs)
        probs = [p / total for p in probs]  # calibrated values are rounded; the contract needs an exact sum of 1
        cid = f"c_est_{team}"
        self._keep([Claim(claim_id=cid, type="opponent_estimate", team=team, metric="opponent_option_probabilities",
                          value=" / ".join(f"{o.label.en} {p:.0%}" for o, p in zip(options, probs, strict=True)),
                          evidence=evidence, label=f"score difference for them: {diff:+d}")])
        est = OpponentOptionsEstimate(estimator=team, opponent=opp, claims=[cid] + evidence,
                                      options=[EstimatedOption(option=o, probability=p)
                                               for o, p in zip(options, probs, strict=True)])
        self.estimates[team] = est
        return est

    def _fork_grid(self, world, rows: list[Option], cols: list[Option], row_team: str, col_team: str, R: int,
                   seed: int) -> list[list]:
        grid = []
        for r in rows:
            line = []
            for c in cols:
                overrides = {}
                if r.lever_changes.model_dump(exclude_none=True) or r.subs:
                    overrides[row_team] = r
                if c.lever_changes.model_dump(exclude_none=True) or c.subs:
                    overrides[col_team] = c
                line.append(world.fork(self.ht_state, overrides, R=R, seed=seed))
            grid.append(line)
        return grid

    def price_matrix(self, match_id: str, own_options: list[Option], opponent_options: list[Option], R: int,
                     perspective: str, opponent_probs: list[float]) -> Matrix:
        if self.ht_state is None:
            raise NotReady("price_matrix exists at half-time")
        if not own_options or not opponent_options:
            raise ValueError("own_options and opponent_options are required")
        R = min(R, self.R_matrix)
        opp = self.opponent(perspective)
        # a bench prices the other team from what it saw in the first half, not from their real levers (D-048)
        observed, seen = observed_levers(opp, self.events, self.home, 45)
        # two rows (or columns) with the same tactics would be one option shown twice (D-055)
        same = (dm.duplicate_pairs(list(own_options), self.ht_state.levers[perspective].model_dump())
                + dm.duplicate_pairs(list(opponent_options), observed))
        if same:
            raise ValueError(f"options with the same tactics: {same}")
        self.declared[perspective] = list(own_options)
        self._keep(seen)
        as_seen = [o.model_copy(update={"lever_changes": LeverChanges(**{
            **observed, **o.lever_changes.model_dump(exclude_none=True)})}) for o in opponent_options]
        grid = self._fork_grid(self.world_for(perspective), own_options, as_seen, perspective, opp, R,
                               self.seeds.believed)
        m, claims = matrix_from_outcomes(f"mx-believed-{perspective}", self.match_id, "believed", perspective,
                                         perspective, opp, own_options, opponent_options, grid,
                                         list(opponent_probs), R, self.seeds.believed)
        self._keep(claims)
        return m

    def validate_plan(self, plan: Plan) -> ValidationResult:
        return ValidationResult(ok=True)

    def validate_option(self, match_id: str, option: Option) -> ValidationResult:
        if self.ht_state is None:
            return ValidationResult(ok=False, errors=["options are validated at half-time"])
        snap, dyn = self.ht_state.snapshot, self.ht_state.dynamics[option.team]
        on = set(snap.on_pitch[option.team])
        used = set(dyn.used_players)
        squad = {p.player_id for p in self.squads.teams[option.team].players}
        errors = []
        left = 5 - snap.subs_used[option.team]
        if len(option.subs) > left:
            errors.append(f"only {left} substitutions left")
        for s in option.subs:
            if s.out not in on:
                errors.append(f"{s.out} is not on the pitch")
            if s.into not in squad or s.into in used:
                errors.append(f"{s.into} cannot come on (unknown or already used)")
        if option.lever_changes.press_target and option.lever_changes.press_target not in {
                p.player_id for p in self.squads.teams[self.opponent(option.team)].players}:
            errors.append("press_target must be an opponent player")
        # an option is measured against the levers in force at half-time (a fired Plan B included), D-055
        now = self.ht_state.levers[option.team].model_dump()
        idle = changes_nothing(now, option.lever_changes, option.subs)
        if option.intent == "stay_the_course" and not idle:
            errors.append("'stay the course' cannot change levers or players")
        elif option.intent != "stay_the_course" and idle:
            in_force = ", ".join(f"{k}={v}" for k, v in option.lever_changes.model_dump(exclude_none=True).items())
            errors.append(f"this option changes nothing: already in force ({in_force or 'no change'})")
        return ValidationResult(ok=not errors, errors=errors)

    def _option(self, team: str, option_id: str) -> Option:
        for o in self.declared.get(team, []):
            if o.option_id == option_id:
                return o
        raise LookupError(f"{option_id} is not one of {team}'s declared options")

    def seal_choice(self, match_id: str, team: str, option_id: str, rule: str = "best_guess") -> SealedChoice:
        self._option(team, option_id)
        if team in self.sealed:
            raise ValueError(f"{team} already sealed its choice")
        # random, never derived from seeds: a salt anyone can recompute would let the other side brute-force the
        # three options from the commit before the reveal (D-045)
        salt = new_salt()
        self.sealed[team] = (option_id, salt, rule)
        return SealedChoice(team=team, sealed_at="half-time", sha256=choice_digest(self.match_id, team, option_id,
                                                                                  salt))

    def true_matrix(self, match_id: str) -> DuelBroadcast:
        if set(self.sealed) != {self.home, self.away}:
            raise NotSealedYet("both benches must seal before the true matrix exists")
        if self.broadcast is not None:
            return self.broadcast
        if self.true_world is None:
            raise NotReady("the true matrix needs the real world (pipeline)")
        rows, cols = self.declared[self.home], self.declared[self.away]
        grid = self._fork_grid(self.true_world, rows, cols, self.home, self.away, self.R_true, self.seeds.true)
        m, claims = matrix_from_outcomes("mx-true", self.match_id, "true", None, self.home, self.away, rows, cols,
                                         grid, None, self.R_true, self.seeds.true)
        self._keep(claims)
        revealed = {t: RevealedChoice(team=t, option_id=o, salt=s, rule=r) for t, (o, s, r) in self.sealed.items()}
        regret = {}
        row_ids, col_ids = [o.option_id for o in rows], [o.option_id for o in cols]
        for team in (self.home, self.away):
            opp = self.opponent(team)
            chosen, opp_chosen = revealed[team].option_id, revealed[opp].option_id
            best, value = dm.regret(m, team, chosen, opp_chosen)
            # paired 90% interval: same replicas (common random numbers) for the best response and the chosen option
            if team == self.home:
                a, b = (grid[row_ids.index(x)][col_ids.index(opp_chosen)] for x in (best, chosen))
            else:
                a, b = (grid[row_ids.index(opp_chosen)][col_ids.index(x)] for x in (best, chosen))
            diff = points(a.goals[team], a.goals[opp]) - points(b.goals[team], b.goals[opp])
            lo, hi = paired_ci(diff, seed=self.seeds.true)
            cid = f"c_rg_{team}"
            self._keep([Claim(claim_id=cid, type="regret", team=team, metric="regret_xpts", value=round(value, 3),
                              n=self.R_true, label=f"best response {best}", interval_low=round(lo, 3),
                              interval_high=round(hi, 3))])
            regret[team] = Regret(team=team, chosen=revealed[team].option_id, opponent_chosen=revealed[opp].option_id,
                                  best_response=best, regret_xpts=round(value, 3), claim_id=cid)
        self.broadcast = DuelBroadcast(revealed=revealed, true_matrix=m, regret=regret)
        return self.broadcast

    def regret(self, match_id: str) -> dict[str, Regret]:
        return self.true_matrix(match_id).regret

    # ------------------------------------------------------------------ live and evidence
    def get_plan_status(self, match_id: str, team: str, minute: int) -> list[Claim]:
        ids = [k.claim_id for k in self.kpi_by_minute.get(minute, []) if k.team == team and k.claim_id]
        return [self.claims[c] for c in ids if c in self.claims]

    def get_match_state(self, match_id: str, minute: int) -> Snapshot:
        if not self.snapshots:
            raise NotReady("the match has not started")
        return self.snapshots[max(0, min(minute, len(self.snapshots) - 1))]

    def get_events(self, match_id: str, filter: dict[str, Any]) -> list[Event]:
        evs = [e for e in self.events
               if all(getattr(e, k) == v for k, v in filter.items() if k not in ("limit", "from_t", "to_t"))
               and filter.get("from_t", 0) <= e.t <= filter.get("to_t", 1e9)]
        return evs[: filter.get("limit", len(evs))]

    def get_claim(self, claim_id: str) -> Claim:
        return self.claims[claim_id]
