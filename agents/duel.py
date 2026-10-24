"""WF-Duelo: both benches decide at half-time, blind to each other, then a barrier, the reveal and the true matrix.

Per bench (own scoped MCP server, visible minute 45): read own KPIs -> manager proposes 3 options (Stay first) ->
validate -> analyst's estimate of the opponent -> believed matrix -> choose by an explicit rule -> seal.
Barrier: the broadcast scope may read the true matrix only after both seals.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import Client
from pydantic import BaseModel, ConfigDict, Field

from contracts import (
    BROADCAST_SCOPE,
    Claim,
    DuelBroadcast,
    I18nText,
    LeverChanges,
    Matrix,
    OpponentOptionsEstimate,
    Option,
    SealedChoice,
    Sub,
    TeamDuelPrivate,
)
from contracts.engine_api import EngineAPI
from contracts.option import Intent
from mcp_server.policy import ScopedTools
from mcp_server.server import build_server

from .clients import ModelChoice, model_choice
from .prematch import Staff, _block

MAX_REVISIONS = 2
ATTACK_ROLES = ("RW", "LW", "ST", "AM")


class OptionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str
    label_en: str
    label_es: str
    intent: Intent
    lever_changes: LeverChanges = Field(default_factory=LeverChanges)
    subs: list[Sub] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class OptionsDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    options: list[OptionDraft] = Field(min_length=3, max_length=3)


MANAGER_DUEL_INSTRUCTIONS = """You are the manager of {team} at half-time against {opp}. Propose exactly 3 options: the
first is "Stay the course" (no changes); the other two change levers (press_height, press_target, build_up,
attack_channel, corner_delivery) and/or make up to 3 substitutions (window "HT"). Cite claim_ids in evidence. Use only
players on the pitch for `out` and unused bench players for `in`. Never write numbers in labels."""


def offline_options(ev: dict[str, Any]) -> OptionsDraft:
    """Deterministic half-time options from the bench's situation (used by the offline rules client)."""
    team, diff = ev["team"], ev["score_diff"]
    statuses = {k["metric"]: k["label"] for k in ev["kpis"]}
    levers = ev["levers"]
    stay = OptionDraft(option_id=f"{team}-HT-A", label_en="Stay the course", label_es="Mantener el plan",
                       intent="stay_the_course")
    press_struggling = statuses.get("high_turnovers") in ("at_risk", "failing")
    out: list[OptionDraft] = [stay]
    if diff < 0:
        subs = [Sub(window="HT", out=o, into=i) for o, i in zip(ev["tired_attackers"], ev["bench_attackers"],
                                                                 strict=False)][:2]
        out.append(OptionDraft(option_id=f"{team}-HT-B", label_en="Fresh legs up front",
                               label_es="Piernas frescas arriba", intent="attacking_subs", subs=subs,
                               lever_changes=LeverChanges(attack_channel="balanced"), evidence=ev["kpi_claims"]))
    elif diff > 0:
        out.append(OptionDraft(option_id=f"{team}-HT-B", label_en="Protect the lead", label_es="Proteger la ventaja",
                               intent="protect_lead", lever_changes=LeverChanges(press_height="low"),
                               evidence=ev["kpi_claims"]))
    else:
        if levers["press_height"] == "high":
            out.append(OptionDraft(option_id=f"{team}-HT-B", label_en="Drop into a mid block",
                                   label_es="Bajar a bloque medio", intent="drop_block",
                                   lever_changes=LeverChanges(press_height="mid"), evidence=ev["kpi_claims"]))
        else:
            out.append(OptionDraft(option_id=f"{team}-HT-B", label_en="Press higher", label_es="Presionar más arriba",
                                   intent="press_higher", lever_changes=LeverChanges(press_height="high"),
                                   evidence=ev["kpi_claims"]))
    if press_struggling and levers["press_height"] == "high" and out[1].intent != "drop_block":
        third = OptionDraft(option_id=f"{team}-HT-C", label_en="Mid block, go direct",
                            label_es="Bloque medio y juego directo", intent="drop_block",
                            lever_changes=LeverChanges(press_height="mid", build_up="direct"),
                            evidence=ev["kpi_claims"])
    elif levers["build_up"] != "direct":
        third = OptionDraft(option_id=f"{team}-HT-C", label_en="Go direct", label_es="Jugar directo",
                            intent="go_direct", lever_changes=LeverChanges(build_up="direct"),
                            evidence=ev["kpi_claims"])
    else:
        third = OptionDraft(option_id=f"{team}-HT-C", label_en="Back to short passing",
                            label_es="Volver al juego corto", intent="short_build_up",
                            lever_changes=LeverChanges(build_up="short"), evidence=ev["kpi_claims"])
    out.append(third)
    return OptionsDraft(options=out)


