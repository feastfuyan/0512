/**
 * render-figures.mjs — FigureSpec → SVG → PNG pipeline glue
 *
 * Usage:
 *   node scripts/render-figures.mjs --specs charts/{id}-specs.json --html draft/{id}.html
 *   node scripts/render-figures.mjs --specs charts/{id}-specs.json --html draft/{id}.html --no-raster
 *
 * What it does:
 *   1. Reads figure_specs[] from the chart-builder's output JSON.
 *   2. For each spec, calls renderFigure(FigureSpec(spec)) → SVG string (all text escaped).
 *   3. Replaces <!-- CHART:{slug} --> placeholder in the HTML with either:
 *      a. If Playwright is available: <img class="chart" src="data:image/png;base64,..."> at 2080×1280
 *      b. If Playwright absent (--no-raster or chromium not installed): inline <svg> wrapped in
 *         a chart-block div + a comment "raster-skipped-no-chromium" for transparency.
 *   4. Writes the modified HTML back to --html (in-place).
 *   5. Returns exit 0 on success, 1 on fatal error.
 *
 * Security contract:
 *   - All SVG text/attr content goes through esc()/escAttr() inside renderFigure (render_product_svg.mjs).
 *   - No raw LLM or data strings ever land in the SVG without escaping.
 *   - PNG IHDR is validated via pngMeetsResolution before embedding (fail-closed on under-spec PNG).
 *
 * Resolution contract:
 *   - viewBox 1040×640 @ deviceScaleFactor 2 → PNG 2080×1280 (exactly meets ≥2080×1280 gate).
 *   - If Playwright renders at a different scale the script warns and exits 1.
 */

import fs   from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, '..');

// ─── imports from the figures module ──────────────────────────────────────────
import { FigureSpec, FigureRenderError } from '../figures/figure_spec.mjs';
import { renderFigure } from '../figures/render_product_svg.mjs';
import { pngMeetsResolution } from '../figures/figure_checks.mjs';

// ─────────────────────────────────────────────────
// Chart placeholder discovery — supports both canonical comments and
// analyst-writer chart-placeholder divs (legacy / mistaken format).
// ─────────────────────────────────────────────────
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** @returns {{ text: string, start: number, end: number, type: 'comment' | 'div' } | null} */
function findChartPlaceholderBlock(html, slug) {
  const comment = `<!-- CHART:${slug} -->`;
  const commentIdx = html.indexOf(comment);
  if (commentIdx !== -1) {
    return { text: comment, start: commentIdx, end: commentIdx + comment.length, type: 'comment' };
  }

  // chart-placeholder div may contain nested .chart-label div — match full outer block by depth
  const openRe = new RegExp(
    `(?:<img class="chart"[^>]*>\\s*)?<div class="chart-placeholder">`,
    'i',
  );
  const openM = openRe.exec(html);
  if (!openM) return null;

  const labelRe = new RegExp(`CHART:\\s*${escapeRegExp(slug)}`, 'i');
  const blockStart = openM.index;
  const searchFrom = openM.index + openM[0].length;
  const labelM = labelRe.exec(html.slice(searchFrom, searchFrom + 800));
  if (!labelM) return null;

  // Walk to the closing </div> of chart-placeholder (depth-aware)
  let depth = 1;
  let i = searchFrom;
  while (i < html.length && depth > 0) {
    const nextOpen = html.indexOf('<div', i);
    const nextClose = html.indexOf('</div>', i);
    if (nextClose === -1) break;
    if (nextOpen !== -1 && nextOpen < nextClose) {
      depth++;
      i = nextOpen + 4;
    } else {
      depth--;
      i = nextClose + 6;
      if (depth === 0) {
        return { text: html.slice(blockStart, i), start: blockStart, end: i, type: 'div' };
      }
    }
  }
  return null;
}

function replaceChartPlaceholderBlock(html, slug, replacement) {
  const block = findChartPlaceholderBlock(html, slug);
  if (!block) return html;
  return html.slice(0, block.start) + replacement + html.slice(block.end);
}

// ─────────────────────────────────────────────────
// Arg parsing
// ─────────────────────────────────────────────────
function parseArgs() {
  const args = process.argv.slice(2);
  const out = { noRaster: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--specs')     out.specsPath = args[++i];
    else if (args[i] === '--html') out.htmlPath  = args[++i];
    else if (args[i] === '--no-raster') out.noRaster = true;
  }
  if (!out.specsPath) throw new Error('--specs path/to/specs.json is required');
  if (!out.htmlPath)  throw new Error('--html path/to/draft.html is required');
  return out;
}

