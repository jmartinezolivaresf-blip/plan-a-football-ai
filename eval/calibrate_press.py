"""Balance the press heights on DEV seasons: no press height should win or lose on average (D-047).

    python -m eval.calibrate_press [--workers 12]

Diagnosis (eval/diagnose_levers.py, dev seasons 9001-9003): pressing high cost ~0.3 xPts and sitting deep gained
~0.16 xPts against every opponent, so rational benches never pressed, the press-based weaknesses were never worth
attacking and "sit deep" dominated half-time matrices. Meanwhile pressing the full-back who really is weak under
pressure gained +0.075 xPts over pressing without a target, so the interaction exists; the main effects hid it.

For each grid point, every dev matchup's home team plays its season plan with press_height high / mid / low (common
random numbers) and we measure xPts(high) - xPts(mid) and xPts(low) - xPts(mid). Rule fixed before running: pick
the point with the smallest max(|high - mid|, |low - mid|); ties go to the point closest to the defaults.
Knobs: the space a high line leaves for long balls, the extra fatigue of pressing, how well a pressing team covers
its own final two fifths, and how compact a low block is there. Writes eval/results/press_calibration.json.
"""

from __future__ import annotations

import argparse
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from sim.model import DEFAULT_COEFFICIENTS

SEASONS = (9001, 9002, 9003, 9004)
MATCHES = range(0, 24, 2)
R = 200
GRID = {"long_vs_high_line": (0.4, 0.2), "high_press_fatigue_mult": (1.25, 1.1),
        "high_press_cover_scale": (1.0, 1.2, 1.4), "low_block_pressure_scale": (0.8, 0.9)}
OUT = Path(__file__).resolve().parent / "results" / "press_calibration.json"


def _effects(job: tuple[int, int, dict]) -> tuple[float, float]:
    from sim import simulate
    from sim.season import build_season

    seed, k, coef = job
    s = build_season(seed, f"dev-{seed}", random_trait_kinds=True, coefficients=coef)
    m = s.public.matches[k]
    plans = s.plans[m.match_id]
    xp = {}
    for ph in ("high", "mid", "low"):
        p = plans[m.home].model_copy(update={"levers": plans[m.home].levers.model_copy(
            update={"press_height": ph, "press_target": None})})
        res = simulate({m.home: p, m.away: plans[m.away]}, s.public.squads, seed=seed * 1000 + k, R=R,
                       truth=s.truth, config=s.config, home=m.home)
        gf, ga = np.array(res.outcomes.goals[m.home]), np.array(res.outcomes.goals[m.away])
        xp[ph] = float(np.where(gf > ga, 3.0, np.where(gf == ga, 1.0, 0.0)).mean())
    return xp["high"] - xp["mid"], xp["low"] - xp["mid"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.calibrate_press")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args(argv)
    points = [dict(zip(GRID, values, strict=True)) for values in itertools.product(*GRID.values())]
    rows = []
    with ProcessPoolExecutor(args.workers) as ex:
        for coef in points:
            eff = list(ex.map(_effects, [(s, k, coef) for s in SEASONS for k in MATCHES]))
            hi, lo = float(np.mean([e[0] for e in eff])), float(np.mean([e[1] for e in eff]))
            distance = sum(abs(coef[k] - DEFAULT_COEFFICIENTS.get(k, 1.0)) for k in coef)
            rows.append({**coef, "high_minus_mid": round(hi, 3), "low_minus_mid": round(lo, 3),
                         "imbalance": round(max(abs(hi), abs(lo)), 3), "distance_from_defaults": round(distance, 3)})
            print(rows[-1], flush=True)
    chosen = min(rows, key=lambda r: (r["imbalance"], r["distance_from_defaults"]))
    out = {"seasons": SEASONS, "matches_per_season": len(MATCHES), "R": R, "grid": rows, "chosen": chosen,
           "rule": "smallest max(|high - mid|, |low - mid|) in xPts; ties to the point closest to the defaults"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print("chosen", chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
