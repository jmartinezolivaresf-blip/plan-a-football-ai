from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts import Duel, MatchBundle

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
SCHEMAS = ROOT / "contracts" / "schemas"


def load(path: Path):
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def bundle() -> MatchBundle:
    return MatchBundle.model_validate(load(FIXTURES / "match_bundle_fixture.json"))


@pytest.fixture(scope="session")
def duel() -> Duel:
    return Duel.model_validate(load(FIXTURES / "duel_fixture.json")["duel"])


@pytest.fixture(scope="session")
def canned() -> dict[str, dict]:
    return {p.stem: load(p) for p in sorted((FIXTURES / "tools_canned").glob("*.json"))}
