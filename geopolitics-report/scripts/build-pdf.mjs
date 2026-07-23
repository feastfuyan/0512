/**
 * build-pdf.mjs
 * MiningClaw 地缘政治报告 PDF 生成主入口
 *
 * 用法：
 *   node scripts/build-pdf.mjs [--input report-data.json] [--output output.pdf]
 *   node scripts/build-pdf.mjs input.json output.pdf   # 平台 Celery 默认调用方式
 *
 * PDF 优先从 Skill 工作区内的「主报告 HTML」生成（自动发现，不写死文件名）。
 * 发现规则与平台入库一致：优先 MiningClaw*.html，取体积最大/最新的那份。
 * 仅当找不到任何报告 HTML 时，才根据 report-data.json 回退生成简化 HTML。
 *
 * report-data.json 结构：
 *   {
 *     "title": "全球矿业宏观经济周度观察报告",
 *     "category": "宏观研究",
 *     "date": "2026.03.19",
 *     "period": "2026.03.10 — 2026.03.16",
 *     "commodities": ["gold", "copper", "uranium", "lithium"],
 *     "content_source": "/path/to/source.docx.txt",
 *     "sections": { ... }  // 可选，直接传内容
 *   }
 */

import { chromium } from 'playwright';
import { createRequire } from 'module';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
const { fixOverflow } = require('./splitOverflow.cjs');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, '..');
const REFS_ROOT  = path.join(SKILL_ROOT, 'references', 'expert-insights');
const ASSETS_DIR = path.join(SKILL_ROOT, 'assets');

/** 调试/中间产物，不作为主报告 */
const EXCLUDED_HTML_NAMES = new Set([
  'input.html', 'snapshot.html', 'uiMode.html', 'trace.html', 'playwright-report.html',
]);

/** 仓库内置样式参考模板（多份候选时加分，非强制路径） */
const PREFERRED_TEMPLATE_BASENAMES = [
  'MiningClaw__ExpertReport_Bilingual.html',
  'MiningClaw_MacroReport.html',
];

// ─────────────────────────────────────────
// CLI 参数解析（兼容 --input/--output 与 positional）
// ─────────────────────────────────────────
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    input: null,
    output: 'output.pdf',
    htmlOnly: false,
    htmlFile: null,
  };
  let positionalCount = 0;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--input') opts.input = args[++i];
    else if (a === '--output') opts.output = args[++i];
    else if (a === '--html') opts.htmlOnly = true;
    else if (a === '--html-file') opts.htmlFile = args[++i];
    else if (!a.startsWith('-')) {
      if (positionalCount === 0) opts.input = a;
      else if (positionalCount === 1) opts.output = a;
      positionalCount++;
    }
  }

  return opts;
}

function isExcludedHtmlPath(absPath) {
  const base = path.basename(absPath);
  if (EXCLUDED_HTML_NAMES.has(base)) return true;
  if (base.startsWith('.')) return true;
  const parts = absPath.split(path.sep);
  return parts.some(p => ['node_modules', 'test-results', '.playwright', 'playwright-report'].includes(p));
}

/** 是否像 MiningClaw 主报告（与 pipeline_tasks 入库规则对齐） */
function looksLikeReportHtmlName(fileName) {
  if (!fileName.endsWith('.html')) return false;
  if (fileName.startsWith('MiningClaw')) return true;
  if (/MacroReport/i.test(fileName)) return true;
  return false;
}

/** 快速检测是否为分页报告结构 */
function looksLikeReportHtmlContent(absPath) {
  try {
    const head = fs.readFileSync(absPath, { encoding: 'utf8' }).slice(0, 8192);
    return head.includes('class="page"') || head.includes("class='page'");
  } catch {
    return false;
  }
}

/**
 * 在目录中收集候选主报告 HTML（递归，跳过 node_modules 等）
 */
