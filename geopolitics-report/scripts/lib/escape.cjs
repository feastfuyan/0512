'use strict';
/**
 * escape.cjs — CJS shim of escape.mjs for use in CommonJS modules
 * (e.g. gen_reference_charts.cjs).
 *
 * Provides identical esc() and escAttr() helpers.
 * See escape.mjs for full documentation.
 */

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escAttr(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

module.exports = { esc, escAttr };
