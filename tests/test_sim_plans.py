"""Plan B triggers, substitutions and plan validation."""

from __future__ import annotations

import pytest

from contracts import LeverChanges, Option, PlanBAction, PlanBCondition, PlanBRule, Sub
from sim import PlanError, fork, fork_detailed, simulate

from .sim_helpers import batch, plain_plans, plans, squads, truth


def _rule(**cond) -> PlanBRule:
    return PlanBRule(if_=PlanBCondition(**cond), then=PlanBAction(levers=LeverChanges(press_height="low")))


def test_minute_rule_fires_once_and_changes_levers():
    p = plain_plans(kes={"press_height": "high"})
    p["KES"] = p["KES"].model_copy(update={"plan_b": [_rule(after_minute=30)]})
    res = simulate(p, squads(), seed=1, R=1, log=True)
    lev = {s.minute: s.active_levers["KES"].press_height for s in res.snapshots}
    assert lev[29] == "high" and lev[30] == "low" and lev[90] == "low"
    b, out = batch(p, 50, 1)
    fired = [(r, t, k) for r, t, k, _ in out.planb_log]
    assert len(fired) == len(set(fired)) == 50  # exactly once per replica
    assert {m for *_, m in out.planb_log} == {30}


def test_score_rule_only_fires_when_condition_holds():
    p = plain_plans()
    p["KES"] = p["KES"].model_copy(update={"plan_b": [_rule(score_diff="<0", after_minute=60)]})
    _, out = batch(p, 300, 2)
    fired = {r for r, *_ in out.planb_log}
    assert 0 < len(fired) < 300
    for _r, _, _, minute in out.planb_log:
        assert minute >= 60


def test_kpi_rule_from_fixture_plan_can_fire():
    """HAR Plan B: switch to direct if central entries KPI is failing after 25'."""
    b, out = batch(plans(), 300, 3)
    fired = [x for x in out.planb_log if x[1] == 1]
    assert fired and all(m >= 25 for *_, m in fired)
    assert len({r for r, *_ in fired}) == len(fired)


def test_planned_subs_happen_in_their_window():
    res = simulate(plans(), squads(), seed=4, R=1, log=True, truth=truth())
    subs = [e for e in res.events if e.type == "sub" and e.team == "KES" and e.sub_out == "KES-11"]
    assert len(subs) == 1 and subs[0].sub_in == "KES-17"
    assert 60 <= subs[0].minute <= 70  # window 60-65, executed at the next stoppage


def test_too_many_planned_subs_are_rejected():
    many = [Sub(window="60-65", out=f"KES-{i}", into=f"KES-{i + 11}") for i in range(2, 8)]
    with pytest.raises(PlanError):
        simulate(plans(KES={"subs_plan": many}), squads(), seed=1)


def test_unknown_player_or_bad_window_is_rejected():
    with pytest.raises(PlanError):
        simulate(plans(KES={"subs_plan": [Sub(window="60-65", out="KES-99", into="KES-12")]}), squads(), seed=1)
    with pytest.raises(PlanError):
        simulate(plans(KES={"subs_plan": [Sub(window="80-70", out="KES-2", into="KES-13")]}), squads(), seed=1)


def test_runtime_invalid_subs_are_skipped_safely():
    """Subbing a player twice or bringing on someone already used is skipped, never applied."""
    subs = [Sub(window="50-55", out="KES-2", into="KES-13"), Sub(window="70-75", out="KES-2", into="KES-14"),
            Sub(window="75-80", out="KES-3", into="KES-13")]
    res = simulate(plans(KES={"subs_plan": subs}), squads(), seed=5, R=1, log=True)
    kes = [e for e in res.events if e.type == "sub" and e.team == "KES"]
    assert [(e.sub_out, e.sub_in) for e in kes] == [("KES-2", "KES-13")]


def test_in_play_windows_are_limited_to_three():
    subs = [Sub(window=f"{m}-{m + 4}", out=f"KES-{i}", into=f"KES-{i + 10}")
            for m, i in ((50, 2), (58, 3), (66, 4), (74, 5))]
    res = simulate(plans(KES={"subs_plan": subs}), squads(), seed=6, R=1, log=True)
    kes = [e for e in res.events if e.type == "sub" and e.team == "KES"]
    assert len(kes) == 3 and res.snapshots[-1].sub_windows_used["KES"] == 3


def test_half_time_override_subs_do_not_use_a_window():
    ht = simulate(plans(), squads(), seed=7, R=1, log=True, until_minute=45, truth=truth()).final_state
    opt = Option(option_id="KES-HT-C", team="KES", label={"en": "x", "es": "x"}, intent="attacking_subs",
                 subs=[Sub(window="HT", out="KES-11", into="KES-17"), Sub(window="HT", out="KES-8", into="KES-16")])
    _, res = fork_detailed(ht, {"KES": opt}, R=1, seed=7, truth=truth(), log=True)
    first = res.events[:6]
    assert [e.type for e in first[:2]] == ["sub", "sub"]
    assert res.snapshots[0].on_pitch["KES"].count("KES-17") == 1
    assert res.final_state.snapshot.sub_windows_used["KES"] <= 3
    assert res.final_state.snapshot.subs_used["KES"] >= 2


def test_fork_overrides_change_the_second_half_levers():
    ht = simulate(plans(), squads(), seed=8, R=1, log=True, until_minute=45, truth=truth()).final_state
    opt = Option(option_id="KES-HT-B", team="KES", label={"en": "x", "es": "x"}, intent="drop_block",
                 lever_changes=LeverChanges(press_height="mid"))
    _, res = fork_detailed(ht, {"KES": opt}, R=1, seed=8, truth=truth(), log=True)
    assert all(s.active_levers["KES"].press_height == "mid" for s in res.snapshots)
    assert ht.levers["KES"].press_height == "high"  # the state itself is untouched
    out = fork(ht, {"KES": opt}, R=50, seed=8, truth=truth())
    assert out.R == 50
