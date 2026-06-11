"""Compliance-Sentinel — advisory LLM check on outbound text."""

from __future__ import annotations

from typing import Any

from schemas.compliance import ComplianceWarningList
from schemas.tasks import SentinelTask
from tier2.base_agent import BaseAgent


class ComplianceSentinel(BaseAgent):
    agent_key = "compliance_sentinel"
    output_model = ComplianceWarningList
    default_model = "claude-sonnet-4-6"
    default_max_tokens = 2048
    default_temperature = 0.0  # we want consistent, deterministic-ish judgements

    @property
    def tools(self) -> list[dict[str, Any]]:
        return []  # no tools — Sentinel only reads the input text

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        return {"error": "Sentinel has no tools"}

    def _mock_response(self, task: SentinelTask) -> ComplianceWarningList:
        return ComplianceWarningList(
            warnings=[], overall_recommendation="publish"
        )

    def advise(self, text: str, *, artifact_id: str = "test", tickers: list[str] | None = None) -> ComplianceWarningList:
        """High-level convenience wrapper for callers who don't want to construct SentinelTask."""
        task = SentinelTask(
            artifact_id=artifact_id,
            text_to_check=text,
            tickers=tickers or [],
        )
        return self.invoke(task)
