/**
 * escape.mjs — shared HTML/SVG/XML escaping helpers.
 *
 * All LLM-derived and data.json-derived strings MUST pass through
 * these helpers before being interpolated into SVG <text>/attributes
 * or HTML markup strings, per the security hardening spec (step-02).
 *
 * esc(s)     — escapes &, <, > for text content inside SVG <text>/<tspan>
 *              or HTML element bodies.  Safe for both XML and HTML5.
 * escAttr(s) — additionally escapes " and ' for use inside attribute values.
 *              Use inside href="…", title="…", etc.
 *
 * Usage (ESM):
 *   import { esc, escAttr } from './lib/escape.mjs';
 */

/**
 * Escape a string for safe use as SVG/HTML text content.
 * @param {*} s - any value; coerced to string.
 * @returns {string}
 */
export function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Escape a string for safe use as an HTML/SVG attribute value.
 * Superset of esc() — also escapes " and '.
 * @param {*} s - any value; coerced to string.
 * @returns {string}
 */
export function escAttr(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
