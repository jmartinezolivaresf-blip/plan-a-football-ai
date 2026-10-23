# Start here: parallel work from H0 to H1

Plan: `docs/plan/PLAN_A_v6.md` (what) and `docs/plan/PLAN_A_v6_EJECUCION.md` (how). Decisions: `docs/DECISIONS.md`.

## Interfaces you must respect

| Interface | File | Owner |
|---|---|---|
| Data contracts (Pydantic) | `contracts/*.py` → `contracts/schemas/*.schema.json` | shared (PR `contract`) |
| Simulator API | `contracts/sim_api.md`, `contracts/sim_types.py` | A |
| Engine API | `contracts/engine_api.md`, `contracts/engine_api.py` (`EngineAPI` Protocol) | A |
| MCP tools | `contracts/tools.md` | B |
| Bundle consumed by the web | `match_bundle.schema.json` → `web/src/contracts/bundle.ts` | B |

Changing any of them: update model → `make schemas fixtures web-types` → tests green → PR labelled `contract`
approved by both → entry in `docs/DECISIONS.md`.

## Person A: simulation and engine (`sim/`, `engine/`, `eval/`, `data/`)

First, in this order (H1, Friday 22:00):
1. `sim/state.py`: vectorised state `(R,)` / `(R, 22)`, 18 zones, seed scheme indexed by `(replica, step, use)`.
2. `sim/core.py`: `simulate()` per `contracts/sim_api.md`: action softmax, success logit, losses, clock, masking,
   `R == 1` + `log=True` emitting `Event`/`Snapshot` contracts.
3. Shots and goals, corner micro-model, fatigue, subs (5 in 3 windows + HT), Plan B triggers, the 5 levers.
4. `tests/test_sim_invariants.py`: possession continuity (reuse the checks in `tests/test_fixture_coherence.py`),
   score = goal events, sub limits, determinism by seed, `R=1` equals the matching replica of `R>1`.
5. `fork(state, overrides, R, seed)` from the half-time snapshot; performance benchmark.

Rules: `sim/` may import `contracts.eval_only`; `engine/` must not (tested). `engine/duel.py` already exists:
reuse it inside `price_matrix`.

## Person B: agents and product (`mcp_server/`, `agents/`, `web/`, `infra/`)

First, in this order (H1, Friday 22:00):
1. Day-0 Azure (needs a subscription owner, see "Costs and permissions"): Foundry project, 2 model deployments,
   quota check, App Insights. Fill `.env` from `.env.example`.
2. `uv pip install -e ".[agents]"` and confirm the Agent Framework and MCP APIs against the pinned versions.
3. `mcp_server/server.py`: the tools in `contracts/tools.md` over streamable HTTP, backed by `MockEngine`;
   `X-Team-Scope` filtering; scope tests (KES cannot read HAR; `get_true_matrix` forbidden for staff and before
   both seals).
4. Analyst + manager pre-match agents against the mock; plan output validated with `contracts.Plan`;
   `contracts.sealing.plan_digest` for the seal.
5. Web: replace the H0 inspector with `Pitch2D`, `Scorebug`, `PlanCard`, `SealBadge`, reading
   `web/public/match_bundle.json`.

## Working against the mock (no simulator needed)

```python
from mcp_server.mock_engine import MockEngine
engine = MockEngine()                       # reads fixtures/match_bundle_fixture.json
engine.get_team_tendencies("HAR", "build_up")
engine.price_matrix("m-demo-001", [], [], 300, "KES", [0.5, 0.15, 0.35])   # KES believed matrix
engine.seal_choice("m-demo-001", "KES", "KES-HT-B"); engine.seal_choice("m-demo-001", "HAR", "HAR-HT-Z")
engine.true_matrix("m-demo-001")            # only after both seals, else NotSealedYet
```

Canned tool payloads per scope: `fixtures/tools_canned/<tool>.<scope>.json`. At I1 (Saturday 13:00) the MCP
server switches with `ENGINE=real`; the real engine must pass `isinstance(engine, contracts.engine_api.EngineAPI)`.

## Commands

```bash
make setup             # .venv (Python 3.12) + Python deps + npm ci
make check             # schemas fresh, fixtures fresh, ruff, pytest
make h0                # check + TS types fresh + web build
make web-dev           # http://localhost:5173 with the fixture bundle, no backend
make schemas fixtures web-types   # after changing a contract
```

## H0: done when

- [x] `make h0` exits 0 locally (schemas, fixtures, lint, tests, TS types, web build).
- [ ] Contracts and fixtures committed on `main` and pushed to a **public** GitHub repo.
- [ ] CI green on GitHub.
- [ ] A Foundry model answers a test prompt (person B, day-0 Azure).
- [ ] Representative and provisional category recorded in `docs/DECISIONS.md`.

## H1 (Friday 22:00): done when

- **A:** `simulate()` plays 90' from the two fixture plans with `R=1, log=True`; the output validates against
  `MatchBundle` events/snapshots; invariants and determinism tests green; benchmark recorded: `R=500` second
  halves in ≤ 1 s on one core (or the H1 cut in the execution plan §9 is applied and logged).
- **B:** the MCP server answers every tool in `contracts/tools.md` from `MockEngine` with scope tests green, and
  a manager agent produces a `Plan` that validates and seals, calling at least one MCP tool (trace captured).

## Costs and permissions (nothing has been provisioned)

Day-0 Azure needs a subscription where you can create a resource group, a Foundry project and model
deployments. Model usage is billed per token; Container Apps with min replicas 1 and Application Insights have
small ongoing costs until the 10 Nov judging deadline. Set a budget alert first.
