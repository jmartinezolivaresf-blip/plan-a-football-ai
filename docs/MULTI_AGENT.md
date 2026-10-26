# The multi-agent system

Plan A is a contest between two teams of agents that each hold private information. A single agent that could see
both rooms would have nothing to anticipate, nothing to hide and nothing to regret, so the duel only exists because
the information is split. The host (`pipeline/`, `agents/`) enforces that split; the agents never share memory.

## Agents

| Agent | Per club | Model (Foundry mode) | Works through | Produces |
|---|---|---|---|---|
| Analyst | yes | `FOUNDRY_MODEL_SMALL` | scouting tools of its club's MCP server | scouting report: up to 5 findings, each tied to one claim, plus a guess of the opponent's levers |
| Manager | yes | `FOUNDRY_MODEL_LARGE` | `simulate_plan`, `validate_plan` | 2-3 candidate plans; the best valued one is sealed |
| Half-time bench | yes | `FOUNDRY_MODEL_LARGE` | `get_squad_condition`, `get_plan_status`, `get_events`, `estimate_opponent_options`, `price_matrix`, `seal_choice` | three distinct options, its believed matrix, a sealed choice |
| Director | broadcast | deterministic code | broadcast MCP server (`get_true_matrix` after both seals) | timed cues; every number is a claim |

In `AGENTS_MODE=offline` the analyst, manager and bench are the same Agent Framework agents with a deterministic
rules client (CI, demo without Azure). Which one produced a bundle is recorded in `eval.build.models`.

## What each agent can see (enforced by the host, tested)

- **Own MCP server, own scope.** Each club's agents get an in-process MCP server created with that club's scope. The
  scope is never read from a request; "own team" tools take no team argument; the broadcast tools
  (`get_true_matrix`, `get_match_state`) are not registered for a club (`mcp_server/policy.py`).
- **No future.** Before kick-off staffs see no events of the match; at half-time only the first half.
- **No hidden truth.** The engine, the MCP server and the agents never import `contracts.eval_only`; scouting only
  sees deviations in past events. Each bench values options in its own *belief world* built from its scouting.
- **No peeking at the other bench.** A bench estimates the other bench's options and prices them from what it
  observed in the first half (press height, build-up, channel, corners read from events, D-048); it never sees the
  other bench's options, matrix or choice before the reveal.

## Handoffs

```
analyst --(report: claim ids)--> manager --(candidate plans)--> validator --> simulate_plan --> seal
   ^ tools: tendencies, profiles, set pieces          tools: validate_plan, simulate_plan
first half (simulator) --> bench: KPIs, goals --> options --> validator --> estimate other bench --> price_matrix
                                                                                         --> seal_choice
both seals --> broadcast: true matrix, regret --> director cues --> bundle
```

## Failure handling and recovery

- **Grounded text.** Agents write `{claim_id.field}` placeholders, never digits; `agents/validators/text.py`
  rejects any other digit and any claim the agent was not served. A rejected report is retried with the
  validator's errors (`MAX_ATTEMPTS`), then a template is used and the trace says so.
- **Valid plans and options.** `validate_plan` rejects levers without evidence the staff actually retrieved,
  unknown players, impossible substitutions and implausible KPI targets (wrong scale or direction, or beyond what
  teams reached by that minute in the league's public matches, D-057); the manager revises up to `MAX_REVISIONS` times, then falls back
  to its sealed template (`tests/test_agents_prematch.py` exercises both paths). At half-time an option is
  measured against the levers the team plays with now (its Plan B included, read through its own
  `get_squad_condition`): an option that changes nothing is rejected, two options with the same tactics are never
  priced as two rows, and guesses about the other bench that look the same from what was seen become one column
  (D-055, `tests/test_duel_options.py`).
- **Seals.** Plans are sealed before kick-off; half-time choices are committed with a random salt and revealed only
  after both benches sealed. The browser re-verifies both.

## Why MCP and Microsoft Agent Framework

- **MCP** gives each bench a tool surface that the host can scope, record and audit: every call (including those
  the model makes on its own) lands in the trace with the claim ids it returned. Swapping the engine (mock,
  real) or the client (offline, Foundry) does not change the agents.
- **Microsoft Agent Framework** provides the `Agent` abstraction over interchangeable chat clients, MCP tools and
  structured outputs (`response_format` -> strict JSON schema), which is what lets the same agents run offline in
  CI and on Microsoft Foundry models. The Foundry path is verified against a local mock of the Responses API
  (`tests/test_foundry_contract.py`); a real deployment has not been called yet (`docs/FOUNDRY.md`).

## Evidence of decisions

The bundle keeps every agent step (`bundle.traces`: workflow, agent, tool or model, arguments, claim ids returned,
status, retries) and the analyst desk shows them. `docs/AGENT_EVIDENCE.md` is generated from the frozen bundle by
`python -m pipeline.evidence` and shows, for the demo match, which claims each decision rests on.
