"""OfflineRulesClient: a deterministic, rule-based stand-in for the LLM (CI, tests, demos without Azure).

It plugs into the same Agent Framework `Agent` as the Foundry client, reads the evidence block that the workflow
puts in the prompt and returns JSON for the requested response format. It is NOT a model; traces label it
`offline-rules` so nothing produced by it is presented as AI output.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Message

from .models import CandidateDraft, CandidateSetDraft, FindingDraft, LeverGuess, ScoutingDraft


class _NoFunctionWarning(logging.Filter):
    """The offline client never calls tools; hide Agent Framework's warning about it (and only that)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "does not support function invoking" not in record.getMessage()


logging.getLogger("agent_framework").addFilter(_NoFunctionWarning())

EVIDENCE = re.compile(r"<<<EVIDENCE\n(.*?)\nEVIDENCE>>>", re.DOTALL)
MODEL_NAME = "offline-rules"

METRIC_LABEL = {
    "losses_per_100_pressured_receptions": "{player} loses the ball under pressure",
    "goal_kick_short_share": "They play goal kicks short",
    "crosses_conceded_share": "They concede crosses down their {label}",
    "first_contact_conceded_share": "They lose the first contact at the {label} on corners",
    "high_turnovers_conceded_per_match": "They concede high turnovers",
    "central_entries_conceded_share": "They concede entries through the centre",
    "entries_conceded_share": "They concede entries down their {label}",
    "balls_in_behind_conceded_per_match": "They concede balls in behind",
    "late_xg_conceded_ratio": "They concede more chances late on",
}
DEFENSIVE_ROLES = ("LB", "RB", "CB", "DM")


def evidence(messages) -> dict[str, Any]:
    for m in reversed(messages):
        text = getattr(m, "text", None) or ""
        match = EVIDENCE.search(text)
        if match:
            return json.loads(match.group(1))
    raise ValueError("offline client: no evidence block in the prompt")


def _ratio(c: dict) -> float:
    ref = c.get("league_ref")
    v = c.get("value")
    if not isinstance(v, (int, float)) or not ref:
        return 1.0
    return float(v) / float(ref)


def scouting(ev: dict) -> ScoutingDraft:
    claims = [c for c in ev["claims"] if c["type"] == "observed_tendency"]
    ranked = sorted(claims, key=lambda c: -abs(_ratio(c) - 1.0))
    findings = []
    for c in ranked[:5]:
        cid = c["claim_id"]
        label = METRIC_LABEL.get(c["metric"], "Observed tendency")
        label = label.format(player=c.get("player_id") or "a player", label=c.get("label") or "side")
        small = c.get("status") != "sufficient" or (c.get("n") is not None and c["n"] < 15)
        hedge = ", which may be noise with limited evidence" if small else ""
        ref = f" against a league reference of {{{cid}.league_ref}}" if c.get("league_ref") is not None else ""
        findings.append(FindingDraft(claim_id=cid, headline=f"{label}: {{{cid}.value}}{ref} (n {{{cid}.n}}){hedge}."))
    by_metric = {c["metric"]: c for c in claims}
    gk = by_metric.get("goal_kick_short_share")
    guess = LeverGuess(build_up="short" if gk and _ratio(gk) > 1.15 else "mixed")
    return ScoutingDraft(findings=findings, opponent_levers=guess,
                         opponent_evidence=[gk["claim_id"]] if gk else [], opponent_confidence="low")


def _mirror(side: str | None) -> str | None:
    if not side:
        return None
    if "left" in side:
        return "right"
    if "right" in side:
        return "left"
    return None


