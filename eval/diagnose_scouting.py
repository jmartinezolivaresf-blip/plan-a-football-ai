"""Which scouting statistics carry information about each hidden trait? DEV seasons only (9001-9010 by default).

    python -m eval.diagnose_scouting [--seasons 9001-9010] [--workers 8]

For every trait kind and candidate statistic it reports the AUC (probability that a club/player WITH the trait
scores higher than one without; 0.5 = no information) over all clubs of the dev seasons, which all draw their
trait kinds at random. It is used to choose statistics and thresholds; it never reads the evaluation seasons.
Writes eval/results/dev/scouting_signals.json.
"""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from engine.eventsx import lane_rel, rel_x

OUT = Path(__file__).resolve().parent / "results" / "dev" / "scouting_signals.json"
FINAL_THIRD = 70.0


def _binom_z(k: float, n: float, p: float) -> float:
    if n <= 0 or p <= 0 or p >= 1:
        return 0.0
    return (k - n * p) / math.sqrt(n * p * (1 - p))


def season_rows(seed: int) -> list[dict]:
    """One row per (club or player, statistic) with the label 'has the trait'."""
    from engine.scouting import MatchLog, Scout
    from sim.season import build_season

    s = build_season(seed, f"dev-{seed}", random_trait_kinds=True)
    positions = {p.player_id: p.position for sq in s.public.squads.teams.values() for p in sq.players}
    matches = [MatchLog(m.match_id, m.home, m.away, m.events) for m in s.public.matches]
    scout = Scout(matches, positions)
    truth = s.truth.teams
    teams = list(s.public.squads.teams)

    # exposure-controlled counts against each defending team
    fwd = {t: [[0, 0], [0, 0], [0, 0]] for t in teams}   # forward actions by defender lane: [success, attempts]
    deep = {t: [0, 0] for t in teams}                     # long/forward balls ending in the final third: [succ, att]
    late = {t: [0, 0, 0, 0] for t in teams}               # shots conceded late/early, goals conceded late/early
    for m in s.public.matches:
        for e in m.events:
            opp = m.away if e.team == m.home else m.home
            if e.type in ("pass", "long_ball", "carry", "cross") and e.end_x is not None:
                x0, x1 = rel_x(e, e.team, m.home), rel_x(e, e.team, m.home, e.end_x)
                ok = e.outcome == "success"
                if x1 - x0 >= 10 or e.type in ("carry", "cross"):
                    lane = 2 - lane_rel(e, e.team, m.home, e.end_y)  # attacker's left = defender's right
                    fwd[opp][lane][0] += ok
                    fwd[opp][lane][1] += 1
                if e.type in ("long_ball", "pass") and x1 >= FINAL_THIRD > x0 and x1 - x0 >= 20:
                    deep[opp][0] += ok
                    deep[opp][1] += 1
            if e.type == "shot":
                late[opp][0 if e.minute >= 75 else 1] += 1
                if e.outcome == "goal":
                    late[opp][2 if e.minute >= 75 else 3] += 1
    lg_lane = [sum(fwd[t][k][0] for t in teams) / max(sum(fwd[t][k][1] for t in teams), 1) for k in range(3)]
    lg_deep = sum(deep[t][0] for t in teams) / max(sum(deep[t][1] for t in teams), 1)
    lg_late = sum(late[t][0] for t in teams) / max(sum(late[t][0] + late[t][1] for t in teams), 1)

    # own-half open-play long share (style) to adjust goal-kick length
    style = {t: [0, 0] for t in teams}
    for m in s.public.matches:
        for e in m.events:
            if e.type in ("pass", "long_ball", "carry") and rel_x(e, e.team, m.home) < 52.5:
                style[e.team][0] += e.type == "long_ball"
                style[e.team][1] += 1

    rows = []

    def add(kind, stat, unit, has, value):
        rows.append({"season": seed, "kind": kind, "stat": stat, "unit": unit, "has": bool(has),
                     "value": float(value)})

    for t in teams:
        kinds = {tr.kind: tr for tr in truth[t].traits}
        # gk_short_bias
        short, n, _ = scout.gk[t]
        add("gk_short_bias", "gk_short_ratio", t, "gk_short_bias" in kinds, (short / max(n, 1)) / scout.ref_gk_short)
        add("gk_short_bias", "gk_short_z", t, "gk_short_bias" in kinds, _binom_z(short, n, scout.ref_gk_short))
        long_share = style[t][0] / max(style[t][1], 1)
        add("gk_short_bias", "gk_short_minus_openplay_short", t, "gk_short_bias" in kinds,
            short / max(n, 1) - (1 - long_share))
        # back_post_weak
        won, k = scout.corners_conc[t]["far_post"]
        add("back_post_weak", "far_post_ratio", t, "back_post_weak" in kinds, (won / max(k, 1)) / max(scout.ref_far,
                                                                                                    1e-9))
        add("back_post_weak", "far_post_z", t, "back_post_weak" in kinds, _binom_z(won, k, scout.ref_far))
        # cb_low_pace
        count, ms = scout.bib_conc[t]
        add("cb_low_pace", "bib_per_match_ratio", t, "cb_low_pace" in kinds, (count / max(len(ms), 1)) / scout.ref_bib)
        add("cb_low_pace", "deep_ball_success_z", t, "cb_low_pace" in kinds, _binom_z(deep[t][0], deep[t][1], lg_deep))
        # weak_channel (side-level rows)
        side_of = {0: "left", 2: "right"}
        weak_side = kinds["weak_channel"].side if "weak_channel" in kinds else None
        lanes, _ = scout.entries_conc[t]
        for k_lane in (0, 2):
            has = weak_side == side_of[k_lane]
            add("weak_channel", "entries_share_ratio", f"{t}:{side_of[k_lane]}", has,
                (lanes[k_lane] / max(sum(lanes), 1)) / max(scout.ref_lane[k_lane], 1e-9))
            sk, nk = fwd[t][k_lane]
            add("weak_channel", "forward_success_z", f"{t}:{side_of[k_lane]}", has, _binom_z(sk, nk, lg_lane[k_lane]))
        # late_fade
        add("late_fade", "late_xg_ratio", t, "late_fade" in kinds, scout._late_ratio(t) / max(scout.ref_late, 1e-9))
        add("late_fade", "late_shot_share_z", t, "late_fade" in kinds,
            _binom_z(late[t][0], late[t][0] + late[t][1], lg_late))
        # fb_low_press_resistance (player-level rows, all outfield players)
        trait_player = kinds["fb_low_press_resistance"].player_id if "fb_low_press_resistance" in kinds else None
        for pid, (loss, npress, _) in scout.press.items():
            if not pid.startswith(f"{t}-") or positions.get(pid) == "GK" or npress < 15:
                continue
            ref = (scout._expected_rate(pid) or 1.0) / 100.0
            unit = f"{pid}:{positions[pid]}"
            add("fb_low_press_resistance", "press_ratio", unit, pid == trait_player, (loss / npress) / ref)
            add("fb_low_press_resistance", "press_z", unit, pid == trait_player, _binom_z(loss, npress, ref))
            if positions[pid] in ("LB", "RB"):
                add("fb_low_press_resistance", "press_z_fullbacks", unit, pid == trait_player,
                    _binom_z(loss, npress, ref))
    return rows


