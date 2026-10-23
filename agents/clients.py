"""Chat clients: Microsoft Foundry (real) or the offline rules client (CI/tests).

Foundry auth uses Entra ID through azure-identity (`az login` locally, managed identity when deployed); no API keys.
Settings (see .env.example): FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_LARGE (manager), FOUNDRY_MODEL_SMALL (analyst).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Mode = Literal["offline", "foundry"]


@dataclass(frozen=True)
class ModelChoice:
    mode: Mode
    analyst: str
    manager: str


def model_choice(mode: Mode | None = None) -> ModelChoice:
    mode = mode or os.environ.get("AGENTS_MODE", "offline")  # type: ignore[assignment]
    if mode == "offline":
        from .offline import MODEL_NAME
        return ModelChoice("offline", MODEL_NAME, MODEL_NAME)
    small = os.environ.get("FOUNDRY_MODEL_SMALL") or os.environ.get("FOUNDRY_MODEL")
    large = os.environ.get("FOUNDRY_MODEL_LARGE") or small
    if not os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or not small:
        raise RuntimeError("AGENTS_MODE=foundry needs FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_SMALL in .env")
    return ModelChoice("foundry", small, large)


def chat_client(choice: ModelChoice, role: Literal["analyst", "manager"]):
    if choice.mode == "offline":
        from .offline import OfflineRulesClient
        return OfflineRulesClient()
    from agent_framework_foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    model = choice.analyst if role == "analyst" else choice.manager
    return FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], model=model,
                             credential=DefaultAzureCredential())
