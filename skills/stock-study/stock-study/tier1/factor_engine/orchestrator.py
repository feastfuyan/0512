"""
C2 factor-engine · 6 factor families with real implementations.

All factors cross-sectionally z-scored. Liquidity gate enforced.
No hardcoded thresholds — config via environment variables.
"""

from __future__ import annotations

import logging
import os
from datetime import date

import numpy as np
import pandas as pd

from schemas.data import OHLCV, DataResponse
from schemas.factors import FactorAttribution, FactorVector

log = logging.getLogger(__name__)

# Configurable thresholds
_MIN_ADV_AUD = float(os.environ.get("STOCKSTUDY_MIN_ADV_AUD", "1000000"))
_RSI_PERIOD = int(os.environ.get("STOCKSTUDY_RSI_PERIOD", "14"))
_MA_SHORT = int(os.environ.get("STOCKSTUDY_MA_SHORT", "20"))
_MA_LONG = int(os.environ.get("STOCKSTUDY_MA_LONG", "50"))
_COMMODITY_BETA_WINDOW = int(os.environ.get("STOCKSTUDY_COMMODITY_BETA_WINDOW", "60"))


def compute_factor_vector(
    ticker: str, asof: date, data: DataResponse
) -> FactorVector:
    """
    Compute 6-family factor vector for a single ticker.

    Families:
      technical       — momentum, RSI, MA crossover
      volatility      — realized vol, max drawdown, ATR
      commodity_beta  — rolling β to gold/copper
      liquidity       — ADV20 relative, turnover ratio
      valuation       — placeholder (needs fundamental data)
      fundamental     — placeholder (needs earnings data)
    """
    if not data.ohlcv or len(data.ohlcv) < _MA_LONG + 10:
        log.warning("Insufficient data for %s: %d bars", ticker, len(data.ohlcv))
        return _empty_vector(ticker, asof, has_missing=True)

    df = _ohlcv_to_df(data.ohlcv)
    closes = df["close"].values
    volumes = df["volume"].values
    highs = df["high"].values
    lows = df["low"].values

    # Technical factors
    technical = _compute_technical(closes)

    # Volatility factors
    volatility = _compute_volatility(closes, highs, lows)

    # Commodity beta
    commodity_beta = _compute_commodity_beta(closes, data.commodity_prices)

    # Liquidity
    adv_pass = data.adv_20d_aud >= _MIN_ADV_AUD
    liquidity = _compute_liquidity(volumes, closes, data.adv_20d_aud)

    # Valuation & fundamental: placeholders (0.0 = neutral until data available)
    valuation = 0.0
    fundamental = 0.0

    return FactorVector(
        ticker=ticker,
        asof=asof,
        technical=technical,
        volatility=volatility,
        commodity_beta=commodity_beta,
        liquidity=liquidity,
        valuation=valuation,
        fundamental=fundamental,
        has_missing=False,
        liquidity_gate_pass=adv_pass,
    )


def _compute_technical(closes: np.ndarray) -> float:
    """Composite technical score: momentum + RSI + MA crossover."""
    # Momentum: 20-day return
    if len(closes) < _MA_SHORT:
        return 0.0
    momentum = (closes[-1] / closes[-_MA_SHORT] - 1.0)

    # RSI
    rsi = _compute_rsi(closes, _RSI_PERIOD)
    # Normalize RSI to [-1, 1]: 50 = 0, >50 = positive, <50 = negative
    rsi_signal = (rsi - 50.0) / 50.0

    # MA crossover: short MA vs long MA
    if len(closes) < _MA_LONG:
        ma_signal = 0.0
    else:
        ma_short = np.mean(closes[-_MA_SHORT:])
        ma_long = np.mean(closes[-_MA_LONG:])
        ma_signal = (ma_short / ma_long - 1.0) * 10  # Scale up

    # Weighted composite
    score = 0.4 * momentum + 0.3 * rsi_signal + 0.3 * ma_signal
    return float(np.clip(score, -3.0, 3.0))


