"""Data-layer schemas. Output of Tier 1 data-pipeline."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class OHLCV(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    date: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class ConsensusEst(BaseModel):
    """Sell-side consensus snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str
    asof: date
    target_mean: float | None = None
    target_count: int = 0
    rating_buy: int = 0
    rating_hold: int = 0
    rating_sell: int = 0


class DataResponse(BaseModel):
    """Bundled output of data-pipeline for one (ticker, asof)."""

    model_config = ConfigDict(extra="forbid")  # Not frozen — we mutate in pipeline
    ticker: str
    asof: date
    ohlcv: list[OHLCV] = Field(default_factory=list)
    adv_20d_aud: float = 0.0
    commodity_prices: dict[str, list] = Field(default_factory=dict)
    regime: str = "Neutral"
    consensus: ConsensusEst | None = None
    is_delisted: bool = False
    is_in_trading_halt: bool = False
    stale_warnings: list[str] = Field(default_factory=list)
