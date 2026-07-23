/**
 * render_product_svg.mjs — deterministic SVG renderer for macro FigureSpec
 *
 * exports renderFigure(spec) → svgString
 *
 * Renderers:
 *   horizontal-bar    — port of Python render_product_svg.py (mc-06 style)
 *   multi-series-line — macro chart1 (PMI line, multiple series over shared X)
 *   grouped-bar       — macro chart2 (CPI grouped bar, one bar-pair per group)
 *   signed-bar        — macro chart3/4/5 (WoW/YTD signed %: negatives valid,
 *                        zero-line mandatory, fail-closed on empty/non-finite)
 *
 * Security contract:
 *   - EVERY label/title/source_note/axis/legend text interpolation goes through esc()
 *   - fig_id attributes go through escAttr() (defense-in-depth; also validated by FigureSpec)
 *   - Geometry rounded to 2dp for byte-stability (matches render_product_svg.py fix #5)
 *
 * viewBox resolution:
 *   Full-width  charts: 1040×360  → deviceScaleFactor 2 → PNG 2080×720  (≥2080×1280 fails for HF)
 *   Two-column charts:  1040×640  → deviceScaleFactor 2 → PNG 2080×1280 (exactly meets threshold)
 *
 *   NOTE: The ≥2080×1280 gate requires AT LEAST 1040×640 SVG @ 2×.
 *   This renderer uses 1040×640 (HH) for all chart types by default,
 *   so any 2× raster meets the ≥2080×1280 threshold.
 *   Full-width line/bar charts use HH=640 (not HF=360) to satisfy the resolution gate.
 */

import { esc, escAttr, FigureRenderError, formatLabel } from './figure_spec.mjs';
import { t } from '../scripts/lib/i18n.mjs';

// ─────────────────────────────────────────────────
// Dimensions
// SVG canvas: W×HH CSS px; deviceScaleFactor=2 → 2080×1280 physical PNG
// Font-size rule: SVG font-size = target_display_px × 2
//   (e.g. target 12px → font-size="24"; target 8px → font-size="16")
// Padding: P=100 on all sides (consistent across chart types)
// ─────────────────────────────────────────────────
const W  = 1040;
const HH = 640;   // all output chart height (ensures ≥2080×1280 @ 2×)
const P  = 100;   // uniform padding (all sides)

// Style colours (from gen_reference_charts.cjs + style-guide.md)
const C = {
  pri:  '#14b8a6', priD: '#0d9488',
  up:   '#22c55e', dn:   '#ef4444',
  hold: '#94a3b8',
  us:   '#3b82f6', eu:   '#8b5cf6',
  jp:   '#f43f5e', ind:  '#06b6d4',
  au:   '#f59e0b',
  cu:   '#e07b39', al:   '#94a3b8', fe: '#dc2626',
  zn:   '#0891b2', ni:   '#64748b',
  li:   '#8b5cf6', co:   '#2563eb', ree: '#10b981',
  grid: 'rgba(0,0,0,0.05)', axis: '#6b7280',
  txt:  '#374151', light: '#6b7280',
};

// Default series colour cycle
const SERIES_COLORS = [C.pri, C.us, C.eu, C.jp, C.ind, C.au, C.cu, C.li, C.co];

// ─────────────────────────────────────────────────
// Geometry helpers (ported from gen_reference_charts.cjs)
// ─────────────────────────────────────────────────

function r2(n) { return Math.round(n * 100) / 100; }

function pxY(v, min, max, h, t, b) {
  return r2(t + (1 - (v - min) / (max - min)) * (h - t - b));
}

function pxX(i, n, l, r) {
  return r2(l + (i / (n - 1)) * (W - l - r));
}

function gridLines(min, max, ticks, h, t, b, l, rr) {
  const step = (max - min) / ticks;
  let out = '';
  for (let i = 0; i <= ticks; i++) {
    const v = min + i * step;
    const y = r2(pxY(v, min, max, h, t, b));
    const label = v % 1 === 0 ? v.toFixed(0) : v.toFixed(1);
    out += `<line x1="${l}" y1="${y}" x2="${W - rr}" y2="${y}" stroke="${C.grid}" stroke-width="0.5"/>`;
    out += `<text x="${l - 8}" y="${r2(y + 5)}" text-anchor="end" font-size="17" fill="${C.light}">${esc(label)}</text>`;
  }
  return out;
}

