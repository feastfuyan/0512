#!/usr/bin/env node
/**
 * render-with-watermark.mjs
 *
 * macro-pdf-report-v3 门控路径专用渲染器.
 * 接 named args (--html / --output / --watermark JSON), 在 HTML 加载后注入:
 *   1. 水印 (每页右下角, 9px 浅灰)
 *   2. 封面顶部横幅 (DEGRADED 时红色警示)
 *   3. 免责声明上方嵌入 6 项评分表
 * 再调用 Playwright page.pdf() 出版.
 *
 * 用法:
 *   # PASS 路径 (无水印, 干净出版)
 *   node scripts/render-with-watermark.mjs --html draft.html --output out.pdf
 *
 *   # DEGRADED 路径 (带水印)
 *   node scripts/render-with-watermark.mjs --html draft.html --output out.pdf \
 *        --watermark '{"watermark_text":"...","cover_banner":{...},"score_table":{...}}'
 *
 * 不替代 build-pdf.mjs — 后者保持现役不动, 服务 v2 / 兼容路径.
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { esc } from "./lib/escape.mjs";

const require = createRequire(import.meta.url);
const { fixOverflow } = require("./splitOverflow.cjs");
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith("--")) {
      const key = args[i].slice(2);
      const val = args[i + 1] && !args[i + 1].startsWith("--") ? args[++i] : true;
      opts[key] = val;
    }
  }
  if (!opts.html) throw new Error("--html 必填");
  if (!opts.output) throw new Error("--output 必填");
  if (opts.watermark && typeof opts.watermark === "string") {
    opts.watermark = JSON.parse(opts.watermark);
  }
  // P1-8: enforce-gate's PASS_WITH_NOTES path passes --embed-score-table <scores-json>
  // WITHOUT --watermark. Previously this arg was unparsed and injectDegradedArtifacts
  // (gated on opts.watermark) never ran, so the score table was silently dropped.
  // Synthesize a minimal watermark object carrying only the score table (no banner,
  // no watermark text) so the existing inject path renders it.
  if (opts["embed-score-table"] && typeof opts["embed-score-table"] === "string") {
    const scoreTable = JSON.parse(opts["embed-score-table"]);
    opts.watermark = {
      ...(opts.watermark && typeof opts.watermark === "object" ? opts.watermark : {}),
      embed_score_table: true,
      score_table: scoreTable
    };
  }
  return opts;
}

// ─────────────────────────────────────────────
// 水印 / 横幅 / 评分表 注入 (在 Playwright page context 中执行)
// ─────────────────────────────────────────────
async function injectDegradedArtifacts(page, watermark) {
  if (!watermark) return;

  await page.evaluate((wm) => {
    // 1. 封面顶部红色横幅
    if (wm.cover_banner?.enabled) {
      const cover = document.querySelector(".page.cover, .cover");
      if (cover) {
        const banner = document.createElement("div");
        banner.style.cssText = `
          position: absolute; top: 0; left: 0; right: 0;
          background: ${wm.cover_banner.color || "#dc2626"};
          color: #ffffff;
          font-family: 'Noto Sans SC', 'Inter', sans-serif;
          font-size: 13px;
          font-weight: 600;
          padding: 8px 24px;
          text-align: center;
          letter-spacing: 0.5px;
          z-index: 9999;
          box-shadow: 0 2px 8px rgba(220, 38, 38, 0.3);
        `;
        banner.textContent = wm.cover_banner.text;
        cover.style.position = "relative";
        cover.insertBefore(banner, cover.firstChild);
      }
    }

    // 2. 每页右下角水印
    if (wm.watermark_text) {
      document.querySelectorAll(".page").forEach((pg) => {
        const wmEl = document.createElement("div");
        wmEl.style.cssText = `
          position: absolute;
          bottom: 6mm;
          right: 8mm;
          font-family: 'Inter', sans-serif;
          font-size: ${wm.watermark_size_px || 9}px;
          color: ${wm.watermark_color || "#9ca3af"};
          opacity: 0.85;
          pointer-events: none;
          z-index: 9998;
          letter-spacing: 0.3px;
        `;
        wmEl.textContent = wm.watermark_text;
        pg.style.position = pg.style.position || "relative";
        pg.appendChild(wmEl);
      });
    }

    // 3. 免责声明上方嵌入 6 项评分表
    // SECURITY: build table entirely via DOM APIs (textContent only).
    // No innerHTML with untrusted data — dimension keys and score values are
    // controlled inputs, but future audit comment fields must never reach innerHTML.
    if (wm.embed_score_table && wm.score_table) {
      const disclaimer =
        document.querySelector(".disclaimer") ||
        document.querySelector('[class*="disclaim"]');
      if (disclaimer) {
        // i18n labels — populated by enforce-gate.mjs from scripts/lib/i18n.mjs
        const i18n = wm.i18n || {};
        const dimNames = i18n.dimNames || {};
        const scoreHeader = i18n.scoreHeader || "Internal Audit Score Detail";
        const passText = i18n.pass || "✓ Pass";
        const failText = i18n.fail || "✗ Below 9.5";

        const container = document.createElement("div");
        container.className = "degraded-score-table";
        container.style.cssText = [
          "margin:16px 0", "padding:12px 16px",
          "border:1px solid #fca5a5", "background:#fef2f2",
          "border-radius:4px", "font-family:'Inter',sans-serif",
          "font-size:10px"
        ].join(";");

        // Header label — localized
        const hdr = document.createElement("div");
        hdr.style.cssText = "color:#991b1b;font-weight:600;margin-bottom:6px;font-size:11px";
        hdr.textContent = scoreHeader;
        container.appendChild(hdr);

        const table = document.createElement("table");
        table.style.cssText = "width:100%;border-collapse:collapse";

        // Header row — localized labels
        const headRow = table.insertRow();
        headRow.style.color = "#7f1d1d";
        [
          [i18n.colDim || "Dimension", "text-align:left;padding:2px 8px 2px 0"],
          [i18n.colMech || "Mech", "text-align:right;padding:2px 0"],
          [i18n.colLlm || "LLM", "text-align:right;padding:2px 0 2px 8px"],
          [i18n.colFused || "Fused", "text-align:right;padding:2px 0 2px 12px"],
          [i18n.colStatus || "Status",  "text-align:left;padding:2px 0 2px 12px"],
        ].forEach(([label, style]) => {
          const th = document.createElement("th");
          th.style.cssText = style;
          th.textContent = label;
          headRow.appendChild(th);
        });

        // Data rows — use textContent for all user-influenced values.
        // Guard against non-dimension keys leaking in (e.g. "lang" or "i18n"):
        // only render entries that look like a dimension score object.
        for (const [k, v] of Object.entries(wm.score_table)) {
          if (!v || typeof v !== "object" || typeof v.score !== "number") continue;
          const passed = v.passes_9_5;
          const statusColor = passed ? "#16a34a" : "#dc2626";

          const row = table.insertRow();

          const tdDim = row.insertCell();
          tdDim.style.cssText = "padding:1px 8px 1px 0";
          tdDim.textContent = dimNames[k] || k;

          const tdMech = row.insertCell();
          tdMech.style.cssText = "text-align:right;padding:1px 0";
          tdMech.textContent = (v.mechanical ?? 0).toFixed(1);

          const tdLlm = row.insertCell();
          tdLlm.style.cssText = "text-align:right;padding:1px 0 1px 8px";
          tdLlm.textContent = (v.llm ?? 0).toFixed(1);

          const tdFused = row.insertCell();
          tdFused.style.cssText = `text-align:right;padding:1px 0 1px 12px;font-weight:600;color:${statusColor}`;
          tdFused.textContent = (v.score ?? v.fused_raw ?? 0).toFixed(1);

          const tdStatus = row.insertCell();
          tdStatus.style.cssText = `padding:1px 0 1px 12px;color:${statusColor}`;
          tdStatus.textContent = passed ? passText : failText;
        }

        container.appendChild(table);
        disclaimer.parentNode.insertBefore(container, disclaimer);
      }
    }
  }, watermark);
}

// ─────────────────────────────────────────────
async function main() {
  const opts = parseArgs();
  const htmlAbs = path.resolve(opts.html);
  if (!fs.existsSync(htmlAbs)) throw new Error(`HTML 不存在: ${htmlAbs}`);

  console.log(`[render] loading ${htmlAbs}`);
  const browser = await chromium.launch({
    headless: true,
    args: [
      // Block all external network access during render.
      // The report HTML is a static local file — no legitimate outbound requests
      // are expected. This prevents an injected <script>/<img src=...> from
      // exfiltrating data from the render host in 7×24 unattended mode.
      "--host-resolver-rules=MAP * 127.0.0.1,EXCLUDE localhost",
      "--disable-background-networking",
    ],
  });
  const page = await browser.newPage();

  // Intercept and abort any non-file:// resource requests as a second layer.
  // Playwright route() fires before the browser resolves the request.
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("file://") || url.startsWith("data:")) {
      route.continue();
    } else {
      // Abort — log at debug level so CI logs stay clean.
      route.abort("blockedbyclient");
    }
  });

  await page.goto(`file://${htmlAbs}`, { waitUntil: "networkidle" });

  // 防溢出 (沿用 v2 splitOverflow) — auto-split pages that exceed A4 height
  await fixOverflow(page);

  // 注入水印 / 横幅 / 评分表
  if (opts.watermark) {
    console.log(`[render] injecting degraded artifacts (DEGRADED mode)`);
    await injectDegradedArtifacts(page, opts.watermark);
  }

  // 出 PDF
  await page.pdf({
    path: path.resolve(opts.output),
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true
  });

  await browser.close();
  console.log(`[render] PDF saved: ${opts.output}${opts.watermark ? " (DEGRADED)" : ""}`);
}

main().catch((err) => {
  console.error("[render-with-watermark]", err);
  process.exit(1);
});
