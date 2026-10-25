"""Pre-match workflow with the offline rules client (no Azure): reports, plans, revisions, fallback, seals, traces."""

from __future__ import annotations

import asyncio
import json

from agent_framework import BaseChatClient, ChatResponse, Message

from agents import prematch as pm
from agents.clients import ModelChoice
from agents.models import CandidateSetDraft, PrematchResult, ScoutingDraft
from agents.offline import candidates as offline_candidates
from agents.offline import evidence as offline_evidence
from agents.offline import scouting as offline_scouting
from agents.validators import text as tv
from agents.validators.plan import non_default_levers, validate_plan
from contracts import Plan, TraceStep
from contracts.eval_only import TRAIT_KINDS
from contracts.sealing import verify_plan
from mcp_server.mock_engine import MockEngine

from .agent_helpers import squads

OFFLINE = ModelChoice("offline", "offline-rules", "offline-rules")


def _run(choice=OFFLINE) -> dict[str, PrematchResult]:
    return asyncio.run(pm.run_prematch(MockEngine(), "KES", "HAR", mode=choice.mode)) if choice is OFFLINE else \
        asyncio.run(_with_choice(choice))


async def _with_choice(choice):
    engine = MockEngine()
    kes, har = await asyncio.gather(pm.run_staff(engine, "KES", "KES", "HAR", choice),
                                    pm.run_staff(engine, "HAR", "KES", "HAR", choice))
    return {"KES": kes, "HAR": har}


def test_both_staffs_produce_reports_and_sealed_valid_plans():
    res = _run()
    for team, r in res.items():
        assert r.team == team and r.opponent != team
        assert 1 <= len(r.report.findings) <= 5 and not r.report.fallback
        plan = Plan.model_validate(r.chosen.model_dump(mode="json", by_alias=True))
        assert plan.team == team and plan.sealed is not None and verify_plan(plan)
        assert validate_plan(plan, squads().teams).ok
        for lever in non_default_levers(plan):
            assert plan.lever_evidence.get(lever), lever
        assert all(TraceStep.model_validate(t.model_dump()) for t in r.traces)
        assert {t.scope for t in r.traces} == {team}


def test_report_numbers_come_from_claims_only():
    res = _run()
    engine = MockEngine()
    for r in res.values():
        for f in r.report.findings:
            claim = engine.get_claim(f.claim_id)
            assert f.value == claim.value and f.n == claim.n and f.league_ref == claim.league_ref
            assert tv.verify(f.headline, {claim.claim_id: claim}) == []


def test_kes_plan_exploits_what_its_analyst_found():
    kes = _run()["KES"].chosen
    assert kes.levers.press_target == "HAR-5" and kes.levers.press_height == "high"
    assert kes.levers.attack_channel == "right" and kes.levers.corner_delivery == "far_post"
    assert kes.lever_evidence["press_target"] == ["c_sc_03"]


def test_evidence_cited_was_served_to_that_staff_only():
    res = _run()
    for team, r in res.items():
        served = {c for t in r.traces for c in t.result_claims}
        cited = {c for cs in r.chosen.lever_evidence.values() for c in cs}
        assert cited <= served
        opp_private = {"c_est_HAR", "c_sim_22"} if team == "KES" else {"c_est_KES", "c_sim_21"}
        assert not (served & opp_private)


def test_no_hidden_truth_or_rival_plan_in_outputs():
    res = _run()
    blob = json.dumps({t: r.model_dump(mode="json") for t, r in res.items()})
    for kind in TRAIT_KINDS:
        assert kind not in blob
    kes_blob = json.dumps(res["KES"].model_dump(mode="json"))
    assert res["HAR"].chosen.sealed.sha256 not in kes_blob


class _ScriptedClient(BaseChatClient):
    """Returns a wrong candidate first, then lets the offline rules answer (tests the revision loop)."""

    def __init__(self, bad_rounds: int):
        super().__init__()
        self.bad_rounds = bad_rounds
        self.manager_calls = 0

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        fmt = options.get("response_format")
        ev = offline_evidence(messages)
        if fmt is ScoutingDraft:
            out = offline_scouting(ev)
        else:
            self.manager_calls += 1
            if self.manager_calls <= self.bad_rounds:
                good = offline_candidates(ev).candidates[0].model_dump()
                good["lever_evidence"] = {}  # every changed lever loses its evidence -> invalid
                out = CandidateSetDraft.model_validate({"candidates": [good]})
            else:
                from agents.offline import revise
                out = revise(ev) if ev.get("errors") else offline_candidates(ev)
        return ChatResponse(messages=[Message(role="assistant", contents=[out.model_dump_json()])])


def _with_client(monkeypatch, client_factory):
    monkeypatch.setattr(pm.ChatClients, "_make", lambda self, role: client_factory())


def test_invalid_candidate_is_revised(monkeypatch):
    shared = _ScriptedClient(bad_rounds=1)
    _with_client(monkeypatch, lambda: shared)
    r = asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", OFFLINE))
    first = r.candidates[0]
    assert len(first.validation) == 2 and first.validation[0] and first.validation[1] == []
    assert first.valid and not r.used_template
    assert any(t.status == "retried" for t in r.traces)


def test_three_failures_fall_back_to_the_template(monkeypatch):
    shared = _ScriptedClient(bad_rounds=99)
    _with_client(monkeypatch, lambda: shared)
    r = asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", OFFLINE))
    assert r.used_template and r.chosen.plan_id == "KES-A"
    assert len(r.candidates[0].validation) == pm.MAX_REVISIONS + 1 and not r.candidates[0].valid
    assert non_default_levers(r.chosen) == [] and verify_plan(r.chosen)


def test_concurrent_staffs_do_not_share_state():
    res = _run()
    kes_tools = {t.tool for t in res["KES"].traces}
    assert "get_true_matrix" not in kes_tools
    assert res["KES"].chosen.sealed.sha256 != res["HAR"].chosen.sealed.sha256
