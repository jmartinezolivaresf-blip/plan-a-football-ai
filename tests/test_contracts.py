"""Schemas are exported from Pydantic, valid JSON Schema, and every fixture validates against them."""

from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from contracts import PUBLIC_CONTRACTS, Duel, MatchBundle, Plan, Squads
from contracts.eval_only import Truth
from contracts.export_schemas import targets
from fixtures.build_fixtures import build_all

from .conftest import FIXTURES, SCHEMAS, load

REQUIRED = {"events", "snapshot", "squads", "plan", "option", "claim", "matrix", "cue", "trace", "match_bundle"}


def test_all_required_contracts_exist():
    assert REQUIRED <= set(PUBLIC_CONTRACTS)
    for name in REQUIRED:
        assert (SCHEMAS / f"{name}.schema.json").exists(), name


def test_exported_schemas_are_up_to_date():
    stale = [str(p) for p, text in targets().items() if not p.exists() or p.read_text() != text]
    assert not stale, f"run `make schemas`: {stale}"


@pytest.mark.parametrize("name", sorted(PUBLIC_CONTRACTS))
def test_schema_is_valid_json_schema(name):
    Draft202012Validator.check_schema(load(SCHEMAS / f"{name}.schema.json"))


def test_fixtures_are_up_to_date():
    stale = [str(p) for p, text in build_all().items() if not p.exists() or p.read_text() != text]
    assert not stale, f"run `make fixtures`: {stale}"


def _json_schema_errors(schema_name: str, instance) -> list[str]:
    validator = Draft202012Validator(load(SCHEMAS / f"{schema_name}.schema.json"))
    return [e.message for e in validator.iter_errors(instance)][:5]


def test_bundle_fixture_validates_pydantic_and_json_schema():
    data = load(FIXTURES / "match_bundle_fixture.json")
    MatchBundle.model_validate(data)
    assert _json_schema_errors("match_bundle", data) == []


def test_component_fixtures_validate():
    Squads.model_validate(load(FIXTURES / "squads_fixture.json"))
    assert _json_schema_errors("squads", load(FIXTURES / "squads_fixture.json")) == []
    for plan in load(FIXTURES / "plans_fixture.json")["plans"].values():
        Plan.model_validate(plan)
        assert _json_schema_errors("plan", plan) == []
    duel = load(FIXTURES / "duel_fixture.json")["duel"]
    Duel.model_validate(duel)
    assert _json_schema_errors("duel", duel) == []
    match = load(FIXTURES / "match_fixture.json")
    for ev in match["events"]:
        assert _json_schema_errors("events", ev) == []
    for snap in match["snapshots"]:
        assert _json_schema_errors("snapshot", snap) == []
    Truth.model_validate(load(FIXTURES / "eval_only" / "truth_fixture.json"))


def test_fixtures_are_flagged_illustrative(bundle):
    assert bundle.illustrative and bundle.duel.illustrative
    assert all(c.illustrative for c in bundle.claims)
    assert bundle.meta.synthetic and bundle.meta.precomputed
