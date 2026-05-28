"""Task envelopes — inputs that flow INTO Agents."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.scores import RiskAlert, StockScore


class NarrativeTask(BaseModel):
    """Input envelope for Agent-XT-Reasoner.invoke()."""

    model_config = ConfigDict(extra="forbid")
    asof: date
    regime: Literal["Bull", "Neutral", "Bear", "Crash"]
    scores: list[StockScore] = Field(min_length=1)
    alerts: list[RiskAlert] = Field(default_factory=list)
    top_n: int = Field(default=10, ge=1, le=20)
    bottom_n: int = Field(default=10, ge=1, le=20)
    language: Literal["zh", "en"] = "zh"


class SentinelTask(BaseModel):
    """Input envelope for Compliance-Sentinel.advise()."""

    model_config = ConfigDict(extra="forbid")
    artifact_id: str
    text_to_check: str = Field(min_length=10, max_length=20000)
    tickers: list[str] = Field(default_factory=list)
