# H1 prompt: Person A (simulation and engine)

Act as a senior Python engineer specialised in vectorised simulation (NumPy) and football analytics. You are
**Person A** on *Plan A: The Battle of the Benches*. Your teammate (Person B) works in parallel on agents, the
MCP server and the web app. Your job in this session is **H1 for Person A only**.

## Repository

- Private repo: `https://github.com/jmartinezolivaresf-blip/plan-a-football-ai` (branch `main`).
- Setup: `uv python install 3.12 && make setup`, then `make h0` must pass before you change anything.
- Read fully before writing code:
  1. `docs/plan/PLAN_A_v6.md` §9.1–§9.4 (contracts, simulator, levers, traits) and §8 (architecture rules).
  2. `docs/plan/PLAN_A_v6_EJECUCION.md` §2, §3, §5 (Friday), §7, §9.
  3. `docs/START_HERE.md`, `docs/DECISIONS.md`, `contracts/sim_api.md`, `contracts/sim_types.py`,
     `contracts/engine_api.md`, `contracts/*.py`.
- These documents are the source of truth. Do not redesign the product or add features.

## Ownership

- You own: `sim/`, `sim/render/`, `engine/`, `eval/`, `data/`.
- Shared (change only through a PR labelled `contract`, approved by both): `contracts/`, `fixtures/`, `tests/`
  (you may **add** new test files under `tests/` for your code), `docs/`, `Makefile`.
- Do not touch: `mcp_server/`, `agents/`, `web/`, `infra/`.

## Goal: H1 (Friday 22:00)

Implement `simulate()` and `fork()` exactly as specified in `contracts/sim_api.md`:

```python
def simulate(plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1, log: bool = False,
             start: MatchState | None = None, until_minute: int = 90) -> SimResult: ...
def fork(state: MatchState, overrides: dict[str, Option], R: int, seed: int) -> Outcomes: ...
```

### Known contract gap to resolve first (small PR labelled `contract`)

Hidden traits must reach the simulator, but `simulate()` has no parameter for them. Add **keyword-only, optional**
parameters `truth: Truth | None = None, config: SimConfig | None = None` to `simulate()` (and carry them inside
`fork()` via the state or the same keywords), update `contracts/sim_api.md`, and add entry **D-019** in
`docs/DECISIONS.md`. Do not change any other contract. With `truth=None` the simulator runs with no traits.

### Implementation order (from the execution plan, Friday)

1. **State and RNG (`sim/state.py`)**: numpy arrays `(R,)` for ball zone, possessing team, carrier index,
   clock, score, active levers, subs used; `(R, 22)` for fatigue. Seed scheme indexed by `(replica, step, use)`
   so that forks from the same state and seed consume the **same uniforms** (common random numbers).
2. **Core loop (`sim/core.py`)**: one step advances one action in all live replicas; finished replicas masked.
   18 zones (6 bands × 3 lanes, `contracts.common.zone_index`). Actions: short pass, progressive pass, long ball,
   carry, cross (outer lanes, bands 5–6), shot; softmax weights from zone, `build_up`, `attack_channel`, score.
   Success: `logit p = α[action, zone] + β_s·(skill−50)/50 − β_p·Pressure_opp(zone)·(1 − press_resistance) +
   β_f·(fatigue_opp − fatigue_own)`. `Pressure_opp` depends on the opponent's `press_height` (high: own bands
   1–3; mid: 3–4; low: 5–6), `press_target` (extra pressure when that player receives) and fatigue. Failure →
   loss in that zone; a win in the opponent's half opens a 10 s counter window. 2–6 s per action plus stoppages
   for ~55–60 min ball in play.
3. **Shots, goals, corners, fatigue, subs, Plan B, levers**: internal goal probability by zone and context
   (counter, header after cross); corner micro-model (`near_post | far_post | short` × marking × aerial duels ×
   `back_post_weak` trait) targeting ~10 corners and ~0.03–0.05 goals per corner; fatigue `s ∈ [0,1]` with ×1.4
   cost under `press_height=high`, pressure efficacy × (0.6 + 0.4·s); 5 subs in 3 windows + HT; Plan B triggers
   evaluated every minute (KPI-status triggers may use simple sim-side counters at H1; the real Plan Tracker is
   engine work on Saturday). The 5 levers of §9.3 and the interaction matrix of §9.2 must have an effect.
4. **`R == 1, log=True`** returns `events[]` and `snapshots[]` that validate against `contracts.Event` /
   `contracts.Snapshot`, absolute coordinates, attack direction per period as in `MatchMeta.attack`. Snapshots:
   leave `condition_est` and `kpis` empty (the engine publishes its own estimates; never expose sim fatigue).
   With `R > 1`, return only `outcomes` (per-replica goals, xPts = 3·P(win)+P(draw), 90% intervals).
5. **`fork(state, overrides, R, seed)`** from the half-time `MatchState`, applying `{"KES": Option, "HAR":
   Option}` (lever changes and subs). Same `seed` for every combination.
6. **Benchmark** (`sim/bench.py`, add `make bench`): `R=500` second halves from a half-time state, wall time on
   one core, printed and recorded in `docs/DECISIONS.md`. Target ≤ 1 s. If not met, apply the H1 cut in the
   execution plan §9 (R = 300, no `corner_delivery`, linear fatigue) and log it.

### Tests you must add (`tests/test_sim_*.py`) and keep green

- Possession continuity, completed passes chain to the receiver, strictly increasing clock, zones match
  coordinates, period matches clock (reuse the checks in `tests/test_fixture_coherence.py`).
- Score in snapshots == goal events; subs ≤ 5 in ≤ 3 windows + HT; no player acts after being subbed off.
- Determinism: same inputs → identical output; different seed → different match.
- `R=1` result equals the matching replica of an `R>1` run with the same seed.
- CRN: `fork` with identical overrides returns identical outcomes; Stay/Stay fork equals continuing the match.
- Levers matter (smoke tests on the §9.2 interaction table, e.g. `press_height=high` vs a short-building,
  low-press-resistance opponent produces more high turnovers than `press_height=low`, over enough replicas).
- Sanity ranges over ~200 matches: goals, shots, passes and corners per match in plausible ranges (full
  calibration is Sunday).
- The package `engine` still never imports `contracts.eval_only` (existing test must stay green).

## Rules

- Respect the contracts exactly. If a contract seems wrong, stop, explain, and propose a `contract` PR; do not
  silently diverge.
- One simulator function: no second code path for logging vs Monte Carlo.
- Only `sim/` and `eval/` may import `contracts.eval_only`.
- NumPy only (no numba unless the benchmark fails and you log the decision).
- Small PRs (< 1 day), branch names `a/<topic>`, CI green on every PR. Do not push to `main` directly.
- Never claim a test or benchmark result you have not run.
- Code and docs in English.

## Out of scope for this session

Teams with hidden traits generator, synthetic season, scouting functions, Plan Tracker, `price_matrix` on real
sims, evaluation E1–E8, calibration, render layer (all Saturday onwards). Agents, MCP, web.

## Definition of done (H1, Person A)

- `simulate()` plays 90' from the two fixture plans (`fixtures/plans_fixture.json`) with `R=1, log=True`; the
  events and snapshots validate against the contracts.
- All new invariant, determinism, CRN and lever tests green; `make h0` still green.
- Benchmark run and recorded (or the H1 cut applied and logged).
- PRs open/merged with CI green.

## Final report I expect from you

What you built (files), exact commands to reproduce, test results (counts, real output), benchmark numbers,
decisions logged, open issues, and what Person B can rely on from your side at I1 (Saturday 13:00).
