"""The independent Foundry probe (pipeline/foundry_probe.py) through the real Foundry client, against the local mock of
the Responses API: it records what the service answered, starts from the demo's exact half-time and never touches
the demo. This proves the probe works; only a run with a real deployment is evidence of a real LLM."""

from __future__ import annotations

import json

from agents.clients import ChatClients
from pipeline import foundry_probe

from .foundry_mock import MockResponses
from .test_foundry_contract import _env


def test_the_probe_records_the_service_and_leaves_the_demo_untouched(monkeypatch, tmp_path):
    from agent_framework_foundry import FoundryChatClient
    mock = MockResponses()

    def make(self, role):  # like ChatClients._make: offline staffs keep the rules client
        if self.choice.mode == "offline":
            from agents.offline import OfflineRulesClient
            return OfflineRulesClient()
        model = self.choice.analyst if role == "analyst" else self.choice.manager
        return FoundryChatClient(project_client=mock.project(), model=model)

    monkeypatch.setattr(ChatClients, "_make", make)
    _env(monkeypatch)
    before = foundry_probe.BUNDLE.read_bytes()
    assert foundry_probe.main(["--mode", "foundry", "--out", str(tmp_path)]) == 0
    assert foundry_probe.BUNDLE.read_bytes() == before
    r = json.loads(next(tmp_path.glob("probe_seed*.json")).read_text())
    s = r["summary"]
    # every model turn went through the Foundry client and came back with the service's own response id and model
    assert s["model_turns"] == 6 and s["turns_with_service_response_id"] == s["model_turns"]
    assert len(mock.requests) >= s["model_turns"]  # a turn where the model calls a tool takes more than one request
    # the half-time replay re-runs the demo's pre-match with the rules client, never through the model (first real
    # run, 2026-10-26: it followed AGENTS_MODE and asked the model for the plans a second time)
    assert sum(b["text"]["format"]["name"] == "CandidateSetDraft" for b in mock.requests) == 2
    assert "errors" not in r
    assert s["service_models"] == ["large-deployment", "small-deployment"]
    assert r["endpoint_host"] == "*.services.ai.azure.com" and r["demo_bundle_unchanged"]
    assert any("get_team_tendencies" in c["tools_called_by_model"] for p in r["prematch"].values()
               for c in p["llm_calls"])  # the model's own MCP tool call is recorded
    h = r["halftime"]
    assert all(h["same_half_time_as_demo"].values())
    for b in h["benches"].values():
        assert b["options_distinct"] and not b["fallback_to_offline_options"]
        assert [c["response_format"] for c in b["llm_calls"]] == ["OptionsDraft"]
    assert "NOT evidence" not in (tmp_path / "FOUNDRY_EVIDENCE.md").read_text()


def test_the_probe_refuses_to_run_without_foundry_settings(monkeypatch, capsys):
    _env(monkeypatch, FOUNDRY_PROJECT_ENDPOINT=None)
    assert foundry_probe.main(["--mode", "foundry"]) == 2
    assert "not configured" in capsys.readouterr().out
