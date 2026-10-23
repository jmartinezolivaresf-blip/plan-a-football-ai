# MCP tools (owner: person B)

Frozen at H0. Transport: MCP streamable HTTP (Azure Container Apps). Each tool maps to one `EngineAPI`
method (`contracts/engine_api.md`). Canned examples: `fixtures/tools_canned/<tool>.<scope>.json`.

## Scope

- The agent **host** sets `X-Team-Scope: KES | HAR | broadcast`. The LLM never sets it.
- For staff scopes (`KES`, `HAR`) the server **derives `team` from the scope** for every "own team" tool:
  the tool has no `team` argument, so a bench cannot ask for the other bench's private data.
- Errors use `contracts.refs.ToolError` (`forbidden_scope`, `not_sealed_yet`, `not_found`, `invalid_args`).

| Tool | Args (LLM-visible) | Scopes | Engine call | Returns |
|---|---|---|---|---|
| `list_matches` | `team` | KES, HAR, broadcast | `list_matches` | `MatchRef[]` |
| `get_team_tendencies` | `team`, `aspect` | KES, HAR, broadcast | `get_team_tendencies` | `Claim[]` |
| `get_player_profile` | `player_id` | KES, HAR, broadcast | `get_player_profile` | `Claim[]` |
| `get_set_piece_profile` | `team` | KES, HAR, broadcast | `get_set_piece_profile` | `Claim[]` |
| `get_squad_condition` | `match_id`, `minute` | KES, HAR (own team) | `get_squad` + `get_squad_condition` | `{squad, condition_est}` |
| `simulate_plan` | `plan`, `opponent_estimate`, `R` | KES, HAR (own plan) | `simulate_plan` | `Claim[]` |
| `estimate_opponent_options` | `match_id` | KES, HAR (own estimate) | `estimate_opponent_options` | `OpponentOptionsEstimate` |
| `price_matrix` | `match_id`, `own_options`, `opponent_options`, `opponent_probs`, `R` | KES, HAR (perspective = scope) | `price_matrix` | `Matrix` (believed) |
| `validate_plan` | `plan` or `option` | KES, HAR | `validate_plan` / `validate_option` | `ValidationResult` |
| `seal_choice` | `match_id`, `option_id` | KES, HAR (own choice) | `seal_choice` | `SealedChoice` |
| `get_plan_status` | `match_id`, `minute` | KES, HAR (own plan); broadcast (+`team`) | `get_plan_status` | `Claim[]` |
| `get_match_state` | `match_id`, `minute` | broadcast | `get_match_state` | `Snapshot` |
| `get_events` | `match_id`, `filter` | KES, HAR, broadcast | `get_events` | `Event[]` |
| `get_claim` | `claim_id` | KES, HAR (non-private claims), broadcast | `get_claim` | `Claim` |
| `get_true_matrix` | `match_id` | **broadcast only, after both seals** | `true_matrix` + `regret` | `DuelBroadcast` |

## Separation tests (implemented by B at H1, fixtures already checked at H0)

1. `KES` scope can never read HAR's options, estimate, believed matrix, choice or squad condition.
2. `get_true_matrix` returns `forbidden_scope` for `KES`/`HAR` and `not_sealed_yet` before both seals.
3. No tool response contains `contracts.eval_only` data.

Validation note: v6 §9.13 lists `validate_plan` under the broadcast group; it is a **staff** tool
(resolved in `docs/DECISIONS.md`, D-004).