def auc(rows: list[dict]) -> float | None:
    pos = [r["value"] for r in rows if r["has"]]
    neg = [r["value"] for r in rows if not r["has"]]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def sweep(rows: list[dict]) -> dict:
    """Best F1 threshold on dev (a statistic flags when value >= threshold)."""
    best = None
    for thr in sorted({round(r["value"], 2) for r in rows}):
        flagged = [r for r in rows if r["value"] >= thr]
        tp = sum(r["has"] for r in flagged)
        p = tp / len(flagged) if flagged else 0.0
        rcl = tp / max(sum(r["has"] for r in rows), 1)
        f1 = 2 * p * rcl / (p + rcl) if p + rcl else 0.0
        if best is None or f1 > best["f1"]:
            best = {"threshold": thr, "precision": round(p, 3), "recall": round(rcl, 3), "f1": round(f1, 3)}
    return best or {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.diagnose_scouting")
    ap.add_argument("--seasons", default="9001-9010")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    lo, hi = (int(x) for x in args.seasons.split("-"))
    with ProcessPoolExecutor(args.workers) as ex:
        rows = [r for rs in ex.map(season_rows, range(lo, hi + 1)) for r in rs]
    out = {"seasons": [lo, hi], "signals": {}}
    for kind in sorted({r["kind"] for r in rows}):
        for stat in sorted({r["stat"] for r in rows if r["kind"] == kind}):
            sel = [r for r in rows if r["kind"] == kind and r["stat"] == stat]
            out["signals"][f"{kind}/{stat}"] = {"n": len(sel), "with_trait": sum(r["has"] for r in sel),
                                                "auc": None if auc(sel) is None else round(auc(sel), 3),
                                                "best_f1": sweep(sel)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    for k, v in out["signals"].items():
        print(f"{k:58s} n={v['n']:4d} pos={v['with_trait']:3d} auc={v['auc']}  best={v['best_f1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
