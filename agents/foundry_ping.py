"""Check the Microsoft Foundry connection. Not run in CI.

    uv run python -m agents.foundry_ping --dry-run   # validate .env and build the clients: no network call
    uv run python -m agents.foundry_ping             # ONE real call per role (a few dozen tokens each)

Needs `az login --tenant $FOUNDRY_TENANT_ID` and the settings in .env (docs/FOUNDRY.md). Prints the endpoint host,
deployment, latency and reply; never prints credentials or tokens. Exit code 0 only if every role answered.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .settings import load_env


async def _ping(dry_run: bool) -> int:
    from agent_framework import Agent

    from .clients import ChatClients, model_choice

    choice = model_choice("foundry")
    print(f"endpoint host: {choice.endpoint.split('/')[2]}")
    print(f"tenant pinned: {choice.tenant_id}")
    chat = ChatClients(choice)
    ok = True
    try:
        for role, deployment in (("analyst", choice.analyst), ("manager", choice.manager)):
            client = chat.get(role)
            if dry_run:
                print(f"{role}: deployment {deployment} -> {type(client).__name__} built (dry run, no call)")
                continue
            agent = Agent(client, "Reply with exactly: PLAN-A-OK", name=f"foundry-ping-{role}")
            t0 = time.perf_counter()
            resp = await agent.run("ping")
            ms = int((time.perf_counter() - t0) * 1000)
            text = (resp.text or "").strip()
            raw = getattr(resp.raw_representation, "raw_representation", None) or resp.raw_representation
            usage = dict(resp.usage_details or {})
            print(f"{role}: deployment {deployment}, latency {ms} ms, reply {text[:80]!r}; service model "
                  f"{getattr(raw, 'model', None)}, response id {resp.response_id}, tokens in/out "
                  f"{usage.get('input_token_count')}/{usage.get('output_token_count')}")
            ok = ok and "PLAN-A-OK" in text
            if choice.analyst == choice.manager:
                break  # same deployment: one call is enough
    finally:
        await chat.aclose()
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agents.foundry_ping")
    ap.add_argument("--dry-run", action="store_true", help="validate settings and build clients without calling")
    args = ap.parse_args(argv)
    load_env()
    try:
        return asyncio.run(_ping(args.dry_run))
    except Exception as exc:  # report the failure class without dumping credentials
        print(f"Foundry check failed: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
