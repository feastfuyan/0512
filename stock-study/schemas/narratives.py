"""Narrative outputs from Agent-XT-Reasoner."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StockNarrative(BaseModel):
    """One ticker's narrative entry."""

    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    text: str = Field(min_length=40, max_length=300)
    factor_refs: list[str] = Field(min_length=1, max_length=6)
    risk_caveats: list[str] = Field(min_length=1, max_length=5)
    confidence: Literal["low", "medium", "high"]


class NarrativeResult(BaseModel):
    """Bundled output from Agent-XT-Reasoner for a daily run."""

    model_config = ConfigDict(extra="forbid")
    top_narratives: list[StockNarrative] = Field(max_length=10)
    bottom_narratives: list[StockNarrative] = Field(max_length=10)
    regime_commentary: str = Field(max_length=400)
    warnings: list[str] = Field(default_factory=list)

    def all_tickers(self) -> list[str]:
        return [n.ticker for n in self.top_narratives + self.bottom_narratives]
