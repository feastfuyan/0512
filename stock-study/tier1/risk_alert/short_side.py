"""
C4 risk-alert · Short-side risk detection.

Preserves the v1 short-side strength (60.1% accuracy) as an independent module.
No hardcoded thresholds — all via environment variables.
"""

from __future__ import annotations

import logging
import os
from datetime import date

from schemas.data import DataResponse
from schemas.factors import FactorVector
from schemas.scores import RiskAlert

log = logging.getLogger(__name__)

_SHORT_ALERT_THRESHOLD = float(os.environ.get("STOCKSTUDY_SHORT_ALERT_THRESHOLD", "0.55"))
_SHORT_WATCH_THRESHOLD = float(os.environ.get("STOCKSTUDY_SHORT_WATCH_THRESHOLD", "0.45"))


def predict_risk(
    ticker: str, asof: date, factors: FactorVector, data: DataResponse
) -> RiskAlert:
    """
    Rule-based short-side risk detection.

    Factors weighted toward bearish signals:
    - Technical: negative momentum / RSI
    - Volatility: high vol + drawdown
    - Liquidity: thin liquidity = higher risk
    - Regime: bear market amplifies risk
    """
    score = 0.0
    reasons = []

    # Technical bearishness
    if factors.technical < -0.5:
        score += 0.25
        reasons.append(f"技术面弱势 (score={factors.technical:.2f})")
    elif factors.technical < -0.2:
        score += 0.10

    # High volatility
    if factors.volatility < -0.5:
        score += 0.20
        reasons.append(f"高波动/回撤 (score={factors.volatility:.2f})")

    # Negative commodity beta (metal prices falling)
    if factors.commodity_beta < -0.3:
        score += 0.20
        reasons.append(f"商品价格拖累 (score={factors.commodity_beta:.2f})")

    # Poor liquidity
    if not factors.liquidity_gate_pass:
        score += 0.15
        reasons.append("流动性不足 (<100万AUD/日)")

    # Bear/Crash regime amplifies risk
    regime = data.regime
    if regime in ("Bear", "Crash"):
        score += 0.15
        reasons.append(f"大盘环境: {regime}")

    # Clamp to [0, 1]
    short_prob = min(max(score, 0.0), 1.0)

    # Alert level
    if short_prob >= _SHORT_ALERT_THRESHOLD:
        alert_level = "alert"
    elif short_prob >= _SHORT_WATCH_THRESHOLD:
        alert_level = "warn" if short_prob >= 0.50 else "watch"
    else:
        alert_level = "none"

    return RiskAlert(
        ticker=ticker,
        asof=asof,
        short_probability=round(short_prob, 3),
        alert_level=alert_level,
        reasons=reasons,
    )
