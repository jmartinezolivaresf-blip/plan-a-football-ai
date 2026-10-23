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

## H2, integration (2026-10-23)

Branch `integration/h2` merges PR #1 (simulator) and PR #2 (MCP, agents, web) without touching `main`; the contract
changes below need approval from both owners before it is merged.

**D-032 · Explicit home team.** `sim.simulate(..., home=)` (and `start.home` for forks) names the home team; the
first key of the `plans` dict is only a fallback. `RealEngine` always passes `home`.

**D-033 · Three worlds, one simulator.** The engine never sees `contracts.eval_only`. It receives opaque handles:
`public_world` (no hidden traits; pre-match plan trajectories and the Plan Tracker's expected curves),
`belief_world(beliefs)` (a world built from what a bench's own scouting suspects, used for that bench's believed
matrix) and `true_world` (hidden truth; used only to play the demo match and the broadcast true matrix after both
seals). Only `pipeline/` constructs `true_world`.

**D-034 · `ENGINE=real` serves the public season only.** `mcp_server/engine_factory.py` loads
`data/season/public.json`; the truth file lives in `data/season/eval_only/` and the MCP server has no path to it, so
`get_true_matrix` answers `not_sealed_yet` until a pipeline-run match has both seals.

**D-035 · Contract additions.** `NotSealedYet`/`NotReady` moved into `contracts.engine_api` (mock and real engine
raise the same types); `seal_choice(..., rule)` records which matrix reading justified the choice; `ToolError` adds
`not_ready`; cues add `goal_flash`; `MatchBundle.scouting` carries each bench's report headlines by claim id.

**D-036 · Evaluation independence and tuning disclosure.** While developing scouting on season 2026 we inspected
the hidden traits of the test teams (HAR, ASH) and raised `press_resistance_trait_penalty` from 40 to 55 so the
trait shows in the data. E1 therefore runs on an unseen season (seed 7777) whose truth nobody looked at. Scouting
compares a player with players in the same position on the same team type (position x team factor) and excludes
goalkeepers from pressure outliers. The offline rules client adds a
Plan B ("go direct if the main KPI fails after 25'") for short/mixed build-up plans. The higher penalty makes the
fixture HAR KPI rule rarer, so `test_kpi_rule_from_fixture_plan_can_fire` uses R=2000.

**D-037 · Demo seed search.** `python -m pipeline.build --search N` tries match seeds in order, prints the criteria
each one missed and keeps the smallest seed meeting `STORY_CRITERIA` (pipeline/build.py). The criteria select a
match that tells the story (an adaptation, no dominant option for one bench, a regret) without editing any number;
the bundle records the criteria and the chosen seed's story.

**D-038 · Adaptation = a build-up switch seen in open play.** Goal kicks alone (3-6 per team per half) cannot show a
change with confidence, and the simulator's `gk_short_bias` trait keeps a biased keeper short whatever the lever
(Person A's model; unchanged). The detector scans the share of long balls among a team's own-half build-up actions
(passes, long balls, carries, goal kicks; ~300 per match) for one change point: >= 20 actions each side,
|change| >= 0.2 and two-proportion z >= 4.0. It runs online: at minute m it reads only events up to m, the broadcast
cue appears at the first minute it fires, and claim ids carry the cutoff (`c_ad_HAR_50_after`) so a half-time reading
is never overwritten by a later one. The cue says "since about minute X" because X is the estimated change point.
The threshold comes from `eval/calibrate_adaptation.py` on dev seasons 11-14 only, measuring the online procedure
(any alarm at any minute): rule "smallest grid z with false-alarm rate <= 5% per team-match" gives 7/192 false alarms,
48/48 injected switches found (none before the switch), detection a median 6.5 minutes after the switch (90th
percentile 20) and the estimated change minute off by a median of 2 (90th percentile 7). Disclosure: a first
version calibrated a single full-time test, which understated online false alarms (18% at its chosen z of 3.0); the
rule was corrected after seeing that. A test keeps the constant equal to the committed calibration result.

**D-039 · Reproducible bundles.** Two bugs made the same seed give different bundles: the pre-match valuation cache
was keyed on levers plus the number of Plan B rules (two candidates with equal levers collided, and the two staffs
run concurrently, so the winner depended on timing), and half-time substitutions broke condition ties by set order
(PYTHONHASHSEED). Both are fixed; a test rebuilds the demo in a subprocess with another hash seed and compares
everything except wall-clock fields (trace durations, build time, seal timestamps, which the seal hash excludes).

**D-040 · Regret with an interval; KPI targets from season rates.** Regret gets a paired 90% bootstrap interval over
the same replicas (common random numbers) of the best response and the chosen option; the cue says "within the
simulator's noise" when it includes zero. Offline plans track four KPIs (lever KPIs first, then balls in behind
conceded <= 14 and high turnovers >= 4, near our simulator's season median 16 and lower quartile 4 per team-match).
The demo story criteria (D-037) now require a live detection that matches a real build-up lever change and a regret
interval above zero; with them 3 of match seeds 202-249 qualify and the smallest, 223, is the demo match.

**D-041 · One definition of "ball in behind".** The simulator counted a ball in behind only against a high line,
the engine counted every completed long ball into the final third, so the Plan Tracker expected 0 for any team not
pressing high. The simulator's KPI counter now uses the engine's definition; only a ball behind a high line still
opens a counter-attack window (game behaviour unchanged). `tests/test_kpi_definitions.py` checks that all simulator
KPI counters equal the engine's event-based values on the same logged match (to +-1 for stoppage time). Simulator
change: needs Person A's review.

**D-042 · Shot volume calibrated on dev seasons.** New coefficient `shot_logit_offset` (-0.4) chosen by
`eval/calibrate_sim.py` on seasons 11-14 (rule: mean shots per match closest to the middle of 24-27): shots 30.3 ->
25.7, goals 3.33 -> 3.00 per match. Other season statistics are reported against their targets, not tuned. The
`test_possession_continuity` check now skips a ball won just before half-time (the other team kicks off the second
half), a legitimate sequence the new coefficient exposed.

**D-043 · E1 on seasons nobody inspected.** Club trait kinds are fixed in `sim.season.TRAITS` and were seen during
development, so E1 now runs on seasons 8001-8005 built with `random_trait_kinds=True` (three kinds per club drawn from
the seed), scouting all six clubs per season (30 scouted teams, 90 traits). Scoring is at the level scouting observes:
player for press resistance, side for a weak channel, team for the rest (the first run scored slow centre-backs per
player and counted correct team-level detections as misses; fixed before the reported run). Nothing is tuned on these
seasons.

**D-044 · Replayed pre-match keeps its claims.** The seed search and the evaluation compute the pre-match once and
replay it into fresh engines; the replay engine now adopts the claims the pre-match engine served (`Prematch`
in pipeline/build.py). Before, plan cues were dropped and plans cited claims missing from the bundle. The
integration test fixture uses this path and a test checks it gives the same bundle as a fresh build.

**D-045 · Random salts for half-time choices.** The engine derived each choice salt from the true-matrix seed, team
and option, all public in the repo, so the three possible commits could be recomputed and the choice read before the
reveal. Salts now come from `secrets` (`contracts.sealing.new_salt`). Bundles stay reproducible except for salts,
commits and wall-clock fields; the determinism test excludes exactly those.
