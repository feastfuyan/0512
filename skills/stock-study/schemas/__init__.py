"""Pydantic v2 single source of truth for all cross-component contracts.

Every object passed between components MUST be defined here. No proto3, no
hand-rolled JSON schemas anywhere else (D3).
"""

from schemas.compliance import ComplianceWarning, ComplianceWarningList
from schemas.data import OHLCV, ConsensusEst, DataResponse
from schemas.factors import FactorAttribution, FactorVector
from schemas.narratives import NarrativeResult, StockNarrative
from schemas.publish import ExcelOutput, PublishArtifactModel
from schemas.scores import RiskAlert, StockScore
from schemas.tasks import NarrativeTask, SentinelTask

__all__ = [
    "OHLCV",
    "ConsensusEst",
    "DataResponse",
    "FactorVector",
    "FactorAttribution",
    "StockScore",
    "RiskAlert",
    "StockNarrative",
    "NarrativeResult",
    "ComplianceWarning",
    "ComplianceWarningList",
    "PublishArtifactModel",
    "ExcelOutput",
    "NarrativeTask",
    "SentinelTask",
]
