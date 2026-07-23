/**
 * figure_spec.mjs — FigureSpec factory/validator (JS port of spec.py)
 *
 * Supports render targets and chart kinds needed by the macro skill:
 *   product: horizontal-bar
 *   paper:   multi-series-line, grouped-bar, signed-bar, horizontal-bar
 *
 * Validators FAIL-CLOSED: throw FigureRenderError on invalid input.
 * Security: fig_id charset + value_format whitelist port from spec.py fix #2/#3.
 */

import { esc, escAttr } from '../scripts/lib/escape.mjs';
import { validateLang } from '../scripts/lib/i18n.mjs';

// Re-export helpers so consumers have a single import point
export { esc, escAttr };

// ─────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────

export const MACRO_CHART_TYPES = new Set([
  'horizontal-bar',
  'multi-series-line',
  'grouped-bar',
  'signed-bar',
]);

// value_format whitelist: Python numeric mini-language, precision ≤ 3
// mirrors spec.py:76-79 _VALUE_FORMAT_RE
const VALUE_FORMAT_RE = /^[<>=^]?[+\- ]?,?(\.\d+)?[fdeEgG%]?$/;
const PRECISION_RE    = /\.(\d+)/;

// fig_id charset whitelist: mirrors spec.py:82 _FIG_ID_RE (fix #2)
const FIG_ID_RE = /^[A-Za-z0-9_-]+$/;

// ─────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────

export class FigureRenderError extends Error {
  constructor(msg) {
    super(msg);
    this.name = 'FigureRenderError';
  }
}

// ─────────────────────────────────────────────────
// formatLabel — mirrors spec.py:18-35
// ─────────────────────────────────────────────────

/**
 * Format a numeric value for a figure label.
 * Honors encoding.value_format (whitelisted numeric format spec) if set.
 * @param {number} value
 * @param {{ unit?: string, value_format?: string }} encoding
 * @returns {string}
 */
export function formatLabel(value, encoding) {
  const unit = encoding.unit ?? '';

  if (encoding.value_format) {
    return _applyNumericFormat(value, encoding.value_format);
  }
  // Default: strip unnecessary decimal if whole number
  if (value === Math.trunc(value)) {
    return `${Math.trunc(value)}${unit}`;
  }
  return `${value}${unit}`;
}

/**
 * Safe numeric formatter — maps whitelisted value_format to JS output.
 * No eval. Only supports the patterns that pass VALUE_FORMAT_RE.
 * @param {number} value
 * @param {string} fmt
 * @returns {string}
 */
function _applyNumericFormat(value, fmt) {
  // Extract precision digits if present (e.g. ".2" from ".2f")
  const precMatch = PRECISION_RE.exec(fmt);
  const prec = precMatch ? parseInt(precMatch[1], 10) : undefined;

  // Detect format type letter (last char of fmt)
  const typeCh = fmt.slice(-1);

  if (typeCh === '%') {
    const p = prec ?? 1;
    return `${(value * 100).toFixed(p)}%`;
  }
  if (typeCh === 'f' || typeCh === 'd' || typeCh === 'e' || typeCh === 'E') {
    const p = prec ?? (typeCh === 'd' ? 0 : 2);
    const hasComma = fmt.includes(',');
    const numStr = value.toFixed(p);
    if (hasComma && p === 0) {
      return Number(numStr).toLocaleString('en-US', { maximumFractionDigits: 0 });
    }
    return numStr;
  }
  if (typeCh === 'g' || typeCh === 'G') {
    return value.toPrecision(prec ?? 6);
  }
  // Fallback: plain string
  return String(value);
}

// ─────────────────────────────────────────────────
// Validators
// ─────────────────────────────────────────────────

function _validateValueFormat(vf) {
  if (vf == null || vf === '') return null;
  if (!VALUE_FORMAT_RE.test(vf)) {
    throw new FigureRenderError(
      `value_format ${JSON.stringify(vf)} is not a whitelisted numeric format spec — ` +
      'only Python numeric format mini-language with precision ≤3 is allowed'
    );
  }
  const precMatch = PRECISION_RE.exec(vf);
  if (precMatch && parseInt(precMatch[1], 10) > 3) {
    throw new FigureRenderError(
      `value_format ${JSON.stringify(vf)} has precision > 3 — maximum allowed is 3`
    );
  }
  return vf;
}

function _validateFigId(figId) {
  if (!FIG_ID_RE.test(figId)) {
    throw new FigureRenderError(
      `fig_id ${JSON.stringify(figId)} contains invalid characters — ` +
      'only A-Za-z0-9, hyphen (-), and underscore (_) are allowed'
    );
  }
  return figId;
}

