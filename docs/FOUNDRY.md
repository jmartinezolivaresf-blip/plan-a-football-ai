# Microsoft Foundry: setup and verification

**Status (2026-10-25): not connected.** No Foundry resource exists and no real model call has been made. The code
path is verified offline: the real `FoundryChatClient` + `Agent` + scoped MCP tools run the pre-match and half-time
workflows against a local mock of the Responses API (`tests/test_foundry_contract.py`). The demo bundle in the repo
was produced by the offline rules client (`eval.build.models` says so). Do not describe the agents as running on
Foundry until `python -m agents.foundry_ping` has succeeded and `make foundry-probe` (below) has recorded a real run.

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

# 5. the independent check on the frozen demo (recommended): the demo, the video and the numbers do not change
AGENTS_MODE=foundry make foundry-probe                 # docs/FOUNDRY_EVIDENCE.md + eval/results/foundry/

# 6. optional, only if the demo itself should be rebuilt with Foundry (a new match, video and docs)
AGENTS_MODE=foundry make seed-search N=48              # a model changes the plans, so the story seed may change
AGENTS_MODE=foundry make bundle SEED=<seed>            # then: uv run python -m pipeline.story
```

### The independent check (`make foundry-probe`, `pipeline/foundry_probe.py`)

It runs the same agents, scoped MCP tools and validators with the real model on the demo's own data, and never
writes the demo bundle (it compares the bundle's SHA-256 before and after):

1. **Pre-match:** both staffs scout and plan with the model on season 2026, match seed 204. Their plans are compared
   with the demo's sealed plans and are not played.
2. **Half-time:** the demo's first half is replayed with the demo's sealed plans (checked identical: plans, the 1-1
   score, the levers in force, every first-half event) and both benches decide with the model from that exact
   state: options validated by the engine (an option that changes nothing is rejected), believed and true matrices,
   choices, regret. The second half is not played.

For every model turn it records what the service returned: the response id, the model the service ran and the token
counts, plus the tools the model called itself. Volume: the same agent turns as one demo build (2 pre-match staffs +
2 benches, the first row of the token table above). `--mode offline` runs it with the rules client (no network; its
report says it is not evidence). Tested through the Foundry client against the mock (`tests/test_foundry_probe.py`).

What may be said after a successful probe (every turn answered with a service response id): "the agents were run
with a real model on Microsoft Foundry on the demo's data and half-time (docs/FOUNDRY_EVIDENCE.md); the published
demo replays the offline run". Report a fallback (template report, rule options) if the probe shows one. Record the
date, region and deployment in `docs/DECISIONS.md`. Only after step 6 may the README, pitch and video say that the
demo itself was produced on Microsoft Foundry.
