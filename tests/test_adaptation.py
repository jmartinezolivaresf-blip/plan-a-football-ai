"""Adaptation detector: finds a build-up switch near its minute and stays quiet when nothing changes."""

from __future__ import annotations

from contracts import LeverChanges, PlanBAction, PlanBCondition, PlanBRule
from engine.tracker import detect_adaptation
from sim import simulate

from .sim_helpers import plain_plans, squads, truth


def _match(switch_at: int | None, seed: int):
    p = plain_plans(kes={"build_up": "mixed"}, har={"build_up": "short"})
    if switch_at is not None:
        rule = PlanBRule(if_=PlanBCondition(after_minute=switch_at),
                         then=PlanBAction(levers=LeverChanges(build_up="direct")))
        p["KES"] = p["KES"].model_copy(update={"plan_b": [rule]})
    return simulate(p, squads(), seed=seed, R=1, log=True, truth=truth(), home="KES").events


def test_switch_to_direct_is_detected_near_its_minute():
    for seed in (1, 2, 3):
        found = detect_adaptation("KES", _match(35, seed), "KES", upto=90)
        assert found is not None
        before, after = found
        assert after.label == "short to long" and after.value > before.value + 0.2
        assert abs(after.minute - 35) <= 10 and after.type == "observed_adaptation"
        assert before.evidence and after.evidence and len(after.evidence) <= 12


def test_no_alarm_without_a_change():
    for seed in (1, 2, 3):
        events = _match(None, seed)
        assert detect_adaptation("KES", events, "KES", upto=90) is None
        assert detect_adaptation("HAR", events, "KES", upto=90) is None


def test_detector_never_reads_past_its_cutoff():
    events = _match(35, 4)
    assert detect_adaptation("KES", events, "KES", upto=30) is None  # the switch at 35' is in the future
    late = detect_adaptation("KES", events, "KES", upto=90)
    assert late is not None and late[1].claim_id == "c_ad_KES_90_after"
    first = next(m for m in range(1, 91) if detect_adaptation("KES", events, "KES", upto=m))
    found = detect_adaptation("KES", events, "KES", upto=first)
    assert first > 35 and found[1].claim_id == f"c_ad_KES_{first:02d}_after"
    ids = {e.event_id for e in events if e.minute <= first}
    assert set(found[0].evidence + found[1].evidence) <= ids
