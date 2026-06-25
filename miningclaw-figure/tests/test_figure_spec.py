import pytest
from figure_spec import FigureSpec, Encoding, Evidence, RenderOpts, ALL_CHART_TYPES


def _enc(**kw): return Encoding(x_field="x", y_field="y", label_field="l", value_field="v",
                                x_title="X", y_title="Y", unit="t", **kw)


def _minimal(**kw):
    """Build a minimal valid FigureSpec with optional overrides."""
    defaults = dict(
        claim="c",
        chart_type="horizontal-bar",
        data=[{"x": 1, "y": 1, "l": "a", "v": 1}],
        encoding=_enc(),
        title="T",
        source_note="s",
    )
    defaults.update(kw)
    return FigureSpec(**defaults)


def test_all_chart_types_accepted():
    """All chart types in ALL_CHART_TYPES must be constructable without error."""
    data = [{"x": 1.0, "y": 10.0, "l": "a", "v": 10.0}]
    for ct in ALL_CHART_TYPES:
        extra = {}
        if ct == "diverging":
            extra["opts"] = RenderOpts(diverging_domain=(-50.0, 50.0))
        FigureSpec(
            claim="c",
            chart_type=ct,
            data=data,
            encoding=_enc(),
            title="T",
            source_note="s",
            **extra,
        )


def test_unknown_chart_type_rejected():
    with pytest.raises(ValueError):
        _minimal(chart_type="waterfall-3d-exploded")


def test_claim_required():
    with pytest.raises(ValueError):
        _minimal(claim="")


def test_claim_whitespace_rejected():
    with pytest.raises(ValueError):
        _minimal(claim="   ")


def test_encoding_unit_required():
    with pytest.raises(Exception):
        Encoding(x_field="x", y_field="y", label_field="l", value_field="v",
                 x_title="X", y_title="Y")  # no unit


def test_non_numeric_value_field_rejected():
    """FigureSpec must raise ValueError when value_field contains a string."""
    with pytest.raises(ValueError):
        FigureSpec(
            claim="c",
            chart_type="horizontal-bar",
            data=[{"x": 1, "y": 1, "l": "a", "v": "not-a-number"}],
            encoding=_enc(),
            title="T",
            source_note="s",
        )


def test_data_rowshape_validated():
    with pytest.raises(ValueError):
        FigureSpec(
            claim="c",
            chart_type="horizontal-bar",
            data=[{"x": 1}],  # rows missing y/l/v
            encoding=_enc(),
            title="T",
            source_note="s",
        )


def test_render_opts_defaults():
    fs = _minimal()
    assert fs.opts.theme == "nature"
    assert fs.opts.output_format == "svg"
    assert fs.opts.dimensions == "183mm"


def test_lynai_theme_accepted():
    fs = _minimal(opts=RenderOpts(theme="lynai", dimensions="report-wide", fig_id="fig-x-1"))
    assert fs.opts.theme == "lynai"
    assert fs.opts.dimensions == "report-wide"
    assert fs.opts.fig_id == "fig-x-1"


def test_old_dimension_strings_accepted():
    """Legacy 'paper-89mm' / 'paper-183mm' dimension strings must still be accepted."""
    fs = _minimal(opts=RenderOpts(dimensions="paper-89mm"))
    assert fs.opts.dimensions == "paper-89mm"
    fs2 = _minimal(opts=RenderOpts(dimensions="paper-183mm"))
    assert fs2.opts.dimensions == "paper-183mm"


def test_diverging_requires_domain():
    with pytest.raises(ValueError):
        FigureSpec(
            claim="c",
            chart_type="diverging",
            data=[{"x": 1, "y": 1, "l": "a", "v": 1}],
            encoding=_enc(),
            title="T",
            source_note="s",
            # opts.diverging_domain not set → should raise
        )


def test_diverging_with_domain_ok():
    fs = FigureSpec(
        claim="c",
        chart_type="diverging",
        data=[{"x": 1.0, "y": 1.0, "l": "a", "v": 1.0}],
        encoding=_enc(),
        title="T",
        source_note="s",
        opts=RenderOpts(diverging_domain=(-100.0, 100.0)),
    )
    assert fs.chart_type == "diverging"
