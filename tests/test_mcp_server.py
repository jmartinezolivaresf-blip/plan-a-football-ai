"""MCP server: registered tools per scope, contract-valid responses, isolation, anti-spoofing, gating."""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp import Client

from contracts import Claim, DuelBroadcast, Event, Matrix, OpponentOptionsEstimate, SealedChoice, Snapshot, Squad
from contracts.eval_only import TRAIT_KINDS
from contracts.refs import MatchRef, ValidationResult
from mcp_server.mock_engine import MockEngine
from mcp_server.policy import BROADCAST_TOOLS, STAFF_TOOLS, ScopedTools
from mcp_server.server import _loopback, build_server, main

MID = "m-demo-001"


def scoped(engine, scope, minute=None):
    visible = minute if minute is not None else (90 if scope == "broadcast" else 0)
    return ScopedTools(engine=engine, scope=scope, home="KES", away="HAR", match_id=MID, visible_minute=visible)


def run(coro):
    return asyncio.run(coro)


async def _call(tools: ScopedTools, name: str, args: dict):
    async with Client(build_server(tools)) as c:
        r = await c.call_tool(name, args)
        return r.is_error, (json.loads(r.content[0].text) if r.content and not r.is_error else r.content[0].text)


async def _list(tools: ScopedTools) -> set[str]:
    async with Client(build_server(tools)) as c:
        return {t.name for t in (await c.list_tools()).tools}


def test_tools_registered_per_scope():
    e = MockEngine()
    assert run(_list(scoped(e, "KES"))) == STAFF_TOOLS
    assert run(_list(scoped(e, "HAR"))) == STAFF_TOOLS
    assert run(_list(scoped(e, "broadcast"))) == BROADCAST_TOOLS
    assert "get_true_matrix" not in STAFF_TOOLS and "seal_choice" not in BROADCAST_TOOLS


def test_contract_tools_are_all_covered():
    contract_tools = {"list_matches", "get_team_tendencies", "get_player_profile", "get_set_piece_profile",
                      "get_squad_condition", "simulate_plan", "estimate_opponent_options", "price_matrix",
                      "validate_plan", "seal_choice", "get_plan_status", "get_match_state", "get_events",
                      "get_claim", "get_true_matrix"}
    assert STAFF_TOOLS | BROADCAST_TOOLS == contract_tools


def test_responses_validate_against_contracts():
    e = MockEngine()
    kes, bc = scoped(e, "KES"), scoped(e, "broadcast")
    _, refs = run(_call(kes, "list_matches", {"team": "HAR"}))
    assert [MatchRef.model_validate(r) for r in refs]
    _, claims = run(_call(kes, "get_team_tendencies", {"team": "HAR", "aspect": "all"}))
    assert claims and all(Claim.model_validate(c) for c in claims)
    _, single = run(_call(kes, "get_player_profile", {"player_id": "HAR-5"}))
    assert isinstance(single, list) and len(single) == 1  # one-item lists stay lists
    _, cond = run(_call(kes, "get_squad_condition", {"minute": 0}))
    assert Squad.model_validate(cond["squad"]).team == "KES"
    assert cond["levers"] == e.get_match_state(MID, 0).active_levers["KES"].model_dump(mode="json")
    _, est = run(_call(kes, "estimate_opponent_options", {}))
    assert OpponentOptionsEstimate.model_validate(est).estimator == "KES"
    _, snap = run(_call(bc, "get_match_state", {"minute": 45}))
    assert Snapshot.model_validate(snap).minute == 45
    _, evs = run(_call(bc, "get_events", {"filter": {"type": "goal"}}))
    assert len(evs) == 3 and all(Event.model_validate(x) for x in evs)


def test_own_levers_respect_the_time_gate():
    e = MockEngine()
    _, cond = run(_call(scoped(e, "KES", minute=10), "get_squad_condition", {"minute": 80}))
    assert cond["levers"] == e.get_match_state(MID, 10).active_levers["KES"].model_dump(mode="json")


