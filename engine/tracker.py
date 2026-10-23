"""Plan Tracker (4 KPIs vs the expected trajectory from pre-match sims) and opponent adaptation detection."""

from __future__ import annotations

import re
from dataclasses import dataclass

from contracts import Claim, Event, KpiStatus, Plan

from .eventsx import entry_lane, goal_kick_is_long, is_ball_in_behind, is_entry, is_high_turnover, rel_x
from .xg import XGModel

LANES = {"left": 0, "center": 1, "right": 2}
_TARGET = re.compile(r"^(>=|<=|>|<)(\d+(?:\.\d+)?)$")
HALF_X = 52.5
HOLD_MINUTES = 2  # hysteresis: a new status must hold this long before it is reported


@dataclass
class KpiValue:
    value: float
    n: int


def kpi_value(metric: str, params: dict[str, str], team: str, events: list[Event], home: str,
              xg: XGModel) -> KpiValue:
    opp_events = [e for e in events if e.team != team]
    own = [e for e in events if e.team == team]
    if metric == "high_turnovers":
        return KpiValue(sum(is_high_turnover(e, home) for e in own), sum(e.type == "pressure" for e in own))
    if metric == "final_third_entries_share":
        entries = [e for e in own if is_entry(e, home)]
        lane = LANES.get(params.get("channel", "center"), 1)
        hits = sum(entry_lane(e, home) == lane for e in entries)
        return KpiValue(hits / len(entries) if entries else 0.0, len(entries))
    if metric == "set_piece_xg":
        shots = [e for e in own if e.type == "shot" and e.set_piece_ref]
        return KpiValue(round(sum(xg(e, home) for e in shots), 3), sum(e.type == "corner" for e in own))
    if metric == "balls_in_behind_conceded":
        longs = [e for e in opp_events if e.type == "long_ball"]
        return KpiValue(sum(is_ball_in_behind(e, home) for e in longs), len(longs))
    raise ValueError(f"unknown KPI metric {metric}")


def expected_at(metric: str, params: dict[str, str], team: str, minute: int,
                trajectories: dict[str, list[float]]) -> float | None:
    """Mean of pre-match simulations at this minute (sim counters share the engine's definitions, D-015)."""
    def at(key: str) -> float | None:
        series = trajectories.get(f"{team}:{key}")
        return series[min(minute, len(series) - 1)] if series else None

    if metric == "final_third_entries_share":
        lane = {"left": "entries_left", "center": "entries_center", "right": "entries_right"}[params.get("channel",
                                                                                                         "center")]
        a, b = at(lane), at("entries_total")
        return a / b if a is not None and b else None
    return at(metric)


def status_for(op: str, value: KpiValue, expected: float | None, metric: str, minute: int) -> tuple[str, float, float]:
    """(status, band_low, band_high) for one KPI at one minute."""
    if expected is None:
        return "insufficient_evidence", 0.0, 0.0
    width = 0.12 if metric == "final_third_entries_share" else (0.12 if metric == "set_piece_xg"
                                                                 else max(1.0, 0.3 * expected))
    low, high = max(0.0, expected - width), expected + width
    min_n = 8 if metric == "final_third_entries_share" else 1
    if minute < 10 or value.n < min_n:
        return "insufficient_evidence", low, high
    if op in (">=", ">"):
        status = "on_track" if value.value >= low else "at_risk" if value.value >= low - width else "failing"
    else:
        status = "on_track" if value.value <= high else "at_risk" if value.value <= high + width else "failing"
    return status, low, high


class PlanTracker:
    """Computes KPI statuses minute by minute with hysteresis and emits kpi_status claims."""

    def __init__(self, plan: Plan, home: str, xg: XGModel, trajectories: dict[str, list[float]]):
        self.plan, self.home, self.xg, self.traj = plan, home, xg, trajectories
        self.reported: dict[str, str] = {}
        self.pending: dict[str, tuple[str, int]] = {}

    def at(self, minute: int, events: list[Event]) -> tuple[list[KpiStatus], list[Claim]]:
        upto = [e for e in events if e.minute < minute or (minute == 0 and e.minute == 0)]
        statuses, claims = [], []
        for k in self.plan.kpis:
            op = _TARGET.match(k.target).group(1)
            v = kpi_value(k.metric, k.params, self.plan.team, upto, self.home, self.xg)
            exp = expected_at(k.metric, k.params, self.plan.team, minute, self.traj)
            raw, low, high = status_for(op, v, exp, k.metric, minute)
            status = self._hysteresis(k.id, raw, minute)
            cid = f"c_kpi_{self.plan.team}_{k.id}_{minute}"
            statuses.append(KpiStatus(plan_id=self.plan.plan_id, kpi_id=k.id, team=self.plan.team,
                                      value=round(v.value, 3), expected=None if exp is None else round(exp, 3),
                                      band_low=round(low, 3), band_high=round(high, 3), n=v.n, status=status,
                                      claim_id=cid))
            claims.append(Claim(claim_id=cid, type="kpi_status", team=self.plan.team, metric=k.metric,
                                value=round(v.value, 3), n=v.n, target=k.target, minute=minute, label=status,
                                interval_low=round(low, 3), interval_high=round(high, 3)))
        return statuses, claims

    def _hysteresis(self, kpi_id: str, raw: str, minute: int) -> str:
        current = self.reported.get(kpi_id)
        if current is None or raw == current:
            self.reported[kpi_id] = raw
            self.pending.pop(kpi_id, None)
            return raw
        since = self.pending.get(kpi_id)
        if since is None or since[0] != raw:
            self.pending[kpi_id] = (raw, minute)
            return current
        if minute - since[1] >= HOLD_MINUTES - 1:
            self.reported[kpi_id] = raw
            self.pending.pop(kpi_id, None)
            return raw
        return current


