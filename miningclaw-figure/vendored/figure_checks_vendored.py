# VENDORED from report_service.runtime.quality.figure_checks @ 3c15840;
# kept in parity via parity.py + golden corpus. DO NOT edit logic.
#
# This file is a faithful copy of the product figure-quality functions
# (extract_figures, score_figure_deterministic, Figure, and helpers).
# It imports chart_registry and rubric from the product modules via the
# sys.path set by the test harness (or by parity.load_product_module).
# Purpose: allows figure_lint.py to run vendored dims independently of
# the full product service, while parity tests confirm byte-for-byte
# output agreement against the live product.

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from report_service.runtime.quality.chart_registry import CHART_WRAPPER_CLASSES, chart_kind_for_classes
from report_service.runtime.quality.rubric import FIGURE_DIMENSIONS, QUALITY_FLOOR

_VIEWBOX_RE = re.compile(r'viewBox="0 0 ([\d.]+) ([\d.]+)"')
_TEXT_X_RE = re.compile(r'<text x="([\d.]+)"')
_G_TRANSLATE_RE = re.compile(r'translate\(([\d.]+),')
_RECT_W_RE = re.compile(r'<rect[^>]*width="([\d.]+)"')
_TITLE_RE = re.compile(r'<div[^>]*>([^<]+)</div>\s*<svg', re.DOTALL)

_VALUE_LABEL_FULL_RE = re.compile(
    r'<text\s[^>]*\bx="([\d.]+)"[^>]*>\s*([\d][\d,]*(?:\.[\d]+)?\s*(?:\([^)]*\)|%|/[^<]*|x\b)?[^<]*?)\s*</text>',
    re.DOTALL,
)
_VALUE_CONTENT_RE = re.compile(
    r'^([\d][\d,]*(?:\.[\d]+)?)\s*(?=\(|%|/|x\b|\s*$)',
)
_RECT_FILL_RE = re.compile(r'<rect\b([^>]*)/?>', re.IGNORECASE)
_FILL_ATTR_RE = re.compile(r'\bfill="([^"]*)"', re.IGNORECASE)
_WIDTH_ATTR_RE = re.compile(r'\bwidth="([\d.]+)"')
_BG_FILL = "#f1f5f9"

_DECIMAL_UNIT_RE = re.compile(
    r'^([\d][\d,]*(?:\.[\d]+)?)\s*(?:\([^)]*\)|%|/[^<]*|x\b|[A-Za-z][^<]*|)\s*$'
)


@dataclass(frozen=True)
class Figure:
    fig_id: str
    title: str
    svg: str
    viewbox_w: float
    chart_kind: str
    raw_block: str


