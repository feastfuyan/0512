"""CostLedger — persists every LLM call to PostgreSQL agent_calls table.

Falls back to in-memory if no DSN is set (useful for tests & local smoke).
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class CostLedger:
    """Thread-safe in-memory ring buffer + optional PG persistence."""

    def __init__(self, dsn: str | None = None, ring_size: int = 10_000) -> None:
        self.dsn = dsn or os.environ.get("POSTGRES_DSN")
        self._ring: deque = deque(maxlen=ring_size)
        self._lock = threading.Lock()
        self._engine = None
        if self.dsn:
            try:
                from sqlalchemy import create_engine

                self._engine = create_engine(self.dsn, pool_pre_ping=True)
            except Exception as e:  # pragma: no cover
                log.warning("CostLedger: PG connect failed (%s); using in-memory only", e)
                self._engine = None

    def write(self, record) -> None:
        # mypy: record is observability.budget.CallRecord
        d = asdict(record)
        d["created_at"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._ring.append(d)
        if self._engine is not None:
            try:
                from sqlalchemy import text

                with self._engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO agent_calls
                              (agent_id, model, prompt_version, input_tokens,
                               output_tokens, cost_usd, duration_ms, stop_reason,
                               trace_id, created_at)
                            VALUES
                              (:agent_id, :model, :prompt_version, :input_tokens,
                               :output_tokens, :cost_usd, :duration_ms, :stop_reason,
                               :trace_id, :created_at)
                            """
                        ),
                        d,
                    )
            except Exception as e:  # pragma: no cover
                log.warning("CostLedger PG write failed: %s", e)

    def _today_records(self) -> list[dict]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            return [r for r in self._ring if r["created_at"].startswith(today)]

    def _month_records(self) -> list[dict]:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._lock:
            return [r for r in self._ring if r["created_at"].startswith(month)]

    def day_spent_usd(self) -> float:
        return sum(r["cost_usd"] for r in self._today_records())

    def month_spent_usd(self) -> float:
        return sum(r["cost_usd"] for r in self._month_records())

    def report_month(self) -> dict:
        rows = self._month_records()
        total = sum(r["cost_usd"] for r in rows)
        by_agent: dict[str, float] = {}
        for r in rows:
            by_agent[r["agent_id"]] = by_agent.get(r["agent_id"], 0) + r["cost_usd"]
        return {
            "total_usd": total,
            "by_agent": by_agent,
            "call_count": len(rows),
        }


def _cli_main() -> None:
    """`python -m observability.cost_ledger --report month`"""
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--report", choices=["month", "day"], default="month")
    args = parser.parse_args()
    ledger = CostLedger()
    if args.report == "month":
        print(json.dumps(ledger.report_month(), indent=2))
    else:
        print(json.dumps({"day_usd": ledger.day_spent_usd()}, indent=2))


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