function collectReportHtmlCandidates(searchRoots, maxDepth = 4) {
  const found = [];
  const seenAbs = new Set();

  function walk(dir, depth) {
    if (depth > maxDepth || !fs.existsSync(dir)) return;
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const ent of entries) {
      const abs = path.join(dir, ent.name);
      if (ent.isDirectory()) {
        if (['node_modules', '.git', 'test-results', '.playwright', 'playwright-report'].includes(ent.name)) {
          continue;
        }
        walk(abs, depth + 1);
        continue;
      }
      if (!ent.name.endsWith('.html')) continue;
      if (isExcludedHtmlPath(abs)) continue;

      const stat = fs.statSync(abs);
      if (ent.name === 'index.html' && stat.size < 10 * 1024) continue;

      const byName = looksLikeReportHtmlName(ent.name);
      const byContent = looksLikeReportHtmlContent(abs);
      if (!byName && !byContent) continue;
      if (seenAbs.has(abs)) continue;
      seenAbs.add(abs);

      found.push({ abs, stat, byName, byContent });
    }
  }

  for (const root of searchRoots) {
    walk(path.resolve(root), 0);
  }
  return found;
}

/**
 * 多份候选时选「最像最终报告」的一份：显式路径 > 命名规则 > 体积 > 修改时间
 */