// ─────────────────────────────────────────────────
// Try to import Playwright chromium (graceful degrade)
// ─────────────────────────────────────────────────
async function tryLoadPlaywright() {
  try {
    const pw = await import('playwright');
    return pw.chromium;
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────
// Rasterize SVG → PNG buffer via Playwright
// viewBox must be 1040×640; deviceScaleFactor=2 → 2080×1280 PNG
// ─────────────────────────────────────────────────
async function rasterizeSvg(chromium, svgString) {
  // Wrap SVG in a minimal HTML page for Playwright rendering
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8">
<style>*{margin:0;padding:0}body{background:#fff}</style></head>
<body>${svgString}</body></html>`;

  // Extract viewBox dimensions to set precise clip
  const vbMatch = svgString.match(/viewBox=["']0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)["']/i);
  const svgW = vbMatch ? parseFloat(vbMatch[1]) : 1040;
  const svgH = vbMatch ? parseFloat(vbMatch[2]) : 640;

  // deviceScaleFactor must be set on the BrowserContext, not on setViewportSize.
  // 1040×640 CSS px × deviceScaleFactor=2 → 2080×1280 physical pixels.
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  let pngBuf;
  try {
    const context = await browser.newContext({ deviceScaleFactor: 2 });
    const page = await context.newPage();
    await page.setViewportSize({ width: svgW, height: svgH });
    await page.setContent(html, { waitUntil: 'load' });
    pngBuf = await page.screenshot({
      clip: { x: 0, y: 0, width: svgW, height: svgH },
      type: 'png',
    });
    await context.close();
  } finally {
    await browser.close();
  }

  // Validate the PNG meets ≥2080×1280 resolution gate
  if (!pngMeetsResolution(pngBuf)) {
    const dims = pngBuf.length >= 24
      ? `${pngBuf.readUInt32BE(16)}×${pngBuf.readUInt32BE(20)}`
      : 'unknown';
    throw new Error(
      `Rasterized PNG is ${dims} — below ≥2080×1280 gate. ` +
      `Check viewBox (got ${svgW}×${svgH}) and deviceScaleFactor=2.`
    );
  }

  return pngBuf;
}

// ─────────────────────────────────────────────────
// Build an inline SVG fallback (no Playwright)
// Wraps the SVG in a chart-block div + raster-skipped note
// ─────────────────────────────────────────────────
function buildInlineSvgFallback(svgString, slug) {
  // Constrain SVG to container width so it never overflows the A4 column
  const constrainedSvg = svgString
    .replace(/(<svg[^>]*)\bwidth="[^"]*"/, '$1width="100%"')
    .replace(/(<svg[^>]*)\bheight="[^"]*"/, '$1height="auto"');
  return (
    `<!-- raster-skipped-no-chromium slug=${slug} -->\n` +
    `<div class="chart-block" data-slug="${slug}" data-raster="skipped" ` +
    `style="max-width:100%;width:100%;overflow:hidden;margin:10px 0">\n` +
    constrainedSvg + `\n</div>`
  );
}

// ─────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────
async function main() {
  const { specsPath, htmlPath, noRaster } = parseArgs();

  // Read specs JSON
  const specsAbs = path.resolve(SKILL_ROOT, specsPath);
  if (!fs.existsSync(specsAbs)) throw new Error(`specs file not found: ${specsAbs}`);
  const specsJson = JSON.parse(fs.readFileSync(specsAbs, 'utf8'));
  const figureSpecs = specsJson.figure_specs || [];

  if (figureSpecs.length === 0) {
    console.log('[render-figures] No figure_specs entries — nothing to render.');
    return;
  }

  // Read HTML
  const htmlAbs = path.resolve(SKILL_ROOT, htmlPath);
  if (!fs.existsSync(htmlAbs)) throw new Error(`HTML file not found: ${htmlAbs}`);
  let html = fs.readFileSync(htmlAbs, 'utf8');

  // Try Playwright unless --no-raster
  let chromium = null;
  if (!noRaster) {
    chromium = await tryLoadPlaywright();
    if (!chromium) {
      console.warn('[render-figures] WARNING: playwright not available — falling back to inline SVG.');
      console.warn('[render-figures] Install with: npx playwright install chromium');
    }
  }

  let rendered = 0;
  let skipped  = 0;
  const errors = [];

  for (const specRaw of figureSpecs) {
    const slug = specRaw.slug;
    if (!slug) {
      console.warn('[render-figures] SKIP: spec has no slug', JSON.stringify(specRaw).slice(0, 80));
      skipped++;
      continue;
    }

    const placeholderBlock = findChartPlaceholderBlock(html, slug);
    if (!placeholderBlock) {
      console.warn(`[render-figures] SKIP: no placeholder for slug="${slug}" (expected <!-- CHART:${slug} --> or chart-placeholder div)`);
      skipped++;
      continue;
    }
    if (placeholderBlock.type === 'div') {
      console.warn(`[render-figures] NOTE: replacing chart-placeholder div for slug="${slug}" (use <!-- CHART:${slug} --> in draft HTML)`);
    }

    // Build validated FigureSpec
    let spec;
    try {
      // Normalise: chart-builder may omit paper/product opts at top level
      const specOpts = {
        render_target: specRaw.render_target ?? 'paper',
        chart_type:    specRaw.chart_type,
        data:          specRaw.data,
        encoding: {
          x_field:      specRaw.encoding?.x_field     ?? specRaw.x_field,
          y_field:      specRaw.encoding?.y_field      ?? specRaw.y_field      ?? specRaw.value_field,
          label_field:  specRaw.encoding?.label_field  ?? specRaw.label_field  ?? specRaw.x_field,
          value_field:  specRaw.encoding?.value_field  ?? specRaw.value_field,
          series_field: specRaw.encoding?.series_field ?? specRaw.series_field ?? null,
          y2_field:     specRaw.encoding?.y2_field     ?? specRaw.y2_field     ?? null,
          unit:         specRaw.encoding?.unit         ?? specRaw.unit         ?? '',
          x_title:      specRaw.encoding?.x_title      ?? specRaw.x_title      ?? '',
          y_title:      specRaw.encoding?.y_title      ?? specRaw.y_title      ?? '',
          value_format: specRaw.encoding?.value_format ?? specRaw.value_format ?? null,
          y2_title:     specRaw.encoding?.y2_title     ?? specRaw.y2_title     ?? null,
        },
        title:       specRaw.title,
        source_note: specRaw.source_note,
        claim:       specRaw.claim ?? specRaw.title,  // fallback claim = title
        paper:       specRaw.paper   ?? (specRaw.render_target === 'product' ? null : { dimensions: 'paper-183mm' }),
        product:     specRaw.product ?? null,
      };
      spec = FigureSpec(specOpts);
    } catch (err) {
      const msg = `[render-figures] FAIL-CLOSED: FigureSpec validation failed for slug="${slug}": ${err.message}`;
      console.error(msg);
      errors.push(msg);
      // Replace placeholder with visible error comment (fail-closed, does not silently skip)
      html = replaceChartPlaceholderBlock(html, slug, `<!-- CHART-ERROR slug=${slug}: ${err.message} -->`);
      continue;
    }

    // Render SVG (deterministic, all text escaped)
    let svgString;
    try {
      svgString = renderFigure(spec);
    } catch (err) {
      const msg = `[render-figures] FAIL-CLOSED: renderFigure failed for slug="${slug}": ${err.message}`;
      console.error(msg);
      errors.push(msg);
      html = replaceChartPlaceholderBlock(html, slug, `<!-- CHART-ERROR slug=${slug}: ${err.message} -->`);
      continue;
    }

    // Rasterize or inline
    let replacement;
    if (chromium) {
      try {
        const pngBuf = await rasterizeSvg(chromium, svgString);
        const b64    = pngBuf.toString('base64');
        replacement  = `<img class="chart" src="data:image/png;base64,${b64}" alt="${slug}" style="width:100%;max-width:170mm;margin:12px auto;display:block">`;
        console.log(`[render-figures] OK (raster) slug=${slug}`);
      } catch (err) {
        const msg = `[render-figures] WARN: rasterization failed for slug="${slug}" (${err.message}) — using inline SVG fallback`;
        console.warn(msg);
        replacement = buildInlineSvgFallback(svgString, slug);
      }
    } else {
      replacement = buildInlineSvgFallback(svgString, slug);
      console.log(`[render-figures] OK (svg-fallback) slug=${slug}`);
    }

    html = replaceChartPlaceholderBlock(html, slug, replacement);
    rendered++;
  }

  // Write modified HTML back
  fs.writeFileSync(htmlAbs, html, 'utf8');

  console.log(`\n[render-figures] done: ${rendered} rendered, ${skipped} skipped, ${errors.length} errors`);
  if (errors.length > 0) {
    console.error('[render-figures] Errors:');
    for (const e of errors) console.error(' ', e);
    process.exit(1);
  }
}

main().catch(err => {
  console.error('[render-figures] FATAL:', err);
  process.exit(1);
});
