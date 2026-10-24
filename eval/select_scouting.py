"""Select the evidence threshold (z) that turns each scouting statistic into a belief, on DEV seasons only.

    python -m eval.select_scouting [--seasons 9001-9010] [--workers 8]

Uses the engine's own claims (exactly what an analyst is served: engine/scouting.py tendencies) for every club of
dev seasons with random trait kinds, labels each claim with whether its club / player / side has the matching hidden
trait, and picks per statistic the z on a fixed grid that maximises F1 (ties: the higher z, fewer false alarms).
Recall counts every real trait of that kind, also those no claim surfaced. Also reports report-level precision and
recall of the offline analyst (five findings) with the chosen thresholds. Never reads the evaluation seasons.
Writes eval/results/dev/scouting_thresholds.json; engine/beliefs.py RULES must match it (tested).
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from contracts.claim import evidence_z

OUT = Path(__file__).resolve().parent / "results" / "dev" / "scouting_thresholds.json"
GRID = [round(0.25 * k, 2) for k in range(0, 13)]  # 0.0 .. 3.0
KIND = {"losses_per_100_pressured_receptions": "fb_low_press_resistance",
        "goal_kick_short_vs_open_play": "gk_short_bias", "first_contact_conceded_share": "back_post_weak",
        "forward_success_conceded_share": "weak_channel", "deep_ball_success_conceded_share": "cb_low_pace",
        "late_xg_conceded_ratio": "late_fade"}


def _season(seed: int) -> dict:
    from engine.scouting import MatchLog, Scout
    from sim.season import build_season

    s = build_season(seed, f"dev-{seed}", random_trait_kinds=True)
    positions = {p.player_id: p.position for sq in s.public.squads.teams.values() for p in sq.players}
    scout = Scout([MatchLog(m.match_id, m.home, m.away, m.events) for m in s.public.matches], positions)
    rows, totals, served = [], {k: 0 for k in KIND.values()}, {}
    for team, tt in s.truth.teams.items():
        traits = {t.kind: t for t in tt.traits}
        for k in traits:
            totals[k] += 1
        claims = scout.tendencies(team, "all")
        served[team] = [c.model_dump(mode="json") for c in claims]
        for c in claims:
            kind = KIND.get(c.metric)
            z = evidence_z(c)
            if kind is None or z is None or c.status != "sufficient":
                continue
            if kind == "fb_low_press_resistance":
                if (c.label or "").split(",")[0] not in ("LB", "RB"):
                    continue
                has = kind in traits and traits[kind].player_id == c.player_id
            elif kind == "back_post_weak":
                if not (c.label or "").startswith("back"):
                    continue
                has = kind in traits
            elif kind == "weak_channel":
                has = kind in traits and traits[kind].side == (c.label or "").split()[0]
            else:
                has = kind in traits
            rows.append({"metric": c.metric, "z": z, "has": has})
    truth = {team: [{"kind": t.kind, "player_id": t.player_id, "side": t.side} for t in tt.traits]
             for team, tt in s.truth.teams.items()}
    return {"rows": rows, "totals": totals, "served": served, "truth": truth}


def _f1(rows, total, z):
    flagged = [r for r in rows if r["z"] >= z]
    tp = sum(r["has"] for r in flagged)
    p = tp / len(flagged) if flagged else 0.0
    r = tp / total if total else 0.0
    return (2 * p * r / (p + r) if p + r else 0.0), p, r, len(flagged)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.select_scouting")
    ap.add_argument("--seasons", default="9001-9010")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seasons.split("-"))
    with ProcessPoolExecutor(args.workers) as ex:
        seasons = list(ex.map(_season, range(lo, hi + 1)))
    rows = [r for s in seasons for r in s["rows"]]
    rules, detail = {}, {}
    for metric, kind in KIND.items():
        sel = [r for r in rows if r["metric"] == metric]
        total = sum(s["totals"][kind] for s in seasons)
        scored = [(_f1(sel, total, z), z) for z in GRID]
        (f1, p, r, n), z = max(scored, key=lambda t: (round(t[0][0], 6), t[1]))
        rules[metric] = [kind, z]
        detail[metric] = {"kind": kind, "z": z, "f1": round(f1, 3), "precision": round(p, 3), "recall": round(r, 3),
                          "flagged": n, "real_traits": total}
    # report level: the offline analyst's five findings with these thresholds
    import engine.beliefs as eb
    from agents import offline
    from contracts import Claim
    from eval.run import match_key
    eb.RULES.update({m: (k, z) for m, (k, z) in rules.items()})
    flagged = correct = real = 0
    for s in seasons:
        for team, claims in s["served"].items():
            report = offline.scouting({"claims": claims})
            by_id = {c["claim_id"]: c for c in claims}
            found = {match_key(b) for b in eb.beliefs_from_claims(
                [Claim.model_validate(by_id[f.claim_id]) for f in report.findings])}
            truth = {match_key({"team": team, **t}) for t in s["truth"][team]}
            flagged, correct, real = flagged + len(found), correct + len(found & truth), real + len(truth)
    out = {"seasons": [lo, hi], "grid": GRID, "rules": rules, "per_statistic": detail,
           "report_level": {"precision": round(correct / max(flagged, 1), 3),
                            "recall": round(correct / max(real, 1), 3), "flagged": flagged, "real_traits": real},
           "rule": "per statistic, the grid z with the best claim-level F1 on dev (ties: higher z)"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    for m, d in detail.items():
        print(f"{m:40s} {d}")
    print("report level (dev):", out["report_level"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
