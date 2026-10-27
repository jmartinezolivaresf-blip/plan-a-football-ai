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
trait shows in the data. The evaluation therefore runs on seasons nobody looked at (D-043 supersedes the first
choice of season 7777, whose trait kinds per club are the same fixed table we had seen). Scouting
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
player and counted correct team-level detections as misses; fixed before the reported run). The match-level tests
(E2-E8, season statistics) moved from season 7777 (fixed trait table, whose kinds per club we had seen) to season
8101 with random trait kinds. Nothing is tuned on these seasons.

**D-044 · Replayed pre-match keeps its claims.** The seed search and the evaluation compute the pre-match once and
replay it into fresh engines; the replay engine now adopts the claims the pre-match engine served (`Prematch`
in pipeline/build.py). Before, plan cues were dropped and plans cited claims missing from the bundle. The
integration test fixture uses this path and a test checks it gives the same bundle as a fresh build.

**D-045 · Random salts for half-time choices.** The engine derived each choice salt from the true-matrix seed, team
and option, all public in the repo, so the three possible commits could be recomputed and the choice read before the
reveal. Salts now come from `secrets` (`contracts.sealing.new_salt`). Bundles stay reproducible except for salts,
commits and wall-clock fields; the determinism test excludes exactly those.

## H3, readiness (2026-10-24)

**D-046 · Foundry and Azure readiness without touching Azure.** The dev machine's CLI is signed in only to corporate
subscriptions, which must not be used. (1) `AGENTS_MODE=foundry` needs `FOUNDRY_PROJECT_ENDPOINT`,
`FOUNDRY_MODEL_SMALL` and `FOUNDRY_TENANT_ID`; the credential is `AzureCliCredential` pinned to that tenant, and the
Microsoft corporate tenant (plus any in `FOUNDRY_DENY_TENANTS`) is refused before any client exists. (2) The Foundry
path is tested end to end against a local mock of the Responses API: the real `FoundryChatClient`, `Agent` and the
staff's scoped MCP tools run the pre-match and half-time workflows (`tests/test_foundry_contract.py`). This found
three bugs that offline mode could not show: `tenacity` missing for MCP tools (first Foundry turn would crash), a
client and an unclosed credential per call, and MCP subscriptions outliving the client (`agent.close()` after each
turn). (3) `.env` is loaded by every entry point (values already set win). (4) `infra/*.sh` always pass an explicit
`PLAN_A_SUBSCRIPTION_ID`, refuse the corporate tenant and any subscription in the git-ignored `infra/deny.local`, and
need `PLAN_A_APPROVED=yes` for billable steps (`tests/test_infra_guard.py`, fake `az`). (5) Static Web Apps Free
config with SPA fallback, MIME types, caching and security headers, verified in the official emulator on loopback.
Nothing was created, deployed or called in Azure.

## H3, evaluation improvements (2026-10-24)

Protocol: every change below was selected on DEV data only (random-trait seasons 9001-9010, dev duels, dev
seasons 11-14 for the older calibrations). The test sets (E1 seasons 8001-8005, match season 8101) were not run
between the "before" numbers (commit 0d51fc7) and the final evaluation, which is run once at the end.

**D-047 · No press height wins on average.** `eval/diagnose_levers.py` (dev 9001-9003, 72 matchups, true world,
common random numbers) found pressing high cost -0.29 xPts against any opponent and sitting deep gained +0.16; the
press-based weaknesses (short goal kicks, a full-back weak under pressure) were never worth attacking and "sit deep"
dominated half-time matrices. Yet pressing the full-back who really is weak gained +0.075 xPts over pressing without a
target, so the interaction existed and the main effects hid it. Two new coefficients scale defensive pressure in the
possessor's final two fifths (`high_press_cover_scale`: how a pressing team recovers behind its press;
`low_block_pressure_scale`: how compact a low block is). `eval/calibrate_press.py` (dev 9001-9004, fixed grid over
these two plus the high-line long-ball bonus and pressing fatigue; rule: smallest max |high - mid|, |low - mid|)
chose long-ball bonus 0.4 (unchanged), pressing fatigue 1.25 -> 1.1, cover 1.0 -> 1.4, low block 1.0 -> 0.8:
high - mid -0.20 -> -0.018 and low - mid +0.10 -> +0.018 xPts. Shot volume, the adaptation detector and the lever
observation thresholds were re-calibrated after it (shot offset stays -0.4; detector stays z >= 4.0 with 4.2%
online false alarms, 48/48 switches, median delay 7 min). Simulator change: needs Person A's review.

