"""Agent-XT-Reasoner tool definitions and dispatcher.

Adding a tool:
  1. Define the input schema as a Pydantic model
  2. register_tool(name, model) so the ToolInputGuard knows it
  3. Append a dict to TOOLS for Anthropic's tool_use API
  4. Implement the dispatch case below
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from safety import register_tool


# ───── Schemas ─────────────────────────────────────────────────────────────


class FactorBreakdownInput(BaseModel):
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    asof: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class CommodityContextInput(BaseModel):
    metal: str = Field(pattern=r"^(lithium|copper|gold|iron_ore|nickel|zinc|silver)$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    window_days: int = Field(default=30, ge=1, le=365)


class RegimeHistoryInput(BaseModel):
    asof: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    window_weeks: int = Field(default=52, ge=4, le=520)


class PeerComparisonInput(BaseModel):
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    top_n: int = Field(default=5, ge=1, le=10)


class HeuristicInput(BaseModel):
    situation_key: str = Field(min_length=2, max_length=80)


# Register so ToolInputGuard knows them.
register_tool("fetch_factor_breakdown", FactorBreakdownInput)
register_tool("fetch_commodity_context", CommodityContextInput)
register_tool("fetch_regime_history", RegimeHistoryInput)
register_tool("fetch_peer_comparison", PeerComparisonInput)
register_tool("fetch_heuristic", HeuristicInput)


# ───── Anthropic tool_use spec ────────────────────────────────────────────


TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_factor_breakdown",
        "description": "Return the 6-factor decomposition for a given ASX ticker on a given date.",
        "input_schema": FactorBreakdownInput.model_json_schema(),
    },
    {
        "name": "fetch_commodity_context",
        "description": "Return recent commodity price context plus material news events.",
        "input_schema": CommodityContextInput.model_json_schema(),
    },
    {
        "name": "fetch_regime_history",
        "description": "Return regime sequence over the recent window.",
        "input_schema": RegimeHistoryInput.model_json_schema(),
    },
    {
        "name": "fetch_peer_comparison",
        "description": "Return peer companies in the same metal / market-cap bucket.",
        "input_schema": PeerComparisonInput.model_json_schema(),
    },
    {
        "name": "fetch_heuristic",
        "description": "Recall a heuristic rule from Chen Xiatong's knowledge base.",
        "input_schema": HeuristicInput.model_json_schema(),
    },
]


# ───── Dispatch (Tier-1 calls go here) ────────────────────────────────────


def dispatch(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Stub implementations that return safe placeholders. Replace each `TODO` with
    a real Tier-1 call when the corresponding module is filled in by
    陈夏童 / 罗阳.
    """
    if tool_name == "fetch_factor_breakdown":
        # TODO: tier1.factor_engine.factor_attribution.get(args["ticker"], args["asof"])
        return {
            "ticker": args["ticker"],
            "asof": args["asof"],
            "technical_pct": 0.20,
            "volatility_pct": 0.15,
            "commodity_beta_pct": 0.30,
            "liquidity_pct": 0.10,
            "valuation_pct": 0.15,
            "fundamental_pct": 0.10,
            "_stub": True,
        }
    if tool_name == "fetch_commodity_context":
        return {
            "metal": args["metal"],
            "price_change_pct": -0.04,
            "events": ["TODO: wire to tier1.data_pipeline"],
            "_stub": True,
        }
    if tool_name == "fetch_regime_history":
        return {
            "asof": args["asof"],
            "regimes": [{"week": "2024-09-30", "regime": "Neutral"}],
            "_stub": True,
        }
    if tool_name == "fetch_peer_comparison":
        return {
            "ticker": args["ticker"],
            "peers": [],
            "_stub": True,
        }
    if tool_name == "fetch_heuristic":
        return {
            "situation_key": args["situation_key"],
            "rules": [],
            "_stub": True,
        }
    return {"error": f"unknown tool {tool_name!r}"}
