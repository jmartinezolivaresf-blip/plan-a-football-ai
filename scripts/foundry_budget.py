"""Estimate the Foundry token volume of one demo build (pre-match + half-time) without calling Azure.

    uv run python scripts/foundry_budget.py [--match-seed 226]

Runs the real pipeline with every Foundry client routed to the local mock (tests/foundry_mock.py) and measures the
requests the agents would send. Tokens are estimated as characters / 4 (a common rule of thumb for English/JSON);
output size is the mock's answer size, a real model's answers will differ.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match-seed", type=int, default=226)
    args = ap.parse_args(argv)
    import os

    from agent_framework_foundry import FoundryChatClient

    from agents.clients import ChatClients
    from pipeline.build import build
    from tests.foundry_mock import MockResponses

    mock = MockResponses()
    sizes: list[tuple[str, str, int, int]] = []
    orig = mock.handler

    def handler(request):
        resp = orig(request)
        body = json.loads(request.content)
        sizes.append((body["text"]["format"]["name"], body["model"], len(request.content), len(resp.content)))
        return resp

    mock.handler = handler  # type: ignore[method-assign]
    ChatClients._make = lambda self, role: FoundryChatClient(  # type: ignore[method-assign]
        project_client=mock.project(), model=self.choice.analyst if role == "analyst" else self.choice.manager)
    os.environ.update({"FOUNDRY_PROJECT_ENDPOINT": "https://budget.invalid/api/projects/p", "FOUNDRY_MODEL_SMALL":
                       "small", "FOUNDRY_MODEL_LARGE": "large", "FOUNDRY_TENANT_ID": "budget-estimate"})
    build(match_seed=args.match_seed, mode="foundry")
    per: dict[tuple[str, str], list[int]] = {}
    for fmt, model, req, out in sizes:
        acc = per.setdefault((fmt, model), [0, 0, 0])
        acc[0] += 1
        acc[1] += req // 4
        acc[2] += out // 4
    total_in = sum(v[1] for v in per.values())
    total_out = sum(v[2] for v in per.values())
    report = {"match_seed": args.match_seed, "requests": len(sizes),
              "by_turn": {f"{f} ({m})": {"requests": v[0], "input_tokens_est": v[1], "output_tokens_est": v[2]}
                          for (f, m), v in sorted(per.items())},
              "input_tokens_est": total_in, "output_tokens_est": total_out,
              "method": "characters / 4 of the HTTP request (instructions, evidence, tool schemas) and of the answer"}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
