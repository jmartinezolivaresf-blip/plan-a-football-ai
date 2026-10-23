"""Vectorised zone-based match simulator: R replicas advance one action per step.

Internal frame: ball position is absolute (x, y). For the team in possession we derive its relative x
(distance from its own goal line), band 0..5 and team-relative lane (0 = its left, 1 = centre, 2 = its right).

The same `Batch.run()` serves R=1 with logging (events + snapshots) and R>1 Monte Carlo: logging only reads
replica 0 and never consumes randomness, so replica 0 of a batch equals an R=1 run.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import model as M
from .rng import replica_seeds, uniforms
from .world import (
    A_AER,
    A_FIN,
    A_PACE,
    A_PASS,
    A_PRES,
    A_STAM,
    K_BIB,
    K_ENT,
    K_ENT_C,
    K_ENT_L,
    K_ENT_R,
    K_HT,
    K_SPXG,
    KPI_METRICS,
    L_BUILD,
    L_CHANNEL,
    L_CORNER,
    L_PRESS,
    L_TARGET,
    MAX_SUBS,
    MAX_WINDOWS,
    World,
)

# uniform slots
U_ACT, U_SUCC, U_RECV, U_BAND, U_LANE, U_X, U_Y, U_DT, U_SHOT, U_OUT, U_WIN, U_CFC, U_CSHOT, U_GK, U_GKL, U_MISC = (
    range(16))

# step categories
(C_PASS_OK, C_CARRY_OK, C_CROSS_OK, C_LOSS_INT, C_LOSS_TACKLE, C_LOSS_OUT, C_CROSS_CLEAR, C_CROSS_CORNER,
 C_GOAL, C_SAVED, C_OFF, C_BLOCK_CORNER, C_BLOCK_LOSS) = range(13)
STOPPAGE_CATS = (C_LOSS_OUT, C_CROSS_CORNER, C_GOAL, C_OFF, C_BLOCK_CORNER)

N_STATS = 12
(S_PASS_ATT, S_PASS_CMP, S_SHOTS, S_GOALS, S_CORNERS, S_LONG, S_CROSS, S_FIRST_CONTACT, S_POSS_T, S_SP_SHOTS,
 S_GK_LONG, S_GK) = range(N_STATS)

ACTION_TYPE = {M.SHORT: "pass", M.PROG: "pass", M.LONG: "long_ball", M.CARRY: "carry", M.CROSS: "cross"}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -12.0, 12.0)))


@dataclass
class BatchResult:
    score: np.ndarray        # (R, 2)
    stats: np.ndarray        # (R, 2, N_STATS)
    counters: np.ndarray     # (R, 2, K)
    losses_by_player: np.ndarray  # (R, 2, P)
    kpi_hist: np.ndarray     # (R, 91, 2, K)
    planb_log: list[tuple[int, int, int, int]]  # (replica, team, rule, minute)
    start_minute: int
    end_minute: int


class Batch:
    """All mutable state for R replicas. Construct with `fresh()` or `from_arrays()`; then `run()`."""

    def __init__(self, world: World, R: int, seed: int, logger=None, debug: bool = False):
        self.w, self.R, self.seed = world, R, seed
        self.debug = debug
        self.checked = 0  # number of probability arrays validated (debug mode)
        self.ar = np.arange(R)
        self.seeds = replica_seeds(seed, self.ar)
        self.log = logger
        T = world.teams
        self.P = max(len(t.player_ids) for t in T)
        P = self.P
        self.ROLES = np.zeros((2, P), dtype=np.int64)
        self.ATTR = np.full((2, P, 6), 50.0)
        self.PR_PEN = np.zeros((2, P))
        self.RATE = np.zeros((2, P))
        for i, t in enumerate(T):
            n = len(t.player_ids)
            self.ROLES[i, :n] = t.roles
            self.ATTR[i, :n] = t.attrs
            self.PR_PEN[i, :n] = t.pr_penalty * world.coef["press_resistance_trait_penalty"]
            base = np.where(t.roles == 0, world.coef["fatigue_gk_rate"], world.coef["fatigue_rate"])
            self.RATE[i, :n] = base * (1.3 - 0.6 * t.attrs[:, A_STAM] / 100.0) * (
                1.0 + world.coef["late_fade_mult"] * t.late_fade)
        self.SLOW_CB = np.array([t.slow_cb for t in T])
        self.BPW = np.array([t.back_post_weak for t in T])
        self.GK_BIAS = np.array([t.gk_short_bias for t in T])
        self.WEAK = np.stack([t.weak_lane for t in T])  # (2, 3)
        self.n_cat = [len(t.catalogue) for t in T]
        self.n_rules = [len(t.rules) for t in T]
        C = max(1, max(self.n_cat))
        NR = max(1, max(self.n_rules))
        # dynamic state
        self.t = np.zeros(R)
        self.period = np.ones(R, dtype=np.int64)
        self.done = np.zeros(R, dtype=bool)
        self.poss = np.zeros(R, dtype=np.int64)
        self.carrier = np.zeros(R, dtype=np.int64)
        self.bx = np.full(R, 52.5)
        self.by = np.full(R, 34.0)
        self.score = np.zeros((R, 2), dtype=np.int64)
        self.on = np.zeros((R, 2, 11), dtype=np.int64)
        self.used = np.zeros((R, 2, P), dtype=bool)
        self.fat = np.ones((R, 2, P))
        self.lev = np.zeros((R, 2, 5), dtype=np.int64)
        self.subs_used = np.zeros((R, 2), dtype=np.int64)
        self.windows_used = np.zeros((R, 2), dtype=np.int64)
        self.counter_until = np.zeros(R)
        self.after_cross = np.zeros(R, dtype=bool)
        self.counters = np.zeros((R, 2, len(KPI_METRICS)))
        self.fired = np.zeros((R, 2, NR), dtype=bool)
        self.sub_pending = np.zeros((R, 2, C), dtype=bool)
        self.sub_done = np.zeros((R, 2, C), dtype=bool)
        self.pending_window = np.zeros((R, 2), dtype=bool)
        self.stats = np.zeros((R, 2, N_STATS))
        self.losses = np.zeros((R, 2, P))
        self.kpi_hist = np.zeros((R, 91, 2, len(KPI_METRICS)))
        self.step = 0
        self.planb_log: list[tuple[int, int, int, int]] = []
        self.start_minute = 0
        self.emitted0 = 0
        self.possession_id0 = 0
        self.last_event_t0 = 0.0

    # ------------------------------------------------------------------ construction
    def fresh(self) -> Batch:
        for i, team in enumerate(self.w.teams):
            self.on[:, i, :] = team.starters
            self.used[:, i, team.starters] = True
            self.lev[:, i, :] = team.levers0
        self._refresh_on()
        self._kick_off(np.ones(self.R, dtype=bool), team=0)
        self._record_minutes(np.ones(self.R, dtype=bool), -1, 0)
        return self

    # ------------------------------------------------------------------ helpers
    def _refresh_on(self) -> None:
        """Cache roles/attributes of the players on the pitch; call whenever `self.on` changes."""
        teams = np.arange(2)[None, :, None]
        self._roles_on_all = self.ROLES[teams, self.on]          # (R, 2, 11)
        self._attr_on_all = self.ATTR[teams, self.on]            # (R, 2, 11, 6)

    def _roles_on(self, team: np.ndarray) -> np.ndarray:
        return self._roles_on_all[self.ar, team]  # (R, 11)

    def _attr_on(self, team: np.ndarray, a: int) -> np.ndarray:
        return self._attr_on_all[self.ar, team, :, a]

    def _mean_stamina(self, team: np.ndarray) -> np.ndarray:
        return np.take_along_axis(self.fat[self.ar, team], self.on[self.ar, team], axis=1).mean(axis=1)

    def _check(self, name: str, p: np.ndarray) -> None:
        """Debug mode: every probability must be finite and within [0, 1]."""
        if self.debug:
            if not (np.all(np.isfinite(p)) and np.all(p >= 0.0) and np.all(p <= 1.0)):
                raise FloatingPointError(f"invalid probability array {name}")
            self.checked += 1

    def _pick(self, weights: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Sample a column per row from non-negative weights (R, k) with uniforms u (R,)."""
        cum = np.cumsum(weights, axis=1)
        total = cum[:, -1:]
        total = np.where(total > 0, total, 1.0)
        return np.minimum((u[:, None] * total > cum).sum(axis=1), weights.shape[1] - 1)

    def _player_at(self, team: np.ndarray, band: np.ndarray, lane: np.ndarray, u: np.ndarray,
                   exclude: np.ndarray | None = None, rows: np.ndarray | None = None) -> np.ndarray:
        """Roster index of the team's player most likely involved at (band, lane) in that team's frame.

        `rows` (bool mask) restricts the work to the replicas that need it; other entries are 0."""
        idx = self.ar if rows is None else np.nonzero(rows)[0]
        out = np.zeros(self.R, dtype=np.int64)
        if len(idx) == 0:
            return out
        tm = team[idx]
        on = self.on[idx, tm]
        w = M.ROLE_W[self._roles_on_all[idx, tm], band[idx, None], lane[idx, None]]
        if exclude is not None:
            w = np.where(on == exclude[idx, None], 0.0, w)
        out[idx] = on[np.arange(len(idx)), self._pick(w, u[idx])]
        return out

    def _role_player(self, team: np.ndarray, roles: tuple[int, ...], rows: np.ndarray | None = None) -> np.ndarray:
        """First on-pitch player of the team with one of the roles (fallback: slot 0)."""
        idx = self.ar if rows is None else np.nonzero(rows)[0]
        out = np.zeros(self.R, dtype=np.int64)
        if len(idx) == 0:
            return out
        tm = team[idx]
        ro = self._roles_on_all[idx, tm]
        hit = ro == roles[0]
        for r in roles[1:]:
            hit |= ro == r
        slot = np.where(hit.any(axis=1), hit.argmax(axis=1), 0)
        out[idx] = self.on[idx, tm, slot]
        return out

    def _dir(self, team: np.ndarray) -> np.ndarray:
        """+1 if the team attacks towards x = 105 in the current period."""
        return np.where((team == 0) == (self.period == 1), 1.0, -1.0)

    def _rel_x(self, team: np.ndarray, x: np.ndarray) -> np.ndarray:
        return np.where(self._dir(team) > 0, x, 105.0 - x)

    def _abs_x(self, team: np.ndarray, rel: np.ndarray) -> np.ndarray:
        return np.where(self._dir(team) > 0, rel, 105.0 - rel)

    def _lane_rel(self, team: np.ndarray, y: np.ndarray) -> np.ndarray:
        lane_abs = np.clip((y / M.LANE_M).astype(np.int64), 0, 2)
        return np.where(self._dir(team) > 0, 2 - lane_abs, lane_abs)

    def _abs_lane(self, team: np.ndarray, lane_rel: np.ndarray) -> np.ndarray:
        return np.where(self._dir(team) > 0, 2 - lane_rel, lane_rel)

    def _band(self, rel: np.ndarray) -> np.ndarray:
        return np.clip((rel / M.BAND_M).astype(np.int64), 0, 5)

    def _kick_off(self, mask: np.ndarray, team: int | np.ndarray) -> None:
        team_arr = np.broadcast_to(np.asarray(team), (self.R,)).astype(np.int64)
        self.poss = np.where(mask, team_arr, self.poss)
        self.bx = np.where(mask, 52.5, self.bx)
        self.by = np.where(mask, 34.0, self.by)
        kicker = self._role_player(team_arr, (9,), rows=mask)
        receiver = self._role_player(team_arr, (5, 4, 6), rows=mask)
        self.carrier = np.where(mask, receiver, self.carrier)
        self.counter_until = np.where(mask, 0.0, self.counter_until)
        self.after_cross = np.where(mask, False, self.after_cross)
        if self.log is not None and mask[0]:
            self.log.event("kick_off", self, team=int(team_arr[0]), player=int(kicker[0]), x=52.5, y=34.0,
                           end=(52.5, 30.0), receiver=int(receiver[0]), outcome="success", new_possession=True)

    # ------------------------------------------------------------------ main loop
    def run(self, until_minute: int = 90) -> BatchResult:
        end_t = until_minute * 60.0
        while True:
            # half-time transition (no randomness)
            ht = ~self.done & (self.period == 1) & (self.t >= M.HALF_T)
            if until_minute <= 45:
                self.done |= ht
            elif ht.any():
                self._half_time(ht)
            self.done |= self.t >= min(end_t, M.FULL_T)
            if self.done.all():
                break
            self._step(~self.done)
            self.step += 1
        return BatchResult(self.score.copy(), self.stats.copy(), self.counters.copy(), self.losses.copy(),
                           self.kpi_hist.copy(), list(self.planb_log), self.start_minute, until_minute)

    def _half_time(self, mask: np.ndarray) -> None:
        self.period = np.where(mask, 2, self.period)
        self.t = np.where(mask, M.HALF_T, self.t)
        for i, team in enumerate(self.w.teams):
            for c in team.plan_subs:
                if team.catalogue[c].start is None:
                    self.sub_pending[mask, i, c] |= ~self.sub_done[mask, i, c]
        self._execute_subs(mask, half_time=True)
        self._kick_off(mask, team=1)

    # ------------------------------------------------------------------ one action
    def _step(self, alive: np.ndarray) -> None:
        _w, cf, R, ar = self.w, self.w.coef, self.R, self.ar
        U = uniforms(self.seeds, self.step)
        poss, opp = self.poss, 1 - self.poss
        t0, bx0, by0, carrier0 = self.t.copy(), self.bx.copy(), self.by.copy(), self.carrier.copy()
        rel = self._rel_x(poss, bx0)
        band = self._band(rel)
        lane = self._lane_rel(poss, by0)
        lev_p, lev_o = self.lev[ar, poss], self.lev[ar, opp]
        counter = t0 < self.counter_until
        lead = self.score[ar, poss] - self.score[ar, opp]
        late = t0 >= 4200.0

        # ---- action choice
        L = M.ACTION_BASE[band].copy()
        bscale = np.where(band <= 1, 1.0, np.where(band == 2, 0.5, 0.0))
        L += M.BUILD_MOD[lev_p[:, L_BUILD]] * bscale[:, None]
        L[:, M.CROSS] = np.where(lane == 1, M.NEG, L[:, M.CROSS])
        L[:, M.SHORT] += 0.3 * (late & (lead > 0))
        L[:, M.PROG] += 0.3 * (late & (lead < 0))
        L[:, M.LONG] += 0.3 * (late & (lead < 0))
        L[:, M.PROG] += 0.6 * counter
        L[:, M.CARRY] += 0.4 * counter
        L[:, M.SHOT] += 0.6 * (counter & (band >= 3)) + cf["shot_logit_offset"]
        L = np.where(self.after_cross[:, None], M.NEG, L)
        L[:, M.SHOT] = np.where(self.after_cross, 5.0, L[:, M.SHOT])
        pa = np.exp(L - L.max(axis=1, keepdims=True))
        self._check("p_action", pa / pa.sum(axis=1, keepdims=True))
        action = self._pick(pa, U[:, U_ACT])

        # ---- target zone
        u_b, u_l = U[:, U_BAND], U[:, U_LANE]
        ch_lane = self._pick(M.CHANNEL_W[lev_p[:, L_CHANNEL]], u_l)
        side = np.where(u_l < 0.15, -1, np.where(u_l > 0.85, 1, 0))
        tb = np.select([action == M.SHORT, action == M.PROG, action == M.LONG, action == M.CARRY],
                       [band + (u_b < 0.35), band + 1 + (u_b < 0.4), band + 2 + (u_b < 0.5), band + (u_b < 0.6)],
                       default=5)
        tb = np.clip(tb, 0, 5)
        tl = np.select([action == M.SHORT, (action == M.PROG) | (action == M.LONG), action == M.CARRY],
                       [np.clip(lane + side, 0, 2), ch_lane, lane], default=1)
        trel = np.clip((tb + U[:, U_X]) * M.BAND_M, 0.5, 104.5)
        trel = np.where(action == M.CROSS, 94.0 + 8.0 * U[:, U_X], trel)
        ty = np.clip((self._abs_lane(poss, tl) + U[:, U_Y]) * M.LANE_M, 0.5, 67.5)
        ty = np.where(action == M.CROSS, 26.0 + 16.0 * U[:, U_Y], ty)
        tx = self._abs_x(poss, trel)

        # ---- success probability
        A = self.ATTR[poss, carrier0]
        sopp = self._mean_stamina(opp)
        sown = self.fat[ar, poss, carrier0]
        pz = M.PRESS_TABLE[lev_o[:, L_PRESS], band] + cf["press_target_bonus"] * (lev_o[:, L_TARGET] == carrier0)
        pz = pz * (0.6 + 0.4 * sopp)
        pres = np.clip((A[:, A_PRES] - self.PR_PEN[poss, carrier0]) / 100.0, 0.05, 0.98)
        skill = np.where(action == M.CARRY, A[:, A_PACE], A[:, A_PASS])
        logit = (M.ALPHA[action, band] + cf["beta_skill"] * (skill - 50.0) / 50.0
                 - cf["beta_press"] * pz * (1.0 - pres) + cf["beta_fatigue"] * ((1.0 - sopp) - (1.0 - sown)))
        is_long_prog = (action == M.LONG) | (action == M.PROG)
        opp_high = lev_o[:, L_PRESS] == 0
        logit += cf["long_vs_high_line"] * ((action == M.LONG) & opp_high)
        logit += cf["slow_cb_bonus"] * self.SLOW_CB[opp] * (is_long_prog & (lev_o[:, L_PRESS] != 2) & (tb >= 4))
        def_lane = 2 - tl
        logit += cf["weak_channel_bonus"] * self.WEAK[opp, def_lane] * (
            (action == M.PROG) | (action == M.CARRY) | (action == M.CROSS))
        logit += cf["counter_bonus"] * counter
        p_succ = _sigmoid(logit)
        self._check("p_success", p_succ)
        success = U[:, U_SUCC] < p_succ

        # ---- shot model
        center = lane == 1
        pg = np.select([(band == 5) & center, band == 5, (band == 4) & center, band == 4],
                       [cf["goal_band5_center"], cf["goal_band5_wide"], cf["goal_band4_center"],
                        cf["goal_band4_wide"]], default=cf["goal_band3"])
        pg = pg * np.where(counter, cf["counter_goal_mult"], 1.0) * np.where(self.after_cross,
                                                                              cf["header_goal_mult"], 1.0)
        pg = pg * np.clip(1.0 + cf["finishing_goal_mult"] * (A[:, A_FIN] - 50.0) / 50.0, 0.3, 1.6)
        pg = np.clip(pg, 0.001, 0.6)
        self._check("p_goal", pg)
        us = U[:, U_SHOT]
        rr = (us - pg) / (1.0 - pg)
        shot_cat = np.select([us < pg, rr < cf["p_saved"], rr < cf["p_saved"] + cf["p_off_target"],
                              U[:, U_OUT] < cf["p_corner_blocked_shot"]],
                             [C_GOAL, C_SAVED, C_OFF, C_BLOCK_CORNER], default=C_BLOCK_LOSS)

        # ---- categorise
        p_out = np.where(action == M.LONG, cf["p_out_long"], cf["p_out_short"])
        out = U[:, U_OUT] < p_out
        fail_cat = np.select([action == M.CROSS, out, action == M.CARRY], [
            np.where(U[:, U_OUT] < cf["p_corner_failed_cross"], C_CROSS_CORNER, C_CROSS_CLEAR),
            C_LOSS_OUT, C_LOSS_TACKLE], default=C_LOSS_INT)
        ok_cat = np.select([action == M.CARRY, action == M.CROSS], [C_CARRY_OK, C_CROSS_OK], default=C_PASS_OK)
        cat = np.where(action == M.SHOT, shot_cat, np.where(success, ok_cat, fail_cat))
        cat = np.where(alive, cat, -1)

        # ---- stats
        is_pass = (action != M.CARRY) & (action != M.SHOT) & alive
        np.add.at(self.stats, (ar[is_pass], poss[is_pass], S_PASS_ATT), 1)
        cmp_ = is_pass & success
        np.add.at(self.stats, (ar[cmp_], poss[cmp_], S_PASS_CMP), 1)
        for a, s in ((M.SHOT, S_SHOTS), (M.LONG, S_LONG), (M.CROSS, S_CROSS)):
            m = alive & (action == a)
            np.add.at(self.stats, (ar[m], poss[m], s), 1)

        # ---- log the on-ball action (replica 0) before state changes
        if self.log is not None and alive[0]:
            self.log.action(self, action=int(action[0]), team=int(poss[0]), player=int(carrier0[0]),
                            x=float(bx0[0]), y=float(by0[0]), tx=float(tx[0]), ty=float(ty[0]),
                            success=bool(success[0]), pz=float(pz[0]), cat=int(cat[0]),
                            band=int(band[0]), lane=int(lane[0]), header=bool(self.after_cross[0]))

        dt = M.ACTION_DT[action] + 2.0 * U[:, U_DT]
        self.after_cross = np.where(alive, False, self.after_cross)

        # ---- successful on-ball outcomes
        m = cat == C_PASS_OK
        recv = self._player_at(poss, tb, tl, U[:, U_RECV], exclude=carrier0, rows=m)
        self._move(m, tx, ty, recv)
        if self.log is not None and m[0]:
            self.log.patch_receiver(int(recv[0]))
        m2 = cat == C_CARRY_OK
        self._move(m2, tx, ty, carrier0)
        m3 = cat == C_CROSS_OK
        aer = self._attr_on(poss, A_AER) * M.ROLE_W[self._roles_on(poss), 5, 1]
        aer = np.where(self.on[ar, poss] == carrier0[:, None], 0.0, aer)
        header = self.on[ar, poss, self._pick(aer, U[:, U_RECV])]
        self._move(m3, tx, ty, header)
        self.after_cross |= m3
        if self.log is not None and m3[0]:
            self.log.patch_receiver(int(header[0]))
        moved = m | m2 | m3
        entry = moved & (tb >= 4) & (band < 4)
        np.add.at(self.counters, (ar[entry], poss[entry], K_ENT), 1)
        for ln, k in ((0, K_ENT_L), (1, K_ENT_C), (2, K_ENT_R)):
            e = entry & (tl == ln)
            np.add.at(self.counters, (ar[e], poss[e], k), 1)
        # KPI: a completed long ball into the final third, the engine's is_ball_in_behind() (D-015, D-041). Only one
        # played behind a HIGH line opens a counter-attack window.
        bib = m & (action == M.LONG) & (tb >= 4)
        np.add.at(self.counters, (ar[bib], opp[bib], K_BIB), 1)
        self.counter_until = np.where(bib & opp_high, t0 + cf["counter_window_s"], self.counter_until)

        # ---- losses in open play
        lost_int = cat == C_LOSS_INT
        lost_tck = (cat == C_LOSS_TACKLE) | (cat == C_BLOCK_LOSS)
        # long balls are won where they land; other passes are cut out halfway
        frac = np.where(action == M.LONG, 1.0, 0.5)
        lx = np.where(lost_int, bx0 + frac * (tx - bx0), bx0)
        ly = np.where(lost_int, by0 + frac * (ty - by0), by0)
        self._turnover(lost_int | lost_tck, opp, lx, ly, U[:, U_WIN], carrier0,
                       kind=np.where(lost_int, 0, 1))

        # ---- stoppages: subs first, then restarts
        stop = (cat == C_LOSS_OUT) | (cat == C_CROSS_CORNER) | (cat == C_GOAL) | (cat == C_OFF) | (
            cat == C_BLOCK_CORNER)
        self._execute_subs(stop & self.sub_pending.any(axis=(1, 2)), half_time=False)
        self._throw_in(cat == C_LOSS_OUT, opp, tx, ty, U, carrier0)
        self._clearance(cat == C_CROSS_CLEAR, opp, U, carrier0)
        corner = (cat == C_CROSS_CORNER) | (cat == C_BLOCK_CORNER)
        self._corner(corner, poss, opp, by0, ty, U)
        goal = cat == C_GOAL
        self._goal(goal, poss, carrier0)
        self._saved(cat == C_SAVED, opp)
        self._goal_kick(cat == C_OFF, opp, U)

        # ---- time, stoppage, fatigue, possession time
        stop_s = np.select([cat == C_GOAL, cat == C_OFF, cat == C_LOSS_OUT, corner, cat == C_SAVED],
                           [cf["stop_goal_s"], cf["stop_goal_kick_s"], cf["stop_throw_s"], cf["stop_corner_s"],
                            cf["stop_save_s"]], default=0.0)
        dt = np.where(alive, dt + stop_s, 0.0)
        limit = np.where(self.period == 1, M.HALF_T, M.FULL_T)
        t1 = np.minimum(t0 + dt, limit)
        dt_eff = t1 - t0
        np.add.at(self.stats, (ar[alive], poss[alive], S_POSS_T), dt_eff[alive])
        press_mult = np.where(self.lev[:, :, L_PRESS] == 0, cf["high_press_fatigue_mult"], 1.0)  # (R, 2)
        on_mask = np.zeros((R, 2, self.P), dtype=bool)
        np.put_along_axis(on_mask, self.on, True, axis=2)
        self.fat = np.clip(self.fat - (dt_eff / 60.0)[:, None, None] * self.RATE[None] * press_mult[:, :, None]
                           * on_mask, 0.0, 1.0)
        self.t = t1
        self._record_minutes(alive, (t0 // 60).astype(np.int64), (t1 // 60).astype(np.int64))

    # ------------------------------------------------------------------ outcome routines
    def _move(self, m, x, y, player) -> None:
        self.bx = np.where(m, x, self.bx)
        self.by = np.where(m, y, self.by)
        self.carrier = np.where(m, player, self.carrier)

    def _turnover(self, m, new, x, y, u, loser, kind) -> None:
        if not m.any():
            return
        rel = self._rel_x(new, x)
        band = self._band(rel)
        lane = self._lane_rel(new, y)
        winner = self._player_at(new, band, lane, u, rows=m)
        np.add.at(self.losses, (self.ar[m], (1 - new)[m], loser[m]), 1)
        high = m & (rel >= M.HIGH_TURNOVER_REL_X)
        np.add.at(self.counters, (self.ar[high], new[high], K_HT), 1)
        self.counter_until = np.where(m & (rel >= 52.5), self.t + self.w.coef["counter_window_s"],
                                      np.where(m, 0.0, self.counter_until))
        self.poss = np.where(m, new, self.poss)
        self._move(m, x, y, winner)
        if self.log is not None and m[0]:
            self.log.event("interception" if kind[0] == 0 else "tackle", self, team=int(new[0]),
                           player=int(winner[0]), x=float(x[0]), y=float(y[0]), outcome="won")
            self.log.event("possession_change", self, team=int(new[0]), player=int(winner[0]), x=float(x[0]),
                           y=float(y[0]), new_possession=True)

    def _throw_in(self, m, new, tx, ty, U, loser) -> None:
        if not m.any():
            return
        y = np.where(ty < 34.0, 0.5, 67.5)
        x = np.clip(tx, 1.0, 104.0)
        rel = self._rel_x(new, x)
        band, lane = self._band(rel), self._lane_rel(new, y)
        thrower = self._player_at(new, band, lane, U[:, U_WIN], rows=m)
        recv = self._player_at(new, band, lane, U[:, U_RECV], exclude=thrower, rows=m)
        np.add.at(self.losses, (self.ar[m], (1 - new)[m], loser[m]), 1)
        ry = np.where(y < 34.0, 6.0, 62.0)
        self.poss = np.where(m, new, self.poss)
        self.counter_until = np.where(m, 0.0, self.counter_until)
        self._move(m, x, ry, recv)
        if self.log is not None and m[0]:
            self.log.event("possession_change", self, team=int(new[0]), player=int(thrower[0]), x=float(x[0]),
                           y=float(y[0]), new_possession=True)
            self.log.event("throw_in", self, team=int(new[0]), player=int(thrower[0]), x=float(x[0]),
                           y=float(y[0]), end=(float(x[0]), float(ry[0])), receiver=int(recv[0]),
                           outcome="success")

    def _clearance(self, m, new, U, loser) -> None:
        if not m.any():
            return
        clearer = self._role_player(new, (2,), rows=m)
        rel_land = 25.0 + 20.0 * U[:, U_MISC]
        x = self._abs_x(new, rel_land)
        y = 10.0 + 48.0 * U[:, U_WIN]
        recv = self._player_at(new, self._band(rel_land), self._lane_rel(new, y), U[:, U_RECV], exclude=clearer,
                               rows=m)
        np.add.at(self.losses, (self.ar[m], (1 - new)[m], loser[m]), 1)
        if self.log is not None and m[0]:
            bx = float(self.bx[0])
            self.log.event("clearance", self, team=int(new[0]), player=int(clearer[0]), x=bx, y=float(self.by[0]),
                           end=(float(x[0]), float(y[0])), outcome="success")
            self.log.event("possession_change", self, team=int(new[0]), player=int(recv[0]), x=float(x[0]),
                           y=float(y[0]), new_possession=True)
        self.poss = np.where(m, new, self.poss)
        self.counter_until = np.where(m, 0.0, self.counter_until)
        self._move(m, x, y, recv)

    def _goal(self, m, team, scorer) -> None:
        if not m.any():
            return
        np.add.at(self.score, (self.ar[m], team[m]), 1)
        np.add.at(self.stats, (self.ar[m], team[m], S_GOALS), 1)
        if self.log is not None and m[0]:
            self.log.event("goal", self, team=int(team[0]), player=int(scorer[0]), x=float(self.bx[0]),
                           y=float(self.by[0]), outcome="goal", body_part=self.log.last_body_part,
                           set_piece_ref=self.log.last_set_piece)
        self._kick_off(m, team=1 - team)

    def _saved(self, m, keeper_team) -> None:
        if not m.any():
            return
        gk = self._role_player(keeper_team, (0,), rows=m)
        x = self._abs_x(keeper_team, np.full(self.R, 5.0))
        self.poss = np.where(m, keeper_team, self.poss)
        self.counter_until = np.where(m, 0.0, self.counter_until)
        self._move(m, x, np.full(self.R, 34.0), gk)
        if self.log is not None and m[0]:
            self.log.event("possession_change", self, team=int(keeper_team[0]), player=int(gk[0]), x=float(x[0]),
                           y=34.0, new_possession=True)

    def _goal_kick(self, m, team, U) -> None:
        if not m.any():
            return
        cf = self.w.coef
        gk = self._role_player(team, (0,), rows=m)
        build = self.lev[self.ar, team, L_BUILD]
        p_short = np.array([cf["gk_short_short"], cf["gk_short_mixed"], cf["gk_short_direct"]])[build]
        p_short = np.where(self.GK_BIAS[team] > 0, np.maximum(p_short, cf["gk_short_bias_floor"]
                                                              + 0.2 * self.GK_BIAS[team]), p_short)
        short = U[:, U_GK] < p_short
        rel_end = np.where(short, 12.0 + 10.0 * U[:, U_MISC], 52.0 + 18.0 * U[:, U_MISC])
        y_end = np.where(short, 10.0 + 48.0 * U[:, U_X], 14.0 + 40.0 * U[:, U_X])
        x_end = self._abs_x(team, rel_end)
        x0 = self._abs_x(team, np.full(self.R, 5.5))
        recv = self._player_at(team, self._band(rel_end), self._lane_rel(team, y_end), U[:, U_RECV], rows=m)
        opp = 1 - team
        att = self._attr_on(team, A_AER).max(axis=1)
        dfn = np.sort(self._attr_on(opp, A_AER), axis=1)[:, -2:].mean(axis=1)
        p_long = _sigmoid(0.2 + 1.5 * (att - dfn) / 50.0)
        self._check("p_goal_kick_short", p_short)
        self._check("p_goal_kick_long", p_long)
        long_ok = ~short & (U[:, U_GKL] < p_long)
        np.add.at(self.stats, (self.ar[m], team[m], S_GK), 1)
        lg = m & ~short
        np.add.at(self.stats, (self.ar[lg], team[lg], S_GK_LONG), 1)
        if self.log is not None and m[0]:
            self.log.event("possession_change", self, team=int(team[0]), player=int(gk[0]), x=float(x0[0]),
                           y=34.0, new_possession=True)
            self.log.event("goal_kick", self, team=int(team[0]), player=int(gk[0]), x=float(x0[0]), y=34.0,
                           end=(float(x_end[0]), float(y_end[0])),
                           receiver=int(recv[0]) if (short[0] or long_ok[0]) else None,
                           outcome="success" if (short[0] or long_ok[0]) else "fail")
        ok = m & (short | long_ok)
        self.poss = np.where(m, team, self.poss)
        self.counter_until = np.where(m, 0.0, self.counter_until)
        self._move(ok, x_end, y_end, recv)
        lost = m & ~short & ~long_ok
        self.bx = np.where(lost, x_end, self.bx)
        self.by = np.where(lost, y_end, self.by)
        self._turnover(lost, opp, x_end, y_end, U[:, U_WIN], gk, kind=np.zeros(self.R, dtype=np.int64))

    def _corner(self, m, att, dfn, by0, ty, U) -> None:
        if not m.any():
            return
        cf, ar = self.w.coef, self.ar
        np.add.at(self.stats, (ar[m], att[m], S_CORNERS), 1)
        side_y = np.where(np.where(m, ty, by0) < 34.0, 0.5, 67.5)
        cx = self._abs_x(att, np.full(self.R, 104.5))
        taker = self._role_player(att, (7, 8, 6, 5), rows=m)
        delivery = self.lev[ar, att, L_CORNER]
        att_air = np.sort(self._attr_on(att, A_AER), axis=1)[:, -3:].mean(axis=1)
        def_air = np.sort(self._attr_on(dfn, A_AER), axis=1)[:, -3:].mean(axis=1)
        base = np.where(delivery == 0, cf["corner_near_logit"], cf["corner_far_logit"])
        logit = base + cf["corner_aerial_beta"] * (att_air - def_air) / 50.0 + (
            cf["back_post_weak_bonus"] * self.BPW[dfn] * (delivery == 1))
        p_fc = np.where(delivery == 2, cf["corner_short_contact"], _sigmoid(logit))
        self._check("p_first_contact", p_fc)
        won = U[:, U_CFC] < p_fc
        post_y = np.where(delivery == 0, np.where(side_y < 34, 30.0, 38.0), np.where(side_y < 34, 40.0, 28.0))
        hx = self._abs_x(att, np.full(self.R, 99.0))
        short_y = np.where(side_y < 34, 8.0, 60.0)
        end_x = np.where(delivery == 2, self._abs_x(att, np.full(self.R, 96.0)), hx)
        end_y = np.where(delivery == 2, short_y, post_y)
        # header taker: one of the 3 best in the air (excluding the corner taker)
        aer = np.where(self.on[ar, att] == taker[:, None], 0.0, self._attr_on(att, A_AER))
        top = np.argsort(aer, axis=1)[:, -3:]
        header = self.on[ar, att, top[ar, np.minimum((U[:, U_MISC] * 3).astype(np.int64), 2)]]
        short_recv = self._role_player(att, (6, 5, 7, 8), rows=m)
        fin = self.ATTR[att, header, A_AER]
        pg = np.clip(cf["corner_header_goal"] * (1.0 + 0.6 * (fin - 50.0) / 50.0) * np.where(delivery == 1, 1.1, 1.0),
                     0.01, 0.4)
        self._check("p_header_goal", pg)
        headed = m & won & (delivery != 2)
        np.add.at(self.counters, (ar[headed], att[headed], K_SPXG), pg[headed])
        np.add.at(self.stats, (ar[headed], att[headed], S_FIRST_CONTACT), 1)
        np.add.at(self.stats, (ar[headed], att[headed], S_SP_SHOTS), 1)
        np.add.at(self.stats, (ar[headed], att[headed], S_SHOTS), 1)
        uc = U[:, U_CSHOT]
        rr = (uc - pg) / (1.0 - pg)
        h_goal = headed & (uc < pg)
        h_saved = headed & ~h_goal & (rr < cf["p_saved"])
        h_off = headed & ~h_goal & ~h_saved & (rr < cf["p_saved"] + cf["p_off_target"])
        h_block = headed & ~h_goal & ~h_saved & ~h_off
        short_ok = m & won & (delivery == 2)
        cleared = m & ~won
        if self.log is not None and m[0]:
            ref = self.log.event("corner", self, team=int(att[0]), player=int(taker[0]), x=float(cx[0]),
                                 y=float(side_y[0]), end=(float(end_x[0]), float(end_y[0])),
                                 receiver=int(short_recv[0] if short_ok[0] else header[0]) if won[0] else None,
                                 outcome="first_contact_won" if won[0] else "first_contact_lost",
                                 new_possession=True)
            if headed[0]:
                outcome = "goal" if h_goal[0] else "saved" if h_saved[0] else "off_target" if h_off[0] else "blocked"
                self.log.event("shot", self, team=int(att[0]), player=int(header[0]), x=float(hx[0]),
                               y=float(post_y[0]), end=(float(self._abs_x(att, np.full(self.R, 105.0))[0]), 34.0),
                               outcome=outcome, body_part="head", set_piece_ref=ref)
                self.log.last_body_part, self.log.last_set_piece = "head", ref
        self.poss = np.where(m, att, self.poss)
        self.bx = np.where(m, np.where(delivery == 2, end_x, hx), self.bx)
        self.by = np.where(m, end_y, self.by)
        self.carrier = np.where(short_ok, short_recv, np.where(headed, header, self.carrier))
        self.counter_until = np.where(m, 0.0, self.counter_until)
        self._goal(h_goal, att, header)
        self._saved(h_saved, dfn)
        self._goal_kick(h_off, dfn, U)
        lost = cleared | h_block
        self._clearance(lost, dfn, U, np.where(cleared, taker, header))
        if self.log is not None and m[0]:
            self.log.last_body_part, self.log.last_set_piece = None, None

    # ------------------------------------------------------------------ subs, plan B, minutes
    def _execute_subs(self, mask: np.ndarray, half_time: bool) -> None:
        for r in np.nonzero(mask)[0]:
            for i, team in enumerate(self.w.teams):
                pend = np.nonzero(self.sub_pending[r, i])[0]
                if len(pend) == 0:
                    continue
                window = self.pending_window[r, i] and not half_time
                if window and self.windows_used[r, i] >= MAX_WINDOWS:
                    self.sub_pending[r, i, :] = False
                    continue
                done_any = False
                for c in pend:
                    e = team.catalogue[c]
                    slot = np.nonzero(self.on[r, i] == e.out)[0]
                    valid = len(slot) == 1 and not self.used[r, i, e.into] and self.subs_used[r, i] < MAX_SUBS
                    self.sub_pending[r, i, c] = False
                    self.sub_done[r, i, c] = True
                    if not valid:
                        continue
                    self.on[r, i, slot[0]] = e.into
                    self.used[r, i, e.into] = True
                    self.subs_used[r, i] += 1
                    if self.poss[r] == i and self.carrier[r] == e.out:
                        self.carrier[r] = e.into
                    done_any = True
                    if self.log is not None and r == 0:
                        self.log.event("sub", self, team=i, player=int(e.into), x=float(self.bx[0]),
                                       y=float(self.by[0]), sub_in=int(e.into), sub_out=int(e.out))
                if done_any and window:
                    self.windows_used[r, i] += 1
                self.pending_window[r, i] = False
        if mask.any():
            self._refresh_on()

    def _kpi_status(self, r: np.ndarray, i: int, cond, minute: np.ndarray) -> np.ndarray:
        c = self.counters[r, i]
        if cond.kpi_metric == "final_third_entries_share":
            k = {"left": K_ENT_L, "center": K_ENT_C, "right": K_ENT_R}.get(cond.kpi_params.get("channel", ""), K_ENT_C)
            total = c[:, K_ENT]
            value = c[:, k] / np.maximum(total, 1.0)
            ratio = value / max(cond.kpi_target, 1e-9)
            st = np.where(ratio >= 0.9, 0, np.where(ratio >= 0.7, 1, 2))
            return np.where((minute < 10) | (total < 5), 3, st)
        idx = {"high_turnovers": K_HT, "set_piece_xg": K_SPXG, "balls_in_behind_conceded": K_BIB}[cond.kpi_metric]
        value = c[:, idx]
        frac = np.minimum(minute, cond.kpi_by) / cond.kpi_by
        if cond.kpi_op in (">=", ">"):
            expected = cond.kpi_target * frac
            st = np.where(value >= 0.85 * expected, 0, np.where(value >= 0.5 * expected, 1, 2))
        else:
            st = np.where(value <= cond.kpi_target * frac, 0, np.where(value <= cond.kpi_target, 1, 2))
        return np.where(minute < 10, 3, st)

    def _plan_triggers(self, rows: np.ndarray, minute: np.ndarray) -> None:
        """Called once per crossed minute for the replicas in `rows` (indices)."""
        for i, team in enumerate(self.w.teams):
            for c in team.plan_subs:
                e = team.catalogue[c]
                if e.start is None:
                    continue
                idle = ~self.sub_done[rows, i, c] & ~self.sub_pending[rows, i, c]
                hit = (minute >= e.start) & (minute <= e.end) & idle
                if hit.any():
                    self.sub_pending[rows[hit], i, c] = True
                    self.pending_window[rows[hit], i] = True
            for k, rule in enumerate(team.rules):
                cond = rule.cond
                ok = ~self.fired[rows, i, k]
                if cond.after_minute is not None:
                    ok &= minute >= cond.after_minute
                if cond.score_op is not None:
                    diff = self.score[rows, i] - self.score[rows, 1 - i]
                    ok &= {">=": diff >= cond.score_value, "<=": diff <= cond.score_value,
                           ">": diff > cond.score_value, "<": diff < cond.score_value,
                           "==": diff == cond.score_value}[cond.score_op]
                if cond.kpi_metric is not None and cond.status is not None:
                    ok &= self._kpi_status(rows, i, cond, minute) == cond.status
                if not ok.any():
                    continue
                hit_rows = rows[ok]
                self.fired[hit_rows, i, k] = True
                for lever, value in rule.levers.items():
                    self.lev[hit_rows, i, lever] = value
                for c in rule.subs:
                    self.sub_pending[hit_rows, i, c] = ~self.sub_done[hit_rows, i, c]
                    self.pending_window[hit_rows, i] = True
                for r, mnt in zip(hit_rows, minute[ok], strict=True):
                    self.planb_log.append((int(r), i, k, int(mnt)))

    def _record_minutes(self, alive: np.ndarray, m0: np.ndarray | int, m1: np.ndarray | int) -> None:
        m0 = np.broadcast_to(np.asarray(m0), (self.R,))
        m1 = np.broadcast_to(np.asarray(m1), (self.R,))
        crossing = alive & (m1 > m0)
        if not crossing.any():
            return
        for k in range(1, int((m1 - m0)[crossing].max()) + 1):
            rows = np.nonzero(crossing & (m0 + k <= m1))[0]
            minute = m0[rows] + k
            self.kpi_hist[rows, np.minimum(minute, 90)] = self.counters[rows]
            self._plan_triggers(rows, minute)
            if self.log is not None and len(rows) and rows[0] == 0:
                self.log.snapshot(self, int(minute[0]))
