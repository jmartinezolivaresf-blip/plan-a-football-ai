"""MockEngine satisfies the EngineAPI Protocol and returns contract-valid objects."""

from __future__ import annotations

from contracts import Claim, Matrix, Snapshot
from contracts.engine_api import EngineAPI
from contracts.plan import Levers, OpponentPlanEstimate
from contracts.refs import ValidationResult
from mcp_server.mock_engine import MockEngine

MID = "m-demo-001"


def test_mock_implements_protocol():
    assert isinstance(MockEngine(), EngineAPI)


def test_protocol_methods_are_all_implemented():
    names = {n for n in dir(EngineAPI) if not n.startswith("_")}
    assert names <= set(dir(MockEngine))


def test_mock_returns_contract_objects():
    e = MockEngine()
    assert all(isinstance(c, Claim) for c in e.get_team_tendencies("HAR", "build_up"))
    assert e.get_player_profile("HAR-5")[0].metric == "losses_per_100_pressured_receptions"
    assert isinstance(e.get_match_state(MID, 45), Snapshot)
    est = OpponentPlanEstimate(estimator="KES", opponent="HAR", levers=Levers(), confidence=0.6)
    assert e.simulate_plan(e.bundle.plans["KES"], est, 500)[0].type == "sim_valuation"
    kes = e.price_matrix(MID, [], [], 300, "KES", [0.5, 0.15, 0.35])
    assert isinstance(kes, Matrix) and kes.believer == "KES"
    assert e.price_matrix(MID, [], [], 300, "HAR", [0.55, 0.3, 0.15]).believer == "HAR"
    assert [k.label for k in e.get_plan_status(MID, "KES", 36)] == ["at_risk"]
    assert len(e.get_events(MID, {"type": "goal"})) == 3
    assert all(c.player_id.startswith("KES-") for c in e.get_squad_condition(MID, "KES", 45))


def test_mock_option_validation_catches_bench_player():
    e = MockEngine()
    option = e.bundle.duel.private["KES"].options[2].model_copy(deep=True)
    assert e.validate_option(MID, option) == ValidationResult(ok=True)
    option.subs[0].out = "KES-14"
    result = e.validate_option(MID, option)
    assert not result.ok and "KES-14" in result.errors[0]
