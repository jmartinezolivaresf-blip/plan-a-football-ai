"""Plan Tracker statuses read consistently with the value and target shown to viewers."""

from __future__ import annotations


def test_settled_cumulative_kpis_never_contradict_their_target():
    from engine.tracker import settled
    assert settled(">=", 4, 5, "high_turnovers", 89) == "on_track"
    assert settled("<=", 14, 15, "balls_in_behind_conceded", 60) == "failing"
    assert settled("<=", 14, 8, "balls_in_behind_conceded", 60) is None  # still open: the expected curve decides
    assert settled(">=", 0.4, 0.5, "final_third_entries_share", 60) is None  # shares can still fall
    assert settled(">=", 4, 5, "high_turnovers", 5) is None  # too early to say anything


def test_at_the_deadline_a_kpi_is_met_or_missed():
    from engine.tracker import settled
    assert settled(">=", 4, 3, "high_turnovers", 90, by_minute=90) == "failing"
    assert settled(">=", 0.4, 0.45, "final_third_entries_share", 90, by_minute=90) == "on_track"
    assert settled(">=", 6, 7, "high_turnovers", 50, by_minute=45) == "on_track"
    assert settled("<=", 14, 10, "balls_in_behind_conceded", 89, by_minute=90) is None


def test_the_deadline_verdict_is_not_delayed_by_the_hysteresis():
    from contracts import Kpi
    from engine.tracker import PlanTracker

    from .sim_helpers import plans
    plan = plans()["KES"].model_copy(update={"kpis": [Kpi(id="k1", metric="high_turnovers", target=">=4",
                                                          by_minute=90)]})
    tracker = PlanTracker(plan, "KES", None, {"KES:high_turnovers": [0.0] * 91})  # high turnovers need no xG model
    tracker.reported["k1"] = "on_track"  # what the live reading showed until now
    statuses, _ = tracker.at(90, [])
    assert statuses[0].status == "failing"  # 0 high turnovers against >= 4 at the deadline
