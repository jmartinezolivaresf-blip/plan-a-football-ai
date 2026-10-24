"""Scope policy: what each caller may do. Pure Python (no MCP), so it is easy to test exhaustively.

Trust model (D-026): the scope is fixed by the trusted host when it creates a `ScopedTools` instance (one per
coaching staff, one for the broadcast desk). It is never read from a request header or a tool argument, so a
client cannot grant itself another scope. "Own team" tools have no `team` argument at all.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agents.validators.plan import validate_plan as validate_plan_rules
from contracts import BROADCAST_SCOPE, Option, Plan
from contracts.engine_api import EngineAPI, NotReady, NotSealedYet
from contracts.plan import OpponentPlanEstimate
from contracts.refs import ToolError

STAFF_TOOLS = frozenset({
    "list_matches", "get_team_tendencies", "get_player_profile", "get_set_piece_profile", "get_squad_condition",
    "simulate_plan", "estimate_opponent_options", "price_matrix", "validate_plan", "seal_choice", "get_plan_status",
    "get_events", "get_claim",
})
BROADCAST_TOOLS = frozenset({
    "list_matches", "get_team_tendencies", "get_player_profile", "get_set_piece_profile", "get_plan_status",
    "get_match_state", "get_events", "get_claim", "get_true_matrix",
})
# Claim types a coaching staff may read through get_claim. Matrix cells, regret and estimates of other benches are
# private or broadcast-only; a staff gets its own matrices from price_matrix and its estimate from its own tool.
STAFF_CLAIM_TYPES_ANY_TEAM = frozenset({"observed_tendency", "observed_adaptation", "observed_mechanism"})
STAFF_CLAIM_TYPES_OWN_TEAM = frozenset({"kpi_status", "sim_valuation", "opponent_estimate"})


def _dump(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True)
    return obj


def error(kind: str, detail: str = "") -> dict[str, Any]:
    return ToolError(error=kind, detail=detail).model_dump()


@dataclass
class CallRecord:
    tool: str
    args: dict[str, Any]
    claims: list[str]
    duration_ms: int
    status: str  # "ok" | "rejected"
    message: str | None = None


@dataclass
class ScopedTools:
    """All MCP tools, evaluated for one fixed scope.

    `visible_minute` is the latest match minute this caller may see in the current phase (0 before kick-off), so a
    staff preparing the match cannot read its future events.
    """

    engine: EngineAPI
    scope: str
    home: str
    away: str
    match_id: str
    visible_minute: int = 0
    calls: list[CallRecord] = field(default_factory=list)
    claims_served: set[str] = field(default_factory=set)

    @property
    def is_staff(self) -> bool:
        return self.scope != BROADCAST_SCOPE

    @property
    def opponent(self) -> str | None:
        if not self.is_staff:
            return None
        return self.away if self.scope == self.home else self.home

    @property
    def allowed(self) -> frozenset[str]:
        return STAFF_TOOLS if self.is_staff else BROADCAST_TOOLS

    # ------------------------------------------------------------------ dispatch
    def call(self, tool: str, args: dict[str, Any]) -> Any:
        t0 = time.perf_counter()
        if tool not in self.allowed:
            result = error("forbidden_scope", f"{tool} is not available to scope {self.scope}")
        else:
            try:
                result = getattr(self, f"_t_{tool}")(**args)
            except ValidationError as exc:
                result = error("invalid_args", str(exc.errors()[:3]))
            except TypeError as exc:
                result = error("invalid_args", str(exc))
            except (KeyError, LookupError, IndexError) as exc:
                result = error("not_found", str(exc))
            except NotReady as exc:
                result = error("not_ready", str(exc))
            except NotSealedYet as exc:
                result = error("not_sealed_yet", str(exc))
            except ValueError as exc:
                result = error("invalid_args", str(exc))
        claims = _claim_ids(result)
        status = "rejected" if isinstance(result, dict) and "error" in result else "ok"
        if status == "ok":
            self.claims_served |= set(claims)
        self.calls.append(CallRecord(tool=tool, args=args, claims=claims,
                                     duration_ms=int((time.perf_counter() - t0) * 1000), status=status,
                                     message=result.get("error") if status == "rejected" else None))
        return result

    # ------------------------------------------------------------------ scouting (any scope)
    def _t_list_matches(self, team: str) -> Any:
        return _dump(self.engine.list_matches(team))

    def _t_get_team_tendencies(self, team: str, aspect: str = "all") -> Any:
        return _dump(self.engine.get_team_tendencies(team, aspect))

    def _t_get_player_profile(self, player_id: str) -> Any:
        return _dump(self.engine.get_player_profile(player_id))

    def _t_get_set_piece_profile(self, team: str) -> Any:
        return _dump(self.engine.get_set_piece_profile(team))

    # ------------------------------------------------------------------ own team only (staff)
    def _t_get_squad_condition(self, minute: int = 0) -> Any:
        minute = min(minute, self.visible_minute)
        return {"squad": _dump(self.engine.get_squad(self.scope)),
                "condition": _dump(self.engine.get_squad_condition(self.match_id, self.scope, minute))}

    def _t_simulate_plan(self, plan: dict, opponent_estimate: dict, R: int = 500) -> Any:
        p = Plan.model_validate(plan)
        est = OpponentPlanEstimate.model_validate(opponent_estimate)
        if p.team != self.scope or est.estimator != self.scope or est.opponent != self.opponent:
            return error("forbidden_scope", "a staff can only value its own plan against its own estimate")
        return _dump(self.engine.simulate_plan(p, est, R))

    def _t_estimate_opponent_options(self) -> Any:
        return _dump(self.engine.estimate_opponent_options(self.match_id, self.scope))

    def _t_price_matrix(self, own_options: list[dict], opponent_options: list[dict], opponent_probs: list[float],
                        R: int = 300) -> Any:
        own = [Option.model_validate(o) for o in own_options]
        opp = [Option.model_validate(o) for o in opponent_options]
        if any(o.team != self.scope for o in own):
            return error("forbidden_scope", "own_options must belong to the caller")
        if any(o.team != self.opponent or not o.estimated for o in opp):
            return error("forbidden_scope", "opponent options must be the caller's own estimates")
        return _dump(self.engine.price_matrix(self.match_id, own, opp, R, self.scope, opponent_probs))

    def _t_validate_plan(self, plan: dict | None = None, option: dict | None = None) -> Any:
        if (plan is None) == (option is None):
            return error("invalid_args", "pass exactly one of plan or option")
        if plan is not None:
            p = Plan.model_validate(plan)
            if p.team != self.scope:
                return error("forbidden_scope", "a staff can only validate its own plan")
            squads = {t: self.engine.get_squad(t) for t in (self.home, self.away)}
            result = validate_plan_rules(p, squads, claims_known=self.claims_served)
            engine_result = self.engine.validate_plan(p)
            errors = result.errors + [e for e in engine_result.errors if e not in result.errors]
            return {"ok": not errors, "errors": errors}
        o = Option.model_validate(option)
        if o.team != self.scope:
            return error("forbidden_scope", "a staff can only validate its own option")
        return _dump(self.engine.validate_option(self.match_id, o))

    def _t_seal_choice(self, option_id: str, rule: str = "best_guess") -> Any:
        if rule not in ("safe_pick", "best_guess", "gamble"):
            return error("invalid_args", "rule must be safe_pick, best_guess or gamble")
        return _dump(self.engine.seal_choice(self.match_id, self.scope, option_id, rule))

    def _t_get_plan_status(self, minute: int, team: str | None = None) -> Any:
        if self.is_staff:
            if team not in (None, self.scope):
                return error("forbidden_scope", "a staff can only read its own plan status")
            team = self.scope
        elif team is None:
            return error("invalid_args", "broadcast must pass team")
        return _dump(self.engine.get_plan_status(self.match_id, team, min(minute, self.visible_minute)))

    # ------------------------------------------------------------------ match and evidence
    def _t_get_match_state(self, minute: int) -> Any:
        return _dump(self.engine.get_match_state(self.match_id, min(minute, self.visible_minute)))

    def _t_get_events(self, filter: dict | None = None) -> Any:
        flt = dict(filter or {})
        events = self.engine.get_events(self.match_id, flt)
        return _dump([e for e in events if e.minute <= self.visible_minute])

    def _t_get_claim(self, claim_id: str) -> Any:
        claim = self.engine.get_claim(claim_id)
        if self.is_staff:
            any_team = claim.type in STAFF_CLAIM_TYPES_ANY_TEAM
            own = claim.type in STAFF_CLAIM_TYPES_OWN_TEAM and claim.team == self.scope
            if not (any_team or own):
                return error("forbidden_scope", f"claim type {claim.type} is not readable by {self.scope}")
            if _claim_time(claim) > self.visible_minute:
                return error("forbidden_scope", "that claim is about a later minute of the match")
        return _dump(claim)

    def _t_get_true_matrix(self) -> Any:
        try:
            broadcast = self.engine.true_matrix(self.match_id)
        except NotSealedYet:
            return error("not_sealed_yet", "both benches must seal their choice first")
        return _dump(broadcast)


def _claim_time(claim) -> int:
    """The match minute a claim speaks for (-1 for season claims, always readable)."""
    parts = claim.claim_id.split("_")
    if claim.claim_id.startswith("c_ad_") and parts[3].isdigit():
        return int(parts[3])  # c_ad_<team>_<data cutoff>_<before|after>
    if claim.claim_id.startswith("c_obs_") and parts[-1].isdigit():
        return int(parts[-1])  # c_obs_<team>_<what>_<data cutoff>
    return claim.minute if claim.minute is not None else -1


def _claim_ids(result: Any) -> list[str]:
    """Every claim_id appearing in a tool result (claims, matrix cells, estimates)."""
    found: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            cid = x.get("claim_id")
            if isinstance(cid, str) and cid.startswith("c"):
                found.append(cid)
            for k, v in x.items():
                if k == "claims" and isinstance(v, list):
                    found.extend(c for c in v if isinstance(c, str))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(result)
    return list(dict.fromkeys(found))
