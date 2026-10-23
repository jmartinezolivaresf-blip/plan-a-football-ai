"""Reproducible demo pipeline -> web/public/match_bundle.json.

    python -m pipeline.build                      # offline rules client
    AGENTS_MODE=foundry python -m pipeline.build  # Microsoft Foundry agents
    python -m pipeline.build --search 40          # seed search for the demo story (criteria in STORY_CRITERIA)

The pipeline is the only place that holds the hidden truth: it builds the real world, hands the engine opaque
simulator handles and never gives truth to agents or the MCP server. Every number in the bundle comes from the
simulator, the engine or a claim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from agents.broadcast import Director
from agents.duel import run_duel
from agents.prematch import run_prematch
from contracts import AttackDirection, Duel, FindingRef, MatchBundle, MatchMeta, ScoutingSummary
from engine.api import RealEngine, Seeds
from engine.scouting import MatchLog
from sim import bind, bind_beliefs
from sim.render.layer import frames
from sim.season import Season, build_season, match_squads

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "match_bundle.json"
EVAL_RESULTS = ROOT / "eval" / "results" / "summary.json"
STORY_CRITERIA = (
    "a build-up switch is detected live and matches a real lever change (the change happened before the detection "
    "and the estimated change minute is within 10 minutes of it); first-half goal difference <= 2; "
    "the true matrix has no dominant option for at least one bench; "
    "at least one bench has a regret whose paired 90% interval is above zero; final goal difference <= 2; "
    "total goals between 1 and 6"
)


@dataclass
class Built:
    bundle: MatchBundle
    story: dict


@dataclass
class Prematch:
    """Both staffs' pre-match results plus every claim their engine served: an engine that replays the match from
    these plans needs those claims (valuations, evidence) or the plans would cite claims missing from the bundle."""
    results: dict
    claims: dict


def run_prematch_for(season: Season, home: str, away: str, mode: str | None, seeds: Seeds | None = None) -> Prematch:
    engine = make_engine(season, home, away, seeds or Seeds())
    results = asyncio.run(run_prematch(engine, home, away, mode))
    return Prematch(results=results, claims=dict(engine.claims))


class StoryRejected(Exception):
    """A match seed that does not meet STORY_CRITERIA; `failed` names the criteria it missed."""

    def __init__(self, story: dict, failed: list[str]):
        super().__init__(", ".join(failed))
        self.story, self.failed = story, failed


def make_engine(season: Season, home: str, away: str, seeds: Seeds) -> RealEngine:
    meta = MatchMeta(match_id=f"{season.public.season_id}-demo", home=home, away=away,
                     kickoff_label="Matchday 9 (fictional)",
                     attack=[AttackDirection(period=1, positive_x=home), AttackDirection(period=2, positive_x=away)])
    return RealEngine(matches=[MatchLog(m.match_id, m.home, m.away, m.events) for m in season.public.matches],
                      squads=season.public.squads, meta=meta, public_world=bind(None, season.config),
                      true_world=bind(season.truth, season.config), belief_world=bind_beliefs, seeds=seeds)


def first_half_story(engine: RealEngine) -> dict:
    ht = engine.ht_state.snapshot.score
    adapt = {t: engine.adaptation(t, 45) for t in (engine.home, engine.away)}
    return {"ht_score": ht, "adaptation": {t: (a[1].minute if a else None) for t, a in adapt.items()}}


def build(season_seed: int = 2026, match_seed: int = 202, mode: str | None = None, home: str = "KES",
          away: str = "HAR", season: Season | None = None, prematch: Prematch | None = None,
          require_story: bool = False) -> Built:
    """Build one match bundle. With require_story, raises StoryRejected as soon as a criterion is missed."""
    t0 = time.perf_counter()
    season = season or build_season(season_seed)
    seeds = Seeds(match=match_seed)
    engine = make_engine(season, home, away, seeds)
    if prematch is None:
        prematch = Prematch(results=asyncio.run(run_prematch(engine, home, away, mode)), claims={})
    engine.claims.update(prematch.claims)
    prematch_results = prematch.results
    plans = {t: r.chosen for t, r in prematch_results.items()}
    engine.set_plans(plans)
    engine.play_first_half()
    story = first_half_story(engine)
    if require_story and abs(story["ht_score"][home] - story["ht_score"][away]) > 2:
        raise StoryRejected(story, ["first-half goal difference <= 2"])
    privates, broadcast, duel_traces = asyncio.run(run_duel(engine, home, away, plans, mode))
    engine.play_second_half()
    final = engine.snapshots[-1].score
    adaptations = {t: engine.first_adaptation(t, 90) for t in (home, away)}
    story["adaptation"] = {t: (a[0] if a else None) for t, a in adaptations.items()}
    story["change_point"] = {t: (a[1][1].minute if a else None) for t, a in adaptations.items()}
    story["build_up_changes"] = {t: _lever_changes(engine.snapshots, t, "build_up") for t in (home, away)}
    m = broadcast.true_matrix
    story.update({"final_score": final, "choices": {t: r.option_id for t, r in broadcast.revealed.items()},
                  "dominant": {t: m.readings[t].dominant for t in (home, away)},
                  "regret": {t: r.regret_xpts for t, r in broadcast.regret.items()},
                  "regret_ci90_low": {t: engine.claims[r.claim_id].interval_low for t, r in broadcast.regret.items()}})
    failed = [k for k, ok in _story_checks(story, home, away).items() if not ok]
    if require_story and failed:
        raise StoryRejected(story, failed)
    names = {home: season.public.squads.teams[home].short_name, away: season.public.squads.teams[away].short_name}
    director = Director(names=names, claims=dict(engine.claims))
    director.prematch(plans)
    director.live(engine.snapshots, engine.events, plans,
                  {t: (a[0], *a[1]) if a else None for t, a in adaptations.items()}, 90)
    options = {t: p.options for t, p in privates.items()}
    director.duel(home, away, options, broadcast)
    director.final(home, away, plans, engine.snapshots[-1], broadcast, options)
    squads = match_squads(season.public.squads, home, away)
    render = frames(engine.events, engine.snapshots, squads, home)
    scouting = {t: ScoutingSummary(team=t, opponent=r.opponent, model=r.report.model,
                                   findings=[FindingRef(claim_id=f.claim_id, headline=f.headline)
                                             for f in r.report.findings],
                                   opponent_estimate=r.report.opponent_plan_estimate)
                for t, r in prematch_results.items()}
    claims = dict(engine.claims)
    claims.update({c.claim_id: c for c in director.extra_claims})
    traces = [t for r in prematch_results.values() for t in r.traces] + duel_traces
    eval_summary = _public_eval(json.loads(EVAL_RESULTS.read_text())) if EVAL_RESULTS.exists() else {
        "note": "run `make eval` to fill the validation panel"}
    eval_summary["story"] = story
    eval_summary["build"] = _provenance(season.config.seed, match_seed, prematch_results)
    eval_summary["story_criteria"] = STORY_CRITERIA
    eval_summary["cues_dropped_by_verifier"] = len(director.dropped)
    eval_summary["cues_dropped_detail"] = [{"cue_id": c, "errors": e} for c, e in director.dropped]
    eval_summary["build_seconds"] = round(time.perf_counter() - t0, 1)
    bundle = MatchBundle(meta=engine.meta, squads=squads, events=engine.events, snapshots=engine.snapshots,
                         render_frames=render, plans=plans,
                         duel=Duel(match_id=engine.match_id, minute=45, private=privates, broadcast=broadcast),
                         claims=_referenced(claims, plans, privates, broadcast, director, scouting, engine, traces),
                         scouting=scouting, cues=sorted(director.cues, key=lambda c: _secs(c.t_match)),
                         traces=traces, eval=eval_summary, illustrative=False)
    return Built(bundle=MatchBundle.model_validate(bundle.model_dump(mode="json", by_alias=True)), story=story)


def _provenance(season_seed: int, match_seed: int, prematch_results: dict) -> dict:
    """What produced this bundle: code version, seeds and the model behind each staff."""
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"git_commit": commit, "uncommitted_changes": dirty, "season_seed": season_seed, "match_seed": match_seed,
            "models": {t: r.model for t, r in prematch_results.items()}}


def _public_eval(summary: dict) -> dict:
    """Aggregates only: per-report rows of E1 name the eval season's hidden traits and stay in eval/results/.
    Adds the chosen settings of the dev-season calibrations (eval/calibrate_*.py) when they have been run."""
    out = {k: ({kk: vv for kk, vv in v.items() if kk not in ("reports", "rows")} if isinstance(v, dict) else v)
           for k, v in summary.items()}
    for key, name in (("adaptation_detector", "adaptation_calibration.json"), ("sim_shots", "sim_calibration.json")):
        path = EVAL_RESULTS.parent / name
        if path.exists():
            data = json.loads(path.read_text())
            out[key] = {"chosen": data["chosen"], "rule": data["rule"], "seasons": data["seasons"]}
    return out


def _secs(t: str) -> int:
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def _lever_changes(snapshots, team: str, lever: str) -> list[int]:
    """Minutes at which a team's active lever changed (its own bench's decision, logged by the simulator)."""
    out, prev = [], None
    for s in snapshots:
        value = getattr(s.active_levers[team], lever)
        if prev is not None and value != prev:
            out.append(s.minute)
        prev = value
    return out


def _story_checks(story: dict, home: str, away: str) -> dict[str, bool]:
    """One entry per STORY_CRITERIA clause, so a rejected seed says exactly what it missed."""
    ht, fs = story["ht_score"], story["final_score"]
    def matches_real_change(team: str) -> bool:
        detected, estimate = story["adaptation"][team], story["change_point"][team]
        return detected is not None and any(c <= detected and abs(estimate - c) <= 10
                                            for c in story["build_up_changes"][team])

    return {
        "adaptation detected and real": any(matches_real_change(t) for t in (home, away)),
        "first-half goal difference <= 2": abs(ht[home] - ht[away]) <= 2,
        "no dominant option for >= 1 bench": not all(story["dominant"].values()),
        "regret above noise for >= 1 bench": any(v > 0 for v in story["regret_ci90_low"].values()),
        "final goal difference <= 2": abs(fs[home] - fs[away]) <= 2,
        "total goals 1-6": 1 <= fs[home] + fs[away] <= 6,
    }


def _referenced(claims, plans, privates, broadcast, director, scouting, engine, traces):
    ids: set[str] = set()
    for p in plans.values():
        ids |= {c for cs in p.lever_evidence.values() for c in cs}
        if p.valuation:
            ids.add(p.valuation)
    for priv in privates.values():
        ids |= {c.claim_id for row in priv.believed_matrix.cells for c in row if c.claim_id}
        ids |= set(priv.opponent_estimate.claims)
        ids |= {c for o in priv.options for c in o.evidence}
    ids |= {c.claim_id for row in broadcast.true_matrix.cells for c in row if c.claim_id}
    ids |= {r.claim_id for r in broadcast.regret.values() if r.claim_id}
    for cue in director.cues:
        ids |= set(cue.claims)
        import re
        ids |= {m for m in re.findall(r"\{(c[\w-]+)\.", cue.text.en + cue.text.es)}
    for s in scouting.values():
        ids |= {f.claim_id for f in s.findings}
        if s.opponent_estimate:
            ids |= set(s.opponent_estimate.claims)
    for snap in engine.snapshots:
        ids |= {k.claim_id for k in snap.kpis if k.claim_id}
    for t in traces:
        ids |= set(t.result_claims)
    return [claims[c] for c in sorted(ids) if c in claims]


def write(built: Built, out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(built.bundle.model_dump_json(by_alias=True))
    return out


def _try_seed(job: tuple) -> tuple[int, list[str], dict]:
    season, prematch, season_seed, seed, mode = job
    try:
        b = build(season_seed, seed, mode, season=season, prematch=prematch, require_story=True)
        return seed, [], b.story
    except StoryRejected as r:
        return seed, r.failed, r.story


def search(n: int, season_seed: int, mode: str | None, start: int = 202, workers: int = 1) -> tuple[int, Built]:
    """Try match seeds start..start+n-1 and keep the SMALLEST one meeting STORY_CRITERIA (independent of worker
    scheduling, so the result is reproducible). Every tried seed is printed with the criteria it missed."""
    season = build_season(season_seed)
    prematch = run_prematch_for(season, "KES", "HAR", mode)
    jobs = [(season, prematch, season_seed, start + k, mode) for k in range(n)]
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(_try_seed, jobs))
    else:
        results = [_try_seed(j) for j in jobs]
    for seed, failed, story in results:
        print(f"seed {seed}: {'OK' if not failed else 'missed ' + '; '.join(failed)} | {story}", flush=True)
    ok = [seed for seed, failed, _ in results if not failed]
    if not ok:
        raise SystemExit(f"no seed in {start}..{start + n - 1} satisfies: {STORY_CRITERIA}")
    seed = min(ok)
    print(f"seed {seed} is the smallest of {len(ok)}/{n} seeds meeting the story criteria")
    return seed, build(season_seed, seed, mode, season=season, prematch=prematch, require_story=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.build")
    ap.add_argument("--mode", choices=["offline", "foundry"], default=None)
    ap.add_argument("--season-seed", type=int, default=2026)
    ap.add_argument("--match-seed", type=int, default=202)
    ap.add_argument("--search", type=int, default=0, help="try N match seeds for the story criteria")
    ap.add_argument("--workers", type=int, default=1, help="processes for --search")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    if args.search:
        _, built = search(args.search, args.season_seed, args.mode, args.match_seed, args.workers)
    else:
        built = build(args.season_seed, args.match_seed, args.mode)
    path = write(built, Path(args.out))
    b = built.bundle
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB): {len(b.events)} events, {len(b.cues)} cues, "
          f"{len(b.claims)} claims, {len(b.traces)} trace steps; story {built.story}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