function zeroLine(min, max, h, t, b, l, rr) {
  const y = r2(pxY(0, min, max, h, t, b));
  return `<line x1="${l}" y1="${y}" x2="${W - rr}" y2="${y}" stroke="${C.axis}" stroke-width="1.5"/>`;
}

function svgWrap(content, h, titleText, sourceNote, lang) {
  const titleEl = `<text x="${W / 2}" y="34" text-anchor="middle" font-size="26" font-weight="600" fill="${C.txt}">${esc(titleText)}</text>`;
  const srcLabel = t("chartSourceLabel", lang);
  const srcEl   = `<text x="${W / 2}" y="${h - 10}" text-anchor="middle" font-size="14" fill="${C.light}">${srcLabel}${esc(sourceNote)}</text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${h}" viewBox="0 0 ${W} ${h}" style="background:#fff;font-family:system-ui,sans-serif">${titleEl}${content}${srcEl}</svg>`;
}

// ─────────────────────────────────────────────────
// Renderer: horizontal-bar (product target)
// Ported from render_product_svg.py
// ─────────────────────────────────────────────────

function renderHorizontalBar(spec) {
  const enc = spec.encoding;
  const vf  = enc.value_field;

  // Fail-closed: no negative magnitudes for horizontal-bar (fix #4 port)
  for (const row of spec.data) {
    const v = row[vf];
    if (v < 0) {
      throw new FigureRenderError(
        `horizontal-bar requires non-negative values; got ${v} in row`
      );
    }
  }

  const sortedData = [...spec.data].sort((a, b) => b[vf] - a[vf]);
  const maxVal = Math.max(...sortedData.map(r => r[vf]));

  const BAR_BG_X    = 180;
  const BAR_BG_Y    = -14;
  const BAR_HEIGHT  = 24;
  const BAR_BG_WIDTH = 720;
  const LABEL_X     = 0;
  const LABEL_Y     = 5;
  const VAL_OFFSET  = 8;
  const RIGHT_MARGIN = 45;

  const numRows  = sortedData.length;
  const svgH     = Math.max(HH, numRows * 42 + 100);

  let groups = '';
  sortedData.forEach((row, i) => {
    const label   = row[enc.label_field];
    const value   = row[vf];
    const barW    = r2(maxVal > 0 ? (value / maxVal) * BAR_BG_WIDTH : 0);
    const labelX  = r2(Math.min(BAR_BG_X + barW + VAL_OFFSET, W - RIGHT_MARGIN));
    const valLabel = formatLabel(value, enc);
    const ty      = 10 + i * 42;

    groups += `<g transform="translate(40, ${ty})">`;
    groups += `<text x="${LABEL_X}" y="${LABEL_Y}" font-size="18" fill="${C.txt}">${esc(String(label))}</text>`;
    groups += `<rect x="${BAR_BG_X}" y="${BAR_BG_Y}" width="${BAR_BG_WIDTH}" height="${BAR_HEIGHT}" fill="${C.hold}" rx="4"/>`;
    groups += `<rect x="${BAR_BG_X}" y="${BAR_BG_Y}" width="${barW}" height="${BAR_HEIGHT}" fill="${C.pri}" rx="4"/>`;
    groups += `<text x="${labelX}" y="${LABEL_Y}" font-size="17" fill="${C.txt}">${esc(String(valLabel))}</text>`;
    groups += '</g>';
  });

  // Title + axis label
  const titleEl  = `<text x="20" y="30" font-size="20" font-weight="bold" fill="${C.txt}">${esc(String(spec.title))}</text>`;
  const srcY     = svgH - 20;
  const sourceEl = `<text x="20" y="${srcY}" font-size="14" fill="${C.light}">${esc(String(spec.source_note))}</text>`;

  const figId = spec.product ? escAttr(spec.product.fig_id) : 'fig-unknown';
  const svg = `<svg viewBox="0 0 ${W} ${svgH}" xmlns="http://www.w3.org/2000/svg">${titleEl}${groups}${sourceEl}</svg>`;
  return `<div class="chart-block" id="${figId}" data-chart-kind="horizontal-bar" style="margin:1rem 0;">${svg}</div>`;
}

