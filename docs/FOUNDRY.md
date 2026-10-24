# Microsoft Foundry: setup and verification

**Status (2026-10-24): not connected.** No Foundry resource exists and no real model call has been made. The code
path is verified offline: the real `FoundryChatClient` + `Agent` + scoped MCP tools run the pre-match and half-time
workflows against a local mock of the Responses API (`tests/test_foundry_contract.py`). The demo bundle in the repo
was produced by the offline rules client (`eval.build.models` says so). Do not describe the agents as running on
Foundry until `python -m agents.foundry_ping` has succeeded and a bundle has been built with `AGENTS_MODE=foundry`.

## What the code does

| Piece | Where | Notes |
|---|---|---|
| Mode switch | `AGENTS_MODE=offline|foundry` (`agents/clients.py`) | Same agents, tools, validators and workflows in both modes |
| Client | `agent_framework_foundry.FoundryChatClient` 1.15.0 (Responses API) | `project_endpoint`, `model` (deployment name), credential |
| Auth | `azure.identity.aio.AzureCliCredential(tenant_id=FOUNDRY_TENANT_ID)` | Entra ID, no keys; pinned tenant, corporate tenants refused |
| Roles | analyst -> `FOUNDRY_MODEL_SMALL`, manager and half-time bench -> `FOUNDRY_MODEL_LARGE` | one deployment can serve both |
| Tools | `MCPStdioTool(mcp_client=...)` over the staff's in-process scoped MCP server | analyst limited to scouting tools; never broadcast tools |
| Output | `response_format` = Pydantic model -> strict JSON schema | validators then check every claim id and number |
| Lifecycle | one client per role per staff run; MCP tool contexts closed after each turn; credentials closed at the end | |

Found and fixed while preparing this (D-046): the MCP tool needs `tenacity` (not pulled by `agent-framework-core`),
so the first Foundry turn would have crashed; per-call clients leaked credentials; MCP subscriptions outlived the
client; `.env` was only read by the ping script.

## Recommended resources for a personal or student subscription

| Resource | Setting | Cost |
|---|---|---|
| Resource group | `rg-plan-a` | free |
| Foundry resource | kind `AIServices`, SKU S0, project management enabled | no fixed fee |
| Foundry project | `plan-a` | free |
| Model deployment | `gpt-4.1-mini` version `2025-04-14`, **Global Standard**, capacity 50 (thousand tokens per minute, a rate limit) | pay per token |
| Role | **Azure AI User** on the Foundry resource for the person running the agents | free |

- **Region:** Sweden Central (EU, broad model availability). Any region listing the model under Global Standard in the
  Foundry model catalog works; check it in the portal before creating.
- **Model:** a small model is enough: the agents only pick and phrase claims and choose levers; numbers never come
  from the model. `gpt-4.1-mini` supports function calling and strict structured outputs on the Responses API.
  Cheaper alternatives listed on the Azure OpenAI pricing page: `gpt-4.1-nano`, `gpt-5-nano`.
- **Permissions to create:** Contributor (or Owner) on the subscription or the resource group; Owner or User Access
  Administrator to assign the role.

### Expected token volume (measured, not estimated from guesses)

`uv run python scripts/foundry_budget.py` runs the full demo build through the Foundry code path with a mock
transport and measures what the agents would send (characters / 4):

| Run | Requests | Input tokens | Output tokens |
|---|---|---|---|
| One demo build (2 pre-match staffs + 2 half-time benches) | 8 | ~23,400 | ~3,400 |
| Ping (`agents.foundry_ping`) | 1-2 | < 100 | < 20 |

Rough totals: a demo build, a few retries and one evaluation run with Foundry (15 pre-matches for E1 and 6 full
matches) stay in the order of **0.5-1 million input tokens**. Cost = tokens x the per-million price of the chosen
deployment on the [Azure OpenAI pricing page](https://azure.microsoft.com/pricing/details/azure-openai/) or the
pricing calculator (the page renders prices in the browser; read them there before approving). Set a budget alert
on the resource group (Cost Management, for example 20 USD).

## Procedure once the subscription exists

```bash
# 1. sign in to the hackathon subscription's own directory (not the corporate one)
az login --tenant <TENANT_ID>
export PLAN_A_SUBSCRIPTION_ID=<SUBSCRIPTION_ID>

# 2. guards only (refuses corporate subscriptions/tenants, creates nothing)
infra/foundry_provision.sh --check

# 3. after approving the resources above
PLAN_A_APPROVED=yes infra/foundry_provision.sh        # prints the .env lines

# 4. settings and checks
cp .env.example .env                                   # paste the printed FOUNDRY_* lines
uv run python -m agents.foundry_ping --dry-run         # no network: config + clients
uv run python -m agents.foundry_ping                   # ONE real call per role

# 5. real agents, analyst and manager on Foundry
make season && ENGINE=real AGENTS_MODE=foundry uv run python -m agents.prematch   # pre-match only, agents/_out/
AGENTS_MODE=foundry make seed-search N=48              # a model changes the plans, so the story seed may change
AGENTS_MODE=foundry make bundle SEED=<seed>            # then: uv run python -m pipeline.story
```

After step 5, check `eval.build.models` in `web/public/match_bundle.json` shows the deployment names, keep the
trace (`bundle.traces`, statuses and retries) and record the date, region and deployment in `docs/DECISIONS.md`.
Only then may the README, pitch and video say the agents run on Microsoft Foundry.
