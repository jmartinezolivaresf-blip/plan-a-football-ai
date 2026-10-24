"""How well can a bench read the other team's levers from play? DEV seasons only (D-048).

    python -m eval.diagnose_estimates [--seasons 9001-9003]

For every team-match of the dev seasons (season plans are known there), it measures in minutes 25-45 the statistics
engine/tracker.py observed_levers uses and reports their range per real lever value, plus the thresholds that sit in
the middle of the gap between neighbouring values (or between their means when the ranges overlap). Writes
eval/results/dev/lever_observation.json; engine/tracker.py PRESS_HIGH_SHARE / LONG_SHARE must match (tested).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from engine.eventsx import rel_x
from engine.tracker import HALF_X, OBSERVE_WINDOW, build_up_actions

OUT = Path(__file__).resolve().parent / "results" / "dev" / "lever_observation.json"


def _threshold(lower: list[float], upper: list[float]) -> float:
    if max(lower) < min(upper):
        return round((max(lower) + min(upper)) / 2, 3)
    return round((statistics.mean(lower) + statistics.mean(upper)) / 2, 3)


def main(argv: list[str] | None = None) -> int:
    from sim.season import build_season

    ap = argparse.ArgumentParser(prog="python -m eval.diagnose_estimates")
    ap.add_argument("--seasons", default="9001-9003")
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seasons.split("-"))
    press, build = defaultdict(list), defaultdict(list)
    for seed in range(lo, hi + 1):
        s = build_season(seed, f"dev-{seed}", random_trait_kinds=True)
        for m in s.public.matches:
            for t in (m.home, m.away):
                lv = s.plans[m.match_id][t].levers
                window = [e for e in m.events if e.team == t and 45 - OBSERVE_WINDOW <= e.minute < 45]
                pr = [e for e in window if e.type == "pressure"]
                press[lv.press_height].append(sum(rel_x(e, t, m.home) >= HALF_X for e in pr) / max(len(pr), 1))
                own = build_up_actions(t, window, m.home)
                build[lv.build_up].append(sum(f for _, f in own) / max(len(own), 1))
    out = {"seasons": [lo, hi], "window_minutes": [45 - OBSERVE_WINDOW, 45],
           "press_high_share": {k: [round(min(v), 3), round(statistics.mean(v), 3), round(max(v), 3), len(v)]
                                for k, v in press.items()},
           "long_share": {k: [round(min(v), 3), round(statistics.mean(v), 3), round(max(v), 3), len(v)]
                          for k, v in build.items()},
           "thresholds": {"PRESS_HIGH_SHARE": [_threshold(press["low"], press["mid"]),
                                               _threshold(press["mid"], press["high"])],
                          "LONG_SHARE": [_threshold(build["short"], build["mixed"]),
                                         _threshold(build["mixed"], build["direct"])]}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