def test_argument_validation():
    e = MockEngine()
    kes = scoped(e, "KES")
    is_err, _ = run(_call(kes, "get_player_profile", {}))
    assert is_err
    _, res = run(_call(kes, "validate_plan", {}))
    assert res["error"] == "invalid_args"
    _, res = run(_call(kes, "simulate_plan", {"plan": {"bad": 1}, "opponent_estimate": {}}))
    assert res["error"] == "invalid_args"


def test_staff_cannot_spoof_its_identity():
    e = MockEngine()
    kes = scoped(e, "KES")
    # extra "team" arguments are ignored: own-team tools have no team parameter
    _, cond = run(_call(kes, "get_squad_condition", {"minute": 0, "team": "HAR"}))
    assert cond["squad"]["team"] == "KES"
    assert all(c["player_id"].startswith("KES-") for c in cond["condition"])
    _, est = run(_call(kes, "estimate_opponent_options", {"team": "HAR"}))
    assert est["estimator"] == "KES"
    _, status = run(_call(kes, "get_plan_status", {"minute": 30, "team": "HAR"}))
    assert status["error"] == "forbidden_scope"
    har_plan = e.bundle.plans["HAR"].model_dump(mode="json", by_alias=True)
    _, res = run(_call(kes, "validate_plan", {"plan": har_plan}))
    assert res["error"] == "forbidden_scope"
    est_har = {"estimator": "HAR", "opponent": "KES", "levers": {}, "confidence": 0.5}
    _, res = run(_call(kes, "simulate_plan", {"plan": har_plan, "opponent_estimate": est_har}))
    assert res["error"] == "forbidden_scope"


def test_staff_cannot_read_the_rivals_private_duel_data():
    e = MockEngine()
    kes = scoped(e, "KES")
    _, m = run(_call(kes, "price_matrix", {"own_options": [], "opponent_options": [], "opponent_probs": []}))
    assert Matrix.model_validate(m).believer == "KES"
    har_real = e.bundle.duel.private["HAR"].options[0].model_dump(mode="json")
    _, res = run(_call(kes, "price_matrix", {"own_options": [], "opponent_options": [har_real],
                                             "opponent_probs": [1.0]}))
    assert res["error"] == "forbidden_scope"  # real (non-estimated) opponent options are refused
    for cid in ("cm_mx-believed-HAR_00", "cm_mx-true_00", "c_rg_HAR", "c_est_HAR", "c_sim_22"):
        _, res = run(_call(kes, "get_claim", {"claim_id": cid}))
        assert res["error"] == "forbidden_scope", cid
    _, own = run(_call(kes, "get_claim", {"claim_id": "c_est_KES"}))
    assert own["claim_id"] == "c_est_KES"
    _, public = run(_call(kes, "get_claim", {"claim_id": "c_sc_11"}))
    assert public["team"] == "KES"


def test_true_matrix_gating():
    e = MockEngine()
    kes, har, bc = scoped(e, "KES"), scoped(e, "HAR"), scoped(e, "broadcast")
    assert kes.call("get_true_matrix", {})["error"] == "forbidden_scope"
    assert bc.call("get_true_matrix", {})["error"] == "not_sealed_yet"
    assert SealedChoice.model_validate(kes.call("seal_choice", {"option_id": "KES-HT-B"})).team == "KES"
    assert bc.call("get_true_matrix", {})["error"] == "not_sealed_yet"
    har.call("seal_choice", {"option_id": "HAR-HT-Z"})
    out = bc.call("get_true_matrix", {})
    assert DuelBroadcast.model_validate(out).true_matrix.kind == "true"
    assert kes.call("get_true_matrix", {})["error"] == "forbidden_scope"  # still forbidden after the reveal


