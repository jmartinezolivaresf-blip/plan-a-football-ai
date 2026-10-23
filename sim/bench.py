"""Simulator benchmark (single process, single core).

    python -m sim.bench [--repeat 3]
"""

from __future__ import annotations

import argparse
import json
import platform
import time
import tracemalloc
from pathlib import Path

from contracts import Plan, Squads
from contracts.eval_only import Truth

from . import fork, simulate

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def _load():
    raw = json.loads((ROOT / "plans_fixture.json").read_text())["plans"]
    plans = {k: Plan.model_validate(v) for k, v in raw.items()}
    squads = Squads.model_validate(json.loads((ROOT / "squads_fixture.json").read_text()))
    truth = Truth.model_validate(json.loads((ROOT / "eval_only" / "truth_fixture.json").read_text()))
    return plans, squads, truth


def _best(fn, repeat: int) -> float:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    plans, squads, truth = _load()
    ht = simulate(plans, squads, seed=1, R=1, log=True, until_minute=45, truth=truth).final_state
    rows = [
        ("R=1 full match, log=True", lambda: simulate(plans, squads, seed=2, R=1, log=True, truth=truth)),
        ("R=1 full match, log=False", lambda: simulate(plans, squads, seed=2, R=1, truth=truth)),
        ("R=500 full matches", lambda: simulate(plans, squads, seed=3, R=500, truth=truth)),
    ]
    rows += [(f"R={r} second halves (fork from HT)", (lambda r=r: fork(ht, {}, R=r, seed=4, truth=truth)))
             for r in (100, 300, 500)]
    print(f"python {platform.python_version()} on {platform.machine()} ({platform.system()})")
    for label, fn in rows:
        print(f"{label:38s} {_best(fn, args.repeat):7.3f} s  (best of {args.repeat})")
    tracemalloc.start()
    fork(ht, {}, R=500, seed=4, truth=truth)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"{'peak traced memory, R=500 fork':38s} {peak / 1e6:7.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
