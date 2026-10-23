"""Model constants: zones, actions, lever encodings and default coefficients.

Coefficients can be overridden through `SimConfig.coefficients` (same keys as DEFAULT_COEFFICIENTS).
All numbers are modelling choices, tuned only for plausible match statistics (see tests/test_sim_sanity.py).
"""

from __future__ import annotations

import numpy as np

N_BANDS, N_LANES = 6, 3
BAND_M = 105.0 / N_BANDS
LANE_M = 68.0 / N_LANES
HALF_T, FULL_T = 2700.0, 5400.0
HIGH_TURNOVER_REL_X = 65.0  # ball won within 40 m of the opponent's goal (same rule as the fixtures)

# Actions
SHORT, PROG, LONG, CARRY, CROSS, SHOT = range(6)
N_ACTIONS = 6
PASS_ACTIONS = (SHORT, PROG, LONG, CROSS)

# Lever encodings
PRESS = {"high": 0, "mid": 1, "low": 2}
BUILD = {"short": 0, "mixed": 1, "direct": 2}
CHANNEL = {"left": 0, "center": 1, "right": 2, "balanced": 3}
CORNER = {"near_post": 0, "far_post": 1, "short": 2}
INV_PRESS = {v: k for k, v in PRESS.items()}
INV_BUILD = {v: k for k, v in BUILD.items()}
INV_CHANNEL = {v: k for k, v in CHANNEL.items()}
INV_CORNER = {v: k for k, v in CORNER.items()}

# Roles
ROLES = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
ROLE_IDX = {r: i for i, r in enumerate(ROLES)}
# Home position in the team's attacking frame: (band, team-relative lane 0=left 1=centre 2=right)
ROLE_HOME = {"GK": (0.0, 1), "RB": (1.6, 2), "CB": (1.0, 1), "LB": (1.6, 0), "DM": (2.0, 1), "CM": (2.8, 1),
             "AM": (3.5, 1), "RW": (4.0, 2), "LW": (4.0, 0), "ST": (4.6, 1)}

NEG = -30.0  # "impossible" logit

# Action-choice logits by team-relative band: short, progressive, long, carry, cross, shot
ACTION_BASE = np.array([
    [1.4, 0.4, 0.2, 0.0, NEG, NEG],
    [1.3, 0.8, 0.3, 0.3, NEG, NEG],
    [1.2, 1.0, 0.0, 0.5, NEG, NEG],
    [1.1, 1.0, -0.8, 0.6, NEG, -4.0],
    [0.9, 0.5, -2.0, 0.6, -0.6, -2.2],
    [0.6, -0.8, -3.0, 0.3, 0.0, -1.1],
])
# build_up modifiers, applied in bands 0-1 (full) and band 2 (half)
BUILD_MOD = np.array([
    [0.6, 0.0, -1.2, 0.0, 0.0, 0.0],   # short
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],    # mixed
    [-0.6, 0.0, 1.6, 0.0, 0.0, 0.0],   # direct
])
# Success intercept by action x band (shot row unused)
ALPHA = np.array([
    [4.1, 3.9, 3.2, 2.5, 1.8, 1.3],     # short
    [2.1, 2.0, 1.3, 0.5, 0.2, -0.1],    # progressive
    [0.3, 0.3, 0.1, -0.3, -0.7, -0.9],  # long
    [3.3, 3.0, 2.1, 0.8, 0.4, 0.1],     # carry
    [0.0, 0.0, 0.0, 0.0, -0.9, -1.1],   # cross
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],     # shot
])
# Opponent pressure intensity by their press_height (rows high/mid/low) at the POSSESSOR's band
PRESS_TABLE = np.array([
    [1.0, 1.0, 0.85, 0.65, 0.55, 0.55],
    [0.3, 0.45, 0.8, 0.9, 0.65, 0.6],
    [0.15, 0.2, 0.4, 0.75, 0.85, 0.85],
])
# Target-lane weights (team-relative) for progressive / long / carry by attack_channel
CHANNEL_W = np.array([
    [0.6, 0.25, 0.15],
    [0.2, 0.6, 0.2],
    [0.15, 0.25, 0.6],
    [0.34, 0.33, 0.33],
])
# Base seconds per action (+ jitter 0..2 s)
ACTION_DT = np.array([2.1, 3.0, 3.6, 3.0, 3.6, 2.5])

DEFAULT_COEFFICIENTS: dict[str, float] = {
    "beta_skill": 0.8,
    "beta_press": 2.2,
    "beta_fatigue": 1.0,
    "press_target_bonus": 0.6,
    "press_resistance_trait_penalty": 55.0,
    "long_vs_high_line": 0.4,
    "slow_cb_bonus": 0.9,
    "weak_channel_bonus": 0.6,
    "counter_bonus": 0.3,
    "counter_window_s": 10.0,
    "p_out_short": 0.12,
    "p_out_long": 0.35,
    "p_corner_failed_cross": 0.30,
    "p_corner_blocked_shot": 0.55,
    "shot_logit_offset": -0.4,  # calibrated on dev seasons 11-14 (eval/calibrate_sim.py, D-042)
    "goal_band5_center": 0.12,
    "goal_band5_wide": 0.05,
    "goal_band4_center": 0.043,
    "goal_band4_wide": 0.024,
    "goal_band3": 0.02,
    "counter_goal_mult": 1.4,
    "header_goal_mult": 0.75,
    "finishing_goal_mult": 0.6,
    "p_saved": 0.30,
    "p_off_target": 0.42,
    "corner_near_logit": -0.4,
    "corner_far_logit": -0.7,
    "corner_short_contact": 0.85,
    "corner_aerial_beta": 2.0,
    "back_post_weak_bonus": 1.6,
    "corner_header_goal": 0.12,
    "fatigue_rate": 0.0035,
    "fatigue_gk_rate": 0.001,
    "high_press_fatigue_mult": 1.25,
    "late_fade_mult": 0.6,
    "gk_short_short": 0.85,
    "gk_short_mixed": 0.55,
    "gk_short_direct": 0.2,
    "gk_short_bias_floor": 0.75,
    "stop_goal_s": 55.0,
    "stop_goal_kick_s": 18.0,
    "stop_throw_s": 9.0,
    "stop_corner_s": 25.0,
    "stop_save_s": 6.0,
    "stop_sub_s": 25.0,
}


def role_weight_table() -> np.ndarray:
    """(roles, bands, lanes) weights of a player being involved at a zone (team frame)."""
    w = np.zeros((len(ROLES), N_BANDS, N_LANES))
    for r, role in enumerate(ROLES):
        hb, hl = ROLE_HOME[role]
        for b in range(N_BANDS):
            for lane in range(N_LANES):
                w[r, b, lane] = np.exp(-((b - hb) ** 2) / 1.6 - ((lane - hl) ** 2) / 0.9)
        if role == "GK":
            w[r, 1:, :] *= 0.02
    return w


ROLE_W = role_weight_table()
