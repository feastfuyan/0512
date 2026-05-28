"""BudgetGuard — D4 enforcement.

Two checkpoints around every LLM call:
  - precheck(agent_id):  before sending → may raise BudgetExceeded
  - postcheck(record):   after response → writes ledger + may toggle degrade mode

Caller is responsible for using these in the right order (BaseAgent does it).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from threading import Lock
from typing import Literal

log = logging.getLogger(__name__)

Scope = Literal["per_call", "per_run", "daily", "monthly"]


@dataclass(frozen=True)
class BudgetSpec:
    max_cost_usd_per_call: float = 0.50
    max_cost_usd_per_run: float = 2.00
    max_cost_usd_per_day: float = 5.00
    max_cost_usd_per_month: float = 120.00
    max_tokens_per_call: int = 16_384
    max_latency_ms_per_call: int = 30_000

    @classmethod
    def from_env(cls) -> BudgetSpec:
        return cls(
            max_cost_usd_per_call=float(os.environ.get("BUDGET_MAX_USD_PER_CALL", 0.50)),
            max_cost_usd_per_run=float(os.environ.get("BUDGET_MAX_USD_PER_RUN", 2.00)),
            max_cost_usd_per_day=float(os.environ.get("BUDGET_MAX_USD_PER_DAY", 5.00)),
            max_cost_usd_per_month=float(os.environ.get("BUDGET_MAX_USD_PER_MONTH", 120.00)),
        )


@dataclass
class CallRecord:
    agent_id: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    stop_reason: str
    trace_id: str = ""


class BudgetExceeded(Exception):
    def __init__(self, *, scope: Scope, spent: float, limit: float) -> None:
        self.scope = scope
        self.spent = spent
        self.limit = limit
        super().__init__(f"BudgetExceeded(scope={scope}, spent=${spent:.4f}, limit=${limit:.2f})")


class BudgetGuard:
    """Reads from CostLedger, raises if a check fails."""

    def __init__(self, spec: BudgetSpec | None = None, ledger: "object | None" = None) -> None:
        self.spec = spec or BudgetSpec.from_env()
        if ledger is None:
            from observability.cost_ledger import CostLedger

            ledger = CostLedger()
        self.ledger = ledger
        self._lock = Lock()
        self._degrade_mode = False

    @classmethod
    def from_env(cls, agent_id: str) -> BudgetGuard:  # noqa: ARG003
        return cls()

    @property
    def degrade_mode(self) -> bool:
        return self._degrade_mode

    def precheck(self, agent_id: str) -> None:
        with self._lock:
            month = self.ledger.month_spent_usd()
            if month >= self.spec.max_cost_usd_per_month:
                raise BudgetExceeded(
                    scope="monthly",
                    spent=month,
                    limit=self.spec.max_cost_usd_per_month,
                )
            day = self.ledger.day_spent_usd()
            if day >= self.spec.max_cost_usd_per_day:
                raise BudgetExceeded(
                    scope="daily",
                    spent=day,
                    limit=self.spec.max_cost_usd_per_day,
                )
            if month >= 0.80 * self.spec.max_cost_usd_per_month:
                if not self._degrade_mode:
                    log.warning(
                        "BudgetGuard: entering degrade mode (month spent=$%.2f, 80%% of limit)",
                        month,
                    )
                self._degrade_mode = True

    def postcheck(self, record: CallRecord) -> None:
        from observability.metrics import llm_cost_inc, llm_tokens_inc

        self.ledger.write(record)
        llm_cost_inc(agent_id=record.agent_id, model=record.model, cost_usd=record.cost_usd)
        llm_tokens_inc(
            agent_id=record.agent_id, model=record.model, kind="input", n=record.input_tokens
        )
        llm_tokens_inc(
            agent_id=record.agent_id, model=record.model, kind="output", n=record.output_tokens
        )
        if record.cost_usd > self.spec.max_cost_usd_per_call:
            log.warning(
                "BudgetGuard: per-call high cost agent=%s cost=$%.4f",
                record.agent_id,
                record.cost_usd,
            )
