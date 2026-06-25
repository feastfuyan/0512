"""
test_render_paper.py — Acceptance tests for the unified figure renderer.

Tests:
  1. figure_spec_to_vegalite returns valid Vega-Lite v5 spec with sort=null injected.
  2. 89mm dimensions constraint (width <= 252px nominal).
  3. report-wide dimensions produce width == 1040.
  4. lynai theme injects LynAI palette into config.
  5. Real render via vl-convert (env-gated, skipped if vl_convert absent).
  6. normalize_svg unit test on a sample SVG string.
"""
import importlib.util
import pytest

from figure_spec import FigureSpec, Encoding, RenderOpts
from render_paper import figure_spec_to_vegalite, normalize_svg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fs(ct: str, **opts_extra) -> FigureSpec:
    """Build a minimal FigureSpec for testing. opts_extra overrides RenderOpts defaults."""
    opts_kwargs = {"dimensions": "89mm"}
    opts_kwargs.update(opts_extra)  # caller can override dimensions
    return FigureSpec(
        claim="grade-tonnage defends resource",
        chart_type=ct,
        data=[{"x": 0.5, "y": 10.0, "l": "a", "v": 10.0}],
        encoding=Encoding(
            x_field="x",
            y_field="y",
            label_field="l",
            value_field="v",
            x_title="Cut-off",
            y_title="Tonnes",
            unit="Mt",
        ),
        title="GT",
        source_note="QP",
        opts=RenderOpts(**opts_kwargs),
    )


# ---------------------------------------------------------------------------
# Test 1: compiles-to-vegalite-with-sort-disabled
# ---------------------------------------------------------------------------

def test_compiles_to_vegalite_with_sort_disabled():
    """figure_spec_to_vegalite must return valid Vega-Lite v5 spec with sort=null on x channel."""
    spec = figure_spec_to_vegalite(_fs("line"))

    assert "$schema" in spec, "spec must have $schema"
    assert spec["$schema"].startswith("https://vega.github.io/schema/vega-lite"), (
        f"$schema must be vega-lite URL, got: {spec['$schema']}"
    )

    enc = spec.get("encoding", {})
    assert "x" in enc, "spec must have encoding.x"
    assert "sort" in enc["x"], "encoding.x must have 'sort' key injected"
    assert enc["x"]["sort"] is None, (
        f"encoding.x.sort must be None (null), got: {enc['x']['sort']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: 89mm width applied
# ---------------------------------------------------------------------------

def test_89mm_width_applied():
    """dimensions='89mm' must produce spec width <= 252px nominal."""
    spec = figure_spec_to_vegalite(_fs("line"))
    assert "width" in spec, "spec must have 'width'"
    assert spec["width"] <= 252, (
        f"89mm column width must be <= 252px nominal, got: {spec['width']}"
    )


def test_old_89mm_dimension_string_accepted():
    """Legacy 'paper-89mm' dimension string must still produce correct width."""
    fs = _fs("line")
    fs = FigureSpec(
        claim=fs.claim, chart_type=fs.chart_type, data=fs.data,
        encoding=fs.encoding, title=fs.title, source_note=fs.source_note,
        opts=RenderOpts(dimensions="paper-89mm"),
    )
    spec = figure_spec_to_vegalite(fs)
    assert spec["width"] <= 252


# ---------------------------------------------------------------------------
# Test 3: report-wide dimensions
# ---------------------------------------------------------------------------

def test_report_wide_produces_1040():
    """dimensions='report-wide' must produce width == 1040."""
    spec = figure_spec_to_vegalite(_fs("horizontal-bar", dimensions="report-wide"))
    assert spec["width"] == 1040, (
        f"report-wide must produce width=1040, got: {spec['width']}"
    )


# ---------------------------------------------------------------------------
# Test 4: lynai theme injects navy/teal palette
# ---------------------------------------------------------------------------

def test_lynai_theme_overrides_mark_color():
    """theme='lynai' must inject LynAI teal as the mark color."""
    spec = figure_spec_to_vegalite(_fs("horizontal-bar", theme="lynai"))
    mark_color = spec.get("config", {}).get("mark", {}).get("color", "")
    assert mark_color.lower() == "#14b8a6", (
        f"lynai theme must set mark.color=#14b8a6, got: {mark_color!r}"
    )


def test_nature_theme_uses_tableau10():
    """Default nature theme must use tableau10 scheme."""
    spec = figure_spec_to_vegalite(_fs("line", theme="nature"))
    category_scheme = spec.get("config", {}).get("range", {}).get("category", {})
    assert isinstance(category_scheme, dict), "range.category must be a dict"
    assert category_scheme.get("scheme") == "tableau10", (
        f"nature theme must use tableau10; got: {category_scheme}"
    )


# ---------------------------------------------------------------------------
# Test 5: all 16 chart types compile without error
# ---------------------------------------------------------------------------

def test_all_chart_types_compile():
    """All 16 chart types must produce a valid Vega-Lite spec."""
    from figure_spec import ALL_CHART_TYPES
    for ct in ALL_CHART_TYPES:
        opts_extra = {}
        if ct == "diverging":
            opts_extra["diverging_domain"] = (-50.0, 50.0)
        spec = figure_spec_to_vegalite(_fs(ct, **opts_extra))
        assert "$schema" in spec, f"chart_type '{ct}' must produce a spec with $schema"


# ---------------------------------------------------------------------------
# Test 6: real render (env-gated)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    importlib.util.find_spec("vl_convert") is None,
    reason="vl-convert not installed (paper render is build-time/prod only)",
)
def test_real_render_produces_svg():
    """When vl-convert is available, render_figure must return a valid SVG string."""
    from render_paper import render_figure

    out = render_figure(_fs("line"))
    assert isinstance(out, dict), "render_figure must return a dict"
    assert "svg" in out, "render_figure result must have 'svg' key"
    svg = out["svg"]
    assert isinstance(svg, str), "svg must be a string"
    assert svg.lstrip().startswith("<svg"), f"svg must start with <svg, got: {svg[:40]!r}"
    assert "</svg>" in svg, "svg must contain </svg>"


# ---------------------------------------------------------------------------
# Test 7: normalize_svg unit test
# ---------------------------------------------------------------------------

def test_normalize_svg_renumbers_ids_and_rounds_floats():
    sample_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="252" height="180">'
        '<defs>'
        '<clipPath id="clip-auto-7f3a2b">'
        '<rect x="0.12345678" y="3.99999999" width="252.0" height="180.0"/>'
        '</clipPath>'
        '</defs>'
        '<g clip-path="url(#clip-auto-7f3a2b)">'
        '<rect x="10.123456789" y="20.987654321" width="100.000001" height="50.000001"/>'
        '</g>'
        '</svg>'
    )

    normalized = normalize_svg(sample_svg)

    assert normalized.lstrip().startswith("<svg"), "normalized must still be SVG"
    assert "</svg>" in normalized
    assert normalize_svg(sample_svg) == normalize_svg(sample_svg), "must be deterministic"

    import re
    float_matches = re.findall(r'\d+\.\d{6,}', normalized)
    assert not float_matches, (
        f"normalized SVG must not contain floats with >=6 decimal digits, found: {float_matches}"
    )

    assert 'clip-auto-7f3a2b' not in normalized
    assert 'clip_0' in normalized
    assert 'url(#clip_0)' in normalized
