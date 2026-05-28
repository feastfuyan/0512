"""
C1 data-pipeline · Yahoo Finance adapter.

Fetches OHLCV + commodity prices for ASX mining stocks.
All configuration via environment variables — no hardcoded secrets.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from schemas.data import OHLCV, DataResponse

log = logging.getLogger(__name__)

# Config from env with sensible defaults
_COMMODITY_MAP = {
    "gold": "GC=F",
    "copper": "HG=F",
    "iron_ore": None,  # No direct Yahoo ticker
    "lithium": None,  # No direct Yahoo ticker
}
_ASX_INDEX = "^AXJO"  # ASX 200
_MIN_ADV_AUD = float(os.environ.get("STOCKSTUDY_MIN_ADV_AUD", "1000000"))


class DataStaleWarning(Exception):
    """Raised when a ticker has no recent data (delisted/halted)."""
    pass


def fetch_ohlcv(ticker: str, asof: date, lookback_days: int = 504) -> list[OHLCV]:
    """
    Fetch OHLCV history for a single ASX ticker.

    Args:
        ticker: e.g. "ASX:BHP" — will be converted to "BHP.AX" for yfinance
        asof: reference date
        lookback_days: how far back to look (default ~2 years)
    """
    yf_ticker = _to_yf_ticker(ticker)
    end_date = asof + timedelta(days=1)
    start_date = asof - timedelta(days=lookback_days)

    try:
        hist = yf.Ticker(yf_ticker).history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
        )
    except Exception as e:
        log.warning("yfinance error for %s (%s): %s", ticker, yf_ticker, e)
        raise DataStaleWarning(f"Failed to fetch {ticker}: {e}") from e

    if hist.empty:
        raise DataStaleWarning(f"No data for {ticker} — possibly delisted")

    results = []
    for idx, row in hist.iterrows():
        results.append(OHLCV(
            date=idx.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        ))

    return results


def fetch_commodity_prices(asof: date, lookback_days: int = 252) -> dict[str, pd.Series]:
    """Fetch gold and copper price series for commodity beta calculation."""
    result = {}
    for name, yf_ticker in _COMMODITY_MAP.items():
        if yf_ticker is None:
            continue
        try:
            end_date = asof + timedelta(days=1)
            start_date = asof - timedelta(days=lookback_days)
            hist = yf.Ticker(yf_ticker).history(
                start=start_date.isoformat(), end=end_date.isoformat(), auto_adjust=True
            )
            if not hist.empty:
                result[name] = hist["Close"]
        except Exception as e:
            log.warning("Failed to fetch %s (%s): %s", name, yf_ticker, e)
    return result


def fetch_index(asof: date, lookback_days: int = 252) -> pd.Series:
    """Fetch ASX 200 index for regime detection."""
    end_date = asof + timedelta(days=1)
    start_date = asof - timedelta(days=lookback_days)
    try:
        hist = yf.Ticker(_ASX_INDEX).history(
            start=start_date.isoformat(), end=end_date.isoformat(), auto_adjust=True
        )
        if not hist.empty:
            return hist["Close"]
    except Exception as e:
        log.warning("Failed to fetch ASX200: %s", e)
    return pd.Series(dtype=float)


def compute_adv_20d(ohlcv_list: list[OHLCV]) -> float:
    """Average daily volume (AUD) over trailing 20 trading days."""
    if len(ohlcv_list) < 20:
        return 0.0
    recent = ohlcv_list[-20:]
    return sum(o.close * o.volume for o in recent) / 20.0


def detect_regime(index_prices: pd.Series) -> str:
    """
    Simple regime detection based on ASX 200 vs 50-day and 200-day MA.
    Returns: 'Bull', 'Neutral', 'Bear', or 'Crash'
    """
    if len(index_prices) < 200:
        return "Neutral"

    ma50 = index_prices.rolling(50).mean()
    ma200 = index_prices.rolling(200).mean()
    current = index_prices.iloc[-1]
    current_ma50 = ma50.iloc[-1]
    current_ma200 = ma200.iloc[-1]

    # Crash: price below both MAs and below 80% of MA200
    if current < current_ma50 and current < current_ma200 * 0.80:
        return "Crash"
    # Bear: price below both MAs
    if current < current_ma50 and current < current_ma200:
        return "Bear"
    # Bull: price above both MAs, MA50 > MA200
    if current > current_ma50 and current_ma50 > current_ma200:
        return "Bull"
    return "Neutral"


def _to_yf_ticker(ticker: str) -> str:
    """Convert 'ASX:BHP' → 'BHP.AX' for yfinance."""
    if ticker.startswith("ASX:"):
        return ticker[4:] + ".AX"
    if "." not in ticker:
        return ticker + ".AX"
    return ticker


def build_data_response(ticker: str, asof: date, lookback_days: int = 504) -> DataResponse:
    """Full data fetch for one ticker — OHLCV + ADV + commodity + regime."""
    ohlcv = fetch_ohlcv(ticker, asof, lookback_days)
    adv_20d = compute_adv_20d(ohlcv)
    commodity = fetch_commodity_prices(asof)
    index_prices = fetch_index(asof)
    regime = detect_regime(index_prices)

    return DataResponse(
        ticker=ticker,
        asof=asof,
        ohlcv=ohlcv,
        adv_20d_aud=adv_20d,
        commodity_prices={k: v.tolist() for k, v in commodity.items()},
        regime=regime,
    )