**D-048 · A bench anticipates from what it sees.** The opponent estimate read the other team's real active levers
(`ht_state.levers`) and each believed matrix forked from the true levers of the other team. Both now use
`engine/tracker.py observed_levers`: press height, build-up, channel and corner delivery read from minutes 25-45
(thresholds from dev distributions, `eval/diagnose_estimates.py`; mid and high press now overlap, so the read is
noisy); the press target is not observable. Observations are claims (`c_obs_*`). Probabilities per score situation
of the other bench come from dev duels (`eval/calibrate_estimates.py`, Laplace-smoothed slot frequencies).

**D-049 · Scouting measures evidence, not volume.** Every scouting claim has a 90% interval (Wilson for shares and
rates, Poisson for per-match counts, log-normal for the late-xG ratio) and `contracts.claim.evidence_z` reads the
distance from the reference in standard errors. New controlled statistics: success of long forward balls into the
final third against the team (slow centre-backs), success of forward actions down each channel against the team
(weak channels), and goal-kick short share minus the team's own open-play short share (goal-kick bias, so a
possession side is not flagged for being one); pressure outliers ranked by z. Beliefs come only from the controlled
statistics, with z thresholds chosen per statistic on dev (`eval/select_scouting.py`, best F1). The offline analyst
ranks findings by evidence, keeps one per theme (preferring the controlled statistic) and at most two individual
players; the manager only acts on findings at least one standard error beyond their reference. Dev, report level
(60 clubs): precision 0.80, recall 0.57 (the test numbers before were 0.49 and 0.33).

**D-050 · KPI statuses and claim time gates.** A cumulative KPI that already met its target stays on track, one past
its limit is failing, and at its deadline every KPI is met or missed (no "on track" with the target missed). Staff
`get_claim` now refuses claims about a later minute than the server's `visible_minute` (defense in depth: no such
claim exists during a duel in the pipeline).

**D-051 · Tried and rejected: one step of theory of mind.** Situation frequencies left E7 at chance on a small dev
holdout (0.34, 12 decisions), so the estimator was given a level-1 step: simulate (public world, observed levers)
which of its guesses the other bench would prefer if this bench kept its plan, and weight that option (0.459, from
how often the simulated pick was the real choice in 72 dev duels: 33 times). A paired check on 72 FRESH dev duels
(seasons 9007-9012, both estimators scored on the same decisions) showed it hurts: probability on the real intent
0.349 with the step vs 0.412 without (difference -0.063 +- 0.034, 90%). It was removed; the record is
`eval/results/dev/estimate_check_level1.json`. The estimator keeps the dev-calibrated situation frequencies.
After the press rebalance (D-047) the lever diagnostic on dev shows the press heights near zero on average (high
-0.05, low +0.02 xPts) and real trait interactions for far-post corners (+0.15), the weak channel (+0.08) and going
direct against a slow centre-back (+0.03); pressing-based exploits (short goal kicks, a full-back weak under
pressure) still show no gain there, a limitation of the pressing model for Person A to review
(`eval/results/dev/lever_effects.json` vs `lever_effects_before_D047.json`).

**D-052 · A bug found in the demo, and a second "after" run on test.** Reviewing the demo's scouting report showed
two goal-kick findings: the analyst's one-finding-per-theme rule keyed on the claim label, which differs between the
raw and the controlled statistic, so it only de-duplicated channels. After the fix (key = team, theme, player, side
for channels), dev report level went from precision 0.80 / recall 0.57 to 0.77 / 0.67; the thresholds did not
change. Because the shipped code changed, the dependent dev calibration (opponent estimates) was re-run and the test
evaluation was run again; this is disclosed here: test was run before the changes (0d51fc7), once after them
(14ba1fd), and once more after this bug fix, which was found by reading the demo output, not the test numbers. The
reported "after" numbers are from the last run. Also: Python wrote -0.002 as "-0"; now "0" (as the web already did).

