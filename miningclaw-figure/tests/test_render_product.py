"""Test product-dialect horizontal-bar renderer."""
import re
import pytest
from figure_spec import FigureSpec, Encoding, RenderOpts
from render_product_svg import render_product_svg


def _fs(rows):
    """Helper: build a FigureSpec for horizontal-bar tests."""
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
            unit="tenements",
        ),
        title="Top Holders",
        source_note="WA registry",
        opts=RenderOpts(output_format="html-embed", theme="lynai", fig_id="fig-mc06-3"),
    )


def test_emits_chart_block_with_id_and_viewbox():
    """Verify wrapper div, id, and viewBox are present."""
    svg = render_product_svg(_fs([{"label": "3D Resources Ltd", "count": 68}, {"label": "BHP", "count": 34}]))
    assert 'class="chart-block"' in svg
    assert 'id="fig-mc06-3"' in svg
    assert 'viewBox="0 0 1040 300"' in svg  # 2 rows × 42px + padding


def test_max_value_long_label_does_not_overflow():
    """Verify x-clamp: value labels stay within x=995 (1040 - 45 margin)."""
    svg = render_product_svg(_fs([{"label": "X", "count": 99999}, {"label": "Y", "count": 2}]))
    xs = [float(m) for m in re.findall(r'<text x="([\d.]+)"', svg)]
    assert max(xs) <= 995, f"max text x={max(xs)} exceeds 995 (overflow)"


def test_format_label_honors_value_format():
    """format_label must apply encoding.value_format when set (e.g. ',.0f')."""
    from figure_spec import format_label, Encoding
    enc_fmt = Encoding(
        x_field="count", y_field="label", label_field="label", value_field="count",
        x_title="Count", y_title="Holder", unit="",
        value_format=",.0f",
    )
    result = format_label(68000, enc_fmt)
    assert result == "68,000", f"Expected '68,000', got {result!r}"


def test_format_label_default_appends_unit():
    """format_label default path must append unit when no value_format is set."""
    from figure_spec import format_label, Encoding
    enc_default = Encoding(
        x_field="count", y_field="label", label_field="label", value_field="count",
        x_title="Count", y_title="Holder", unit=" Mt",
    )
    result = format_label(42, enc_default)
    assert result == "42 Mt", f"Expected '42 Mt', got {result!r}"


def test_format_label_used_in_render():
    """When value_format=',.0f', rendered SVG must show comma-formatted values."""
    fs = FigureSpec(
        claim="formatted test",
        chart_type="horizontal-bar",
        data=[{"label": "A", "count": 68000}],
        encoding=Encoding(
            x_field="count", y_field="label", label_field="label", value_field="count",
            x_title="Count", y_title="Holder", unit="",
            value_format=",.0f",
        ),
        title="Formatted Chart",
        source_note="test",
        opts=RenderOpts(output_format="html-embed", fig_id="fig-fmt-1"),
    )
    svg = render_product_svg(fs)
    assert "68,000" in svg, f"Expected '68,000' in rendered SVG; got snippet: {svg[:300]}"


def test_byte_stable():
    """Verify deterministic output (same input → same bytes)."""
    rows = [{"label": "a", "count": 5}, {"label": "b", "count": 3}]
    out1 = render_product_svg(_fs(rows))
    out2 = render_product_svg(_fs(rows))
    assert out1 == out2, "render_product_svg not byte-stable"
