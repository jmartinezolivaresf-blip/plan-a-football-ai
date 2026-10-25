"""Evaluation E1-E8 + calibration (v6 §11). Writes eval/results/summary.json and eval/results/*.md.

    python -m eval.run [--season-seed 8101] [--matches 6]   # TEST: run once, for the final numbers
    python -m eval.run --dev                                # DEV check (seasons 9011-9015, 9101) -> results/dev/

What each number means (and does not mean) is written next to it in the output. Everything is measured INSIDE our
simulator; nothing here is a claim about real football.

Independence: E1 runs on seasons 8001-8005 and E2/E3/E4/E7/E8 plus the season statistics on season 8101; all of
them draw each club's trait kinds at random and none was inspected or used for tuning (D-043). The scouting
thresholds were developed on season 2026 (disclosed in docs/DECISIONS.md, D-036); simulator knobs were calibrated on
dev seasons 11-14 only (eval/calibrate_*.py).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import numpy as np

from agents.prematch import run_prematch
from engine.api import Seeds
from engine.beliefs import beliefs_from_claims
from engine.eventsx import is_high_turnover
from engine.valuation import paired_ci, points
from pipeline.build import build, make_engine, run_prematch_for
from sim.season import build_season

OUT = Path(__file__).parent / "results"
MATCHUPS = [("KES", "HAR"), ("MOR", "ASH"), ("WEX", "HAR"), ("BRY", "ASH"), ("ASH", "KES"), ("HAR", "MOR")]
TARGETS = {  # Anexo A of PLAN_A_v6 (to be re-checked against the cited sources before publishing)
    "goals_per_match": (2.7, 3.0), "shots_per_match": (24, 27), "shot_conversion": (0.10, 0.12),
    "passes_per_match": (850, 900), "pass_accuracy": (0.80, 0.85), "corners_per_match": (9, 11),
    "high_turnovers_per_team": (5, 14), "home_win_share": (0.35, 0.47), "draw_share": (0.20, 0.30),
}


E1_SEASONS = (8001, 8002, 8003, 8004, 8005)
DEV_E1_SEASONS = (9011, 9012, 9013, 9014, 9015)  # dev seasons not used to select thresholds (those are 9001-9010)
DEV_MATCH_SEASON = 9101
E1_MATCHUPS = (("KES", "HAR"), ("MOR", "ASH"), ("WEX", "BRY"))  # each pre-match scouts both clubs: 6 per season


def match_key(t: dict) -> tuple:
    """Traits are scored at the level scouting can see them: a player for press resistance, a side for a weak
    channel, the team for the rest (a slow centre-back shows as balls in behind conceded by the team)."""
    if t["kind"] == "fb_low_press_resistance":
        return t["team"], t["kind"], t.get("player_id")
    if t["kind"] == "weak_channel":
        return t["team"], t["kind"], t.get("side")
    return t["team"], t["kind"]


def _e1_season(job: tuple[int, str | None]) -> list[dict]:
    """Scouting reports of every club in one unseen season with randomly drawn trait kinds."""
    seed, mode = job
    season = build_season(seed, season_id=f"s-e1-{seed}", random_trait_kinds=True)
    rows = []
    for home, away in E1_MATCHUPS:
        engine = make_engine(season, home, away, Seeds())
        pre = asyncio.run(run_prematch(engine, home, away, mode))
        for r in pre.values():
            found = beliefs_from_claims([engine.claims[f.claim_id] for f in r.report.findings
                                         if f.claim_id in engine.claims])
            real = [{"team": r.opponent, "kind": tr.kind, "player_id": tr.player_id, "side": tr.side}
                    for tr in season.truth.teams[r.opponent].traits]
            rows.append({"season": seed, "scouted": r.opponent, "by": r.report.team,
                         "flagged": sorted({match_key(b) for b in found}),
                         "truth": sorted({match_key(t) for t in real})})
    return rows


def e1(mode: str | None, workers: int, seasons: tuple[int, ...] = E1_SEASONS) -> dict:
    """Scouting vs hidden truth on seasons whose trait kinds were drawn at random and never inspected (D-043)."""
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(workers) as ex:
        rows = [r for rs in ex.map(_e1_season, [(s, mode) for s in seasons]) for r in rs]
    flagged = correct = total = 0
    per_kind: dict[str, dict[str, int]] = {}
    for r in rows:
        f, t = set(map(tuple, r["flagged"])), set(map(tuple, r["truth"]))
        flagged, correct, total = flagged + len(f), correct + len(f & t), total + len(t)
        for key in f | t:
            k = per_kind.setdefault(key[1], {"flagged": 0, "correct": 0, "true": 0})
            k["flagged"] += key in f
            k["correct"] += key in f and key in t
            k["true"] += key in t
    for k in per_kind.values():
        k["precision"] = round(k["correct"] / k["flagged"], 3) if k["flagged"] else None
        k["recall"] = round(k["correct"] / k["true"], 3) if k["true"] else None
    return {"precision": round(correct / flagged, 3) if flagged else None,
            "recall": round(correct / total, 3) if total else None, "flagged": flagged, "true_traits": total,
            "scouted_teams": len(rows), "seasons": seasons, "per_kind": per_kind, "reports": rows,
            "meaning": "share of flagged weaknesses that are real hidden traits / share of hidden traits flagged, "
                       "on unseen seasons with random trait kinds"}


def e2(engine, R_small: int = 300, R_big: int = 3000) -> dict:
    """Monte Carlo stability: deltas vs Stay/Stay with R=300 against a R=3000 reference (same world, same state)."""
    from contracts import LeverChanges, Option
    st = engine.ht_state
    rows = []
    for team in (engine.home, engine.away):
        opp = engine.opponent(team)
        for k, changes in enumerate([LeverChanges(press_height="low"), LeverChanges(build_up="direct"),
                                     LeverChanges(press_height="high")]):
            opt = Option(option_id=f"E2-{team}-{k}", team=team, label={"en": "x", "es": "x"}, intent="drop_block",
                         lever_changes=changes)
            res = {}
            for R in (R_small, R_big):
                base = engine.public_world.fork(st, {}, R=R, seed=900 + k)
                alt = engine.public_world.fork(st, {team: opt}, R=R, seed=900 + k)
                d = points(alt.goals[team], alt.goals[opp]) - points(base.goals[team], base.goals[opp])
                res[R] = (float(d.mean()), *paired_ci(d, seed=k))
            rows.append({"team": team, "change": changes.model_dump(exclude_none=True), "small": res[R_small],
                         "reference": res[R_big]})
    sign = np.mean([np.sign(r["small"][0]) == np.sign(r["reference"][0]) for r in rows])
    mae = np.mean([abs(r["small"][0] - r["reference"][0]) for r in rows])
    cover = np.mean([r["small"][1] <= r["reference"][0] <= r["small"][2] for r in rows])
    clear = [r for r in rows if r["reference"][1] > 0 or r["reference"][2] < 0]  # reference CI excludes zero
    sign_clear = np.mean([np.sign(r["small"][0]) == np.sign(r["reference"][0]) for r in clear]) if clear else None
    return {"sign_agreement": round(float(sign), 3), "mean_abs_error_xpts": round(float(mae), 3),
            "sign_agreement_when_reference_is_clear": None if sign_clear is None else round(float(sign_clear), 3),
            "clear_cells": len(clear),
            "ci90_coverage_of_reference": round(float(cover), 3), "cells": len(rows), "R": [R_small, R_big],
            "rows": rows, "meaning": "noise of the Monte Carlo estimate only, not validity of the model"}


def attacks(levers, trait) -> bool:
    """Does a set of levers target this hidden trait (the mechanism the simulator implements for it)?"""
    if trait.kind == "fb_low_press_resistance":
        return levers.press_target == trait.player_id
    if trait.kind == "back_post_weak":
        return levers.corner_delivery == "far_post"
    if trait.kind == "weak_channel":
        return bool(trait.side) and levers.attack_channel == {"left": "right", "right": "left"}[trait.side]
    if trait.kind == "cb_low_pace":
        return levers.build_up == "direct"
    if trait.kind == "gk_short_bias":
        return levers.press_height == "high"
    return False  # late_fade has no lever; it pays off through the duel


def _random_hit_rate(opponent_traits, opponent_players: list[str]) -> float:
    """Share of ALL lever combinations that attack at least one real trait: what a blind plan would score."""
    from itertools import product

    from contracts import Levers
    combos = list(product(("high", "mid", "low"), [None, *opponent_players], ("short", "mixed", "direct"),
                          ("left", "center", "right", "balanced"), ("near_post", "far_post", "short")))
    hits = sum(any(attacks(Levers(press_height=a, press_target=b, build_up=c, attack_channel=d, corner_delivery=e), t)
                   for t in opponent_traits) for a, b, c, d, e in combos)
    return hits / len(combos)


def e3(plans_with_truth: list, squads) -> dict:
    """Plans justified by claims, and plans that attack at least one REAL hidden weakness, against a blind baseline."""
    from agents.validators.plan import non_default_levers
    changed = cited = attacking = 0
    baseline = []
    for plan, served, truth in plans_with_truth:
        for lever in non_default_levers(plan):
            changed += 1
            if plan.lever_evidence.get(lever) and set(plan.lever_evidence[lever]) <= served:
                cited += 1
        real = truth.teams[plan.opponent].traits
        attacking += any(attacks(plan.levers, tr) for tr in real)
        starters = [p.player_id for p in squads.teams[plan.opponent].players if p.starter]
        baseline.append(_random_hit_rate(real, starters))
    n = len(plans_with_truth)
    return {"levers_citing_served_claims": round(cited / changed, 3) if changed else None, "changed_levers": changed,
            "plans_attacking_a_real_weakness": round(attacking / n, 3) if n else None, "plans": n,
            "random_plan_baseline": round(float(np.mean(baseline)), 3) if baseline else None,
            "meaning": "a plan counts if one lever targets a real hidden trait; the baseline is the share of all "
                       "lever combinations that would also count"}


def e4(reports: list, dropped: list[dict]) -> dict:
    first = sum(1 for rep in reports if rep.attempts == 1 and not rep.fallback)
    return {"reports_valid_first_try": round(first / len(reports), 3) if reports else None,
            "reports_fallback": sum(rep.fallback for rep in reports), "cues_dropped": len(dropped),
            "cues_dropped_detail": dropped, "llm_numbers": 0,
            "meaning": "digits outside {claim.field} placeholders are rejected by code (0 by construction)"}


def e7_e8(duels: list) -> dict:
    """E7: probability the analyst gave to the opponent's actual intent. E8: regret of the AI vs baselines."""
    probs, ai, stay, rnd = [], [], [], []
    for duel in duels:
        b = duel.broadcast
        m = b.true_matrix
        for team, priv in duel.private.items():
            opp = next(t for t in duel.private if t != team)
            real_intent = next(o.intent for o in duel.private[opp].options if o.option_id == b.revealed[opp].option_id)
            probs.append(sum(e.probability for e in priv.opponent_estimate.options if e.option.intent == real_intent))
            from engine import duel as dm
            own, oppo, P = dm.payoffs(m, team)
            j = oppo.index(b.revealed[opp].option_id)
            best = max(P[i][j] for i in range(len(own)))
            ai.append(best - P[own.index(b.revealed[team].option_id)][j])
            stay.append(best - P[0][j])
            rnd.append(best - float(np.mean([P[i][j] for i in range(len(own))])))
    def ci(x):
        x = np.asarray(x)
        lo, hi = paired_ci(x, seed=7) if len(x) > 1 else (float(x.mean()), float(x.mean()))
        return {"mean": round(float(x.mean()), 3), "ci90": [round(lo, 3), round(hi, 3)], "n": len(x)}
    dominated = [m.readings[t].dominant is not None for d in duels for m in [d.broadcast.true_matrix]
                 for t in d.private]
    return {"duel_interaction": {"benches": len(dominated),
                                 "share_without_dominant_option": round(1 - sum(dominated) / len(dominated), 3)
                                 if dominated else None,
                                 "meaning": "how often a bench's best half-time answer depends on what the other "
                                            "bench does (true matrix); plan target: at least half"},
            "E7": {"prob_on_actual_intent": ci(probs), "uniform_baseline": round(1 / 3, 3),
                   "meaning": "how much the analyst anticipated the other bench (higher is better)"},
            "E8": {"ai_regret": ci(ai), "always_stay_regret": ci(stay), "random_choice_regret": ci(rnd),
                   "meaning": "xPts lost vs the best response to what the other bench really did, in our simulator"}}


