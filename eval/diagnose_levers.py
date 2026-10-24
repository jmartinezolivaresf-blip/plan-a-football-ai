"""Do levers pay off by targeting a real weakness, or regardless of the opponent? DEV seasons only.

    python -m eval.diagnose_levers [--seasons 9001-9003] [--R 400] [--workers 8]

For every dev matchup the home team plays each single-lever variation of its season plan in the TRUE world, with
common random numbers against the unchanged plan. Each row is labelled by whether the lever targets one of the
opponent's hidden traits (eval.run.attacks). Reported per lever value: mean xPts change when it targets a real trait
vs when it does not (the latter is the lever's systematic effect). Writes eval/results/dev/lever_effects.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "results" / "dev" / "lever_effects.json"
VARIANTS = [("press_height", v) for v in ("high", "mid", "low")] + \
           [("build_up", v) for v in ("short", "mixed", "direct")] + \
           [("attack_channel", v) for v in ("left", "center", "right", "balanced")] + \
           [("corner_delivery", v) for v in ("near_post", "far_post", "short")]


def _points(goals_for, goals_against) -> np.ndarray:
    a, b = np.asarray(goals_for), np.asarray(goals_against)
    return np.where(a > b, 3.0, np.where(a == b, 1.0, 0.0))


def matchup_rows(job: tuple[int, int, int]) -> list[dict]:
    from eval.run import attacks
    from sim import simulate
    from sim.season import build_season

    seed, k, R = job
    s = build_season(seed, f"dev-{seed}", random_trait_kinds=True)
    m = s.public.matches[k]
    plans = s.plans[m.match_id]
    home, away = m.home, m.away
    base_plan = plans[home]
    traits = s.truth.teams[away].traits
    fullbacks = [p.player_id for p in s.public.squads.teams[away].players if p.starter and p.position in ("LB", "RB")]
    variants = [(lever, value) for lever, value in VARIANTS if getattr(base_plan.levers, lever) != value]
    variants += [("press_target", pid) for pid in fullbacks]

    def run(plan):
        res = simulate({home: plan, away: plans[away]}, s.public.squads, seed=seed * 1000 + k, R=R, truth=s.truth,
                       config=s.config, home=home)
        return _points(res.outcomes.goals[home], res.outcomes.goals[away])

    base = run(base_plan)
    rows = []
    for lever, value in variants:
        changes = {lever: value}
        if lever == "press_target":
            changes["press_height"] = "high"  # targeting needs the press up
        plan = base_plan.model_copy(update={"levers": base_plan.levers.model_copy(update=changes)})
        d = run(plan) - base
        rows.append({"season": seed, "match": k, "lever": lever, "value": value if lever != "press_target" else
                     "fullback", "targets_trait": any(attacks(plan.levers, t) for t in traits)
                     and not any(attacks(base_plan.levers, t) for t in traits),
                     "delta_xpts": float(d.mean())})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.diagnose_levers")
    ap.add_argument("--seasons", default="9001-9003")
    ap.add_argument("--R", type=int, default=400)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seasons.split("-"))
    jobs = [(s, k, args.R) for s in range(lo, hi + 1) for k in range(24)]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = [r for rs in ex.map(matchup_rows, jobs) for r in rs]
    table = {}
    for lever, value in sorted({(r["lever"], r["value"]) for r in rows}):
        sel = [r for r in rows if r["lever"] == lever and r["value"] == value]
        hit = [r["delta_xpts"] for r in sel if r["targets_trait"]]
        miss = [r["delta_xpts"] for r in sel if not r["targets_trait"]]
        table[f"{lever}={value}"] = {
            "n_targeting": len(hit), "mean_when_targeting_trait": round(statistics.mean(hit), 3) if hit else None,
            "n_other": len(miss), "mean_otherwise": round(statistics.mean(miss), 3) if miss else None}
    out = {"seasons": [lo, hi], "R": args.R, "matchups": len(jobs), "effects": table}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    for k, v in table.items():
        print(f"{k:28s} targeting n={v['n_targeting']:3d} mean={v['mean_when_targeting_trait']}   "
              f"otherwise n={v['n_other']:3d} mean={v['mean_otherwise']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
