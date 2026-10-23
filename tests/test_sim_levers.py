"""Each of the 5 levers (and the v6 §9.2 interactions) has a statistically detectable effect."""

from __future__ import annotations

import numpy as np

from sim.core import S_CORNERS, S_FIRST_CONTACT, S_LONG
from sim.world import K_BIB, K_ENT, K_ENT_L, K_ENT_R, K_HT, K_SPXG

from .sim_helpers import batch, plain_plans, points

R = 400


def test_probabilities_stay_valid():
    b, _ = batch(plain_plans(kes={"press_height": "high", "press_target": "HAR-5", "build_up": "direct"},
                             har={"build_up": "short", "press_height": "low"}), 200, 1, debug=True)
    assert b.checked > 1000


def test_high_press_vs_short_build_up_wins_more_high_balls():
    _, high = batch(plain_plans(kes={"press_height": "high"}, har={"build_up": "short"}), R, 3)
    _, low = batch(plain_plans(kes={"press_height": "low"}, har={"build_up": "short"}), R, 3)
    assert high.counters[:, 0, K_HT].mean() > 1.3 * low.counters[:, 0, K_HT].mean()


def test_press_target_increases_that_players_losses():
    _, target = batch(plain_plans(kes={"press_height": "high", "press_target": "HAR-5"}), R, 4)
    _, none = batch(plain_plans(kes={"press_height": "high"}), R, 4)
    assert target.losses_by_player[:, 1, 4].mean() > 1.2 * none.losses_by_player[:, 1, 4].mean()


def test_direct_build_up_beats_a_high_press_more_often_in_behind():
    _, direct = batch(plain_plans(kes={"press_height": "high"}, har={"build_up": "direct"}), R, 5)
    _, short = batch(plain_plans(kes={"press_height": "high"}, har={"build_up": "short"}), R, 5)
    assert direct.stats[:, 1, S_LONG].mean() > 1.3 * short.stats[:, 1, S_LONG].mean()
    assert direct.counters[:, 0, K_BIB].mean() > short.counters[:, 0, K_BIB].mean()


def test_attack_channel_shifts_entries():
    _, right = batch(plain_plans(kes={"attack_channel": "right"}), R, 6)
    _, left = batch(plain_plans(kes={"attack_channel": "left"}), R, 6)

    def share(res, k):
        return res.counters[:, 0, k].sum() / res.counters[:, 0, K_ENT].sum()

    assert share(right, K_ENT_R) > share(right, K_ENT_L) + 0.1
    assert share(right, K_ENT_R) > share(left, K_ENT_R) + 0.1


def test_far_post_pays_against_a_weak_back_post():
    """HAR has back_post_weak in the truth fixture: far-post corners win more first contacts."""
    _, far = batch(plain_plans(kes={"corner_delivery": "far_post"}), R, 7)
    _, near = batch(plain_plans(kes={"corner_delivery": "near_post"}), R, 7)

    def rate(res):
        return res.stats[:, 0, S_FIRST_CONTACT].sum() / res.stats[:, 0, S_CORNERS].sum()

    assert rate(far) > rate(near) + 0.05
    assert far.counters[:, 0, K_SPXG].mean() > near.counters[:, 0, K_SPXG].mean()


def test_far_post_has_no_bonus_without_the_weakness():
    """Against KES (no back_post_weak), HAR's far post is not better than near post."""
    _, far = batch(plain_plans(har={"corner_delivery": "far_post"}), R, 8)
    _, near = batch(plain_plans(har={"corner_delivery": "near_post"}), R, 8)

    def rate(res):
        return res.stats[:, 1, S_FIRST_CONTACT].sum() / res.stats[:, 1, S_CORNERS].sum()

    assert rate(far) <= rate(near) + 0.03


def test_no_strategy_always_wins():
    combos = [{}, {"press_height": "high", "press_target": "HAR-5", "attack_channel": "right"},
              {"press_height": "low", "build_up": "direct"}, {"build_up": "short", "corner_delivery": "short"}]
    for kes in combos:
        _, res = batch(plain_plans(kes=kes), 300, 9)
        p = points(res.score, 0)
        win = (p == 3).mean()
        assert 0.1 < win < 0.75, (kes, win)
        assert 0.6 < p.mean() < 2.2, (kes, p.mean())


def test_lever_effects_are_bounded():
    """No single lever moves expected points by more than one point (v6: effects of tenths)."""
    _, base = batch(plain_plans(), R, 10)
    for kes in ({"press_height": "high"}, {"press_height": "low"}, {"build_up": "short"}, {"build_up": "direct"},
                {"attack_channel": "left"}, {"corner_delivery": "far_post"}):
        _, res = batch(plain_plans(kes=kes), R, 10)
        assert abs(points(res.score, 0).mean() - points(base.score, 0).mean()) < 1.0, kes
    assert np.isfinite(base.counters).all()
