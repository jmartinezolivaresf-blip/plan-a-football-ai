"""A local stand-in for the Foundry project's OpenAI Responses endpoint (no network, no Azure).

The real `FoundryChatClient` and `Agent` run unchanged; only the HTTP transport is replaced. The "model" answers
like the offline rules would (so validators pass), and on the analyst's first turn it calls an MCP tool itself, so
the tool loop (model -> framework -> scoped MCP server -> model) is exercised too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
from openai import AsyncOpenAI

from agents import offline
from agents.duel import offline_options

POLICY = {"ScoutingDraft": offline.scouting, "CandidateSetDraft": offline.candidates, "OptionsDraft": offline_options}


def _texts(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [t for v in node.values() for t in _texts(v)]
    if isinstance(node, list):
        return [t for v in node for t in _texts(v)]
    return []


def _evidence(body: dict) -> dict:
    for text in reversed(_texts(body.get("input", []))):
        m = offline.EVIDENCE.search(text)
        if m:
            return json.loads(m.group(1))
    raise AssertionError("no evidence block in the request")


@dataclass
class MockResponses:
    requests: list[dict] = field(default_factory=list)
    _evidence_of: dict[str, dict] = field(default_factory=dict)  # response id -> evidence of that conversation

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        fmt = body["text"]["format"]["name"]
        # like the service, later turns may only send the tool output plus previous_response_id
        prev = body.get("previous_response_id")
        ev = self._evidence_of[prev] if prev in self._evidence_of else _evidence(body)
        self._evidence_of[f"resp_{len(self.requests)}"] = ev
        answered = prev is not None or any(isinstance(i, dict) and i.get("type") == "function_call_output"
                                           for i in body["input"])
        tools = {t.get("name") for t in body.get("tools", [])}
        if fmt == "ScoutingDraft" and not answered and "get_team_tendencies" in tools:
            output = [{"type": "function_call", "id": "fc_1", "call_id": f"call_{len(self.requests)}",
                       "name": "get_team_tendencies", "status": "completed",
                       "arguments": json.dumps({"team": ev["opponent"], "aspect": "all"})}]
        else:
            draft = (offline.revise(ev) if fmt == "CandidateSetDraft" and ev.get("errors") else POLICY[fmt](ev))
            output = [{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                       "content": [{"type": "output_text", "annotations": [], "text": draft.model_dump_json()}]}]
        return httpx.Response(200, json={
            "id": f"resp_{len(self.requests)}", "object": "response", "created_at": 0, "model": body["model"],
            "status": "completed", "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "error": None, "incomplete_details": None, "instructions": None, "metadata": {}, "temperature": 1.0,
            "top_p": 1.0, "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                                    "input_tokens_details": {"cached_tokens": 0},
                                    "output_tokens_details": {"reasoning_tokens": 0}}})

    def project(self):
        """Stands in for the azure-ai-projects AIProjectClient: only the OpenAI client it hands out is replaced."""
        mock = self

        class _Project:
            def get_openai_client(self, **_):
                return AsyncOpenAI(api_key="unused", base_url="https://foundry.invalid/openai/v1",
                                   http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)))

        return _Project()
