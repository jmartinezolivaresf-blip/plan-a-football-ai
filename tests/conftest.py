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


@pytest.fixture(autouse=True)
def _never_the_real_dotenv(monkeypatch):
    """Tests never read the developer's .env: with real Foundry settings in it, a test that removes them and runs the
    ping or the probe would otherwise call the real model (and spend tokens)."""
    from agents import foundry_ping, settings
    monkeypatch.setattr(settings, "load_env", lambda: False)
    monkeypatch.setattr(foundry_ping, "load_env", lambda: False)  # imported by name at module level


@pytest.fixture(scope="session")
def bundle() -> MatchBundle:
    return MatchBundle.model_validate(load(FIXTURES / "match_bundle_fixture.json"))


@pytest.fixture(scope="session")
def duel() -> Duel:
    return Duel.model_validate(load(FIXTURES / "duel_fixture.json")["duel"])


@pytest.fixture(scope="session")
def canned() -> dict[str, dict]:
    return {p.stem: load(p) for p in sorted((FIXTURES / "tools_canned").glob("*.json"))}
