"""Public contracts shared by sim, engine, MCP server, agents and web.

Pydantic models are the source of truth; JSON Schemas in contracts/schemas/ are exported from them
(`make schemas`). Evaluator-only models live in contracts.eval_only and are deliberately NOT exported here.
"""

from .bundle import SCHEMA_VERSION, AttackDirection, FindingRef, MatchBundle, MatchMeta, RenderFrame, ScoutingSummary
from .claim import Claim
from .common import BROADCAST_SCOPE, I18nText, zone_index
from .cue import Cue
from .duel import (
    Duel,
    DuelBroadcast,
    EstimatedOption,
    OpponentOptionsEstimate,
    Regret,
    RevealedChoice,
    SealedChoice,
    TeamDuelPrivate,
)
from .events import Event
from .matrix import Cell, Matrix, MatrixReading
from .option import Option
from .plan import Kpi, LeverChanges, Levers, Plan, PlanBAction, PlanBCondition, PlanBRule, Seal, Sub
from .snapshot import KpiStatus, Snapshot
from .squads import Attributes, Player, Squad, Squads
from .trace import TraceStep

# Contract name -> model, used to export one JSON Schema per contract.
PUBLIC_CONTRACTS = {
    "events": Event,
    "snapshot": Snapshot,
    "squads": Squads,
    "plan": Plan,
    "option": Option,
    "claim": Claim,
    "matrix": Matrix,
    "cue": Cue,
    "trace": TraceStep,
    "duel": Duel,
    "match_bundle": MatchBundle,
}

__all__ = [
    "BROADCAST_SCOPE", "PUBLIC_CONTRACTS", "SCHEMA_VERSION", "AttackDirection", "Attributes", "Cell", "Claim",
    "FindingRef", "ScoutingSummary", "Cue", "Duel", "DuelBroadcast", "EstimatedOption", "Event", "I18nText", "Kpi",
    "KpiStatus", "LeverChanges",
    "Levers", "MatchBundle", "MatchMeta", "Matrix", "MatrixReading", "OpponentOptionsEstimate", "Option", "Plan",
    "PlanBAction", "PlanBCondition", "PlanBRule", "Player", "Regret", "RenderFrame", "RevealedChoice", "Seal",
    "SealedChoice", "Snapshot", "Squad", "Squads", "Sub", "TeamDuelPrivate", "TraceStep", "zone_index",
]
