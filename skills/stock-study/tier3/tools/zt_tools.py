"""Agent-ZT-Evolver tool definitions and dispatcher.

Skeleton only — TODO for 张涛 in S4.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from safety import register_tool


class HistoricalWindowInput(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    universe: list[str] = Field(min_length=1, max_length=500)


class HoneySimulationInput(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=80)
    n_replications: int = Field(default=100, ge=10, le=10000)


class CounterfactualInput(BaseModel):
    policy_a: str = Field(min_length=1, max_length=80)
    policy_b: str = Field(min_length=1, max_length=80)
    window_start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    window_end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ProposeChallengerInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    spec: dict = Field(default_factory=dict)


register_tool("fetch_historical_window", HistoricalWindowInput)
register_tool("run_honey_simulation", HoneySimulationInput)
register_tool("compute_counterfactual", CounterfactualInput)
register_tool("propose_challenger_factor", ProposeChallengerInput)


TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_historical_window",
        "description": "Fetch OHLCV + factor history for a window and universe.",
        "input_schema": HistoricalWindowInput.model_json_schema(),
    },
    {
        "name": "run_honey_simulation",
        "description": "Run Honey simulator on a scenario; returns SimResult.",
        "input_schema": HoneySimulationInput.model_json_schema(),
    },
    {
        "name": "compute_counterfactual",
        "description": "Compare two policies on a historical window.",
        "input_schema": CounterfactualInput.model_json_schema(),
    },
    {
        "name": "propose_challenger_factor",
        "description": "Write a challenger factor candidate to candidates/ for human review.",
        "input_schema": ProposeChallengerInput.model_json_schema(),
    },
]


def dispatch(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """All four return stubs for now. 张涛 wires real implementations in S4."""
    if tool_name == "fetch_historical_window":
        return {"_stub": True, "n_rows": 0}
    if tool_name == "run_honey_simulation":
        return {"_stub": True, "wasserstein_distance": 0.05, "passes_gate": True}
    if tool_name == "compute_counterfactual":
        return {"_stub": True, "ic_a": 0.05, "ic_b": 0.07, "delta": 0.02}
    if tool_name == "propose_challenger_factor":
        return {"_stub": True, "candidate_id": "fc-stub-001"}
    return {"error": f"unknown tool {tool_name!r}"}
