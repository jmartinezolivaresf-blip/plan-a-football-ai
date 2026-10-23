# Azure plan (needs explicit approval before anything is created)

Status on 2026-10-23: **nothing provisioned**. Azure CLI 2.91.0 is installed on the dev machine but there is no
Azure session (`az account show` asks for `az login`), so no subscription, quota or model availability has been
inspected. No `.env` exists. Everything below is a proposal.

## Step 1: Microsoft Foundry (the agents' model)

| # | Resource | Why | Cost source |
|---|---|---|---|
| 1 | Resource group `rg-plan-a` | Container for everything; deleted after judging | Free |
| 2 | Microsoft Foundry resource + project | Model deployment and project endpoint | No fixed fee; usage only |
| 3 | One model deployment, Standard (a small `gpt-4.1-mini`-class model) | Analyst, manager, duel bench | Pay per token |
| 4 | (optional) Application Insights + Log Analytics | Agent traces in Foundry | Per GB ingested (free monthly allowance) |

- **Region:** one where the chosen model is offered in Foundry (Sweden Central or East US 2 are common); checked
  read-only with `az` before creating anything.
- **Expected usage:** a pre-match run is ~6 model calls of a few thousand tokens; a duel adds ~2 per bench. The demo
  bundle plus the 6-match evaluation is in the order of 100 calls. CI never calls Azure. Check the per-token price of
  the chosen model on the Azure pricing page before approving.
- **Reuse:** an existing Foundry project works too: only the project endpoint and a deployment name are needed.
- A budget alert on the resource group (for example 20 USD) is recommended.

## Step 2: public demo (judging until 10 Nov 2026)

| # | Resource | Why | Cost source |
|---|---|---|---|
| 5 | Azure Static Web Apps, **Free** plan | Serves the web app and the precomputed `match_bundle.json` | Free plan |

- Anonymous read access is intended (judges open it without a login). It serves static files only: the synthetic
  bundle, no keys, no tokens, no backend.
- **No public MCP server.** The MCP server has no client authentication (D-026), so it stays on loopback and is not
  deployed. The demo shows the agents' recorded tool calls (traces) from the bundle instead.

## Permissions

- To create: Contributor (or Owner) on the subscription or on the resource group.
- To call the model keylessly (Entra ID): **Azure AI User** (or Cognitive Services OpenAI User) on the Foundry
  resource for the signed-in user. No API keys in the repo.

## Steps once approved

```bash
az login                                   # pick the subscription you approve
# read-only checks first: az account show, model availability in the chosen region
# create resources (portal or CLI), then:
cp .env.example .env                       # FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_SMALL (and _LARGE)
uv run python -m agents.foundry_ping       # real call; prints model, latency, reply (no secrets)
AGENTS_MODE=foundry make bundle SEED=223   # demo bundle with the real model
```

Decisions to make: subscription, region, model, Application Insights yes/no, and approval of step 2.