## H3, final review (2026-10-25)

**D-053 · Found in the final end-to-end review.** (1) The full-time KPI verdict went through the live 2-minute
hysteresis, so a target missed at 90' could still read "on track" (the demo's Kestrel showed "2 of 3 KPIs" instead of
1 of 3); the full-time verdict is now settled immediately. Only full time changes (live readings before 90' keep the
smoothing), so the evaluation numbers, which never use the full-time KPI status, are unaffected. (2) The half-time
screen said "choice seal verified" before the reveal, when only the commitment exists; it now shows "locked" until
the reveal and verifies with the revealed salt afterwards. (3) Known, not fixed here: a bench builds its half-time
options from its sealed plan, not from its current levers, so after a Plan B it can offer an option that changes
nothing (in the demo, Kestrel's "Go direct" equals "Stay the course" because its Plan B already went direct at 25').
The fix touches the engine protocol and changes the demo match and the evaluated numbers; it is prepared on branch
`fix/duel-active-levers` with its measured effect for the owners to decide (the owners chose to fix it: D-055). A clean clone rebuilds the demo bundle
identical to the committed one (salts and wall-clock fields aside), and `tests/test_demo_consistency.py` checks the
bundle against itself, the README story block and every number in the video narration.

**D-054 · Half-time options start from the levers in force (first step; completed and merged as D-055).** A bench
built its options from its sealed plan, so after a Plan B it could offer a change that was already in force (D-053:
Kestrel's "Go direct" at seed 236). `get_squad_condition` now also returns the caller's own levers at the visible
minute (its plan, or its Plan B once fired; own team only, same time gate), and the bench builds its options from
them. No change to the engine protocol. Measured on dev only: the dev check (season 9101, 12 bench decisions, plus
E1 on 9011-9015) is identical before and after, because no dev bench had a no-op option. The demo match changes:
at seed 236 Kestrel's third option becomes "Back to short passing", Kestrel picks it, the match ends 4-1 (not 2-2) and
seed 236 no longer meets the story criteria (final goal difference 3). Merging needs a new seed search, bundle,
story, evidence, screenshots and video; the test seasons were not run with this change. Seed search with the fix (48 seeds from 202): 4 meet the criteria (215, 238, 242, 248; 236 does not); the smallest, 215, is Kestrel 1-3 at half-time and 2-3 at full time, with Kestrel's switch detected only in the second half (minute 61).

**D-055 · Every half-time option is a real alternative; new demo match (2026-10-25, owners' decision).** Cause: a
bench built its options from its sealed plan, while the match is played with the levers in force (the plan, or its
Plan B once fired). At seed 236 Kestrel's Plan B had switched it to a direct build-up at 25' (k3 failing), so "Go
direct" re-applied a lever already in force; with common random numbers its forks were the very same replicas as
"Stay the course", hence identical rows in both matrices. `fork()` itself was right: it restores the half-time
levers (Plan B included) and overrides only the fields an option sets; a fired Plan B rule never fires again. In 43
of 120 benches of the demo season the levers at half-time differ from the sealed plan. Fix: (1) the bench reads its
own levers in force (D-054); (2) one definition of what an option does, `contracts.option.tactics` (levers in force
with the option's changes applied, plus substitutions); (3) the engine rejects an option that changes nothing, and
`price_matrix` refuses two rows or two columns with the same tactics; (4) the offline bench takes the next real
alternative when its situational move is already in force (e.g. "Protect the lead" when already sitting deep), and an
option that stays invalid is dropped instead of being stripped into a copy of Stay; (5) the estimate of the other
bench merges guesses that are the same tactics on top of what was seen (in about 3% of benches "they push for a goal"
= press high with a balanced attack was what the other team already did); probabilities add up and the matrix has two
columns, which the contract already allowed. No difference was forced: options that are the same are one option.
Recalibration (dev only): the estimate probabilities for a level score came from dev duels that included the
redundant options; re-running `eval.calibrate_estimates` on 9001-9006 until two passes agree moved them from
[0.452, 0.194, 0.355] to [0.258, 0.29, 0.452] (leading and trailing unchanged; share of dev half-times without a
dominant option 0.431 to 0.583). Measured: dev check (9101, 12 decisions) E7 0.341 to 0.284 (the merge removed a
0.68 credit where the other bench made attacking substitutions; E7 matches labels, and that guess was priced as no
change), E8 AI / stay / random 0.032 / 0.035 / 0.036 to 0.026 / 0.022 / 0.029; then one test run: E7 0.40 to 0.457,
E8 0.028 / 0.045 / 0.029 to 0.028 / 0.045 / 0.032, no-dominant share 0.5 unchanged, E1/E3 unchanged. With 12
decisions per run neither direction is a finding. Demo: the seed search with the unchanged STORY_CRITERIA picks the
smallest passing seed, 204 (4 of 48 pass; 236 no longer does): Kestrel 1-1 Harbourside at half-time, 1-3 at full
time; Kestrel's Plan B at 25' is detected at 31'; at half-time Kestrel stay the course and Harbourside go back to
short passing, the best answer to the move they expected (Kestrel going back to short) but not to what Kestrel did;
Harbourside's regret 0.12 xPts (paired 90% interval 0.01 to 0.228) against "Drop into a mid block", Kestrel's 0.026
is within noise; neither bench has a dominant option. Known limits recorded in the README: the estimate prices "they
push for a goal" without substitutions, and the detector's single change point dates Harbourside's 46' switch to
minute 13 because their long-ball share was already drifting down in the first half.

**D-056 · First real Microsoft Foundry run (2026-10-26).** Where: the owners' personal subscription "Azure subscription
1" (Free Trial, spending limit on, its own directory; the three corporate subscriptions and the corporate tenant were
never used), resource group `rg-plan-a` in Sweden Central: one AIServices S0 resource with a project and one
`gpt-4.1-mini` (2025-04-14) Global Standard deployment (pay per token, capacity 50K tokens/min of a 200K quota), the
"Foundry User" role on that resource, and a 20 EUR budget alert. What ran: `make foundry-ping` (one call) and one
complete `AGENTS_MODE=foundry make foundry-probe`: 15 model turns, every one answered with a service response id;
100,845 input and 5,442 output tokens, identical to Azure Monitor for the same window; both analysts and both managers
called their scoped MCP tools themselves (`get_player_profile`, `get_team_tendencies`, `get_set_piece_profile`). The
validators rejected numbers typed by the model, KPI targets out of range, digits in plan names and sentences without a
claim; the model fixed them on retry except one Kestrel candidate, which stayed invalid and was discarded; the half-time options were all valid and distinct with no fallback. Found by
the real run and fixed (each with a regression test): the manager's CandidateSetDraft used two free-form maps
(lever_evidence, Kpi.params) that strict structured outputs refuse (400 invalid_json_schema; the mock did not check
schemas, a test now does): the drafts write them as lists and code rebuilds the same Plan, so the demo is unchanged;
the probe's half-time replay followed AGENTS_MODE and asked the model for the demo's plans again (its identity check
stopped it); tests could read a real `.env` (Python and the infra scripts now never do in tests); the built-in role
"Azure AI User" is now "Foundry User" (the script assigns it by id). Two incomplete probe runs came before the complete
one; the whole day used 61 requests, 353,797 input and 19,060 output tokens, about 0.17 EUR at the public price (the
complete probe alone about 0.05 EUR). Quality note: the model's plans differ from the demo's and some KPI targets are
not sensible (e.g. 27.2 high turnovers by minute 15); the validators checked grounding and format, not tactical sense (addressed in D-057).
The demo bundle (seed 204) and the video are unchanged (SHA-256 checked before and after) and still say offline rules.

**D-057 · KPI targets must be football-plausible (2026-10-26).** Cause: the plan validator only checked that a share
lay in (0, 1) and that a minimum was positive, so the real Foundry run's "high_turnovers >=27.2 by 15'" passed.
Now, deterministically: (1) scale: high turnovers and balls in behind conceded are counts (whole numbers), the
final-third entry share is a fraction, set-piece xG is continuous; (2) direction: a KPI states a goal, a minimum for
what the plan wants more of (turnovers, entries down its channel, set-piece xG) and a maximum for balls in behind
conceded; (3) range by minute: the engine (`validate_plan`, through the staff's own `validate_plan` tool) rejects a
minimum above the highest value any team reached by that minute, or a maximum below the lowest, in the league's
public matches (the matches the staffs scout; never hidden traits or the match being planned), with the tracker's
own definitions and cut. The bound is the observed range, not a tuned margin: 27.2 high turnovers by 15' against a
league maximum of 6 is rejected, 6 is accepted. The message gives the manager the league's range and median so it
can correct the target within the existing revision limit; if it cannot, the KPIs it could not fix are dropped
(with any Plan B rule watching them) when others remain, otherwise the candidate is discarded and the template plan,
whose target is now plausible (balls in behind conceded <=14 by 90, as the rule-based plans; the old <=3 was below
every team in every season), is used. Checked on the 27 seasons the pipeline and evaluations use: every rule-based
KPI target is within range, so the demo (seed 204 rebuilds identically) and the evaluated numbers do not change.
The recorded Foundry run (D-056) is unchanged; a new run would now reject its KPI targets and ask for corrections.

**D-058 · The real Foundry run in the web, and the Foundry agents measured against the rule agents (2026-10-26).**
(1) The analyst desk has a "Real Microsoft Foundry Run" tab (`?tab=desk&section=foundry`, linked from the banner)
built from the recorded run (D-056) by `pipeline/foundry_web.py`: model turns with service response ids, tokens and
the MCP tools the model chose, validator rejections in plain words and the agents' reaction, the Foundry benches'
half-time calls next to the offline demo's. It is a separate, allow-listed file (`web/public/foundry_run.json`); the
match bundle is unchanged. (2) `eval/compare_agents.py` ran E1 and E3 for both systems on the same units: the official
test seasons (E1 8001-8005, E3 8101) and ten fresh seasons 8006-8015 declared before the run; 51 units, the model twice
per unit (102 runs), same seasons, matchups, seeds and scoring as `eval/run.py` (the rule agents reproduced the
committed E1 0.687/0.633 and E3 0.75 exactly). Budget: a hard cap in code (`agents/budget.py`: a shared ledger of the
tokens each turn reported; a turn that could pass the cap is refused before it is sent), set to 15 EUR of the
owners' 100 EUR allowance after a one-unit pilot (0.06 EUR); the deployment's rate limit was raised from 50K to 200K
tokens/min for the run (Global Standard, pay per token; no new resource) and set back to 50K afterwards; units run one
at a time after parallel runs hit the rate limit (8 throttled attempts, re-run). Spent: 13,686,108 input and 668,923
output tokens in 2,190 requests according to Azure Monitor, about 6.41 EUR at the public price, on the Free Trial
credit; the ledger recorded 99.5% of it (throttled attempts consumed tokens it could not see) and its +10% margin
covered the rest. Results (95% paired bootstrap, all units): E1 precision 0.724 (model) vs 0.697 (rules), not
significant; E1 recall 0.287 vs 0.604, significantly lower; E3 0.441 vs 0.784, significantly lower and below a random
plan (0.545). Official set alone: same directions; E3 not significant (12 plans). Diagnostic: the model flags 1.17
weaknesses per report against 2.61; its validated reports are precise (0.806) but miss most real traits; 31% of its
reports were valid at the first attempt and 40% ended as the template after the retries; its own plans hit a real
weakness about as often as a random plan. Conclusion published as is: with the production prompts and validators,
gpt-4.1-mini does not beat the rule agents at scouting or planning in our simulator; the validators keep it grounded.
Nothing was tuned for this comparison and no unit was dropped.
