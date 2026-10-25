"""MockEngine: implements contracts.engine_api.EngineAPI from fixtures/match_bundle_fixture.json.

Lets person B build MCP tools, agents and UI before the real engine exists. All data is ILLUSTRATIVE.
Scope filtering is NOT done here (that is the MCP server's job); `true_matrix` does enforce "sealed first".
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from contracts import Claim, DuelBroadcast, Event, MatchBundle, Matrix, Option, Plan, Snapshot, Squad
from contracts.duel import OpponentOptionsEstimate, Regret, SealedChoice
from contracts.engine_api import NotSealedYet
from contracts.plan import OpponentPlanEstimate
from contracts.refs import MatchRef, ValidationResult

BUNDLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "match_bundle_fixture.json"


class MockEngine:
    def __init__(self, bundle_path: Path = BUNDLE_PATH):
        self._path = bundle_path
        self._sealed: set[str] = set()

    @cached_property
    def bundle(self) -> MatchBundle:
        return MatchBundle.model_validate(json.loads(self._path.read_text()))

    @cached_property
    def _claims(self) -> dict[str, Claim]:
        return {c.claim_id: c for c in self.bundle.claims}

    def _duel(self):
        if self.bundle.duel is None:
            raise LookupError("fixture has no duel")
        return self.bundle.duel

    # scouting
    def list_matches(self, team: str) -> list[MatchRef]:
        opp = self.bundle.meta.away if team == self.bundle.meta.home else self.bundle.meta.home
        return [MatchRef(match_id=f"s-fixture-{k:02d}", home=team, away=opp, score={team: 1, opp: 1})
                for k in range(1, 9)]

    def get_team_tendencies(self, team: str, aspect: str) -> list[Claim]:
        return [c for c in self.bundle.claims if c.type == "observed_tendency" and c.team == team]

    def get_player_profile(self, player_id: str) -> list[Claim]:
        return [c for c in self.bundle.claims if c.player_id == player_id]

    def get_set_piece_profile(self, team: str) -> list[Claim]:
        return [c for c in self.bundle.claims if c.team == team and c.claim_id.startswith("c_sp_")]

    # own squad
    def get_squad(self, team: str) -> Squad:
        return self.bundle.squads.teams[team]

    def get_squad_condition(self, match_id: str, team: str, minute: int) -> list[Claim]:
        snap = self.get_match_state(match_id, minute)
        return [Claim(claim_id=f"c_cond_{pid}_{minute}", type="observed_tendency", team=team, player_id=pid,
                      metric="condition_est", value=v, minute=minute, illustrative=True)
                for pid, v in snap.condition_est.items() if pid.startswith(f"{team}-")]

    # valuation and the duel
    def simulate_plan(self, plan: Plan, opponent_estimate: OpponentPlanEstimate, R: int) -> list[Claim]:
        cid = self.bundle.plans[plan.team].valuation
        return [self._claims[cid]] if cid else []

    def estimate_opponent_options(self, match_id: str, team: str) -> OpponentOptionsEstimate:
        return self._duel().private[team].opponent_estimate

    def price_matrix(self, match_id: str, own_options: list[Option], opponent_options: list[Option], R: int,
                     perspective: str, opponent_probs: list[float]) -> Matrix:
        return self._duel().private[perspective].believed_matrix

    def seal_choice(self, match_id: str, team: str, option_id: str, rule: str = "best_guess") -> SealedChoice:
        self._sealed.add(team)
        return self._duel().private[team].choice

    def true_matrix(self, match_id: str) -> DuelBroadcast:
        duel = self._duel()
        if self._sealed != set(duel.private):
            raise NotSealedYet("both benches must seal before the true matrix exists")
        return duel.broadcast

    def regret(self, match_id: str) -> dict[str, Regret]:
        return self.true_matrix(match_id).regret

    # validation (the real validator is agents/validators, H1)
    def validate_plan(self, plan: Plan) -> ValidationResult:
        return ValidationResult(ok=True)

    def validate_option(self, match_id: str, option: Option) -> ValidationResult:
        on_pitch = set(self.get_match_state(match_id, 45).on_pitch[option.team])
        errors = [f"{s.out} is not on the pitch" for s in option.subs if s.out not in on_pitch]
        return ValidationResult(ok=not errors, errors=errors)

    # live and evidence
    def get_plan_status(self, match_id: str, team: str, minute: int) -> list[Claim]:
        snap = self.get_match_state(match_id, minute)
        return [Claim(claim_id=f"c_kpi_{k.kpi_id}_{minute}", type="kpi_status", team=team, metric=k.kpi_id,
                      value=k.value, n=k.n, minute=minute, label=k.status, illustrative=True)
                for k in snap.kpis if k.team == team]

    def get_match_state(self, match_id: str, minute: int) -> Snapshot:
        return self.bundle.snapshots[max(0, min(minute, len(self.bundle.snapshots) - 1))]

    def get_events(self, match_id: str, filter: dict[str, Any]) -> list[Event]:
        evs = [e for e in self.bundle.events
               if all(getattr(e, k) == v for k, v in filter.items() if k not in ("limit", "from_t", "to_t"))
               and filter.get("from_t", 0) <= e.t <= filter.get("to_t", 1e9)]
        return evs[: filter.get("limit", len(evs))]

    def get_claim(self, claim_id: str) -> Claim:
        return self._claims[claim_id]
