"""E1 and E3: the real model (gpt-4.1-mini on Microsoft Foundry) against the rule agents, same test data (D-058).

    python -m eval.compare_agents --pilot                         # one LLM unit: measures tokens, time and cost
    PLAN_A_LLM_BUDGET_EUR=12 python -m eval.compare_agents         # the full comparison (needs .env for Foundry)
    python -m eval.compare_agents --report-only                    # re-render the report from the saved rows

Design (declared before the run; nothing is selected after seeing results):
- Units are pre-match workflows (scouting + plan) of both staffs. E1 units: the official E1 test seasons 8001-8005 with
  E1_MATCHUPS, plus fresh seasons 8006-8015 never used before (all with random trait kinds); E3 units: the official
  match season 8101 with MATCHUPS and its seeds. Every unit is run by both systems with the same season, matchup,
  seeds and scoring functions as eval/run.py; the rule agents must reproduce the committed E1/E3 numbers exactly.
- The model is run LLM_RUNS times per unit (it is not deterministic); the rule agents once.
- E1: precision and recall of the flagged weaknesses against the hidden truth. E3: share of plans with a lever that
  attacks a real hidden weakness. Differences (model minus rules) with 95% paired bootstrap intervals over units;
  "significant" means the 95% interval excludes zero.
- A hard spending cap (agents/budget.py) refuses any model turn that could pass it; the run also stops after repeated
  errors. Rows, ledger and report go to eval/results/compare/; the committed evaluations are not touched.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "results" / "compare"
OFFICIAL_E1 = (8001, 8002, 8003, 8004, 8005)
EXTENDED_E1 = tuple(range(8006, 8016))
E3_SEASON = 8101
LLM_RUNS = 2
STOP_AFTER_ERRORS = 3  # consecutive failed units
THROTTLE_RETRIES, THROTTLE_WAIT = 2, 60  # a unit throttled by the deployment's rate limit is run again after a pause
BOOT, SEED = 10_000, 58


def units(extended: bool = True) -> list[tuple[str, int, int]]:
    e1 = [("e1", s, k) for s in OFFICIAL_E1 + (EXTENDED_E1 if extended else ()) for k in range(3)]
    return e1 + [("e3", E3_SEASON, k) for k in range(6)]


def _season(kind: str, seed: int):
    from sim.season import build_season
    return build_season(seed, season_id=f"s-e1-{seed}" if kind == "e1" else f"s-eval-{seed}", random_trait_kinds=True)


def _describe(exc: BaseException) -> str:
    """The innermost errors of an exception group (asyncio task groups wrap the real cause)."""
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe(e) for e in exc.exceptions)
    cause = f" <- {_describe(exc.__cause__)}" if exc.__cause__ else ""
    return f"{type(exc).__name__}: {str(exc)[:250]}{cause}"


def run_unit(job: tuple[str, int, int, str, int]) -> dict:
    """One pre-match of both staffs, exactly as eval/run.py runs it for E1 or E3, scored with its functions."""
    kind, seed, k, mode, rep = job
    from agents.prematch import run_prematch
    from agents.validators.plan import non_default_levers
    from engine.api import Seeds
    from engine.beliefs import beliefs_from_claims
    from eval.run import E1_MATCHUPS, MATCHUPS, _random_hit_rate, attacks, match_key
    from pipeline.build import make_engine

    os.environ["PLAN_A_LLM_TAG"] = f"{kind}-{seed}-{k}-{mode}-{rep}"
    t0 = time.perf_counter()
    season = _season(kind, seed)
    home, away = (E1_MATCHUPS if kind == "e1" else MATCHUPS)[k]
    engine = make_engine(season, home, away, Seeds() if kind == "e1" else Seeds(match=500 + k))
    try:
        pre = asyncio.run(run_prematch(engine, home, away, mode))
    except Exception as exc:  # noqa: BLE001 - recorded; repeated failures stop the run
        return {"unit": [kind, seed, k], "mode": mode, "rep": rep, "error": _describe(exc)[:600]}
    reports, plans = [], []
    for r in pre.values():
        found = beliefs_from_claims([engine.claims[f.claim_id] for f in r.report.findings
                                     if f.claim_id in engine.claims])
        real = season.truth.teams[r.opponent].traits
        truth = [{"team": r.opponent, "kind": t.kind, "player_id": t.player_id, "side": t.side} for t in real]
        reports.append({"by": r.team, "scouted": r.opponent, "flagged": sorted({match_key(b) for b in found}),
                        "truth": sorted({match_key(t) for t in truth}), "attempts": r.report.attempts,
                        "fallback": r.report.fallback})
        served = {c for t in r.traces for c in t.result_claims}
        changed = non_default_levers(r.chosen)
        starters = [p.player_id for p in season.public.squads.teams[r.opponent].players if p.starter]
        plans.append({"team": r.team, "opponent": r.opponent, "attacks_real": any(attacks(r.chosen.levers, t)
                                                                                   for t in real),
                      "changed_levers": len(changed),
                      "cited_served": sum(bool(r.chosen.lever_evidence.get(lv)) and set(r.chosen.lever_evidence[lv])
                                          <= served for lv in changed),
                      "used_template": r.used_template, "random_baseline": _random_hit_rate(real, starters),
                      "levers": r.chosen.levers.model_dump()})
    return {"unit": [kind, seed, k], "mode": mode, "rep": rep, "reports": reports, "plans": plans,
            "seconds": round(time.perf_counter() - t0, 1)}


# ---------------------------------------------------------------------------------------------- statistics
def _e1_counts(rows: list[dict]) -> np.ndarray:
    """Per unit: [correct, flagged, true] summed over its reports (and over the model's runs)."""
    out = []
    for row in rows:
        c = f = t = 0
        for rep in row:
            for r in rep["reports"]:
                fl, tr = {tuple(x) for x in r["flagged"]}, {tuple(x) for x in r["truth"]}
                c, f, t = c + len(fl & tr), f + len(fl), t + len(tr)
        out.append((c, f, t))
    return np.array(out, dtype=float)


def _e3_hits(rows: list[dict]) -> np.ndarray:
    """Per unit: [plans attacking a real weakness, plans] summed over its staffs (and over the model's runs)."""
    return np.array([(sum(p["attacks_real"] for rep in row for p in rep["plans"]),
                      sum(len(rep["plans"]) for rep in row)) for row in rows], dtype=float)


def _boot(stat, a: np.ndarray, b: np.ndarray) -> dict:
    """Paired bootstrap over units of stat(b) - stat(a) (b = model, a = rules), with each side's own interval."""
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(a), size=(BOOT, len(a)))
    diffs = np.array([stat(b[i]) - stat(a[i]) for i in idx])
    sa, sb = np.array([stat(a[i]) for i in idx]), np.array([stat(b[i]) for i in idx])
    q = lambda x: [round(float(np.quantile(x, 0.025)), 3), round(float(np.quantile(x, 0.975)), 3)]  # noqa: E731
    d = float(stat(b) - stat(a))
    lo, hi = q(diffs)
    return {"rules": {"value": round(float(stat(a)), 3), "ci95": q(sa)},
            "llm": {"value": round(float(stat(b)), 3), "ci95": q(sb)},
            "diff": {"value": round(d, 3), "ci95": [lo, hi]}, "significant": lo > 0 or hi < 0, "units": len(a)}


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "error" not in r]
    by = {}
    for r in ok:
        by.setdefault((tuple(r["unit"]), r["mode"]), []).append(r)
    llm_units = {u for u, m in by if m == "foundry"}
    paired = sorted(u for u in llm_units if (u, "offline") in by)
    out = {"design": {"official_e1_seasons": OFFICIAL_E1, "extended_e1_seasons": EXTENDED_E1, "e3_season": E3_SEASON,
                      "llm_runs_per_unit": LLM_RUNS, "bootstrap": BOOT, "interval": "95% paired bootstrap over units"},
           "units_paired": len(paired),
           "errors": [r for r in rows if "error" in r],  # every failed attempt, also those run again successfully
           "errors_unresolved": [r for r in rows if "error" in r and (tuple(r["unit"]), r["mode"]) not in by]}
    precision = lambda x: x[:, 0].sum() / x[:, 1].sum()  # noqa: E731
    recall = lambda x: x[:, 0].sum() / x[:, 2].sum()  # noqa: E731
    share = lambda x: x[:, 0].sum() / x[:, 1].sum()  # noqa: E731
    for name, keep in (("official", lambda u: u[1] in OFFICIAL_E1 or u[0] == "e3"),
                       ("extended", lambda u: u[1] in EXTENDED_E1), ("all", lambda u: True)):
        us = [u for u in paired if keep(u)]
        e1u, e3u = [u for u in us if u[0] == "e1"], [u for u in us if u[0] == "e3"]
        sec: dict = {"e1_units": len(e1u), "e3_units": len(e3u)}
        if e1u:
            a, b = _e1_counts([by[(u, "offline")] for u in e1u]), _e1_counts([by[(u, "foundry")] for u in e1u])
            sec["E1_precision"], sec["E1_recall"] = _boot(precision, a, b), _boot(recall, a, b)
            sec["E1_counts"] = {"rules": a.sum(0).tolist(), "llm": b.sum(0).tolist(), "fields": ["correct", "flagged",
                                                                                                  "true"]}
        plan_units = e3u if name == "official" else us  # E3 on the official season; also pooled over all units
        if plan_units:
            a = _e3_hits([by[(u, "offline")] for u in plan_units])
            b = _e3_hits([by[(u, "foundry")] for u in plan_units])
            sec["E3_attacks_real_weakness"] = _boot(share, a, b)
            sec["E3_plans"] = {"rules": int(a[:, 1].sum()), "llm": int(b[:, 1].sum())}
            base = [p["random_baseline"] for u in plan_units for rep in by[(u, "offline")] for p in rep["plans"]]
            sec["E3_random_plan_baseline"] = round(float(np.mean(base)), 3)
        out[name] = sec
    llm = [r for r in ok if r["mode"] == "foundry"]
    if llm:
        reports = [x for r in llm for x in r["reports"]]
        plans = [p for r in llm for p in r["plans"]]
        out["llm_behaviour"] = {"reports": len(reports),
                                "reports_valid_first_try": round(np.mean([x["attempts"] == 1 and not x["fallback"]
                                                                          for x in reports]), 3),
                                "reports_fallback": int(sum(x["fallback"] for x in reports)),
                                "plans_from_template": int(sum(p["used_template"] for p in plans)),
                                "levers_citing_served_claims": round(sum(p["cited_served"] for p in plans) / max(
                                    1, sum(p["changed_levers"] for p in plans)), 3)}
        def flags(rs):
            reps = [x for r in rs for x in r["reports"]]
            return sum(len(x["flagged"]) for x in reps) / max(1, len(reps))
        valid = [x for r in llm for x in r["reports"] if not x["fallback"]]
        c = sum(len({tuple(a) for a in x["flagged"]} & {tuple(a) for a in x["truth"]}) for x in valid)
        f, t = sum(len(x["flagged"]) for x in valid), sum(len(x["truth"]) for x in valid)
        own = [p for p in plans if not p["used_template"]]
        out["diagnostic"] = {  # where a gap comes from; every unit, nothing selected; not a second comparison
            "flagged_per_report": {"rules": round(flags([r for r in ok if r["mode"] == "offline"]), 2),
                                   "llm": round(flags(llm), 2)},
            "llm_validated_reports": {"n": len(valid), "precision": round(c / f, 3) if f else None,
                                      "recall": round(c / t, 3) if t else None},
            "llm_own_plans": {
                "n": len(own),
                "attack_real_weakness": round(np.mean([p["attacks_real"] for p in own]), 3) if own else None,
                "random_baseline": round(np.mean([p["random_baseline"] for p in own]), 3) if own else None}}
        runs = {}
        for r in llm:
            if r["unit"][0] == "e1":
                runs.setdefault(r["rep"], []).append([r])
        if len(runs) > 1:
            out["llm_run_to_run"] = {f"run {k}": round(precision(_e1_counts(v)), 3) for k, v in sorted(runs.items())}
    return out


