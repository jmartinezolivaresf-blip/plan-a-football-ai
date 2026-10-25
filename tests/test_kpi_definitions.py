"""The simulator's KPI counters (expected curves, in-sim Plan B) match the engine's event definitions (D-015)."""

from __future__ import annotations

import pytest

from engine.eventsx import entry_lane, is_ball_in_behind, is_entry, is_high_turnover
from sim import simulate

from .sim_helpers import plain_plans, plans, squads, truth


@pytest.mark.parametrize("seed", [1, 2])
@pytest.mark.parametrize("variant", ["fixture", "high_press_vs_direct"])
def test_sim_counters_match_engine_event_metrics(seed, variant):
    p = plans() if variant == "fixture" else plain_plans(kes={"press_height": "high"}, har={"build_up": "direct"})
    res = simulate(p, squads(), seed=seed, R=1, log=True, truth=truth(), home="KES")
    ev, tr = res.events, res.outcomes.kpi_trajectories
    for team in ("KES", "HAR"):
        engine = {
            "high_turnovers": sum(e.team == team and is_high_turnover(e, "KES") for e in ev),
            "entries_total": sum(e.team == team and is_entry(e, "KES") for e in ev),
            "entries_center": sum(e.team == team and is_entry(e, "KES") and entry_lane(e, "KES") == 1 for e in ev),
            "balls_in_behind_conceded": sum(e.team != team and is_ball_in_behind(e, "KES") for e in ev),
        }
        for metric, value in engine.items():
            # the trajectory stops at minute 90; events in stoppage time may add one
            assert 0 <= value - tr[f"{team}:{metric}"][-1] <= 1, (team, metric)
