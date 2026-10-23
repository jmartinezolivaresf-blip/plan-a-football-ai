"""Integration: season -> RealEngine -> MCP scopes -> agents -> duel -> bundle (offline rules client, no Azure)."""

from __future__ import annotations

import json
import re

import pytest

from agents.validators import text as tv
from contracts import MatchBundle
from contracts.engine_api import EngineAPI
from contracts.eval_only import TRAIT_KINDS
from contracts.sealing import verify_choice, verify_plan
from engine import duel as dm
from mcp_server.policy import ScopedTools
from pipeline.build import build, make_engine, run_prematch_for
from sim.season import build_season

PLACEHOLDER = re.compile(r"\{(c[\w-]+)\.(\w+)\}")


@pytest.fixture(scope="session")
def season():
    return build_season(2026)


@pytest.fixture(scope="session")
def built(season):
    # the path used by the seed search and the evaluation: pre-match computed once by another engine, then replayed
    return build(season=season, match_seed=202, prematch=run_prematch_for(season, "KES", "HAR", None))


@pytest.fixture(scope="session")
def bundle(built) -> MatchBundle:
    return built.bundle


def test_real_engine_implements_the_protocol(season):
    from engine.api import Seeds
    assert isinstance(make_engine(season, "KES", "HAR", Seeds()), EngineAPI)


def test_scouting_claims_are_observed_and_complete(season):
    from engine.api import Seeds
    e = make_engine(season, "KES", "HAR", Seeds())
    claims = e.get_team_tendencies("HAR", "all")
    assert claims and all(c.type == "observed_tendency" and c.n is not None and c.status in ("sufficient",
                                                                                             "insufficient")
                          for c in claims)
    assert all(c.league_ref is not None for c in claims)
    blob = json.dumps([c.model_dump() for c in claims])
    for kind in TRAIT_KINDS:
        assert kind not in blob


def test_scouting_sees_harbourside_short_goal_kicks(season):
    from engine.api import Seeds
    e = make_engine(season, "KES", "HAR", Seeds())
    gk = e.get_team_tendencies("HAR", "build_up")[0]
    assert gk.value / gk.league_ref > 1.3  # HAR has a hidden gk_short_bias; scouting only sees the deviation


def test_bundle_is_valid_and_real(bundle):
    assert not bundle.illustrative and bundle.meta.precomputed
    MatchBundle.model_validate(bundle.model_dump(mode="json", by_alias=True))
    assert len(bundle.snapshots) == 91 and bundle.events[-1].minute >= 85
    goals = {t: 0 for t in bundle.plans}
    for e in bundle.events:
        if e.type == "goal":
            goals[e.team] += 1
    assert bundle.snapshots[-1].score == goals


def test_plans_are_sealed_and_justified(bundle):
    claims = {c.claim_id for c in bundle.claims}
    for plan in bundle.plans.values():
        assert verify_plan(plan)
        for ids in plan.lever_evidence.values():
            assert ids and set(ids) <= claims
        assert plan.valuation in claims


def test_duel_separation_and_seals(bundle):
    duel = bundle.duel
    true_id = duel.broadcast.true_matrix.matrix_id
    for team, priv in duel.private.items():
        opp = next(t for t in duel.private if t != team)
        blob = json.dumps(priv.model_dump(mode="json"))
        assert true_id not in blob and '"kind": "true"' not in blob
        for o in duel.private[opp].options:
            assert o.option_id not in blob
        r = duel.broadcast.revealed[team]
        assert verify_choice(priv.choice.sha256, duel.match_id, team, r.option_id, r.salt)
        assert r.option_id in [o.option_id for o in priv.options]
        assert priv.options[0].intent == "stay_the_course"


def test_regret_matches_the_true_matrix(bundle):
    b = bundle.duel.broadcast
    for team, rg in b.regret.items():
        best, value = dm.regret(b.true_matrix, team, rg.chosen, rg.opponent_chosen)
        assert rg.best_response == best and abs(rg.regret_xpts - round(value, 3)) < 1e-9 and rg.regret_xpts >= 0


