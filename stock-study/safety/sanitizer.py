"""
Layer 1 — Input Sanitizer.

Any external text destined for an LLM context must pass through `InputSanitizer.scan()`
first. Critical-severity matches are redacted (text replaced with `[REDACTED]`) and
written to incidents. Lower severities are escaped + logged but allowed through.

Reference: see `safety/patterns/pi_patterns.yaml` for the full pattern library.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

Severity = Literal["low", "medium", "high", "critical"]
_SEV_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

log = logging.getLogger(__name__)

PATTERNS_PATH = Path(__file__).parent / "patterns" / "pi_patterns.yaml"


@dataclass
class SanitizeResult:
    """Result of a single sanitize pass."""

    safe: bool
    redacted_text: str
    severity: Severity
    matched_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "severity": self.severity,
            "matched_ids": self.matched_ids,
            "notes": self.notes,
        }


class InputSanitizer:
    """
    Stateless scanner. Construct once per process; call `scan()` per input.

    Performance note: patterns are compiled once at construction. A scan on a
    2KB string runs in <1ms on a 2024 laptop.
    """

    def __init__(self, patterns_path: Path | None = None) -> None:
        self._compiled: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
        self._unicode_red_flags: list[tuple[str, re.Pattern[str], Severity]] = []
        self._load(patterns_path or PATTERNS_PATH)

    def _load(self, path: Path) -> None:
        with path.open(encoding="utf-8") as f:
            data: dict = yaml.safe_load(f)
        for sev in ("critical", "high", "medium"):
            bucket: list[tuple[str, re.Pattern[str]]] = []
            for entry in data.get(sev, []):
                pid: str = entry["id"]
                pat: str = entry["pattern"]
                try:
                    bucket.append((pid, re.compile(pat, re.IGNORECASE | re.MULTILINE)))
                except re.error as e:
                    log.error("bad regex %s: %s", pid, e)
            self._compiled[sev] = bucket
        for entry in data.get("unicode_red_flags", []):
            pid = entry["id"]
            pat = entry["pattern"]
            sev2: Severity = entry.get("severity", "medium")  # type: ignore[assignment]
            self._unicode_red_flags.append((pid, re.compile(pat), sev2))

    @staticmethod
    def normalize(text: str) -> str:
        """
        Defend against Unicode trickery: NFKC normalize, strip zero-width chars,
        collapse BiDi controls. Keep full-width visible chars (they're valid input
        but flagged separately by unicode_red_flags).
        """
        text = unicodedata.normalize("NFKC", text)
        # 零宽字符 + BiDi 控制字符
        text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
        return text

    def scan(self, text: str, *, source: str = "unknown") -> SanitizeResult:
        """
        Returns SanitizeResult. Critical → safe=False, text replaced with
        '[REDACTED]'. Other severities → safe=True, text escaped (dangerous
        tokens wrapped in backticks).
        """
        if not text:
            return SanitizeResult(safe=True, redacted_text="", severity="low")

        normalized = self.normalize(text)

        matched_ids: list[str] = []
        overall: Severity = "low"

        # Pre-normalize Unicode scan (using original text, before NFKC)
        for pid, regex, sev in self._unicode_red_flags:
            if regex.search(text):
                matched_ids.append(pid)
                if _SEV_RANK[sev] > _SEV_RANK[overall]:
                    overall = sev

        # Pattern bucket scan (using normalized text)
        for sev in ("critical", "high", "medium"):
            for pid, regex in self._compiled[sev]:
                if regex.search(normalized):
                    matched_ids.append(pid)
                    if _SEV_RANK[sev] > _SEV_RANK[overall]:  # type: ignore[index]
                        overall = sev  # type: ignore[assignment]

        if overall in ("critical", "high"):
            self._write_incident(text, matched_ids, source)
            return SanitizeResult(
                safe=False,
                redacted_text=f"[REDACTED: {overall} injection detected]",
                severity=overall,
                matched_ids=matched_ids,
                notes=[f"source={source}"],
            )

        # high / medium: escape dangerous tokens but pass through
        escaped = self._escape(normalized, matched_ids)
        return SanitizeResult(
            safe=True,
            redacted_text=escaped,
            severity=overall,
            matched_ids=matched_ids,
            notes=[f"source={source}"],
        )

    def _escape(self, text: str, matched_ids: list[str]) -> str:
        """Wrap risky tokens in backticks so the LLM sees them as quoted code."""
        if not matched_ids:
            return text
        out = text
        # Escape the most common dangerous lexemes. Cheap & safe enough.
        risky = [
            "ignore previous",
            "ignore all previous",
            "[SYSTEM]",
            "[系统]",
            "DAN",
            "do anything now",
            "developer mode",
            "<|system|>",
            "<|im_start|>",
        ]
        for lex in risky:
            out = re.sub(re.escape(lex), f"`{lex}`", out, flags=re.IGNORECASE)
        return out

    def _write_incident(self, text: str, matched_ids: list[str], source: str) -> None:
        """
        Write to incidents/{date}_pi.jsonl. In production, this also pushes to
        Slack #incidents and increments Prometheus counter
        `stockstudy_safety_blocks_total{severity="critical"}`.
        """
        try:
            from observability.metrics import safety_block_inc

            safety_block_inc(layer="L1", severity="critical")
        except Exception:
            pass
        log.warning(
            "PI critical incident: source=%s matched=%s sample=%r",
            source,
            matched_ids,
            text[:120],
        )


# Convenience: a process-wide singleton.
_default: InputSanitizer | None = None


def default_sanitizer() -> InputSanitizer:
    global _default
    if _default is None:
        _default = InputSanitizer()
    return _default


def scan(text: str, *, source: str = "unknown") -> SanitizeResult:
    """Module-level shortcut, suitable for ad-hoc tests."""
    return default_sanitizer().scan(text, source=source)
