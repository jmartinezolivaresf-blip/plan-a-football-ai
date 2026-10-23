# Azure plan for H1 (needs approval before anything is created)

Status on 2026-10-23: **nothing provisioned**. On this machine Azure CLI is not installed, there is no Azure
session and no `.env`. No subscription could be inspected.

## What H1 needs

Only a working Microsoft Foundry model call (the last open H0 item) and, optionally, traces. No compute: the app is
deployed on Sunday (H3) and will need a separate approval.

| # | Resource | Why | Cost source |
|---|---|---|---|
| 1 | Resource group `rg-plan-a` | Container for everything | Free |
| 2 | Microsoft Foundry resource + project | Hosts the model deployments and the project endpoint | No fixed fee; usage only |
| 3 | One model deployment (small, e.g. a `gpt-4.1-mini`-class model, Standard) | Analyst and manager in H1 | Pay per token |
| 4 | (optional) Application Insights + Log Analytics | Agent traces in Foundry | Pay per GB ingested (free monthly allowance) |

- **Region:** one with the chosen model available in Foundry (Sweden Central or East US 2 are common choices); confirm
  in the portal's model catalog before creating.
- **Expected H1 usage:** a pre-match run is ~6 model calls of a few thousand tokens each; tests in CI never call
  Azure. Check current per-token prices on the Azure pricing page for the exact model before approving.
- **Reuse:** if you already have a Foundry project, we can reuse it: only the endpoint and a deployment name are needed.

## Permissions

- To create: Contributor (or Owner) on the subscription or on the resource group.
- To call the model keylessly (Entra ID): the role **Azure AI User** (or Cognitive Services OpenAI User) on the Foundry
  resource for the signed-in user now, and for the managed identity of the Container App later. No API keys.

## Steps once approved

```bash
brew install azure-cli
az login                                   # pick the subscription you approve
# create resources (portal or CLI), then:
cp .env.example .env                       # FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_SMALL (and _LARGE)
uv run python -m agents.foundry_ping       # real call; prints model, latency, reply (no secrets)
AGENTS_MODE=foundry make prematch          # both staffs with the real model
```

Decisions to make: which subscription, region, model, and whether Application Insights is wanted now.
