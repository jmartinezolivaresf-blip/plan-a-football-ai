"""The scripted fixture match is internally coherent and every reference resolves."""

from __future__ import annotations

import re

from contracts import zone_index
from contracts.claim import PLACEHOLDER_FIELDS

PLACEHOLDER = re.compile(r"\{(c[\w-]+)\.(\w+)\}")
ACTIONS = {"pass", "long_ball", "cross", "carry", "shot", "goal_kick", "corner", "kick_off"}


def test_event_clock_ids_and_zones(bundle):
    evs = bundle.events
    assert len({e.event_id for e in evs}) == len(evs)
    assert all(a.t < b.t for a, b in zip(evs, evs[1:], strict=False))
    assert all(e.zone == zone_index(e.x, e.y) for e in evs)
    assert all((e.period == 1) == (e.t < 2700) for e in evs)


def test_possession_continuity(bundle):
    """After a possession change the next on-ball action is by the winning team, starting with the winner."""
    evs = bundle.events
    for i, e in enumerate(evs):
        if e.type != "possession_change":
            continue
        nxt = next((f for f in evs[i + 1:] if f.type in ACTIONS), None)
        if nxt is None:  # the match ended during this possession
            continue
        assert nxt.team == e.team, e.event_id
        if nxt.type in ("pass", "long_ball", "cross", "carry", "shot"):
            assert nxt.player_id == e.player_id, e.event_id


def test_completed_passes_chain_to_receiver(bundle):
    evs = [e for e in bundle.events if e.type in ACTIONS | {"interception", "tackle"}]
    for a, b in zip(evs, evs[1:], strict=False):
        if a.type == "pass" and a.outcome == "success" and b.type in ("pass", "cross", "shot", "long_ball"):
            if b.team == a.team:
                assert b.player_id == a.receiver_id, a.event_id


def test_snapshot_score_matches_goal_events(bundle):
    goals = {"KES": 0, "HAR": 0}
    for e in bundle.events:
        if e.type == "goal":
            goals[e.team] += 1
    assert bundle.snapshots[-1].score == goals == {"KES": 2, "HAR": 1}
    assert bundle.snapshots[45].score == {"KES": 0, "HAR": 1}


def test_all_claim_references_resolve(bundle):
    ids = {c.claim_id for c in bundle.claims}
    refs: set[str] = set()
    for plan in bundle.plans.values():
        refs |= {c for cs in plan.lever_evidence.values() for c in cs}
        refs |= {plan.valuation} if plan.valuation else set()
    for cue in bundle.cues:
        refs |= set(cue.claims)
        for text in [cue.text.en, cue.text.es, *cue.fields.values()]:
            for cid, field in PLACEHOLDER.findall(text):
                assert field in PLACEHOLDER_FIELDS, field
                refs.add(cid)
    duel = bundle.duel
    for m in [duel.broadcast.true_matrix, *(p.believed_matrix for p in duel.private.values())]:
        refs |= {c.claim_id for row in m.cells for c in row if c.claim_id}
    for t in bundle.traces:
        refs |= set(t.result_claims)
    missing = refs - ids
    assert not missing, missing


def test_placeholders_only_in_cue_text_never_raw_numbers_from_llm(bundle):
    """Cue texts carry numbers only through placeholders (digits allowed only inside {...})."""
    for cue in bundle.cues:
        for text in (cue.text.en, cue.text.es):
            stripped = PLACEHOLDER.sub("", text)
            assert not re.search(r"\d", stripped.replace("1-0", "")), (cue.cue_id, text)


def test_every_non_default_lever_has_evidence(bundle):
    defaults = {"press_height": "mid", "press_target": None, "build_up": "mixed", "attack_channel": "balanced",
                "corner_delivery": "near_post"}
    for plan in bundle.plans.values():
        for lever, default in defaults.items():
            if getattr(plan.levers, lever) != default:
                assert plan.lever_evidence.get(lever), (plan.plan_id, lever)
