"""Tracing / metrics / budget cross-cutting concerns.

Module is import-safe even when the OTel collector and Prometheus pushgateway are
not running — all writes are best-effort.
"""

from observability.budget import BudgetExceeded, BudgetGuard, BudgetSpec, CallRecord
from observability.cost_ledger import CostLedger
from observability.metrics import (
    compliance_block_inc,
    llm_cost_inc,
    safety_block_inc,
)
from observability.tracing import trace_llm, tracer

__all__ = [
    "BudgetGuard",
    "BudgetSpec",
    "BudgetExceeded",
    "CallRecord",
    "CostLedger",
    "trace_llm",
    "tracer",
    "safety_block_inc",
    "compliance_block_inc",
    "llm_cost_inc",
]
