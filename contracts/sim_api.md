# Simulator API (owner: person A)

Frozen at H0, amended by **D-019** (H1, needs joint review). Changes go through a PR labelled `contract`.
Types: `contracts/sim_types.py` (`MatchState`, `Outcomes`, `SimResult`), plus `Plan`, `Option`, `Squads`.

```python
def simulate(plans: dict[str, Plan], squads: Squads, seed: int, R: int = 1, log: bool = False,
             start: MatchState | None = None, until_minute: int = 90, *,
             truth: Truth | None = None, config: SimConfig | None = None,
             match_id: str | None = None, home: str | None = None) -> SimResult: ...
def fork(state: MatchState, overrides: dict[str, Option], R: int, seed: int, *,
         truth: Truth | None = None, config: SimConfig | None = None) -> Outcomes: ...
def bind(truth: Truth | None, config: SimConfig | None) -> World: ...   # World.simulate / World.fork
```

D-019 additions are keyword-only and optional, so H0 call sites keep working. `bind()` returns an object with
the same two methods and the truth captured inside: the pipeline (which may know the truth) hands a `World` to
the engine, so `engine/` can fork matches without ever importing or seeing `contracts.eval_only`.

## Rules

1. **One function, R replicas at once.** State is held in numpy arrays of shape `(R,)` (and `(R, 2, 18)` for
   fatigue). Each step advances one action in every live replica; finished replicas are masked.
2. **`log=True` is only valid with `R == 1`.** It returns `events[]`, `snapshots[]` (minutes 0..`until_minute`)
   and `final_state`. With `R > 1` only `outcomes` is returned. Same code path, no second simulator.
3. **Home team** = `home` (or `start.home`); the first key of `plans` is only a fallback (D-032). The home team
   attacks towards x = 105 in the first half and kicks off.
4. **Determinism.** Same `plans`, `squads`, `seed`, `start`, `truth` and `config` give identical results.
5. **Common random numbers.** Uniforms are a counter-based hash of `(replica seed, step, use)`
   (`sim/rng.py`). Replica `r` of a run with `seed` uses replica seed `h(seed, r)`, so an `R=1` run equals
   replica 0 of an `R>1` run. `fork()` from the same state with different `overrides` consumes the same uniform
   at the same step and use. Limitation: once two forks diverge, step `k` is a different football moment in each,
   so CRN reduces but does not remove the variance of a difference.
6. **`fork()` overrides** are `{"KES": Option, "HAR": Option}` (missing team = Stay). Lever changes apply
   immediately; subs apply at the next stoppage (at half-time if `state` is the half-time state, without using an
   in-play window). All duel cells use the same `seed`.
7. **Half-time state.** `simulate(..., R=1, until_minute=45)` stops at the first-half whistle, before the
   half-time changes. `fork(state, {}, R=1, seed)` then equals continuing the original match.
8. **Outcomes** keep per-replica goals. `xpts` = 3·P(win) + 1·P(draw) per team; `ci90` is a normal
   approximation on per-replica points (the engine computes paired bootstrap intervals for deltas).
9. **Coordinates**: absolute 105 × 68 m, zone = band·3 + lane (`contracts.common.zone_index`), attack direction
   per period as in `MatchMeta.attack`.
10. **Hidden truth.** Only `sim/` and `eval/` import `contracts.eval_only`. Nothing the simulator returns
    (`SimResult`, `Outcomes`, `MatchState`) contains traits or `SimConfig` values (tested).
    `MatchState.fatigue` and `dynamics` are sim-internal: the engine publishes its own `condition_est` and KPIs.
11. **Snapshots** from the simulator leave `condition_est` and `kpis` empty (engine work).

## Performance target (measured at H1)

`R = 500` second halves in ≤ 1 s on one core. See `docs/DECISIONS.md` for the measured numbers.
