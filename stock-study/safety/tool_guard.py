"""
Layer 2 — Tool Input Guard.

Every tool_use call from an Agent must pass through `ToolInputGuard.validate()`
BEFORE the actual tool function executes. This catches:
  1. Pydantic schema violations (extra fields, wrong types, range errors).
  2. Long string fields containing injection patterns from external sources.
  3. Format anomalies on known sensitive fields (e.g. ticker must be ASX:XXX).

Configure tool schemas in `tier2/tools/*.py` and register them in TOOL_REGISTRY.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from safety.exceptions import (
    InjectionDetected,
    ToolArgInvalid,
    ToolArgTooLong,
    ToolSchemaViolation,
)
from safety.sanitizer import default_sanitizer

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^ASX:[A-Z0-9]{3,5}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_TEXT_LEN_DEFAULT = 8000

# Tools register their input model here. Populated at import time by tier2/tools/.
TOOL_REGISTRY: dict[str, type[BaseModel]] = {}


def register_tool(name: str, model: type[BaseModel]) -> None:
    """Tools call this on import to register their input schema."""
    TOOL_REGISTRY[name] = model


class ToolInputGuard:
    """Validate tool args. Raise on any violation."""

    def __init__(self, max_text_len: int = _MAX_TEXT_LEN_DEFAULT) -> None:
        self.sanitizer = default_sanitizer()
        self.max_text_len = max_text_len

    def validate(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        source: str = "llm_generated",
    ) -> dict[str, Any]:
        """
        Returns sanitized params (possibly with redacted strings). Raises on
        any safety violation.

        `source` indicates where the params originated:
          - 'llm_generated': the Agent constructed these args (lower risk)
          - 'user_input', 'news_feed', 'pdf_extract', 'social_media',
            'kg_query': external source, high risk → full PI scan
        """
        # 1. Schema check
        model = TOOL_REGISTRY.get(tool_name)
        if model is None:
            raise ToolSchemaViolation(tool_name, f"tool {tool_name!r} not registered")
        try:
            validated = model(**params)
        except ValidationError as e:
            raise ToolSchemaViolation(tool_name, str(e)) from e

        # 2. String field checks
        out_params = validated.model_dump()
        for k, v in out_params.items():
            if isinstance(v, str):
                self._check_string(tool_name, k, v, source, out_params)

        # 3. Known sensitive fields
        if "ticker" in out_params and not _TICKER_RE.match(out_params["ticker"]):
            raise ToolArgInvalid("ticker", out_params["ticker"])
        if "asof" in out_params and not _DATE_RE.match(str(out_params["asof"])):
            raise ToolArgInvalid("asof", str(out_params["asof"]))

        return out_params

    def _check_string(
        self,
        tool: str,
        field: str,
        value: str,
        source: str,
        out: dict[str, Any],
    ) -> None:
        if len(value) > self.max_text_len:
            raise ToolArgTooLong(tool, field, len(value))
        # External-source strings always get scanned (regardless of length).
        # `llm_generated` only scans long strings to keep latency low.
        if source not in ("user_input", "news_feed", "pdf_extract", "social_media", "kg_query"):
            if len(value) < 200:
                return
        elif len(value) < 30:
            # Even external sources need a minimum text length to scan meaningfully.
            return
        # External-source strings always get scanned.
        if source in ("user_input", "news_feed", "pdf_extract", "social_media", "kg_query"):
            r = self.sanitizer.scan(value, source=source)
            if not r.safe:
                raise InjectionDetected(
                    severity=r.severity,
                    matched_ids=r.matched_ids,
                    source=source,
                    sample=value,
                )
            # If high/medium severity, replace with escaped version
            if r.matched_ids:
                out[field] = r.redacted_text
                log.info(
                    "tool_guard: %s.%s sanitized (severity=%s, ids=%s)",
                    tool,
                    field,
                    r.severity,
                    r.matched_ids,
                )


# Convenience singleton
_default: ToolInputGuard | None = None


def default_guard() -> ToolInputGuard:
    global _default
    if _default is None:
        _default = ToolInputGuard()
    return _default
