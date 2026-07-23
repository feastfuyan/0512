/**
 * test-figures.mjs — self-contained test suite for the JS figure module
 *
 * Run: node figures/test-figures.mjs
 *
 * Tests:
 *   1. Each of the 3 macro chart kinds renders without error (scoreFigureSvg passes, no veto)
 *   2. XSS escape: a label containing </text><script> is escaped, no live tag
 *   3. Empty data → FigureRenderError thrown (fail-closed)
 *   4. viewBox is large enough for ≥2080×1280 2× raster (≥1040×640)
 *   5. Determinism: same spec → same SVG string (byte-stable)
 *   6. Missing unit field → FigureRenderError
 *   7. Bad value_format → FigureRenderError
 *   8. Bad fig_id charset → FigureRenderError
 *   9. Non-numeric value_field → FigureRenderError
 */

import assert from 'node:assert/strict';
import { FigureSpec, FigureRenderError } from '../figures/figure_spec.mjs';
import { renderFigure } from '../figures/render_product_svg.mjs';
import { scoreFigureSvg, pngMeetsResolution } from '../figures/figure_checks.mjs';

// ─────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────

let passed = 0;
let failed = 0;

async function test(name, fn) {
  try {
    await fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

function baseEncoding(overrides = {}) {
  return {
    x_field:     'x',
    y_field:     'y',
    label_field: 'label',
    value_field: 'value',
    x_title:     'Month',
    y_title:     'Value',
    unit:        '%',
    ...overrides,
  };
}

// ─────────────────────────────────────────────────
// Sample data
// ─────────────────────────────────────────────────

const PMI_DATA = [
  { x: 'Jan', y: 49.1, label: 'Jan', value: 49.1, series: 'China' },
  { x: 'Feb', y: 49.8, label: 'Feb', value: 49.8, series: 'China' },
  { x: 'Mar', y: 50.0, label: 'Mar', value: 50.0, series: 'China' },
  { x: 'Jan', y: 49.0, label: 'Jan', value: 49.0, series: 'US' },
  { x: 'Feb', y: 48.6, label: 'Feb', value: 48.6, series: 'US' },
  { x: 'Mar', y: 49.1, label: 'Mar', value: 49.1, series: 'US' },
];

const CPI_DATA = [
  { x: 'US',        label: 'US 美国',        value: 3.0, y: 3.0, y2: 3.3, _color: '#3b82f6' },
  { x: 'Eurozone',  label: 'Eurozone 欧元区', value: 2.5, y: 2.5, y2: 2.9, _color: '#8b5cf6' },
  { x: 'China',     label: 'China 中国',      value: 0.2, y: 0.2, y2: 0.6, _color: '#14b8a6' },
  { x: 'AU',        label: 'AU 澳大利亚',     value: 3.6, y: 3.6, y2: 4.0, _color: '#f59e0b' },
];

const SIGNED_DATA = [
  { x: 'Cu', label: 'Cu 铜', value:  2.3, y:  2.3, _color: '#e07b39' },
  { x: 'Al', label: 'Al 铝', value:  1.1, y:  1.1, _color: '#94a3b8' },
  { x: 'Fe', label: 'Fe 铁', value: -1.2, y: -1.2, _color: '#dc2626' },
  { x: 'Zn', label: 'Zn 锌', value:  0.8, y:  0.8, _color: '#0891b2' },
  { x: 'Ni', label: 'Ni 镍', value: -0.5, y: -0.5, _color: '#64748b' },
];

// ─────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────

console.log('\n── figure module tests ──\n');

// 1a. multi-series-line renders + scores clean
await test('multi-series-line: renders + scoreFigureSvg passes (no veto)', async () => {
  const spec = FigureSpec({
    render_target: 'paper',
    chart_type:    'multi-series-line',
    data:          PMI_DATA,
    encoding:      baseEncoding({ series_field: 'series', unit: '' }),
    title:         'Global Manufacturing PMI',
    source_note:   'Caixin, ISM',
    claim:         'PMI showing divergence between EM and DM',
    paper:         { dimensions: 'paper-183mm' },
  });
  const svg = renderFigure(spec);
  assert.ok(typeof svg === 'string' && svg.length > 100, 'renderFigure returned a string');
  const { vetoes, blockers } = await scoreFigureSvg(svg, { expectedSeries: 2 });
  assert.equal(vetoes.length, 0,   `unexpected vetoes: ${JSON.stringify(vetoes)}`);
  assert.equal(blockers.length, 0, `unexpected blockers: ${JSON.stringify(blockers)}`);
});

// 1b. grouped-bar renders + scores clean
await test('grouped-bar: renders + scoreFigureSvg passes (no veto)', async () => {
  const spec = FigureSpec({
    render_target: 'paper',
    chart_type:    'grouped-bar',
    data:          CPI_DATA,
    encoding:      baseEncoding({ y2_field: 'y2', y2_title: 'Core CPI', unit: '%' }),
    title:         'CPI & Core CPI YoY %',
    source_note:   'BLS, Eurostat, NBS, ABS',
    claim:         'Inflation broadly softening across regions',
    paper:         { dimensions: 'paper-183mm' },
  });
  const svg = renderFigure(spec);
  assert.ok(typeof svg === 'string' && svg.length > 100);
  const { vetoes, blockers } = await scoreFigureSvg(svg);
  assert.equal(vetoes.length, 0,   `unexpected vetoes: ${JSON.stringify(vetoes)}`);
  assert.equal(blockers.length, 0, `unexpected blockers: ${JSON.stringify(blockers)}`);
});

// 1c. signed-bar renders + scores clean (negatives valid)
await test('signed-bar: renders with negatives + scoreFigureSvg passes (no veto)', async () => {
  const spec = FigureSpec({
    render_target: 'paper',
    chart_type:    'signed-bar',
    data:          SIGNED_DATA,
    encoding:      baseEncoding({ unit: '%' }),
    title:         'Base Metals WoW %',
    source_note:   'LME',
    claim:         'Iron and nickel declined week on week',
    paper:         { dimensions: 'paper-183mm' },
  });
  const svg = renderFigure(spec);
  assert.ok(typeof svg === 'string' && svg.length > 100);
  const { vetoes, blockers } = await scoreFigureSvg(svg);
  assert.equal(vetoes.length, 0,   `unexpected vetoes: ${JSON.stringify(vetoes)}`);
  assert.equal(blockers.length, 0, `unexpected blockers: ${JSON.stringify(blockers)}`);
});

// 2. XSS escape: label with </text><script> is escaped — no live tag in output
await test('XSS escape: </text><script> in label is neutralised', async () => {
  // Put the injection string in BOTH x_field (rendered as x-axis text label)
  // AND series_field (rendered as data-series attribute + legend text) so we
  // exercise both the text-content and attribute-content escaping paths.
  const XSS = '</text><script>alert(1)</script>';
  const xssData = [
    { x: XSS, y: 1, label: XSS, value: 1, series: XSS },
    { x: 'b', y: 2, label: 'normal label', value: 2, series: XSS },
  ];
  const spec = FigureSpec({
    render_target: 'paper',
    chart_type:    'multi-series-line',
    data:          xssData,
    encoding:      baseEncoding({ series_field: 'series', unit: '' }),
    title:         'XSS test',
    source_note:   'test',
    claim:         'XSS escape test',
    paper:         { dimensions: 'paper-183mm' },
  });
  const svg = renderFigure(spec);
  // The raw injection string must NOT appear verbatim in the SVG output
  assert.ok(!svg.includes('</text><script>'), 'raw </text><script> must not appear in SVG');
  // The escaped entities must be present (esc encodes < → &lt; and > → &gt;)
  assert.ok(
    svg.includes('&lt;/text&gt;') || svg.includes('&lt;script&gt;') || svg.includes('&lt;'),
    'escaped &lt; entities must be present in SVG'
  );
  // scoreFigureSvg must find no safety violations
  const { vetoes } = await scoreFigureSvg(svg);
  const safetyVetoes = vetoes.filter(v => v.type === 'svg_injection');
  assert.equal(safetyVetoes.length, 0, `safety vetoes after escaping: ${JSON.stringify(safetyVetoes)}`);
});

// 3. Empty data → FigureRenderError (fail-closed)
await test('empty data → FigureRenderError (fail-closed)', async () => {
  let threw = false;
  try {
    FigureSpec({
      render_target: 'paper',
      chart_type:    'multi-series-line',
      data:          [],
      encoding:      baseEncoding({ series_field: 'series', unit: '' }),
      title:         'empty',
      source_note:   'test',
      claim:         'test claim',
      paper:         { dimensions: 'paper-183mm' },
    });
  } catch (err) {
    threw = true;
    assert.ok(err instanceof FigureRenderError, `expected FigureRenderError, got ${err.constructor.name}`);
  }
  assert.ok(threw, 'expected error for empty data was not thrown');
});

// 4. viewBox resolution: ≥ 1040×640 (so 2× raster ≥ 2080×1280)
await test('viewBox ≥ 1040×640 for ≥2080×1280 2× raster (all 3 kinds)', async () => {
  const specs = [
    FigureSpec({
      render_target: 'paper', chart_type: 'multi-series-line',
      data: PMI_DATA,
      encoding: baseEncoding({ series_field: 'series', unit: '' }),
      title: 'PMI', source_note: 'src', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    }),
    FigureSpec({
      render_target: 'paper', chart_type: 'grouped-bar',
      data: CPI_DATA,
      encoding: baseEncoding({ unit: '%' }),
      title: 'CPI', source_note: 'src', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    }),
    FigureSpec({
      render_target: 'paper', chart_type: 'signed-bar',
      data: SIGNED_DATA,
      encoding: baseEncoding({ unit: '%' }),
      title: 'Metals', source_note: 'src', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    }),
  ];

  for (const spec of specs) {
    const svg = renderFigure(spec);
    const vbMatch = svg.match(/viewBox=["']0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)["']/i);
    assert.ok(vbMatch, `${spec.chart_type}: no viewBox found`);
    const vbW = parseFloat(vbMatch[1]);
    const vbH = parseFloat(vbMatch[2]);
    assert.ok(vbW >= 1040, `${spec.chart_type}: viewBox width ${vbW} < 1040`);
    assert.ok(vbH >= 640,  `${spec.chart_type}: viewBox height ${vbH} < 640 (2× raster would be ${vbW * 2}×${vbH * 2})`);
  }
});

// 5. Determinism: same spec → same SVG (byte-stable)
await test('determinism: same spec → same SVG string (byte-stable)', async () => {
  const makeSpec = () => FigureSpec({
    render_target: 'paper', chart_type: 'signed-bar',
    data: SIGNED_DATA,
    encoding: baseEncoding({ unit: '%' }),
    title: 'Metals WoW', source_note: 'LME', claim: 'claim',
    paper: { dimensions: 'paper-183mm' },
  });
  const svg1 = renderFigure(makeSpec());
  const svg2 = renderFigure(makeSpec());
  assert.equal(svg1, svg2, 'SVG output must be byte-stable across identical spec calls');
});

// 6. Missing unit field → FigureRenderError
await test('missing unit field → FigureRenderError', async () => {
  let threw = false;
  try {
    FigureSpec({
      render_target: 'paper', chart_type: 'signed-bar',
      data: SIGNED_DATA,
      encoding: {
        x_field: 'x', y_field: 'y', label_field: 'label', value_field: 'value',
        x_title: 'X', y_title: 'Y',
        // unit deliberately omitted
      },
      title: 'test', source_note: 'test', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    });
  } catch (err) {
    threw = true;
    assert.ok(err instanceof FigureRenderError);
  }
  assert.ok(threw, 'expected FigureRenderError for missing unit');
});

// 7. Invalid value_format → FigureRenderError
await test('invalid value_format → FigureRenderError (whitelist enforced)', async () => {
  let threw = false;
  try {
    FigureSpec({
      render_target: 'paper', chart_type: 'signed-bar',
      data: SIGNED_DATA,
      encoding: baseEncoding({ unit: '%', value_format: '999f' }), // not whitelisted
      title: 'test', source_note: 'test', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    });
  } catch (err) {
    threw = true;
    assert.ok(err instanceof FigureRenderError);
    assert.ok(err.message.includes('value_format'), `error message should mention value_format: ${err.message}`);
  }
  assert.ok(threw, 'expected FigureRenderError for invalid value_format');
});

// 8. Invalid fig_id charset → FigureRenderError
await test('invalid fig_id charset → FigureRenderError', async () => {
  let threw = false;
  try {
    FigureSpec({
      render_target: 'product', chart_type: 'horizontal-bar',
      data: [{ x: 'a', y: 1, label: 'a', value: 1 }],
      encoding: baseEncoding({ unit: '' }),
      title: 'test', source_note: 'test', claim: 'claim',
      product: { fig_id: 'bad id with spaces & <injection>' },
    });
  } catch (err) {
    threw = true;
    assert.ok(err instanceof FigureRenderError);
    assert.ok(err.message.includes('fig_id'));
  }
  assert.ok(threw, 'expected FigureRenderError for invalid fig_id');
});

// 9. Non-numeric value_field → FigureRenderError
await test('non-numeric value_field → FigureRenderError (row-shape guard)', async () => {
  let threw = false;
  try {
    FigureSpec({
      render_target: 'paper', chart_type: 'signed-bar',
      data: [
        { x: 'a', y: 1.0, label: 'a', value: 'not-a-number' },  // string value
      ],
      encoding: baseEncoding({ unit: '%' }),
      title: 'test', source_note: 'test', claim: 'claim',
      paper: { dimensions: 'paper-183mm' },
    });
  } catch (err) {
    threw = true;
    assert.ok(err instanceof FigureRenderError);
  }
  assert.ok(threw, 'expected FigureRenderError for non-numeric value');
});

// 10. pngMeetsResolution utility works on a known buffer
await test('pngMeetsResolution: rejects small PNG, accepts ≥2080×1280', async () => {
  // Construct a minimal valid PNG IHDR with known dimensions
  function makePngHeader(w, h) {
    const buf = Buffer.alloc(24);
    // PNG signature
    buf[0]=137; buf[1]=80; buf[2]=78; buf[3]=71; buf[4]=13; buf[5]=10; buf[6]=26; buf[7]=10;
    // IHDR chunk: 4 bytes length (13), 4 bytes type "IHDR"
    buf.writeUInt32BE(13, 8);
    buf.write('IHDR', 12, 'ascii');
    // Width and height
    buf.writeUInt32BE(w, 16);
    buf.writeUInt32BE(h, 20);
    return buf;
  }

  const smallBuf = makePngHeader(1040, 720);   // below threshold
  const okBuf    = makePngHeader(2080, 1280);  // exactly at threshold
  const bigBuf   = makePngHeader(2080, 1440);  // above threshold

  assert.equal(pngMeetsResolution(smallBuf), false, '1040×720 should fail');
  assert.equal(pngMeetsResolution(okBuf),    true,  '2080×1280 should pass');
  assert.equal(pngMeetsResolution(bigBuf),   true,  '2080×1440 should pass');
});

// ─────────────────────────────────────────────────
// Results
// ─────────────────────────────────────────────────

console.log(`\n── results: ${passed} passed, ${failed} failed ──\n`);
if (failed > 0) process.exit(1);
