"""Manual check that Microsoft Foundry answers (H0 closure). Not run in CI.

    az login                       # Entra ID; no API keys
    cp .env.example .env           # set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_SMALL
    uv run python -m agents.foundry_ping

Prints the model deployment, latency and the reply. Never prints credentials or tokens.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv


async def _ping() -> int:
    from agent_framework import Agent

    from .clients import chat_client, model_choice

    choice = model_choice("foundry")
    agent = Agent(chat_client(choice, "analyst"), "Reply with exactly: PLAN-A-OK", name="foundry-ping")
    t0 = time.perf_counter()
    resp = await agent.run("ping")
    ms = int((time.perf_counter() - t0) * 1000)
    text = (resp.text or "").strip()
    print(f"endpoint host: {os.environ['FOUNDRY_PROJECT_ENDPOINT'].split('/')[2]}")
    print(f"model deployment: {choice.analyst}")
    print(f"latency: {ms} ms")
    print(f"reply: {text[:200]!r}")
    return 0 if "PLAN-A-OK" in text else 2


def main() -> int:
    load_dotenv()
    try:
        return asyncio.run(_ping())
    except Exception as exc:  # report the failure class without dumping credentials
        print(f"Foundry call failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
