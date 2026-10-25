"""The committed demo bundle (web/public/match_bundle.json) is internally consistent, and every number the README
and the video script quote is in it. These tests guard the submission materials, not only the code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agents.validators import text as tv
from contracts import MatchBundle
from contracts.sealing import verify_choice, verify_plan
from engine import duel as dm
from pipeline.story import END, START, describe

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo() -> MatchBundle:
    return MatchBundle.model_validate_json((ROOT / "web" / "public" / "match_bundle.json").read_text())


@pytest.fixture(scope="module")
def claims(demo):
    return {c.claim_id: c for c in demo.claims}


def _filled_cues(demo, claims) -> str:
    return "\n".join(tv.fill(c.text.en, claims) for c in demo.cues)


def test_score_is_the_same_everywhere(demo):
    goals = {t: 0 for t in demo.plans}
    ht = None
    for e in demo.events:
        if e.type == "goal":
            goals[e.team] += 1
        if ht is None and e.period == 2:
            ht = dict(goals)
    story = demo.eval["story"]
    assert demo.snapshots[-1].score == goals == story["final_score"]
    assert demo.snapshots[45].score == story["ht_score"] == (ht or goals)


def test_matrix_cells_are_proper_expected_points(demo):
    duel = demo.duel
    for m in [duel.broadcast.true_matrix] + [p.believed_matrix for p in duel.private.values()]:
        for row in m.cells:
            for cell in row:
                a, b = cell.xpts[m.row_team], cell.xpts[m.col_team]
                assert 0 <= a <= 3 and 0 <= b <= 3
                assert 2 - 1e-6 <= a + b <= 3 + 1e-6  # 3 per decided match, 2 per draw
                for t in (m.row_team, m.col_team):
                    lo, hi = cell.ci90[t]
                    assert lo <= cell.xpts[t] <= hi


def test_readings_regret_and_best_responses_recompute(demo, claims):
    b = demo.duel.broadcast
    m = b.true_matrix
    for team, stored in m.readings.items():
        assert dm.reading(m, team, None) == stored
    for p in demo.duel.private.values():
        bm = p.believed_matrix
        assert dm.reading(bm, p.team, bm.col_probs) == bm.readings[p.team]
    for team, rg in b.regret.items():
        best, value = dm.regret(m, team, rg.chosen, rg.opponent_chosen)
        assert (rg.best_response, rg.regret_xpts) == (best, round(value, 3)) and rg.regret_xpts >= 0
        c = claims[rg.claim_id]
        assert c.interval_low <= c.value <= c.interval_high


def test_each_choice_follows_its_own_believed_matrix_and_rule(demo):
    for team, p in demo.duel.private.items():
        r = demo.duel.broadcast.revealed[team]
        reading = p.believed_matrix.readings[team]
        assert {"safe_pick": reading.safe_pick, "best_guess": reading.best_guess,
                "gamble": reading.gamble}[r.rule] == r.option_id
        assert verify_choice(p.choice.sha256, demo.duel.match_id, team, r.option_id, r.salt)
        other = next(t for t in demo.duel.private if t != team)
        assert all(e.option.estimated for e in p.opponent_estimate.options)  # its columns are its own guesses
        assert not {o.option_id for o in demo.duel.private[other].options} & set(p.believed_matrix.cols)


def test_every_half_time_option_is_a_real_alternative(demo):
    """Each option changes the levers in force at half-time (a fired Plan B included) and no two options, rows or
    columns are the same (D-054, D-055)."""
    from contracts.option import changes_nothing, tactics
    for team, p in demo.duel.private.items():
        now = demo.snapshots[45].active_levers[team].model_dump()
        assert p.options[0].intent == "stay_the_course"
        assert all(not changes_nothing(now, o.lever_changes, o.subs) for o in p.options[1:]), team
        assert len({tactics(now, o.lever_changes, o.subs) for o in p.options}) == len(p.options), team
    for m in [demo.duel.broadcast.true_matrix] + [p.believed_matrix for p in demo.duel.private.values()]:
        rows = [tuple(c.xpts[m.row_team] for c in row) for row in m.cells]
        cols = [tuple(row[j].xpts[m.row_team] for row in m.cells) for j in range(len(m.cols))]
        assert len(set(rows)) == len(rows) and len(set(cols)) == len(cols), m.matrix_id


def test_no_dominated_option_is_called_a_gamble(demo):
    for m in [demo.duel.broadcast.true_matrix] + [p.believed_matrix for p in demo.duel.private.values()]:
        for team, reading in m.readings.items():
            if reading.gamble:
                own, _, pay = dm.payoffs(m, team)
                g, s = own.index(reading.gamble), own.index(reading.safe_pick)
                assert max(pay[g]) > max(pay[s])


def test_plans_are_sealed_and_rest_on_served_evidence(demo, claims):
    served = {cid for t in demo.traces for cid in t.result_claims}
    for plan in demo.plans.values():
        assert verify_plan(plan)
        for ids in plan.lever_evidence.values():
            assert ids and all(i in claims and i in served for i in ids)
        assert plan.valuation in claims


def test_kpis_are_met_or_missed_at_full_time(demo):
    from engine.tracker import _TARGET
    plans = {p.plan_id: p for p in demo.plans.values()}
    for k in demo.snapshots[-1].kpis:
        kpi = next(x for x in plans[k.plan_id].kpis if x.id == k.kpi_id)
        op, thr = _TARGET.match(kpi.target).groups()
        met = {">=": k.value >= float(thr), "<=": k.value <= float(thr), ">": k.value > float(thr),
               "<": k.value < float(thr)}[op]
        assert k.status == ("on_track" if met else "failing"), (k.kpi_id, k.value, kpi.target)


def test_cues_verify_and_never_speak_before_their_data(demo, claims):
    for cue in demo.cues:
        for text in (cue.text.en, cue.text.es):
            assert tv.verify(text, claims) == []
        minute = int(cue.t_match.split(":")[0])
        for cid in cue.claims:
            c = claims[cid]
            if cid.startswith("c_ad_"):
                assert int(cid.split("_")[3]) <= minute  # the live detector fired by then
            elif c.type == "kpi_status":
                assert c.minute <= minute


def test_readme_story_block_is_the_bundle(demo):
    readme = (ROOT / "README.md").read_text()
    block = readme.split(START, 1)[1].split(END, 1)[0].strip()
    assert block == "\n".join(describe(demo))


def test_video_script_numbers_are_in_the_bundle(demo, claims):
    """Every number the narration quotes appears in the filled cues or the demo story."""
    script = (ROOT / "docs" / "VIDEO_SCRIPT.md").read_text()
    narration = " ".join(re.findall(r'\| "([^"]+)" \|', script))
    cues = _filled_cues(demo, claims)
    story = demo.eval["story"]
    words = {"one": 1, "two": 2, "three": 3, "nil": 0}
    for value in re.findall(r"\d+(?:\.\d+)?%?", narration):
        assert value in cues or value in str(story), f"narration number {value} is not in the bundle"
    for a, b in re.findall(r"\b(one|two|three|nil)-(one|two|three|nil)\b", narration.lower()):
        score = (words[a], words[b])
        assert score in {(story["ht_score"][t], story["ht_score"][o]) for t in story["ht_score"] for o in
                         story["ht_score"] if t != o} | {(story["final_score"][t], story["final_score"][o])
                                                         for t in story["final_score"] for o in story["final_score"]
                                                         if t != o}, (a, b)
