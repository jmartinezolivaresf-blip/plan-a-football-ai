"""Calibrate the simulator's shot volume on synthetic DEV seasons (never the demo season 2026 or the evaluation seasons).

    python -m eval.calibrate_sim [--workers 8]

One knob, `shot_logit_offset`, shifts the propensity to shoot in the final two fifths of the pitch. Rule fixed
before the run: pick the grid value whose mean shots per match over seasons 11-14 is closest to the middle of the
target range (24-27, eval/run.py TARGETS); all other season statistics are reported, not tuned.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from eval.run import TARGETS, calibration

SEASONS = (11, 12, 13, 14)
GRID = (0.0, -0.1, -0.2, -0.3, -0.4)
OUT = Path(__file__).resolve().parent / "results" / "sim_calibration.json"


def _season_stats(job: tuple[int, float]) -> dict[str, float]:
    from sim.season import build_season

    seed, offset = job
    s = build_season(seed, f"cal-{seed}", coefficients={"shot_logit_offset": offset})
    return {k: v["value"] for k, v in calibration(s).items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.calibrate_sim")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    jobs = [(s, o) for o in GRID for s in SEASONS]
    with ProcessPoolExecutor(args.workers) as ex:
        stats = list(ex.map(_season_stats, jobs))
    rows = []
    for o in GRID:
        per = [st for (s, oo), st in zip(jobs, stats, strict=True) if oo == o]
        mean = {k: round(sum(p[k] for p in per) / len(per), 3) for k in per[0]}
        rows.append({"shot_logit_offset": o, **mean,
                     "in_range": {k: TARGETS[k][0] <= v <= TARGETS[k][1] for k, v in mean.items()}})
    mid = sum(TARGETS["shots_per_match"]) / 2
    chosen = min(rows, key=lambda r: abs(r["shots_per_match"] - mid))
    out = {"seasons": SEASONS, "targets": TARGETS, "grid": rows, "chosen": chosen,
           "rule": "grid value with mean shots per match closest to the middle of the target range"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    for r in rows:
        print({k: r[k] for k in ("shot_logit_offset", "shots_per_match", "goals_per_match", "shot_conversion",
                                 "draw_share", "home_win_share")})
    print("chosen", chosen["shot_logit_offset"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
