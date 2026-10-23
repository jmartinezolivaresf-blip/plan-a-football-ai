"""Plans and half-time choices seal and verify with SHA-256 (commit-reveal)."""

from __future__ import annotations

from contracts.sealing import choice_digest, new_salt, plan_digest, verify_choice, verify_plan


def test_fixture_plans_verify(bundle):
    for plan in bundle.plans.values():
        assert verify_plan(plan), plan.plan_id


def test_tampered_plan_fails(bundle):
    plan = bundle.plans["KES"].model_copy(deep=True)
    plan.levers.press_height = "low"
    assert not verify_plan(plan)


def test_digest_ignores_the_seal_itself(bundle):
    plan = bundle.plans["HAR"].model_copy(deep=True)
    before = plan_digest(plan)
    plan.sealed = None
    assert plan_digest(plan) == before


def test_fixture_choices_reveal_correctly(duel):
    for team, revealed in duel.broadcast.revealed.items():
        sealed = duel.private[team].choice
        assert verify_choice(sealed.sha256, duel.match_id, team, revealed.option_id, revealed.salt)


def test_wrong_option_or_salt_does_not_verify(duel):
    sealed = duel.private["KES"].choice
    salt = duel.broadcast.revealed["KES"].salt
    assert not verify_choice(sealed.sha256, duel.match_id, "KES", "KES-HT-A", salt)
    assert not verify_choice(sealed.sha256, duel.match_id, "KES", "KES-HT-B", "0" * 32)


def test_salt_prevents_guessing_from_option_ids():
    a, b = new_salt(), new_salt()
    assert a != b and len(a) == 32
    assert choice_digest("m", "KES", "X", a) != choice_digest("m", "KES", "X", b)
