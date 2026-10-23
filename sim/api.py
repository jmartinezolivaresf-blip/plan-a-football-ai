"""Public simulator API: simulate(), fork(), bind(). See contracts/sim_api.md."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from contracts import Option, Plan, Squads
from contracts.eval_only import SimConfig, Truth
from contracts.sim_types import MatchState, Outcomes, SimResult, TeamDynamics

from . import model as M
from .core import Batch, BatchResult
from .log import Logger, decode_levers
from .world import KPI_METRICS, World, add_override_subs, compile_world, lever_changes_to_codes


def simulate(plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1, log: bool = False,
             start: MatchState | None = None, until_minute: int = 90, *, truth: Truth | None = None,
             config: SimConfig | None = None, match_id: str | None = None) -> SimResult:
    if log and R != 1:
        raise ValueError("log=True requires R == 1")
    if not 1 <= until_minute <= 90:
        raise ValueError("until_minute must be in 1..90")
    world = compile_world(plans, squads, truth, config)
    match_id = match_id or (start.match_id if start else f"sim-{seed}")
    if start is None:
        logger = Logger(match_id) if log else None
        batch = Batch(world, R, seed, logger)
        batch.fresh()
    else:
        logger = Logger(match_id, start.events_emitted, start.possession_id) if log else None
        batch = _from_state(world, start, R, seed, logger)
    res = batch.run(until_minute)
    return _result(world, batch, res, seed, logger, match_id)


def fork(state: MatchState, overrides: dict[str, Option], R: int, seed: int, *, truth: Truth | None = None,
         config: SimConfig | None = None) -> Outcomes:
    world = compile_world(state.plans, state.squads, truth, config)
    batch = _from_state(world, state, R, seed, None)
    _apply_overrides(world, batch, state, overrides)
    res = batch.run(90)
    return _outcomes(world, res, seed)


def fork_detailed(state: MatchState, overrides: dict[str, Option], R: int, seed: int, *,
                  truth: Truth | None = None, config: SimConfig | None = None,
                  log: bool = False) -> tuple[BatchResult, SimResult]:
    """Like fork() but also returns internal batch statistics (and events with R=1, log=True). For tests/eval."""
    if log and R != 1:
        raise ValueError("log=True requires R == 1")
    world = compile_world(state.plans, state.squads, truth, config)
    logger = Logger(state.match_id, state.events_emitted, state.possession_id) if log else None
    batch = _from_state(world, state, R, seed, logger)
    _apply_overrides(world, batch, state, overrides)
    res = batch.run(90)
    return res, _result(world, batch, res, seed, logger, state.match_id)


@dataclass(frozen=True)
class BoundWorld:
    """Simulator with the hidden truth captured inside. Hand this to code that must not see the truth."""

    _truth: Truth | None
    _config: SimConfig | None

    def simulate(self, plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1, log: bool = False,
                 start: MatchState | None = None, until_minute: int = 90, match_id: str | None = None) -> SimResult:
        return simulate(plans, squads, seed, R, log, start, until_minute, truth=self._truth, config=self._config,
                        match_id=match_id)

    def fork(self, state: MatchState, overrides: dict[str, Option], R: int, seed: int) -> Outcomes:
        return fork(state, overrides, R, seed, truth=self._truth, config=self._config)

    def __repr__(self) -> str:  # never print the truth
        return "BoundWorld(<hidden>)"


def bind(truth: Truth | None, config: SimConfig | None = None) -> BoundWorld:
    return BoundWorld(truth, config)


# ---------------------------------------------------------------------------------------- overrides

def _apply_overrides(world: World, b: Batch, state: MatchState, overrides: dict[str, Option]) -> None:
    if not overrides:
        return
    n_before = [len(t.catalogue) for t in world.teams]
    new_subs = add_override_subs(world, overrides)
    if any(len(t.catalogue) != n for t, n in zip(world.teams, n_before, strict=True)):
        _grow_catalogue(b, world)
    at_half_time = state.period == 1 and state.t >= M.HALF_T
    for code, option in overrides.items():
        i = world.index(code)
        for lever, value in lever_changes_to_codes(option.lever_changes, world.teams[1 - i].player_ids).items():
            b.lev[:, i, lever] = value
        for c in new_subs.get(i, []):
            b.sub_pending[:, i, c] = True
            if not at_half_time:
                b.pending_window[:, i] = True


def _grow_catalogue(b: Batch, world: World) -> None:
    C = max(len(t.catalogue) for t in world.teams)
    for name in ("sub_pending", "sub_done"):
        old = getattr(b, name)
        if old.shape[2] < C:
            new = np.zeros((b.R, 2, C), dtype=bool)
            new[:, :, : old.shape[2]] = old
            setattr(b, name, new)
    b.n_cat = [len(t.catalogue) for t in world.teams]


# ---------------------------------------------------------------------------------------- state I/O

def _from_state(world: World, s: MatchState, R: int, seed: int, logger: Logger | None) -> Batch:
    if [s.home, s.away] != world.codes:
        raise ValueError("state teams do not match the plans (home first)")
    b = Batch(world, R, seed, logger)
    for i, team in enumerate(world.teams):
        ids, code = team.player_ids, team.code
        opp_ids = world.teams[1 - i].player_ids
        b.on[:, i, :] = [ids.index(p) for p in s.snapshot.on_pitch[code]]
        dyn = s.dynamics[code]
        b.used[:, i, [ids.index(p) for p in dyn.used_players]] = True
        for pid, v in s.fatigue.items():
            if pid in ids:
                b.fat[:, i, ids.index(pid)] = v
        lv = s.levers[code]
        b.lev[:, i, :] = [M.PRESS[lv.press_height], opp_ids.index(lv.press_target) if lv.press_target else -1,
                          M.BUILD[lv.build_up], M.CHANNEL[lv.attack_channel], M.CORNER[lv.corner_delivery]]
        b.score[:, i] = s.snapshot.score[code]
        b.subs_used[:, i] = s.snapshot.subs_used[code]
        b.windows_used[:, i] = s.snapshot.sub_windows_used[code]
        for k, name in enumerate(KPI_METRICS):
            b.counters[:, i, k] = dyn.counters.get(name, 0.0)
        b.fired[:, i, dyn.plan_b_fired] = True
        b.sub_done[:, i, dyn.subs_plan_done] = True
        for out, into in dyn.pending_subs:
            c = next(c for c, e in enumerate(team.catalogue)
                     if ids[e.out] == out and ids[e.into] == into and not b.sub_done[0, i, c])
            b.sub_pending[:, i, c] = True
        b.pending_window[:, i] = dyn.pending_window
    b._refresh_on()
    b.t[:] = s.t
    b.period[:] = s.period
    b.poss[:] = world.index(s.possession)
    b.carrier[:] = world.teams[world.index(s.possession)].player_ids.index(s.carrier)
    b.bx[:], b.by[:] = s.ball
    b.counter_until[:] = s.counter_until
    b.after_cross[:] = s.after_cross
    b.step = s.rng_step
    b.start_minute = s.minute
    b.emitted0 = s.events_emitted
    b.kpi_hist[:, s.minute] = b.counters
    b.possession_id0, b.last_event_t0 = s.possession_id, s.last_event_t
    if logger is not None:
        logger.last_t = s.last_event_t
    return b


def _to_state(world: World, b: Batch, match_id: str, emitted: int, possession_id: int,
              last_event_t: float) -> MatchState:
    teams = world.teams
    codes = world.codes
    minute = int(min(b.t[0] // 60, 90))
    snap_logger = Logger(match_id)
    snap_logger.snapshot(b, minute)
    snap = snap_logger.snapshots[0]
    dynamics, fatigue, levers = {}, {}, {}
    for i, team in enumerate(teams):
        ids = team.player_ids
        pending = [(ids[team.catalogue[c].out], ids[team.catalogue[c].into])
                   for c in np.nonzero(b.sub_pending[0, i])[0]]
        dynamics[team.code] = TeamDynamics(
            used_players=[ids[p] for p in np.nonzero(b.used[0, i])[0]],
            plan_b_fired=[int(k) for k in np.nonzero(b.fired[0, i])[0]],
            subs_plan_done=[int(c) for c in np.nonzero(b.sub_done[0, i])[0]],
            pending_subs=pending, pending_window=bool(b.pending_window[0, i]),
            counters={name: float(b.counters[0, i, k]) for k, name in enumerate(KPI_METRICS)})
        for p, pid in enumerate(ids):
            fatigue[pid] = round(float(b.fat[0, i, p]), 6)
        levers[team.code] = decode_levers(b.lev[0, i], teams[1 - i].player_ids)
    poss = int(b.poss[0])
    return MatchState(
        match_id=match_id, minute=minute, snapshot=snap, levers=levers, fatigue=fatigue, rng_step=b.step,
        home=codes[0], away=codes[1], plans=world.plans, squads=world.squads, t=float(b.t[0]),
        period=int(b.period[0]), possession=codes[poss], carrier=teams[poss].player_ids[int(b.carrier[0])],
        ball=(float(b.bx[0]), float(b.by[0])), counter_until=float(b.counter_until[0]),
        after_cross=bool(b.after_cross[0]), dynamics=dynamics,
        events_emitted=emitted, possession_id=possession_id, last_event_t=last_event_t)


# ---------------------------------------------------------------------------------------- results

def _outcomes(world: World, res: BatchResult, seed: int) -> Outcomes:
    R = res.score.shape[0]
    codes = world.codes
    goals = {codes[i]: res.score[:, i].astype(int).tolist() for i in range(2)}
    xpts, ci = {}, {}
    for i in range(2):
        pts = np.where(res.score[:, i] > res.score[:, 1 - i], 3.0, np.where(res.score[:, i] == res.score[:, 1 - i],
                                                                           1.0, 0.0))
        mean = float(pts.mean())
        half = 1.645 * float(pts.std(ddof=1)) / np.sqrt(R) if R > 1 else 0.0
        xpts[codes[i]] = round(mean, 6)
        ci[codes[i]] = (round(mean - half, 6), round(mean + half, 6))
    traj = {}
    lo, hi = res.start_minute, min(res.end_minute, 90)
    for i in range(2):
        for k, name in enumerate(KPI_METRICS):
            traj[f"{codes[i]}:{name}"] = [round(float(v), 6) for v in res.kpi_hist[:, lo:hi + 1, i, k].mean(axis=0)]
    return Outcomes(R=R, seed=seed, goals=goals, xpts=xpts, ci90=ci, kpi_trajectories=traj)


def _result(world: World, b: Batch, res: BatchResult, seed: int, logger: Logger | None, match_id: str) -> SimResult:
    outcomes = _outcomes(world, res, seed)
    if b.R != 1:
        return SimResult(outcomes=outcomes)
    events = logger.finish(b) if logger is not None else []
    emitted = logger.n if logger is not None else b.emitted0
    pid = logger.possession_id if logger is not None else b.possession_id0
    last_t = max(logger.last_t, 0.0) if logger is not None else b.last_event_t0
    return SimResult(outcomes=outcomes, events=events, snapshots=logger.snapshots if logger else [],
                     final_state=_to_state(world, b, match_id, emitted, pid, last_t))