class _AttrParser(HTMLParser):
    """Minimal parser to extract attributes from a single opening tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attrs = {k: (v or "") for k, v in attrs}


def _parse_attrs(tag_html: str) -> dict[str, str]:
    """Return attribute dict for the first opening tag in *tag_html*."""
    p = _AttrParser()
    p.feed(tag_html)
    return p.attrs


_DIV_TAG_RE = re.compile(r'(<div\b[^>]*>)|</div>', re.IGNORECASE | re.DOTALL)


def _find_chart_divs(html: str) -> list[tuple[str, dict[str, str]]]:
    """Return (outer_html, attrs) for every div whose class contains a wrapper class."""
    results: list[tuple[str, dict[str, str]]] = []
    stack: list[tuple[int, int, dict[str, str], bool]] = []
    depth = 0

    for m in _DIV_TAG_RE.finditer(html):
        if m.group(1) is not None:
            open_start = m.start()
            attrs = _parse_attrs(m.group(1))
            classes = set((attrs.get("class") or "").split())
            is_wrapper = bool(classes & CHART_WRAPPER_CLASSES)
            stack.append((open_start, depth, attrs, is_wrapper))
            depth += 1
        else:
            depth -= 1
            if stack:
                open_start, open_depth, attrs, is_wrapper = stack[-1]
                if depth == open_depth:
                    stack.pop()
                    if is_wrapper:
                        close_end = m.end()
                        outer_html = html[open_start:close_end]
                        results.append((outer_html, attrs))

    return results


def extract_figures(html: str) -> list[Figure]:
    """Return one Figure per chart wrapper div found in *html*."""
    figs: list[Figure] = []
    for i, (outer_html, attrs) in enumerate(_find_chart_divs(html)):
        fig_id = attrs.get("id") or f"fig-{i}"

        vb = _VIEWBOX_RE.search(outer_html)
        viewbox_w = float(vb.group(1)) if vb else 0.0

        svg_match = re.search(r'<svg[\s\S]*?</svg>', outer_html, re.IGNORECASE)
        svg = svg_match.group(0) if svg_match else ""

        title = ""
        tm = _TITLE_RE.search(outer_html)
        if tm:
            title = tm.group(1).strip()

        classes = set((attrs.get("class") or "").split())
        kind = chart_kind_for_classes(classes) or "unknown"

        figs.append(
            Figure(
                fig_id=fig_id,
                title=title,
                svg=svg,
                viewbox_w=viewbox_w,
                chart_kind=kind,
                raw_block=outer_html,
            )
        )
    return figs


def _extract_value_labels(svg: str) -> list[tuple[float, float, str]]:
    """Return (text_x, value, full_text_content) for every VALUE-LABEL <text> in the SVG."""
    results = []
    for m in _VALUE_LABEL_FULL_RE.finditer(svg):
        x_val = float(m.group(1))
        if x_val <= 150:
            continue
        full_text = m.group(2).strip()
        vm = _VALUE_CONTENT_RE.match(full_text)
        if vm:
            numeric = float(vm.group(1).replace(",", ""))
            results.append((x_val, numeric, full_text))
    return results


def _extract_value_bar_widths(svg: str) -> list[float]:
    """Return widths of VALUE bars only, identified by fill colour."""
    rects: list[tuple[str | None, float | None]] = []
    any_fill = False

    for m in _RECT_FILL_RE.finditer(svg):
        attrs_str = m.group(1)
        fill_m = _FILL_ATTR_RE.search(attrs_str)
        fill: str | None = None
        if fill_m:
            fill = fill_m.group(1).strip().lower() or None
            if fill:
                any_fill = True
        width_m = _WIDTH_ATTR_RE.search(attrs_str)
        w = float(width_m.group(1)) if width_m else None
        rects.append((fill, w))

    if any_fill:
        from collections import Counter
        fill_counts: Counter[str] = Counter(
            f for (f, _) in rects if f and f != _BG_FILL.lower()
        )
        if not fill_counts:
            return []
        value_fill = fill_counts.most_common(1)[0][0]
        return [
            w for (fill, w) in rects
            if fill == value_fill and w is not None
        ]
    else:
        all_widths = [w for (_, w) in rects if w is not None]
        return all_widths[1::2]


def _value_label_right_edges(svg: str, viewbox_w: float) -> list[float]:
    """Return estimated right-edge x (absolute) for each VALUE-LABEL <text>."""
    g_offsets: list[float] = []
    g_positions: list[int] = []
    for gm in re.finditer(r'<g\b[^>]*transform\s*=\s*"[^"]*translate\(([\d.]+)', svg):
        g_offsets.append(float(gm.group(1)))
        g_positions.append(gm.start())

    edges = []
    for tm in _VALUE_LABEL_FULL_RE.finditer(svg):
        x_val = float(tm.group(1))
        if x_val <= 150:
            continue

        full_text = tm.group(2).strip()
        if not (_VALUE_CONTENT_RE.match(full_text) or _DECIMAL_UNIT_RE.match(full_text)):
            continue

        pos = tm.start()
        g_x = 0.0
        for gi, gp in enumerate(g_positions):
            if gp < pos:
                g_x = g_offsets[gi]
            else:
                break

        fs_m = re.search(r'font-size="(\d+)"', tm.group(0))
        font_size = float(fs_m.group(1)) if fs_m else 12.0

        right_edge = g_x + x_val + len(full_text) * font_size * 0.62
        edges.append(right_edge)

    return edges


def detect_duplicate_geometry(figures: list[Figure]) -> list[int]:
    """Return indices of figures whose value-bar geometry duplicates an earlier figure's."""
    seen: list[tuple[tuple[float, ...], str]] = []
    duplicates: list[int] = []

    for idx, fig in enumerate(figures):
        bars = tuple(_extract_value_bar_widths(fig.svg))
        if not bars:
            seen.append((bars, fig.title))
            continue

        for prev_bars, prev_title in seen:
            if bars == prev_bars and fig.title != prev_title:
                duplicates.append(idx)
                break

        seen.append((bars, fig.title))

    return duplicates


def score_figure_deterministic(
    fig: Figure, *, model_values: list[float] | None = None, is_duplicate: bool = False
) -> dict[str, float]:
    scores: dict[str, float] = {d: QUALITY_FLOOR for d in FIGURE_DIMENSIONS}

    if is_duplicate:
        scores["data_viz_integrity"] = 0.0
        return scores

    kind = fig.chart_kind
    if kind == "horizontal-bar":
        return _score_horizontal_bar(fig, scores, model_values=model_values)
    elif kind == "diverging-html-bar":
        return _score_diverging_html_bar(fig, scores)
    else:
        return scores


