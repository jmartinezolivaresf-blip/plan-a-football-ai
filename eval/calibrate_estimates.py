"""Calibrate how a bench anticipates the other bench's half-time call, from DEV duels only (E7, D-048).

    python -m eval.calibrate_estimates [--seasons 9001-9006] [--workers 12]

Plays the full pipeline (pre-match, first half, duel) for the evaluation matchups in dev seasons with random trait
kinds, and records, for every bench, the score situation of the OTHER bench (leading / level / trailing at half-time)
and the intent that bench really chose. The estimator's probabilities for its three slots (keep the plan, the
situational move, the build-up switch) are the Laplace-smoothed frequencies of those slots per situation: like
scouting how managers usually react, learnt on dev matches only. Writes eval/results/estimate_calibration.json;
engine/api.py ESTIMATE_PROBS must match it (tested).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

OUT = Path(__file__).resolve().parent / "results" / "estimate_calibration.json"
SLOT_OF = {"stay_the_course": 0, "protect_lead": 1, "attacking_subs": 1, "press_higher": 1, "drop_block": 1,
           "go_direct": 2, "short_build_up": 2}


def situation(diff: int) -> str:
    return "leading" if diff > 0 else "trailing" if diff < 0 else "level"


def _duel(job: tuple[int, int, str, str]) -> list[dict]:
    from engine.api import Seeds
    from pipeline.build import build, run_prematch_for
    from sim.season import build_season

    seed, k, home, away = job
    season = build_season(seed, f"dev-{seed}", random_trait_kinds=True)
    pre = run_prematch_for(season, home, away, None, Seeds(match=700 + k))
    b = build(season=season, prematch=pre, home=home, away=away, match_seed=700 + k).bundle
    ht = b.eval["story"]["ht_score"]
    out = []
    for team in (home, away):
        opp = away if team == home else home
        chosen = b.duel.broadcast.revealed[opp].option_id
        intent = next(o.intent for o in b.duel.private[opp].options if o.option_id == chosen)
        est = b.duel.private[team].opponent_estimate.options
        out.append({"season": seed,
                    "match": f"{home}-{away}", "opponent_situation": situation(ht[opp] - ht[team]),
                    "opponent_intent": intent, "estimated_intents": [e.option.intent for e in est],
                    "prob_on_actual": sum(e.probability for e in est if e.option.intent == intent),
                    "own_options": [o.intent for o in b.duel.private[team].options],
                    "dominant": b.duel.broadcast.true_matrix.readings[team].dominant is not None})
    return out


def main(argv: list[str] | None = None) -> int:
    from eval.run import MATCHUPS

    ap = argparse.ArgumentParser(prog="python -m eval.calibrate_estimates")
    ap.add_argument("--seasons", default="9001-9006")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default=str(OUT), help="where to write (a different file for a check run)")
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seasons.split("-"))
    jobs = [(s, k, h, a) for s in range(lo, hi + 1) for k, (h, a) in enumerate(MATCHUPS)]
    with ProcessPoolExecutor(args.workers) as ex:
        rows = [r for rs in ex.map(_duel, jobs) for r in rs]
    probs, counts = {}, {}
    for sit in ("leading", "level", "trailing"):
        c = Counter(SLOT_OF.get(r["opponent_intent"], -1) for r in rows if r["opponent_situation"] == sit)
        n = sum(c[s] for s in (0, 1, 2))
        probs[sit] = [round((c[s] + 1) / (n + 3), 3) for s in (0, 1, 2)]
        counts[sit] = {"stay": c[0], "situational": c[1], "build_up_switch": c[2], "other": c[-1]}
    intents = Counter((r["opponent_situation"], r["opponent_intent"]) for r in rows)
    out = {"seasons": [lo, hi], "duels": len(rows), "probabilities": probs, "slot_counts": counts,
           "intent_counts": {f"{s}:{i}": n for (s, i), n in sorted(intents.items())},
           "dev_prob_on_actual_intent": round(sum(r["prob_on_actual"] for r in rows) / max(len(rows), 1), 3),
           "dev_share_without_dominant_option": round(1 - sum(r["dominant"] for r in rows) / max(len(rows), 1), 3),

           "rows": rows,
           "rule": "Laplace-smoothed frequency of each estimator slot per score situation of the other bench"}
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
