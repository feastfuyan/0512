"""Agent-XT-Reasoner — narrative agent for daily run + ad-hoc."""

from __future__ import annotations

from typing import Any

from schemas.narratives import NarrativeResult, StockNarrative
from schemas.tasks import NarrativeTask
from tier2.base_agent import BaseAgent


class AgentXTReasoner(BaseAgent):
    agent_key = "agent_xt_reasoner"
    output_model = NarrativeResult
    default_model = "claude-sonnet-4-6"
    default_max_tokens = 4096
    default_temperature = 0.2

    @property
    def tools(self) -> list[dict[str, Any]]:
        from tier2.tools.xt_tools import TOOLS

        return TOOLS

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        from tier2.tools.xt_tools import dispatch

        return dispatch(tool_name, tool_input)

    def _mock_response(self, task: NarrativeTask) -> NarrativeResult:
        """Deterministic mock for smoke tests."""
        scores = task.scores[: task.top_n + task.bottom_n]
        tops, bottoms = [], []
        for s in scores[: task.top_n]:
            tops.append(
                StockNarrative(
                    ticker=s.ticker,
                    text=(
                        f"{s.ticker.split(':')[-1]} 评分 {s.p_up_calibrated:.2f}，"
                        f"主要由 {','.join(s.attribution.top_two)} 推动。"
                        f"短期趋势 {s.label}；建议观察。"
                    ),
                    factor_refs=s.attribution.top_two,
                    risk_caveats=["商品价格波动", "流动性风险"],
                    confidence="medium",
                )
            )
        for s in scores[task.top_n :]:
            bottoms.append(
                StockNarrative(
                    ticker=s.ticker,
                    text=(
                        f"{s.ticker.split(':')[-1]} 评分 {s.p_up_calibrated:.2f}，"
                        f"由 {','.join(s.attribution.top_two)} 主导负面。"
                        f"短期趋势 {s.label}；建议规避。"
                    ),
                    factor_refs=s.attribution.top_two,
                    risk_caveats=["反弹风险", "供给端不确定性"],
                    confidence="medium",
                )
            )
        return NarrativeResult(
            top_narratives=tops,
            bottom_narratives=bottoms,
            regime_commentary=f"当前 regime: {task.regime}。mock narrative for smoke test.",
            warnings=["mock_mode"],
        )