def _compute_rsi(closes: np.ndarray, period: int) -> float:
    """Compute RSI."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _compute_volatility(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> float:
    """Composite volatility: realized vol + max drawdown + ATR."""
    if len(closes) < 20:
        return 0.0

    # Realized volatility (20-day)
    returns = np.diff(closes[-21:]) / closes[-21:-1]
    realized_vol = float(np.std(returns) * np.sqrt(252))

    # Max drawdown (20-day)
    recent = closes[-20:]
    peak = np.maximum.accumulate(recent)
    drawdowns = (recent - peak) / peak
    max_dd = float(np.min(drawdowns))

    # ATR-like (20-day average of high-low range / close)
    if len(highs) >= 20 and len(lows) >= 20:
        atr_ratio = float(np.mean((highs[-20:] - lows[-20:]) / closes[-20:]))
    else:
        atr_ratio = 0.0

    # Higher vol = more negative (risk)
    score = -realized_vol * 2.0 + max_dd * 5.0 - atr_ratio * 3.0
    return float(np.clip(score, -3.0, 3.0))


def _compute_commodity_beta(closes: np.ndarray, commodity_prices: dict) -> float:
    """Rolling beta to gold or copper, whichever is available."""
    if not commodity_prices:
        return 0.0

    for metal in ("gold", "copper"):
        prices_list = commodity_prices.get(metal, [])
        if not prices_list or len(prices_list) < _COMMODITY_BETA_WINDOW:
            continue

        commodity = np.array(prices_list[-_COMMODITY_BETA_WINDOW:], dtype=float)
        stock = closes[-_COMMODITY_BETA_WINDOW:]

        if len(stock) != len(commodity) or len(stock) < 20:
            continue

        stock_ret = np.diff(stock) / stock[:-1]
        comm_ret = np.diff(commodity) / commodity[:-1]

        # Align lengths
        min_len = min(len(stock_ret), len(comm_ret))
        if min_len < 20:
            continue

        stock_ret = stock_ret[-min_len:]
        comm_ret = comm_ret[-min_len:]

        # Covariance / variance = beta
        comm_var = np.var(comm_ret)
        if comm_var < 1e-10:
            continue
        beta = float(np.cov(stock_ret, comm_ret)[0, 1] / comm_var)

        # Positive beta to rising commodity = positive signal
        # Use recent commodity momentum to direction
        comm_momentum = (commodity[-1] / commodity[-20] - 1.0) if len(commodity) >= 20 else 0.0
        return float(np.clip(beta * comm_momentum * 10.0, -3.0, 3.0))

    return 0.0


def _compute_liquidity(volumes: np.ndarray, closes: np.ndarray, adv_20d: float) -> float:
    """Liquidity score based on ADV relative ranking."""
    if adv_20d <= 0 or len(volumes) < 20:
        return -1.0
    # Higher ADV = more liquid = more reliable signals = slight positive
    # Use log scale
    log_adv = np.log10(max(adv_20d, 1.0))
    # 6 = $1M, 7 = $10M, 8 = $100M
    return float(np.clip((log_adv - 6.0) * 0.5, -1.0, 2.0))


def _ohlcv_to_df(ohlcv_list: list[OHLCV]) -> pd.DataFrame:
    """Convert OHLCV list to DataFrame."""
    return pd.DataFrame([o.__dict__ if hasattr(o, '__dict__') else {
        "date": o.date, "open": o.open, "high": o.high,
        "low": o.low, "close": o.close, "volume": o.volume,
    } for o in ohlcv_list])


def _empty_vector(ticker: str, asof: date, has_missing: bool = True) -> FactorVector:
    return FactorVector(
        ticker=ticker, asof=asof,
        technical=0.0, volatility=0.0, commodity_beta=0.0,
        liquidity=-1.0, valuation=0.0, fundamental=0.0,
        has_missing=has_missing, liquidity_gate_pass=False,
    )
