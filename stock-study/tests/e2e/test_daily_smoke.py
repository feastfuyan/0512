"""End-to-end smoke test of workflows.daily_run in mock mode.

Runs entire pipeline with STOCKSTUDY_MOCK_LLM=true. No external API calls.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_llm_env(monkeypatch):
    monkeypatch.setenv("STOCKSTUDY_MOCK_LLM", "true")


def test_daily_run_smoke_completes():
    from workflows.daily_run import daily_run

    result = daily_run(asof="2024-09-30")
    assert result["status"] == "ok"
    assert result["n_scores"] >= 5
    assert "artifact_id" in result


def test_daily_run_blocks_restricted_issuer(monkeypatch, tmp_path):
    """If we add ASX:BHP to restricted list, the run should be blocked."""
    restricted_path = tmp_path / "restricted.yaml"
    restricted_path.write_text("tickers:\n  - ASX:BHP\n", encoding="utf-8")
    monkeypatch.setenv("COMPLIANCE_RESTRICTED_PATH", str(restricted_path))

    from workflows.daily_run import daily_run

    result = daily_run(asof="2024-09-30")
    assert result["status"] == "blocked"
    assert any("ASX:BHP" in b for b in result["blocks"])


def test_daily_run_dry_run_blocks(monkeypatch):
    monkeypatch.setenv("STOCKSTUDY_DRY_RUN", "true")
    from workflows.daily_run import daily_run

    result = daily_run(asof="2024-09-30")
    assert result["status"] == "blocked"
    assert "dry_run_mode" in result["blocks"]
