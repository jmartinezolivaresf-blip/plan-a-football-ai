"""Plan validator and text verifier, including deliberately wrong inputs."""

from __future__ import annotations

import pytest

from agents.validators import text as tv
from agents.validators.plan import validate_plan
from contracts import Claim, I18nText, Levers, PlanBAction, PlanBCondition, PlanBRule, Sub

from .agent_helpers import plans, squads

CLAIMS = {
    "c1": Claim(claim_id="c1", type="observed_tendency", metric="m", value=31.7, league_ref=15.2, n=41),
    "c2": Claim(claim_id="c2", type="observed_tendency", metric="m", value=0.4, n=6, status="insufficient"),
    "c3": Claim(claim_id="c3", type="observed_mechanism", metric="pressers", value=2.6),
    "c4": Claim(claim_id="c4", type="sim_valuation", metric="dxpts", value=0.21, interval_low=0.1,
                interval_high=0.3),
}


def _ok(plan):
    return validate_plan(plan, squads().teams)


# ------------------------------------------------------------------ plan validator
def test_fixture_plans_are_valid():
    for p in plans().values():
        assert _ok(p).ok


def test_non_default_lever_without_evidence_is_rejected():
    p = plans()["KES"].model_copy(update={"lever_evidence": {}})
    res = _ok(p)
    assert not res.ok and any("cites no claim" in e for e in res.errors)


def test_evidence_must_have_been_retrieved():
    p = plans()["KES"]
    assert not validate_plan(p, squads().teams, claims_known=set()).ok
    known = {c for cs in p.lever_evidence.values() for c in cs}
    assert validate_plan(p, squads().teams, claims_known=known).ok


@pytest.mark.parametrize("update,needle", [
    ({"levers": Levers(press_target="KES-3")}, "not an opponent player"),
    ({"subs_plan": [Sub(window="60-65", out="KES-12", into="KES-13")]}, "not on the pitch"),
    ({"subs_plan": [Sub(window="60-65", out="KES-2", into="KES-3")]}, "already starts"),
    ({"subs_plan": [Sub(window="60-65", out="KES-2", into="KES-13"), Sub(window="70-75", out="KES-2",
                                                                          into="KES-14")]}, "already subbed off"),
    ({"subs_plan": [Sub(window=f"{50 + 5 * i}-{52 + 5 * i}", out=f"KES-{2 + i}", into=f"KES-{12 + i}")
                    for i in range(4)]}, "windows"),
    ({"plan_b": [PlanBRule(if_=PlanBCondition(kpi="kX", status="failing"), then=PlanBAction(
        levers={"press_height": "low"}))]}, "unknown KPI"),
    ({"plan_b": [PlanBRule(if_=PlanBCondition(), then=PlanBAction(levers={"press_height": "low"}))]}, "no condition"),
    ({"plan_b": [PlanBRule(if_=PlanBCondition(after_minute=30), then=PlanBAction())]}, "changes nothing"),
    ({"name": I18nText(en="Press for 90 minutes", es="x")}, "numbers"),
])
def test_invalid_plans_are_rejected(update, needle):
    res = _ok(plans()["KES"].model_copy(update=update))
    assert not res.ok and any(needle in e for e in res.errors), res.errors


# ------------------------------------------------------------------ text verifier
def test_valid_text_passes_and_fills():
    text = "Their left-back loses it under pressure: {c1.value} vs {c1.league_ref} (n {c1.n})."
    assert tv.verify(text, CLAIMS) == []
    assert tv.fill(text, CLAIMS) == "Their left-back loses it under pressure: 31.7 vs 15.2 (n 41)."


@pytest.mark.parametrize("text,needle", [
    ("Their left-back loses the ball 31 times. [c1]", "numbers"),
    ("Pressure works {c9.value}.", "unknown claim c9"),
    ("Value {c1.metric}.", "not allowed"),
    ("Value {c3.league_ref}.", "has no league_ref"),
    ("They lose the ball under pressure.", "cites no claim"),
    ("They always lose it: {c2.value}.", "insufficient evidence"),
    ("We won the ball because of our press {c1.value}.", "causal"),
    ("", "empty"),
])
def test_invalid_texts_are_rejected(text, needle):
    errors = tv.verify(text, CLAIMS)
    assert any(needle in e for e in errors), errors


def test_hedged_insufficient_and_mechanism_backed_causal_pass():
    assert tv.verify("It may be an early sign: {c2.value}.", CLAIMS) == []
    assert tv.verify("Recoveries rose because more players pressed the ball ({c3.value}).", CLAIMS) == []


def test_casual_mode_rejects_intervals():
    text = "Worth {c4.value} ({c4.interval_low} to {c4.interval_high})."
    assert tv.verify(text, CLAIMS, mode="analyst") == []
    assert any("intervals" in e for e in tv.verify(text, CLAIMS, mode="casual"))


def test_player_ids_are_not_numbers():
    assert tv.verify("HAR-5 loses it under pressure: {c1.value}.", CLAIMS) == []


def test_regenerate_twice_then_fallback():
    attempts = []

    def gen(errors):
        attempts.append(errors)
        return "Invented 42 stat."

    text, history, used = tv.with_fallback(gen, CLAIMS, fallback="Observed: {c1.value} (n {c1.n}).")
    assert used and len(attempts) == tv.MAX_ATTEMPTS == 3 and text.startswith("Observed")
    assert attempts[0] == [] and attempts[1]  # the second call receives the validator errors


def test_correction_succeeds_before_fallback():
    texts = iter(["Bad 7.", "Good {c1.value}."])
    text, history, used = tv.with_fallback(lambda e: next(texts), CLAIMS, fallback="x {c1.value}.")
    assert not used and text == "Good {c1.value}." and len(history) == 2


def test_broken_fallback_raises():
    with pytest.raises(ValueError):
        tv.with_fallback(lambda e: "bad 1", CLAIMS, fallback="also bad 2")


def test_negative_zero_is_written_as_zero():
    from agents.validators.text import format_value
    from contracts import Claim
    c = Claim(claim_id="c_x", type="observed_tendency", metric="goal_kick_short_vs_open_play", value=-0.002)
    assert format_value(c, "value") == "0"


def test_analyst_keeps_one_finding_per_theme():
    from agents.offline import scouting
    base = {"type": "observed_tendency", "team": "HAR", "status": "sufficient", "n": 30}
    claims = [
        {**base, "claim_id": "c_a", "metric": "goal_kick_short_share", "value": 0.8, "league_ref": 0.5,
         "interval_low": 0.7, "interval_high": 0.9},
        {**base, "claim_id": "c_b", "metric": "goal_kick_short_vs_open_play", "value": 0.1, "league_ref": -0.1,
         "interval_low": 0.0, "interval_high": 0.2, "label": "goal kicks short minus open-play short share"},
        {**base, "claim_id": "c_c", "metric": "entries_conceded_share", "value": 0.5, "league_ref": 0.3,
         "interval_low": 0.4, "interval_high": 0.6, "label": "left channel"},
        {**base, "claim_id": "c_d", "metric": "forward_success_conceded_share", "value": 0.7, "league_ref": 0.6,
         "interval_low": 0.65, "interval_high": 0.75, "label": "left channel"},
        {**base, "claim_id": "c_e", "metric": "forward_success_conceded_share", "value": 0.7, "league_ref": 0.6,
         "interval_low": 0.65, "interval_high": 0.75, "label": "right channel"},
    ]
    ids = [f.claim_id for f in scouting({"claims": claims}).findings]
    assert sorted(ids) == ["c_b", "c_d", "c_e"]  # the controlled statistic wins its theme; sides stay separate
