"""Unit tests for Pydantic v2 schemas — single source of truth (D3)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from schemas.compliance import ComplianceWarning, ComplianceWarningList
from schemas.data import OHLCV, ConsensusEst, DataResponse
from schemas.factors import FactorAttribution, FactorVector
from schemas.narratives import NarrativeResult, StockNarrative
from schemas.scores import RiskAlert, StockScore
from schemas.tasks import NarrativeTask


def test_ohlcv_valid():
    o = OHLCV(
        ticker="ASX:BHP",
        asof=date(2024, 9, 30),
        open=42.0,
        high=43.5,
        low=41.5,
        close=43.0,
        volume=1_000_000,
        adv_20d=42_000_000,
    )
    assert o.ticker == "ASX:BHP"


def test_ohlcv_rejects_bad_ticker():
    with pytest.raises(ValidationError):
        OHLCV(
            ticker="BHP",  # missing ASX: prefix
            asof=date(2024, 9, 30),
            open=42, high=43, low=41, close=42.5,
            volume=100, adv_20d=1.0,
        )


def test_ohlcv_rejects_negative_volume():
    with pytest.raises(ValidationError):
        OHLCV(
            ticker="ASX:BHP",
            asof=date(2024, 9, 30),
            open=42, high=43, low=41, close=42.5,
            volume=-100, adv_20d=1.0,
        )


def test_ohlcv_is_frozen():
    o = OHLCV(
        ticker="ASX:BHP", asof=date(2024, 9, 30),
        open=42, high=43, low=41, close=42.5,
        volume=100, adv_20d=1.0,
    )
    with pytest.raises(ValidationError):
        o.close = 99.0  # type: ignore[misc]


def test_factor_attribution_top_two():
    fa = FactorAttribution(
        technical_pct=0.40,
        volatility_pct=0.05,
        commodity_beta_pct=0.30,
        liquidity_pct=0.05,
        valuation_pct=0.10,
        fundamental_pct=0.10,
    )
    assert fa.top_two == ["technical", "commodity_beta"]


def test_stock_score_label_literal_enforced():
    fa = FactorAttribution(
        technical_pct=0.20, volatility_pct=0.20,
        commodity_beta_pct=0.20, liquidity_pct=0.10,
        valuation_pct=0.15, fundamental_pct=0.15,
    )
    with pytest.raises(ValidationError):
        StockScore(
            ticker="ASX:BHP", asof=date(2024, 9, 30),
            p_up_raw=0.6, p_up_calibrated=0.6,
            label="BUY",  # invalid — must be one of the 4 Chinese labels
            target_central=100, target_p20=90, target_p80=110,
            stop_loss=80, attribution=fa, regime="Bull",
            liquidity_gate_pass=True,
        )


def test_stock_narrative_min_factor_refs():
    with pytest.raises(ValidationError):
        StockNarrative(
            ticker="ASX:BHP",
            text="BHP up 3 percent driven by commodity beta this week reasonable.",
            factor_refs=[],  # min_length=1
            risk_caveats=["commodity volatility"],
            confidence="medium",
        )


def test_narrative_result_extra_forbidden():
    nr = NarrativeResult(
        top_narratives=[], bottom_narratives=[],
        regime_commentary="ok", warnings=[],
    )
    with pytest.raises(ValidationError):
        NarrativeResult.model_validate(
            {**nr.model_dump(), "extra_field": "boom"}
        )


def test_compliance_warning_list_recommendation_literal():
    cwl = ComplianceWarningList(
        warnings=[
            ComplianceWarning(
                severity="medium", field_path="text",
                issue="suggestive language", suggested_fix="rephrase",
            )
        ],
        overall_recommendation="publish_with_caveats",
    )
    assert cwl.overall_recommendation == "publish_with_caveats"


def test_narrative_task_requires_scores():
    fa = FactorAttribution(
        technical_pct=0.20, volatility_pct=0.20,
        commodity_beta_pct=0.20, liquidity_pct=0.10,
        valuation_pct=0.15, fundamental_pct=0.15,
    )
    s = StockScore(
        ticker="ASX:BHP", asof=date(2024, 9, 30),
        p_up_raw=0.6, p_up_calibrated=0.6, label="↑多头",
        target_central=100, target_p20=90, target_p80=110,
        stop_loss=80, attribution=fa, regime="Bull",
        liquidity_gate_pass=True,
    )
    task = NarrativeTask(
        asof=date(2024, 9, 30), regime="Bull",
        scores=[s], alerts=[], top_n=1, bottom_n=1,
    )
    assert len(task.scores) == 1

    with pytest.raises(ValidationError):
        NarrativeTask(
            asof=date(2024, 9, 30), regime="Bull",
            scores=[], alerts=[],  # min_length=1
        )
