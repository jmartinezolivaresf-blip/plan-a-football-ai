"""Chat clients: Microsoft Foundry (real) or the offline rules client (CI/tests).

Foundry auth is Entra ID through the Azure CLI login, pinned to one tenant; no API keys. Settings (.env.example):
FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_SMALL (analyst), FOUNDRY_MODEL_LARGE (manager, defaults to small) and
FOUNDRY_TENANT_ID (the directory of the subscription that hosts the project). Nothing here makes a network call;
the first one happens when an agent runs. See docs/FOUNDRY.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

Mode = Literal["offline", "foundry"]
Role = Literal["analyst", "manager"]

# Directories we must never run models in (D-046). Microsoft's corporate tenant id is public; more can be added
# through FOUNDRY_DENY_TENANTS (comma separated). The repository never stores subscription ids.
DENIED_TENANTS = frozenset({"72f988bf-86f1-41af-91ab-2d7cd011db47"})


class FoundryConfigError(RuntimeError):
    """AGENTS_MODE=foundry without a complete, allowed configuration."""


@dataclass(frozen=True)
class ModelChoice:
    mode: Mode
    analyst: str
    manager: str
    endpoint: str | None = None
    tenant_id: str | None = None


def model_choice(mode: Mode | None = None) -> ModelChoice:
    mode = mode or os.environ.get("AGENTS_MODE", "offline")  # type: ignore[assignment]
    if mode == "offline":
        from .offline import MODEL_NAME
        return ModelChoice("offline", MODEL_NAME, MODEL_NAME)
    if mode != "foundry":
        raise FoundryConfigError(f"AGENTS_MODE must be offline or foundry, not {mode!r}")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    small = (os.environ.get("FOUNDRY_MODEL_SMALL") or os.environ.get("FOUNDRY_MODEL") or "").strip()
    large = (os.environ.get("FOUNDRY_MODEL_LARGE") or "").strip() or small
    tenant = os.environ.get("FOUNDRY_TENANT_ID", "").strip().lower()
    missing = [k for k, v in (("FOUNDRY_PROJECT_ENDPOINT", endpoint), ("FOUNDRY_MODEL_SMALL", small),
                              ("FOUNDRY_TENANT_ID", tenant)) if not v]
    if missing:
        raise FoundryConfigError(f"AGENTS_MODE=foundry needs {', '.join(missing)} in .env (see docs/FOUNDRY.md)")
    if not endpoint.startswith("https://"):
        raise FoundryConfigError("FOUNDRY_PROJECT_ENDPOINT must be an https:// Foundry project endpoint")
    denied = DENIED_TENANTS | {t.strip().lower() for t in os.environ.get("FOUNDRY_DENY_TENANTS", "").split(",")
                               if t.strip()}
    if tenant in denied:
        raise FoundryConfigError("FOUNDRY_TENANT_ID is a denied (corporate) directory; use the directory of the "
                                 "hackathon subscription")
    return ModelChoice("foundry", small, large, endpoint, tenant)


@dataclass
class ChatClients:
    """One chat client per role for a staff's run, closed at the end (a Foundry client owns an Entra credential)."""

    choice: ModelChoice
    _clients: dict[str, Any] = field(default_factory=dict)
    _credentials: list[Any] = field(default_factory=list)

    def get(self, role: Role):
        if role not in self._clients:
            self._clients[role] = self._make(role)
        return self._clients[role]

    def _make(self, role: Role):
        if self.choice.mode == "offline":
            from .offline import OfflineRulesClient
            return OfflineRulesClient()
        from agent_framework_foundry import FoundryChatClient
        from azure.identity.aio import AzureCliCredential

        # pinned tenant: a CLI session in another directory fails instead of silently using it
        credential = AzureCliCredential(tenant_id=self.choice.tenant_id)
        self._credentials.append(credential)
        model = self.choice.analyst if role == "analyst" else self.choice.manager
        return FoundryChatClient(project_endpoint=self.choice.endpoint, model=model, credential=credential)

    async def aclose(self) -> None:
        for credential in self._credentials:
            await credential.close()
        self._credentials.clear()
        self._clients.clear()
