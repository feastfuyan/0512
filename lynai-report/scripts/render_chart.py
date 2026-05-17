#!/usr/bin/env python3
"""
render_chart.py — LynAI Institutional Chart Renderer
====================================================

Converts a chart_spec (JSON) + data into a publication-grade PNG at 300 DPI,
applying the house style automatically.

Usage:
    python render_chart.py --spec chart_specs.json --out charts/

The chart_specs.json is a list of spec objects produced by the Chart-Smith agent.
Each spec follows this schema:

{
  "id": "chart_03",
  "type": "line" | "bar" | "barh" | "stacked_bar" | "area" | "scatter" |
          "histogram" | "boxplot" | "waterfall" | "dual_axis",
  "title": "Lithium demand outpaces supply through 2028E",
  "subtitle": "Optional descriptive subtitle",
  "x": { "label": "Year", "data": [2020, 2021, ...], "is_forecast_from": 2026 },
  "y": { "label": "Demand (kt LCE)", "start_at_zero": true },
  "series": [
    { "name": "Demand", "data": [..], "color_role": "primary" },
    { "name": "Supply", "data": [..], "color_role": "accent" }
  ],
  "annotations": [
    { "x": 2024, "y": 1450, "text": "China stimulus", "direction": "up" }
  ],
  "source_line": "Source: USGS MCS 2026; LynAI Research analysis",
  "width_in": 6.0,
  "height_in": 3.7
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

# ----- Locate house style ----------------------------------------------------

HERE = Path(__file__).resolve().parent
STYLE_FILE = HERE.parent / "templates" / "chart_style.mplstyle"
TOKENS_FILE = HERE.parent / "templates" / "house_style.json"

if not STYLE_FILE.exists():
    sys.exit(f"FATAL: chart style not found at {STYLE_FILE}")
if not TOKENS_FILE.exists():
    sys.exit(f"FATAL: house style tokens not found at {TOKENS_FILE}")

plt.style.use(str(STYLE_FILE))

with open(TOKENS_FILE) as f:
    TOKENS = json.load(f)

PALETTE = TOKENS["chart"]["series_palette"]   # list of hex (no #)
NEG_COLOR = "#" + TOKENS["chart"]["negative_color"]
POS_COLOR = "#" + TOKENS["chart"]["positive_color"]
GRIDLINE  = "#" + TOKENS["chart"]["gridline_color"]
AXIS_GREY = "#" + TOKENS["chart"]["axis_color"]
NAVY      = "#" + TOKENS["palette"]["primary_navy"]
GOLD      = "#" + TOKENS["palette"]["accent_gold"]


# ----- Helpers ---------------------------------------------------------------

def _color_for(role: str | None, index: int) -> str:
    """Map a color role or fall back to the palette by index."""
    roles = {
        "primary": NAVY,
        "accent":  GOLD,
        "support_steel": "#" + TOKENS["palette"]["support_steel"],
        "support_olive": "#" + TOKENS["palette"]["support_olive"],
        "support_slate": "#" + TOKENS["palette"]["support_slate"],
    }
    if role and role in roles:
        return roles[role]
    return "#" + PALETTE[index % len(PALETTE)]


def _setup_axes(ax, spec: dict[str, Any]) -> None:
    """Apply common house axis discipline.

    For 'barh' charts the value axis is x, not y, so axis-handling is mirrored.
    """
    is_barh = spec.get("type") == "barh"
    y_spec = spec.get("y", {})
    x_spec = spec.get("x", {})

    # For barh: y holds value-axis metadata, x holds category labels (already set)
    if is_barh:
        # y_spec.label is actually the value-axis label → goes on x-axis
        if y_spec.get("label"):
            ax.set_xlabel(y_spec["label"])
        # x_spec.label is the category dimension name → goes on y-axis
        if x_spec.get("label"):
            ax.set_ylabel(x_spec["label"])
        # Force x to start at 0 if requested
        if y_spec.get("start_at_zero", True):
            xmin, xmax = ax.get_xlim()
            ax.set_xlim(min(0, xmin), xmax)
        # Gridlines on x only (the value axis)
        ax.xaxis.grid(True, color=GRIDLINE, linewidth=0.5, zorder=0)
        ax.yaxis.grid(False)
    else:
        if y_spec.get("label"):
            ax.set_ylabel(y_spec["label"])
        if x_spec.get("label"):
            ax.set_xlabel(x_spec["label"])
        # Y axis starts at 0 unless explicitly told otherwise
        if y_spec.get("start_at_zero", True):
            ymin, ymax = ax.get_ylim()
            ax.set_ylim(min(0, ymin), ymax)
        # Horizontal-only gridlines
        ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.5, zorder=0)
        ax.xaxis.grid(False)

    ax.set_axisbelow(True)

    # Optional forecast separator (only meaningful for time-axis charts)
    forecast_from = x_spec.get("is_forecast_from")
    if forecast_from is not None and not is_barh:
        ax.axvline(x=forecast_from - 0.5, color=AXIS_GREY,
                   linewidth=0.5, linestyle=":", zorder=0)

    # Percent formatting if label hints at it
    value_label = (y_spec.get("label") or "").lower()
    if "%" in value_label or "percent" in value_label or "share" in value_label:
        if is_barh:
            ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
        else:
            ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))


def _apply_annotations(ax, spec: dict[str, Any]) -> None:
    """Add GS-style inflection annotations. Auto-redirect 'up' annotations to
    side when the data point is near the top of the y-range, to avoid title
    collision."""
    ymin, ymax = ax.get_ylim()
    yrange = ymax - ymin if ymax > ymin else 1
    for ann in spec.get("annotations", []):
        x, y, text = ann["x"], ann["y"], ann["text"]
        direction = ann.get("direction", "up")
        # Auto-redirect: if 'up' but point is in top 15% of y-range, use 'left' instead
        if direction == "up" and (y - ymin) / yrange > 0.85:
            direction = "left"
        if direction == "up":
            xytext = (0, 28)
            arrowstyle = "->"
        elif direction == "down":
            xytext = (0, -32)
            arrowstyle = "->"
        else:  # "right" or "left"
            sign = 1 if direction == "right" else -1
            xytext = (40 * sign, 0)
            arrowstyle = "->"

        ax.annotate(
            text,
            xy=(x, y),
            xytext=xytext,
            textcoords="offset points",
            fontsize=8,
            color=NAVY,
            ha="center",
            arrowprops=dict(arrowstyle=arrowstyle,
                            color=NAVY, lw=0.7,
                            shrinkA=2, shrinkB=2),
        )


def _add_source_line(fig, ax, spec: dict[str, Any]) -> None:
    """Bottom-left source attribution at 7pt grey."""
    text = spec.get("source_line", "Source: LynAI Research")
    fig.text(0.01, 0.005, text,
             fontsize=7, color=AXIS_GREY,
             ha="left", va="bottom",
             style="italic")


def _add_title_block(fig, spec: dict[str, Any]) -> None:
    """Title (finding) on top, optional subtitle below in lighter style."""
    title = spec["title"]
    subtitle = spec.get("subtitle")

    fig.text(0.01, 0.97, title,
             fontsize=10, fontweight="bold",
             color=NAVY, ha="left", va="top")
    if subtitle:
        fig.text(0.01, 0.93, subtitle,
                 fontsize=9, color=AXIS_GREY,
                 ha="left", va="top", style="italic")


# ----- Per-chart-type renderers ---------------------------------------------

def _render_line(ax, spec):
    x = spec["x"]["data"]
    for i, series in enumerate(spec["series"]):
        ax.plot(x, series["data"],
                color=_color_for(series.get("color_role"), i),
                linewidth=1.8,
                label=series["name"],
                marker=series.get("marker"),
                markersize=4.5)
    if len(spec["series"]) > 1:
        ax.legend(loc="best", frameon=False)


def _render_bar(ax, spec):
    x = spec["x"]["data"]
    n_series = len(spec["series"])
    width = 0.8 / max(n_series, 1)
    x_idx = np.arange(len(x))
    for i, series in enumerate(spec["series"]):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(x_idx + offset, series["data"],
               width=width,
               color=_color_for(series.get("color_role"), i),
               label=series["name"],
               edgecolor="none")
    ax.set_xticks(x_idx)
    ax.set_xticklabels(x)
    if n_series > 1:
        ax.legend(loc="best", frameon=False)


def _render_barh(ax, spec):
    """Horizontal bar — preferred for category names."""
    x = spec["x"]["data"]    # category labels
    n_series = len(spec["series"])
    height = 0.8 / max(n_series, 1)
    y_idx = np.arange(len(x))
    for i, series in enumerate(spec["series"]):
        offset = (i - (n_series - 1) / 2) * height
        ax.barh(y_idx + offset, series["data"],
                height=height,
                color=_color_for(series.get("color_role"), i),
                label=series["name"],
                edgecolor="none")
    ax.set_yticks(y_idx)
    ax.set_yticklabels(x)
    ax.invert_yaxis()
    if n_series > 1:
        ax.legend(loc="best", frameon=False)


def _render_stacked_bar(ax, spec):
    x = spec["x"]["data"]
    x_idx = np.arange(len(x))
    bottom = np.zeros(len(x))
    for i, series in enumerate(spec["series"]):
        data = np.array(series["data"])
        ax.bar(x_idx, data,
               bottom=bottom,
               color=_color_for(series.get("color_role"), i),
               label=series["name"],
               edgecolor="none",
               width=0.7)
        bottom += data
    ax.set_xticks(x_idx)
    ax.set_xticklabels(x)
    ax.legend(loc="best", frameon=False)


def _render_area(ax, spec):
    x = spec["x"]["data"]
    for i, series in enumerate(spec["series"]):
        color = _color_for(series.get("color_role"), i)
        ax.fill_between(x, series["data"],
                        color=color, alpha=0.25,
                        label=series["name"])
        ax.plot(x, series["data"], color=color, linewidth=1.8)
    if len(spec["series"]) > 1:
        ax.legend(loc="best", frameon=False)


def _render_scatter(ax, spec):
    for i, series in enumerate(spec["series"]):
        color = _color_for(series.get("color_role"), i)
        ax.scatter(series["x"], series["y"],
                   color=color, s=24, alpha=0.85,
                   edgecolor="none",
                   label=series["name"])
    if len(spec["series"]) > 1:
        ax.legend(loc="best", frameon=False)


def _render_waterfall(ax, spec):
    """Bridge chart for value walks."""
    labels = spec["x"]["data"]
    values = spec["series"][0]["data"]
    cumulative = 0
    for i, (label, val) in enumerate(zip(labels, values)):
        color = NAVY if val >= 0 else NEG_COLOR
        if i == 0 or i == len(labels) - 1:
            ax.bar(i, val, color=NAVY, edgecolor="none")
            cumulative = val if i == 0 else cumulative
        else:
            ax.bar(i, val, bottom=cumulative,
                   color=color, edgecolor="none")
            cumulative += val
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right")


_RENDERERS = {
    "line":         _render_line,
    "bar":          _render_bar,
    "barh":         _render_barh,
    "stacked_bar":  _render_stacked_bar,
    "area":         _render_area,
    "scatter":      _render_scatter,
    "waterfall":    _render_waterfall,
}


# ----- Top-level entry -------------------------------------------------------

# v1.4.2 D-16 P1-5: whitelist chart IDs to defeat path-traversal injection (red-team M2)
import re as _re
_CHART_ID_RE = _re.compile(r"^chart_[a-z0-9_]{1,60}$")


def render_chart(spec: dict[str, Any], out_dir: Path) -> Path:
    """Render a single chart spec to a PNG file. Returns the file path."""
    # v1.4.2 D-16 P1-5: chart id sandbox — no path traversal, no shell special chars
    cid = spec.get("id", "")
    if not _CHART_ID_RE.match(cid):
        raise ValueError(f"INVALID_CHART_ID: {cid!r} must match {_CHART_ID_RE.pattern}")

    width  = spec.get("width_in", 6.0)
    height = spec.get("height_in", 3.7)
    fig, ax = plt.subplots(figsize=(width, height), dpi=300)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.86, bottom=0.13)

    chart_type = spec["type"]
    if chart_type not in _RENDERERS:
        raise ValueError(f"Unsupported chart type: {chart_type}. "
                         f"Supported: {sorted(_RENDERERS)}")
    _RENDERERS[chart_type](ax, spec)

    _setup_axes(ax, spec)
    _apply_annotations(ax, spec)
    _add_title_block(fig, spec)
    _add_source_line(fig, ax, spec)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{spec['id']}.png"
    fig.savefig(out_path, dpi=300, facecolor="white", bbox_inches="tight",
                pad_inches=0.08)
    plt.close(fig)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render LynAI institutional charts")
    parser.add_argument("--spec", required=True,
                        help="Path to chart_specs.json (list of specs)")
    parser.add_argument("--out", required=True,
                        help="Output directory for PNGs")
    args = parser.parse_args()

    with open(args.spec) as f:
        specs = json.load(f)

    out_dir = Path(args.out)
    results = []
    for spec in specs:
        try:
            path = render_chart(spec, out_dir)
            results.append({"id": spec["id"], "status": "ok", "path": str(path)})
            print(f"[ok]  {spec['id']:20s} -> {path}")
        except Exception as exc:
            results.append({"id": spec["id"], "status": "error",
                            "error": str(exc)})
            print(f"[err] {spec['id']:20s} -> {exc}", file=sys.stderr)

    # Write index
    with open(out_dir / "render_log.json", "w") as f:
        json.dump(results, f, indent=2)

    n_err = sum(1 for r in results if r["status"] != "ok")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
