"""Publish-layer schemas (artifacts that go out of the system)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.narratives import NarrativeResult
from schemas.scores import RiskAlert, StockScore


class ExcelOutput(BaseModel):
    """Rendered Excel artifact metadata."""

    model_config = ConfigDict(extra="forbid")
    filepath: str
    template_version: str
    sha256: str
    row_count: int


class PublishArtifactModel(BaseModel):
    """A full publish bundle. Renderer constructs this, OutputGate inspects this."""

    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(min_length=8, max_length=64)
    asof: date
    universe_size: int = Field(ge=1)
    regime: str

    scores: list[StockScore]
    alerts: list[RiskAlert]
    narrative: NarrativeResult

    excel: ExcelOutput | None = None
    text_for_publish: str = Field(min_length=10)  # Slack / Email body

    metadata: dict[str, Any] = Field(default_factory=dict)