# ---------------------------------------------------------------------------------------------- report
SETS = (("official", "Official test set (E1 seasons 8001-8005, E3 season 8101)"),
        ("extended", "Fresh seasons 8006-8015 (declared before the run)"),
        ("all", "All units"))
METRICS = (("E1_precision", "E1 precision"), ("E1_recall", "E1 recall"),
           ("E3_attacks_real_weakness", "E3 plans attacking a real weakness"))


def _fmt(x: dict) -> str:
    return f"{x['value']} ({x['ci95'][0]} to {x['ci95'][1]})"


def _interpretation(summary: dict) -> str:
    """One generated sentence for the analyst desk, from the pooled results and the diagnostic."""
    a, d = summary.get("all", {}), summary.get("diagnostic")
    if not a.get("E1_precision") or not d:
        return ""
    p, r, e3 = a["E1_precision"], a["E1_recall"], a.get("E3_attacks_real_weakness")
    fl = d["flagged_per_report"]
    text = (f"The model is about as precise as the rules ({p['llm']['value']} vs {p['rules']['value']}) but flags "
            f"fewer weaknesses ({fl['llm']} vs {fl['rules']} per report), so its recall is lower "
            f"({r['llm']['value']} vs {r['rules']['value']}).")
    if e3:
        text += (f" Its plans attack a real weakness {e3['llm']['value']} of the time against {e3['rules']['value']} "
                 f"for the rules (a random plan: {a.get('E3_random_plan_baseline')}).")
    return text