# Adaptation thresholds for the ONLINE detector (re-tested every minute), calibrated on synthetic dev seasons 11-14
# (eval/calibrate_adaptation.py, result in eval/results/adaptation_calibration.json): 7 of 192 unchanged team-matches
# raise an alarm at some minute and 48 of 48 injected build-up switches are found, a median 6.5 minutes later
# (D-038). A test keeps ADAPT_MIN_Z equal to the calibration's choice.
ADAPT_MIN_SIDE = 20
ADAPT_MIN_CHANGE = 0.2
ADAPT_MIN_Z = 4.0
EVIDENCE_IDS = 12


def build_up_actions(team: str, events: list[Event], home: str) -> list[tuple[Event, float]]:
    """A team's build-up actions in its own half (passes, long balls, carries, goal kicks), flagged 1.0 if long."""
    out = []
    for e in events:
        if e.team != team:
            continue
        if e.type == "goal_kick":
            out.append((e, 1.0 if goal_kick_is_long(e, home) else 0.0))
        elif e.type in ("pass", "long_ball", "carry") and rel_x(e, team, home) < HALF_X:
            out.append((e, 1.0 if e.type == "long_ball" else 0.0))
    return out


def _z(before: float, n1: int, after: float, n2: int) -> float:
    pooled = (before * n1 + after * n2) / (n1 + n2)
    se = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    return abs(after - before) / se if se > 0 else (float("inf") if after != before else 0.0)


def detect_adaptation(team: str, events: list[Event], home: str, upto: int, min_side: int = ADAPT_MIN_SIDE,
                      min_change: float = ADAPT_MIN_CHANGE, min_z: float = ADAPT_MIN_Z) -> tuple[Claim, Claim] | None:
    """Regime change in how long a team builds up (share of long balls in its own half). Returns (before, after).

    Uses only events up to minute `upto` (the claim ids carry it, so a half-time reading and a later one never
    overwrite each other). Scans every split point; a split counts only with >= min_side actions each side, a change
    >= min_change and a two-proportion z >= min_z. The scan inflates false alarms, hence the strict z (see the
    calibration above). The "after" claim's minute is the estimated change point, not the detection time."""
    events = [e for e in events if e.minute <= upto]
    actions = build_up_actions(team, events, home)
    flags = [f for _, f in actions]
    n = len(flags)
    prefix = [0.0]
    for f in flags:
        prefix.append(prefix[-1] + f)
    best = None
    for k in range(min_side, n - min_side + 1):
        before, after = prefix[k] / k, (prefix[n] - prefix[k]) / (n - k)
        z = _z(before, k, after, n - k)
        if abs(after - before) >= min_change and z >= min_z and (best is None or z > best[1]):
            best = (k, z, before, after)
    if best is None:
        return None
    k, _, before, after = best
    first_after = actions[k][0]
    label = "short to long" if after > before else "long to short"
    longs_before = [e.event_id for e, f in actions[:k] if f][-EVIDENCE_IDS:]
    longs_after = [e.event_id for e, f in actions[k:] if f == (1.0 if after > before else 0.0)][:EVIDENCE_IDS]
    metric = "build_up_long_share"
    b = Claim(claim_id=f"c_ad_{team}_{upto:02d}_before", type="observed_tendency", team=team, metric=metric,
              value=round(before, 3), n=k, minute=actions[0][0].minute, label="before the change",
              evidence=longs_before)
    a = Claim(claim_id=f"c_ad_{team}_{upto:02d}_after", type="observed_adaptation", team=team, metric=metric,
              value=round(after, 3), n=n - k, minute=first_after.minute, label=label, evidence=longs_after)
    return b, a
