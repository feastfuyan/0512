"""
figure_spec.py — FigureSpec contract (unified: single render path)

render_target has been removed.  All 16 chart types are available regardless
of output document type.  Figure choice is driven by data and content.
theme / output_format / dimensions in RenderOpts control appearance and output.

Pydantic v2.  Single source of truth consumed by all renderers.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared label formatter (M1)
# ---------------------------------------------------------------------------

def format_label(value: int | float, encoding: "Encoding") -> str:
    """Format a numeric data value for display in a figure label.

    Honors ``encoding.value_format`` (a Python format spec such as ``",.0f"``
    or ``".1f"``) when set; otherwise falls back to the default behavior of
    ``int(value)`` concatenated with ``encoding.unit``.
    """
    unit = encoding.unit or ""
    if encoding.value_format:
        return format(value, encoding.value_format)
    if value == int(value):
        return f"{int(value)}{unit}"
    return f"{value}{unit}"


# ---------------------------------------------------------------------------
# Chart-type constants
# ---------------------------------------------------------------------------

ALL_CHART_TYPES: set[str] = {
    "horizontal-bar",
    "vertical-bar",
    "line",
    "area",
    "scatter",
    "grouped-bar",
    "stacked-bar",
    "diverging",
    "waterfall",
    "tornado",
    "resource-classification-stack",
    "grade-tonnage",
    "production-profile",
    "cost-curve",
    "risk-matrix",
    "traffic-light-scorecard",
}

# Deprecated aliases — kept so existing import sites don't break
PAPER_CHART_TYPES: set[str] = ALL_CHART_TYPES
PRODUCT_CHART_TYPES: set[str] = {"horizontal-bar"}  # no longer enforced as a gate


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    """Structured evidence record (I9)."""
    source_type: str
    ref: str


class Encoding(BaseModel):
    """Data-binding descriptor. All field names are verified against data rows by FigureSpec."""
    x_field: str
    y_field: str
    y2_field: str | None = None
    y2_title: str | None = None
    series_field: str | None = None
    color_field: str | None = None
    label_field: str
    value_field: str
    x_title: str
    y_title: str
    unit: str                                       # required — no default (I8)
    real_nominal: Literal["real", "nominal", "n/a"] = "n/a"
    base_year: int | None = None
    legend_title: str | None = None
    scale_x: Literal["linear", "log"] = "linear"
    scale_y: Literal["linear", "log"] = "linear"
    value_format: str | None = None
    label_template: str | None = None


# ---------------------------------------------------------------------------
# Unified render opts
# ---------------------------------------------------------------------------

class RenderOpts(BaseModel):
    """Unified rendering options.

    Chart type availability is no longer gated here — all 16 types are
    available for any document.  These opts control output format, size,
    and styling only.
    """
    # Output dimensions.
    # "89mm" / "paper-89mm"   → Nature single-col  (252 px)
    # "183mm" / "paper-183mm" → Nature double-col  (519 px)
    # "report-wide"           → product report width (1040 px)
    # Old "paper-*" names are accepted for backward compatibility.
    dimensions: Literal[
        "89mm", "183mm", "report-wide",
        "paper-89mm", "paper-183mm",  # deprecated aliases
    ] = "183mm"

    # Output format
    output_format: Literal["svg", "html-embed", "pdf", "png"] = "svg"

    # Style theme — controls colour palette / typography, NOT chart type availability.
    # "lynai"  → LynAI report palette: navy #1F3864 text, teal #14b8a6 bars
    # "nature" → Nature journal palette: Tableau-10 categorical, Inter font
    theme: Literal["lynai", "nature"] = "nature"

    # JORC / NI 43-101 classification (for G14 guard)
    classification_category: Literal[
        "inferred", "indicated", "measured",
        "exploration-target", "mixed", "n/a"
    ] = "n/a"
    is_economic_figure: bool = False
    classification_note: str | None = None

    # Chart-type-specific opts
    tornado_base: float | None = None
    waterfall_anchor: Literal["zero", "running"] | None = None
    diverging_domain: tuple[float, float] | None = None
    cutoff_grade: float | None = None
    cutoff_unit: str | None = None
    stack_type: Literal["zero", "normalize", "center"] | None = None
    color_scale: Literal["default", "risk-semantic"] = "default"
    highlight_band: tuple[float, float] | None = None
    is_subject_project: bool = False

    # Stable figure id for HTML embed (was ProductRenderOpts.fig_id)
    fig_id: str | None = None


# ---------------------------------------------------------------------------
# Assembled contract
# ---------------------------------------------------------------------------

class FigureSpec(BaseModel):
    """
    Full figure contract: data + encoding + unified RenderOpts.

    render_target has been removed.  All chart types in ALL_CHART_TYPES are
    available.  Use opts.theme / opts.output_format to control appearance.
    """
    claim: str
    evidence: list[Evidence] = []
    chart_type: str
    data: list[dict]
    encoding: Encoding
    title: str
    source_note: str
    sort: list[str] | None = None
    opts: RenderOpts = Field(default_factory=RenderOpts)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _validate_all(self) -> "FigureSpec":
        # 1. claim non-empty
        if not self.claim or not self.claim.strip():
            raise ValueError("claim must be non-empty")

        # 2. chart_type must be a known type
        if self.chart_type not in ALL_CHART_TYPES:
            raise ValueError(
                f"chart_type '{self.chart_type}' is not recognised "
                f"(allowed: {sorted(ALL_CHART_TYPES)})"
            )

        # 3. data row-shape: every referenced Encoding field must exist in ALL rows (fail-closed)
        enc = self.encoding
        required_fields: list[str] = [
            enc.x_field, enc.y_field, enc.label_field, enc.value_field,
        ]
        for opt_field in (enc.y2_field, enc.series_field, enc.color_field):
            if opt_field is not None:
                required_fields.append(opt_field)

        for i, row in enumerate(self.data):
            missing = [f for f in required_fields if f not in row]
            if missing:
                raise ValueError(
                    f"data[{i}] is missing fields required by Encoding: {missing}"
                )

        # 4. value-type guard: value_field must contain int/float in every row
        for i, row in enumerate(self.data):
            raw = row.get(enc.value_field)
            if raw is not None and not isinstance(raw, (int, float)):
                raise ValueError(
                    f"data[{i}]['{enc.value_field}'] must be int or float, "
                    f"got {type(raw).__name__!r}: {raw!r}"
                )

        # 5. base_year required iff real_nominal == "real"
        if enc.real_nominal == "real" and enc.base_year is None:
            raise ValueError(
                "Encoding.base_year is required when real_nominal='real'"
            )

        # 6. diverging_domain required iff chart_type == "diverging"
        if self.chart_type == "diverging" and self.opts.diverging_domain is None:
            raise ValueError(
                "RenderOpts.diverging_domain is required for chart_type='diverging'"
            )

        return self
