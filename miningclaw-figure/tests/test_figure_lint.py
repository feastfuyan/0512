"""tests/test_figure_lint.py — Acceptance tests for figure lint (product + unified)."""
import pathlib
import sys
import os

import pytest

_PROD_SRC_RAW = os.environ.get("MININGCLAWD_SRC", "")
_PROD_SRC = pathlib.Path(_PROD_SRC_RAW) if _PROD_SRC_RAW else pathlib.Path("NOT_CONFIGURED")

from figure_lint import lint_product, lint_figure
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_product_svg import render_product_svg


# ---------------------------------------------------------------------------
# Helper: build a standard FigureSpec for render tests
# ---------------------------------------------------------------------------

def _fs(rows, fig_id="fig-mc06-3"):
    return FigureSpec(
        claim="WA tenement accumulation",
        chart_type="horizontal-bar",
        data=rows,
        encoding=Encoding(
            x_field="count",
            y_field="label",
            label_field="label",
            value_field="count",
            x_title="Count",
            y_title="Holder",
            unit=" tenements",
        ),
        title="Top Holders",
        source_note="WA registry",
        opts=RenderOpts(output_format="html-embed", theme="lynai", fig_id=fig_id),
    )


# ---------------------------------------------------------------------------
# Test 1: honest horizontal-bar passes floor (all dims >= 9.0)
# ---------------------------------------------------------------------------

def test_honest_horizontal_bar_passes_floor():
    svg = render_product_svg(_fs([{"label": "a", "count": 68}, {"label": "b", "count": 34}]))
    r = lint_product(svg)
    assert r.passed, f"expected passed=True; blockers={r.blockers}"
    assert all(v >= 9.0 for v in r.dim_scores.values()), (
        f"all dims must be >=9.0 but got: {r.dim_scores}"
    )


# ---------------------------------------------------------------------------
# Test 2: G14 inferred-in-economic figure floors data_viz_integrity → failed
# ---------------------------------------------------------------------------

def test_g14_inferred_economic_floored():
    svg = render_product_svg(_fs([{"label": "Inferred zone", "count": 50}]))
    r = lint_product(
        svg,
        is_economic=True,
        classification="inferred",
        has_inferred_exclusion=False,
    )
    assert not r.passed, "G14 guard should set passed=False"
    assert r.dim_scores["data_viz_integrity"] == 0.0, (
        f"G14: data_viz_integrity must be floored to 0.0, got {r.dim_scores['data_viz_integrity']}"
    )
    assert any("G14" in b for b in r.blockers), f"expected G14 blocker, got {r.blockers}"


# ---------------------------------------------------------------------------
# Test 3: G14 inferred WITH exclusion note → data_viz_integrity preserved
# ---------------------------------------------------------------------------

def test_g14_inferred_with_exclusion_ok():
    svg = render_product_svg(_fs([{"label": "Inferred zone", "count": 50}]))
    r = lint_product(
        svg,
        is_economic=True,
        classification="inferred",
        has_inferred_exclusion=True,
    )
    assert r.dim_scores["data_viz_integrity"] > 0.0, (
        f"With has_inferred_exclusion=True, data_viz_integrity should not be floored; "
        f"got {r.dim_scores['data_viz_integrity']}"
    )


# ---------------------------------------------------------------------------
# Test 4: I8 unit-missing floors labeling
# ---------------------------------------------------------------------------

def _fs_no_unit(rows, fig_id="fig-mc06-no-unit"):
    """FigureSpec whose labels carry NO unit token (unit='')."""
    return FigureSpec(
        claim="bare count figure",
        chart_type="horizontal-bar",
        data=rows,
        encoding=Encoding(
            x_field="count",
            y_field="label",
            label_field="label",
            value_field="count",
            x_title="Count",
            y_title="Holder",
            unit="",
        ),
        title="No Unit Chart",
        source_note="test",
        opts=RenderOpts(output_format="html-embed", fig_id=fig_id),
    )


def test_i8_missing_unit_floors_labeling():
    svg = render_product_svg(_fs_no_unit([{"label": "Alpha", "count": 42}]))
    r = lint_product(svg)
    assert not r.passed, (
        f"Expected passed=False when no unit token present; blockers={r.blockers}"
    )
    assert r.dim_scores.get("labeling", 9.0) < 9.0, (
        f"labeling dim must be floored below 9.0, got {r.dim_scores.get('labeling')}"
    )
    assert any("I8" in b for b in r.blockers), (
        f"Expected I8 blocker in blockers={r.blockers}"
    )


