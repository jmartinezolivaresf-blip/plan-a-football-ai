# Architecture

Plan A is a pipeline that turns a synthetic season into one replayable match: two AI coaching staffs scout each
other, seal plans, play a simulated first half, make a blind half-time call, and a broadcast layer explains it.
The web app plays the resulting `match_bundle.json` with no backend.

```
                 sim.season (6 fictional clubs, 8 past matches each, hidden traits)
                        │ public events + squads            │ hidden truth (eval_only)
                        ▼                                   ▼
   ┌──────────── engine.RealEngine ─────────────┐     pipeline/ only
   │ scouting claims · xG · valuation · tracker │◄── true_world  (plays the demo match,
   │ adaptation detector · duel matrices        │                 prices the true matrix)
   │ public_world · belief_world(beliefs)       │
   └──────┬─────────────────┬───────────────────┘
          │ ScopedTools(KES) │ ScopedTools(HAR)      ScopedTools(broadcast)
          ▼ MCP (in-process) ▼ MCP (in-process)      ▼
   KES staff: analyst,  HAR staff: analyst,      Director: cues from claims,
   manager, duel bench  manager, duel bench      true matrix after both seals
          └───────────── sealed plans · sealed choices ─────────────┘
                                   ▼
                    pipeline.build → web/public/match_bundle.json → React app
```

## Layers

| Layer | Package | What it does |
|---|---|---|
| Contracts | `contracts/` | Pydantic models are the source of truth; JSON Schemas and TS types are generated from them. `eval_only.py` holds the hidden truth types and is never imported by engine, MCP server or agents (test-enforced). |
| Simulator | `sim/` | Vectorised zone-based match model (NumPy). Counter-based RNG (replica, step, use) gives common random numbers, so forks of the same state differ only by the decision being compared. `fork()` replays the second half from the exact half-time state. |
| Season | `sim/season.py` | 6 clubs, 18-player squads, archetypes, 3 hidden traits per club, 24 past matches (a round robin plus 3 return rounds: 8 per club). Test-split clubs: HAR, ASH. |
| Engine | `engine/` | Everything a staff can know: scouting claims from season events (with league reference and sample size), an xG model fitted on the season, plan valuation (paired bootstrap intervals), the 4-KPI Plan Tracker with expected curves from pre-match sims, an online adaptation detector, believed and true payoff matrices and regret. |
| MCP server | `mcp_server/` | One server per scope (KES, HAR, broadcast). The scope is fixed by the host, never read from a request; only the scope's tools are registered; future events are hidden from staffs. HTTP mode binds 127.0.0.1 only. |
| Agents | `agents/` | Microsoft Agent Framework `Agent`s (analyst, manager, duel bench) that work only through MCP tools. `AGENTS_MODE=foundry` uses Microsoft Foundry models; `offline` uses a deterministic rules client with the same agents and tools. Validators reject plans that cite claims the staff never retrieved and any text with numbers that are not `{claim_id.field}` placeholders. |
| Pipeline | `pipeline/` | The only code that holds the hidden truth. Builds the season, runs pre-match, plays the match, runs the duel, writes the bundle; seed search with documented story criteria. |
| Web | `web/` | React 19 + TypeScript + Vite. Broadcast view (pitch, scorebug, Plan Tracker, cues), half-time Duel (rooms, browser-verified seals, payoff matrix), analyst desk (evidence, traces, believed vs real matrix, validation panel). |
| Evaluation | `eval/` | E1-E8 and calibration on seasons not used for development (see README). |

## Three worlds (D-033)

| World | Built from | Used for |
|---|---|---|
| `public_world` | no hidden traits | expected KPI curves of the Plan Tracker |
| `belief_world(beliefs)` | what a bench's own scouting suspects (`engine/beliefs.py`) | that bench's plan valuation and believed half-time matrix |
| `true_world` | hidden truth | playing the demo match; the true matrix, priced only after both benches sealed |

A bench never sees the other bench's options, its believed matrix or the true matrix before the reveal; the
pipeline checks this and a test asserts it on the bundle.

## Sealing

- Plans: SHA-256 over canonical JSON of the plan (excluding the seal itself), sealed before kick-off; the browser
  recomputes it with Web Crypto.
- Half-time choices: commit-reveal with a random 128-bit salt (SHA-256 over canonical JSON of match id, team, option
  id and salt), so a 3-option choice cannot be brute-forced from the commit before the reveal. The bundle carries the
  commit, the revealed option and the salt; the browser recomputes the commit.

## Numbers come from claims

Every number shown to a viewer is a field of a claim (`{claim_id.value}`, `.n`, `.interval_low`, ...). LLM text
and broadcast cues are verified by code before they are kept: any digit outside a placeholder (other than player
identifiers) rejects the text. Claims carry sample size, league reference, intervals and a sufficient/insufficient
status.

## Reproducibility

The same seeds give the same bundle, independent of process hash seed and of whether the pre-match is computed in
place or replayed (tests in `tests/test_real_engine.py`); only the random commit-reveal salts and wall-clock fields
differ between runs. Seeds: pre-match valuation 101, match 202 (demo: see
README), believed matrices 303, true matrix 404. Monte Carlo sizes: 300 replicas per plan valuation and believed
cell, 500 per true cell.
