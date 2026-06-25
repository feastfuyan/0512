"""
render_paper.py — Unified publication-quality renderer for FigureSpec.

Exports
-------
figure_spec_to_vegalite(fs: FigureSpec) -> dict
    Pure function: FigureSpec → Vega-Lite v5 JSON dict.
    No vl-convert import — fully testable offline.

render_figure(fs: FigureSpec) -> dict
    Calls vl-convert to produce SVG + optional PDF/PNG.
    Returns: {"svg": str, "pdf": bytes|None, "png": bytes|None}

render_paper(fs: FigureSpec) -> dict
    Deprecated alias for render_figure. Kept for backward compatibility.

normalize_svg(svg: str) -> str
    Normalise a rendered SVG for golden-test assertions.

All 16 chart types are available via this renderer regardless of document type.
Theme is controlled by fs.opts.theme ("lynai" or "nature").
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from figure_spec import FigureSpec
from profiles.nature_paper import (
    VEGALITE_SCHEMA,
    VEGALITE_CONFIG,
    WIDTH_89MM,
    WIDTH_183MM,
    HEIGHT_RATIO,
    COLOR_SCHEME_CATEGORICAL,
)

# LynAI report palette constants (from profiles/lynai_report.py)
_LYNAI_NAVY = "#1F3864"
_LYNAI_TEAL = "#14b8a6"
_LYNAI_FONT = "Inter, Liberation Sans, Arial, sans-serif"


# ---------------------------------------------------------------------------
# Dimension resolver
# ---------------------------------------------------------------------------

def _resolve_width(dimensions: str) -> int:
    """Map dimension string → pixel width."""
    if dimensions in ("paper-89mm", "89mm"):
        return WIDTH_89MM
    if dimensions in ("paper-183mm", "183mm"):
        return WIDTH_183MM
    # "report-wide"
    return 1040


# ---------------------------------------------------------------------------
# Theme config builder
# ---------------------------------------------------------------------------

def _build_config(theme: str) -> dict:
    """Return a Vega-Lite config block for the requested theme."""
    if theme == "lynai":
        cfg = copy.deepcopy(VEGALITE_CONFIG)
        # Override palette to LynAI navy/teal
        cfg["mark"] = {"color": _LYNAI_TEAL}
        cfg["axis"] = {
            **cfg.get("axis", {}),
            "labelFont": _LYNAI_FONT,
            "titleFont": _LYNAI_FONT,
            "domainColor": _LYNAI_NAVY,
            "tickColor": _LYNAI_NAVY,
        }
        cfg["title"] = {
            **cfg.get("title", {}),
            "font": _LYNAI_FONT,
            "color": _LYNAI_NAVY,
        }
        cfg["range"] = {
            "category": [_LYNAI_TEAL, "#14532d", "#1e40af", "#7c2d12", "#6b21a8"],
        }
        return cfg
    # Default: nature profile
    return copy.deepcopy(VEGALITE_CONFIG)


# ---------------------------------------------------------------------------
# Encoding channel mapping
# ---------------------------------------------------------------------------

def _mark_type(chart_type: str) -> str:
    """Map FigureSpec chart_type to Vega-Lite mark type."""
    _MAP = {
        "horizontal-bar": "bar",
        "vertical-bar": "bar",
        "line": "line",
        "area": "area",
        "scatter": "point",
        "grouped-bar": "bar",
        "stacked-bar": "bar",
        "diverging": "bar",
        "waterfall": "bar",
        "tornado": "bar",
        "resource-classification-stack": "bar",
        "grade-tonnage": "line",
        "production-profile": "area",
        "cost-curve": "line",
        "risk-matrix": "rect",
        "traffic-light-scorecard": "rect",
    }
    return _MAP.get(chart_type, "point")


def _infer_data_type(values: list[Any]) -> str:
    """Infer Vega-Lite data type from sample values."""
    non_none = [v for v in values if v is not None]
    if not non_none:
        return "nominal"
    sample = non_none[0]
    if isinstance(sample, bool):
        return "nominal"
    if isinstance(sample, (int, float)):
        return "quantitative"
    return "nominal"


# ---------------------------------------------------------------------------
# Pure compile: FigureSpec → Vega-Lite dict
# ---------------------------------------------------------------------------

def figure_spec_to_vegalite(fs: FigureSpec) -> dict:
    """
    Pure compile: FigureSpec → Vega-Lite v5 JSON dict.

    Determinism rule (I10): this function is pure — no side effects, no randomness.
    Injects encoding.<x>.sort = None (null) to disable Vega's implicit axis
    reordering, ensuring data order is preserved as-supplied.

    All 16 chart types are supported. Theme is applied via fs.opts.theme.
    """
    opts = fs.opts

    # -- Dimensions ----------------------------------------------------------
    width = _resolve_width(opts.dimensions)
    height = int(width * HEIGHT_RATIO)

    # -- Data ----------------------------------------------------------------
    vl_data = {"values": fs.data}

    # -- Mark ----------------------------------------------------------------
    mark_type = _mark_type(fs.chart_type)

    # -- Encoding channels ---------------------------------------------------
    enc = fs.encoding
    data_values_x = [row.get(enc.x_field) for row in fs.data]
    data_values_y = [row.get(enc.y_field) for row in fs.data]

    x_type = _infer_data_type(data_values_x)
    y_type = _infer_data_type(data_values_y)

    # Build x channel — inject sort=None to disable implicit reordering (I10)
    x_channel: dict = {
        "field": enc.x_field,
        "type": x_type,
        "title": enc.x_title,
        "sort": None,
    }
    if enc.scale_x == "log":
        x_channel["scale"] = {"type": "log"}

    # Build y channel
    y_channel: dict = {
        "field": enc.y_field,
        "type": y_type,
        "title": enc.y_title,
        "sort": None,
    }
    if enc.scale_y == "log":
        y_channel["scale"] = {"type": "log"}

    encoding: dict = {
        "x": x_channel,
        "y": y_channel,
    }

    # Series / color channel
    if enc.series_field:
        encoding["color"] = {
            "field": enc.series_field,
            "type": "nominal",
            "title": enc.legend_title or enc.series_field,
            "scale": {"scheme": COLOR_SCHEME_CATEGORICAL},
        }
    elif enc.color_field:
        color_values = [row.get(enc.color_field) for row in fs.data]
        color_type = _infer_data_type(color_values)
        encoding["color"] = {
            "field": enc.color_field,
            "type": color_type,
            "title": enc.legend_title or enc.color_field,
        }

    # Dual-y axis (y2_field)
    if enc.y2_field:
        encoding["y2"] = {
            "field": enc.y2_field,
            "type": "quantitative",
            "title": enc.y2_title or enc.y2_field,
        }

    # -- Title ---------------------------------------------------------------
    title_block: dict = {
        "text": fs.title,
        "anchor": "start",
    }

    # -- Description (for traceability) -------------------------------------
    description = f"{fs.claim} | Source: {fs.source_note}"

    # -- Config (theme-aware) -----------------------------------------------
    config = _build_config(opts.theme)

    # -- Assemble spec -------------------------------------------------------
    spec: dict = {
        "$schema": VEGALITE_SCHEMA,
        "description": description,
        "title": title_block,
        "width": width,
        "height": height,
        "data": vl_data,
        "mark": {"type": mark_type, "tooltip": True},
        "encoding": encoding,
        "config": config,
    }

    return spec


# ---------------------------------------------------------------------------
# Render (env-gated, lazy import of vl_convert)
# ---------------------------------------------------------------------------

def render_figure(fs: FigureSpec) -> dict:
    """
    Render a FigureSpec to SVG + optional PDF/PNG via vl-convert.

    All 16 chart types supported. Theme controlled by fs.opts.theme.

    Returns
    -------
    dict with keys:
        "svg"  : str   — rendered SVG markup
        "pdf"  : bytes | None
        "png"  : bytes | None

    Raises
    ------
    RuntimeError
        If vl_convert is not installed.
    """
    try:
        import vl_convert as vlc  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "vl-convert is not installed.  The figure renderer requires "
            "'vl-convert-python' (Rust wheel with embedded Vega/Vega-Lite JS).\n"
            "Install it with: pip install vl-convert-python\n"
            "Pin the exact version in requirements-paper.txt for deterministic output.\n"
            "See fonts/README.md for font vendoring instructions."
        ) from exc

    spec_dict = figure_spec_to_vegalite(fs)
    spec_json = json.dumps(spec_dict)

    svg: str = vlc.vegalite_to_svg(spec_json)

    png: bytes | None = None
    pdf: bytes | None = None
    try:
        png = vlc.vegalite_to_png(spec_json, scale=2)
    except Exception:  # noqa: BLE001
        pass
    try:
        pdf = vlc.vegalite_to_pdf(spec_json)
    except Exception:  # noqa: BLE001
        pass

    return {"svg": svg, "pdf": pdf, "png": png}


# Backward-compatible alias
render_paper = render_figure


# ---------------------------------------------------------------------------
# normalize_svg — for deterministic golden-test assertions
# ---------------------------------------------------------------------------

def normalize_svg(svg: str) -> str:
    """
    Normalise a rendered SVG for golden-test assertions (I10).

    Transformations applied:
    1. Renumber auto-generated clip-path / mask / gradient ids.
    2. Round floating-point coordinate values to 4 decimal places.
    3. Strip vl-convert / Vega metadata comments.
    4. Collapse multiple spaces to single space.
    """
    # -- Step 1: Strip XML/HTML comments ------------------------------------
    result = re.sub(r'<!--.*?-->', '', svg, flags=re.DOTALL)

    # -- Step 2: Renumber auto-generated ids --------------------------------
    AUTO_ID_PAT = re.compile(
        r'id="('
        r'clip-[a-zA-Z0-9_-]*[0-9a-f]{4,}'
        r'|vl_[a-zA-Z0-9_-]+'
        r'|[a-zA-Z_][a-zA-Z0-9_-]*\d{4,}'
        r')"'
    )
    found_ids: list[str] = list(dict.fromkeys(AUTO_ID_PAT.findall(result)))

    id_map: dict[str, str] = {}
    clip_counter = 0
    mask_counter = 0
    grad_counter = 0
    other_counter = 0
    for raw_id in found_ids:
        low = raw_id.lower()
        if "clip" in low:
            id_map[raw_id] = f"clip_{clip_counter}"
            clip_counter += 1
        elif "mask" in low:
            id_map[raw_id] = f"mask_{mask_counter}"
            mask_counter += 1
        elif "grad" in low or "linear" in low or "radial" in low:
            id_map[raw_id] = f"grad_{grad_counter}"
            grad_counter += 1
        else:
            id_map[raw_id] = f"auto_{other_counter}"
            other_counter += 1

    for raw_id, norm_id in id_map.items():
        result = result.replace(f'id="{raw_id}"', f'id="{norm_id}"')
        result = result.replace(f'url(#{raw_id})', f'url(#{norm_id})')
        result = result.replace(f'href="#{raw_id}"', f'href="#{norm_id}"')

    # -- Step 3: Round floating-point numbers to 4 decimal places -----------
    def _round_float(match: re.Match) -> str:
        val = float(match.group(0))
        rounded = round(val, 4)
        if rounded == int(rounded):
            return str(int(rounded))
        return f"{rounded:.4f}".rstrip('0')

    FLOAT_PAT = re.compile(r'(?<![#a-zA-Z_-])\b\d+\.\d+\b')
    result = FLOAT_PAT.sub(_round_float, result)

    # -- Step 4: Collapse excess whitespace ---------------------------------
    result = re.sub(r'[ \t]{2,}', ' ', result)
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()
