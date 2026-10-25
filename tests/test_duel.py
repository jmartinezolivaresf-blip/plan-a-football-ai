"""Matrix format, estimate probabilities, readings and regret."""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from contracts import Matrix
from engine import duel as dm


def all_matrices(duel):
    return [duel.broadcast.true_matrix, *(p.believed_matrix for p in duel.private.values())]


def test_matrix_shape_and_kinds(duel):
    true = duel.broadcast.true_matrix
    assert true.kind == "true" and true.believer is None and true.col_probs is None
    assert len(true.rows) == len(true.cols) == 3
    for team, priv in duel.private.items():
        m = priv.believed_matrix
        assert m.kind == "believed" and m.believer == team and m.row_team == team
        assert m.rows == [o.option_id for o in priv.options]
        assert m.cols == [o.option.option_id for o in priv.opponent_estimate.options]
        assert m.col_probs == [o.probability for o in priv.opponent_estimate.options]
    for m in all_matrices(duel):
        assert all(len(r) == len(m.cols) for r in m.cells)
        for row in m.cells:
            for c in row:
                for team, (lo, hi) in c.ci90.items():
                    assert lo <= c.xpts[team] <= hi


def test_true_matrix_uses_the_real_options(duel):
    true = duel.broadcast.true_matrix
    assert true.rows == [o.option_id for o in duel.private["KES"].options]
    assert true.cols == [o.option_id for o in duel.private["HAR"].options]


def test_stay_is_first_option(duel):
    for priv in duel.private.values():
        assert priv.options[0].intent == "stay_the_course"
        assert priv.opponent_estimate.options[0].option.intent == "stay_the_course"


def test_estimated_probabilities_sum_to_one(duel):
    for priv in duel.private.values():
        assert sum(o.probability for o in priv.opponent_estimate.options) == pytest.approx(1.0)


def test_matrix_rejects_probabilities_that_do_not_sum_to_one(duel):
    data = duel.private["KES"].believed_matrix.model_dump(mode="json")
    data["col_probs"] = [0.5, 0.2, 0.2]
    with pytest.raises(ValidationError):
        Matrix.model_validate(data)


def test_matrix_rejects_bad_shape(duel):
    data = duel.broadcast.true_matrix.model_dump(mode="json")
    data["cells"] = data["cells"][:2]
    with pytest.raises(ValidationError):
        Matrix.model_validate(data)


def test_stored_readings_match_recomputation(duel):
    for m in all_matrices(duel):
        for team, stored in m.readings.items():
            assert dm.reading(m, team, m.col_probs if m.kind == "believed" else None) == stored


def test_choices_follow_each_bench_rule_on_its_own_believed_matrix(duel):
    for team, revealed in duel.broadcast.revealed.items():
        reading = duel.private[team].believed_matrix.readings[team]
        pick = {"safe_pick": reading.safe_pick, "best_guess": reading.best_guess, "gamble": reading.gamble}
        assert pick[revealed.rule] == revealed.option_id


def test_regret_is_consistent_and_non_negative(duel):
    true = duel.broadcast.true_matrix
    for team, r in duel.broadcast.regret.items():
        best, value = dm.regret(true, team, r.chosen, r.opponent_chosen)
        assert r.best_response == best
        assert r.regret_xpts == pytest.approx(value, abs=1e-9)
        assert r.regret_xpts >= -1e-9
        assert r.chosen == duel.broadcast.revealed[team].option_id


def test_regret_non_negative_on_random_matrices(duel):
    template = duel.broadcast.true_matrix.model_dump(mode="json")
    rng = random.Random(0)
    for _ in range(200):
        for row in template["cells"]:
            for c in row:
                k, h = rng.uniform(0, 3), rng.uniform(0, 3)
                c["xpts"] = {"KES": k, "HAR": h}
                c["ci90"] = {"KES": [k, k], "HAR": [h, h]}
        m = Matrix.model_validate(template | {"readings": {}})
        for team, own, opp in (("KES", m.rows, m.cols), ("HAR", m.cols, m.rows)):
            _, value = dm.regret(m, team, rng.choice(own), rng.choice(opp))
            assert value >= -1e-12


def test_a_dominated_option_is_never_a_gamble():
    from contracts import Cell, Matrix
    # row 1 is better than row 0 in every column (dominant); row 0 must not be called a gamble
    vals = [[1.0, 0.9], [1.2, 1.1]]
    cells = [[Cell(xpts={"KES": v, "HAR": 3 - v}, ci90={"KES": (v - .05, v + .05), "HAR": (2.9 - v, 3.1 - v)},
                   claim_id=f"cm_t_{i}{j}") for j, v in enumerate(row)] for i, row in enumerate(vals)]
    m = Matrix(matrix_id="t", match_id="m", kind="true", row_team="KES", col_team="HAR", rows=["A", "B"],
               cols=["X", "Y"], cells=cells, R=10, seed=1)
    assert dm.dominant(m, "KES") == "B" and dm.safe_pick(m, "KES") == "B" and dm.gamble(m, "KES") is None
