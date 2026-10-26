"""Publish the recorded Microsoft Foundry run (and the agent comparison, when it exists) for the web app's analyst desk.

    python -m pipeline.foundry_web        # writes web/public/foundry_run.json

Reads eval/results/foundry/probe_seed204.json (the real run, D-056), the frozen demo bundle (read only: the offline
decisions to compare with) and, if present, eval/results/compare/agents_llm_vs_rules.json (the E1/E3 comparison).
Only allow-listed fields are copied (model, response ids, tokens, tools, validator messages, decisions): no tenant,
subscription, resource name, endpoint or account. The demo bundle is never written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "eval" / "results" / "foundry" / "probe_seed204.json"
COMPARISON = ROOT / "eval" / "results" / "compare" / "agents_llm_vs_rules.json"
BUNDLE = ROOT / "web" / "public" / "match_bundle.json"
OUT = ROOT / "web" / "public" / "foundry_run.json"
SCHEMA = "plan-a/foundry-run@1"

# What each validator message means, for a judge who does not read code (first match wins).
PLAIN = [
    ("contains numbers that do not come from a claim placeholder", "typed a number instead of citing recorded data"),
    ("must not contain numbers", "put numbers in a plan's name"),
    ("a share target must be between 0 and 1", "set a percentage target outside 0-100%"),
    ("target must be positive", "set a KPI target of zero or less"),
    ("whole number", "used a fraction for a count"),
    ("beyond anything in the league", "set a target no team ever reached"),
    ("sentence cites no claim", "wrote a sentence without citing evidence"),
    ("causal claim without an observed_mechanism claim", "claimed a cause without evidence of the mechanism"),
    ("cites claims this staff never retrieved", "cited evidence it never looked up"),
    ("cites no claim", "changed a tactic without citing evidence"),
]


def plain(message: str) -> str:
    return next((p for key, p in PLAIN if key in message), "broke a validation rule")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _turns(r: dict) -> list[dict]:
    groups = [("pre-match", t, p) for t, p in r["prematch"].items()]
    groups += [("half-time", t, b) for t, b in r["halftime"]["benches"].items()]
    return [{"phase": phase, "club": club, "role": c["role"], "output": c["response_format"],
             "response_id": c["response_id"], "service_model": c["service_model"], "input_tokens": c["input_tokens"],
             "output_tokens": c["output_tokens"], "tools": c["tools_called_by_model"], "ms": c["ms"]}
            for phase, club, g in groups for c in g["llm_calls"]]


def _guardrails(r: dict) -> list[dict]:
    """What the validators rejected and how each agent reacted (fixed on a later attempt, or discarded)."""
    out = []
    for club, p in r["prematch"].items():
        report_errors = [m for m in p["rejected_steps"] if m.startswith("c_")]  # text verifier, scouting report
        if p["report"]["attempts"] > 1 or report_errors:
            ok, attempts = not p["report"]["fallback"], p["report"]["attempts"]
            out.append({"club": club, "agent": "analyst", "item": "scouting report", "attempts": attempts,
                        "rejections": [{"message": m, "plain": plain(m)} for m in report_errors],
                        "outcome": f"accepted on attempt {attempts}" if ok else "replaced by a template"})
        for i, c in enumerate(p["candidates"], 1):
            failed = [errs for errs in c["validation"] if errs]
            if not failed:
                continue
            seen: dict[str, str] = {}
            for errs in failed:
                for e in errs:
                    seen.setdefault(plain(e), e)
            attempts = len(c["validation"])
            out.append({"club": club, "agent": "manager", "item": f"plan candidate {i}", "attempts": attempts,
                        "rejections": [{"message": m, "plain": k} for k, m in seen.items()],
                        "outcome": f"fixed on attempt {attempts}" if c["valid"] else
                        f"still invalid after {attempts} attempts: discarded"})
    return out


def _demo_decisions(bundle: dict) -> dict[str, dict]:
    duel = bundle["duel"]
    labels = {o["option_id"]: o["label"]["en"] for p in duel["private"].values() for o in p["options"]}
    claims = {c["claim_id"]: c for c in bundle["claims"]}
    out = {}
    for club, rg in duel["broadcast"]["regret"].items():
        c = claims[rg["claim_id"]]
        out[club] = {"choice": labels[rg["chosen"]], "rule": duel["broadcast"]["revealed"][club]["rule"],
                     "regret_xpts": rg["regret_xpts"], "regret_ci90": [c["interval_low"], c["interval_high"]],
                     "best_response": labels[rg["best_response"]],
                     "options": [o["label"]["en"] for o in duel["private"][club]["options"]]}
    return out


def build(evidence: dict, bundle: dict, comparison: dict | None, evidence_sha: str, comparison_sha: str | None) -> dict:
    turns = _turns(evidence)
    demo = _demo_decisions(bundle)
    benches = {}
    for club, b in evidence["halftime"]["benches"].items():
        benches[club] = {
            "foundry": {"options": [{"label": o["label"], "changes": o["lever_changes"], "subs": len(o["subs"])}
                                    for o in b["options"]],
                        "distinct": b["options_distinct"], "fell_back_to_rules": b["fallback_to_offline_options"],
                        "choice": b["choice"], "rule": b["rule"], "regret_xpts": b["regret_xpts"],
                        "regret_ci90": b["regret_ci90"], "best_response": b["best_response"]},
            "demo": demo[club]}
    plans = {club: {"foundry_plan": p["chosen"]["name"], "kpis": p["chosen"]["kpis"],
                    "seal_verifies": p["chosen"]["seal_verifies"], "demo_plan": p["demo_plan"]["name"],
                    "same_levers_as_demo": p["same_levers_as_demo"], "report_attempts": p["report"]["attempts"],
                    "findings": len(p["report"]["findings"])}
             for club, p in evidence["prematch"].items()}
    tools: dict[str, int] = {}
    for t in turns:
        for name in t["tools"]:
            tools[name] = tools.get(name, 0) + 1
    s = evidence["summary"]
    return {
        "schema": SCHEMA,
        "sources": {"evidence": str(EVIDENCE.relative_to(ROOT)), "evidence_sha256": evidence_sha,
                    "comparison": str(COMPARISON.relative_to(ROOT)) if comparison else None,
                    "comparison_sha256": comparison_sha},
        "run": {"mode": evidence["mode"], "model": sorted(set(s["service_models"])), "started_utc":
                evidence["started_utc"], "seconds": evidence["seconds"], "endpoint_domain": evidence["endpoint_host"],
                "season_seed": evidence["season_seed"], "match_seed": evidence["match_seed"],
                "demo_bundle_sha256": evidence["demo_bundle_sha256"],
                "demo_bundle_unchanged": evidence["demo_bundle_unchanged"]},
        "totals": {"model_turns": s["model_turns"], "with_service_response_id": s["turns_with_service_response_id"],
                   "input_tokens": s["input_tokens"], "output_tokens": s["output_tokens"],
                   "tool_calls_by_model": sum(tools.values()), "tools_by_model": dict(sorted(tools.items()))},
        "turns": turns,
        "guardrails": _guardrails(evidence),
        "plans": plans,
        "halftime": {"score": evidence["halftime"]["ht_score"],
                     "same_as_demo": evidence["halftime"]["same_half_time_as_demo"], "benches": benches},
        "comparison": comparison.get("web_summary") if comparison else None,
    }


def render() -> dict:
    evidence = json.loads(EVIDENCE.read_text())
    bundle = json.loads(BUNDLE.read_text())
    comparison = json.loads(COMPARISON.read_text()) if COMPARISON.exists() else None
    return build(evidence, bundle, comparison, _sha(EVIDENCE), _sha(COMPARISON) if comparison else None)


def main() -> int:
    data = render()
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {data['totals']['model_turns']} model turns, "
          f"{len(data['guardrails'])} guardrail events, comparison {'included' if data['comparison'] else 'not yet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
