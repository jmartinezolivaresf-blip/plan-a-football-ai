"""WF-Previa: analyst -> scouting report -> manager -> candidates -> validation -> valuation -> choice -> seal.

Each staff runs against its OWN scoped MCP server (in-process, no network). Both staffs share the engine but never
a scope, so neither can read the other's private data. Usage:

    python -m agents.prematch                    # offline rules client (no Azure)
    AGENTS_MODE=foundry python -m agents.prematch  # Microsoft Foundry models (needs .env, az login)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_framework import Agent, MCPStdioTool
from mcp import Client

from contracts import Claim, I18nText, Kpi, Levers, Plan, Seal, TraceStep
from contracts.engine_api import EngineAPI
from contracts.plan import OpponentPlanEstimate
from contracts.sealing import plan_digest, verify_plan
from mcp_server.policy import ScopedTools
from mcp_server.server import DEMO_MATCH, build_server

from .clients import ChatClients, ModelChoice, model_choice
from .models import (
    CandidateDraft,
    CandidateResult,
    CandidateSetDraft,
    Finding,
    PrematchResult,
    ScoutingDraft,
    ScoutingReport,
)
from .validators import text as tv

MAX_REVISIONS = 2
SCOUTING_TOOLS = ["list_matches", "get_team_tendencies", "get_player_profile", "get_set_piece_profile", "get_claim"]

ANALYST_INSTRUCTIONS = """You are the opposition analyst of {team}. Study {opp} using ONLY the claims in the evidence
block (you may call the scouting tools to look up more claims). Pick at most 5 findings, each tied to one claim_id.
Prefer the strongest evidence of a WEAKNESS: a value far above its reference relative to its likely range
(interval_low to interval_high); a reference inside that range may be noise.
Never write a number: refer to values only as {{claim_id.field}} placeholders (fields: value, league_ref, n,
interval_low, interval_high). If a claim has status "insufficient", say it may be noise. Also guess the opponent's
likely levers, citing claims.
You know nothing about hidden traits; only observed data."""

MANAGER_INSTRUCTIONS = """You are the manager of {team} preparing the match against {opp}. Propose 2 or 3 candidate game
plans using ONLY these levers: press_height (high|mid|low), press_target (an opponent player_id or null), build_up
(short|mixed|direct), attack_channel (left|center|right|balanced), corner_delivery (near_post|far_post|short).
Every lever you change from the default (mid, null, mixed, balanced, near_post) must cite at least one claim_id
from the scouting report in lever_evidence. KPIs must come from: high_turnovers, final_third_entries_share
(params.channel), set_piece_xg, balls_in_behind_conceded. Never write numbers in the rationale except as
{{claim_id.field}} placeholders or [claim_id] tags. If VALIDATION ERRORS are given, fix exactly those."""


def _block(payload: dict[str, Any]) -> str:
    return "<<<EVIDENCE\n" + json.dumps(payload, ensure_ascii=False) + "\nEVIDENCE>>>"


class Staff:
    """One coaching staff: its scoped tools, an in-process MCP client, its chat clients and its trace."""

    def __init__(self, engine: EngineAPI, team: str, home: str, away: str, choice: ModelChoice,
                 visible_minute: int = 0, workflow: str = "prematch"):
        self.team, self.opp = team, (away if team == home else home)
        match_id = getattr(getattr(engine, "meta", None), "match_id", None) or DEMO_MATCH
        self.tools = ScopedTools(engine=engine, scope=team, home=home, away=away, match_id=match_id,
                                 visible_minute=visible_minute)
        self.server = build_server(self.tools)
        self.choice = choice
        self.chat = ChatClients(choice)
        self.workflow = workflow
        self.trace: list[TraceStep] = []
        self._actor = "analyst"
        self._recorded = 0

    # ------------------------------------------------------------------ tools and trace
    async def call(self, client: Client, tool: str, args: dict[str, Any]) -> Any:
        result = await client.call_tool(tool, args)
        text = result.content[0].text if result.content else "null"
        self._flush()
        return json.loads(text)

    def _flush(self) -> None:
        """Copy server-side call records (also those made by the LLM through MCP) into the trace."""
        for rec in self.tools.calls[self._recorded:]:
            self._step(self._actor, rec.tool, rec.args, rec.claims, rec.duration_ms,
                       "ok" if rec.status == "ok" else "rejected", rec.message)
        self._recorded = len(self.tools.calls)

    def _step(self, agent: str, tool: str | None, args: dict, claims: list[str], ms: int, status: str,
              message: str | None = None) -> None:
        safe_args = {k: (v if k not in ("plan", "opponent_estimate") else "<plan>") for k, v in args.items()}
        tag = {"prematch": "pre", "duel": "duel", "final": "fin", "live": "live"}[self.workflow]
        self.trace.append(TraceStep(trace_id=f"{self.team}-{tag}-{len(self.trace) + 1:03d}", workflow=self.workflow,
                                    agent=agent, scope=self.team, step=len(self.trace), tool=tool, args=safe_args,
                                    result_claims=claims, duration_ms=ms, status=status, message=message))

    def claims(self) -> dict[str, Claim]:
        """Claims actually served to this staff in this run (the only evidence it may cite)."""
        out = {}
        for cid in self.tools.claims_served:
            raw = self.tools.call("get_claim", {"claim_id": cid})
            if "error" not in raw:
                out[cid] = Claim.model_validate(raw)
        self.tools.calls = self.tools.calls[: self._recorded]  # internal lookups are not agent actions
        return out

    async def ask(self, role: str, instructions: str, prompt: str, fmt, client: Client):
        """One LLM turn with structured output. Foundry agents also get the scoped MCP tools."""
        tools = None
        if self.choice.mode == "foundry":
            tools = [MCPStdioTool(name=f"plan-a-{self.team}", mcp_client=client,
                                  allowed_tools=SCOUTING_TOOLS if role == "analyst" else None)]
        agent = Agent(self.chat.get(role), instructions, name=f"{self.team}-{role}", tools=tools)
        t0 = time.perf_counter()
        try:
            resp = await agent.run(prompt, options={"response_format": fmt})
        finally:
            await agent.close()  # closes the MCP tool contexts the run opened; the shared chat client stays open
        self._flush()
        model = self.choice.analyst if role == "analyst" else self.choice.manager
        self._step(role, None, {"response_format": fmt.__name__}, [], int((time.perf_counter() - t0) * 1000), "ok",
                   f"model:{model}")
        value = resp.value if resp.value is not None else fmt.model_validate_json(resp.text)
        return value

    # ------------------------------------------------------------------ analyst
    async def scout(self, client: Client) -> ScoutingReport:
        self._actor = "analyst"
        await self.call(client, "list_matches", {"team": self.opp})
        tendencies = await self.call(client, "get_team_tendencies", {"team": self.opp, "aspect": "all"})
        await self.call(client, "get_set_piece_profile", {"team": self.opp})
        for pid in sorted({c["player_id"] for c in tendencies if c.get("player_id")}):
            await self.call(client, "get_player_profile", {"player_id": pid})
        claims = self.claims()
        payload = {"team": self.team, "opponent": self.opp,
                   "claims": [c.model_dump(mode="json") for c in claims.values()]}
        prompt_base = f"Scout {self.opp} for {self.team}.\n" + _block(payload)
        errors: list[str] = []
        draft: ScoutingDraft | None = None
        attempts = 0
        for attempt in range(1, tv.MAX_ATTEMPTS + 1):
            attempts = attempt
            prompt = prompt_base if not errors else prompt_base + "\nVALIDATION ERRORS:\n" + "\n".join(errors)
            draft = await self.ask("analyst", ANALYST_INSTRUCTIONS.format(team=self.team, opp=self.opp), prompt,
                                   ScoutingDraft, client)
            errors = self._check_scouting(draft, claims)
            self._step("validator", None, {"check": "scouting_report"}, [f.claim_id for f in draft.findings], 0,
                       "ok" if not errors else "rejected", "; ".join(errors)[:300] or None)
            if not errors:
                break
        fallback = bool(errors)
        if fallback:
            draft = _template_scouting(claims)
        return self._build_report(draft, claims, attempts, fallback)

    def _check_scouting(self, draft: ScoutingDraft, claims: dict[str, Claim]) -> list[str]:
        errors = []
        for f in draft.findings:
            if f.claim_id not in claims:
                errors.append(f"finding cites {f.claim_id}, which no tool returned")
                continue
            errors += [f"{f.claim_id}: {e}" for e in tv.verify(f.headline, claims)]
        errors += [f"estimate cites unknown {c}" for c in draft.opponent_evidence if c not in claims]
        return errors

    def _build_report(self, draft: ScoutingDraft, claims: dict[str, Claim], attempts: int,
                      fallback: bool) -> ScoutingReport:
        findings = []
        for f in draft.findings:
            c = claims[f.claim_id]
            findings.append(Finding(claim_id=c.claim_id, headline=f.headline, metric=c.metric, player_id=c.player_id,
                                    value=c.value, league_ref=c.league_ref, n=c.n, confidence=_confidence(c)))
        est = OpponentPlanEstimate(estimator=self.team, opponent=self.opp,
                                   levers=Levers(**draft.opponent_levers.model_dump()),
                                   confidence={"high": 0.7, "medium": 0.5, "low": 0.3}[draft.opponent_confidence],
                                   claims=draft.opponent_evidence)
        model = self.choice.analyst if not fallback else "template"
        return ScoutingReport(team=self.team, opponent=self.opp, findings=findings, opponent_plan_estimate=est,
                              model=model, attempts=attempts, fallback=fallback)

    # ------------------------------------------------------------------ manager
    async def plan(self, client: Client, report: ScoutingReport) -> tuple[list[CandidateResult], Plan, str, bool]:
        self._actor = "manager"
        await self.call(client, "get_squad_condition", {"minute": 0})
        claims = self.claims()
        payload = {"team": self.team, "opponent": self.opp, "report": report.model_dump(mode="json"),
                   "claims": [c.model_dump(mode="json") for c in claims.values()]}
        prompt = f"Prepare {self.team}'s plan against {self.opp}.\n" + _block(payload)
        instructions = MANAGER_INSTRUCTIONS.format(team=self.team, opp=self.opp)
        drafts = (await self.ask("manager", instructions, prompt, CandidateSetDraft, client)).candidates
        results: list[CandidateResult] = []
        for i, draft in enumerate(drafts[:3]):
            results.append(await self._validate_with_revisions(client, i, draft, claims, payload, instructions))
        valid = [r for r in results if r.valid]
        used_template = not valid
        if used_template:
            tpl = self._template_plan()
            check = await self.call(client, "validate_plan", {"plan": tpl.model_dump(mode="json", by_alias=True)})
            if not check["ok"]:
                raise RuntimeError(f"template plan does not validate: {check['errors']}")
            valid = [CandidateResult(plan=tpl, rationale="", validation=[[]], valid=True)]
            results.append(valid[0])
        for r in valid:
            vals = await self.call(client, "simulate_plan", {"plan": r.plan.model_dump(mode="json", by_alias=True),
                                                             "opponent_estimate": report.opponent_plan_estimate
                                                             .model_dump(mode="json"), "R": 500})
            r.valuation_claims = [v["claim_id"] for v in vals] if isinstance(vals, list) else []
        chosen, reason = self._choose(valid, self.claims())
        final = chosen.plan.model_copy(deep=True)
        final.plan_id = f"{self.team}-A"
        final.valuation = chosen.valuation_claims[0] if chosen.valuation_claims else None
        check = await self.call(client, "validate_plan", {"plan": final.model_dump(mode="json", by_alias=True)})
        if not check["ok"]:
            raise RuntimeError(f"chosen plan stopped validating: {check['errors']}")
        final.sealed = Seal(at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), sha256=plan_digest(final))
        assert verify_plan(final)
        cited = list(dict.fromkeys(c for cs in final.lever_evidence.values() for c in cs))
        self._step("manager", None, {"action": "seal", "plan_id": final.plan_id}, cited, 0, "ok",
                   f"sealed sha256 {final.sealed.sha256[:12]}")
        return results, final, reason, used_template

    async def _validate_with_revisions(self, client: Client, i: int, draft: CandidateDraft, claims: dict,
                                       payload: dict, instructions: str) -> CandidateResult:
        history: list[list[str]] = []
        for attempt in range(MAX_REVISIONS + 1):
            plan, rationale_errors = self._to_plan(i, draft, claims)
            check = await self.call(client, "validate_plan", {"plan": plan.model_dump(mode="json", by_alias=True)})
            errors = list(check.get("errors", [])) + rationale_errors
            history.append(errors)
            if not errors:
                return CandidateResult(plan=plan, rationale=draft.rationale, validation=history, valid=True)
            if attempt == MAX_REVISIONS:
                break
            self.trace[-1] = self.trace[-1].model_copy(update={"status": "rejected",
                                                               "message": "; ".join(errors)[:300]})
            revise = {**payload, "candidates": [draft.model_dump(mode="json")], "errors": errors}
            prompt = "Revise this candidate.\nVALIDATION ERRORS:\n" + "\n".join(errors) + "\n" + _block(revise)
            revised = (await self.ask("manager", instructions, prompt, CandidateSetDraft, client)).candidates
            if not revised:
                break
            draft = revised[0]
            self.trace[-1] = self.trace[-1].model_copy(update={"status": "retried"})
        return CandidateResult(plan=plan, rationale=draft.rationale, validation=history, valid=False)

    def _to_plan(self, i: int, d: CandidateDraft, claims: dict[str, Claim]) -> tuple[Plan, list[str]]:
        plan = Plan(plan_id=f"{self.team}-cand-{i + 1}", team=self.team, opponent=self.opp,
                    name=I18nText(en=d.name_en, es=d.name_es),
                    levers=Levers(press_height=d.press_height, press_target=d.press_target, build_up=d.build_up,
                                  attack_channel=d.attack_channel, corner_delivery=d.corner_delivery),
                    lever_evidence=d.lever_evidence, kpis=d.kpis, plan_b=d.plan_b)
        errors = [f"rationale: {e}" for e in tv.verify(d.rationale, claims)] if d.rationale.strip() else []
        return plan, errors

    def _choose(self, valid: list[CandidateResult], claims: dict[str, Claim]) -> tuple[CandidateResult, str]:
        """Highest simulated value; ties broken by the amount of evidence. Values come from claims only."""
        def value(r: CandidateResult) -> float:
            vs = [claims[c].value for c in r.valuation_claims if c in claims]
            return float(vs[0]) if vs and isinstance(vs[0], (int, float)) else float("-inf")

        def evidence(r: CandidateResult) -> int:
            return sum(len(v) for v in r.plan.lever_evidence.values())

        best = max(valid, key=lambda r: (value(r), evidence(r)))
        tied = [r for r in valid if value(r) == value(best)]
        reason = ("highest simulated value" if len(tied) == 1 else
                  "simulated values tie (the mock engine returns one valuation); chose the plan with more evidence")
        return best, reason

    def _template_plan(self) -> Plan:
        return Plan(plan_id=f"{self.team}-template", team=self.team, opponent=self.opp,
                    name=I18nText(en="Balanced default plan", es="Plan equilibrado por defecto"), levers=Levers(),
                    kpis=[Kpi(id="k1", metric="balls_in_behind_conceded", target="<=3", by_minute=90)])


def _confidence(c: Claim) -> str:
    if c.status == "insufficient" or (c.n is not None and c.n < 15):
        return "insufficient"
    if c.n is not None and c.n >= 60:
        return "high"
    return "medium" if (c.n or 0) >= 30 else "low"


def _template_scouting(claims: dict[str, Claim]) -> ScoutingDraft:
    from .models import FindingDraft, LeverGuess
    tendencies = [c for c in claims.values() if c.type == "observed_tendency" and c.n is not None][:5]
    findings = [FindingDraft(claim_id=c.claim_id,
                             headline=f"Observed {c.metric.replace('_', ' ')}: {{{c.claim_id}.value}}"
                                      f" (n {{{c.claim_id}.n}}), which may be noise.")
                for c in tendencies]
    return ScoutingDraft(findings=findings, opponent_levers=LeverGuess(), opponent_confidence="low")


# ---------------------------------------------------------------------------- orchestration
async def run_staff(engine: EngineAPI, team: str, home: str, away: str, choice: ModelChoice) -> PrematchResult:
    staff = Staff(engine, team, home, away, choice)
    try:
        async with Client(staff.server) as client:
            report = await staff.scout(client)
            candidates, chosen, reason, used_template = await staff.plan(client, report)
    finally:
        await staff.chat.aclose()
    return PrematchResult(team=team, opponent=staff.opp, report=report, candidates=candidates, chosen=chosen,
                          chosen_reason=reason, used_template=used_template, traces=staff.trace,
                          model=f"{choice.analyst}/{choice.manager}")


async def run_prematch(engine: EngineAPI, home: str, away: str, mode: str | None = None) -> dict[str, PrematchResult]:
    """Both staffs concurrently, each isolated in its own scope."""
    choice = model_choice(mode)  # type: ignore[arg-type]
    kes, har = await asyncio.gather(run_staff(engine, home, home, away, choice),
                                    run_staff(engine, away, home, away, choice))
    return {home: kes, away: har}


def engine_meta(engine) -> tuple[str, str]:
    meta = getattr(engine, "meta", None) or engine.bundle.meta
    return meta.home, meta.away


def main(argv: list[str] | None = None) -> int:
    from agents.settings import load_env
    from mcp_server.engine_factory import get_engine
    load_env()
    ap = argparse.ArgumentParser(prog="python -m agents.prematch")
    ap.add_argument("--mode", choices=["offline", "foundry"], default=None)
    ap.add_argument("--out", default=str(Path(__file__).parent / "_out" / "prematch.json"))
    args = ap.parse_args(argv)
    engine = get_engine()
    home, away = engine_meta(engine)
    results = asyncio.run(run_prematch(engine, home, away, args.mode))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({t: r.model_dump(mode="json", by_alias=True) for t, r in results.items()}, indent=1,
                              ensure_ascii=False))
    for t, r in results.items():
        print(f"{t}: {len(r.report.findings)} findings · plan '{r.chosen.name.en}' · levers "
              f"{r.chosen.levers.model_dump(exclude_defaults=True)} · sealed {r.chosen.sealed.sha256[:12]} · "
              f"{len(r.traces)} trace steps · template={r.used_template}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
