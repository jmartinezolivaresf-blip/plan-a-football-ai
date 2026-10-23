# Decisions log

Format: ID · date · context → decision · who. Contract changes need a PR labelled `contract` approved by both.

## H0 (2026-10-23)

**D-001 · Repo.** Repository root is `plan-a/`. The Spanish planning docs are copied verbatim to `docs/plan/`
(source of truth). Code and technical docs are in English.

**D-002 · Contracts as a Python package.** `contracts/` holds the Pydantic models (source of truth), the exported
JSON Schemas (`contracts/schemas/`) and the API docs. Schemas are exported in *serialization* mode with defaulted
fields marked required, because they describe files we write (fixtures, bundle). Inputs (e.g. LLM structured
output) are validated with the Pydantic models directly.

**D-003 · Contradiction: `price_matrix` signature.** v6 §9.13 has `price_matrix(match_id, team, own_options[],
opponent_options[], R)`; the execution plan §3.3 has `price_matrix(match_id, own_options, opponent_options, R,
perspective)`. → Engine signature follows the execution plan plus `opponent_probs` (needed for the best-guess
reading). The MCP tool has **no team argument**: the server sets `perspective` from `X-Team-Scope`. Same rule
for every "own team" tool (`get_squad_condition`, `estimate_opponent_options`, `seal_choice`, `get_plan_status`).

**D-004 · Contradiction: `validate_plan` grouping.** v6 §9.13 lists it under the broadcast group. → It is a staff
tool (KES/HAR); the table layout was a typo.

**D-005 · Claim types.** Union of v6 §9.1 and execution §3.1, plus `kpi_status` for Plan Tracker claims.

**D-006 · Bundle shape.** Execution §3.1 lists `duel{options, estimates, believed_matrices, choices, true_matrix,
regret}` flat. → `duel.private[team]` (options, estimate, believed matrix, sealed choice) and `duel.broadcast`
(revealed choices, true matrix, regret), so the separation rule is structural and testable. `claims[]` added to
the bundle: cue placeholders must be fillable offline.

**D-007 · Matrix contract.** Adds `kind`, `believer`, `row_team`, `col_team`, `col_probs`, `readings`. Cells store
absolute xPts for both teams (the game is not zero-sum); deltas vs Stay/Stay are derived, never stored.

**D-008 · Option contract.** Adds `intent` (small shared vocabulary) and `estimated`. Needed for E7: the
evaluator matches an estimated opponent option to the real one by intent, without the estimator seeing the
real options.

**D-009 · Sealing.** Plans: SHA-256 of canonical JSON without `sealed`. Choices: SHA-256 of `{match_id, team,
option_id, salt}`; the salt is revealed with the choice. Without it a 3-option commit could be brute-forced.

**D-010 · Agent dependencies.** Optional extra `agents` pinned to the latest PyPI releases on 2026-10-23
(`agent-framework 1.23.0`, `mcp 2.3.0`, `azure-ai-projects 2.9.0`, `azure-identity 1.26.0`). Not installed by
`make setup`; B validates the Agent Framework workflow API at H1 before relying on it.

**D-011 · Zones.** Absolute `zone = band * 3 + lane` (band from x = 0). `contracts.common.relative_band` converts to
a team's attacking view.

**D-012 · Shirt numbering.** Fixture squads number players by role order (1 GK, 2 RB, 3–4 CB, 5 LB, …). The plan
examples call HAR's left-back "#3"; in the fixtures it is `HAR-5`. Display-only difference.

**D-013 · Alert minute.** v6 §7.2 shows the "at risk" alert at 31'. Fixture KPI statuses are derived from the
scripted events, which put the change at 36'. The story is unchanged.

**D-014 · Fixture size.** Execution §3.5 says ~300 events; the scripted match has ~560 so that the KPI values,
goal-kick shares and score are derived from events rather than typed by hand. All fixture data is flagged
`illustrative`.

**D-015 · High turnover definition (A to confirm at H2).** Ball won within 40 m of the opponent's goal
(`HIGH_TURNOVER_REL_X = 65`), as in common provider definitions.

**D-016 · Toolchain.** Python 3.12 via `uv` (the machine default is 3.14). Web: React 19, Vite 8, TypeScript 7
(latest at install time). TS types are generated from `match_bundle.schema.json` and checked in CI.

**D-017 · `engine/duel.py` at H0.** Pure matrix reading (best response, safe pick, best guess, gamble, dominant,
regret) was needed to build and test consistent fixtures. Owned by A from now on.

