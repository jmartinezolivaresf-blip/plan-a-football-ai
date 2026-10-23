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
