#!/usr/bin/env bash
# Create the Microsoft Foundry resource, project and one model deployment for the agents, then print the .env lines.
#
#   PLAN_A_SUBSCRIPTION_ID=<id> PLAN_A_APPROVED=yes infra/foundry_provision.sh
#   PLAN_A_SUBSCRIPTION_ID=<id> infra/foundry_provision.sh --check      # guards only, nothing created
#
# Creates (docs/FOUNDRY.md): resource group, Foundry resource (kind AIServices, S0, no fixed fee), project, one
# Global Standard deployment (pay per token) and an "Azure AI User" role for the signed-in user. No API keys are
# read or printed: the agents authenticate with Entra ID.

source "$(dirname "$0")/lib.sh"
load_env_file

RG="${PLAN_A_RESOURCE_GROUP:-rg-plan-a}"
LOCATION="${PLAN_A_FOUNDRY_LOCATION:-swedencentral}"
ACCOUNT="${PLAN_A_FOUNDRY_ACCOUNT:-plan-a-foundry-$RANDOM}"
PROJECT="${PLAN_A_FOUNDRY_PROJECT:-plan-a}"
MODEL="${PLAN_A_MODEL_NAME:-gpt-4.1-mini}"
MODEL_VERSION="${PLAN_A_MODEL_VERSION:-2025-04-14}"
DEPLOYMENT="${PLAN_A_DEPLOYMENT_NAME:-$MODEL}"
CAPACITY="${PLAN_A_DEPLOYMENT_CAPACITY:-50}"   # thousands of tokens per minute (a rate limit, not a charge)

require_subscription
if [[ "${1:-}" == "--check" ]]; then
  echo "check only: would create $ACCOUNT/$PROJECT in $LOCATION with $MODEL ($MODEL_VERSION) as '$DEPLOYMENT'"
  exit 0
fi
require_approval "Foundry resource + Global Standard model deployment (pay per token)"

az_sub group create --name "$RG" --location "$LOCATION" --tags project=plan-a purpose=hackathon -o none
if ! az_sub cognitiveservices account show --name "$ACCOUNT" --resource-group "$RG" -o none 2>/dev/null; then
  az_sub cognitiveservices account create --name "$ACCOUNT" --resource-group "$RG" --location "$LOCATION" \
    --kind AIServices --sku S0 --custom-domain "$ACCOUNT" --allow-project-management --yes -o none
fi
if ! az_sub cognitiveservices account project show --name "$ACCOUNT" --resource-group "$RG" \
    --project-name "$PROJECT" -o none 2>/dev/null; then
  az_sub cognitiveservices account project create --name "$ACCOUNT" --resource-group "$RG" \
    --project-name "$PROJECT" --location "$LOCATION" -o none
fi
az_sub cognitiveservices account deployment create --name "$ACCOUNT" --resource-group "$RG" \
  --deployment-name "$DEPLOYMENT" --model-name "$MODEL" --model-version "$MODEL_VERSION" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity "$CAPACITY" -o none

SCOPE="$(az_sub cognitiveservices account show --name "$ACCOUNT" --resource-group "$RG" --query id -o tsv)"
ME="$(az ad signed-in-user show --query id -o tsv)"
az_sub role assignment create --assignee-object-id "$ME" --assignee-principal-type User --role "Azure AI User" \
  --scope "$SCOPE" -o none || echo "role assignment failed: ask the subscription owner to grant 'Azure AI User'"

cat <<EOF
Add to .env (never commit it):
FOUNDRY_PROJECT_ENDPOINT=https://$ACCOUNT.services.ai.azure.com/api/projects/$PROJECT
FOUNDRY_MODEL_SMALL=$DEPLOYMENT
FOUNDRY_MODEL_LARGE=$DEPLOYMENT
FOUNDRY_TENANT_ID=$PLAN_A_TENANT_ID
Then: uv run python -m agents.foundry_ping --dry-run && uv run python -m agents.foundry_ping
EOF
