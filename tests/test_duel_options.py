"""Half-time options are real alternatives: each changes the levers in force and no two are the same (D-054, D-055).

Regression for the demo match at seed 236: Kestrel's Plan B had already switched it to a direct build-up at 25', and
its bench still offered "Go direct", a copy of "Stay the course" with identical numbers in both matrices."""

from __future__ import annotations

import asyncio
import itertools

import pytest

from agents.duel import offline_options, run_duel
from contracts import I18nText, Option
from contracts.option import changes_nothing, tactics
from contracts.plan import LeverChanges, Sub
from engine import duel as dm
from engine.api import Seeds
from engine.tracker import build_up_actions
from pipeline.build import make_engine, run_prematch_for
from sim.season import build_season

KES_AT_HALF_TIME = {"press_height": "mid", "press_target": None, "build_up": "direct", "attack_channel": "balanced",
                    "corner_delivery": "far_post"}  # its sealed plan said build_up "mixed"; the Plan B fired at 25'


def _ev(levers, diff, struggling=False, subs=True):
    return {"team": "KES", "opponent": "HAR", "score_diff": diff, "levers": levers,
            "kpis": [{"metric": "high_turnovers", "label": "failing" if struggling else "on_track",
                      "claim_id": "c_kpi_KES_k1_45"}],
            "kpi_claims": ["c_kpi_KES_k1_45"], "tired_attackers": ["KES-9", "KES-11"] if subs else [],
            "bench_attackers": ["KES-19", "KES-20"] if subs else [], "on_pitch": []}


def _assert_real_alternatives(options, levers):
    assert options[0].intent == "stay_the_course" and changes_nothing(levers, options[0].lever_changes)
    keys = [tactics(levers, o.lever_changes, o.subs) for o in options]
    assert len(set(keys)) == len(options) == 3, [o.label_en for o in options]


def test_kestrel_after_its_plan_b_is_not_offered_what_it_already_does():
    options = offline_options(_ev(KES_AT_HALF_TIME, diff=2)).options
    assert [o.label_en for o in options] == ["Stay the course", "Protect the lead", "Back to short passing"]
    _assert_real_alternatives(options, KES_AT_HALF_TIME)


def test_offline_options_are_three_real_alternatives_in_every_situation():
    for press, build, channel, diff, struggling, subs in itertools.product(
            ("high", "mid", "low"), ("short", "mixed", "direct"), ("balanced", "right"), (-1, 0, 1), (False, True),
            (False, True)):
        levers = {**KES_AT_HALF_TIME, "press_height": press, "build_up": build, "attack_channel": channel}
        _assert_real_alternatives(offline_options(_ev(levers, diff, struggling, subs)).options, levers)


def test_a_move_already_in_force_falls_back_to_the_next_real_alternative():
    deep = {**KES_AT_HALF_TIME, "press_height": "low", "build_up": "mixed"}
    options = offline_options(_ev(deep, diff=1)).options  # "Protect the lead" = sit deep, which they already do
    assert "Protect the lead" not in [o.label_en for o in options]
    _assert_real_alternatives(options, deep)


def test_tactics_keep_the_levers_an_option_does_not_set():
    after, subs = tactics(KES_AT_HALF_TIME, LeverChanges(press_height="low"))
    assert dict(after) == {**KES_AT_HALF_TIME, "press_height": "low"} and subs == ()
    assert changes_nothing(KES_AT_HALF_TIME, LeverChanges(build_up="direct"))
    assert changes_nothing(KES_AT_HALF_TIME, LeverChanges(press_target="none"))  # "no target" is no target
    assert not changes_nothing(KES_AT_HALF_TIME, LeverChanges(build_up="short"))
    assert not changes_nothing(KES_AT_HALF_TIME, LeverChanges(), [Sub(window="HT", out="KES-9", into="KES-19")])


def _est(n, intent, changes):
    return Option(option_id=f"KES-EST-HAR-{n}", team="HAR", intent=intent, estimated=True,
                  label=I18nText(en=intent, es=intent), lever_changes=changes)


def test_an_estimate_that_changes_nothing_seen_is_merged_into_keep_their_plan():
    seen = {"press_height": "high", "build_up": "direct", "attack_channel": "balanced"}
    guesses = [_est(1, "stay_the_course", LeverChanges()),
               _est(2, "attacking_subs", LeverChanges(press_height="high", attack_channel="balanced")),
               _est(3, "short_build_up", LeverChanges(build_up="short"))]
    kept, probs = dm.merge_equivalent(guesses, [0.2, 0.68, 0.12], seen)
    assert [o.option_id for o in kept] == ["KES-EST-HAR-1", "KES-EST-HAR-3"]
    assert probs == [0.2 + 0.68, 0.12]
    kept, probs = dm.merge_equivalent(guesses, [0.2, 0.68, 0.12], {**seen, "press_height": "mid"})
    assert len(kept) == 3 and probs == [0.2, 0.68, 0.12]
    assert dm.duplicate_pairs(guesses, seen) == [("KES-EST-HAR-1", "KES-EST-HAR-2")]


