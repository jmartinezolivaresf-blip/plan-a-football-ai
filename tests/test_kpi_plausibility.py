"""KPI targets must be football-plausible (D-057).

Regression for the first real Foundry run (2026-10-26): a manager proposed "high_turnovers >=27.2 by 15'" and the
validators accepted it. Now: a count is a whole number, a share a fraction, set-piece xG continuous; a KPI is a minimum
for what the plan wants more of and a maximum for balls in behind conceded; and a target must lie within what teams
really reached by that minute in the league's public matches (the staffs' own evidence, never hidden or future data).
"""

from __future__ import annotations

import asyncio

import pytest
from agent_framework import BaseChatClient, ChatResponse, Message

from agents import prematch as pm
from agents.clients import ModelChoice
from agents.models import CandidateSetDraft, ScoutingDraft
from agents.offline import candidates as offline_candidates
from agents.offline import evidence as offline_evidence
from agents.offline import scouting as offline_scouting
from agents.validators.plan import validate_plan
from contracts import Kpi, MatchBundle
from engine.api import Seeds
from engine.tracker import kpi_plausibility
from mcp_server.policy import ScopedTools
from pipeline.build import make_engine
from sim.season import build_season

from .agent_helpers import plans, squads
from .conftest import ROOT

OFFLINE = ModelChoice("offline", "offline-rules", "offline-rules")


def _rule_errors(*targets: tuple[str, str, int]) -> list[str]:
    kpis = [Kpi(id=f"k{i}", metric=m, target=t, by_minute=b,
                params={"channel": "left"} if m == "final_third_entries_share" else {})
            for i, (m, t, b) in enumerate(targets)]
    return validate_plan(plans()["KES"].model_copy(update={"kpis": kpis, "plan_b": []}), squads().teams).errors


# ------------------------------------------------------------------ scale and direction (no data needed)
@pytest.mark.parametrize("metric,target,minute,message", [
    ("high_turnovers", ">=27.2", 15, "whole number"),            # a count is not fractional
    ("balls_in_behind_conceded", "<=3.5", 90, "whole number"),
    ("final_third_entries_share", "<=0.416", 15, "state a minimum"),  # capping what the plan wants more of
    ("set_piece_xg", "<0.3", 90, "state a minimum"),
    ("balls_in_behind_conceded", ">=10", 90, "state a maximum"),  # asking to concede more
    ("final_third_entries_share", ">=1.4", 90, "between 0 and 1"),
    ("high_turnovers", ">=0", 90, "positive"),
])
def test_targets_with_the_wrong_scale_or_direction_are_rejected(metric, target, minute, message):
    assert any(message in e for e in _rule_errors((metric, target, minute)))


@pytest.mark.parametrize("metric,target,minute", [
    ("high_turnovers", ">=6", 45), ("high_turnovers", ">4", 90), ("balls_in_behind_conceded", "<=14", 90),
    ("set_piece_xg", ">=0.35", 90),  # continuous: decimals are fine
    ("final_third_entries_share", ">=0.40", 90),
])
def test_well_formed_targets_pass_the_rules(metric, target, minute):
    assert _rule_errors((metric, target, minute)) == []


# ------------------------------------------------------------------ range by minute (observed league values)
@pytest.mark.parametrize("metric,target,minute,values,ok", [
    ("high_turnovers", ">=27", 15, [0, 1, 1, 2, 6], False),   # the league maximum by 15' is 6
    ("high_turnovers", ">=6", 15, [0, 1, 1, 2, 6], True),     # ambitious, but a team did it
    ("high_turnovers", ">6", 15, [0, 1, 1, 2, 6], False),
    ("balls_in_behind_conceded", "<=3", 90, [4, 12, 17, 25, 34], False),  # nobody conceded fewer than 4
    ("balls_in_behind_conceded", "<4", 90, [4, 12, 17, 25, 34], False),
    ("balls_in_behind_conceded", "<=4", 90, [4, 12, 17, 25, 34], True),
    ("set_piece_xg", ">=0.5", 15, [0.0, 0.0, 0.05, 0.26], False),
    ("set_piece_xg", ">=0.3", 90, [0.0, 0.2, 0.26, 0.79], True),
    ("final_third_entries_share", ">=0.75", 90, [0.07, 0.28, 0.61], False),
])
def test_targets_must_lie_within_what_teams_reached_by_that_minute(metric, target, minute, values, ok):
    kpi = Kpi(id="k1", metric=metric, target=target, by_minute=minute,
              params={"channel": "left"} if metric == "final_third_entries_share" else {})
    message = kpi_plausibility(kpi, [float(v) for v in values])
    assert (message is None) == ok, message
    if not ok:
        assert f"by minute {minute}" in message and "Use a target" in message  # concrete feedback for the manager


