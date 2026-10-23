"""Calibrate the ONLINE adaptation detector on synthetic DEV seasons (never the demo season 2026 or eval seasons).

    python -m eval.calibrate_adaptation [--workers 8]

The live detector re-tests at every minute with the events seen so far, so its false-alarm rate is the chance of an
alarm at ANY minute of a match, not of one test at full time (an earlier version measured the latter; D-038).

Null: every team-match of seasons 11-14 (season plans never change build-up); any alarm is a false alarm.
Power: for 24 matches of seasons 11-12 the home team switches build-up at a known minute (mixed/short -> direct,
direct -> short) through a Plan B rule. A hit is a first alarm at or after the switch (an alarm before it counts
as a false alarm); we report the detection delay and the error of the estimated change minute.
Rule: the smallest grid z whose online false-alarm rate is <= 5% per team-match, at min_change 0.2.
"""

from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from engine.tracker import ADAPT_MIN_CHANGE, ADAPT_MIN_SIDE, build_up_actions

NULL_SEASONS = (11, 12, 13, 14)
POWER_SEASONS = (11, 12)
Z_GRID = (3.0, 3.5, 4.0, 4.5, 5.0)
MAX_FALSE_ALARM = 0.05
OUT = Path(__file__).resolve().parent / "results" / "adaptation_calibration.json"


def online_alarms(flags: list[tuple[int, float]], min_side: int = ADAPT_MIN_SIDE,
                  min_change: float = ADAPT_MIN_CHANGE) -> dict[float, tuple[int, int] | None]:
    """For each grid z: (first minute the live detector fires, estimated change minute then) or None."""
    minutes = np.array([m for m, _ in flags])
    f = np.array([x for _, x in flags], dtype=float)
    prefix = np.concatenate([[0.0], np.cumsum(f)])
    out: dict[float, tuple[int, int] | None] = dict.fromkeys(Z_GRID)
    for minute in range(1, 91):
        n = int(np.searchsorted(minutes, minute, side="right"))
        if n < 2 * min_side:
            continue
        k = np.arange(min_side, n - min_side + 1)
        before, after, pooled = prefix[k] / k, (prefix[n] - prefix[k]) / (n - k), prefix[n] / n
        se = np.sqrt(pooled * (1 - pooled) * (1 / k + 1 / (n - k)))
        z = np.where(se > 0, np.abs(after - before) / np.where(se > 0, se, 1), 0.0)
        z = np.where(np.abs(after - before) >= min_change, z, 0.0)
        best = int(np.argmax(z))
        for zc in Z_GRID:
            if out[zc] is None and z[best] >= zc:
                out[zc] = (minute, int(minutes[k[best]]))
    return out


def _flags(team, events, home):
    return [(e.minute, f) for e, f in build_up_actions(team, events, home)]


def null_season(seed: int) -> list[dict]:
    from sim.season import build_season

    s = build_season(seed, f"cal-{seed}")
    return [online_alarms(_flags(t, m.events, m.home)) for m in s.public.matches for t in (m.home, m.away)]


def switched_match(job: tuple[int, int]) -> dict:
    from contracts import LeverChanges, PlanBAction, PlanBCondition, PlanBRule
    from sim import simulate
    from sim.season import build_season

    seed, k = job
    s = build_season(seed, f"cal-{seed}")
    m = s.public.matches[k]
    plans = s.plans[m.match_id]
    plan = plans[m.home]
    old = plan.levers.build_up
    new = "short" if old == "direct" else "direct"
    when = 25 + (k * 7) % 40
    plan = plan.model_copy(update={"plan_b": [PlanBRule(if_=PlanBCondition(after_minute=when),
                                                        then=PlanBAction(levers=LeverChanges(build_up=new)))]})
    res = simulate({m.home: plan, m.away: plans[m.away]}, s.public.squads, seed=seed * 100 + k + 7, R=1, log=True,
                   truth=s.truth, config=s.config, home=m.home)
    return {"switch": f"{old}->{new}", "minute": when, "alarms": online_alarms(_flags(m.home, res.events, m.home))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.calibrate_adaptation")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    with ProcessPoolExecutor(args.workers) as ex:
        nulls = [r for rows in ex.map(null_season, NULL_SEASONS) for r in rows]
        power = list(ex.map(switched_match, [(s, k) for s in POWER_SEASONS for k in range(24)]))
    grid = []
    for zc in Z_GRID:
        early = sum(1 for p in power if p["alarms"][zc] and p["alarms"][zc][0] < p["minute"])
        hits = [p for p in power if p["alarms"][zc] and p["alarms"][zc][0] >= p["minute"]]
        delays = sorted(p["alarms"][zc][0] - p["minute"] for p in hits)
        errors = sorted(abs(p["alarms"][zc][1] - p["minute"]) for p in hits)
        grid.append({"min_z": zc, "min_change": ADAPT_MIN_CHANGE,
                     "false_alarm_rate": round(sum(a[zc] is not None for a in nulls) / len(nulls), 4),
                     "power": round(len(hits) / len(power), 3), "alarms_before_the_switch": early,
                     "median_delay_min": statistics.median(delays) if hits else None,
                     "p90_delay_min": delays[int(0.9 * (len(delays) - 1))] if hits else None,
                     "median_change_minute_error": statistics.median(errors) if hits else None,
                     "p90_change_minute_error": errors[int(0.9 * (len(errors) - 1))] if hits else None})
    chosen = next((g for g in grid if g["false_alarm_rate"] <= MAX_FALSE_ALARM), grid[-1])
    out = {"procedure": "online: re-tested every minute on the events seen so far",
           "null_team_matches": len(nulls), "switched_matches": len(power), "min_side": ADAPT_MIN_SIDE,
           "seasons": {"null": NULL_SEASONS, "power": POWER_SEASONS}, "grid": grid, "chosen": chosen,
           "rule": f"smallest z with online false-alarm rate <= {MAX_FALSE_ALARM:.0%} per team-match at min_change "
                   f"{ADAPT_MIN_CHANGE}"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
