# Plan A: The Battle of the Benches

Two AI coaching staffs, each blind to the other's private information, scout a fictional opponent, seal a game
plan before kick-off and make a simultaneous half-time call. Every decision is priced against the other bench's
answer with Monte Carlo forks of the same match. Built for the Microsoft + Premier League *Inside the Game*
hackathon.

> **Data statement.** All data is synthetic. Clubs and players are fictional. No Premier League data is used.
> The current `fixtures/` are **hand-scripted and illustrative** (not simulated) so that agents and UI can be
> built before the simulator exists.

Status: **H0** (contracts, fixtures, mocks, CI). See `docs/START_HERE.md`.

## Layout

```
contracts/    Pydantic contracts (source of truth), exported JSON Schemas, sim/engine/tools API docs
fixtures/     Illustrative fixtures + canned MCP tool responses, built by fixtures/build_fixtures.py
sim/          Vectorised simulator (person A)
engine/       Scouting, KPIs, valuation, duel reading (person A)
eval/         E1–E8 evaluation, calibration (person A)
mcp_server/   MCP tools with team scopes; mock_engine.py for development (person B)
agents/       Microsoft Agent Framework roles, workflows, validators (person B)
web/          React + TypeScript + Vite; plays match_bundle.json with no backend (person B)
infra/        Azure deployment notes (person B)
tests/        Shared tests
docs/         Plan (docs/plan), decisions, start guide, Copilot usage
```

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for the project)
- Node.js 22+ and npm

## Setup and run

```bash
uv python install 3.12
make setup        # .venv + Python deps + web deps
make h0           # schemas, fixtures, lint, tests, TS types, web build
make web-dev      # open http://localhost:5173 (fixture bundle, no backend)
```

Individual commands: `make help`.

## Rules that are enforced by tests

- The engine, MCP server and agents never import `contracts.eval_only` (hidden truth, simulator config).
- A bench's private duel data never contains the true matrix or the opponent's real options or choice.
- Plans and half-time choices are sealed with SHA-256 (salted commit-reveal for choices) and verifiable.
- Text uses `{claim_id.field}` placeholders; numbers come from claims, not from the LLM.

## License

MIT, see `LICENSE`.