# ------------------------------------------------------------------ the real engine, on the demo season
@pytest.fixture(scope="module")
def engine():
    return make_engine(build_season(2026), "KES", "HAR", Seeds(match=204))


def _tool(engine) -> ScopedTools:
    return ScopedTools(engine=engine, scope="KES", home="KES", away="HAR", match_id=engine.match_id, visible_minute=0)


def test_the_engine_uses_only_the_leagues_public_matches(engine):
    ids = {m.match_id for m in engine.matches}
    assert ids and engine.match_id not in ids  # no future: the match being planned is not in the league data


def test_the_demo_plans_and_the_template_are_plausible(engine):
    demo = MatchBundle.model_validate_json((ROOT / "web" / "public" / "match_bundle.json").read_text())
    for plan in demo.plans.values():
        assert engine.validate_plan(plan).ok, plan.plan_id
    staff = pm.Staff(engine, "KES", "KES", "HAR", OFFLINE)
    assert engine.validate_plan(staff._template_plan()).ok


def test_the_foundry_case_is_rejected_with_the_leagues_range(engine):
    plan = plans()["KES"].model_copy(update={"plan_b": [], "kpis": [
        Kpi(id="k1", metric="high_turnovers", target=">=27.2", by_minute=15)]})  # the real run's target
    errors = engine.validate_plan(plan).errors
    assert len(errors) == 1 and "no team had more than" in errors[0] and "by minute 15" in errors[0]
    res = _tool(engine).call("validate_plan", {"plan": plan.model_dump(mode="json", by_alias=True)})
    assert not res["ok"] and any("whole number" in e for e in res["errors"]) and errors[0] in res["errors"]


# ------------------------------------------------------------------ the manager corrects, or the fallback is valid
class _Manager(BaseChatClient):
    """Offline answers, except that the manager's first `bad_rounds` drafts add an implausible KPI."""

    def __init__(self, bad_rounds: int, only_bad: bool = False):
        super().__init__()
        self.bad_rounds, self.only_bad, self.calls, self.errors_seen = bad_rounds, only_bad, 0, []

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        fmt = options.get("response_format")
        ev = offline_evidence(messages)
        if fmt is ScoutingDraft:
            out = offline_scouting(ev)
        else:
            self.calls += 1
            self.errors_seen += ev.get("errors", [])
            drafts = offline_candidates(ev).candidates[:1]
            if self.calls <= self.bad_rounds:
                d = drafts[0].model_dump()
                bad = {"id": "kx", "metric": "high_turnovers", "target": ">=27", "by_minute": 15}
                d["kpis"] = [bad] if self.only_bad else d["kpis"] + [bad]
                d["plan_b"] = [] if self.only_bad else d["plan_b"]
                out = CandidateSetDraft.model_validate({"candidates": [d]})
            else:
                out = CandidateSetDraft(candidates=drafts)
        return ChatResponse(messages=[Message(role="assistant", contents=[out.model_dump_json()])])


def _staff(monkeypatch, engine, manager):
    monkeypatch.setattr(pm.ChatClients, "_make", lambda self, role: manager)
    return asyncio.run(pm.run_staff(engine, "KES", "KES", "HAR", OFFLINE))


def test_the_manager_gets_the_range_and_corrects_the_target(monkeypatch, engine):
    manager = _Manager(bad_rounds=1)
    r = _staff(monkeypatch, engine, manager)
    assert manager.calls == 2 and any("no team had more than" in e for e in manager.errors_seen)
    assert r.candidates[0].valid and not r.used_template
    assert all(k.id != "kx" for k in r.chosen.kpis) and engine.validate_plan(r.chosen).ok


def test_after_the_last_revision_only_the_failing_kpi_is_dropped(monkeypatch, engine):
    manager = _Manager(bad_rounds=99)
    r = _staff(monkeypatch, engine, manager)
    assert manager.calls == 1 + pm.MAX_REVISIONS  # the existing revision limit, no extra model calls
    assert r.candidates[0].valid and not r.used_template
    assert "kx" not in {k.id for k in r.chosen.kpis} and len(r.chosen.kpis) >= 1 and engine.validate_plan(r.chosen).ok
    assert any(t.args.get("action") == "drop_kpis" for t in r.traces)


def test_a_plan_with_no_plausible_kpi_falls_back_to_the_valid_template(monkeypatch, engine):
    r = _staff(monkeypatch, engine, _Manager(bad_rounds=99, only_bad=True))
    assert r.used_template and engine.validate_plan(r.chosen).ok
    assert [(k.metric, k.target, k.by_minute) for k in r.chosen.kpis] == [("balls_in_behind_conceded", "<=14", 90)]
