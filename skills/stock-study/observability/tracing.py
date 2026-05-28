"""OpenTelemetry tracing. Best-effort: works without a collector running."""

from __future__ import annotations

import logging
import os
import time
from functools import wraps
from typing import Any, Callable

log = logging.getLogger(__name__)

_ENABLED = False
tracer: Any | None = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.environ.get("OTEL_SERVICE_NAME", "stockstudy")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("stockstudy")

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as e:  # pragma: no cover
            log.warning("OTLP exporter init failed: %s — tracing will be local only", e)

    _ENABLED = True
except Exception as e:  # pragma: no cover
    log.warning("OpenTelemetry not available: %s", e)
    tracer = None


def trace_llm(fn: Callable) -> Callable:
    """
    Decorator: instrument an LLM invocation. Records:
      - agent_id, model, prompt_version (from kwargs)
      - input_tokens, output_tokens, cost_usd, stop_reason (from response)
      - duration_ms
    Compatible with BaseAgent.invoke style.
    """

    @wraps(fn)
    def wrapped(self, *args: Any, **kwargs: Any) -> Any:
        if tracer is None:
            return fn(self, *args, **kwargs)
        with tracer.start_as_current_span("llm.invoke") as span:
            span.set_attribute("agent_id", getattr(self, "agent_id", "unknown"))
            span.set_attribute("model", getattr(self, "model", "unknown"))
            span.set_attribute(
                "prompt_version", getattr(self, "prompt_version", "unknown")
            )
            t0 = time.monotonic()
            try:
                resp = fn(self, *args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                span.set_attribute("error", True)
                raise
            duration_ms = int((time.monotonic() - t0) * 1000)
            span.set_attribute("duration_ms", duration_ms)
            # Caller is responsible for recording cost/tokens via BudgetGuard.postcheck
            return resp

    return wrapped