def choose_rule(score_diff: int) -> str:
    """Explicit decision rule: protect a lead with the safe pick, otherwise play the best expected value."""
    return "safe_pick" if score_diff > 0 else "best_guess"


class DuelBench:
    """One bench at half-time. It only sees the match through its own scoped MCP tools and its own sealed plan."""

    def __init__(self, engine: EngineAPI, team: str, home: str, away: str, choice: ModelChoice, plan):
        self.staff = Staff(engine, team, home, away, choice, visible_minute=45, workflow="duel")
        self.team, self.opp, self.plan = team, self.staff.opp, plan
        self.options: list[Option] = []
        self.estimate: OpponentOptionsEstimate | None = None
        self.matrix: Matrix | None = None
        self.sealed: SealedChoice | None = None
        self.rule = "best_guess"
        self.validation: list[list[str]] = []

    async def decide(self) -> TeamDuelPrivate:
        try:
            return await self._decide()
        finally:
            await self.staff.chat.aclose()

    async def _decide(self) -> TeamDuelPrivate:
        s = self.staff
        async with Client(s.server) as client:
            s._actor = "analyst"
            state = await s.call(client, "get_squad_condition", {"minute": 45})
            kpis = await s.call(client, "get_plan_status", {"minute": 45})
            goals = await s.call(client, "get_events", {"filter": {"type": "goal"}})
            s._actor = "manager"
            diff = sum(1 if g["team"] == self.team else -1 for g in goals)
            ev = self._evidence(state, kpis, diff)
            drafts = await self._options(client, ev)
            self.options = await self._validated(client, drafts, ev)
            s._actor = "analyst"
            est = await s.call(client, "estimate_opponent_options", {})
            self.estimate = OpponentOptionsEstimate.model_validate(est)
            for cid in self.estimate.claims:
                await s.call(client, "get_claim", {"claim_id": cid})
            s._actor = "manager"
            matrix = await s.call(client, "price_matrix", {
                "own_options": [o.model_dump(mode="json") for o in self.options],
                "opponent_options": [o.option.model_dump(mode="json") for o in self.estimate.options],
                "opponent_probs": [o.probability for o in self.estimate.options], "R": 300})
            if "error" in matrix:
                raise RuntimeError(f"price_matrix failed: {matrix}")
            self.matrix = Matrix.model_validate(matrix)
            self.rule = choose_rule(diff)
            reading = self.matrix.readings[self.team]
            pick = {"safe_pick": reading.safe_pick, "best_guess": reading.best_guess, "gamble": reading.gamble}[
                self.rule] or reading.safe_pick
            sealed = await s.call(client, "seal_choice", {"option_id": pick, "rule": self.rule})
            if "error" in sealed:
                raise RuntimeError(f"seal_choice failed: {sealed}")
            self.sealed = SealedChoice.model_validate(sealed)
            s._step("manager", None, {"action": "seal_choice", "rule": self.rule}, [self.matrix.cells[0][0].claim_id],
                    0, "ok", f"sealed sha256 {self.sealed.sha256[:12]}")
        return TeamDuelPrivate(team=self.team, options=self.options, opponent_estimate=self.estimate,
                               believed_matrix=self.matrix, choice=self.sealed)

    def _evidence(self, state: dict, kpis: list, diff: int) -> dict[str, Any]:
        cond = {c["player_id"]: c["value"] for c in state["condition"]}  # players on the pitch now
        on = set(cond)
        squad = {p["player_id"]: p for p in state["squad"]["players"]}
        planned_in = {s.into for s in self.plan.subs_plan}
        # ties in condition break by player id, never by set order (which changes with PYTHONHASHSEED)
        attackers_on = sorted((p for p in on if squad[p]["position"] in ATTACK_ROLES),
                              key=lambda p: (cond.get(p, 1.0), p))
        bench = [p for p, d in squad.items() if p not in on and not d["starter"] and p not in planned_in
                 and d["position"] in ATTACK_ROLES]
        # options change the levers in force at half-time (after a Plan B), not the ones sealed before kick-off
        levers = state.get("levers") or self.plan.levers.model_dump()
        return {"team": self.team, "opponent": self.opp, "score_diff": diff, "kpis": kpis,
                "kpi_claims": [k["claim_id"] for k in kpis][:2], "levers": levers,
                "tired_attackers": attackers_on[:2], "bench_attackers": bench[:2], "on_pitch": sorted(on)}

    async def _options(self, client: Client, ev: dict) -> list[OptionDraft]:
        s = self.staff
        if s.choice.mode == "offline":
            s._step("manager", None, {"response_format": "OptionsDraft"}, [], 0, "ok", f"model:{s.choice.manager}")
            return offline_options(ev).options
        prompt = f"Half-time options for {self.team}.\n" + _block(ev)
        out = await s.ask("manager", MANAGER_DUEL_INSTRUCTIONS.format(team=self.team, opp=self.opp), prompt,
                          OptionsDraft, client)
        return out.options

    async def _validated(self, client: Client, drafts: list[OptionDraft], ev: dict) -> list[Option]:
        options = []
        for d in drafts:
            opt = Option(option_id=d.option_id, team=self.team, label=I18nText(en=d.label_en, es=d.label_es),
                         intent=d.intent, lever_changes=d.lever_changes, subs=d.subs, evidence=d.evidence)
            for attempt in range(MAX_REVISIONS + 1):
                res = await self.staff.call(client, "validate_plan", {"option": opt.model_dump(mode="json")})
                self.validation.append(res.get("errors", []))
                if res.get("ok"):
                    break
                # deterministic repair: drop invalid substitutions, keep the lever changes
                self.staff.trace[-1] = self.staff.trace[-1].model_copy(update={
                    "status": "rejected", "message": "; ".join(res.get("errors", []))[:300]})
                opt = opt.model_copy(update={"subs": []})
                if attempt == MAX_REVISIONS:
                    opt = opt.model_copy(update={"subs": [], "lever_changes": LeverChanges()})
            options.append(opt)
        return options