def candidates(ev: dict) -> CandidateSetDraft:
    """Map the analyst's findings to levers; every non-default lever cites the claim that motivates it."""
    claims = {c["claim_id"]: c for c in ev["claims"]}
    findings = [claims[f["claim_id"]] for f in ev["report"]["findings"] if f["claim_id"] in claims]
    usable = [c for c in findings if c.get("status") == "sufficient"]
    lev: dict[str, Any] = {}
    evid: dict[str, list[str]] = {}
    for c in usable:
        r, cid, m = _ratio(c), c["claim_id"], c["metric"]
        role = (c.get("label") or "").split(",")[0]
        if m == "losses_per_100_pressured_receptions" and r >= 1.15 and c.get("player_id") and (
                not c.get("label") or role in DEFENSIVE_ROLES):
            lev.update(press_height="high", press_target=c["player_id"])
            evid.setdefault("press_height", []).append(cid)
            evid["press_target"] = [cid]
        elif m == "goal_kick_short_share" and r > 1.15:
            lev["press_height"] = "high"
            evid.setdefault("press_height", []).append(cid)
        elif m in ("crosses_conceded_share", "entries_conceded_share") and r > 1.15 and _mirror(c.get("label")) \
                and "attack_channel" not in lev:
            lev["attack_channel"] = _mirror(c.get("label"))
            evid["attack_channel"] = [cid]
        elif m == "central_entries_conceded_share" and r > 1.1:
            lev["attack_channel"] = "center"
            evid["attack_channel"] = [cid]
        elif m == "first_contact_conceded_share" and r > 1.15 and "back" in (c.get("label") or ""):
            lev["corner_delivery"] = "far_post"
            evid["corner_delivery"] = [cid]
        elif m == "balls_in_behind_conceded_per_match" and r > 1.2 and lev.get("press_height") != "high":
            lev["build_up"] = "direct"
            evid["build_up"] = [cid]
    if not lev:
        return CandidateSetDraft(candidates=[])  # nothing to exploit: the workflow falls back to its template
    out = [_candidate(lev, evid, "Exploit their weaknesses", "Explotar sus debilidades")]
    safe_keys = [k for k in ("attack_channel", "corner_delivery") if k in lev]
    if safe_keys and len(safe_keys) < len(lev):
        out.append(_candidate({k: lev[k] for k in safe_keys}, {k: evid[k] for k in safe_keys},
                              "Measured approach", "Enfoque prudente"))
    return CandidateSetDraft(candidates=out)


def _candidate(lev: dict, evid: dict, en: str, es: str) -> CandidateDraft:
    kpis = []
    if lev.get("press_height") == "high":
        kpis.append({"id": "k1", "metric": "high_turnovers", "target": ">=6", "by_minute": 45})
    ch = lev.get("attack_channel")
    if ch in ("left", "center", "right"):
        kpis.append({"id": "k2", "metric": "final_third_entries_share", "params": {"channel": ch},
                     "target": ">=0.40"})
    if lev.get("corner_delivery") == "far_post":
        kpis.append({"id": "k3", "metric": "set_piece_xg", "target": ">=0.30", "by_minute": 90})
    if not kpis:
        kpis.append({"id": "k4", "metric": "balls_in_behind_conceded", "target": "<=3", "by_minute": 90})
    plan_b = []
    first_kpi = kpis[0]["id"]
    if lev.get("press_height") == "high":
        plan_b.append({"if": {"kpi": "k1", "status": "failing", "after_minute": 30},
                       "then": {"levers": {"press_height": "mid"}}})
    if lev.get("build_up", "mixed") in ("short", "mixed"):
        # if the main KPI fails, stop building through the press and go direct
        plan_b.append({"if": {"kpi": first_kpi, "status": "failing", "after_minute": 25},
                       "then": {"levers": {"build_up": "direct"}}})
    else:
        plan_b.append({"if": {"score_diff": "<0", "after_minute": 60}, "then": {"levers": {"press_height": "high"}}})
    cites = [c for cs in evid.values() for c in cs]
    rationale = " ".join(f"Supported by [{c}]." for c in dict.fromkeys(cites))
    return CandidateDraft.model_validate({"name_en": en, "name_es": es, **lev, "lever_evidence": evid,
                                          "kpis": kpis, "plan_b": plan_b, "rationale": rationale})


def revise(ev: dict) -> CandidateSetDraft:
    """Drop every lever the validator complained about (back to default) and keep the rest."""
    errors = " ".join(ev.get("errors", []))
    out = []
    for cand in ev["candidates"]:
        c = dict(cand)
        for lever in ("press_height", "press_target", "build_up", "attack_channel", "corner_delivery"):
            if f"lever {lever}" in errors or (lever == "press_target" and "press_target" in errors):
                c.pop(lever, None)
                c.get("lever_evidence", {}).pop(lever, None)
        out.append(c)
    return CandidateSetDraft.model_validate({"candidates": out})


class OfflineRulesClient(BaseChatClient):
    """Deterministic rules behind the Agent Framework chat-client interface."""

    model_name = MODEL_NAME

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):  # type: ignore[override]
        fmt = (options or {}).get("response_format")
        ev = evidence(messages)
        if fmt is ScoutingDraft:
            out = scouting(ev)
        elif fmt is CandidateSetDraft and ev.get("errors"):
            out = revise(ev)
        elif fmt is CandidateSetDraft:
            out = candidates(ev)
        else:
            raise ValueError(f"offline client: unsupported response format {fmt}")
        text = out.model_dump_json()
        return ChatResponse(messages=[Message(role="assistant", contents=[text])], model=MODEL_NAME)
