# infra (owner: person B)

Nothing is provisioned from this repo yet. Day-0 Azure steps are in `docs/plan/PLAN_A_v6_EJECUCION.md` §10.1
and must be run by a team member with the right subscription permissions (see `docs/START_HERE.md`).

Planned resources: one resource group with a Microsoft Foundry project (2 model deployments), Application
Insights, an Azure Container Apps environment (MCP server, min replicas 1 until 10 Nov) and Azure Static Web
Apps (web + bundle), plus a budget alert. Deployment via `az` CLI or `azd`, no custom Bicep (v6 §10).
