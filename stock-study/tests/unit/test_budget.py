"""Unit tests for observability.budget."""

from __future__ import annotations

import pytest

from observability.budget import BudgetExceeded, BudgetGuard, BudgetSpec, CallRecord
from observability.cost_ledger import CostLedger


@pytest.fixture()
def fresh_ledger():
    """Fresh in-memory ledger (no PG)."""
    return CostLedger(dsn="")  # empty DSN → memory only


@pytest.fixture()
def tight_spec():
    """Tiny limits so we can trip them in unit tests."""
    return BudgetSpec(
        max_cost_usd_per_call=0.10,
        max_cost_usd_per_run=0.20,
        max_cost_usd_per_day=0.50,
        max_cost_usd_per_month=1.00,
    )


def _record(cost: float, agent_id: str = "AGT-XT-R") -> CallRecord:
    return CallRecord(
        agent_id=agent_id, model="claude-sonnet-4-6", prompt_version="v1.0.0",
        input_tokens=1000, output_tokens=200, cost_usd=cost,
        duration_ms=500, stop_reason="end_turn",
    )


def test_precheck_passes_when_under_budget(fresh_ledger, tight_spec):
    guard = BudgetGuard(spec=tight_spec, ledger=fresh_ledger)
    guard.precheck("AGT-XT-R")  # should not raise


def test_postcheck_writes_ledger(fresh_ledger, tight_spec):
    guard = BudgetGuard(spec=tight_spec, ledger=fresh_ledger)
    guard.postcheck(_record(0.05))
    assert fresh_ledger.day_spent_usd() == pytest.approx(0.05)


def test_daily_limit_raises(fresh_ledger):
    """Daily limit fires before monthly limit when daily limit is tighter."""
    spec = BudgetSpec(
        max_cost_usd_per_call=10,
        max_cost_usd_per_run=10,
        max_cost_usd_per_day=0.50,
        max_cost_usd_per_month=99.00,  # monthly intentionally loose
    )
    guard = BudgetGuard(spec=spec, ledger=fresh_ledger)
    # 6 × 0.10 = 0.60 > daily 0.50, but well under monthly 99
    for _ in range(6):
        guard.postcheck(_record(0.10))
    with pytest.raises(BudgetExceeded) as exc:
        guard.precheck("AGT-XT-R")
    assert exc.value.scope == "daily"


def test_monthly_limit_raises_before_daily(fresh_ledger):
    spec = BudgetSpec(
        max_cost_usd_per_call=10,
        max_cost_usd_per_run=10,
        max_cost_usd_per_day=999,
        max_cost_usd_per_month=0.50,
    )
    guard = BudgetGuard(spec=spec, ledger=fresh_ledger)
    guard.postcheck(_record(0.60))  # blows past monthly even though daily allows
    with pytest.raises(BudgetExceeded) as exc:
        guard.precheck("AGT-XT-R")
    assert exc.value.scope == "monthly"


def test_degrade_mode_triggers_at_80pct(fresh_ledger):
    spec = BudgetSpec(
        max_cost_usd_per_call=10,
        max_cost_usd_per_run=10,
        max_cost_usd_per_day=999,
        max_cost_usd_per_month=1.00,
    )
    guard = BudgetGuard(spec=spec, ledger=fresh_ledger)
    assert guard.degrade_mode is False
    # 0.85 of 1.00 → over 80% threshold
    guard.postcheck(_record(0.85))
    guard.precheck("AGT-XT-R")
    assert guard.degrade_mode is True


def test_ledger_month_report(fresh_ledger):
    fresh_ledger.write(_record(0.05, "AGT-XT-R"))
    fresh_ledger.write(_record(0.10, "AGT-CSentinel"))
    fresh_ledger.write(_record(0.15, "AGT-XT-R"))
    r = fresh_ledger.report_month()
    assert r["total_usd"] == pytest.approx(0.30)
    assert r["by_agent"]["AGT-XT-R"] == pytest.approx(0.20)
    assert r["call_count"] == 3