def calibration(season) -> dict:
    ms = season.public.matches
    goals = shots = passes = passes_ok = corners = ht = 0
    home_w = draws = 0
    for m in ms:
        g = {m.home: 0, m.away: 0}
        for e in m.events:
            if e.type == "goal":
                g[e.team] += 1
            elif e.type == "shot":
                shots += 1
            elif e.type in ("pass", "long_ball", "cross"):
                passes += 1
                passes_ok += e.outcome == "success"
            elif e.type == "corner":
                corners += 1
            ht += is_high_turnover(e, m.home)
        goals += sum(g.values())
        home_w += g[m.home] > g[m.away]
        draws += g[m.home] == g[m.away]
    n = len(ms)
    vals = {"goals_per_match": goals / n, "shots_per_match": shots / n, "shot_conversion": goals / max(shots, 1),
            "passes_per_match": passes / n, "pass_accuracy": passes_ok / max(passes, 1),
            "corners_per_match": corners / n,
            "high_turnovers_per_team": ht / (2 * n), "home_win_share": home_w / n, "draw_share": draws / n}
    out = {k: {"value": round(v, 3), "target": TARGETS[k], "in_range": TARGETS[k][0] <= v <= TARGETS[k][1]}
           for k, v in vals.items()}
    for k in ("home_win_share", "draw_share"):  # shares of n matches: say how much a 24-match season can tell
        lo, hi = _wilson(vals[k], n)
        out[k]["ci90"] = [round(lo, 3), round(hi, 3)]
        out[k]["target_inside_ci90"] = lo <= TARGETS[k][1] and hi >= TARGETS[k][0]
    return out