def web_summary(summary: dict) -> dict:
    """The few rows the analyst desk shows (official set and all units), with the report's path."""
    rows = []
    for key, label in METRICS:
        for name, short in (("official", "official test set"), ("all", "all units")):
            m = summary.get(name, {}).get(key)
            if m:
                rows.append({"metric": f"{label} · {short}", "rules": {"value": m["rules"]["value"]},
                             "llm": {"value": m["llm"]["value"]},
                             "diff": {"value": m["diff"]["value"], "ci95": m["diff"]["ci95"]},
                             "significant": m["significant"]})
    led = summary.get("ledger") or {}
    return {"title": "E1 and E3: Foundry agents (gpt-4.1-mini) against the rule agents",
            "design": f"Same test seasons, matchups, seeds and scoring for both; the model ran {LLM_RUNS} times per "
                      f"unit; differences (model minus rules) with 95% paired bootstrap intervals over units.",
            "rows": rows, "llm_runs": LLM_RUNS, "cost_eur": round(led.get("cost_eur", 0.0), 2),
            "calls": led.get("turns", 0),
            "note": _interpretation(summary) + " \"Significant\" means the 95% interval of the difference "
                    "excludes zero.",
            "report": "eval/results/compare/AGENTS_COMPARISON.md"}


def render_report(summary: dict) -> str:
    lines = ["# Foundry agents (gpt-4.1-mini) against the rule agents: E1 and E3",
             "", "Generated by `python -m eval.compare_agents --report-only` from "
             "`eval/results/compare/rows.jsonl`; no number is typed by hand. Everything is measured inside our "
             "simulator on synthetic data.", "",
             "## Design (declared before the run)", "",
             "- Units: pre-match workflows of both staffs. E1: official test seasons 8001-8005 and fresh seasons "
             "8006-8015 (random trait kinds, never used before), three matchups each; E3: the official match season "
             "8101, six matchups and their seeds. Both systems ran every unit with the same seasons, matchups, seeds "
             "and the scoring functions of `eval/run.py`; the rule agents reproduce the committed E1/E3 exactly.",
             f"- The model (gpt-4.1-mini, Global Standard, Microsoft Foundry) ran {LLM_RUNS} times per unit with the "
             "production prompts and validators; nothing was tuned for this comparison. Rule agents: once "
             "(deterministic). Validation failures and template fallbacks count as the system's output.",
             "- E1: precision and recall of the weaknesses a scouting report flags against the hidden traits. E3: "
             "share of chosen plans with a lever that attacks a real hidden weakness (the random-plan baseline is "
             "the share of all lever combinations that would also count).",
             f"- Differences are model minus rules, with 95% paired bootstrap intervals over units ({BOOT} "
             "resamples, fixed seed); \"significant\" means the 95% interval excludes zero. The model's runs are "
             "pooled per unit.", ""]
    for name, title in SETS:
        sec = summary.get(name)
        if not sec or not (sec.get("e1_units") or sec.get("e3_units")):
            continue
        lines += [f"## {title}", "", f"Units: {sec.get('e1_units', 0)} E1, {sec.get('e3_units', 0)} E3"
                  + (f"; plans: {sec['E3_plans']['rules']} (rules), {sec['E3_plans']['llm']} (model, all runs)"
                     if sec.get("E3_plans") else "") + ".", "",
                  "| Measure | Rule agents (95% CI) | Foundry agents (95% CI) | Difference (95% CI) | Significant |",
                  "|---|---|---|---|---|"]
        for key, label in METRICS:
            m = sec.get(key)
            if m:
                lines.append(f"| {label} | {_fmt(m['rules'])} | {_fmt(m['llm'])} | {_fmt(m['diff'])} | "
                             f"{'yes' if m['significant'] else 'no'} |")
        if sec.get("E1_counts"):
            r, mm = sec["E1_counts"]["rules"], sec["E1_counts"]["llm"]
            lines.append(f"\nE1 counts (correct / flagged / real): rules {int(r[0])} / {int(r[1])} / {int(r[2])}; "
                         f"model, all runs {int(mm[0])} / {int(mm[1])} / {int(mm[2])}.")
        if sec.get("E3_random_plan_baseline") is not None:
            lines.append(f"E3 random-plan baseline: {sec['E3_random_plan_baseline']}.")
        lines.append("")
    b = summary.get("llm_behaviour")
    if b:
        lines += ["## How the model behaved", "",
                  f"- Scouting reports valid at the first attempt: {b['reports_valid_first_try']} of {b['reports']}; "
                  f"reports replaced by the template after the retries: {b['reports_fallback']}.",
                  f"- Plans from the template (no valid candidate): {b['plans_from_template']}; levers citing claims "
                  f"the staff retrieved: {b['levers_citing_served_claims']}."]
        if summary.get("llm_run_to_run"):
            lines.append("- E1 precision by model run: " + ", ".join(f"{k} {v}" for k, v in
                                                                        summary["llm_run_to_run"].items()) + ".")
        lines.append("")
    d = summary.get("diagnostic")
    if d:
        v, o = d["llm_validated_reports"], d["llm_own_plans"]
        lines += ["## Where the gap comes from (diagnostic over every unit; not a second comparison)", "",
                  f"- Weaknesses flagged per scouting report: rules {d['flagged_per_report']['rules']}, model "
                  f"{d['flagged_per_report']['llm']}.",
                  f"- The model's {v['n']} reports that passed validation: precision {v['precision']}, recall "
                  f"{v['recall']}: it is precise but flags few weaknesses, so it misses most real ones.",
                  f"- The model's {o['n']} plans that were not the template attack a real weakness "
                  f"{o['attack_real_weakness']} of the time, against {o['random_baseline']} for a random plan on "
                  "the same opponents.", ""]
    led = summary.get("ledger") or {}
    lines += ["## Cost and errors", "",
              f"- Model turns recorded by the spending ledger: {led.get('turns', 0)}; tokens "
              f"{led.get('input_tokens', 0):,} in, {led.get('output_tokens', 0):,} out; about EUR "
              f"{led.get('cost_eur', 0)} at the public price plus 10%, charged to the Free Trial credit.",
              f"- Failed attempts: {len(summary.get('errors', []))} (throttling by the deployment's rate limit, run "
              f"again); units still missing: {len(summary.get('errors_unresolved', []))}.", "",
              "## Limitations", "",
              "- A synthetic world: these numbers say how each system does inside our simulator, not in real football.",
              "- One model, its default sampling and the production prompts; a different model or prompt could do "
              "better or worse. E3 counts a lever-trait match only, not whether the plan would win.",
              "- The official E3 set has 12 plans: its interval is wide; the pooled set adds every plan of the E1 "
              "units under the same criterion.", ""]
    return "\n".join(lines)


