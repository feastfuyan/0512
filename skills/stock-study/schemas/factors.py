"""Factor outputs from Tier 1 factor-engine."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class FactorVector(BaseModel):
    """One ticker, one asof, all 6 factor-family values."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str = Field(pattern=r"^ASX:[A-Z0-9]{3,5}$")
    asof: date

    # 6 factor families — each cross-sectionally z-scored.
    technical: float
    volatility: float
    commodity_beta: float
    liquidity: float
    valuation: float
    fundamental: float

    # Health flags
    has_missing: bool = False
    liquidity_gate_pass: bool = True


class FactorAttribution(BaseModel):
    """Contribution of each factor to a stock's score."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    technical_pct: float = Field(ge=0, le=1)
    volatility_pct: float = Field(ge=0, le=1)
    commodity_beta_pct: float = Field(ge=0, le=1)
    liquidity_pct: float = Field(ge=0, le=1)
    valuation_pct: float = Field(ge=0, le=1)
    fundamental_pct: float = Field(ge=0, le=1)

    @property
    def top_two(self) -> list[str]:
        """Names of the two highest-contribution factors."""
        items = [
            ("technical", self.technical_pct),
            ("volatility", self.volatility_pct),
            ("commodity_beta", self.commodity_beta_pct),
            ("liquidity", self.liquidity_pct),
            ("valuation", self.valuation_pct),
            ("fundamental", self.fundamental_pct),
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in items[:2]]