def test_staff_cannot_see_future_match_events():
    e = MockEngine()
    _, evs = run(_call(scoped(e, "KES", minute=0), "get_events", {"filter": {"type": "goal"}}))
    assert evs == []
    _, evs = run(_call(scoped(e, "KES", minute=45), "get_events", {"filter": {"type": "goal"}}))
    assert len(evs) == 1 and evs[0]["minute"] <= 45  # only the first-half goal is visible at half-time
    assert scoped(e, "KES").call("get_match_state", {"minute": 45})["error"] == "forbidden_scope"


def test_no_response_contains_hidden_truth():
    e = MockEngine()
    kes = scoped(e, "KES")
    blobs = [json.dumps(kes.call(t, a)) for t, a in [
        ("get_team_tendencies", {"team": "HAR"}), ("get_player_profile", {"player_id": "HAR-5"}),
        ("get_set_piece_profile", {"team": "HAR"}), ("estimate_opponent_options", {}),
        ("get_squad_condition", {"minute": 0})]]
    for blob in blobs:
        for kind in TRAIT_KINDS:
            assert kind not in blob


def test_validate_plan_checks_evidence_provenance():
    e = MockEngine()
    kes = scoped(e, "KES")
    plan = e.bundle.plans["KES"].model_dump(mode="json", by_alias=True)
    res = ValidationResult.model_validate(kes.call("validate_plan", {"plan": plan}))
    assert not res.ok and any("never retrieved" in x for x in res.errors)
    kes.call("get_team_tendencies", {"team": "HAR"})
    kes.call("get_set_piece_profile", {"team": "HAR"})
    assert kes.call("validate_plan", {"plan": plan})["ok"] is True


def test_calls_are_recorded_server_side():
    e = MockEngine()
    kes = scoped(e, "KES")
    kes.call("get_team_tendencies", {"team": "HAR"})
    kes.call("get_plan_status", {"minute": 1, "team": "HAR"})
    assert [(c.tool, c.status) for c in kes.calls] == [("get_team_tendencies", "ok"), ("get_plan_status", "rejected")]
    assert "c_sc_03" in kes.claims_served


def test_http_mode_refuses_non_loopback():
    assert _loopback("127.0.0.1") and _loopback("::1") and _loopback("localhost")
    assert not _loopback("0.0.0.0") and not _loopback("192.168.1.10")
    with pytest.raises(SystemExit):
        main(["--scope", "KES", "--http", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        main(["--scope", "XYZ"])


def test_staff_cannot_read_claims_about_later_minutes():
    from contracts import Claim
    from mcp_server.policy import ScopedTools

    class _Engine:
        claims = {c.claim_id: c for c in [
            Claim(claim_id="c_kpi_KES_k1_60", type="kpi_status", team="KES", metric="high_turnovers", value=3,
                  minute=60),
            Claim(claim_id="c_kpi_KES_k1_40", type="kpi_status", team="KES", metric="high_turnovers", value=1,
                  minute=40),
            Claim(claim_id="c_ad_HAR_50_after", type="observed_adaptation", team="HAR", metric="build_up_long_share",
                  value=0.4, minute=41),
            Claim(claim_id="c_obs_HAR_press_45", type="observed_tendency", team="HAR",
                  metric="pressures_in_opponent_half_share", value=0.5, minute=25),
            Claim(claim_id="c_sc_HAR_gk_short", type="observed_tendency", team="HAR", metric="goal_kick_short_share",
                  value=0.8)]}

        def get_claim(self, cid):
            return self.claims[cid]

    tools = ScopedTools(engine=_Engine(), scope="KES", home="KES", away="HAR", match_id="m", visible_minute=45)
    assert tools.call("get_claim", {"claim_id": "c_kpi_KES_k1_60"})["error"] == "forbidden_scope"
    assert tools.call("get_claim", {"claim_id": "c_ad_HAR_50_after"})["error"] == "forbidden_scope"  # cutoff 50
    for ok in ("c_kpi_KES_k1_40", "c_obs_HAR_press_45", "c_sc_HAR_gk_short"):
        assert "error" not in tools.call("get_claim", {"claim_id": ok}), ok
