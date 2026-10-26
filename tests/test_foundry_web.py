"""The web's "Real Microsoft Foundry Run" data (web/public/foundry_run.json) is the recorded run, nothing else.

It must be exactly what pipeline/foundry_web.py derives from the recorded evidence and the frozen demo bundle; its
numbers must add up; the demo decisions it shows must be the bundle's; and it must not publish anything sensitive."""

from __future__ import annotations

import hashlib
import json
import re

from pipeline import foundry_web as fw

DATA = fw.OUT


def _data() -> dict:
    return json.loads(DATA.read_text())


def test_the_published_file_is_derived_from_the_recorded_evidence():
    assert _data() == fw.render()  # regenerate with `python -m pipeline.foundry_web` after a new run
    assert _data()["sources"]["evidence_sha256"] == hashlib.sha256(fw.EVIDENCE.read_bytes()).hexdigest()


def test_every_turn_is_a_real_service_answer_and_the_totals_add_up():
    d, evidence = _data(), json.loads(fw.EVIDENCE.read_text())
    turns, t = d["turns"], d["totals"]
    assert d["run"]["mode"] == "foundry" and d["run"]["model"] == ["gpt-4.1-mini"]
    assert len(turns) == t["model_turns"] == t["with_service_response_id"] == evidence["summary"]["model_turns"]
    assert all(x["response_id"] and x["response_id"].startswith("resp_") and x["service_model"] for x in turns)
    assert sum(x["input_tokens"] for x in turns) == t["input_tokens"] == evidence["summary"]["input_tokens"]
    assert sum(x["output_tokens"] for x in turns) == t["output_tokens"] == evidence["summary"]["output_tokens"]
    tools = [name for x in turns for name in x["tools"]]
    assert len(tools) == t["tool_calls_by_model"] and {n: tools.count(n) for n in set(tools)} == t["tools_by_model"]


def test_the_demo_side_is_the_frozen_bundle_and_the_half_time_was_the_same():
    d = _data()
    bundle = json.loads(fw.BUNDLE.read_text())
    assert d["run"]["demo_bundle_sha256"] == hashlib.sha256(fw.BUNDLE.read_bytes()).hexdigest()  # "unchanged ✓"
    assert d["run"]["demo_bundle_unchanged"] and all(d["halftime"]["same_as_demo"].values())
    labels = {o["option_id"]: o["label"]["en"] for p in bundle["duel"]["private"].values() for o in p["options"]}
    for club, rg in bundle["duel"]["broadcast"]["regret"].items():
        demo = d["halftime"]["benches"][club]["demo"]
        assert (demo["choice"], demo["regret_xpts"]) == (labels[rg["chosen"]], rg["regret_xpts"])


def test_every_guardrail_event_says_what_was_rejected_and_how_it_ended():
    for g in _data()["guardrails"]:
        assert g["rejections"] and all(r["plain"] != "broke a validation rule" for r in g["rejections"])
        assert re.match(r"(fixed|accepted) on attempt \d|still invalid after \d attempts: discarded", g["outcome"])


def test_nothing_sensitive_is_published():
    text = DATA.read_text()
    guid = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
    assert not guid.search(text)  # no tenant or subscription ids
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)  # no e-mail addresses
    for bad in ("plan-a-foundry", "Bearer", "api-key", "apiKey", "AccountKey", "eyJ0", "FOUNDRY_", "PLAN_A_"):
        assert bad not in text, bad
    hosts = set(re.findall(r"[\w*.-]+\.azure\.com", text))
    assert hosts <= {"*.services.ai.azure.com"}, hosts
    allowed = {"schema", "sources", "run", "totals", "turns", "guardrails", "plans", "halftime", "comparison"}
    assert set(_data()) == allowed
