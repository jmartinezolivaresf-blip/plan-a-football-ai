"""Foundry path without Azure: configuration guards, and the real FoundryChatClient + Agent + scoped MCP tools
running the pre-match and half-time workflows against a local mock of the Responses API (tests/foundry_mock.py).

These tests prove the code is compatible with the installed Agent Framework and Foundry client. They do NOT prove
that a real Foundry deployment answers: that needs `python -m agents.foundry_ping` with an approved subscription.
"""

from __future__ import annotations

import asyncio

import pytest

from agents import clients
from agents import prematch as pm
from agents.clients import ChatClients, FoundryConfigError, ModelChoice, model_choice
from contracts.sealing import verify_plan
from mcp_server.mock_engine import MockEngine

from .foundry_mock import MockResponses

GOOD_ENV = {"FOUNDRY_PROJECT_ENDPOINT": "https://plan-a.services.ai.azure.com/api/projects/plan-a",
            "FOUNDRY_MODEL_SMALL": "small-deployment", "FOUNDRY_MODEL_LARGE": "large-deployment",
            "FOUNDRY_TENANT_ID": "00000000-0000-0000-0000-000000000001"}


def _env(monkeypatch, **overrides):
    for k in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_SMALL", "FOUNDRY_MODEL_LARGE", "FOUNDRY_MODEL",
              "FOUNDRY_TENANT_ID", "FOUNDRY_DENY_TENANTS", "AGENTS_MODE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in {**GOOD_ENV, **overrides}.items():
        if v is not None:
            monkeypatch.setenv(k, v)


# ---------------------------------------------------------------------------------------------- configuration

def test_offline_is_the_default(monkeypatch):
    _env(monkeypatch)
    assert model_choice().mode == "offline"


def test_foundry_config_is_read_from_the_environment(monkeypatch):
    _env(monkeypatch)
    c = model_choice("foundry")
    assert (c.mode, c.analyst, c.manager, c.endpoint) == ("foundry", "small-deployment", "large-deployment",
                                                          GOOD_ENV["FOUNDRY_PROJECT_ENDPOINT"])
    _env(monkeypatch, FOUNDRY_MODEL_LARGE=None)
    assert model_choice("foundry").manager == "small-deployment"


@pytest.mark.parametrize("missing", ["FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL_SMALL", "FOUNDRY_TENANT_ID"])
def test_foundry_needs_endpoint_model_and_tenant(monkeypatch, missing):
    _env(monkeypatch, **{missing: None})
    with pytest.raises(FoundryConfigError, match=missing):
        model_choice("foundry")


def test_corporate_tenants_are_refused(monkeypatch):
    _env(monkeypatch, FOUNDRY_TENANT_ID=next(iter(clients.DENIED_TENANTS)).upper())
    with pytest.raises(FoundryConfigError, match="denied"):
        model_choice("foundry")
    _env(monkeypatch, FOUNDRY_DENY_TENANTS="00000000-0000-0000-0000-000000000001")
    with pytest.raises(FoundryConfigError, match="denied"):
        model_choice("foundry")


def test_endpoint_must_be_https_and_mode_must_be_known(monkeypatch):
    _env(monkeypatch, FOUNDRY_PROJECT_ENDPOINT="http://plan-a.services.ai.azure.com")
    with pytest.raises(FoundryConfigError, match="https"):
        model_choice("foundry")
    with pytest.raises(FoundryConfigError):
        model_choice("azure")  # type: ignore[arg-type]


def test_foundry_clients_are_built_without_network_and_closed(monkeypatch):
    _env(monkeypatch)
    chat = ChatClients(model_choice("foundry"))
    analyst, manager = chat.get("analyst"), chat.get("manager")
    assert type(analyst).__name__ == "FoundryChatClient" and chat.get("analyst") is analyst
    assert (analyst.model, manager.model) == ("small-deployment", "large-deployment")
    assert type(chat._credentials[0]).__name__ == "AzureCliCredential" and len(chat._credentials) == 2
    asyncio.run(chat.aclose())
    assert chat._credentials == []


# ---------------------------------------------------------------------------------------------- workflows

@pytest.fixture
def foundry(monkeypatch):
    """Route every Foundry client to the mock Responses API; returns the mock (recorded requests)."""
    from agent_framework_foundry import FoundryChatClient
    mock = MockResponses()

    def make(self, role):
        model = self.choice.analyst if role == "analyst" else self.choice.manager
        return FoundryChatClient(project_client=mock.project(), model=model)

    monkeypatch.setattr(ChatClients, "_make", make)
    _env(monkeypatch)
    return mock


def test_prematch_runs_through_the_foundry_client_and_mcp_tools(foundry):
    choice = model_choice("foundry")
    r = asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", choice))
    assert r.model == "small-deployment/large-deployment" and verify_plan(r.chosen)
    models = {b["text"]["format"]["name"]: b["model"] for b in foundry.requests}
    assert models["ScoutingDraft"] == "small-deployment" and models["CandidateSetDraft"] == "large-deployment"
    for body in foundry.requests:
        assert body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"] is True
    analyst_tools = {t["name"] for b in foundry.requests if b["text"]["format"]["name"] == "ScoutingDraft"
                     for t in b.get("tools", [])}
    assert analyst_tools and analyst_tools <= set(pm.SCOUTING_TOOLS)
    # the model's own tool call reached the scoped MCP server and is in the trace like the workflow's calls
    analyst_calls = [t for t in r.traces if t.agent == "analyst" and t.tool == "get_team_tendencies"]
    assert len(analyst_calls) >= 2 and all(t.scope == "KES" for t in r.traces)


def test_a_staff_is_never_offered_broadcast_tools(foundry):
    asyncio.run(pm.run_staff(MockEngine(), "HAR", "KES", "HAR", model_choice("foundry")))
    offered = {t["name"] for b in foundry.requests for t in b.get("tools", [])}
    assert offered and not offered & {"get_true_matrix", "get_match_state"}


def test_half_time_bench_runs_through_the_foundry_client(foundry):
    from agents.duel import DuelBench
    engine = MockEngine()
    plans = engine.bundle.plans
    priv = asyncio.run(DuelBench(engine, "KES", "KES", "HAR", model_choice("foundry"), plans["KES"]).decide())
    assert priv.choice.sha256 and len(priv.options) == 3 and priv.options[0].intent == "stay_the_course"
    assert any(b["text"]["format"]["name"] == "OptionsDraft" and b["model"] == "large-deployment"
               for b in foundry.requests)


def test_switching_back_to_offline_needs_no_azure(monkeypatch):
    _env(monkeypatch)
    r = asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", ModelChoice("offline", "offline-rules",
                                                                                   "offline-rules")))
    assert r.model == "offline-rules/offline-rules" and verify_plan(r.chosen)


def test_ping_dry_run_builds_clients_without_calling(monkeypatch, capsys):
    from agents import foundry_ping
    _env(monkeypatch)
    assert foundry_ping.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "plan-a.services.ai.azure.com" in out and "dry run, no call" in out


def test_ping_fails_cleanly_without_settings(monkeypatch, capsys):
    from agents import foundry_ping
    _env(monkeypatch, FOUNDRY_PROJECT_ENDPOINT=None)
    monkeypatch.setattr("agents.settings.load_env", lambda: False)
    monkeypatch.setattr(foundry_ping, "load_env", lambda: False)
    assert foundry_ping.main(["--dry-run"]) == 1
    assert "FOUNDRY_PROJECT_ENDPOINT" in capsys.readouterr().err
