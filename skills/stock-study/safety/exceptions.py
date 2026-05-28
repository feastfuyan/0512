"""Safety exceptions. Raised by Layer 1 (sanitizer), Layer 2 (tool_guard), Layer 3 (output_gate)."""

from __future__ import annotations


class SafetyError(Exception):
    """Base. Catch this if you want to handle any safety violation."""


class InjectionDetected(SafetyError):
    """Layer 1 / Layer 2: prompt injection pattern matched."""

    def __init__(
        self,
        *,
        severity: str,
        matched_ids: list[str],
        source: str,
        sample: str = "",
    ) -> None:
        self.severity = severity
        self.matched_ids = matched_ids
        self.source = source
        self.sample = sample[:200]
        super().__init__(
            f"InjectionDetected(severity={severity}, "
            f"matched={matched_ids}, source={source})"
        )


class ToolSchemaViolation(SafetyError):
    """Layer 2: tool input failed Pydantic schema validation."""

    def __init__(self, tool: str, detail: str) -> None:
        self.tool = tool
        self.detail = detail
        super().__init__(f"ToolSchemaViolation(tool={tool}): {detail}")


class ToolArgTooLong(SafetyError):
    def __init__(self, tool: str, field: str, length: int) -> None:
        super().__init__(f"ToolArgTooLong(tool={tool}, field={field}, len={length})")


class ToolArgInvalid(SafetyError):
    def __init__(self, field: str, value: str) -> None:
        super().__init__(f"ToolArgInvalid({field}={value!r})")


class OutputBlocked(SafetyError):
    """Layer 3: output gate rejected publish."""

    def __init__(self, blocks: list[str]) -> None:
        self.blocks = blocks
        super().__init__(f"OutputBlocked: {blocks}")
