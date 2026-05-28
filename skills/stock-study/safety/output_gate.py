"""
Layer 3 — Output Deterministic Gate.

Last line of defence. ANY publish-bound artifact must pass `OutputGate.gate()`
before going to Slack / Excel / API. The LLM has NO override power here — this
gate is rule-based.

Rules:
  R1 (hard block) — ticker in Restricted Issuer List
  R2 (hard block) — text contains a Banned Phrase
  R3 (hard block) — required Disclaimer missing
  R4 (advisory)   — Sentinel LLM warnings are attached but do NOT block
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass
class GateDecision:
    allowed: bool
    blocks: list[str] = field(default_factory=list)
    advisory_warnings: list[dict[str, Any]] = field(default_factory=list)
    requires_human: bool = False
    decided_at: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "blocks": self.blocks,
            "advisory_warnings": self.advisory_warnings,
            "requires_human": self.requires_human,
            "decided_at": self.decided_at,
        }


@dataclass
class PublishArtifact:
    """The thing being published. Construct in your renderer/workflow."""

    artifact_id: str
    tickers: list[str]
    text: str
    sentinel_warnings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OutputGate:
    """Deterministic rule-based gate. LLM-free."""

    def __init__(self) -> None:
        self.restricted = self._load_set(
            os.environ.get("COMPLIANCE_RESTRICTED_PATH", "compliance/restricted_issuers.yaml")
        )
        self.banned = self._load_banned(
            os.environ.get("COMPLIANCE_BANNED_PATH", "compliance/banned_phrases.yaml")
        )
        self.disclaimer = self._load_text(
            os.environ.get("COMPLIANCE_DISCLAIMER_PATH", "compliance/disclaimer.txt")
        )

    @staticmethod
    def _load_set(path: str) -> set[str]:
        p = Path(path)
        if not p.exists():
            log.warning("compliance file missing: %s", path)
            return set()
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return set(data.get("tickers", []))

    @staticmethod
    def _load_banned(path: str) -> dict[str, str]:
        p = Path(path)
        if not p.exists():
            return {}
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {item["phrase"]: item.get("reason", "") for item in data.get("phrases", [])}

    @staticmethod
    def _load_text(path: str) -> str:
        p = Path(path)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8").strip()

    def gate(self, artifact: PublishArtifact) -> GateDecision:
        blocks: list[str] = []

        # R1: Restricted Issuer
        for t in artifact.tickers:
            if t in self.restricted:
                blocks.append(f"restricted_issuer:{t}")

        # R2: Banned phrases
        for phrase, reason in self.banned.items():
            if phrase in artifact.text:
                blocks.append(f"banned_phrase:{phrase}:{reason}")

        # R3: Disclaimer required
        if self.disclaimer and self.disclaimer not in artifact.text:
            blocks.append("missing_disclaimer")

        # R4: emergency kill switch
        if os.environ.get("STOCKSTUDY_DRY_RUN", "").lower() == "true":
            blocks.append("dry_run_mode")

        decision = GateDecision(
            allowed=len(blocks) == 0,
            blocks=blocks,
            advisory_warnings=artifact.sentinel_warnings,
            requires_human=len(blocks) > 0,
            decided_at=datetime.now(timezone.utc).isoformat(),
        )

        if not decision.allowed:
            log.warning(
                "OutputGate BLOCK: artifact=%s blocks=%s",
                artifact.artifact_id,
                blocks,
            )
            try:
                from observability.metrics import compliance_block_inc

                for b in blocks:
                    compliance_block_inc(reason=b.split(":")[0])
            except Exception:
                pass

        return decision
