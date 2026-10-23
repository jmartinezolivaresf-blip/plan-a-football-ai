"""Monte Carlo valuation: plans vs a default, believed and true duel matrices, paired-difference intervals.

Benches value options with the PUBLIC world model (the simulator without hidden traits, D-033); only the broadcast
true matrix uses the real world. Every number here comes from simulations and is reported with R and an interval.
"""

from __future__ import annotations

import numpy as np

from contracts import Cell, Claim, I18nText, Kpi, Levers, Matrix, Option, Plan
from contracts.plan import OpponentPlanEstimate

from . import duel as dm

BOOTSTRAP = 1000


def points(goals_for: list[int], goals_against: list[int]) -> np.ndarray:
    a, b = np.asarray(goals_for), np.asarray(goals_against)
    return np.where(a > b, 3.0, np.where(a == b, 1.0, 0.0))


def paired_ci(diff: np.ndarray, seed: int = 0, level: float = 0.90) -> tuple[float, float]:
    """Bootstrap interval of the mean of paired differences (same seeds -> paired replicas)."""
    if len(diff) < 2:
        return float(diff.mean()), float(diff.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diff), size=(BOOTSTRAP, len(diff)))
    means = diff[idx].mean(axis=1)
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def estimate_plan(est: OpponentPlanEstimate) -> Plan:
    return Plan(plan_id=f"{est.opponent}-estimated", team=est.opponent, opponent=est.estimator,
                name=I18nText(en="Estimated plan", es="Plan estimado"), levers=est.levers,
                kpis=[Kpi(id="k1", metric="balls_in_behind_conceded", target="<=3")])


def default_plan(plan: Plan) -> Plan:
    return plan.model_copy(update={"levers": Levers(), "plan_b": [], "subs_plan": [], "lever_evidence": {},
                                   "plan_id": f"{plan.team}-default", "sealed": None})


def label_for(delta: float, lo: float, hi: float) -> str:
    if abs(delta) >= 0.10 and (lo > 0 or hi < 0):
        return "clear gain" if delta > 0 else "clear loss"
    if lo <= 0 <= hi and min(abs(lo), abs(hi)) < 0.05:
        return "within noise"
    return "marginal"


def matrix_from_outcomes(matrix_id: str, match_id: str, kind: str, believer: str | None, row_team: str,
                         col_team: str, rows: list[Option], cols: list[Option], outcomes: list[list],
                         probs: list[float] | None, R: int, seed: int) -> tuple[Matrix, list[Claim]]:
    """outcomes[i][j] = sim Outcomes for row option i x column option j (same seeds)."""
    claims: list[Claim] = []
    persp = believer or row_team
    other = col_team if persp == row_team else row_team
    base = points(outcomes[0][0].goals[persp], outcomes[0][0].goals[other])
    cells = []
    for i, row in enumerate(outcomes):
        cr = []
        for j, out in enumerate(row):
            cid = f"cm_{matrix_id}_{i}{j}"
            p = points(out.goals[persp], out.goals[other])
            diff = p - base
            lo, hi = paired_ci(diff, seed=seed + 10 * i + j)
            delta = float(diff.mean())
            claims.append(Claim(claim_id=cid, type="sim_matrix_cell", team=persp, metric="xpts_delta_vs_stay_stay",
                                value=round(delta, 3), n=R, interval_low=round(lo, 3), interval_high=round(hi, 3),
                                label=f"{rows[i].option_id} x {cols[j].option_id}: {label_for(delta, lo, hi)}"))
            cr.append(Cell(xpts={t: round(out.xpts[t], 4) for t in (row_team, col_team)},
                           ci90={t: (round(out.ci90[t][0], 4), round(out.ci90[t][1], 4)) for t in (row_team, col_team)},
                           claim_id=cid))
        cells.append(cr)
    m = Matrix(matrix_id=matrix_id, match_id=match_id, kind=kind, believer=believer, row_team=row_team,
               col_team=col_team, rows=[o.option_id for o in rows], cols=[o.option_id for o in cols], col_probs=probs,
               cells=cells, R=R, seed=seed)
    if kind == "believed":
        m.readings = {believer: dm.reading(m, believer, probs)}
    else:
        m.readings = {t: dm.reading(m, t) for t in (row_team, col_team)}
    return m, claims


def stay_option(team: str, option_id: str | None = None) -> Option:
    return Option(option_id=option_id or f"{team}-HT-A", team=team, label=I18nText(en="Stay the course",
                                                                                   es="Mantener el plan"),
                  intent="stay_the_course")
