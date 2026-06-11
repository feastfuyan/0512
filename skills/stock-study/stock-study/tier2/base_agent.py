"""
BaseAgent — every LLM-augmented step inherits from this.

Responsibilities:
  - Load system prompt from prompts/<agent_id>/<version>.md
  - Wrap Anthropic SDK call with BudgetGuard precheck/postcheck
  - Sanitize task input before adding to context (Layer 1)
  - Validate tool args before dispatch (Layer 2)
  - Validate LLM output against Pydantic output_model

Subclasses register tools and provide a `_dispatch_tool(name, args) -> dict`.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from observability.budget import BudgetGuard, CallRecord
from observability.tracing import trace_llm
from safety import InjectionDetected, ToolInputGuard, default_sanitizer

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"


# Per-1M-token pricing in USD (as of 2026-05). Update via registry.yaml as Anthropic changes.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
}


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    p = MODEL_PRICING.get(model, MODEL_PRICING["claude-sonnet-4-6"])
    return (input_tokens / 1_000_000) * p["input"] + (output_tokens / 1_000_000) * p["output"]


def load_pinned_prompt(agent_key: str) -> tuple[str, str]:
    """Read prompts/registry.yaml, find production pin, load prompt text. Returns (version, prompt_md)."""
    registry_path = PROMPTS_DIR / "registry.yaml"
    with registry_path.open(encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    version = registry["production"][agent_key]
    prompt_path = PROMPTS_DIR / agent_key / f"{version}.md"
    return version, prompt_path.read_text(encoding="utf-8")


class MaxStepsExhausted(Exception):
    pass


class BaseAgent:
    """Subclass and override `tools` + `_dispatch_tool` + `output_model`."""

    agent_key: str = "base_agent"
    output_model: type[BaseModel] | None = None
    default_model: str = "claude-sonnet-4-6"
    default_max_tokens: int = 4096
    default_temperature: float = 0.2

    def __init__(self, *, model: str | None = None, budget: BudgetGuard | None = None) -> None:
        self.agent_id = self.agent_key
        self.model = model or self.default_model
        self.prompt_version, self.system_prompt = load_pinned_prompt(self.agent_key)
        self.budget = budget or BudgetGuard()
        self.sanitizer = default_sanitizer()
        self.tool_guard = ToolInputGuard()
        self._llm = None
        if os.environ.get("STOCKSTUDY_MOCK_LLM", "false").lower() == "true":
            return
        try:
            from anthropic import Anthropic

            self._llm = Anthropic()
        except Exception as e:  # pragma: no cover
            log.warning("Anthropic SDK init failed (%s); will fail on invoke", e)

    @property
    def tools(self) -> list[dict[str, Any]]:
        """Subclass overrides this. Each entry must conform to Anthropic tools spec."""
        return []

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Subclass implements this. Receives validated `tool_input`."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement _dispatch_tool")

    def _mock_response(self, task: BaseModel) -> BaseModel:
        """Used in CI / smoke tests. Subclass may override to return realistic dummy."""
        if self.output_model is None:
            raise RuntimeError("mock mode requires output_model to be set")
        # Trivial: try constructing a minimal valid output. Override per-subclass for richer mocks.
        try:
            return self.output_model.model_validate({})
        except ValidationError:
            raise RuntimeError(
                f"{self.__class__.__name__}: no mock implementation; override _mock_response"
            )

    @trace_llm
    def invoke(self, task: BaseModel, *, max_steps: int = 5) -> BaseModel:
        if os.environ.get("STOCKSTUDY_MOCK_LLM", "false").lower() == "true":
            return self._mock_response(task)

        if self._llm is None:
            raise RuntimeError(
                "Anthropic SDK not initialised. Either set STOCKSTUDY_MOCK_LLM=true or fix env."
            )

        self.budget.precheck(self.agent_id)

        # Layer 1: sanitize any free-text fields in task
        task_dict = task.model_dump()
        self._scan_task_strings(task_dict)

        history: list[dict[str, Any]] = [
            {"role": "user", "content": json.dumps(task_dict, ensure_ascii=False, default=str)}
        ]

        for step in range(max_steps):
            t0 = time.monotonic()
            resp = self._llm.messages.create(
                model=self.model,
                system=self.system_prompt,
                tools=self.tools,
                messages=history,
                max_tokens=self.default_max_tokens,
                temperature=self.default_temperature,
            )
            duration_ms = int((time.monotonic() - t0) * 1000)
            cost = calculate_cost(resp.usage.input_tokens, resp.usage.output_tokens, self.model)
            self.budget.postcheck(
                CallRecord(
                    agent_id=self.agent_id,
                    model=self.model,
                    prompt_version=self.prompt_version,
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    stop_reason=resp.stop_reason,
                )
            )

            if resp.stop_reason == "end_turn":
                text_blocks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
                return self._parse_output("".join(text_blocks))

            if resp.stop_reason == "tool_use":
                tool_results = []
                for block in resp.content:
                    if getattr(block, "type", "") != "tool_use":
                        continue
                    try:
                        validated_args = self.tool_guard.validate(
                            block.name, dict(block.input), source="llm_generated"
                        )
                        result = self._dispatch_tool(block.name, validated_args)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False, default=str),
                            }
                        )
                    except InjectionDetected as e:
                        log.error("tool guard blocked: %s", e)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "is_error": True,
                                "content": f"tool_blocked_by_safety: {e}",
                            }
                        )
                history.append({"role": "assistant", "content": resp.content})
                history.append({"role": "user", "content": tool_results})
                continue

            # Unknown stop reason
            log.warning("unexpected stop_reason=%s; aborting loop", resp.stop_reason)
            break

        raise MaxStepsExhausted(f"{self.agent_id} ran {max_steps} steps without end_turn")

    # --------- helpers ---------

    def _scan_task_strings(self, obj: Any, path: str = "$") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._scan_task_strings(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._scan_task_strings(item, f"{path}[{i}]")
        elif isinstance(obj, str) and len(obj) > 60:
            r = self.sanitizer.scan(obj, source="user_input")
            if not r.safe:
                raise InjectionDetected(
                    severity=r.severity,
                    matched_ids=r.matched_ids,
                    source=f"task_input:{path}",
                    sample=obj,
                )

    def _parse_output(self, text: str) -> BaseModel:
        if self.output_model is None:
            raise RuntimeError("output_model not set on subclass")
        # Try direct JSON first; if the model fenced it in ```json ... ```, strip that.
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("```", 2)[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.rsplit("```", 1)[0]
        try:
            return self.output_model.model_validate_json(clean)
        except ValidationError as e:
            log.error("output validation failed: %s; text=%r", e, text[:500])
            raise
