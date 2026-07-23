/**
 * figure_checks.mjs — deterministic figure scorer
 *
 * exports scoreFigureSvg(svg, { expectedSeries? }) → { dims, vetoes, blockers }
 * exports pngMeetsResolution(buf) → boolean   (reads IHDR, asserts ≥2080×1280)
 *
 * Single source of truth for SVG-safety + IHDR checks:
 *   - SVG safety: HARD import of enforce-gate exported checkSvgSafety() -- no local copy.
 *   - IHDR reader: HARD import of enforce-gate exported readPngDimensions() -- no local copy.
 *   Both lazy-loaded to avoid circular import at parse time. Step 5b deleted fallbacks.
 *
 * Contract consumed by enforce-gate step 5b integration:
 *   vetoes  — array of { type, detail } that force chart_quality set_score=0
 *   blockers — array of { type, detail } that set_score=0 on the image_metadata dim
 *   dims    — { safety: 0|1, data_marks: 0|1, labeling: 0|1 }
 *             (1 = passes, 0 = fails; enforce-gate maps to sub-score 0-10)
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─────────────────────────────────────────────────
// Single-source IHDR + SVG-safety: HARD import from enforce-gate.mjs
// NO local fallback copies (step 5b: deleted to prevent drift).
// Lazy-loaded via dynamic import to avoid circular ESM at parse time.
// Uses pathToFileURL for Windows compatibility (c: path → file:// URL).
// ─────────────────────────────────────────────────

let _readPngDimensions = null;
let _checkSvgSafety    = null;

async function _loadEnforceGate() {
  if (_readPngDimensions && _checkSvgSafety) return;
  const { pathToFileURL } = await import('node:url');
  const enforceGateUrl = pathToFileURL(path.resolve(__dirname, '../scripts/enforce-gate.mjs')).href;
  const mod = await import(enforceGateUrl);
  if (typeof mod.readPngDimensions !== 'function') {
    throw new Error('figure_checks: readPngDimensions not exported from enforce-gate.mjs — single source violated');
  }
  if (typeof mod.checkSvgSafety !== 'function') {
    throw new Error('figure_checks: checkSvgSafety not exported from enforce-gate.mjs — single source violated');
  }
  _readPngDimensions = mod.readPngDimensions;
  _checkSvgSafety    = mod.checkSvgSafety;
}

// ─────────────────────────────────────────────────
// pngMeetsResolution
// ─────────────────────────────────────────────────

/**
 * Check that a PNG buffer meets the ≥2080×1280 raster requirement.
 * Reads IHDR bytes directly — no image library needed.
 *
 * @param {Buffer} buf — raw PNG binary buffer (NOT base64)
 * @returns {boolean}
 */
export function pngMeetsResolution(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 24) return false;
  const sig = buf.slice(0, 8);
  const expected = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (!sig.equals(expected)) return false;
  const width  = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  return width >= 2080 && height >= 1280;
}

// ─────────────────────────────────────────────────
// scoreFigureSvg
// ─────────────────────────────────────────────────

/**
 * Deterministic scorer for a rendered figure SVG string.
 *
 * Checks:
 *   (a) SVG-safety: zero unescaped <>&" inside <text>/<tspan> → veto
 *   (b) data marks: chart has at least one <polyline>/<rect>/<path>/<circle>
 *       for each declared series → veto if none found
 *   (c) labeling: SVG contains at least one <text> element (axis/title)
 *   (d) viewBox resolution: SVG viewBox width×height ≥ 1040×640
 *       (so a 2× raster is ≥ 2080×1280)
 *
 * @param {string} svg — raw SVG/HTML string from renderFigure()
 * @param {{ expectedSeries?: number }} [opts]
 *   expectedSeries — number of distinct series expected (polylines or bar groups);
 *                    if omitted, only asserts ≥1 data mark exists
 * @returns {{ dims: Object, vetoes: Array, blockers: Array }}
 */
export async function scoreFigureSvg(svg, opts = {}) {
  await _loadEnforceGate();

  const { expectedSeries } = opts;

  const vetoes   = [];
  const blockers = [];
  const dims     = {
    safety:     1,   // 1=pass, 0=fail
    data_marks: 1,
    labeling:   1,
    resolution: 1,
  };

  // ── (a) SVG safety ──────────────────────────────
  const safetyViolations = _checkSvgSafety(svg);
  if (safetyViolations.length > 0) {
    dims.safety = 0;
    for (const v of safetyViolations) {
      vetoes.push({ type: 'svg_injection', detail: v.content });
    }
  }

  // ── (b) Data marks ──────────────────────────────
  // Count distinct data-bearing marks
  const polylines = (svg.match(/<polyline\b/gi) || []).length;
  const rects     = (svg.match(/<rect\b[^>]*data-value/gi) || []).length;
  const paths     = (svg.match(/<path\b/gi) || []).length;
  const circles   = (svg.match(/<circle\b[^>]*cy=/gi) || []).length;  // data dots

  const totalMarks = polylines + rects + paths + circles;

  if (totalMarks === 0) {
    dims.data_marks = 0;
    vetoes.push({ type: 'no_data_marks', detail: 'SVG has no polyline/rect(data-value)/path/circle data marks' });
  } else if (expectedSeries != null && expectedSeries > 0) {
    // For line charts: should have at least expectedSeries polylines
    // For bar charts:  should have at least expectedSeries rects with data-value
    const seriesMarks = polylines > 0 ? polylines : rects;
    if (seriesMarks < expectedSeries) {
      dims.data_marks = 0;
      vetoes.push({
        type: 'insufficient_series_marks',
        detail: `Expected ${expectedSeries} series marks, found ${seriesMarks}`,
      });
    }
  }

  // ── (c) Labeling ──────────────────────────────
  const textCount = (svg.match(/<text\b/gi) || []).length;
  if (textCount === 0) {
    dims.labeling = 0;
    blockers.push({ type: 'no_labels', detail: 'SVG has no <text> elements (no axis/title labels)' });
  }

  // ── (d) viewBox resolution ──────────────────────
  // SVG must declare viewBox with width ≥ 1040 and height ≥ 640
  // so deviceScaleFactor=2 raster is ≥ 2080×1280
  const vbMatch = svg.match(/viewBox=["']0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)["']/i);
  if (!vbMatch) {
    dims.resolution = 0;
    blockers.push({ type: 'no_viewbox', detail: 'SVG has no viewBox attribute' });
  } else {
    const vbW = parseFloat(vbMatch[1]);
    const vbH = parseFloat(vbMatch[2]);
    if (vbW < 1040 || vbH < 640) {
      dims.resolution = 0;
      blockers.push({
        type: 'viewbox_too_small',
        detail: `viewBox ${vbW}×${vbH} < 1040×640 — 2× raster would be ${vbW * 2}×${vbH * 2}, below ≥2080×1280 threshold`,
      });
    }
  }

  return { dims, vetoes, blockers };
}