**D-018 · Contradiction: validation panel contents.** v6 §9.15 lists E1, E2, E4; v6 §16 and §11 list E1–E4, E7,
E8. → Use §16.

## H1, person A (2026-10-23)

**D-019 · Contract: hidden truth reaches the simulator (needs joint review).** `simulate()` and `fork()` gain
keyword-only, optional `truth`, `config` (and `match_id` for `simulate`); `sim.bind(truth, config)` returns a
`BoundWorld` with the same two methods and the truth captured inside, so `engine/` can fork matches without
importing `contracts.eval_only`. Existing call sites are unaffected. B uses none of these types.

**D-020 · Contract: `MatchState` carries what an exact fork needs.** Added sim-internal fields: `home`, `away`,
`plans`, `squads`, `t`, `period`, `possession`, `carrier`, `ball`, `counter_until`, `after_cross`,
`dynamics[team]` (used players, Plan B rules fired, executed/pending subs, sim-side KPI counters),
`events_emitted`, `possession_id`, `last_event_t`. No truth, no `SimConfig` (tested). `SimResult.final_state`
is returned for `R == 1`.

**D-021 · Home team.** `simulate()` has no metadata argument: the home team is the first key of `plans`
(attacks towards x = 105 in the first half and kicks off).

**D-022 · Calibration (fixture plans, no truth, 200 replicas).** Goals 2.78/match, shots 26.2, conversion 10.6 %,
passes 973 (79 % completed), corners 9.0, long balls 76, high turnovers ≈ 7–13 per team, H/D/A 33/28/39. With
default levers for both teams the model is symmetric (37/22/40). Single-lever effects on expected points are
within ±0.25 (high press without traits to exploit costs ≈ −0.2). Full calibration against the Anexo A table is
Sunday's task (person A).

**D-023 · Benchmark (`make bench`, Apple Silicon, Python 3.12, one core, best of 3).** R=1 full match with log:
0.36 s; R=500 full matches: 1.74 s; second halves forked from half-time: R=100 0.39 s, R=300 0.64 s, R=500
0.85 s (target ≤ 1 s met); peak traced memory for R=500: 11.8 MB. Optimisations: cached on-pitch roles and
attributes, per-subset player selection.

**D-024 · Model simplifications.** No cards, offsides, penalties or added time. Slow centre-back is team level.
Invalid subs at run time are skipped deterministically; structurally invalid plans raise `sim.PlanError`. Sim-side
KPI statuses for Plan B are an approximation of the engine's Plan Tracker (H2), which stays authoritative.

## H1, person B (2026-10-23)

**D-025 · Agent dependencies.** The H0 pins did not resolve (`agent-framework 1.23.0` needs `azure-ai-projects<2.8`,
H0 pinned 2.9.0) and the meta-package pulls pre-release integrations. The `agents` extra now pins
`agent-framework-core==1.23.0`, `agent-framework-foundry==1.15.0`, `mcp==2.3.0`, `azure-identity==1.26.0`
(`azure-ai-projects 2.7.0` comes transitively). `make setup` and CI install `.[dev,agents]`.

**D-026 · MCP trust model (refines tools.md "X-Team-Scope set by the host").** The scope is fixed per server instance
by the trusted host and never read from a request header or argument. Agents connect in-process (no listener). HTTP
mode serves one scope on loopback only and refuses other hosts until real client authentication exists. Only the tools
allowed for the scope are registered. Details: `mcp_server/README.md`.

**D-027 · Tool results are one JSON text block.** MCP splits list results into one content item per element, which is
ambiguous for one-item lists; every tool returns a single JSON string (same payloads as `fixtures/tools_canned`).

**D-028 · Staff claim visibility and time gating.** Staffs read public observed claims plus their own `kpi_status`,
`sim_valuation` and `opponent_estimate`; matrix cells and regret only via their own tools or broadcast.
`visible_minute` (0 before kick-off) hides future events/snapshots of the match being prepared.

**D-029 · Offline rules client.** CI and demos without Azure run the same Agent Framework `Agent`s with a deterministic
`OfflineRulesClient`; outputs are labelled `offline-rules`. The Foundry path is implemented against the installed
APIs but has not been run against a real deployment (no Azure access yet, see `infra/AZURE_PLAN.md`).

**D-030 · Text verifier and identifiers.** Player ids such as `HAR-5` are identifiers, not statistics, and are allowed
in text; every other digit must come from a `{claim_id.field}` placeholder.

**D-031 · Browser seal check.** The web app recomputes each plan's SHA-256 with Web Crypto over the same canonical
JSON as `contracts/sealing.py` (plans contain no floats, so encodings match) and shows "Seal verified" only then.
