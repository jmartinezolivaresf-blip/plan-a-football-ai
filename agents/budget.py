"""A hard spending limit for real model calls, independent of Azure's budget alerts (D-058).

Active only when PLAN_A_LLM_BUDGET_EUR is set (evaluation runs); the demo, CI and tests never set it.

    PLAN_A_LLM_BUDGET_EUR=12 PLAN_A_LLM_LEDGER=eval/results/compare/ledger.jsonl ...

Every model turn appends one line to the ledger (a JSON-lines file shared by all worker processes, under a file lock)
with the tokens the service reported. Before a turn starts, the ledger total plus a reserve for that turn is priced;
if it would pass the cap, the turn is refused with BudgetExceeded, so the run stops with margin instead of finding out
from the bill. PLAN_A_LLM_MAX_TURNS caps the number of turns the same way.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

# Public Azure retail price, gpt-4.1-mini Global Standard, EUR per million tokens (prices.azure.com, Sweden Central,
# checked 2026-10-26: 0.0004 and 0.0014 per thousand), plus 10% so the estimate errs on the expensive side.
PRICE_IN_EUR_PER_M = 0.40 * 1.10
PRICE_OUT_EUR_PER_M = 1.40 * 1.10
RESERVE_IN, RESERVE_OUT = 40_000, 3_000  # the largest single turn seen in the real run was ~18k / 0.8k tokens


class BudgetExceeded(RuntimeError):
    """The next model turn could pass the spending cap (or the turn cap): stop the run."""


def cost_eur(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_IN_EUR_PER_M / 1e6 + output_tokens * PRICE_OUT_EUR_PER_M / 1e6


@dataclass
class Ledger:
    path: Path
    cap_eur: float
    max_turns: int | None = None

    @classmethod
    def from_env(cls) -> Ledger | None:
        cap = os.environ.get("PLAN_A_LLM_BUDGET_EUR", "").strip()
        if not cap:
            return None
        path = Path(os.environ.get("PLAN_A_LLM_LEDGER", "llm_ledger.jsonl"))
        turns = os.environ.get("PLAN_A_LLM_MAX_TURNS", "").strip()
        return cls(path=path, cap_eur=float(cap), max_turns=int(turns) if turns else None)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def totals(self) -> dict:
        rows = self._read()
        tin, tout = sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows)
        return {"turns": len(rows), "input_tokens": tin, "output_tokens": tout,
                "cost_eur": round(cost_eur(tin, tout), 4)}

    def _locked(self, write: dict | None = None) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if write is not None:
                    with open(self.path, "a") as f:
                        f.write(json.dumps(write) + "\n")
                return self.totals()
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def check(self) -> None:
        """Refuse the next turn if it could take the run past a cap."""
        t = self._locked()
        if self.max_turns is not None and t["turns"] >= self.max_turns:
            raise BudgetExceeded(f"turn cap reached: {t['turns']} of {self.max_turns}")
        worst = t["cost_eur"] + cost_eur(RESERVE_IN, RESERVE_OUT)
        if worst > self.cap_eur:
            raise BudgetExceeded(f"spending cap: {t['cost_eur']:.4f} EUR spent, the next turn could reach "
                                 f"{worst:.4f} EUR > cap {self.cap_eur} EUR")

    def record(self, *, input_tokens: int | None, output_tokens: int | None, response_id: str | None, tag: str) -> None:
        self._locked({"t": round(time.time(), 3), "tag": tag, "response_id": response_id,
                      "input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0)})
