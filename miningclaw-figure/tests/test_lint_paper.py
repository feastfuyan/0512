"""
test_lint_paper.py — Tests for lint_paper and lint_figure paper-path checks.
"""

from __future__ import annotations

import sys
import pathlib

_SK = pathlib.Path(__file__).parent.parent
if str(_SK) not in sys.path:
    sys.path.insert(0, str(_SK))

import pytest
from figure_lint import lint_paper, lint_figure
from figure_spec import FigureSpec, Encoding, RenderOpts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paper_fs(*, claim: str = "grade-tonnage defends resource", color_scale: str = "default") -> FigureSpec:
    return FigureSpec(
        claim=claim,
        chart_type="line",
        data=[{"x": 0.5, "y": 10.0, "l": "a", "v": 10.0}],
        encoding=Encoding(
            x_field="x", y_field="y", label_field="l", value_field="v",
            x_title="Cut-off (g/t)", y_title="Tonnes (Mt)", unit="Mt",
        ),
        title="Grade-Tonnage",
        source_note="QP signed 2026-06-01",
        opts=RenderOpts(dimensions="89mm", color_scale=color_scale),
    )


def _minimal_svg(*, with_text: bool = True, with_risk_palette: bool = False) -> str:
    text_el = '<text x="10" y="20">Cut-off (g/t)</text>' if with_text else ""
    risk_fill = ' fill="#C00000"' if with_risk_palette else ""
    return (
        f'<svg viewBox="0 0 252 180" xmlns="http://www.w3.org/2000/svg">'
        f'{text_el}'
        f'<rect x="10" y="10" width="100" height="80"{risk_fill}/>'
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# lint_paper tests (backward-compat function still exported)
# ---------------------------------------------------------------------------

def test_empty_claim_paper_fails():
    """fs=None must produce a claim blocker."""
    r = lint_paper("<svg></svg>", fs=None)
    assert not r.passed
    assert "claim" in " ".join(r.blockers).lower()


def test_well_formed_paper_passes():
    """Paper SVG with <text> + valid claim passes."""
    r = lint_paper(_minimal_svg(with_text=True), fs=_paper_fs())
    assert r.passed, f"Expected pass; blockers: {r.blockers}"


def test_no_text_element_fails():
    """Paper SVG without <text> fails with labeling blocker."""
    r = lint_paper(_minimal_svg(with_text=False), fs=_paper_fs())
    assert not r.passed
    assert any("label" in b.lower() or "text" in b.lower() or "axis" in b.lower()
               for b in r.blockers), f"Expected labeling blocker; got: {r.blockers}"


def test_risk_semantic_without_palette_fails():
    """color_scale='risk-semantic' but SVG lacks risk hex → blocker."""
    r = lint_paper(_minimal_svg(with_text=True, with_risk_palette=False),
                   fs=_paper_fs(color_scale="risk-semantic"))
    assert not r.passed
    assert any("risk" in b.lower() or "palette" in b.lower() or "color" in b.lower()
               for b in r.blockers)


def test_risk_semantic_with_palette_passes():
    """color_scale='risk-semantic' + SVG contains risk hex → passes."""
    r = lint_paper(_minimal_svg(with_text=True, with_risk_palette=True),
                   fs=_paper_fs(color_scale="risk-semantic"))
    assert r.passed, f"Expected pass; blockers: {r.blockers}"


# ---------------------------------------------------------------------------
# lint_figure tests (new unified entry point)
# ---------------------------------------------------------------------------

def test_lint_figure_passes_well_formed():
    """lint_figure must pass on a well-formed SVG with claim and text labels."""
    r = lint_figure(_minimal_svg(with_text=True), _paper_fs())
    assert r.passed, f"lint_figure should pass; blockers={r.blockers}"


def test_lint_figure_risk_semantic_blocks():
    """lint_figure applies risk-palette check via opts.color_scale."""
    r = lint_figure(
        _minimal_svg(with_text=True, with_risk_palette=False),
        _paper_fs(color_scale="risk-semantic"),
    )
    assert not r.passed
    assert any("risk" in b.lower() for b in r.blockers)