def test_i8_unit_present_passes():
    svg = render_product_svg(_fs([{"label": "a", "count": 68}, {"label": "b", "count": 34}]))
    r = lint_product(svg)
    assert r.passed, (
        f"Honest case (unit=' tenements') should pass; blockers={r.blockers}"
    )
    assert r.dim_scores.get("labeling", 9.0) >= 9.0, (
        f"labeling must be >=9.0 when unit present; got {r.dim_scores.get('labeling')}"
    )


def test_i8_exotic_unit_with_expected_unit_passes():
    """Exotic unit (bbl) not in curated list passes when expected_unit is provided."""
    svg = render_product_svg(
        FigureSpec(
            claim="oil barrel volumes",
            chart_type="horizontal-bar",
            data=[
                {"label": "Zone A", "volume": 1500},
                {"label": "Zone B", "volume": 2200},
            ],
            encoding=Encoding(
                x_field="volume",
                y_field="label",
                label_field="label",
                value_field="volume",
                x_title="Barrels",
                y_title="Zone",
                unit=" bbl",
            ),
            title="Oil Volumes by Zone",
            source_note="production data",
            opts=RenderOpts(output_format="html-embed", fig_id="fig-oil-001"),
        )
    )

    r_pass = lint_product(svg, expected_unit="bbl")
    assert r_pass.passed, (
        f"exotic unit 'bbl' with expected_unit='bbl' should pass; "
        f"blockers={r_pass.blockers}"
    )
    assert r_pass.dim_scores["labeling"] >= 9.0

    r_fail = lint_product(svg, expected_unit=None)
    assert not r_fail.passed
    assert r_fail.dim_scores["labeling"] < 9.0
    assert any("I8" in b for b in r_fail.blockers)


# ---------------------------------------------------------------------------
# Test 5: parity — vendored vs product identical
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _PROD_SRC.exists(),
    reason="Set MININGCLAWD_SRC env var to lynai-miningclawd-monorepo/services/report/src",
)
def test_parity_vendored_vs_product_identical():
    import parity
    import vendored.figure_checks_vendored as ven

    prod = parity.load_product_module("figure_checks")

    corpus_dir = pathlib.Path(__file__).parent / "golden_corpus"
    svg_files = list(corpus_dir.glob("*.svg"))
    assert svg_files, f"golden_corpus/ is empty — no .svg fixtures found in {corpus_dir}"

    for svg_file in svg_files:
        html = svg_file.read_text("utf-8")
        ven_figs = ven.extract_figures(html)
        prod_figs = prod.extract_figures(html)
        pf = [ven.score_figure_deterministic(f) for f in ven_figs]
        qf = [prod.score_figure_deterministic(f) for f in prod_figs]
        assert pf == qf, (
            f"parity drift on {svg_file.name}:\n  vendored={pf}\n  product={qf}"
        )


# ---------------------------------------------------------------------------
# Test 6: lint_figure — unified entry point
# ---------------------------------------------------------------------------

def test_lint_figure_passes_on_honest_svg():
    """lint_figure must pass on a well-formed horizontal-bar with unit."""
    fs = _fs([{"label": "a", "count": 68}, {"label": "b", "count": 34}])
    svg = render_product_svg(fs)
    # Use svg output (not html-embed) so vendored floor check is skipped
    fs_svg = FigureSpec(
        claim=fs.claim,
        chart_type=fs.chart_type,
        data=fs.data,
        encoding=fs.encoding,
        title=fs.title,
        source_note=fs.source_note,
        opts=RenderOpts(output_format="svg"),
    )
    r = lint_figure(svg, fs_svg)
    assert r.passed, f"lint_figure should pass on honest svg; blockers={r.blockers}"


def test_lint_figure_g14_blocks():
    """lint_figure G14 guard must block inferred data in economic figures."""
    fs = FigureSpec(
        claim="Inferred cashflow projection",
        chart_type="horizontal-bar",
        data=[{"label": "Inferred zone", "count": 50}],
        encoding=Encoding(
            x_field="count", y_field="label", label_field="label", value_field="count",
            x_title="Count", y_title="Zone", unit=" Mt",
        ),
        title="Economic figure",
        source_note="test",
        opts=RenderOpts(
            output_format="svg",
            is_economic_figure=True,
            classification_category="inferred",
        ),
    )
    svg = render_product_svg(fs)
    r = lint_figure(svg, fs)
    assert not r.passed, "G14 should block inferred in economic figure"
    assert any("G14" in b for b in r.blockers)


def test_lint_figure_missing_claim_blocks():
    """lint_figure must block when claim is missing (passed as None via fs hack)."""
    fs = _fs([{"label": "a", "count": 10}])
    svg = render_product_svg(fs)

    class _FakeFSNoClaim:
        claim = ""
        opts = RenderOpts(output_format="svg")

    r = lint_figure(svg, _FakeFSNoClaim())
    assert not r.passed
    assert any("claim" in b for b in r.blockers)