def _extract_value_labels_extended(svg: str) -> list[tuple[float, float, str]]:
    """Like _extract_value_labels but also handles decimal+unit labels ("12.5 Mt")."""
    results = []
    for m in _VALUE_LABEL_FULL_RE.finditer(svg):
        x_val = float(m.group(1))
        if x_val <= 150:
            continue
        full_text = m.group(2).strip()

        vm = _VALUE_CONTENT_RE.match(full_text)
        if vm:
            numeric = float(vm.group(1).replace(",", ""))
            results.append((x_val, numeric, full_text))
            continue

        dm = _DECIMAL_UNIT_RE.match(full_text)
        if dm:
            numeric = float(dm.group(1).replace(",", ""))
            results.append((x_val, numeric, full_text))

    return results


def _score_horizontal_bar(
    fig: Figure,
    scores: dict[str, float],
    *,
    model_values: list[float] | None = None,
) -> dict[str, float]:
    """Score a horizontal-bar chart (chart-block or mc-bar-chart wrapper)."""
    if not fig.svg:
        for d in FIGURE_DIMENSIONS:
            scores[d] = QUALITY_FLOOR
        return scores

    has_title = bool(fig.title)
    has_text = bool(_TEXT_X_RE.search(fig.svg))
    if not (has_title and has_text):
        scores["labeling"] = 0.0

    _OVERFLOW_TOLERANCE_PX = 50.0
    if fig.viewbox_w:
        right_edges = _value_label_right_edges(fig.svg, fig.viewbox_w)
        if right_edges and max(right_edges) > fig.viewbox_w + _OVERFLOW_TOLERANCE_PX:
            scores["layout_integrity"] = 0.0

    if model_values:
        value_bars = _extract_value_bar_widths(fig.svg)
        if value_bars and max(model_values) > 0:
            vmax = max(model_values)
            wmax = max(value_bars) or 1.0
            for w, v in zip(value_bars, model_values):
                if abs((w / wmax) - (v / vmax)) > 0.02:
                    scores["data_viz_integrity"] = 0.0
                    break
    else:
        value_label_entries = _extract_value_labels_extended(fig.svg)
        value_bars = _extract_value_bar_widths(fig.svg)

        if value_bars:
            parsed_values = [v for (_, v, _) in value_label_entries]

            if len(parsed_values) != len(value_bars):
                scores["data_viz_integrity"] = 0.0
            elif not parsed_values or max(parsed_values) == 0:
                scores["data_viz_integrity"] = 0.0
            else:
                vmax = max(parsed_values)
                wmax = max(value_bars) or 1.0
                for w, v in zip(value_bars, parsed_values):
                    if abs((w / wmax) - (v / vmax)) > 0.02:
                        scores["data_viz_integrity"] = 0.0
                        break

    return scores


def _score_diverging_html_bar(
    fig: Figure,
    scores: dict[str, float],
) -> dict[str, float]:
    """Score an mc-08 diverging sentiment chart (bar-track wrapper)."""
    if not fig.svg:
        return scores

    has_title = bool(fig.title)
    has_caption = bool(re.search(r'<div[^>]*>[^<]{5,}</div>', fig.raw_block or ""))
    if not (has_title or has_caption):
        scores["labeling"] = 0.0

    vb_match = _VIEWBOX_RE.search(fig.svg)
    if vb_match:
        vb_w = float(vb_match.group(1))
        if vb_w != 520.0:
            return scores
    else:
        return scores

    rect_widths: list[float] = []
    for rm in _RECT_FILL_RE.finditer(fig.svg):
        attrs_str = rm.group(1)
        width_m = _WIDTH_ATTR_RE.search(attrs_str)
        if width_m:
            w = float(width_m.group(1))
            if w > 0:
                rect_widths.append(w)

    _SENTIMENT_FLOAT_RE = re.compile(
        r'<text\s[^>]*\bx="([\d.]+)"[^>]*>\s*(-?[\d]+\.[\d]{2})\s*</text>'
    )
    sentiment_values: list[float] = []
    for sm in _SENTIMENT_FLOAT_RE.finditer(fig.svg):
        x_val = float(sm.group(1))
        if x_val > 130:
            val = float(sm.group(2))
            sentiment_values.append(val)

    if rect_widths and sentiment_values and len(rect_widths) == len(sentiment_values):
        max_w = 320.0
        for bar_w, val in zip(rect_widths, sentiment_values):
            if not (-1.0 <= val <= 1.0):
                scores["layout_integrity"] = 0.0
                scores["data_viz_integrity"] = 0.0
                break
            expected_w = max(0.0, (val + 1) / 2 * max_w)
            if expected_w > 0 and abs((bar_w - expected_w) / max(expected_w, 1.0)) > 0.02:
                scores["data_viz_integrity"] = 0.0
                break
            if 130 + bar_w > 520:
                scores["layout_integrity"] = 0.0
    elif rect_widths and not sentiment_values:
        pass

    return scores


__all__ = [
    "Figure",
    "extract_figures",
    "score_figure_deterministic",
    "detect_duplicate_geometry",
]
