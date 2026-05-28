"""Agent-ZT-Evolver — monthly meta-strategy agent (T3).

Skeleton only. Full implementation in S4. Owner: 张涛.

Key constraints (see ADR-0005 + prompts/agent_zt_evolver/v1.0.0.md):
  - Opus 4.7 (most expensive model; monthly = low frequency justifies it)
  - Hard $20 budget per monthly run
  - Cannot promote challenger without human sign-off (D10)
  - Skips RL loop if Honey sim-to-real Wasserstein > 0.1 (IP-5)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tier2.base_agent import BaseAgent


@dataclass
class EvolveResult:
    status: str  # "completed" | "aborted" | "degraded"
    reason: str = ""
    candidates: list[dict] = None  # type: ignore[assignment]
    meta_insights: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = []
        if self.meta_insights is None:
            self.meta_insights = []


# Note: AgentZTEvolver is fully wired in S4 — for S0/S1 we only need the skeleton
# so that workflows/monthly_evolve.py imports do not break.

class AgentZTEvolver(BaseAgent):  # pragma: no cover — skeleton
    agent_key = "agent_zt_evolver"
    default_model = "claude-opus-4-7"
    default_max_tokens = 8192
    default_temperature = 0.3

    @property
    def tools(self) -> list[dict[str, Any]]:
        from tier3.tools.zt_tools import TOOLS

        return TOOLS

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        from tier3.tools.zt_tools import dispatch

        return dispatch(tool_name, tool_input)

    def _mock_response(self, task):  # type: ignore[no-untyped-def]
        # Mock returns "no candidate proposed this month" — a perfectly valid outcome
        return EvolveResult(status="completed", candidates=[], meta_insights=["mock_mode"])
