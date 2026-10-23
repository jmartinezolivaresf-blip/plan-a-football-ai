# Plan A: The Battle of the Benches

Two AI coaching staffs, each blind to the other's private information, scout a fictional opponent, seal a game plan
before kick-off and make a simultaneous half-time call. Every call is priced against the other bench's possible
answers with Monte Carlo forks of the same match, and after the reveal the broadcast shows what each bench believed
next to what was really true. Built for the Microsoft + Premier League *Inside the Game* hackathon.

> **Data statement.** All data is synthetic. Clubs and players are fictional. No Premier League data, names or marks
> are used. Every number is produced inside our own simulator and is not a prediction about real football.

**Demo:** <!-- DEMO_URL --> not deployed yet (see `infra/AZURE_PLAN.md`). Run it locally in two commands below.

## What you see

1. **Pre-match.** Each staff (an analyst and a manager agent) scouts the other club from 8 past matches through
   its own MCP tools, proposes plans, values them in simulation against its estimate of the opponent, and seals one
   (SHA-256, verified in your browser).
2. **First half.** A live Plan Tracker follows each plan's KPIs against the curve the staff expected; a detector
   flags when a team changes how it builds up.
3. **Half-time Duel.** Both benches choose at the same time from three options, without seeing each other's. Each
   prices a payoff matrix with *its own* beliefs and seals its choice (salted commit-reveal). Only after both seals
   does the broadcast price the true matrix.
4. **Full time.** Whose plan worked, which KPIs held, and the regret of each call: the xPts left on the table
   against the best answer to what the other bench really did, with an interval.

<!-- DEMO_STORY -->

Deep links open any moment: `?t=45:00&reveal=1&mode=analyst`, `?t=90:00`, `?tab=desk&lang=es&club=HAR`.

## Why it is agentic

- **Two adversarial teams of agents with private information.** Each staff only reaches the world through MCP
  tools scoped to its club; the scope is fixed by the host, never by the request, and the other bench's options,
  matrix and choice are unreachable (tested).
- **Commitments.** Plans and half-time choices are sealed before anything that could change them is revealed.
- **Grounded by construction.** Agents write `{claim_id.field}` placeholders, never digits; code fills them from
  claims and rejects any text that is not grounded. Plans must cite claims the staff actually retrieved.
- **Decisions under uncertainty, then accountability.** Believed vs true matrices and regret make each agent's
  reasoning checkable after the fact.

## Microsoft technology

| Piece | Status |
|---|---|
| Microsoft Agent Framework (`agent-framework-core` 1.23.0): analyst, manager and duel-bench agents with MCP tools | used in every run |
| Model Context Protocol (MCP SDK 2.3.0): one scoped server per club and one for the broadcast | used in every run |
| Microsoft Foundry (`agent-framework-foundry`, Entra ID, no keys): `AGENTS_MODE=foundry` | implemented; **not yet called against a real deployment** (needs an approved Azure resource, `infra/AZURE_PLAN.md`) |
| Azure Static Web Apps (Free) for the public demo | planned, needs approval |

Without Azure, the same agents run with a deterministic offline rules client (`AGENTS_MODE=offline`), which is what
CI and the current demo bundle use; the bundle says which model produced it (`eval.build.models`).

## Results (inside our simulator)

Full tables: [`eval/results/RESULTS.md`](eval/results/RESULTS.md) (generated from the JSON results).

<!-- RESULTS_HEADLINE -->
| Test | What it measures | Result |
|---|---|---|
| E1 | Scouting reports vs hidden truth, 30 clubs in 5 unseen seasons with random trait kinds | precision 0.492, recall 0.333 (61 flagged, 90 real traits) |
| E2 | Monte Carlo noise: R=300 vs R=3000 for 6 lever changes from one half-time state | mean abs error 0.018 xPts; 90% CI covers the reference 1.0; sign agreement 0.667 overall, 1.0 on the 2 cells whose reference interval excludes zero |
| E3 | Plans that target a real hidden weakness (12 plans) | 1.0 vs 0.536 for a blind random plan; levers citing claims the staff retrieved 1.0 |
| E4 | Grounded text | reports valid at first try 1.0; cues dropped by the verifier 0; numbers written by the model 0 (by construction) |
| E7 | Probability a bench gave to what the other bench really did | 0.383 (90% CI 0.342 to 0.425, n 12); uniform guess 0.333 |
| E8 | Half-time regret (xPts lost vs the best answer to the other bench's real choice) | AI 0.02 (90% CI 0.0 to 0.044, n 12); always stay 0.078 (90% CI 0.042 to 0.122, n 12); random 0.066 (90% CI 0.041 to 0.098, n 12) |
<!-- /RESULTS_HEADLINE -->

The scouting thresholds were developed on season 2026 (the demo season); E1 runs on seasons whose trait kinds were
drawn at random and never inspected. Simulator knobs were calibrated on dev seasons only. Disclosures:
`docs/DECISIONS.md` (D-036, D-038, D-042, D-043).

## Run it

Requirements: [uv](https://docs.astral.sh/uv/) (installs Python 3.12) and Node.js 22+.

```bash
make setup        # .venv + Python and web dependencies
make web-dev      # http://localhost:5173 with the committed demo bundle, no backend
```

Rebuild everything from scratch (offline mode, about a minute per match on a laptop):

```bash
make bundle SEED=226        # season -> pre-match -> first half -> duel -> second half -> web/public/match_bundle.json
make seed-search N=48       # how the demo seed was chosen (criteria in pipeline/build.py, STORY_CRITERIA)
make eval                   # calibrations on dev seasons, E1-E8, eval/results/RESULTS.md
make check                  # lint, schemas, fixtures, tests
```

With Microsoft Foundry: `cp .env.example .env`, set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_SMALL`, `az login`,
then `uv run python -m agents.foundry_ping` and `AGENTS_MODE=foundry make bundle SEED=226`.

## Layout

```
contracts/    Pydantic contracts (source of truth) -> JSON Schemas -> TypeScript types
sim/          Vectorised match simulator, synthetic season, render layer
engine/       Scouting claims, xG, plan valuation, Plan Tracker, adaptation detector, duel matrices, regret
mcp_server/   Scoped MCP tools (KES, HAR, broadcast); loopback only
agents/       Microsoft Agent Framework agents, offline rules client, validators, broadcast director
pipeline/     The only holder of the hidden truth: builds the demo bundle, seed search
eval/         Calibrations, E1-E8, results
web/          React + TypeScript + Vite app (static)
docs/         Architecture, decisions, plan, submission checklist, video script
```

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Every design decision and disclosure:
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Rules enforced by tests

- Engine, MCP server and agents never import the hidden truth (`contracts.eval_only`).
- A bench's private duel data never contains the true matrix or the other bench's options or choice.
- Plan seals and choice commits verify; salts are random; regret is non-negative and matches the true matrix.
- Every broadcast cue passes the text verifier; the bundle contains no hidden trait.
- The simulator's KPI counters equal the engine's event definitions; the same seed gives the same bundle in any
  process.

## License

MIT, see `LICENSE`.
