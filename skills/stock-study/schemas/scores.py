"""Score & risk-alert outputs."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.factors import FactorAttribution

Label = Literal["↑多头", "↗偏多", "↘偏空", "↓空头"]
Regime = Literal["Bull", "Neutral", "Bear", "Crash"]


class StockScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    asof: date

    p_up_raw: float = Field(ge=0, le=1)
    p_up_calibrated: float = Field(ge=0, le=1)
    label: Label

    target_central: float = Field(gt=0)
    target_p20: float = Field(gt=0)
    target_p80: float = Field(gt=0)
    stop_loss: float = Field(gt=0)

    attribution: FactorAttribution
    regime: Regime
    liquidity_gate_pass: bool


class RiskAlert(BaseModel):
    """Short-side alert from C4 risk-alert sklearn model."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    asof: date
    short_probability: float = Field(ge=0, le=1)
    alert_level: Literal["none", "watch", "warn", "alert"]
    reasons: list[str] = Field(default_factory=list)