# ---------------------------------------------------------------------------------------- the real demo half-time

@pytest.fixture(scope="module")
def at_236():
    """The old demo match (season 2026, seed 236) at half-time, after both benches decided."""
    season = build_season(2026)
    pre = run_prematch_for(season, "KES", "HAR", None)
    plans = {t: r.chosen for t, r in pre.results.items()}
    engine = make_engine(season, "KES", "HAR", Seeds(match=236))
    engine.claims.update(pre.claims)
    engine.set_plans(plans)
    engine.play_first_half()
    privates, broadcast, _ = asyncio.run(run_duel(engine, "KES", "HAR", plans))
    return engine, plans, privates, broadcast


def _rows_and_cols(m):
    rows = [tuple(c.xpts[m.row_team] for c in row) for row in m.cells]
    cols = [tuple(row[j].xpts[m.row_team] for row in m.cells) for j in range(len(m.cols))]
    return rows, cols


def test_the_demo_bench_starts_from_its_plan_b(at_236):
    engine, plans, privates, _ = at_236
    now = engine.ht_state.levers["KES"].model_dump()
    assert plans["KES"].levers.build_up == "mixed" and now["build_up"] == "direct"  # the Plan B fired at 25'
    labels = [o.label.en for o in privates["KES"].options]
    assert "Go direct" not in labels
    for team, priv in privates.items():
        _assert_real_alternatives(priv.options, engine.ht_state.levers[team].model_dump())


def test_no_two_rows_or_columns_of_any_matrix_are_the_same(at_236):
    _, _, privates, broadcast = at_236
    for m in [broadcast.true_matrix] + [p.believed_matrix for p in privates.values()]:
        rows, cols = _rows_and_cols(m)
        assert len(set(rows)) == len(rows) and len(set(cols)) == len(cols), m.matrix_id
    true = broadcast.true_matrix
    assert true.rows == [o.option_id for o in privates[true.row_team].options]
    assert true.cols == [o.option_id for o in privates[true.col_team].options]
    for p in privates.values():
        assert p.believed_matrix.rows == [o.option_id for o in p.options]
        assert p.believed_matrix.cols == [e.option.option_id for e in p.opponent_estimate.options]


def test_the_engine_rejects_an_option_that_changes_nothing(at_236):
    engine = at_236[0]

    def option(changes, intent="go_direct"):
        return Option(option_id="KES-X", team="KES", intent=intent, label=I18nText(en="x", es="x"),
                      lever_changes=changes)
    res = engine.validate_option(engine.match_id, option(LeverChanges(build_up="direct")))
    assert not res.ok and "changes nothing" in res.errors[0]
    assert engine.validate_option(engine.match_id, option(LeverChanges(build_up="short"))).ok
    assert not engine.validate_option(engine.match_id, option(LeverChanges(press_height="low"), "stay_the_course")).ok
    stay = option(LeverChanges(), "stay_the_course")
    est = engine.estimate_opponent_options(engine.match_id, "KES").options
    with pytest.raises(ValueError, match="same tactics"):
        engine.price_matrix(engine.match_id, [stay, option(LeverChanges(build_up="direct"))],
                            [e.option for e in est], 50, "KES", [e.probability for e in est])


def test_a_lever_already_in_force_changes_nothing_and_a_real_switch_changes_play(at_236):
    engine = at_236[0]
    world, ht = engine.true_world, engine.ht_state

    def opt(changes):
        return Option(option_id="KES-X", team="KES", intent="go_direct", label=I18nText(en="x", es="x"),
                      lever_changes=changes)
    stay = world.fork(ht, {}, R=64, seed=3)
    same = world.fork(ht, {"KES": opt(LeverChanges(build_up="direct"))}, R=64, seed=3)
    short = world.fork(ht, {"KES": opt(LeverChanges(build_up="short"))}, R=64, seed=3)
    assert same.goals == stay.goals  # common random numbers: the same tactics give the very same replicas
    assert short.goals != stay.goals

    def long_share(changes, seed):
        _, res = world.fork_detailed(ht, {"KES": opt(changes)}, R=1, seed=seed, log=True)
        own = list(build_up_actions("KES", [e for e in res.events if e.period == 2], engine.home))
        return sum(f for _, f in own) / max(len(own), 1)
    direct = [long_share(LeverChanges(build_up="direct"), s) for s in range(6)]
    back = [long_share(LeverChanges(build_up="short"), s) for s in range(6)]
    assert sum(direct) / 6 > sum(back) / 6 + 0.1  # going back to short passing really plays fewer long balls
