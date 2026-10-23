"""Information separation: private bench data, broadcast-only true matrix, evaluator-only truth."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys

import pytest

from contracts import PUBLIC_CONTRACTS
from contracts.eval_only import TRAIT_KINDS, SimConfig, TeamTruth, Truth
from mcp_server.mock_engine import MockEngine, NotSealedYet

from .conftest import FIXTURES, ROOT, load


def _opponent(team: str) -> str:
    return "HAR" if team == "KES" else "KES"


def test_private_bench_data_never_contains_the_true_matrix_or_opponent_secrets(duel):
    true_id = duel.broadcast.true_matrix.matrix_id
    for team, priv in duel.private.items():
        opp = _opponent(team)
        blob = json.dumps(priv.model_dump(mode="json"))
        assert true_id not in blob
        assert '"kind": "true"' not in blob
        for opt in duel.private[opp].options:  # opponent's REAL options
            assert opt.option_id not in blob
        assert duel.private[opp].choice.sha256 not in blob
        assert duel.broadcast.revealed[opp].salt not in blob
        assert all(o.option.estimated and o.option.team == opp for o in priv.opponent_estimate.options)


def test_staff_scoped_canned_tools_contain_no_true_matrix_or_opponent_secrets(duel, canned):
    true_id = duel.broadcast.true_matrix.matrix_id
    staff = {name: c for name, c in canned.items() if c["scope"] in ("KES", "HAR")}
    assert staff, "expected staff-scoped canned responses"
    for name, c in staff.items():
        blob = json.dumps(c["response"])
        opp = _opponent(c["scope"])
        assert true_id not in blob, name
        assert '"kind": "true"' not in blob, name
        for opt in duel.private[opp].options:
            assert opt.option_id not in blob, name
        assert duel.private[opp].choice.sha256 not in blob, name


def test_true_matrix_tool_is_forbidden_for_staff(canned):
    assert canned["get_true_matrix.KES"]["response"]["error"] == "forbidden_scope"
    assert "true_matrix" in canned["get_true_matrix.broadcast"]["response"]


def test_mock_engine_refuses_true_matrix_before_both_seals():
    engine = MockEngine()
    with pytest.raises(NotSealedYet):
        engine.true_matrix("m-demo-001")
    engine.seal_choice("m-demo-001", "KES", "KES-HT-B")
    with pytest.raises(NotSealedYet):
        engine.true_matrix("m-demo-001")
    engine.seal_choice("m-demo-001", "HAR", "HAR-HT-Z")
    assert engine.true_matrix("m-demo-001").true_matrix.kind == "true"


def test_importing_public_contracts_does_not_load_eval_only():
    code = "import sys, contracts; print('contracts.eval_only' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=True)
    assert out.stdout.strip() == "False"


def test_public_contracts_have_no_eval_only_fields():
    hidden = set(TeamTruth.model_fields) | set(Truth.model_fields) | set(SimConfig.model_fields)
    hidden -= {"team", "teams", "season_id", "seed"}  # generic names that legitimately appear elsewhere
    for name, model in PUBLIC_CONTRACTS.items():
        schema = json.dumps(model.model_json_schema())
        for field in hidden:
            assert f'"{field}"' not in schema, (name, field)


def test_public_fixtures_never_mention_hidden_traits():
    truth = load(FIXTURES / "eval_only" / "truth_fixture.json")
    assert truth["teams"], "truth fixture should not be empty"
    public = [p for p in FIXTURES.rglob("*.json") if "eval_only" not in p.parts]
    assert public
    for path in public:
        text = path.read_text()
        for trait in TRAIT_KINDS:
            assert trait not in text, (path.name, trait)
        assert '"archetype"' not in text, path.name


@pytest.mark.parametrize("package", ["engine", "mcp_server", "agents"])
def test_engine_mcp_agents_do_not_import_eval_only(package):
    for path in (ROOT / package).rglob("*.py"):
        assert "eval_only" not in path.read_text(), path
    importlib.import_module(package)
