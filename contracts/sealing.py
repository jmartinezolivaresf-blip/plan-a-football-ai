"""Commit-reveal sealing with SHA-256 over canonical JSON.

- Plans: hash of the plan JSON without its `sealed` field.
- Half-time choices: hash of {match_id, team, option_id, salt}. The salt prevents an opponent from
  brute-forcing a 3-option commit; it is published only at the reveal.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from .plan import Plan


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_digest(plan: Plan) -> str:
    payload = plan.model_dump(mode="json", by_alias=True, exclude={"sealed"})
    return sha256_hex(canonical_json(payload))


def verify_plan(plan: Plan) -> bool:
    return plan.sealed is not None and plan.sealed.sha256 == plan_digest(plan)


def new_salt() -> str:
    return secrets.token_hex(16)


def choice_digest(match_id: str, team: str, option_id: str, salt: str) -> str:
    payload = {"match_id": match_id, "team": team, "option_id": option_id, "salt": salt}
    return sha256_hex(canonical_json(payload))


def verify_choice(sha256: str, match_id: str, team: str, option_id: str, salt: str) -> bool:
    return sha256 == choice_digest(match_id, team, option_id, salt)
