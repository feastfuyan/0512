"""Compliance-Sentinel advisory output schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComplianceWarning(BaseModel):
    """One advisory warning from Compliance-Sentinel.

    Note: warnings are advisory only. The OutputGate (Layer 3) is the authority
    on whether to block (D7).
    """

    model_config = ConfigDict(extra="forbid")
    severity: Literal["info", "low", "medium", "high"]
    field_path: str = Field(min_length=1, max_length=200)
    issue: str = Field(min_length=1, max_length=500)
    suggested_fix: str | None = None


class ComplianceWarningList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warnings: list[ComplianceWarning] = Field(default_factory=list)
    overall_recommendation: Literal["publish", "publish_with_caveats", "human_review"]