function pickBestReportHtml(candidates) {
  if (!candidates.length) return null;

  const scored = candidates.map(({ abs, stat, byName }) => {
    const base = path.basename(abs);
    let score = 0;
    if (byName) score += 500;
    if (PREFERRED_TEMPLATE_BASENAMES.includes(base)) score += 200;
    if (abs.startsWith(ASSETS_DIR + path.sep)) score += 300;
    if (/Bilingual/i.test(base)) score += 50;
    if (/MacroReport/i.test(base)) score += 30;
    score += stat.size / 1024;
    score += stat.mtimeMs / 1e12;
    return { abs, score, size: stat.size, mtime: stat.mtimeMs };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored[0];
}

/**
 * 解析用于转 PDF 的 HTML 路径
 * 优先级：CLI --html-file > input.json 显式字段 > 工作区内自动发现
 */
function resolveReportHtmlPath(opts, payload = {}) {
  if (opts.htmlFile) {
    const abs = path.resolve(opts.htmlFile);
    if (fs.existsSync(abs)) return abs;
    console.warn(`[build-pdf] --html-file 不存在: ${abs}`);
  }

  for (const key of ['report_html_path', 'html_path', 'html_file', 'report_html', 'html_output']) {
    if (!payload[key]) continue;
    const abs = path.isAbsolute(payload[key])
      ? payload[key]
      : path.join(SKILL_ROOT, payload[key]);
    if (fs.existsSync(abs)) {
      console.log(`[build-pdf] 使用 input.json 指定 HTML (${key})`);
      return path.resolve(abs);
    }
    console.warn(`[build-pdf] input.json.${key} 不存在: ${abs}`);
  }

  const searchRoots = [
    ASSETS_DIR,
    SKILL_ROOT,
    path.join(SKILL_ROOT, 'output'),
    path.join(SKILL_ROOT, 'dist'),
  ];
  const discovered = collectReportHtmlCandidates(searchRoots);
  if (!discovered.length) return null;

  const best = pickBestReportHtml(discovered);
  if (discovered.length > 1) {
    console.log(
      `[build-pdf] 发现 ${discovered.length} 份报告 HTML，选用: ${path.basename(best.abs)}` +
      ` (${(best.size / 1024).toFixed(1)} KB)`
    );
  }
  return best.abs;
}

/**
 * 将已有 HTML 渲染为 PDF（与 SKILL.md 一致：fixOverflow + printBackground）
 */
async function renderPdfFromHtml(htmlPath, outPath) {
  const absHtml = path.resolve(htmlPath);
  const absOut = path.resolve(outPath);

  console.log('Rendering PDF from HTML:', absHtml);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.goto(`file://${absHtml}`, {
    waitUntil: 'networkidle0',
    timeout: 120_000,
  });
  await fixOverflow(page);
  await page.pdf({
    path: absOut,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: 0, bottom: 0, left: 0, right: 0 },
  });
  await browser.close();

  const sizeKb = (fs.statSync(absOut).size / 1024).toFixed(1);
  console.log(`PDF saved: ${absOut} (${sizeKb} KB)`);
}

// ─────────────────────────────────────────
// References 加载器
// ─────────────────────────────────────────
function loadReferences(commodities = []) {
  const refs = {
    rickRule: null,
    philosophy: null,
    expressions: {},
    frameworks: {},
    commodityInsights: {}
  };

  // Rick Rule 核心内容
  const rrKeyInsights = path.join(REFS_ROOT, '01_rick-rule', 'key-insights.json');
  const rrPhilosophy  = path.join(REFS_ROOT, '01_rick-rule', 'investment-philosophy.json');
  if (fs.existsSync(rrKeyInsights))  refs.rickRule   = JSON.parse(fs.readFileSync(rrKeyInsights,  'utf-8'));
  if (fs.existsSync(rrPhilosophy))   refs.philosophy = JSON.parse(fs.readFileSync(rrPhilosophy,   'utf-8'));

  // 表达模板
  const exprDir = path.join(REFS_ROOT, '03_expression-templates');
  for (const fname of fs.readdirSync(exprDir)) {
    if (!fname.endsWith('.json')) continue;
    const key = fname.replace('.json', '');
    refs.expressions[key] = JSON.parse(fs.readFileSync(path.join(exprDir, fname), 'utf-8'));
  }

  // 分析框架
  const anaDir = path.join(REFS_ROOT, '04_analysis-frameworks');
  for (const fname of fs.readdirSync(anaDir)) {
    if (!fname.endsWith('.json')) continue;
    const key = fname.replace('.json', '');
    refs.frameworks[key] = JSON.parse(fs.readFileSync(path.join(anaDir, fname), 'utf-8'));
  }

  // 商品专项 insights（按报告涉及的商品加载）
  const coreDir = path.join(REFS_ROOT, '02_core-content');
  for (const commodity of commodities) {
    const fpath = path.join(coreDir, `${commodity}-insights.json`);
    if (fs.existsSync(fpath)) {
      refs.commodityInsights[commodity] = JSON.parse(fs.readFileSync(fpath, 'utf-8'));
    }
  }

  return refs;
}

// ─────────────────────────────────────────
// 专家引用提取（从 references 库自动拉取）
// ─────────────────────────────────────────
function pickQuotes(refs, commodity, category = 'authority_statement', count = 3) {
  const data = refs.commodityInsights[commodity];
  if (!data) return [];
  const pool = data.references_by_category?.[category] || [];
  return pool.slice(0, count).map(q => ({
    text: q.text,
    expert: q.expert,
    source: q.source_title
  }));
}

// ─────────────────────────────────────────
// HTML 构建器（核心）
// ─────────────────────────────────────────
function buildHtml(reportData, refs) {
  const { title, category, date, period, sections = {} } = reportData;

  // 从 references 自动注入专家引用
  const commodities = reportData.commodities || [];
  const injectedQuotes = {};
  for (const c of commodities) {
    injectedQuotes[c] = {
      authority:  pickQuotes(refs, c, 'authority_statement', 2),
      risk:       pickQuotes(refs, c, 'risk_assessment', 2),
      data:       pickQuotes(refs, c, 'data_citation', 2),
    };
  }

  // 加载参考模板 HTML（提取 CSS 部分复用）
  const templatePath = path.join(ASSETS_DIR, 'MiningClaw__ExpertReport_Bilingual.html');
  const templateHtml = fs.existsSync(templatePath) ? fs.readFileSync(templatePath, 'utf-8') : '';

  // 提取 CSS（<style> 块）
  const cssMatch = templateHtml.match(/<style[^>]*>([\s\S]*?)<\/style>/);
  const css = cssMatch ? cssMatch[1] : '';

  // 构建 keyPoints（报告要点）
  const keyPoints = sections.key_points || [
    '本周宏观数据显示全球经济韧性持续，大宗商品需求支撑未明显减弱',
    '资源品种分化加剧：铀、铜供给约束持续，锂、钴市场承压',
    '地缘政治风险溢价推升能源价格，建议适当配置能源板块',
  ];

  return `<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    @page { size: A4; margin: 0 }
    body { margin: 0; padding: 0; }
    .page { width: 210mm; min-height: 297mm; page-break-after: always; overflow: hidden; }
    .key-points, .data-table, .risk-box, .highlight, .disclaimer, .sb-section {
      break-inside: avoid; page-break-inside: avoid;
    }
    ${css}
  </style>
</head>
<body>

  <!-- 封面 -->
  <div class="page cover">
    <div class="glow1"></div><div class="glow2"></div><div class="glow3"></div>
    <div class="streak"></div><div class="streak2"></div>
    <div class="cover-inner">
      <div class="eyebrow">MININGCLAWD INTELLIGENCE SYSTEMS</div>
      <h1>${title}</h1>
      <div class="subtitle">${category} · AI-Powered Research</div>
      <div class="cover-meta">
        <span class="cover-date">${date}</span>
        ${period ? `<span class="cover-period">${period}</span>` : ''}
      </div>
      <div class="cover-badges">
        <span class="badge">AI GENERATED</span>
        <span class="badge">INSTITUTIONAL</span>
      </div>
    </div>
  </div>

  <!-- 报告要点 -->
  <div class="page">
    <div class="content-page">
      <div class="sidebar-col">
        <div class="page-header-bar"></div>
        <div class="sb-section">
          <div class="sb-title">本期摘要</div>
          ${keyPoints.map(p => `<div class="sb-highlight">▸ ${p.slice(0, 40)}...</div>`).join('')}
        </div>
        <div class="sb-pagenum">Page 2 / ?</div>
      </div>
      <div class="main-col">
        <div class="page-header">报告要点 <span class="badge-ai">AI GENERATED</span></div>
        <div class="key-points">
          <div class="kp-title">KEY INSIGHTS</div>
          <ul>
            ${keyPoints.map(p => `<li>${p}</li>`).join('')}
          </ul>
        </div>
        ${sections.macro_overview ? `
        <h2>一、全球宏观概览</h2>
        <p>${sections.macro_overview}</p>` : ''}
      </div>
    </div>
  </div>

  <!-- 大宗商品追踪 -->
  ${commodities.length > 0 ? `
  <div class="page">
    <div class="content-page">
      <div class="sidebar-col">
        <div class="sb-section">
          <div class="sb-title">专家观点</div>
          ${commodities.slice(0,2).flatMap(c =>
            (injectedQuotes[c]?.authority || []).slice(0,1).map(q =>
              `<div class="sb-item"><span class="comm-pill">${c.toUpperCase()}</span> ${q.expert}: "${q.text.slice(0,60)}..."</div>`
            )
          ).join('')}
        </div>
        <div class="sb-pagenum">Page 3 / ?</div>
      </div>
      <div class="main-col">
        <div class="page-header">二、大宗商品市场追踪</div>
        ${sections.commodities || '<p>（大宗商品数据待填入）</p>'}
        ${commodities.map(c => {
          const q = injectedQuotes[c]?.authority?.[0];
          return q ? `
          <div class="highlight">
            <strong>${q.expert}</strong> on ${c}: "${q.text}"
            <div style="font-size:9px;color:#94a3b8;margin-top:4px">Source: ${q.source} · Money of Mine</div>
          </div>` : '';
        }).join('')}
      </div>
    </div>
  </div>` : ''}

  <!-- 风险提示 -->
  <div class="page">
    <div class="content-page">
      <div class="sidebar-col">
        <div class="sb-section">
          <div class="sb-title">风险监控</div>
          <div class="sb-item">▼ 政策风险</div>
          <div class="sb-item">▼ 地缘风险</div>
          <div class="sb-item">● 供需风险</div>
        </div>
        <div class="sb-pagenum">Page 4 / ?</div>
      </div>
      <div class="main-col">
        <div class="page-header">三、风险提示</div>
        <div class="risk-box">
          <div class="rtitle">⚠ 主要风险因子</div>
          <ul>
            ${(sections.risks || [
              '美联储政策转向风险：利率路径不确定性仍高',
              '地缘政治供应中断：关键矿产供应链脆弱性上升',
              '大宗商品周期反转：部分品种涨幅已充分定价'
            ]).map(r => `<li>${r}</li>`).join('')}
          </ul>
        </div>
        ${sections.investment_view ? `
        <h2>四、AI评级与投资建议</h2>
        <p>${sections.investment_view}</p>` : ''}
      </div>
    </div>
  </div>

  <!-- 封底 -->
  <div class="page back-cover">
    <div class="glow1" style="top:55%;opacity:0.6"></div>
    <div class="glow2" style="bottom:auto;top:8%;opacity:0.6"></div>
    <div class="glow3" style="right:auto;left:18%;top:42%;opacity:0.45"></div>
    <div class="streak" style="top:36%"></div>
    <div class="streak2" style="top:63%"></div>
    <div class="bc-top">
      <div style="font-size:8px;color:#374151;letter-spacing:2px;text-transform:uppercase">End of Report · 报告完结</div>
      <div style="font-size:8px;color:#374151">MiningClaw Intelligence Systems</div>
    </div>
    <div class="bc-center">
      <div style="margin-top:18px">
        <span style="font-family:'Space Grotesk',sans-serif;font-weight:700;font-style:italic;font-size:30px">
          <span style="color:#fff">Mining</span><span style="color:#14b8a6">Clawd</span>
        </span>
      </div>
      <div style="font-size:10px;color:#14b8a6;letter-spacing:3.5px;text-transform:uppercase;margin-top:7px">Mining Intelligence · AI-Powered</div>
      <div class="bc-divider"></div>
      <div class="bc-info">
        <div><div class="bc-col-title">About</div><div class="bc-col-body">MiningClaw 是基于 AI 多因子模型的矿业经济研究平台。</div></div>
        <div><div class="bc-col-title">Coverage</div><div class="bc-col-body"><strong>宏观研究</strong> · 大宗商品</strong> · <strong>矿业投资</strong></div></div>
        <div><div class="bc-col-title">Frequency</div><div class="bc-col-body">周报 / 月报 / 专题</div></div>
      </div>
    </div>
    <div class="bc-bottom">
      <div class="disclaimer">本报告由 AI 自动生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。</div>
      <div style="font-size:7px;color:#374151;margin-top:6px">© ${new Date().getFullYear()} MiningClaw Intelligence Systems · All Rights Reserved</div>
    </div>
  </div>

</body>
</html>`;
}

// ─── Main ────────────────────────────────────────────────────────────────────
async function main() {
  const opts = parseArgs();

  let payload = {};
  if (opts.input && fs.existsSync(opts.input)) {
    try {
      payload = JSON.parse(fs.readFileSync(opts.input, 'utf8'));
    } catch (e) {
      console.warn(`[build-pdf] input.json 解析失败，将仅使用双语 HTML: ${e.message}`);
    }
  }

  let htmlPath = resolveReportHtmlPath(opts, payload);

  if (!htmlPath) {
    if (!opts.input || !fs.existsSync(opts.input)) {
      console.error(
        '未找到报告 HTML。请在 assets/ 或 Skill 根目录放置 MiningClaw*.html / *MacroReport*.html，' +
        '或在 input.json 中设置 report_html_path，或使用 --html-file。'
      );
      process.exit(1);
    }

    const refs = loadReferences(payload.commodities || []);
    const generated = buildHtml(payload, refs);
    htmlPath = path.join(
      path.dirname(path.resolve(opts.input)),
      path.basename(opts.input, path.extname(opts.input)) + '.generated.html'
    );
    fs.writeFileSync(htmlPath, generated, 'utf8');
    console.log('[build-pdf] 回退：由 report-data.json 生成简化 HTML →', htmlPath);
    if (payload.title) console.log('[build-pdf] 报告标题:', payload.title);
  } else {
    console.log('[build-pdf] 使用主报告 HTML（与预览一致）→', htmlPath);
    if (payload.title) console.log('[build-pdf] input.json 标题:', payload.title);
  }

  if (opts.htmlOnly) {
    console.log('[build-pdf] --html 模式，跳过 PDF');
    return;
  }

  await renderPdfFromHtml(htmlPath, opts.output);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
