"""Football invariants on logged R=1 matches (several seeds)."""

from __future__ import annotations

import pytest

from contracts import Event, Snapshot, zone_index

from .sim_helpers import ON_BALL, logged_match

SEEDS = [1, 2, 3, 4, 5]


@pytest.fixture(params=SEEDS)
def match(request):
    return logged_match(request.param)


def test_events_and_snapshots_are_contract_objects(match):
    assert match.events and all(isinstance(e, Event) for e in match.events)
    assert [s.minute for s in match.snapshots] == list(range(91))
    assert all(isinstance(s, Snapshot) and s.kpis == [] and s.condition_est == {} for s in match.snapshots)


def test_clock_ids_zones_and_periods(match):
    evs = match.events
    assert len({e.event_id for e in evs}) == len(evs)
    assert all(a.t < b.t for a, b in zip(evs, evs[1:], strict=False))
    assert all(e.zone == zone_index(e.x, e.y) for e in evs)
    assert all(0 <= e.x <= 105 and 0 <= e.y <= 68 for e in evs)
    periods = [e.period for e in evs]
    assert periods == sorted(periods)
    assert all(e.t <= 2701 for e in evs if e.period == 1)
    assert all(e.t >= 2700 for e in evs if e.period == 2)


def test_score_equals_goal_events(match):
    goals = {"KES": 0, "HAR": 0}
    for e in match.events:
        if e.type == "goal":
            goals[e.team] += 1
    assert match.snapshots[-1].score == goals == match.final_state.snapshot.score
    shots = [e for e in match.events if e.type == "shot" and e.outcome == "goal"]
    assert len(shots) == sum(goals.values())


def test_scores_never_decrease(match):
    for a, b in zip(match.snapshots, match.snapshots[1:], strict=False):
        assert all(b.score[t] >= a.score[t] for t in a.score)


def test_possession_continuity(match):
    """After a possession change, the next on-ball action is by the winning team; passes/carries start with
    the player who won the ball (restart events such as goal kicks are taken by the specialist)."""
    evs = match.events
    for i, e in enumerate(evs):
        if e.type != "possession_change":
            continue
        nxt = next((f for f in evs[i + 1:] if f.type in ON_BALL), None)
        if nxt is None:
            continue
        assert nxt.team == e.team, e.event_id
        if nxt.type in ("pass", "long_ball", "cross", "carry", "shot", "throw_in"):
            assert nxt.player_id == e.player_id, e.event_id


def test_no_team_acts_without_the_ball(match):
    """Between two on-ball actions of different teams there is always a possession change or a restart."""
    evs = [e for e in match.events if e.type in ON_BALL | {"possession_change", "goal", "clearance"}]
    for a, b in zip(evs, evs[1:], strict=False):
        if a.type in ON_BALL and b.type in ON_BALL and a.team != b.team:
            assert b.type in ("kick_off", "goal_kick"), (a.event_id, b.event_id)


def test_completed_passes_chain_to_receiver_and_ball_does_not_jump(match):
    evs = [e for e in match.events if e.type in ON_BALL]
    for a, b in zip(evs, evs[1:], strict=False):
        if a.type in ("pass", "long_ball", "throw_in", "goal_kick") and a.outcome == "success" and b.team == a.team \
                and b.type in ("pass", "long_ball", "cross", "carry", "shot"):
            assert b.player_id == a.receiver_id, a.event_id
            assert abs(b.x - a.end_x) < 0.2 and abs(b.y - a.end_y) < 0.2, a.event_id


def test_subs_follow_the_rules(match):
    for team in ("KES", "HAR"):
        subs = [e for e in match.events if e.type == "sub" and e.team == team]
        assert len(subs) <= 5
        in_play_windows = {e.t for e in subs if e.t != 2700.0 and not (2700 <= e.t < 2701 and e.period == 2)}
        assert len(in_play_windows) <= 3
        assert match.snapshots[-1].subs_used[team] == len(subs)
        for s in subs:
            later = [e for e in match.events if e.t > s.t and e.player_id == s.sub_out]
            assert not later, f"{s.sub_out} acted after being subbed off"
            earlier = [e for e in match.events if e.t < s.t and e.player_id == s.sub_in]
            assert not earlier, f"{s.sub_in} acted before coming on"
            assert s.sub_in not in {p for snap in match.snapshots if snap.minute < s.minute
                                    for p in snap.on_pitch[team]}
    for snap in match.snapshots:
        for ids in snap.on_pitch.values():
            assert len(ids) == 11 and len(set(ids)) == 11


def test_restarts_are_coherent(match):
    evs = match.events
    for i, e in enumerate(evs):
        if e.type == "goal":
            nxt = next(f for f in evs[i + 1:] if f.type in ON_BALL)
            assert nxt.type == "kick_off" and nxt.team != e.team
        if e.type == "shot" and e.outcome == "off_target":
            nxt = next(f for f in evs[i + 1:] if f.type in ON_BALL)
            assert nxt.type == "goal_kick" and nxt.team != e.team
    for e in evs:
        if e.set_piece_ref:
            ref = next(f for f in evs if f.event_id == e.set_piece_ref)
            assert ref.type == "corner" and ref.team == e.team


def test_statistics_are_plausible_for_one_match(match):
    types = [e.type for e in match.events]
    assert 500 < types.count("pass") < 1400
    assert 8 < types.count("shot") < 60
    assert types.count("goal") < 12
    assert types.count("kick_off") == 2 + types.count("goal")
