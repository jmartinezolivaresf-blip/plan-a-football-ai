# agents (person B)

```bash
make prematch                              # offline rules client, no Azure: agents/_out/prematch.json
AGENTS_MODE=foundry make prematch          # Microsoft Foundry models (.env + az login), see infra/AZURE_PLAN.md
uv run python -m agents.foundry_ping       # manual check that Foundry answers
```

## WF-Previa (`prematch.py`)

Per team, both teams concurrently and isolated (each with its own scoped MCP server, in-process):

1. **Analyst** gathers evidence through MCP (`list_matches`, `get_team_tendencies`, `get_set_piece_profile`,
   `get_player_profile`), then an Agent Framework `Agent` returns a `ScoutingDraft` (≤ 5 findings, each tied to a
   claim, numbers only as `{claim_id.field}` placeholders, plus a guess of the opponent's levers).
   Code checks every claim was served to this staff and verifies each headline (`validators/text.py`); up to two
   corrections, then a template report. Code copies values, `n` and league reference from the claims.
2. **Manager** proposes 1–3 candidates (`CandidateSetDraft`) with the 5 levers; each non-default lever cites claims.
   Each candidate goes through MCP `validate_plan` (rules in `validators/plan.py` + evidence provenance); up to two
   revisions with the validator's errors, then dropped. No valid candidate → template plan.
3. **Valuation:** `simulate_plan` for each valid candidate; the choice is the highest simulated value, ties broken by
   evidence (with the mock all candidates get the same valuation claim, and the reason says so).
4. **Seal:** `contracts.sealing.plan_digest`, verified, and recorded in the trace.

`traces` are `contracts.TraceStep`: agent, scope, tool, args (plans redacted), claims, duration, status
(`ok` / `rejected` / `retried`), and model turns (`model:<name>`). Tool calls made by the LLM through MCP are captured
from the server-side log.

## Model clients (`clients.py`)

- `foundry`: `agent_framework_foundry.FoundryChatClient` with `DefaultAzureCredential` (Entra ID, no keys); analyst
  uses `FOUNDRY_MODEL_SMALL`, manager `FOUNDRY_MODEL_LARGE`. Agents also get the scoped MCP server as an
  `MCPStdioTool(mcp_client=...)` so they can look up more claims. **Not yet exercised against a real deployment.**
- `offline`: `OfflineRulesClient`, deterministic rules behind the same `Agent` interface, for CI and demos without
  Azure. Its output is labelled `offline-rules` and is never presented as AI output.