// ─────────────────────────────────────────────────
// Renderer: multi-series-line (macro PMI chart)
// ─────────────────────────────────────────────────

/**
 * Expects spec.data rows with: x_field (label), series_field (series name), value_field (numeric)
 * OR pre-grouped via encoding.series_field.
 *
 * Data layout: each row = { [x_field]: label, [series_field]: seriesName, [value_field]: number }
 */
function renderMultiSeriesLine(spec) {
  const enc     = spec.encoding;
  const h = HH, t = P, b = P, l = P + 5, rr = P - 45;

  // Group data by series
  const seriesMap = new Map();   // seriesName → value[]
  const xLabels   = [];

  // Collect unique x labels in order
  const seenX = new Set();
  for (const row of spec.data) {
    const xVal = String(row[enc.x_field]);
    if (!seenX.has(xVal)) { xLabels.push(xVal); seenX.add(xVal); }
  }

  for (const row of spec.data) {
    const serName = enc.series_field ? String(row[enc.series_field]) : 'series';
    if (!seriesMap.has(serName)) seriesMap.set(serName, []);
    seriesMap.get(serName).push(Number(row[enc.value_field]));
  }

  if (seriesMap.size === 0) {
    throw new FigureRenderError('multi-series-line: no series data found');
  }

  const allValues = [...seriesMap.values()].flat().filter(isFinite);
  if (allValues.length === 0) {
    throw new FigureRenderError('multi-series-line: all values are non-finite');
  }

  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  // Pad by 10% for visual breathing room
  const pad  = (maxV - minV) * 0.1 || 1;
  const MIN  = r2(minV - pad);
  const MAX  = r2(maxV + pad);
  const ticks = 6;

  const n = xLabels.length;
  const seriesEntries = [...seriesMap.entries()];

  let content = '';
  content += gridLines(MIN, MAX, ticks, h, t, b, l, rr);

  // Y axis title
  if (enc.y_title) {
    content += `<text x="${l - 45}" y="${h / 2}" text-anchor="middle" font-size="16" fill="${C.light}" transform="rotate(-90,${l - 45},${h / 2})">${esc(enc.y_title)}</text>`;
  }

  // Polylines + dots
  seriesEntries.forEach(([name, vals], si) => {
    const color = SERIES_COLORS[si % SERIES_COLORS.length];
    const pts = vals.map((v, i) =>
      `${pxX(i, n, l, rr)},${pxY(v, MIN, MAX, h, t, b)}`
    ).join(' ');
    content += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="${si === 0 ? 5 : 4}" stroke-linecap="round" stroke-linejoin="round" data-series="${escAttr(name)}"/>`;
    vals.forEach((v, i) => {
      const cx = pxX(i, n, l, rr);
      const cy = pxY(v, MIN, MAX, h, t, b);
      content += `<circle cx="${cx}" cy="${cy}" r="${si === 0 ? 6 : 5}" fill="${color}" stroke="white" stroke-width="2.5"/>`;
    });
  });

  // X axis labels
  xLabels.forEach((lbl, i) => {
    content += `<text x="${pxX(i, n, l, rr)}" y="${h - b + 26}" text-anchor="middle" font-size="18" fill="${C.light}">${esc(lbl)}</text>`;
  });

  // Inline legend (top-right)
  const legendItems = seriesEntries.map(([name], si) => ({
    c: SERIES_COLORS[si % SERIES_COLORS.length], l: name
  }));
  content += _inlineLegend(legendItems, t, rr);

  return svgWrap(content, h, spec.title, spec.source_note, spec.lang);
}

// ─────────────────────────────────────────────────
// Renderer: grouped-bar (macro CPI chart)
// ─────────────────────────────────────────────────

/**
 * Expects spec.data rows: { [x_field]: groupLabel, [y_field]: primaryValue, [y2_field?]: secondaryValue, [value_field]: primaryValue }
 * Each row = one group with two bars (primary = solid, secondary = transparent).
 * If encoding.y2_field is absent, renders single bar per group.
 */
function renderGroupedBar(spec) {
  const enc = spec.encoding;
  const h = HH, t = P, b = P, l = P - 5, rr = P - 70;

  const groups = spec.data.map(row => ({
    label:   String(row[enc.label_field] ?? row[enc.x_field]),
    primary: Number(row[enc.value_field]),
    secondary: enc.y2_field != null ? Number(row[enc.y2_field]) : null,
    color:   row._color ? String(row._color) : null,
  }));

  // Fail-closed: all primary values must be finite
  for (let i = 0; i < groups.length; i++) {
    if (!isFinite(groups[i].primary)) {
      throw new FigureRenderError(
        `grouped-bar: data[${i}] primary value is non-finite`
      );
    }
  }

  const allVals = groups.flatMap(g => g.secondary != null ? [g.primary, g.secondary] : [g.primary]);
  const MIN = 0;
  const MAX = r2(Math.max(...allVals) * 1.15 || 1);
  const ticks = 5;

  const gW    = (W - l - rr) / groups.length;
  const bW    = r2(gW * 0.28);
  const gap   = r2(gW * 0.06);
  const baseY = pxY(0, MIN, MAX, h, t, b);

  let content = '';
  content += gridLines(MIN, MAX, ticks, h, t, b, l, rr);
  content += `<line x1="${l}" y1="${r2(baseY)}" x2="${W - rr}" y2="${r2(baseY)}" stroke="${C.axis}" stroke-width="1.5"/>`;

  groups.forEach((g, i) => {
    const color = g.color || SERIES_COLORS[i % SERIES_COLORS.length];
    const gx    = l + i * gW + gW / 2;
    const x1    = r2(gx - bW - gap / 2);
    const x2    = r2(gx + gap / 2);
    const y1    = r2(pxY(g.primary, MIN, MAX, h, t, b));

    // Primary bar
    content += `<rect x="${x1}" y="${y1}" width="${bW}" height="${r2(baseY - y1)}" fill="${color}" rx="3" data-value="${g.primary}"/>`;
    content += `<text x="${r2(x1 + bW / 2)}" y="${r2(y1 - 7)}" text-anchor="middle" font-size="19" font-weight="600" fill="${color}">${esc(formatLabel(g.primary, enc))}</text>`;

    // Secondary bar (if present)
    if (g.secondary != null && isFinite(g.secondary)) {
      const y2 = r2(pxY(g.secondary, MIN, MAX, h, t, b));
      content += `<rect x="${x2}" y="${y2}" width="${bW}" height="${r2(baseY - y2)}" fill="${color}" rx="3" opacity="0.38" data-value="${g.secondary}"/>`;
      content += `<text x="${r2(x2 + bW / 2)}" y="${r2(y2 - 7)}" text-anchor="middle" font-size="18" fill="${color}" opacity="0.75">${esc(formatLabel(g.secondary, enc))}</text>`;
    }

    // X label
    content += `<text x="${r2(gx)}" y="${h - b + 26}" text-anchor="middle" font-size="17" fill="${C.light}">${esc(g.label)}</text>`;
  });

  // Legend for primary/secondary if y2_title present
  if (enc.y2_title) {
    const legendItems = [
      { c: C.pri, l: enc.y_title || 'Primary' },
      { c: C.pri, l: enc.y2_title, opacity: '0.38' },
    ];
    content += _inlineLegendOpts(legendItems, t, rr);
  }

  return svgWrap(content, h, spec.title, spec.source_note, spec.lang);
}

// ─────────────────────────────────────────────────
// Renderer: signed-bar (macro WoW/YTD charts)
// Negatives are VALID for this kind; fail-closed on non-finite only
// ─────────────────────────────────────────────────

function renderSignedBar(spec) {
  const enc = spec.encoding;
  const h = HH, t = P, b = P, l = P + 10, rr = P - 60;

  const items = spec.data.map((row, i) => ({
    label: String(row[enc.label_field] ?? row[enc.x_field]),
    value: Number(row[enc.value_field]),
    color: row._color ? String(row._color) : null,
    idx: i,
  }));

  // Fail-closed: no non-finite values, but negatives are allowed
  for (const item of items) {
    if (!isFinite(item.value)) {
      throw new FigureRenderError(
        `signed-bar: value for '${item.label}' is non-finite (NaN/Infinity)`
      );
    }
  }

  const allVals = items.map(m => m.value);
  const rawMin  = Math.min(...allVals);
  const rawMax  = Math.max(...allVals);
  const pad     = (rawMax - rawMin) * 0.18 || 1;
  const MIN     = r2(rawMin - pad);
  const MAX     = r2(rawMax + pad);
  const ticks   = 6;

  const bW    = r2((W - l - rr) / items.length * 0.52);
  const baseY = pxY(0, MIN, MAX, h, t, b);

  let content = '';
  content += gridLines(MIN, MAX, ticks, h, t, b, l, rr);
  // Mandatory zero-line for signed charts
  content += zeroLine(MIN, MAX, h, t, b, l, rr);

  items.forEach((m, i) => {
    const cx  = r2(l + (i + 0.5) * (W - l - rr) / items.length);
    const x   = r2(cx - bW / 2);
    const y   = r2(pxY(m.value, MIN, MAX, h, t, b));
    const col = m.color || (m.value >= 0 ? C.up : C.dn);

    content += `<rect x="${x}" y="${r2(Math.min(y, baseY))}" width="${bW}" height="${r2(Math.abs(baseY - y))}" fill="${col}" rx="3" opacity="0.85" data-value="${m.value}"/>`;

    const sign = m.value >= 0 ? '+' : '';
    const vy   = r2(m.value >= 0 ? y - 12 : y + 26);
    content += `<text x="${cx}" y="${vy}" text-anchor="middle" font-size="22" font-weight="700" fill="${col}">${esc(sign)}${esc(formatLabel(m.value, enc))}</text>`;
    content += `<text x="${cx}" y="${h - b + 30}" text-anchor="middle" font-size="19" font-weight="600" fill="${col}">${esc(m.label)}</text>`;
  });

  return svgWrap(content, h, spec.title, spec.source_note, spec.lang);
}

// ─────────────────────────────────────────────────
// Legend helpers
// ─────────────────────────────────────────────────

function _inlineLegend(items, t, rr) {
  return _inlineLegendOpts(items, t, rr);
}

function _inlineLegendOpts(items, t, rr) {
  const itemH = 22, boxW = 140, boxH = items.length * itemH + 10;
  const bx = W - rr - boxW, by = t + 6;
  let out = `<rect x="${r2(bx - 6)}" y="${r2(by - 4)}" width="${boxW + 8}" height="${boxH}" rx="4" fill="white" fill-opacity="0.88"/>`;
  items.forEach((item, i) => {
    const cy = r2(by + 10 + i * itemH);
    const op = item.opacity ? ` opacity="${item.opacity}"` : '';
    out += `<circle cx="${r2(bx + 6)}" cy="${cy}" r="6" fill="${item.c}"${op}/>`;
    out += `<text x="${r2(bx + 18)}" y="${r2(cy + 5)}" font-size="16" fill="${C.txt}">${esc(item.l)}</text>`;
  });
  return out;
}

// ─────────────────────────────────────────────────
// Public API: renderFigure
// ─────────────────────────────────────────────────

/**
 * Render a validated FigureSpec to an SVG string (or chart-block HTML for product target).
 *
 * @param {Object} spec — result of FigureSpec() factory (validated, frozen)
 * @returns {string} SVG/HTML string; EVERY text node escaped; geometry at 2dp
 * @throws {FigureRenderError} on empty data or value invariant violations
 */
export function renderFigure(spec) {
  if (!spec || typeof spec !== 'object') {
    throw new FigureRenderError('renderFigure requires a validated FigureSpec object');
  }
  if (!Array.isArray(spec.data) || spec.data.length === 0) {
    throw new FigureRenderError('renderFigure: data is empty — fail-closed');
  }

  switch (spec.chart_type) {
    case 'horizontal-bar':   return renderHorizontalBar(spec);
    case 'multi-series-line': return renderMultiSeriesLine(spec);
    case 'grouped-bar':       return renderGroupedBar(spec);
    case 'signed-bar':        return renderSignedBar(spec);
    default:
      throw new FigureRenderError(`No renderer for chart_type '${spec.chart_type}'`);
  }
}
