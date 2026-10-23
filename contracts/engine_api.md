# Engine API (owner: person A)

Frozen at H0. Source of truth: the `EngineAPI` Protocol in `contracts/engine_api.py`.
Implementations: `engine/` (real, person A, from H1) and `mcp_server/mock_engine.py` (fixtures, person B).

| Method | Returns | Notes |
|---|---|---|
| `list_matches(team)` | `list[MatchRef]` | Season history |
| `get_team_tendencies(team, aspect)` | `list[Claim]` | `observed_tendency` with `n`, `league_ref`, `status` |
| `get_player_profile(player_id)` | `list[Claim]` | Observed only, never hidden traits |
| `get_set_piece_profile(team)` | `list[Claim]` | |
| `get_squad(team)` | `Squad` | Visible attributes. MCP allows own team only |
| `get_squad_condition(match_id, team, minute)` | `list[Claim]` | Engine estimate from observable load. Own team only |
| `simulate_plan(plan, opponent_estimate, R)` | `list[Claim]` | `sim_valuation` vs the analyst's `OpponentPlanEstimate` |
| `estimate_opponent_options(match_id, team)` | `OpponentOptionsEstimate` | Options flagged `estimated`, probabilities sum to 1. Deterministic rules; the analyst may adjust within validator limits |
| `price_matrix(match_id, own_options, opponent_options, R, perspective, opponent_probs)` | `Matrix` (`kind="believed"`) | Rows = `perspective`'s options. Includes `readings[perspective]` |
| `seal_choice(match_id, team, option_id)` | `SealedChoice` | Commit only (salted SHA-256, `contracts.sealing`) |
| `true_matrix(match_id)` | `DuelBroadcast` | Only after both benches sealed. Raises otherwise |
| `regret(match_id)` | `dict[team, Regret]` | On the true matrix; `regret_xpts >= 0` |
| `validate_plan(plan)` | `ValidationResult` | Real rules in `agents/validators` (H1) |
| `validate_option(match_id, option)` | `ValidationResult` | Subs on the pitch, 5 subs / 3 windows + HT |
| `get_plan_status(match_id, team, minute)` | `list[Claim]` | `kpi_status` |
| `get_match_state(match_id, minute)` | `Snapshot` | |
| `get_events(match_id, filter)` | `list[Event]` | `filter`: event fields + `limit`, `from_t`, `to_t` |
| `get_claim(claim_id)` | `Claim` | |

## Matrix conventions

- `cells[i][j]` = row option `i` × column option `j`; absolute `xpts` for **both** teams (not zero-sum).
- `rows[0]` and `cols[0]` are *Stay the course*. Deltas vs `cells[0][0]` are derived, never stored.
- Readings (`engine/duel.py`): best response per opponent option, safe pick (maximin), best guess
  (expected value under `col_probs`), gamble, dominant.
- Regret = xPts(best response to the opponent's real choice) − xPts(own choice), on the true matrix.

## Not exposed, ever

`contracts.eval_only` (`Truth`, `SimConfig`) and `MatchState.fatigue`. The engine package must not import
`contracts.eval_only` (tested from H1 once `engine/` has real modules).
