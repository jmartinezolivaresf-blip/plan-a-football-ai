# Simulator API (owner: person A)

Frozen at H0. Changes go through a PR labelled `contract` approved by both (see `docs/DECISIONS.md`).
Types: `contracts/sim_types.py` (`MatchState`, `Outcomes`, `SimResult`), plus `Plan`, `Option`, `Squads`.

```python
def simulate(plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1, log: bool = False,
             start: MatchState | None = None, until_minute: int = 90) -> SimResult: ...
def fork(state: MatchState, overrides: dict[str, Option], R: int, seed: int) -> Outcomes: ...
```

## Rules

1. **One function, R replicas at once.** State is held in numpy arrays of shape `(R,)` (and `(R, 22)` for
   fatigue). Each step advances one action in every live replica; finished replicas are masked.
2. **`log=True` is only valid with `R == 1`.** It returns `events[]` and `snapshots[]` in the `events` /
   `snapshot` contracts. With `R > 1` only `outcomes` is returned. Same code path, no second simulator.
3. **Determinism.** Same `plans`, `squads`, `seed` and `start` give identical results.
4. **Common random numbers.** Uniform draws are indexed by `(replica, step, use)` from the replica seed.
   `fork()` with different `overrides` from the same `state` and `seed` consumes the same uniforms, so the
   difference between two cells reflects the decision, not the noise.
5. **`fork()` overrides** are `{"KES": Option, "HAR": Option}` applied at `state.minute` (lever changes and
   subs). Stay is an `Option` with no changes. All 9 duel cells use the same `seed`.
6. **Outcomes** keep per-replica goals so the engine can compute paired deltas and bootstrap intervals.
   `xpts` = 3·P(win) + 1·P(draw) per team.
7. **Coordinates**: absolute 105 × 68 m, zone = band·3 + lane (`contracts.common.zone_index`), attack
   direction per period in `MatchMeta.attack`.
8. **Hidden truth.** The simulator reads `contracts.eval_only.Truth` and `SimConfig` to generate matches.
   Nothing it returns (`SimResult`, `Outcomes`, `MatchState` except `fatigue`) may expose traits. `fatigue`
   is sim-internal: the engine must publish its own `condition_est`, never `MatchState.fatigue`.

## Performance target (measured at H1)

`R = 500` second halves in ≤ 1 s on one core. If not met: cut per `docs/plan/PLAN_A_v6_EJECUCION.md` §9
(R = 300, precompute the demo).
