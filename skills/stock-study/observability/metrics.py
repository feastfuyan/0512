"""Prometheus metrics. Best-effort: works without a pushgateway running."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram

    SAFETY_BLOCKS = Counter(
        "stockstudy_safety_blocks_total",
        "Number of safety blocks triggered",
        ["layer", "severity"],
    )
    COMPLIANCE_BLOCKS = Counter(
        "stockstudy_compliance_blocks_total",
        "OutputGate compliance blocks",
        ["reason"],
    )
    LLM_COST = Counter(
        "stockstudy_llm_cost_usd_total",
        "Cumulative LLM cost in USD",
        ["agent_id", "model"],
    )
    LLM_TOKENS = Counter(
        "stockstudy_llm_tokens_total",
        "Cumulative LLM tokens",
        ["agent_id", "model", "kind"],  # kind: input | output
    )
    LLM_LATENCY = Histogram(
        "stockstudy_llm_latency_seconds",
        "LLM call latency",
        ["agent_id", "model"],
        buckets=(0.5, 1, 2, 5, 10, 15, 30, 60),
    )
    IC_ROLLING = Gauge("stockstudy_ic_rolling_4w", "Rolling 4-week IC")
    BRIER_ROLLING = Gauge("stockstudy_brier_rolling_4w", "Rolling 4-week Brier")

    _ENABLED = True
except Exception as e:  # pragma: no cover
    log.warning("prometheus_client unavailable: %s", e)
    _ENABLED = False


def safety_block_inc(*, layer: str, severity: str) -> None:
    if _ENABLED:
        SAFETY_BLOCKS.labels(layer=layer, severity=severity).inc()


def compliance_block_inc(*, reason: str) -> None:
    if _ENABLED:
        COMPLIANCE_BLOCKS.labels(reason=reason).inc()


def llm_cost_inc(*, agent_id: str, model: str, cost_usd: float) -> None:
    if _ENABLED:
        LLM_COST.labels(agent_id=agent_id, model=model).inc(cost_usd)


def llm_tokens_inc(*, agent_id: str, model: str, kind: str, n: int) -> None:
    if _ENABLED:
        LLM_TOKENS.labels(agent_id=agent_id, model=model, kind=kind).inc(n)


def llm_latency_observe(*, agent_id: str, model: str, seconds: float) -> None:
    if _ENABLED:
        LLM_LATENCY.labels(agent_id=agent_id, model=model).observe(seconds)


def ic_set(value: float) -> None:
    if _ENABLED:
        IC_ROLLING.set(value)


def brier_set(value: float) -> None:
    if _ENABLED:
        BRIER_ROLLING.set(value)


def push_to_gateway() -> None:
    """Push collected metrics to the configured pushgateway."""
    gw = os.environ.get("PROMETHEUS_PUSHGATEWAY")
    if not gw or not _ENABLED:
        return
    try:
        from prometheus_client import REGISTRY, push_to_gateway as _push

        _push(gw, job="stockstudy", registry=REGISTRY)
    except Exception as e:  # pragma: no cover
        log.warning("push_to_gateway failed: %s", e)