def test_true_matrix_uses_the_real_options(bundle):
    m = bundle.duel.broadcast.true_matrix
    assert m.rows == [o.option_id for o in bundle.duel.private[m.row_team].options]
    assert m.cols == [o.option_id for o in bundle.duel.private[m.col_team].options]


def test_every_cue_verifies_and_resolves(bundle):
    assert bundle.eval["cues_dropped_by_verifier"] == 0, bundle.eval["cues_dropped_detail"]
    claims = {c.claim_id: c for c in bundle.claims}
    for cue in bundle.cues:
        for text in (cue.text.en, cue.text.es):
            assert tv.verify(text, claims) == [], (cue.cue_id, text)
            assert all(cid in claims for cid, _ in PLACEHOLDER.findall(text))


def test_snapshots_carry_kpis_and_engine_condition(bundle):
    mid = bundle.snapshots[30]
    assert mid.kpis and all(k.claim_id for k in mid.kpis)
    assert mid.condition_est and all(0 <= v <= 1 for v in mid.condition_est.values())


def test_traces_cover_both_workflows_and_scopes(bundle):
    flows = {t.workflow for t in bundle.traces}
    assert {"prematch", "duel"} <= flows
    assert {t.scope for t in bundle.traces} == set(bundle.plans)
    assert not any(t.tool == "get_true_matrix" for t in bundle.traces if t.scope != "broadcast")


def test_no_hidden_truth_anywhere_in_the_bundle(bundle):
    blob = bundle.model_dump_json(exclude={"eval"})
    for kind in TRAIT_KINDS:
        assert kind not in blob
    assert '"archetype"' not in blob
    # the validation panel may name trait kinds in aggregate tables of OTHER (evaluation) seasons, never per-team truth
    panel = json.dumps(bundle.eval)
    assert '"truth"' not in panel and '"reports"' not in panel and "eval_only" not in panel


def test_mcp_on_the_real_engine_isolates_benches(season):
    from engine.api import Seeds
    e = make_engine(season, "KES", "HAR", Seeds(match=202))
    kes = ScopedTools(engine=e, scope="KES", home="KES", away="HAR", match_id=e.match_id, visible_minute=0)
    har = ScopedTools(engine=e, scope="HAR", home="KES", away="HAR", match_id=e.match_id, visible_minute=0)
    bc = ScopedTools(engine=e, scope="broadcast", home="KES", away="HAR", match_id=e.match_id, visible_minute=90)
    assert kes.call("price_matrix", {"own_options": [], "opponent_options": [], "opponent_probs": []})["error"] in (
        "not_ready", "invalid_args")
    assert bc.call("get_true_matrix", {})["error"] == "not_sealed_yet"
    assert kes.call("get_true_matrix", {})["error"] == "forbidden_scope"
    assert kes.call("get_events", {"filter": {}}) == []
    claims = kes.call("get_team_tendencies", {"team": "HAR"})
    assert claims and not any("error" in c for c in claims if isinstance(c, dict))
    assert har.call("get_squad_condition", {"minute": 0, "team": "KES"})["error"] == "invalid_args"
    assert har.call("get_squad_condition", {"minute": 0})["squad"]["team"] == "HAR"


def _digest(bundle: MatchBundle) -> str:
    import hashlib
    # Excluded: wall-clock data (trace durations, build time, when each plan was sealed; the plan hash does not
    # cover that timestamp) and the half-time commit-reveal, whose salt is random by design (D-045).
    data = bundle.model_dump(mode="json", by_alias=True, exclude={"traces", "eval"})
    for plan in data["plans"].values():
        plan["sealed"]["at"] = None
    for team in data["duel"]["private"]:
        data["duel"]["private"][team]["choice"]["sha256"] = None
        data["duel"]["broadcast"]["revealed"][team]["salt"] = None
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def test_bundle_does_not_depend_on_the_process_hash_seed(bundle):
    import os
    import subprocess
    import sys
    code = ("from pipeline.build import build; from tests.test_real_engine import _digest; "
            "print(_digest(build(match_seed=202).bundle))")
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == _digest(bundle)
