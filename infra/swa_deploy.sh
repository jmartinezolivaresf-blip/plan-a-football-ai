#!/usr/bin/env bash
# Deploy the static demo (web/dist with the frozen match_bundle.json) to Azure Static Web Apps, Free plan.
#
#   PLAN_A_SUBSCRIPTION_ID=<id> PLAN_A_APPROVED=yes infra/swa_deploy.sh            # create (if needed) + deploy
#   PLAN_A_SUBSCRIPTION_ID=<id> infra/swa_deploy.sh --check                       # guards + local build only
#
# Creates: resource group PLAN_A_RESOURCE_GROUP (free) and Static Web App PLAN_A_SWA_NAME on the Free plan.
# The site is public by design (judges, no login) and serves static files only: no backend, no API, no keys.
# The deployment token is read into an environment variable and never printed.

source "$(dirname "$0")/lib.sh"
load_env_file

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RG="${PLAN_A_RESOURCE_GROUP:-rg-plan-a}"
LOCATION="${PLAN_A_LOCATION:-westeurope}"
# Static Web Apps regions: eastus2, centralus, westus2, eastasia, westeurope (westeurope refused new Free Trial
# customers on 2026-10-26; the static content is served the same way from any of them)
SWA_LOCATION="${PLAN_A_SWA_LOCATION:-eastus2}"
NAME="${PLAN_A_SWA_NAME:-plan-a-football}"
CHECK_ONLY="${1:-}"

require_subscription

echo "== local build"
npm --prefix "$ROOT/web" ci --no-audit --no-fund >/dev/null
npm --prefix "$ROOT/web" run build >/dev/null
python3 - "$ROOT/web/dist" <<'PY'
import json, sys
from pathlib import Path
dist = Path(sys.argv[1])
bundle = json.loads((dist / "match_bundle.json").read_text())
assert not bundle["illustrative"], "dist has the illustrative fixture bundle, not the frozen demo"
json.loads((dist / "staticwebapp.config.json").read_text())
assert (dist / "index.html").exists()
print(f"dist ok: bundle seed {bundle['eval']['build']['match_seed']}, models {sorted(set(bundle['eval']['build']['models'].values()))}")
PY

if [[ "$CHECK_ONLY" == "--check" ]]; then
  echo "check only: nothing created or deployed"
  exit 0
fi
require_approval "Static Web Apps Free + resource group"

if az_sub group show --name "$RG" -o none 2>/dev/null; then
  echo "== resource group $RG exists ($(az_sub group show --name "$RG" --query location -o tsv)): reused"
else
  echo "== resource group $RG ($LOCATION)"
  az_sub group create --name "$RG" --location "$LOCATION" --tags project=plan-a purpose=hackathon -o none
fi

echo "== static web app $NAME (Free)"
if ! az_sub staticwebapp show --name "$NAME" --resource-group "$RG" -o none 2>/dev/null; then
  az_sub staticwebapp create --name "$NAME" --resource-group "$RG" --location "$SWA_LOCATION" --sku Free \
    --tags project=plan-a -o none
fi
SKU="$(az_sub staticwebapp show --name "$NAME" --resource-group "$RG" --query sku.name -o tsv)"
[[ "$SKU" == "Free" ]] || die "the static web app is on plan '$SKU', not Free: stopping"

echo "== deploy web/dist"
SWA_CLI_DEPLOYMENT_TOKEN="$(az_sub staticwebapp secrets list --name "$NAME" --resource-group "$RG" \
  --query properties.apiKey -o tsv)"
export SWA_CLI_DEPLOYMENT_TOKEN
(cd "$ROOT/web" && npx swa deploy ./dist --env production --no-use-keychain >/dev/null)
unset SWA_CLI_DEPLOYMENT_TOKEN

HOST="$(az_sub staticwebapp show --name "$NAME" --resource-group "$RG" --query defaultHostname -o tsv)"
echo "== verify as an anonymous client: https://$HOST"
curl -fsS -o /dev/null "https://$HOST/" || die "home page not reachable"
curl -fsS "https://$HOST/match_bundle.json" | python3 -c "import json,sys; b=json.load(sys.stdin); assert not b['illustrative']; print('bundle ok')"
curl -fsSI "https://$HOST/" | grep -i "content-security-policy" >/dev/null || die "security headers missing"
echo "Deployed: https://$HOST"
