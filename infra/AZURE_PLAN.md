# Azure plan (needs explicit approval before anything is created)

Status on 2026-10-24: **nothing provisioned, nothing deployed.** The dev machine's Azure CLI is signed in to
corporate subscriptions that must not be used for this project: no resources, no deployments, no model calls. The
scripts below refuse any subscription in the Microsoft corporate tenant and any listed in the git-ignored
`infra/deny.local` (or `PLAN_A_DENY_SUBSCRIPTIONS`), never fall back to the CLI's default subscription, and stop
before any billable step unless `PLAN_A_APPROVED=yes` (D-046, tested in `tests/test_infra_guard.py` with a fake
`az`).

## What gets created, and what can cost money

| # | Resource | Script | Cost |
|---|---|---|---|
| 1 | Resource group `rg-plan-a` | both | free |
| 2 | Static Web App, **Free** plan (public demo) | `infra/swa_deploy.sh` | free plan; the script stops if the plan is not Free |
| 3 | Foundry resource (AIServices S0) + project | `infra/foundry_provision.sh` | no fixed fee |
| 4 | Model deployment `gpt-4.1-mini` Global Standard | `infra/foundry_provision.sh` | **pay per token** (docs/FOUNDRY.md: ~23k input + 3.4k output tokens per demo build) |
| 5 | Role assignment "Azure AI User" for the signed-in user | `infra/foundry_provision.sh` | free |
| - | Not created: Container Apps, App Service, databases, Application Insights, public MCP server | | |

Only item 4 generates charges. Recommended: a budget alert on the resource group (Cost Management) before step 4.

## Public demo: Azure Static Web Apps (Free)

- The app is fully static: `web/dist` = `index.html`, two hashed assets, `favicon.svg`, the frozen
  `match_bundle.json` and `staticwebapp.config.json`. **No backend, no API, no keys**; the browser verifies seals
  with Web Crypto.
- `web/public/staticwebapp.config.json`: SPA fallback to `index.html` (deep links like `/?t=45:00` work),
  `application/json` for the bundle, long cache for hashed assets, 5-minute cache for the bundle, the config file and
  `/.auth/*` return 404, and security headers (CSP `default-src 'self'`, no framing, `nosniff`, no referrer).
- Verified locally with the official SWA CLI emulator (`npx swa start dist --host 127.0.0.1`): routes, MIME types,
  headers, deep links, and the app renders with no CSP violations; seals verify.
- Anonymous read access is intended (judges, no login) and the content is synthetic. The deploy script checks the
  live site anonymously (home page, bundle, CSP header) after uploading.
- **The MCP server is not deployed:** it has no client authentication (D-026). The demo shows recorded tool calls.
- If the subscription is not available in time, the same build can go to GitHub Pages (`docs/PUBLISH.md`,
  `.github/workflows/pages.yml`, manual only).

```bash
az login --tenant <HACKATHON_TENANT_ID>
export PLAN_A_SUBSCRIPTION_ID=<HACKATHON_SUBSCRIPTION_ID>
infra/swa_deploy.sh --check                 # guards + production build + bundle checks, creates nothing
PLAN_A_APPROVED=yes infra/swa_deploy.sh     # group + Free static web app + deploy + anonymous verification
```

Optional settings (env or `.env`): `PLAN_A_RESOURCE_GROUP`, `PLAN_A_LOCATION`, `PLAN_A_SWA_LOCATION` (Static Web
Apps regions: westeurope, eastus2, centralus, westus2, eastasia), `PLAN_A_SWA_NAME`. Redeploying after a new bundle:
run the same command; the deployment token is read from Azure each time and never printed or stored.

## Microsoft Foundry

See `docs/FOUNDRY.md` (resources, region, model, permissions, measured token volume, procedure, verification).

```bash
infra/foundry_provision.sh --check
PLAN_A_APPROVED=yes infra/foundry_provision.sh
```

## After judging (10 Nov 2026)

`infra/teardown.sh` lists what is in the resource group and deletes it only after you type its name.
