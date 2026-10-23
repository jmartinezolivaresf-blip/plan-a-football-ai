# mcp_server (person B)

Tools: `contracts/tools.md`. Policy: `policy.py` (pure Python). Server: `server.py` (MCP SDK 2.x `MCPServer`).

```bash
python -m mcp_server --scope KES                     # stdio
make mcp SCOPE=broadcast                             # streamable HTTP on 127.0.0.1:8765/mcp
ENGINE=real python -m mcp_server --scope HAR         # real engine (person A, I1)
```

## Trust model (D-026)

- **One server instance per scope.** The trusted host (the pre-match workflow, later the live/duel workflows) creates
  `ScopedTools(scope=...)` and the matching `MCPServer`; agents talk to it in-process (`mcp.Client(server)`), so there is
  no network listener at all for agents.
- **The scope is never read from a request.** No `X-Team-Scope` header is parsed; "own team" tools have no `team`
  argument; a staff passing someone else's plan/estimate/options gets `forbidden_scope`.
- **Only allowed tools are registered:** a staff server does not list `get_true_matrix` or `get_match_state`; the
  broadcast server does not list `seal_choice`, `price_matrix`, `simulate_plan`, ...
- **Private and broadcast-only claims:** staffs read public observed claims and their own `kpi_status`,
  `sim_valuation` and `opponent_estimate` claims only; matrix cells and regret only through their own tools / broadcast.
- **Time gating:** `visible_minute` (0 before kick-off) hides future match events and snapshots from staffs.
- **`get_true_matrix`:** broadcast only, and only after both benches sealed (`not_sealed_yet` otherwise).
- **HTTP mode is loopback-only** and refuses any other host: there is no client authentication yet, and anyone who could
  reach the port would get that server's scope. Any non-loopback deployment is an H3 decision.
- Every call is recorded server-side (`ScopedTools.calls`, `claims_served`): traces include tool calls made by the LLM
  itself, and `validate_plan` rejects evidence the staff never retrieved.