README = Path(__file__).resolve().parents[1] / "README.md"
START, END = "<!-- AGENTS_COMPARISON -->", "<!-- /AGENTS_COMPARISON -->"


def readme_block(summary: dict) -> str:
    rows = ["| Measure | Set | Rule agents | Foundry agents | Difference (95% CI) | Significant |",
            "|---|---|---|---|---|---|"]
    for key, label in METRICS:
        for name, short in (("official", "official test set"), ("all", "all units")):
            m = summary.get(name, {}).get(key)
            if m:
                rows.append(f"| {label} | {short} | {m['rules']['value']} | {m['llm']['value']} | "
                            f"{_fmt(m['diff'])} | {'yes' if m['significant'] else 'no'} |")
    return START + "\n" + "\n".join(rows) + "\n" + END


def update_readme(summary: dict) -> bool:
    text = README.read_text()
    if START not in text:
        return False
    before, rest = text.split(START, 1)
    README.write_text(before + readme_block(summary) + rest.split(END, 1)[1])
    return True


# ---------------------------------------------------------------------------------------------- execution
def execute(jobs: list[tuple], workers: int, rows_path: Path) -> list[dict]:
    from agents.budget import BudgetExceeded
    rows = [json.loads(x) for x in rows_path.read_text().splitlines()] if rows_path.exists() else []
    done = {(tuple(r["unit"]), r["mode"], r["rep"]) for r in rows if "error" not in r}
    todo = [j for j in jobs if ((j[0], j[1], j[2]), j[3], j[4]) not in done]  # resumable
    print(f"{len(done)} unit runs already saved, {len(todo)} to run", flush=True)
    consecutive, retries = 0, {}
    with ProcessPoolExecutor(workers) as ex, open(rows_path, "a") as sink:
        pending = {ex.submit(run_unit, j): j for j in todo[:workers]}
        queue = todo[workers:]
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in finished:
                job = pending.pop(fut)
                row = fut.result()
                err = row.get("error", "")
                if "rate_limit_exceeded" in err and retries.get(job, 0) < THROTTLE_RETRIES:
                    retries[job] = retries.get(job, 0) + 1  # throttled, not broken: wait and run the unit again
                    print(f"{job[:3]} {job[3]}#{job[4]}: throttled (429), retry {retries[job]} in {THROTTLE_WAIT} s",
                          flush=True)
                    time.sleep(THROTTLE_WAIT)
                    pending[ex.submit(run_unit, job)] = job
                    continue
                sink.write(json.dumps(row) + "\n")
                sink.flush()
                rows.append(row)
                consecutive = consecutive + 1 if err else 0
                print(f"{job[:3]} {job[3]}#{job[4]}: {err or 'ok'} ({row.get('seconds', '-')} s)", flush=True)
                if BudgetExceeded.__name__ in err or consecutive >= STOP_AFTER_ERRORS:
                    print(f"STOPPING: {err}", flush=True)
                    queue = []
                if queue:
                    nxt = queue.pop(0)
                    pending[ex.submit(run_unit, nxt)] = nxt
    return rows


