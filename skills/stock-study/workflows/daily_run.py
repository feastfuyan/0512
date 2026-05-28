"""
Daily run workflow — Prefect DAG (or plain script when Prefect unavailable).

Tier 1 → score & alert
Tier 2 → Agent-XT-Reasoner narrative
Layer 3 OutputGate → block?
Tier 2 → Compliance-Sentinel (advisory)
Publish.

Run:
    python -m workflows.daily_run                  # uses real LLM + real data
    STOCKSTUDY_MOCK_LLM=true python -m workflows.daily_run --asof 2024-09-30
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def daily_run(asof: str | None = None) -> dict:
    """Top-level smoke entry. Returns {"status": ..., "artifact_id": ...}."""
    asof_date = date.fromisoformat(asof) if asof else date.today()
    log.info("daily_run start asof=%s mock_llm=%s",
             asof_date, os.environ.get("STOCKSTUDY_MOCK_LLM", "false"))

    # Tier 1 (mock-friendly stubs until tier1/* fully implemented)
    scores, alerts, regime = _tier1_mock(asof_date) if _is_mock() else _tier1_real(asof_date)

    # Tier 2 — narrative
    from schemas.tasks import NarrativeTask
    from tier2.agent_xt_reasoner import AgentXTReasoner

    task = NarrativeTask(
        asof=asof_date,
        regime=regime,
        scores=scores,
        alerts=alerts,
        top_n=min(10, len(scores)),
        bottom_n=min(10, len(scores)),
    )
    agent = AgentXTReasoner()
    narrative = agent.invoke(task)
    log.info("narrative ok: %d top, %d bottom",
             len(narrative.top_narratives), len(narrative.bottom_narratives))

    # Build publish artifact
    from safety.output_gate import OutputGate, PublishArtifact

    artifact_id = f"ss-{asof_date.isoformat()}-{datetime.now(timezone.utc):%H%M%S}"
    text_for_publish = _build_text(narrative, regime)
    publish_artifact = PublishArtifact(
        artifact_id=artifact_id,
        tickers=[s.ticker for s in scores],
        text=text_for_publish,
    )

    # Layer 3 gate
    gate = OutputGate()
    decision = gate.gate(publish_artifact)
    if not decision.allowed:
        log.warning("OutputGate BLOCK %s: %s", artifact_id, decision.blocks)
        return {"status": "blocked", "artifact_id": artifact_id, "blocks": decision.blocks}

    # Tier 2 — advisory (Sentinel)
    if not _is_mock():
        from tier2.compliance_sentinel import ComplianceSentinel

        sentinel = ComplianceSentinel()
        sentinel_warnings = sentinel.advise(
            text_for_publish, artifact_id=artifact_id, tickers=[s.ticker for s in scores]
        )
        publish_artifact.sentinel_warnings = [w.model_dump() for w in sentinel_warnings.warnings]

    log.info("daily_run completed artifact_id=%s", artifact_id)
    return {"status": "ok", "artifact_id": artifact_id,
            "n_scores": len(scores), "regime": regime}


# ───── helpers ─────────────────────────────────────────────────────────────


def _is_mock() -> bool:
    return os.environ.get("STOCKSTUDY_MOCK_LLM", "false").lower() == "true"


def _tier1_mock(asof: date) -> tuple[list, list, str]:
    """Build a tiny fake universe so smoke tests run without external data."""
    from schemas.factors import FactorAttribution
    from schemas.scores import RiskAlert, StockScore

    tickers = ["ASX:BHP", "ASX:PLS", "ASX:NCM", "ASX:RIO", "ASX:LTR"]
    scores, alerts = [], []
    for i, t in enumerate(tickers):
        p_up = 0.65 - 0.08 * i
        scores.append(
            StockScore(
                ticker=t,
                asof=asof,
                p_up_raw=p_up,
                p_up_calibrated=p_up,
                label="↑多头" if p_up > 0.55 else "↗偏多" if p_up > 0.5 else "↘偏空" if p_up > 0.4 else "↓空头",
                target_central=100.0 + i * 10,
                target_p20=90.0 + i * 10,
                target_p80=110.0 + i * 10,
                stop_loss=80.0 + i * 10,
                attribution=FactorAttribution(
                    technical_pct=0.20, volatility_pct=0.15,
                    commodity_beta_pct=0.30, liquidity_pct=0.10,
                    valuation_pct=0.15, fundamental_pct=0.10,
                ),
                regime="Neutral",
                liquidity_gate_pass=True,
            )
        )
        alerts.append(
            RiskAlert(
                ticker=t, asof=asof, short_probability=0.2 + 0.1 * i,
                alert_level="none" if i < 2 else "watch" if i < 4 else "warn",
                reasons=[],
            )
        )
    return scores, alerts, "Neutral"


def _tier1_real(asof: date) -> tuple[list, list, str]:
    """TODO (陈夏童 + 罗阳): wire to tier1/* once those are filled in."""
    log.warning("real-tier1 not implemented yet — falling back to mock")
    return _tier1_mock(asof)


def _build_text(narrative, regime: str) -> str:
    """Compose the Slack/Email body. Always end with the disclaimer."""
    from pathlib import Path

    parts = [f"# StockStudy Daily — regime: {regime}\n"]
    parts.append("## Top picks\n")
    for n in narrative.top_narratives:
        parts.append(f"- **{n.ticker}**: {n.text}")
    parts.append("\n## Bottom picks\n")
    for n in narrative.bottom_narratives:
        parts.append(f"- **{n.ticker}**: {n.text}")
    parts.append(f"\n{narrative.regime_commentary}\n")
    disclaimer_path = Path(os.environ.get("COMPLIANCE_DISCLAIMER_PATH",
                                          "compliance/disclaimer.txt"))
    if disclaimer_path.exists():
        parts.append("\n---\n" + disclaimer_path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", help="ISO date, defaults to today")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = daily_run(args.asof)
    print(result)
    if result.get("status") == "blocked":
        sys.exit(2)


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
