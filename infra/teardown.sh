#!/usr/bin/env bash
# Delete everything Plan A created (after judging ends on 10 Nov 2026). Destructive: asks you to type the group name.
#
#   PLAN_A_SUBSCRIPTION_ID=<id> infra/teardown.sh

source "$(dirname "$0")/lib.sh"
load_env_file
RG="${PLAN_A_RESOURCE_GROUP:-rg-plan-a}"
require_subscription
echo "This deletes resource group '$RG' and everything in it from subscription $PLAN_A_SUBSCRIPTION_NAME."
az_sub resource list --resource-group "$RG" --query "[].{name:name, type:type}" -o table
read -r -p "Type the resource group name to confirm: " answer
[[ "$answer" == "$RG" ]] || die "not confirmed"
az_sub group delete --name "$RG" --yes
