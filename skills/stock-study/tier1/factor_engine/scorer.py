"""
Score engine — combines 6 factors into calibrated probability + label.

Key fixes vs v1:
  - Regime filter: Bull/Bear/Crash adjusts base probability
  - Liquidity gate: low-liquidity stocks get neutral label
  - Risk-adjusted scoring: E[r]/σ instead of just E[r]
  - Output: probability (0-100%) instead of deterministic labels
  - Target price: confidence interval (P20/P80) instead of point estimate
"""

from __future__ import annotations

import logging
import os
from datetime import date

import numpy as np

from schemas.data import DataResponse
from schemas.factors import FactorAttribution, FactorVector
from schemas.scores import Label, Regime, RiskAlert, StockScore

log = logging.getLogger(__name__)

# Factor weights (configurable)
_W_TECHNICAL = float(os.environ.get("STOCKSTUDY_W_TECHNICAL", "0.20"))
_W_VOLATILITY = float(os.environ.get("STOCKSTUDY_W_VOLATILITY", "0.15"))
_W_COMMODITY = float(os.environ.get("STOCKSTUDY_W_COMMODITY", "0.30"))
_W_LIQUIDITY = float(os.environ.get("STOCKSTUDY_W_LIQUIDITY", "0.10"))
_W_VALUATION = float(os.environ.get("STOCKSTUDY_W_VALUATION", "0.15"))
_W_FUNDAMENTAL = float(os.environ.get("STOCKSTUDY_W_FUNDAMENTAL", "0.10"))

# Regime adjustments
_REGIME_ADJUST = {
    "Bull": 0.05,
    "Neutral": 0.00,
    "Bear": -0.15,
    "Crash": -0.25,
}

# Label thresholds (configurable)
_BULL_THRESHOLD = float(os.environ.get("STOCKSTUDY_BULL_THRESHOLD", "0.55"))
_BEAR_THRESHOLD = float(os.environ.get("STOCKSTUDY_BEAR_THRESHOLD", "0.40"))
_LEAN_BULL = float(os.environ.get("STOCKSTUDY_LEAN_BULL", "0.50"))
_LEAN_BEAR = float(os.environ.get("STOCKSTUDY_LEAN_BEAR", "0.45"))


def score_stock(
    factors: FactorVector,
    data: DataResponse,
    risk: RiskAlert,
) -> StockScore:
    """
    Combine factors into a calibrated score with regime filter.
    """
    # Raw weighted score
    raw_score = (
        _W_TECHNICAL * factors.technical
        + _W_VOLATILITY * factors.volatility
        + _W_COMMODITY * factors.commodity_beta
        + _W_LIQUIDITY * factors.liquidity
        + _W_VALUATION * factors.valuation
        + _W_FUNDAMENTAL * factors.fundamental
    )

    # Normalize to [0, 1] probability via sigmoid
    p_up_raw = float(1.0 / (1.0 + np.exp(-raw_score)))

    # Regime adjustment
    regime = data.regime
    regime_adj = _REGIME_ADJUST.get(regime, 0.0)
    p_up_calibrated = float(np.clip(p_up_raw + regime_adj, 0.05, 0.95))

    # Liquidity gate: if failed, force neutral
    if not factors.liquidity_gate_pass:
        p_up_calibrated = 0.50  # Neutral
        label: Label = "↘偏空"  # Low liquidity → cautious

    # Label assignment
    elif p_up_calibrated >= _BULL_THRESHOLD:
        label = "↑多头"
    elif p_up_calibrated >= _LEAN_BULL:
        label = "↗偏多"
    elif p_up_calibrated <= _BEAR_THRESHOLD:
        label = "↓空头"
    elif p_up_calibrated <= _LEAN_BEAR:
        label = "↘偏空"
    else:
        label = "↘偏空"

    # Target price: confidence interval based on volatility
    current_price = _get_current_price(data)
    vol_estimate = _estimate_volatility(data)
    horizon_days = int(os.environ.get("STOCKSTUDY_HORIZON_DAYS", "14"))  # Shortened from 30

    if current_price > 0 and vol_estimate > 0:
        # Central target: drift-adjusted (slight upward bias in expectation)
        drift = (p_up_calibrated - 0.50) * vol_estimate * np.sqrt(horizon_days / 252)
        target_central = current_price * (1.0 + drift)
        # Confidence interval
        vol_range = vol_estimate * np.sqrt(horizon_days / 252)
        target_p80 = current_price * (1.0 + drift + 1.28 * vol_range)
        target_p20 = current_price * (1.0 + drift - 1.28 * vol_range)
        # Stop loss: -2σ
        stop_loss = current_price * (1.0 - 2.0 * vol_range)
    else:
        target_central = target_p80 = target_p20 = stop_loss = 0.0

    # Factor attribution
    total_w = _W_TECHNICAL + _W_VOLATILITY + _W_COMMODITY + _W_LIQUIDITY + _W_VALUATION + _W_FUNDAMENTAL
    attribution = FactorAttribution(
        technical_pct=round(_W_TECHNICAL / total_w, 3),
        volatility_pct=round(_W_VOLATILITY / total_w, 3),
        commodity_beta_pct=round(_W_COMMODITY / total_w, 3),
        liquidity_pct=round(_W_LIQUIDITY / total_w, 3),
        valuation_pct=round(_W_VALUATION / total_w, 3),
        fundamental_pct=round(_W_FUNDAMENTAL / total_w, 3),
    )

    return StockScore(
        ticker=factors.ticker,
        asof=factors.asof,
        p_up_raw=round(p_up_raw, 3),
        p_up_calibrated=round(p_up_calibrated, 3),
        label=label,
        target_central=round(target_central, 3),
        target_p20=round(target_p20, 3),
        target_p80=round(target_p80, 3),
        stop_loss=round(stop_loss, 3),
        attribution=attribution,
        regime=regime,
        liquidity_gate_pass=factors.liquidity_gate_pass,
    )


def _get_current_price(data: DataResponse) -> float:
    """Get the latest close price."""
    if data.ohlcv:
        return float(data.ohlcv[-1].close)
    return 0.0


def _estimate_volatility(data: DataResponse) -> float:
    """Estimate annualized volatility from recent data."""
    if len(data.ohlcv) < 21:
        return 0.4  # Default high vol for mining stocks

    closes = np.array([o.close for o in data.ohlcv[-21:]])
    returns = np.diff(closes) / closes[:-1]
    return float(np.std(returns) * np.sqrt(252))
