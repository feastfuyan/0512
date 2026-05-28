"""Unit tests for safety.output_gate."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from safety.output_gate import OutputGate, PublishArtifact


@pytest.fixture()
def gate(monkeypatch, tmp_path):
    # Build a fresh compliance set for this test
    restricted_path = tmp_path / "restricted.yaml"
    restricted_path.write_text("tickers:\n  - ASX:RESTRICT\n", encoding="utf-8")
    banned_path = tmp_path / "banned.yaml"
    banned_path.write_text(
        "phrases:\n"
        "  - {phrase: 'guaranteed return', reason: 'promise'}\n"
        "  - {phrase: '保证收益', reason: '承诺'}\n",
        encoding="utf-8",
    )
    disclaimer_path = tmp_path / "disclaimer.txt"
    disclaimer_path.write_text("Disclaimer: not investment advice.", encoding="utf-8")
    monkeypatch.setenv("COMPLIANCE_RESTRICTED_PATH", str(restricted_path))
    monkeypatch.setenv("COMPLIANCE_BANNED_PATH", str(banned_path))
    monkeypatch.setenv("COMPLIANCE_DISCLAIMER_PATH", str(disclaimer_path))
    monkeypatch.delenv("STOCKSTUDY_DRY_RUN", raising=False)
    return OutputGate()


def test_clean_artifact_allowed(gate):
    art = PublishArtifact(
        artifact_id="a1",
        tickers=["ASX:BHP"],
        text="BHP up 3% this week. Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert d.allowed is True
    assert d.blocks == []


def test_restricted_ticker_blocked(gate):
    art = PublishArtifact(
        artifact_id="a2",
        tickers=["ASX:RESTRICT", "ASX:BHP"],
        text="some text. Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert d.allowed is False
    assert any("restricted_issuer:ASX:RESTRICT" in b for b in d.blocks)


def test_banned_phrase_blocked(gate):
    art = PublishArtifact(
        artifact_id="a3",
        tickers=["ASX:BHP"],
        text="BHP guaranteed return next quarter. Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert d.allowed is False
    assert any("banned_phrase:guaranteed return" in b for b in d.blocks)


def test_chinese_banned_phrase_blocked(gate):
    art = PublishArtifact(
        artifact_id="a4",
        tickers=["ASX:PLS"],
        text="PLS 是保证收益的标的。Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert d.allowed is False
    assert any("保证收益" in b for b in d.blocks)


def test_missing_disclaimer_blocked(gate):
    art = PublishArtifact(
        artifact_id="a5",
        tickers=["ASX:BHP"],
        text="BHP up 3%, looking strong this quarter.",
    )
    d = gate.gate(art)
    assert d.allowed is False
    assert "missing_disclaimer" in d.blocks


def test_dry_run_kill_switch_blocks_everything(gate, monkeypatch):
    monkeypatch.setenv("STOCKSTUDY_DRY_RUN", "true")
    art = PublishArtifact(
        artifact_id="a6",
        tickers=["ASX:BHP"],
        text="Clean text. Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert d.allowed is False
    assert "dry_run_mode" in d.blocks


def test_decided_at_is_iso(gate):
    art = PublishArtifact(
        artifact_id="a7",
        tickers=["ASX:BHP"],
        text="text. Disclaimer: not investment advice.",
    )
    d = gate.gate(art)
    assert "T" in d.decided_at and d.decided_at.endswith("+00:00")
