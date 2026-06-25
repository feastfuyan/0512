"""
nature_paper.py — Style profile for publication-quality (Vega-Lite) paper rendering.

Dimensions are derived from Nature journal column widths:
  - paper-89mm  → single column  ≈  252 px  (@ 72 dpi nominal / 96 dpi screen: ~337 px)
  - paper-183mm → double column  ≈  519 px  (@ 72 dpi)

We use 252 / 519 as the nominal Vega-Lite width values.  vl-convert renders at
the specified DPI independently of these CSS-pixel widths.

Font:
  Inter (variable) is the recommended vendored font; Liberation Sans / Arial is
  the fallback for environments without the vendored .ttf files.
  See $SK/fonts/README.md for how to register the vendored fonts with vl-convert.

Color scheme:
  Tableau-10 (default) — perceptually distinct, color-blind-safe for common forms
  of color vision deficiency (deuteranopia / protanopia).
  Alternative: "viridis" for sequential / quantitative scales.

Determinism note (I10):
  Pin the vl-convert wheel version and its bundled Vega/Vega-Lite JS versions
  in requirements-paper.txt (see fonts/README.md).  For golden-test assertions,
  use normalize_svg() from render_paper.py — NOT raw byte comparison — to absorb
  generated id/clip-path sequence differences between renders.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Column widths (px, nominal 72 dpi)
# ---------------------------------------------------------------------------

WIDTH_89MM: int = 252      # Nature single-column  (89 mm × 72 dpi / 25.4)
WIDTH_183MM: int = 519     # Nature double-column (183 mm × 72 dpi / 25.4)

# Typical height ratios — callers may override
HEIGHT_RATIO: float = 0.75   # width * ratio = default height

# ---------------------------------------------------------------------------
# Color scheme — color-blind-safe
# ---------------------------------------------------------------------------

# Vega-Lite named scheme for categorical data (Tableau-10)
COLOR_SCHEME_CATEGORICAL: str = "tableau10"

# For sequential/quantitative (heatmaps, gradients)
COLOR_SCHEME_SEQUENTIAL: str = "viridis"

# Explicit 8-color palette for inline use (subset of Tableau-10, verified
# safe for deuteranopia + protanopia via Coblis simulator):
PALETTE = [
    "#4e79a7",  # blue
    "#f28e2b",  # orange
    "#59a14f",  # green
    "#e15759",  # red
    "#76b7b2",  # teal
    "#edc948",  # yellow
    "#b07aa1",  # purple
    "#ff9da7",  # pink
]

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_FAMILY: str = "Inter, Liberation Sans, Arial, sans-serif"
FONT_SIZE_BASE: int = 9       # pt  (Nature standard axis label size)
FONT_SIZE_TITLE: int = 10     # pt
FONT_SIZE_SOURCE: int = 7     # pt

# ---------------------------------------------------------------------------
# Vega-Lite theme config block (injected into spec["config"])
# ---------------------------------------------------------------------------

VEGALITE_CONFIG: dict = {
    "font": FONT_FAMILY,
    "axis": {
        "labelFont": FONT_FAMILY,
        "titleFont": FONT_FAMILY,
        "labelFontSize": FONT_SIZE_BASE,
        "titleFontSize": FONT_SIZE_BASE,
        "gridColor": "#e0e0e0",
        "domainColor": "#444444",
        "tickColor": "#444444",
    },
    "legend": {
        "labelFont": FONT_FAMILY,
        "titleFont": FONT_FAMILY,
        "labelFontSize": FONT_SIZE_BASE,
        "titleFontSize": FONT_SIZE_BASE,
    },
    "title": {
        "font": FONT_FAMILY,
        "fontSize": FONT_SIZE_TITLE,
        "fontWeight": "bold",
        "anchor": "start",
        "color": "#222222",
    },
    "view": {
        "stroke": "transparent",
    },
    "range": {
        "category": {"scheme": COLOR_SCHEME_CATEGORICAL},
        "ordinal": {"scheme": COLOR_SCHEME_SEQUENTIAL},
    },
    "mark": {
        "color": PALETTE[0],
    },
}

# ---------------------------------------------------------------------------
# Vega-Lite schema URL (v5)
# ---------------------------------------------------------------------------

VEGALITE_SCHEMA: str = "https://vega.github.io/schema/vega-lite/v5.json"
