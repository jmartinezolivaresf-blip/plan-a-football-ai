"""Deterministic plan validator (v6 §9.14). The flow can never publish a plan that fails these rules."""

from __future__ import annotations

import re
from collections.abc import Iterable

from contracts import Levers, Plan, Squad
from contracts.refs import ValidationResult

DEFAULT_LEVERS = Levers()
LEVER_NAMES = ("press_height", "press_target", "build_up", "attack_channel", "corner_delivery")
SHARE_METRICS = {"final_third_entries_share"}
CHANNELS = {"left", "center", "right"}
MAX_SUBS, MAX_WINDOWS = 5, 3
_DIGIT = re.compile(r"\d")


def non_default_levers(plan: Plan) -> list[str]:
    return [n for n in LEVER_NAMES if getattr(plan.levers, n) != getattr(DEFAULT_LEVERS, n)]


def validate_plan(plan: Plan, squads: dict[str, Squad], claims_known: Iterable[str] | None = None) -> ValidationResult:
    """`claims_known`: claim ids actually served to this staff in this run (None = do not check provenance)."""
    errors: list[str] = []
    known = set(claims_known) if claims_known is not None else None
    if plan.team not in squads or plan.opponent not in squads or plan.team == plan.opponent:
        return ValidationResult(ok=False, errors=["plan teams are not the two teams of this match"])
    own = {p.player_id for p in squads[plan.team].players}
    starters = {p.player_id for p in squads[plan.team].players if p.starter}
    opp = {p.player_id for p in squads[plan.opponent].players}

    # levers and their evidence
    if plan.levers.press_target is not None and plan.levers.press_target not in opp:
        errors.append(f"press_target {plan.levers.press_target} is not an opponent player")
    for lever in non_default_levers(plan):
        cites = plan.lever_evidence.get(lever, [])
        if not cites:
            errors.append(f"lever {lever} changes from the default but cites no claim")
        elif known is not None:
            unknown = [c for c in cites if c not in known]
            if unknown:
                errors.append(f"lever {lever} cites claims this staff never retrieved: {unknown}")
    for lever in plan.lever_evidence:
        if lever not in LEVER_NAMES:
            errors.append(f"lever_evidence has an unknown lever {lever}")

    # KPIs: library metrics with measurable targets
    ids = [k.id for k in plan.kpis]
    if len(set(ids)) != len(ids):
        errors.append("duplicate KPI ids")
    for k in plan.kpis:
        value = float(k.target.lstrip("<>="))
        if k.metric in SHARE_METRICS:
            if k.params.get("channel") not in CHANNELS:
                errors.append(f"KPI {k.id}: final_third_entries_share needs channel left|center|right")
            if not 0 < value < 1:
                errors.append(f"KPI {k.id}: a share target must be between 0 and 1")
        elif value <= 0 and k.target.startswith(">"):
            errors.append(f"KPI {k.id}: target must be positive")

    # Plan B
    for i, rule in enumerate(plan.plan_b):
        c = rule.if_
        if c.kpi is None and c.after_minute is None and c.score_diff is None:
            errors.append(f"plan_b[{i}] has no condition")
        if (c.kpi is None) != (c.status is None):
            errors.append(f"plan_b[{i}] needs both kpi and status, or neither")
        if c.kpi is not None and c.kpi not in ids:
            errors.append(f"plan_b[{i}] references unknown KPI {c.kpi}")
        lc = rule.then.levers
        if lc.press_target is not None and lc.press_target not in opp:
            errors.append(f"plan_b[{i}] press_target is not an opponent player")
        if lc.model_dump(exclude_none=True) == {} and not rule.then.subs:
            errors.append(f"plan_b[{i}] changes nothing")

    # Substitutions: 5 subs, 3 in-play windows + half-time, players valid
    subs = list(plan.subs_plan) + [s for r in plan.plan_b for s in r.then.subs]
    if len(subs) > MAX_SUBS:
        errors.append(f"more than {MAX_SUBS} substitutions planned")
    windows = {s.window for s in plan.subs_plan if s.window != "HT"}
    if len(windows) > MAX_WINDOWS:
        errors.append(f"more than {MAX_WINDOWS} in-play substitution windows")
    off, on = set(), set()
    for s in subs:
        if s.out not in own or s.into not in own:
            errors.append(f"sub {s.out}->{s.into}: unknown player")
            continue
        if s.into in starters:
            errors.append(f"sub {s.out}->{s.into}: {s.into} already starts")
        if s.out in off:
            errors.append(f"sub {s.out}->{s.into}: {s.out} is already subbed off")
        if s.into in on:
            errors.append(f"sub {s.out}->{s.into}: {s.into} already comes on")
        if s.out not in starters and s.out not in on:
            errors.append(f"sub {s.out}->{s.into}: {s.out} is not on the pitch")
        off.add(s.out)
        on.add(s.into)
        if "-" in s.window:
            a, b = (int(x) for x in s.window.split("-"))
            if a > b or b > 90:
                errors.append(f"sub {s.out}->{s.into}: bad window {s.window}")

    # Names are display text: no numbers (numbers only come from claims)
    for lang in ("en", "es"):
        if _DIGIT.search(getattr(plan.name, lang)):
            errors.append(f"plan name ({lang}) must not contain numbers")
    return ValidationResult(ok=not errors, errors=errors)
