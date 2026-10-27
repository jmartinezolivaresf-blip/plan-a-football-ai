# Shared guards for every Azure script in infra/ (sourced, not executed).
#
# - The subscription is ALWAYS explicit (PLAN_A_SUBSCRIPTION_ID) and passed to every az command; the CLI default is
#   never used, because the CLI can be signed in to subscriptions outside this project.
# - Subscriptions in the Microsoft corporate tenant are refused by tenant id; more subscriptions (names or ids) can be
#   refused through PLAN_A_DENY_SUBSCRIPTIONS (comma separated) or infra/deny.local (git-ignored, one per line), so no
#   other subscription's name is published in this repository (D-046).
# - Anything that can cost money needs PLAN_A_APPROVED=yes, set by the owner after approving infra/AZURE_PLAN.md.
# - Secrets (deployment tokens) are never printed or written to disk.

set -euo pipefail

PLAN_A_DENIED_TENANTS=("72f988bf-86f1-41af-91ab-2d7cd011db47")

denied_subscriptions() {
  local deny_file
  deny_file="$(dirname "${BASH_SOURCE[0]}")/deny.local"
  [[ -f "$deny_file" ]] && grep -vE '^\s*(#|$)' "$deny_file"
  [[ -n "${PLAN_A_DENY_SUBSCRIPTIONS:-}" ]] && tr ',' '\n' <<< "$PLAN_A_DENY_SUBSCRIPTIONS"
  return 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

load_env_file() {
  local root
  [[ "${PLAN_A_NO_DOTENV:-}" == "1" ]] && return 0  # tests: never the developer's real settings
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -f "$root/.env" ]]; then
    # only the PLAN_A_* deployment settings; never source the whole file into the shell
    while IFS='=' read -r key value; do
      [[ "$key" =~ ^PLAN_A_[A-Z_]+$ ]] || continue
      [[ -n "${!key:-}" ]] || export "$key=$value"
    done < <(grep -E '^PLAN_A_[A-Z_]+=' "$root/.env" || true)
  fi
}

require_subscription() {
  [[ -n "${PLAN_A_SUBSCRIPTION_ID:-}" ]] || die "set PLAN_A_SUBSCRIPTION_ID to the approved hackathon subscription id"
  command -v az >/dev/null || die "Azure CLI not found"
  local info name tenant denied
  # reads the local CLI profile only; fails if this subscription is not in it (az login --tenant <its tenant>)
  info="$(az account show --subscription "$PLAN_A_SUBSCRIPTION_ID" --query "[name, tenantId]" -o tsv 2>/dev/null)" \
    || die "subscription $PLAN_A_SUBSCRIPTION_ID is not in the local az profile: run az login --tenant <its tenant>"
  name="$(printf '%s\n' "$info" | sed -n 1p)"
  tenant="$(printf '%s\n' "$info" | sed -n 2p | tr '[:upper:]' '[:lower:]')"
  while IFS= read -r denied; do
    denied="$(sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' <<< "$denied")"
    [[ -n "$denied" ]] || continue
    if [[ "$name" == "$denied" || "$PLAN_A_SUBSCRIPTION_ID" == "$denied" ]]; then
      die "refusing to use the corporate subscription '$name'"
    fi
  done < <(denied_subscriptions)
  for denied in "${PLAN_A_DENIED_TENANTS[@]}"; do
    [[ "$tenant" == "$denied" ]] && die "refusing to use a subscription in a corporate tenant ($tenant)"
  done
  PLAN_A_SUBSCRIPTION_NAME="$name"
  PLAN_A_TENANT_ID="$tenant"
  echo "Subscription: $name ($PLAN_A_SUBSCRIPTION_ID), tenant $tenant"
}

require_approval() {
  [[ "${PLAN_A_APPROVED:-}" == "yes" ]] \
    || die "this step can create billable resources: set PLAN_A_APPROVED=yes once the owner approved infra/AZURE_PLAN.md ($*)"
}

az_sub() { az "$@" --subscription "$PLAN_A_SUBSCRIPTION_ID"; }