def _wilson(p: float, n: int, z: float = 1.645) -> tuple[float, float]:
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return centre - half, centre + half


def _eval_match(job: tuple) -> dict:
    """One full pipeline match of the evaluation season (pre-match, first half, duel, second half)."""
    season_seed, k, home, away, mode = job
    season = build_season(season_seed, season_id=f"s-eval-{season_seed}", random_trait_kinds=True)
    pre = run_prematch_for(season, home, away, mode, Seeds(match=500 + k))
    built = build(season=season, prematch=pre, home=home, away=away, match_seed=500 + k, mode=mode)
    return {"reports": [r.report for r in pre.results.values()],
            "plans": [(r.chosen, {c for t in r.traces for c in t.result_claims}) for r in pre.results.values()],
            "duel": built.bundle.duel, "plans_sealed": built.bundle.plans,
            "dropped": [{"match": f"{home}-{away}", **d} for d in built.bundle.eval.get("cues_dropped_detail", [])]}


def main(argv: list[str] | None = None) -> int:
    from concurrent.futures import ProcessPoolExecutor

    from agents.settings import load_env
    load_env()
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("--season-seed", type=int, default=8101)
    ap.add_argument("--dev", action="store_true", help="dev seasons only; writes eval/results/dev/summary.json")
    ap.add_argument("--matches", type=int, default=len(MATCHUPS))
    ap.add_argument("--mode", choices=["offline", "foundry"], default=None)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    if args.dev:
        args.season_seed = DEV_MATCH_SEASON
    out_dir = OUT / "dev" if args.dev else OUT
    t0 = time.perf_counter()
    season = build_season(args.season_seed, season_id=f"s-eval-{args.season_seed}", random_trait_kinds=True)
    jobs = [(args.season_seed, k, h, a, args.mode) for k, (h, a) in enumerate(MATCHUPS[: args.matches])]
    with ProcessPoolExecutor(args.workers) as ex:
        matches = list(ex.map(_eval_match, jobs))
    print(f"  {len(matches)} matches done ({time.perf_counter() - t0:.0f}s)")
    reports = [r for m in matches for r in m["reports"]]
    plans_truth = [(p, served, season.truth) for m in matches for p, served in m["plans"]]
    home, away = MATCHUPS[0]
    e2_engine = make_engine(season, home, away, Seeds(match=500))
    e2_engine.set_plans(matches[0]["plans_sealed"])
    e2_engine.play_first_half()
    summary = {"season_seed": args.season_seed, "matches": args.matches, "dev": args.dev,
               "E1": e1(args.mode, args.workers, DEV_E1_SEASONS if args.dev else E1_SEASONS),
               "E2": e2(e2_engine), "E3": e3(plans_truth, season.public.squads),
               "E4": e4(reports, [d for m in matches for d in m["dropped"]]),
               **e7_e8([m["duel"] for m in matches]), "calibration": calibration(season),
               "seconds": round(time.perf_counter() - t0, 1),
               "scope": "all results are inside our simulator; synthetic data; not claims about real football"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("calibration",)}, indent=1)[:3000])
    print("calibration:", {k: (v["value"], v["in_range"]) for k, v in summary["calibration"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
