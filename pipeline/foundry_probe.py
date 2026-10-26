"""Independent check of the agents on a real LLM (Microsoft Foundry), on the frozen demo match, which it never changes.

    AGENTS_MODE=foundry python -m pipeline.foundry_probe     # .env as in docs/FOUNDRY.md; about ten model turns
    python -m pipeline.foundry_probe --mode offline          # the same run with the rules client: NOT evidence

1. Pre-match: both staffs scout and plan with the model through their own scoped MCP tools, on the demo's season and
   match (season and seed read from the committed bundle). Their plans are compared with the demo's sealed plans and
   are not played.
2. Half-time: the demo's first half is replayed with the demo's sealed plans (checked identical: plans, score, levers
   in force, every first-half event) and both benches decide with the model from that exact state. Their options go
   through the same validators, the believed matrices and the true matrix are priced and regret is computed. The
   second half is not played.

Every model turn records what the service itself returned (response id, the model it ran, tokens). Writes
eval/results/foundry/probe_seed<seed>.json and docs/FOUNDRY_EVIDENCE.md in foundry mode (agents/_out/foundry_probe/
in offline mode). The demo bundle's hash is checked before and after: the demo, the video and every published number
stay as they are.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp import Client

from agents.clients import FoundryConfigError, ModelChoice, model_choice
from agents.duel import run_duel
from agents.prematch import Staff
from contracts import MatchBundle
from contracts.option import tactics
from contracts.sealing import verify_plan
from engine.api import Seeds
from sim.season import Season, build_season

from .build import make_engine, run_prematch_for

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "web" / "public" / "match_bundle.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _host(endpoint: str | None) -> str | None:
    """The service domain only (the resource name is left out of the record)."""
    host = urlparse(endpoint).hostname if endpoint else None
    return f"*.{host.split('.', 1)[1]}" if host and "." in host else host


async def _staff(engine, team: str, home: str, away: str, choice: ModelChoice):
    staff = Staff(engine, team, home, away, choice)
    try:
        async with Client(staff.server) as client:
            report = await staff.scout(client)
            candidates, chosen, reason, used_template = await staff.plan(client, report)
    finally:
        await staff.chat.aclose()
    return staff, report, candidates, chosen, reason, used_template


def prematch_part(season: Season, demo: MatchBundle, choice: ModelChoice) -> dict[str, Any]:
    home, away, seed = demo.meta.home, demo.meta.away, demo.eval["build"]["match_seed"]
    engine = make_engine(season, home, away, Seeds(match=seed))
    out: dict[str, Any] = {}
    for team in (home, away):
        staff, report, candidates, chosen, reason, used_template = asyncio.run(
            _staff(engine, team, home, away, choice))
        demo_plan = demo.plans[team]
        out[team] = {
            "report": {"model": report.model, "attempts": report.attempts, "fallback": report.fallback,
                       "findings": [f.claim_id for f in report.findings]},
            "candidates": [{"plan_id": c.plan.plan_id, "valid": c.valid, "validation": c.validation}
                           for c in candidates],
            "chosen": {"name": chosen.name.en, "levers": chosen.levers.model_dump(),
                       "kpis": [f"{k.metric} {k.target} by {k.by_minute}'" for k in chosen.kpis],
                       "plan_b_rules": len(chosen.plan_b), "seal_verifies": verify_plan(chosen), "reason": reason,
                       "used_template": used_template},
            "demo_plan": {"name": demo_plan.name.en, "levers": demo_plan.levers.model_dump()},
            "same_levers_as_demo": chosen.levers == demo_plan.levers,
            "tool_calls": sum(1 for t in staff.trace if t.tool),
            "rejected_steps": [t.message for t in staff.trace if t.status != "ok"],
            "llm_calls": staff.llm_calls,
        }
    return out


def halftime_part(season: Season, demo: MatchBundle, choice: ModelChoice) -> dict[str, Any]:
    home, away, seed = demo.meta.home, demo.meta.away, demo.eval["build"]["match_seed"]
    # the demo's own pre-match, ALWAYS with the rules client (never AGENTS_MODE): the same sealed plans and claims
    pre = run_prematch_for(season, home, away, "offline")
    plans = {t: r.chosen for t, r in pre.results.items()}
    engine = make_engine(season, home, away, Seeds(match=seed))
    engine.claims.update(pre.claims)
    engine.set_plans(plans)
    engine.play_first_half()
    ht = engine.snapshots[45]
    checks = {
        "plans": all(plans[t].sealed.sha256 == demo.plans[t].sealed.sha256 for t in plans),
        "score": ht.score == demo.snapshots[45].score,
        "levers_in_force": ht.active_levers == demo.snapshots[45].active_levers,
        "first_half_events": [e.model_dump() for e in engine.events]
        == [e.model_dump() for e in demo.events if e.period == 1],
    }
    if not all(checks.values()):
        raise RuntimeError(f"the replayed first half is not the demo's: {checks}")
    benches: dict = {}
    privates, broadcast, _ = asyncio.run(run_duel(engine, home, away, plans, choice.mode, benches_out=benches))
    labels = {o.option_id: o.label.en for p in privates.values() for o in p.options}
    demo_labels = {o.option_id: o.label.en for p in demo.duel.private.values() for o in p.options}
    out: dict[str, Any] = {"same_half_time_as_demo": checks, "ht_score": ht.score, "benches": {}}
    for team, p in privates.items():
        bench, now = benches[team], engine.ht_state.levers[team].model_dump()
        keys = [tactics(now, o.lever_changes, o.subs) for o in p.options]
        regret = broadcast.regret[team]
        claim = engine.claims[regret.claim_id]
        out["benches"][team] = {
            "levers_in_force": now,
            "options": [{"option_id": o.option_id, "label": o.label.en, "intent": o.intent,
                         "lever_changes": o.lever_changes.model_dump(exclude_none=True),
                         "subs": [[s.out, s.into] for s in o.subs], "evidence": o.evidence} for o in p.options],
            "options_distinct": len(set(keys)) == len(keys),
            "fallback_to_offline_options": bench.fallback,
            "validation": bench.validation,
            "estimate_of_other_bench": [[e.option.label.en, round(e.probability, 3)]
                                        for e in p.opponent_estimate.options],
            "believed_reading": {k: (labels.get(v, v) if isinstance(v, str) else v)
                                 for k, v in p.believed_matrix.readings[team].model_dump().items()
                                 if k in ("safe_pick", "best_guess", "gamble", "dominant")},
            "rule": broadcast.revealed[team].rule,
            "choice": labels[broadcast.revealed[team].option_id],
            "demo_choice": demo_labels[demo.duel.broadcast.revealed[team].option_id],
            "regret_xpts": regret.regret_xpts, "regret_ci90": [claim.interval_low, claim.interval_high],
            "best_response": labels[regret.best_response],
            "llm_calls": bench.staff.llm_calls,
        }
    m = broadcast.true_matrix
    out["true_matrix"] = {"rows": [labels[r] for r in m.rows], "cols": [labels[c] for c in m.cols],
                          "dominant": {t: labels.get(m.readings[t].dominant) for t in m.readings}}
    return out


def _calls(result: dict[str, Any]) -> list[dict[str, Any]]:
    staffs = list(result.get("prematch", {}).values()) + list(result.get("halftime", {}).get("benches", {}).values())
    return [c for s in staffs for c in s["llm_calls"]]


def render(r: dict[str, Any]) -> str:
    s = r["summary"]
    real = r["mode"] == "foundry"
    lines = ["# Foundry evidence (generated by `python -m pipeline.foundry_probe`; do not edit)", ""]
    if not real:
        lines += ["> **Offline rules client: this run is NOT evidence of a real LLM.** It only checks the probe.", ""]
    lines += [
        f"- **Run:** {r['started_utc']} ({r['seconds']} s), mode `{r['mode']}`, deployments analyst "
        f"`{r['deployments']['analyst']}` and manager `{r['deployments']['manager']}`, endpoint "
        f"`{r['endpoint_host'] or '-'}`.",
        f"- **Service:** {s['model_turns']} model turns, {s['turns_with_service_response_id']} answered with a "
        f"service response id; models reported by the service: {', '.join(s['service_models']) or 'none'}; tokens "
        f"in/out {s['input_tokens']} / {s['output_tokens']}.",
        *([f"- **FAILED:** {r['errors']}"] if r.get("errors") else []),
        f"- **Demo untouched:** bundle sha256 `{r['demo_bundle_sha256'][:16]}…` before and after: "
        f"{'yes' if r['demo_bundle_unchanged'] else 'NO'} (season {r['season_seed']}, match seed {r['match_seed']}).",
        "",
    ]
    if "prematch" in r:
        lines += ["## 1. Pre-match with the model (plans compared, not played)", "",
                  "| Club | Report: attempts, fallback | Findings | Plan chosen | Same levers as the demo | Seal |",
                  "|---|---|---|---|---|---|"]
        for team, p in r["prematch"].items():
            lines.append(f"| {team} | {p['report']['attempts']}, {'yes' if p['report']['fallback'] else 'no'} | "
                         f"{len(p['report']['findings'])} | {p['chosen']['name']} "
                         f"({'template' if p['chosen']['used_template'] else p['chosen']['reason']}) | "
                         f"{'yes' if p['same_levers_as_demo'] else 'no'} (demo: {p['demo_plan']['name']}) | "
                         f"{'verifies' if p['chosen']['seal_verifies'] else 'FAILS'} |")
        lines.append("")
    if "halftime" in r:
        h = r["halftime"]
        same = all(h["same_half_time_as_demo"].values())
        lines += ["## 2. Half-time with the model, from the demo's own half-time state", "",
                  f"Same half-time as the demo (plans, score {h['ht_score']}, levers in force, first-half events): "
                  f"{'yes' if same else 'NO'}. The second half is not played.", "",
                  "| Bench | Options (validated) | Distinct | Fell back to rules | Choice (rule) | Demo's choice | "
                  "Regret xPts (90% interval) |", "|---|---|---|---|---|---|---|"]
        for team, b in h["benches"].items():
            lines.append(f"| {team} | {' / '.join(o['label'] for o in b['options'])} | "
                         f"{'yes' if b['options_distinct'] else 'NO'} | "
                         f"{'yes' if b['fallback_to_offline_options'] else 'no'} | {b['choice']} ({b['rule']}) | "
                         f"{b['demo_choice']} | {b['regret_xpts']} ({b['regret_ci90'][0]} to {b['regret_ci90'][1]}) "
                         f"vs {b['best_response']} |")
        lines.append("")
    lines += ["## Model turns", "",
              "| Staff | Role | Output | Deployment | Service model | Response id | Tokens in/out | Tools called by "
              "the model |", "|---|---|---|---|---|---|---|---|"]
    groups = [(f"pre-match {t}", p) for t, p in r.get("prematch", {}).items()]
    groups += [(f"half-time {t}", b) for t, b in r.get("halftime", {}).get("benches", {}).items()]
    for name, g in groups:
        for c in g["llm_calls"]:
            lines.append(f"| {name} | {c['role']} | {c['response_format']} | {c['deployment']} | "
                         f"{c['service_model'] or '-'} | {c['response_id'] or '-'} | {c['input_tokens'] or '-'} / "
                         f"{c['output_tokens'] or '-'} | {', '.join(c['tools_called_by_model']) or '-'} |")
    lines += ["", "What this shows: the same agents, tools and validators run with a real model on the demo's data and "
              "half-time state. What it does not change: the committed demo (offline rules) and its video.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from agents.settings import load_env
    load_env()
    ap = argparse.ArgumentParser(prog="python -m pipeline.foundry_probe")
    ap.add_argument("--mode", choices=["offline", "foundry"], default=None, help="default: AGENTS_MODE")
    ap.add_argument("--parts", default="prematch,halftime", help="comma separated: prematch, halftime")
    ap.add_argument("--out", default=None, help="directory for the JSON and Markdown (default depends on the mode)")
    args = ap.parse_args(argv)
    try:
        choice = model_choice(args.mode)  # type: ignore[arg-type]
    except FoundryConfigError as e:
        print(f"Foundry is not configured: {e}")
        return 2
    parts = {p.strip() for p in args.parts.split(",") if p.strip()}
    before = _sha(BUNDLE)
    demo = MatchBundle.model_validate_json(BUNDLE.read_text())
    build = demo.eval["build"]
    season = build_season(build["season_seed"])
    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "mode": choice.mode, "deployments": {"analyst": choice.analyst, "manager": choice.manager},
        "endpoint_host": _host(choice.endpoint), "season_seed": build["season_seed"],
        "match_seed": build["match_seed"], "demo_bundle_sha256": before,
        "started_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    # a part that fails is recorded with its error; the parts that ran are still written (their model calls count)
    for part, run in (("prematch", prematch_part), ("halftime", halftime_part)):
        if part not in parts:
            continue
        try:
            result[part] = run(season, demo, choice)
        except Exception as exc:  # noqa: BLE001 - recorded in the evidence, then the exit code says it failed
            result.setdefault("errors", {})[part] = f"{type(exc).__name__}: {str(exc)[:500]}"
            break
    result["seconds"] = round(time.perf_counter() - t0, 1)
    result["demo_bundle_unchanged"] = _sha(BUNDLE) == before
    calls = _calls(result)
    result["summary"] = {
        "model_turns": len(calls), "turns_with_service_response_id": sum(1 for c in calls if c["response_id"]),
        "service_models": sorted({c["service_model"] for c in calls if c["service_model"]}),
        "input_tokens": sum(c["input_tokens"] or 0 for c in calls),
        "output_tokens": sum(c["output_tokens"] or 0 for c in calls)}
    if args.out:
        out_dir = docs_dir = Path(args.out)
    elif choice.mode == "foundry":
        out_dir, docs_dir = ROOT / "eval" / "results" / "foundry", ROOT / "docs"
    else:
        out_dir = docs_dir = ROOT / "agents" / "_out" / "foundry_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    data = out_dir / f"probe_seed{build['match_seed']}.json"
    data.write_text(json.dumps(result, indent=1))
    doc = docs_dir / "FOUNDRY_EVIDENCE.md"
    doc.write_text(render(result))
    print(f"wrote {data} and {doc}: {result['summary']}; demo unchanged: {result['demo_bundle_unchanged']}"
          + (f"; FAILED: {result['errors']}" if result.get("errors") else ""))
    return 0 if result["demo_bundle_unchanged"] and not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
