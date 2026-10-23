"""Plan Tracker statuses read consistently with the value and target shown to viewers."""

from __future__ import annotations


def test_settled_cumulative_kpis_never_contradict_their_target():
    from engine.tracker import settled
    assert settled(">=", 4, 5, "high_turnovers", 89) == "on_track"
    assert settled("<=", 14, 15, "balls_in_behind_conceded", 60) == "failing"
    assert settled("<=", 14, 8, "balls_in_behind_conceded", 60) is None  # still open: the expected curve decides
    assert settled(">=", 0.4, 0.5, "final_third_entries_share", 60) is None  # shares can still fall
    assert settled(">=", 4, 5, "high_turnovers", 5) is None  # too early to say anything
