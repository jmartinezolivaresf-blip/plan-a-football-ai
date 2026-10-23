# sim: zone-based vectorised simulator (person A)

API and rules: `contracts/sim_api.md`. Types: `contracts/sim_types.py`.

```python
from sim import simulate, fork, bind
res = simulate(plans, squads, seed=7, R=1, log=True, truth=truth)        # one match: events + snapshots
ht = simulate(plans, squads, seed=7, R=1, log=True, until_minute=45, truth=truth).final_state
out = fork(ht, {"KES": option}, R=500, seed=2024, truth=truth)          # 500 second halves, CRN
world = bind(truth)          # hand `world` to code that must not see the truth (world.simulate / world.fork)
```

## Model in one page

- **Pitch:** 6 bands × 3 lanes. The ball has absolute coordinates; for the team in possession the code derives its
  band (from its own goal) and team-relative lane. Attack direction flips at half-time.
- **One step = one on-ball action in every live replica**: short pass, progressive pass, long ball, carry, cross,
  shot. Choice: softmax over `model.ACTION_BASE[band]` + `build_up` (bands 0–2), score state after 70', counter
  window, forced header after a completed cross.
- **Success:** `logit = α[action, band] + β_s·(skill−50)/50 − β_p·pressure·(1−press_resistance) +
  β_f·(fatigue_opp − fatigue_own) + context`. Pressure comes from the opponent's `press_height` profile by band
  (`model.PRESS_TABLE`), `press_target` and the opponent's mean stamina.
- **Outcomes:** completed pass (receiver by role/zone), carry, cross; loss by interception (long balls where they
  land), tackle or ball out (throw-in); shots → goal / saved / off target (goal kick) / blocked (corner or loss).
  A win within 40 m of goal is a high turnover; wins in the opponent's half open a 10 s counter window; a long ball
  completed behind a high press counts as a ball in behind and also opens it.
- **Corners:** delivery (`corner_delivery`) × top-3 aerial attackers vs defenders × `back_post_weak` →
  first contact → header shot → goal/saved/off/blocked. Short corners keep possession.
- **Goal kicks:** short/long by `build_up` (and `gk_short_bias`); contested long kicks.
- **Fatigue:** stamina 0..1 per player, faster for outfielders, low-stamina players, `press_height=high` (×1.25)
  and `late_fade`. It lowers pressure efficacy and action success.
- **Subs:** 5 per team, 3 in-play windows + half-time, executed at the next stoppage; invalid subs (player not on
  the pitch, player already used, limits reached) are skipped deterministically. Plans that cannot be simulated
  (unknown players, bad windows, > 5 planned subs) raise `PlanError`.
- **Plan B:** rules checked at every minute (minute, score difference, sim-side KPI status); each rule fires at most
  once per replica; lever changes apply immediately, subs at the next stoppage.
- **Hidden traits** (`contracts.eval_only.Truth`): weak press resistance of a player, slow centre-back (team level),
  weak back post, goal-keeper short bias, late fade, weak channel. Used only inside `sim/world.py` and `sim/core.py`.

## Randomness

`sim/rng.py`: uniform = splitmix64 hash of `(replica seed, step, use)`, 16 uses per step. Replica `r` uses seed
`h(seed, r)`; an `R=1` run is replica 0. Forks from one state with the same seed share every draw (common random
numbers). Logging reads replica 0 only and consumes no randomness, so `log=True` does not change results.

## Known simplifications (documented on purpose)

No cards, offsides, penalties or added time; halves end exactly at 45:00 and 90:00. Slow centre-back is applied at
team level. Sim-side KPI statuses for Plan B triggers are an approximation; the engine's Plan Tracker (H2) is the
authority for what is shown. The render layer (`sim/render/`) is not part of H1.

## Commands

```bash
make test     # includes tests/test_sim_*.py
make bench    # timings on this machine
```
