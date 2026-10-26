"""The spending cap for real model calls (agents/budget.py) and the statistics of the agent comparison (D-058)."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from agents import prematch as pm
from agents.budget import BudgetExceeded, Ledger, cost_eur
from agents.clients import ChatClients, model_choice
from eval import compare_agents as ca
from mcp_server.mock_engine import MockEngine

from .foundry_mock import MockResponses
from .test_foundry_contract import _env


def test_cost_uses_the_public_price_plus_a_margin():
    assert cost_eur(1_000_000, 0) == pytest.approx(0.44) and cost_eur(0, 1_000_000) == pytest.approx(1.54)


def test_the_ledger_refuses_a_turn_that_could_pass_the_cap(tmp_path):
    ledger = Ledger(path=tmp_path / "l.jsonl", cap_eur=0.05)
    ledger.check()  # empty ledger: one turn's reserve fits
    ledger.record(input_tokens=60_000, output_tokens=2_000, response_id="resp_1", tag="t")
    assert ledger.totals()["turns"] == 1 and ledger.totals()["cost_eur"] == pytest.approx(cost_eur(60_000, 2_000), 1e-3)
    with pytest.raises(BudgetExceeded, match="spending cap"):
        ledger.check()  # 0.029 spent + a 40k/3k reserve > 0.05
    with pytest.raises(BudgetExceeded, match="turn cap"):
        Ledger(path=tmp_path / "l.jsonl", cap_eur=100, max_turns=1).check()


def test_inactive_unless_configured(monkeypatch):
    monkeypatch.delenv("PLAN_A_LLM_BUDGET_EUR", raising=False)
    assert Ledger.from_env() is None  # the demo, CI and tests never spend through it


def _foundry(monkeypatch):
    from agent_framework_foundry import FoundryChatClient
    mock = MockResponses()
    monkeypatch.setattr(ChatClients, "_make", lambda self, role: FoundryChatClient(
        project_client=mock.project(), model=self.choice.analyst if role == "analyst" else self.choice.manager))
    _env(monkeypatch)
    return mock


def test_every_model_turn_is_recorded_and_the_cap_stops_before_the_call(monkeypatch, tmp_path):
    mock = _foundry(monkeypatch)
    monkeypatch.setenv("PLAN_A_LLM_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("PLAN_A_LLM_BUDGET_EUR", "10")
    asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", model_choice("foundry")))
    t = Ledger.from_env().totals()
    assert t["turns"] == 2 and t["input_tokens"] > 0  # analyst + manager, the tokens the service reported
    sent = len(mock.requests)
    monkeypatch.setenv("PLAN_A_LLM_BUDGET_EUR", "0.0001")
    with pytest.raises((BudgetExceeded, BaseExceptionGroup)) as stopped:  # the MCP task group wraps it
        asyncio.run(pm.run_staff(MockEngine(), "KES", "KES", "HAR", model_choice("foundry")))
    assert "BudgetExceeded: spending cap" in ca._describe(stopped.value)  # what the runner reads to stop
    assert len(mock.requests) == sent  # refused before anything was sent


def _rows(rules_hits, llm_hits):
    """E3-style rows: one unit per pair of plans, rules (offline) and model (foundry)."""
    rows = []
    for k, (a, b) in enumerate(zip(rules_hits, llm_hits, strict=True)):
        for mode, hits in (("offline", a), ("foundry", b)):
            rows.append({"unit": ["e3", 8101, k], "mode": mode, "rep": 1 if mode == "foundry" else 0,
                         "reports": [], "plans": [{"attacks_real": h, "random_baseline": 0.5, "cited_served": 0,
                                                    "changed_levers": 0, "used_template": False} for h in hits]})
    return rows


def test_the_comparison_is_paired_and_says_when_a_difference_is_not_significant():
    same = ca.summarize(_rows([(True, False)] * 6, [(True, False)] * 6))["official"]["E3_attacks_real_weakness"]
    assert same["diff"]["value"] == 0 and not same["significant"]
    better = ca.summarize(_rows([(False, False)] * 6, [(True, True)] * 6))["official"]["E3_attacks_real_weakness"]
    assert better["diff"]["value"] == 1 and better["significant"] and better["units"] == 6
    a, b = np.array([[1, 2], [0, 2]], float), np.array([[2, 2], [1, 2]], float)
    assert ca._boot(lambda x: x[:, 0].sum() / x[:, 1].sum(), a, b) == ca._boot(lambda x: x[:, 0].sum() / x[:, 1].sum(),
                                                                              a, b)  # seeded: reproducible