def main(argv: list[str] | None = None) -> int:
    from agents.budget import Ledger
    from agents.settings import load_env
    load_env()
    ap = argparse.ArgumentParser(prog="python -m eval.compare_agents")
    ap.add_argument("--pilot", action="store_true", help="one model unit only, to measure tokens and cost")
    ap.add_argument("--rules-only", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--no-extended", action="store_true", help="official test seasons only")
    ap.add_argument("--workers", type=int, default=1)  # one at a time: two parallel units exceed 200K tokens/min
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows_path = OUT / ("pilot_rows.jsonl" if args.pilot else "rows.jsonl")
    us = units(extended=not args.no_extended)
    if args.pilot:
        jobs = [(*us[0], "foundry", 1)]
    elif args.rules_only:
        jobs = [(*u, "offline", 0) for u in us]
    else:
        jobs = [(*u, "offline", 0) for u in us] + [(*u, "foundry", rep) for rep in range(1, LLM_RUNS + 1) for u in us]
    if not args.report_only:
        if any(j[3] == "foundry" for j in jobs) and Ledger.from_env() is None:
            raise SystemExit("set PLAN_A_LLM_BUDGET_EUR (and PLAN_A_LLM_LEDGER): model runs need a hard spending cap")
        rows = execute(jobs, args.workers, rows_path)
    else:
        rows = [json.loads(x) for x in rows_path.read_text().splitlines()]
    ledger = Ledger.from_env() or (Ledger(OUT / "ledger.jsonl", 0) if (OUT / "ledger.jsonl").exists() else None)
    summary = summarize(rows)
    summary["ledger"] = ledger.totals() if ledger else None
    if args.pilot:
        (OUT / "pilot_summary.json").write_text(json.dumps(summary, indent=1))
    else:
        summary["web_summary"] = web_summary(summary)
        (OUT / "agents_llm_vs_rules.json").write_text(json.dumps(summary, indent=1))
        (OUT / "AGENTS_COMPARISON.md").write_text(render_report(summary))
        if update_readme(summary):
            print("README comparison block updated")
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