// ─────────────────────────────────────────────────
// FigureSpec factory
// ─────────────────────────────────────────────────

/**
 * FigureSpec — validated figure contract (JS port of spec.py FigureSpec).
 *
 * @param {Object} opts
 * @param {'product'|'paper'} opts.render_target
 * @param {string} opts.chart_type
 * @param {Array<Object>} opts.data
 * @param {Object} opts.encoding   — x_field, y_field, label_field, value_field, unit, [series_field], [value_format], ...
 * @param {string} opts.title
 * @param {string} opts.source_note
 * @param {string} opts.claim
 * @param {Object} [opts.product]  — { fig_id }
 * @param {Object} [opts.paper]    — { dimensions, ... }
 * @returns {Object} validated, frozen spec
 * @throws {FigureRenderError} on any validation failure (fail-closed)
 */
export function FigureSpec(opts) {
  const {
    render_target,
    chart_type,
    data,
    encoding,
    title,
    source_note,
    claim,
    product = null,
    paper   = null,
    lang    = "en",
  } = opts;

  // lang drives the chart source-note prefix ("Source: " vs "数据来源：") and
  // any future locale-aware rendering. Fail-closed on unsupported values.
  const validLang = validateLang(lang);

  // 1. claim non-empty
  if (!claim || !String(claim).trim()) {
    throw new FigureRenderError('claim must be non-empty');
  }

  // 2. chart_type gating
  if (!MACRO_CHART_TYPES.has(chart_type)) {
    throw new FigureRenderError(
      `chart_type '${chart_type}' is not a recognised macro chart type ` +
      `(allowed: ${[...MACRO_CHART_TYPES].join(', ')})`
    );
  }

  // 3. render_target opts mutual exclusion
  if (render_target === 'product') {
    if (!product) throw new FigureRenderError("render_target='product' requires product opts");
    if (paper)    throw new FigureRenderError("render_target='product' must not supply paper opts");
    if (chart_type !== 'horizontal-bar') {
      throw new FigureRenderError(
        `render_target='product' only allows chart_type='horizontal-bar', got '${chart_type}'`
      );
    }
  } else if (render_target === 'paper') {
    if (!paper)   throw new FigureRenderError("render_target='paper' requires paper opts");
    if (product)  throw new FigureRenderError("render_target='paper' must not supply product opts");
  } else {
    throw new FigureRenderError(`render_target must be 'product' or 'paper', got '${render_target}'`);
  }

  // 4. data non-empty (fail-closed — empty data cannot produce a meaningful figure)
  if (!Array.isArray(data) || data.length === 0) {
    throw new FigureRenderError('data must be a non-empty array');
  }

  // 5. Validate encoding fields
  const enc = { ...encoding };
  enc.unit = enc.unit ?? null;
  if (!enc.unit && enc.unit !== '') {
    throw new FigureRenderError('encoding.unit is required (may be empty string but must be present)');
  }
  // value_format whitelist (fix #3)
  enc.value_format = _validateValueFormat(enc.value_format ?? null);

  // 6. Row-shape: every referenced encoding field must exist in ALL rows
  const required = [enc.x_field, enc.y_field, enc.label_field, enc.value_field];
  for (const optField of [enc.y2_field, enc.series_field, enc.color_field]) {
    if (optField != null) required.push(optField);
  }
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const missing = required.filter(f => !(f in row));
    if (missing.length) {
      throw new FigureRenderError(
        `data[${i}] is missing fields required by encoding: ${missing.join(', ')}`
      );
    }
    // value_field must be numeric (fail-closed — mirrors spec.py:262-271)
    const rawVal = row[enc.value_field];
    if (rawVal != null && typeof rawVal !== 'number') {
      throw new FigureRenderError(
        `data[${i}]['${enc.value_field}'] must be a number, got ${typeof rawVal}: ${JSON.stringify(rawVal)}`
      );
    }
  }

  // 7. Validate product opts
  let productOpts = null;
  if (product) {
    _validateFigId(product.fig_id);
    productOpts = { fig_id: product.fig_id };
  }

  // 8. Validate paper opts
  let paperOpts = null;
  if (paper) {
    paperOpts = { ...paper };
  }

  return Object.freeze({
    render_target,
    chart_type,
    data,
    encoding: Object.freeze(enc),
    title,
    source_note,
    claim,
    lang: validLang,
    product: productOpts ? Object.freeze(productOpts) : null,
    paper:   paperOpts   ? Object.freeze(paperOpts)   : null,
  });
}
