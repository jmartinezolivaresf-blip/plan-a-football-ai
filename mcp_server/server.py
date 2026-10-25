"""MCP server for one fixed scope (KES, HAR or broadcast). See contracts/tools.md and policy.py.

    python -m mcp_server --scope KES                       # stdio (what the agent host uses)
    python -m mcp_server --scope broadcast --http          # streamable HTTP on 127.0.0.1 only

Only the tools allowed for the scope are registered, so a staff server does not even list `get_true_matrix`.
The scope comes from the process arguments chosen by the trusted host; request headers are never read (D-026).
"""

from __future__ import annotations

import argparse
import functools
import ipaddress
import json
import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from contracts import BROADCAST_SCOPE

from .engine_factory import get_engine
from .policy import ScopedTools

DEMO_MATCH = "m-demo-001"


def _json(payload: Any) -> str:
    """One text block with the whole JSON payload (lists stay lists, even with one item)."""
    return json.dumps(payload, ensure_ascii=False)


def build_server(tools: ScopedTools) -> MCPServer:
    server = MCPServer(name=f"plan-a-{tools.scope}", version="0.1.0",
                       instructions=f"Plan A match intelligence tools, scope {tools.scope}. Numbers come only from "
                                    "claims returned by these tools.")
    allowed = tools.allowed

    def reg(fn):
        """Register `fn` if the scope allows it; its result is sent as one JSON text block."""
        if fn.__name__ in allowed:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs) -> str:
                return _json(fn(*args, **kwargs))

            wrapper.__annotations__ = {**fn.__annotations__, "return": str}
            server.tool(name=fn.__name__)(wrapper)
        return fn

    @reg
    def list_matches(team: str) -> Any:
        """Matches in a team's season history."""
        return tools.call("list_matches", {"team": team})

    @reg
    def get_team_tendencies(team: str, aspect: str = "all") -> Any:
        """Observed tendencies of a team (claims with n and league reference)."""
        return tools.call("get_team_tendencies", {"team": team, "aspect": aspect})

    @reg
    def get_player_profile(player_id: str) -> Any:
        """Observed claims about one player (never hidden traits)."""
        return tools.call("get_player_profile", {"player_id": player_id})

    @reg
    def get_set_piece_profile(team: str) -> Any:
        """Set-piece claims of a team."""
        return tools.call("get_set_piece_profile", {"team": team})

    @reg
    def get_squad_condition(minute: int = 0) -> Any:
        """Your own squad's visible attributes and estimated condition."""
        return tools.call("get_squad_condition", {"minute": minute})

    @reg
    def simulate_plan(plan: dict, opponent_estimate: dict, R: int = 500) -> Any:
        """Value your plan against your own estimate of the opponent's plan."""
        return tools.call("simulate_plan", {"plan": plan, "opponent_estimate": opponent_estimate, "R": R})

    @reg
    def estimate_opponent_options() -> Any:
        """Your analyst's estimate of the opponent's half-time options."""
        return tools.call("estimate_opponent_options", {})

    @reg
    def price_matrix(own_options: list[dict], opponent_options: list[dict], opponent_probs: list[float],
                     R: int = 300) -> Any:
        """Your believed payoff matrix: your options x your estimate of the opponent's options."""
        return tools.call("price_matrix", {"own_options": own_options, "opponent_options": opponent_options,
                                           "opponent_probs": opponent_probs, "R": R})

    @reg
    def validate_plan(plan: dict | None = None, option: dict | None = None) -> Any:
        """Validate your plan or half-time option."""
        return tools.call("validate_plan", {"plan": plan, "option": option})

    @reg
    def seal_choice(option_id: str, rule: str = "best_guess") -> Any:
        """Seal your half-time choice (commit only) and the rule you chose it by."""
        return tools.call("seal_choice", {"option_id": option_id, "rule": rule})

    @reg
    def get_plan_status(minute: int, team: str | None = None) -> Any:
        """KPI status of a plan (staff: own plan only)."""
        return tools.call("get_plan_status", {"minute": minute, "team": team})

    @reg
    def get_match_state(minute: int) -> Any:
        """Match snapshot at a minute (broadcast)."""
        return tools.call("get_match_state", {"minute": minute})

    @reg
    def get_events(filter: dict | None = None) -> Any:
        """Match events visible at this point of the match."""
        return tools.call("get_events", {"filter": filter})

    @reg
    def get_claim(claim_id: str) -> Any:
        """One claim by id (staff: public claims and your own)."""
        return tools.call("get_claim", {"claim_id": claim_id})

    @reg
    def get_true_matrix() -> Any:
        """The real half-time matrix and regret (broadcast only, after both seals)."""
        return tools.call("get_true_matrix", {})

    return server


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mcp_server")
    ap.add_argument("--scope", required=True, help="KES | HAR | broadcast (set by the trusted host)")
    ap.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    ap.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8765")))
    ap.add_argument("--visible-minute", type=int, default=None, help="latest visible minute (default 0 for staff)")
    args = ap.parse_args(argv)
    engine = get_engine()
    meta = getattr(engine, "meta", None) or getattr(getattr(engine, "bundle", None), "meta", None)
    home, away = (meta.home, meta.away) if meta else ("KES", "HAR")
    if args.scope not in (home, away, BROADCAST_SCOPE):
        ap.error(f"unknown scope {args.scope}")
    visible = args.visible_minute if args.visible_minute is not None else (90 if args.scope == BROADCAST_SCOPE
                                                                            else 0)
    match_id = meta.match_id if meta else DEMO_MATCH
    tools = ScopedTools(engine=engine, scope=args.scope, home=home, away=away, match_id=match_id,
                        visible_minute=visible)
    server = build_server(tools)
    if not args.http:
        server.run("stdio")
        return 0
    if not _loopback(args.host):
        ap.error("H1 serves MCP over HTTP on loopback only (no client authentication yet); see docs/DECISIONS.md D-026")
    server.run("streamable-http", host=args.host, port=args.port)
    return 0