async def run_duel(engine: EngineAPI, home: str, away: str, plans: dict, mode: str | None = None) -> tuple[
        dict, DuelBroadcast, list]:
    """Both benches concurrently (blind), barrier, then the broadcast reveal."""
    choice = model_choice(mode)  # type: ignore[arg-type]
    benches = {t: DuelBench(engine, t, home, away, choice, plans[t]) for t in (home, away)}
    privates = dict(zip(benches, await asyncio.gather(*(b.decide() for b in benches.values())), strict=True))
    bc = ScopedTools(engine=engine, scope=BROADCAST_SCOPE, home=home, away=away,
                     match_id=benches[home].staff.tools.match_id, visible_minute=45)
    async with Client(build_server(bc)) as client:
        r = await client.call_tool("get_true_matrix", {})
        payload = json.loads(r.content[0].text)
    if "error" in payload:
        raise RuntimeError(f"true matrix not available: {payload}")
    traces = [t for b in benches.values() for t in b.staff.trace]
    return privates, DuelBroadcast.model_validate(payload), traces


def claims_of(engine: EngineAPI, ids: list[str]) -> list[Claim]:
    out = []
    for cid in dict.fromkeys(ids):
        try:
            out.append(engine.get_claim(cid))
        except KeyError:
            continue
    return out
