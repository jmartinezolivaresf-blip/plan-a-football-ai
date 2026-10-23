"""Seeds, common random numbers, vectorisation and forks."""

from __future__ import annotations

import numpy as np

from contracts import LeverChanges, Option
from sim import bind, fork, fork_detailed, simulate
from sim.core import Batch
from sim.world import compile_world

from .sim_helpers import plans, squads, truth


def _sim(seed, **kw):
    return simulate(plans(), squads(), seed=seed, truth=truth(), **kw)


def test_same_seed_same_match():
    a, b = _sim(42, log=True), _sim(42, log=True)
    assert [e.model_dump() for e in a.events] == [e.model_dump() for e in b.events]
    assert a.final_state == b.final_state


def test_different_seeds_differ():
    a, b = _sim(1, log=True), _sim(2, log=True)
    assert [e.model_dump() for e in a.events] != [e.model_dump() for e in b.events]


def test_logging_does_not_change_the_simulation():
    assert _sim(9, log=True).outcomes == _sim(9, log=False).outcomes


def test_r1_equals_replica_zero_of_a_batch():
    single = _sim(123).outcomes
    many = _sim(123, R=64).outcomes
    for team in ("KES", "HAR"):
        assert many.goals[team][0] == single.goals[team][0]


def test_every_replica_equals_its_own_r1_run():
    """Replica r of a batch == an R=1 run whose replica index is r (stateless counter RNG)."""
    world = compile_world(plans(), squads(), truth())
    big = Batch(world, 8, 77).fresh()
    res = big.run(90)
    for r in range(8):
        world_r = compile_world(plans(), squads(), truth())
        one = Batch(world_r, 1, 77)
        one.seeds = big.seeds[r:r + 1].copy()
        one.fresh()
        assert (one.run(90).score[0] == res.score[r]).all(), r


def test_batch_results_vary_across_replicas():
    goals = np.array(_sim(5, R=200).outcomes.goals["KES"])
    assert goals.std() > 0.5


def _half_time_state(seed=31):
    return _sim(seed, log=True, until_minute=45).final_state


def test_first_half_is_a_prefix_of_the_full_match():
    full = _sim(31, log=True)
    half = _sim(31, log=True, until_minute=45)
    n = len(half.events)
    assert [e.model_dump() for e in full.events[:n]] == [e.model_dump() for e in half.events]
    assert half.final_state.period == 1 and half.final_state.t == 2700.0 and half.final_state.minute == 45


def test_stay_stay_fork_equals_continuing_the_match():
    full = _sim(31, log=True)
    state = _half_time_state(31)
    _, cont = fork_detailed(state, {}, R=1, seed=31, truth=truth(), log=True)
    n_first = len(_sim(31, log=True, until_minute=45).events)
    assert [e.model_dump() for e in cont.events] == [e.model_dump() for e in full.events[n_first:]]
    assert cont.final_state.snapshot.score == full.final_state.snapshot.score


def test_repeated_fork_is_identical_and_does_not_mutate_state():
    state = _half_time_state()
    frozen = state.model_dump()
    a = fork(state, {}, R=100, seed=4, truth=truth())
    b = fork(state, {}, R=100, seed=4, truth=truth())
    assert a == b
    assert state.model_dump() == frozen


def test_fork_keeps_the_first_half():
    state = _half_time_state()
    ht = state.snapshot.score
    out = fork(state, {}, R=200, seed=8, truth=truth())
    for team in ("KES", "HAR"):
        assert min(out.goals[team]) >= ht[team]


def test_forks_use_common_random_numbers():
    """A no-op override gives exactly the Stay outcomes; a real change moves only some replicas."""
    state = _half_time_state()
    stay = fork(state, {}, R=300, seed=8, truth=truth())
    noop = Option(option_id="KES-noop", team="KES", label={"en": "x", "es": "x"}, intent="stay_the_course")
    assert fork(state, {"KES": noop}, R=300, seed=8, truth=truth()) == stay
    drop = Option(option_id="KES-mid", team="KES", label={"en": "x", "es": "x"}, intent="drop_block",
                  lever_changes=LeverChanges(press_height="low"))
    changed = fork(state, {"KES": drop}, R=300, seed=8, truth=truth())
    same = np.array(stay.goals["HAR"]) == np.array(changed.goals["HAR"])
    assert 0.0 < same.mean() < 1.0
    # independent seeds would agree far less often than CRN-paired forks
    indep = fork(state, {"KES": drop}, R=300, seed=9, truth=truth())
    indep_same = np.array(stay.goals["HAR"]) == np.array(indep.goals["HAR"])
    assert same.mean() > indep_same.mean()


def test_bound_world_matches_explicit_truth_and_hides_it():
    world = bind(truth())
    assert world.simulate(plans(), squads(), seed=3).outcomes == _sim(3).outcomes
    state = _half_time_state()
    assert world.fork(state, {}, R=50, seed=1) == fork(state, {}, R=50, seed=1, truth=truth())
    assert "hidden" in repr(world) and "HAR-5" not in repr(world)


def test_outcomes_are_consistent():
    out = _sim(10, R=300).outcomes
    for team in ("KES", "HAR"):
        lo, hi = out.ci90[team]
        assert lo <= out.xpts[team] <= hi
        assert 0 <= out.xpts[team] <= 3
        assert len(out.goals[team]) == 300
    traj = out.kpi_trajectories["KES:high_turnovers"]
    assert len(traj) == 91 and traj == sorted(traj)


def test_explicit_home_overrides_dict_order():
    p = plans()
    swapped = {"HAR": p["HAR"], "KES": p["KES"]}
    a = simulate(p, squads(), seed=12, R=1, log=True, truth=truth())
    b = simulate(swapped, squads(), seed=12, R=1, log=True, truth=truth(), home="KES")
    assert [e.model_dump() for e in a.events] == [e.model_dump() for e in b.events]
    c = simulate(swapped, squads(), seed=12, R=1, log=True, truth=truth())  # fallback: HAR becomes home
    assert c.events[0].team == "HAR"
