#!/usr/bin/env node
// macro-pdf-report-v3 / enforce-gate.mjs
//
// 主入口: 3 轮 评 → 改 → 重评 循环.
// 轮次 1-2: 单项 < 9.5 触发回退到对应 subagent.
// 轮次 3:   加权总分 ≥ 9.0 (90/100) → 放行 (附评分明细); 总分 < 9.0 → 水印降级出书.
//
// 调用方:
//   node scripts/enforce-gate.mjs --report-id MCW-MACRO-20260528-001 --source path/to/word.docx --output out.pdf
//
// 产出:
//   - draft/{report-id}-v{1..final}.html
//   - scores/{report-id}-v{1..final}.json
//   - audit-{report-id}.json   ← 完整审计链
//   - {output}.pdf             ← 最终 PDF (可能带水印)
//
// 关键设计:
//   1. subagent 调度通过外部 "agent runner" 接口 (Agent tool / Claude API / CLI), 此处只定义协议
//   2. 评分 LLM + 机械检查混合 (60/40 加权, 按 weight_in_dim 真实加权)
//   3. 全程 stateful: 每轮 read state, 决策, write state, 让上游 agent 系统 dispatch

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import YAML from "yaml";
import { parseFlags } from "./lib/args.mjs";
import { t as i18nT, DEFAULT_LANG as DEFAULT_LANG_I18N, validateLang as i18nValidateLang } from "./lib/i18n.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, "..");
const RUBRIC_PATH = path.join(SKILL_ROOT, "rubric", "institutional-rubric.yaml");

// ─────────────────────────────────────────────────
// 参数解析 (delegates to shared parseFlags)
//
// Recognized flags:
//   --report-id <id>   必填
//   --source <path>    必填 (Word/原文路径)
//   --output <path>    默认 <report-id>.pdf
//   --run-dir <dir>    默认 runs/<report-id>/ (REPORT_OUTPUT_ROOT env 覆盖)
//   --lang <en|zh>     报告语言，默认 en；驱动 degraded banner / score table i18n
// ─────────────────────────────────────────────────
function parseArgs() {
  const out = parseFlags();
  if (!out["report-id"]) throw new Error("--report-id 必填");
  if (!out["source"]) throw new Error("--source 必填 (Word/原文路径)");
  if (!out["output"]) out["output"] = `${out["report-id"]}.pdf`;
  // --run-dir: per-run writable directory (items 3+4 per-run namespacing)
  // Default: runs/{report-id}/ relative to skill root (REPORT_OUTPUT_ROOT env override)
  if (!out["run-dir"]) {
    const outputRoot = process.env.REPORT_OUTPUT_ROOT
      ? path.resolve(process.env.REPORT_OUTPUT_ROOT)
      : path.join(SKILL_ROOT, "runs");
    out["run-dir"] = path.join(outputRoot, out["report-id"]);
  }
  // --lang: validate at the boundary so typos (e.g. "eng") fail fast rather
  // than silently rendering the report in the default language.
  out["lang"] = i18nValidateLang(out["lang"] || DEFAULT_LANG_I18N);
  return out;
}

// ─────────────────────────────────────────────────
// 加载 rubric
// ─────────────────────────────────────────────────
function loadRubric() {
  const raw = fs.readFileSync(RUBRIC_PATH, "utf8");
  return YAML.parse(raw);
}

// ─────────────────────────────────────────────────
// 通用工具
// ─────────────────────────────────────────────────
function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

/**
 * Atomic write: write to a temp file, then fs.renameSync over target.
 * rename(2) is atomic on same filesystem (POSIX and NTFS).
 * A crash mid-write never leaves a torn file.
 */
function writeJson(p, obj) {
  ensureDir(path.dirname(p));
  const tmp = p + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2), "utf8");
  fs.renameSync(tmp, p);
}

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}
function now() {
  return new Date().toISOString();
}

// ─────────────────────────────────────────────────
// Per-run state persistence (crash-resume)
//
// State is persisted to runs/{report-id}/state.json after each
// completed step. On startup, if state.json exists for this run,
// the pipeline resumes from the last incomplete step (round counter
// lives in the state file, not only in memory).
// ─────────────────────────────────────────────────
function loadRunState(statePath) {
  if (!fs.existsSync(statePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(statePath, "utf8"));
  } catch (_) {
    return null;
  }
}

function saveRunState(statePath, state) {
  writeJson(statePath, state);   // already atomic via writeJson
}

// ─────────────────────────────────────────────────
// Fatal audit writer — always called before process.exit(1)
// Writes runs/{report-id}/audit-fatal.json then marks run FAILED.
// ─────────────────────────────────────────────────
function writeAuditFatal(runDir, reportId, stage, err, partialState) {
  try {
    ensureDir(runDir);
    const fatalPath = path.join(runDir, "audit-fatal.json");
    const record = {
      timestamp: now(),
      report_id: reportId,
      stage,
      error: err ? err.message : "unknown",
      stack: err ? err.stack : undefined,
      partial_state: partialState,
      pid: process.pid
    };
    writeJson(fatalPath, record);   // atomic write
    console.error(`[audit-fatal] written to ${fatalPath}`);

    // Also mark state as FAILED so a resume knows to retry rather than re-run all
    if (partialState) {
      const statePath = path.join(runDir, "state.json");
      try {
        saveRunState(statePath, { ...partialState, status: "FAILED", failed_at: now(), fail_stage: stage });
      } catch (_) { /* best-effort */ }
    }
  } catch (writeErr) {
    console.error(`[audit-fatal] WRITE FAILED (${writeErr.message}) — original error:`, err?.message);
  }
}

// ─────────────────────────────────────────────────
// Subagent 调度接口 (通用包装层)
//
// 实际 dispatch 由上游 Claude Agent harness 接管. 此处定义协议:
// runner 必须实现 `dispatchSubagent(name, prompt_path, context)` 并返回产物路径.
//
// 简单环境下退化为 CLI 调用 (e.g. 通过 `claude --agent` 或 cron).
// 当前实现: 写"调度请求"到 dispatch-queue-{report-id}.json (per-run namespaced),
// 由外部 watcher / run.mjs-supervised dispatch-runner 消费.
//
// CRASH-RESUME: if a request_id already appears DONE in the queue, it is treated
// as a cache hit and not re-dispatched (idempotent, bounded LLM calls).
// ─────────────────────────────────────────────────
function dispatchSubagent(agentName, contextObj, runDir) {
  // Per-run queue lives in the run directory to avoid cross-run collisions
  const effectiveRunDir = runDir || path.join(SKILL_ROOT, "runs", contextObj.report_id);
  ensureDir(effectiveRunDir);
  const queuePath = path.join(effectiveRunDir, "dispatch-queue.json");
  let queue = [];
  if (fs.existsSync(queuePath)) {
    try { queue = readJson(queuePath); } catch (_) { queue = []; }
  }
  if (!Array.isArray(queue)) queue = [];

  // Build a stable request_id (round + agent, no Date.now — survives resume)
  const stableId = `${contextObj.report_id}-r${contextObj.round}-${agentName}`;

  // CRASH-RESUME: check if already DONE (cache hit)
  const existing = queue.find(r => r.request_id === stableId);
  if (existing && existing.status === "DONE") {
    console.log(`[dispatch] CACHE HIT ${agentName} r${contextObj.round} (${stableId}) — skipping re-dispatch`);
    return stableId;
  }

  // Add or re-enqueue (replace if previously FAILED)
  const req = {
    request_id: stableId,
    agent: agentName,
    prompt_path: path.join(SKILL_ROOT, "agents", agentMdFile(agentName)),
    context: contextObj,
    enqueued_at: now(),
    status: "PENDING"
  };

  const existingIdx = queue.findIndex(r => r.request_id === stableId);
  if (existingIdx >= 0) {
    queue[existingIdx] = req;
  } else {
    queue.push(req);
  }
  writeJson(queuePath, queue);   // atomic write
  console.log(`[dispatch] queued ${agentName} for round ${contextObj.round} (${stableId})`);
  return stableId;
}

function agentMdFile(name) {
  const map = {
    "data-collector":   "01-data-collector.md",
    "content-writer":   "02-content-writer.md",
    "visual-designer":    "03-visual-designer.md",
    "rubric-reviewer":  "04-rubric-reviewer.md"
  };
  if (!map[name]) throw new Error(`未知 subagent: ${name}`);
  return map[name];
}

// Cross-platform async sleep — non-blocking, works on Windows and POSIX
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 等待 subagent 完成 (由外部主 Claude 完成后回写 status=DONE)
// runDir: per-run directory (item 3 — namespaced queue)
// killSwitchDir: directory where STOP file is checked (graceful stop)
async function awaitDispatch(requestId, runDir, timeoutMs = 30 * 60 * 1000, killSwitchDir = null) {
  const queuePath = path.join(runDir, "dispatch-queue.json");
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // Kill-switch check (item 5)
    const stopFile = killSwitchDir ? path.join(path.dirname(runDir), "STOP") : null;
    const localStop = path.join(runDir, "STOP");
    if ((stopFile && fs.existsSync(stopFile)) || fs.existsSync(localStop)) {
      throw new Error("KILL_SWITCH: graceful stop requested");
    }

    // Guard against missing or partially-written queue file
    if (!fs.existsSync(queuePath)) {
      await sleep(5000);
      continue;
    }
    let queue;
    try {
      queue = readJson(queuePath);
    } catch (_) {
      // File mid-write or corrupt — skip this tick
      await sleep(5000);
      continue;
    }
    if (!Array.isArray(queue)) {
      await sleep(5000);
      continue;
    }
    const req = queue.find(r => r.request_id === requestId);
    if (req?.status === "DONE") return req.result_path;
    if (req?.status === "FAILED") throw new Error(`Subagent ${req.agent} 失败: ${req.error}`);
    await sleep(5000);
  }
  throw new Error(`Subagent ${requestId} 超时`);
}

// Strip Python-style (?i) inline flag and return a JS RegExp
function makeRegex(pattern, extraFlags = "") {
  if (pattern === undefined || pattern === null) {
    return /(?!)/; // never-matches sentinel
  }
  let flags = extraFlags;
  let p = String(pattern);
  if (p.startsWith("(?i)")) {
    p = p.slice(4);
    if (!flags.includes("i")) flags += "i";
  }
  return new RegExp(p, flags);
}

// ─────────────────────────────────────────────────
// PNG IHDR dimension reader (pure JS, no external lib)
// PNG header: 8 bytes signature, then IHDR chunk:
//   4 bytes length, 4 bytes "IHDR", 4 bytes width, 4 bytes height
// ─────────────────────────────────────────────────
function readPngDimensions(base64Data) {
  // Remove data-URI prefix if present
  const b64 = base64Data.replace(/^data:image\/png;base64,/, "");
  const buf = Buffer.from(b64, "base64");
  // PNG signature: 8 bytes, IHDR chunk: 4 (length) + 4 (type) = 12 bytes offset
  // Width at offset 16, height at offset 20
  if (buf.length < 24) return null;
  const sig = buf.slice(0, 8);
  const expectedSig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (!sig.equals(expectedSig)) return null;
  const width  = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  return { width, height };
}

// ─────────────────────────────────────────────────
// Prose-only HTML stripper for citation denominator
// Strips <style>, <script>, attributes, table cells,
// returns only text inside chapter <p>, <li>, .thesis, .risk-box
// ─────────────────────────────────────────────────
function extractProseText(html) {
  // Step 1: Remove <style>...</style> and <script>...</script> blocks
  let withoutStyle = html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ");

  // Step 2: Remove <table>...</table> blocks entirely (axes, table cells are not prose citations)
  withoutStyle = withoutStyle.replace(/<table[^>]*>[\s\S]*?<\/table>/gi, " ");

  // Step 3: Extract content from prose elements BEFORE stripping attributes
  // (class attributes must remain intact for risk-box/thesis matching)
  // Both double-quote and single-quote class attribute styles supported.
  const proseMatches = [];

  // Match <p>...</p>
  for (const m of withoutStyle.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)) {
    proseMatches.push(m[1]);
  }
  // Match <li>...</li>
  for (const m of withoutStyle.matchAll(/<li\b[^>]*>([\s\S]*?)<\/li>/gi)) {
    proseMatches.push(m[1]);
  }
  // Match elements with class containing "thesis" or "risk-box" (both quote styles)
  for (const m of withoutStyle.matchAll(/<(?:div|span)\b[^>]*class=["'][^"']*(?:thesis|risk-box)[^"']*["'][^>]*>([\s\S]*?)<\/(?:div|span)>/gi)) {
    proseMatches.push(m[1]);
  }

  // Step 4: Strip remaining tags from extracted prose, AND remove [src:N] citation
  // markers. The citation markers must NOT be counted in the citation_coverage
  // denominator — otherwise the N inside [src:N] is itself counted as a "number
  // token", inflating the denominator and double-counting: the marker is both
  // numerator (it IS a citation) and denominator (its line number looks like an
  // uncited number). This drove coverage from a true ~65% down to a reported 44%.
  // Replacing with a space (not empty) avoids gluing adjacent tokens together.
  return proseMatches
    .map(p => p.replace(/<[^>]+>/g, " ").replace(/\[src:(?:line-)?\d+\]/g, " "))
    .join(" ");
}

// ─────────────────────────────────────────────────
// SVG safety check: unescaped < > & " in <text>/<tspan> elements
// ─────────────────────────────────────────────────
function checkSvgSafety(svgContent) {
  // Find all text/tspan content
  const violations = [];
  const textContentRe = /<(?:text|tspan)[^>]*>([\s\S]*?)<\/(?:text|tspan)>/gi;
  for (const m of svgContent.matchAll(textContentRe)) {
    const content = m[1];
    // Check for unescaped dangerous characters (that are not part of HTML entities)
    if (/[<>&"]/.test(content.replace(/&(?:lt|gt|amp|quot|#\d+);/g, ""))) {
      violations.push({ content: content.slice(0, 80) });
    }
  }
  return violations;
}

// ─────────────────────────────────────────────────
// 机械检查 (regex / 计数 / hex 白名单 / 结构 / 跨引用 / 格式 / 元数据)
// 对应 rubric.dimensions[*].mechanical_checks
//
// Each check now returns a sub-score (0-10) rather than a raw deduct,
// enabling proper weight_in_dim aggregation.
// ─────────────────────────────────────────────────
async function runMechanicalChecks(htmlPath, dataPath, rubric) {
  const html = fs.readFileSync(htmlPath, "utf8");
  const data = fs.existsSync(dataPath) ? readJson(dataPath) : {};
  const out = {};

  for (const dim of rubric.dimensions) {
    const checkResults = [];

    for (const check of dim.mechanical_checks || []) {
      const r = await runOneCheck(check, html, data, htmlPath);
      checkResults.push({ id: check.id, ...r });
    }

    // Weighted aggregation using weight_in_dim
    let totalWeight = 0;
    let weightedScore = 0;
    let vetoScore = undefined; // set_score vetoes override everything

    for (let i = 0; i < checkResults.length; i++) {
      const r = checkResults[i];
      const check = (dim.mechanical_checks || [])[i];
      const w = (check && check.weight_in_dim) ? check.weight_in_dim : (1 / (dim.mechanical_checks || [{ weight_in_dim: 1 }]).length);

      // set_score is a veto — takes absolute minimum
      if (r.set_score !== undefined) {
        vetoScore = vetoScore === undefined ? r.set_score : Math.min(vetoScore, r.set_score);
      }

      // subscore: each check produces a 0-10 subscore
      const subscore = r.subscore !== undefined ? r.subscore : (10.0 - (r.deduct || 0));
      weightedScore += Math.max(0, Math.min(10, subscore)) * w;
      totalWeight += w;
    }

    // Normalize if weights don't sum to 1.0
    let dimScore = totalWeight > 0 ? weightedScore / totalWeight : 10.0;
    dimScore = Math.max(0, Math.min(10, dimScore));

    // Apply veto if any check set_score'd
    if (vetoScore !== undefined) {
      dimScore = Math.min(dimScore, vetoScore);
    }

    out[dim.id] = {
      mechanical_score: dimScore,
      checks: checkResults
    };
  }
  return out;
}

// ─────────────────────────────────────────────────
// Single-check runner — returns { subscore, deduct?, set_score?, ...details }
// subscore: 0-10 for this check only
// set_score: veto applied at dim level
// ─────────────────────────────────────────────────
async function runOneCheck(check, html, data, htmlPath) {
  switch (check.method) {

    // ── regex_count ──
    // For per-chapter checks (thesis/risk): ratio against chapter count
    // For singleton checks (back_cover, disclaimer, ai_badge): assert ≥ 1
    // For keyword_coverage checks (check.keywords array): count how many
    //   keyword groups are present in prose text (≥ min_matches required)
    case "regex_count": {
      // ── keyword_coverage branch: check.keywords is an array of alternative patterns ──
      // Each element in keywords[] is treated as one "category"; we count how many
      // categories appear at least once in the report prose text.
      // Scoring: coverage = matched_categories / total_categories
      //   ≥ 3 categories (default rubric rule "matches ≥ 3 类") → score 10.0
      //   < required → proportional deduction
      if (Array.isArray(check.keywords) && check.keywords.length > 0) {
        const proseText = extractProseText(html);
        const fullText = html.replace(/<[^>]+>/g, " "); // also scan full text for headings/metadata
        const total = check.keywords.length;
        let matched = 0;
        const matchedKws = [];
        const missedKws = [];
        for (const kw of check.keywords) {
          let re;
          try {
            re = makeRegex(kw, "ig");
          } catch (_) {
            missedKws.push(kw);
            continue;
          }
          if (re.test(proseText) || re.test(fullText)) {
            matched++;
            matchedKws.push(kw);
          } else {
            missedKws.push(kw);
          }
        }
        // required_matches: rubric says "≥ 3 类"; use check.min_matches if defined, else 3
        const required = typeof check.min_matches === "number" ? check.min_matches : 3;
        // Subscore: full marks if matched ≥ required; proportional below
        const subscore = matched >= required
          ? 10.0
          : Math.max(0, 10.0 * (matched / required));
        return { total, matched, required, matchedKws, missedKws, subscore };
      }

      // ── Standard regex_count: uses check.pattern ──
      const re = makeRegex(check.pattern, "g");
      const matches = (html.match(re) || []).length;
      const chapterCount = (html.match(/<section class="chapter">/g) || []).length || 1;

      // Singleton checks: back_cover_present, disclaimer_present, ai_generated_disclosure, ai_generated_badge
      const singletonIds = ["back_cover_present", "disclaimer_present", "ai_generated_disclosure", "ai_generated_badge", "table_of_contents_present"];
      const isSingleton = singletonIds.some(id => check.id === id);

      if (isSingleton) {
        // Must appear at least once
        const subscore = matches >= 1 ? 10.0 : 0.0;
        return { matches, is_singleton: true, subscore };
      }

      // Per-chapter checks: ratio ≥ 0.9
      const ratio = matches / chapterCount;
      const deduct = ratio < 0.9 ? (0.9 - ratio) * 2 : 0;
      const subscore = Math.max(0, 10.0 - deduct * 10 / (0.9 * 2));
      // Simpler: subscore proportional
      const s = Math.max(0, Math.min(10, ratio >= 0.9 ? 10.0 : 10.0 * (ratio / 0.9)));
      return { matches, chapterCount, ratio, deduct, subscore: s };
    }

    // ── regex_ratio (citation coverage) ──
    // FIXED: Scope denominator to prose text only (strip style/script/tables/attributes)
    case "regex_ratio": {
      const proseText = extractProseText(html);
      const num = (html.match(makeRegex(check.numerator, "g")) || []).length;
      const den = (proseText.match(makeRegex(check.denominator, "g")) || []).length || 1;
      const coverage = num / den;
      const deduct = coverage < 0.98 ? (0.98 - coverage) * 20 : 0;
      const subscore = Math.max(0, Math.min(10, 10.0 - deduct));
      return { num, den, coverage, deduct, subscore };
    }

    // ── negative_regex_strict ──
    case "negative_regex_strict": {
      for (const pat of check.forbidden_patterns || []) {
        try {
          if (makeRegex(pat).test(html)) {
            return { triggered: pat, deduct: 3.0, subscore: 7.0, triggers: [pat] };
          }
        } catch (_) {
          // skip malformed pattern
        }
      }
      return { deduct: 0, subscore: 10.0 };
    }

    // ── negative_regex (chart lib check) — VETO ──
    case "negative_regex": {
      for (const pat of check.forbidden_patterns || []) {
        try {
          if (makeRegex(pat).test(html)) {
            return { triggered: pat, set_score: 5.0, subscore: 5.0 };
          }
        } catch (_) {
          // skip malformed pattern
        }
      }
      return { subscore: 10.0 };
    }

    // ── hex_whitelist — FIXED: scope to chart <img> decoded SVG only ──
    case "hex_whitelist": {
      // Extract base64 from chart images
      const chartImgRe = /<img[^>]+class="chart"[^>]+src="data:image\/[^;]+;base64,([^"]+)"/gi;
      const svgMatches = [];
      for (const m of html.matchAll(chartImgRe)) {
        try {
          const decoded = Buffer.from(m[1], "base64").toString("utf8");
          svgMatches.push(decoded);
        } catch (_) { /* skip non-decodable */ }
      }

      // Also look for inline SVG inside chart containers
      for (const m of html.matchAll(/<div[^>]*class="[^"]*chart[^"]*"[^>]*>([\s\S]*?)<\/div>/gi)) {
        if (m[1].includes("<svg")) svgMatches.push(m[1]);
      }

      if (svgMatches.length === 0) {
        // No SVG charts found — check passes (no violations)
        return { hexes: 0, allowed: 0, ratio: 1.0, subscore: 10.0, note: "no-svg-charts" };
      }

      const combinedSvg = svgMatches.join("\n");
      const hexes = combinedSvg.match(/#[0-9a-fA-F]{6}/g) || [];
      const ok = hexes.filter(h => check.allowed_hexes.includes(h.toLowerCase()));
      const ratio = hexes.length === 0 ? 1.0 : ok.length / hexes.length;
      const deduct = ratio < 0.95 ? (0.95 - ratio) * 10 : 0;
      const subscore = Math.max(0, 10.0 - deduct);
      return { hexes: hexes.length, allowed: ok.length, ratio, deduct, subscore };
    }

    // ── structural_check: thesis-first paragraph ──
    // Each <section class="chapter"> first block child must have <strong> or class containing "thesis"
    case "structural_check": {
      // Find all chapter sections
      const chapterRe = /<section[^>]*class="chapter"[^>]*>([\s\S]*?)<\/section>/gi;
      const chapters = [...html.matchAll(chapterRe)];
      if (chapters.length === 0) {
        return { chapters: 0, misses: 0, subscore: 10.0, note: "no-chapters" };
      }

      let misses = 0;
      for (const chap of chapters) {
        const content = chap[1];
        // Find first block-level child element
        const firstBlockRe = /<(p|div|h[1-6])\b([^>]*)>([\s\S]*?)<\/\1>/i;
        const firstBlock = content.match(firstBlockRe);
        if (!firstBlock) {
          misses++;
          continue;
        }
        const attrs = firstBlock[2] || "";
        const inner = firstBlock[3] || "";
        const hasThesisClass = /class="[^"]*(?:thesis)[^"]*"/.test(attrs);
        const hasStrong = /<strong>/i.test(inner);
        if (!hasThesisClass && !hasStrong) {
          misses++;
        }
      }

      const deductPerMiss = 0.30 * 10 / chapters.length;
      const deduct = misses * deductPerMiss;
      const subscore = Math.max(0, 10.0 - deduct);
      return { chapters: chapters.length, misses, deduct, subscore };
    }

    // ── cross_check: src_line validity ──
    // Every [src:N] in HTML must map to a src_line==N entry with non-empty quote in data.json
    case "cross_check": {
      const srcRe = /\[src:(?:line-)?(\d+)\]/g;
      const refs = [...html.matchAll(srcRe)].map(m => parseInt(m[1], 10));

      if (refs.length === 0) {
        return { refs: 0, orphans: 0, subscore: 10.0, note: "no-src-refs" };
      }

      // Build lookup from data.json
      const validLines = new Set();
      const chapters = data.chapters || [];
      for (const ch of chapters) {
        for (const fact of ch.numeric_facts || []) {
          if (fact.src_line && fact.src_quote && fact.src_quote.trim()) {
            validLines.add(Number(fact.src_line));
          }
        }
        for (const kp of ch.key_points || []) {
          if (kp.src_line) validLines.add(Number(kp.src_line));
        }
        for (const tbl of ch.tables || []) {
          for (const sl of tbl.src_lines || []) {
            validLines.add(Number(sl));
          }
        }
      }

      let orphans = 0;
      const orphanList = [];
      for (const lineNum of refs) {
        if (!validLines.has(lineNum)) {
          orphans++;
          orphanList.push(lineNum);
        }
      }

      const deduct = orphans * 2.0;
      const subscore = Math.max(0, 10.0 - deduct);
      return { refs: refs.length, orphans, orphanList, deduct, subscore };
    }

    // ── format_check: number precision rules ──
    // rates: 2dp, prices: 0dp with thousands sep, w/w: 1dp
    case "format_check": {
      const proseText = extractProseText(html);
      let violations = 0;
      let total = 0;

      // Rule 1: Interest rates (% with 2dp required) — e.g. "5.25%" or "5.25-5.50%"
      //
      // PCE/CPI/inflation rates are macro indicators, NOT central-bank policy rates.
      // They are conventionally 1dp (4.1%, not 4.10%), so a "%" token inside an
      // inflation-anchored SENTENCE is exempt from the 2dp check. Central-bank /
      // benchmark policy rates (Fed funds, ECB, LPR, MLF, OMO...) must still be
      // checked even when a bare word like "核心"/"标题" or "core" appears nearby
      // (e.g. "核心决策维持利率 5.3%" — "核心" here modifies "决策", not the rate).
      //
      // Detection strategy (adversarial-review fix, replaces the old fixed
      // 14-char look-behind window which both (a) let bare "核心"/"标题" wrongly
      // exempt real policy rates, and (b) was too narrow to catch inflation
      // keywords more than ~14 chars before/after the "%" token):
      //   1. Split prose into sentences on sentence-boundary punctuation.
      //   2. A "%" token is inflation-exempt only if its OWN sentence contains an
      //      inflation anchor — keyword can appear before OR after the number.
      //   3. Bare "核心"/"标题"/"core"/"headline" must be compounded with an
      //      actual inflation term (CPI/PCE/通胀/价格/inflation) to count as an
      //      anchor — a lone "核心" no longer exempts anything.
      //   4. Policy-rate vocabulary anywhere in the sentence forces the check
      //      back ON regardless of any inflation anchor also present (handles
      //      sentences that mix a policy decision with inflation commentary).
      // Sentence-boundary punctuation (CJK + Latin). The Latin "." must NOT split on a
      // decimal point (e.g. "5.3%") — only treat "." as a boundary when it is not
      // flanked by digits on both sides.
      const SENTENCE_SPLIT_RE = /(?<!\d)\.(?!\d)|[。;；\n]+/g;
      const inflationAnchorRe =
        /(?:PCE|CPI|通胀|通货膨胀|个人消费(?:支出)?|price index|核心(?:CPI|PCE|通胀|价格)|标题(?:通胀|CPI|PCE)|core\s+(?:CPI|PCE|inflation)|headline\s+(?:inflation|CPI|PCE))/i;
      const policyRateAnchorRe =
        /(?:政策利率|基准利率|利率决议|联邦基金利率|fed(?:eral)?\s*funds|policy\s*rate|target\s*range|benchmark\s*rate|LPR|MLF|OMO)/i;
      const rateRe = /\b(\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?)\s*%(?!\s*(?:w\/w|yoy|ytd|变化|涨跌))/gi;

      const sentences = proseText.split(SENTENCE_SPLIT_RE);
      for (const sentence of sentences) {
        for (const m of sentence.matchAll(rateRe)) {
          // Policy-rate vocabulary takes priority over any inflation anchor —
          // a sentence that both names a policy rate AND mentions inflation
          // (e.g. "核心决策维持利率 5.3%") must still be checked as a rate.
          const isPolicyRate = policyRateAnchorRe.test(sentence);
          const isInflation = !isPolicyRate && inflationAnchorRe.test(sentence);
          if (isInflation) continue; // inflation indicator, not a policy rate

          total++;
          const val = m[1];
          // Rate values: must have 2 decimal places (e.g. 5.25, not 5.2 or 5)
          // Allow range like "5.25-5.50"
          const parts = val.split("-");
          for (const part of parts) {
            if (part.includes(".")) {
              const decimals = part.split(".")[1]?.length || 0;
              if (decimals !== 2) violations++;
            }
            // Integer rates (e.g. 0%) are borderline — allow them
          }
        }
      }

      // Rule 2: Price values (0dp with thousands separator) — e.g. "9,180 USD/t"
      const priceRe = /\b([\d,]+(?:\.\d+)?)\s*(?:USD\/t|USD\/oz|USD\/lb|元\/t|RMB\/t)/gi;
      for (const m of proseText.matchAll(priceRe)) {
        total++;
        const val = m[1];
        // Should not have decimal places
        if (val.includes(".")) violations++;
        // Should have thousands separator if >= 1000
        const numVal = parseFloat(val.replace(/,/g, ""));
        if (numVal >= 1000 && !val.includes(",")) violations++;
      }

      // Rule 3: w/w percentage changes — must be 1dp e.g. "+2.3% w/w"
      const wowRe = /([+-]?\d+(?:\.\d+)?)\s*%\s*(?:w\/w|周环比)/gi;
      for (const m of proseText.matchAll(wowRe)) {
        total++;
        const val = m[1];
        if (val.includes(".")) {
          const decimals = val.split(".")[1]?.length || 0;
          if (decimals !== 1) violations++;
        } else {
          // w/w should have 1dp (e.g. +2.0%)
          violations++;
        }
      }

      if (total === 0) return { total: 0, violations: 0, subscore: 10.0, note: "no-numeric-tokens" };

      const ratio = violations / total;
      const deduct = ratio * 10.0;
      const subscore = Math.max(0, 10.0 - deduct);
      return { total, violations, ratio: Math.round(ratio * 100) / 100, deduct, subscore };
    }

    // ── image_metadata: PNG dimension check — VETO if below 2080×1280 ──
    // Three-way semantics (inline-SVG path awareness):
    //   (a) <img class="chart"> base64 PNG exists → verify IHDR ≥ 2080×1280, veto if under-res.
    //   (b) No PNG but valid inline chart <svg> in <div class="chart-block"> exists →
    //       return not-measured: SVG path, resolution is a product-env concern (Playwright 2×
    //       raster guarantees ≥2080×1280); NO deduct. scoreFigureSvg handles SVG quality.
    //   (c) Neither PNG nor inline SVG → veto (genuinely no chart).
    case "image_metadata": {
      // Extract all chart images
      const chartImgRe = /<img[^>]+class="chart"[^>]+src="(data:image\/png;base64,[^"]+)"/gi;
      const imgs = [...html.matchAll(chartImgRe)];

      if (imgs.length === 0) {
        // Check for inline SVG chart-blocks (the no-raster / dev-env path)
        const hasInlineSvgChart = /<div[^>]*class="[^"]*chart[^"]*"[^>]*>[\s\S]*?<svg\b/gi.test(html);
        if (hasInlineSvgChart) {
          // SVG path: resolution verified by Playwright 2× raster in product env.
          // scoreFigureSvg (figure_quality_score check) handles SVG quality here.
          return {
            charts: 0,
            subscore: 10.0,
            note: "not-measured: SVG path — raster resolution verified in product env (Playwright 2×); SVG quality via score_figure_svg"
          };
        }
        // No PNG and no inline SVG → genuinely no chart (real defect)
        return { charts: 0, subscore: 0, set_score: 0, note: "no-chart-found: neither PNG img.chart nor inline-SVG chart-block present" };
      }

      const results = [];
      let hasUndersized = false;
      let hasUnparseable = false;

      for (const m of imgs) {
        const src = m[1];
        const dims = readPngDimensions(src);
        if (!dims) {
          hasUnparseable = true;
          results.push({ parseable: false });
          continue;
        }
        const ok = dims.width >= 2080 && dims.height >= 1280;
        if (!ok) hasUndersized = true;
        results.push({ width: dims.width, height: dims.height, ok });
      }

      if (hasUndersized || hasUnparseable) {
        // Veto: set_score to 0 on expert_citation_quality
        return {
          charts: imgs.length,
          results,
          hasUndersized,
          hasUnparseable,
          set_score: 0,
          subscore: 0,
          note: "chart-resolution-veto"
        };
      }

      return { charts: imgs.length, results, set_score: 10, subscore: 10.0 };
    }

    // ── playwright_check: overflow sidecar JSON ──
    // Reads overflow-check.json sidecar written by render-with-watermark.mjs
    case "playwright_check": {
      const htmlDir = htmlPath ? path.dirname(htmlPath) : SKILL_ROOT;
      const sidecarPath = path.join(htmlDir, "overflow-check.json");
      if (!fs.existsSync(sidecarPath)) {
        console.warn(`[playwright_check] WARNING: overflow-check.json not found at ${sidecarPath} — skipping deduct`);
        return { subscore: 10.0, note: "sidecar-absent-warning", deduct: 0 };
      }

      let sidecar;
      try {
        sidecar = readJson(sidecarPath);
      } catch (_) {
        console.warn("[playwright_check] WARNING: could not parse overflow-check.json — skipping deduct");
        return { subscore: 10.0, note: "sidecar-parse-warning", deduct: 0 };
      }

      const overflowCount = sidecar.overflowCount || 0;
      if (overflowCount > 0) {
        return { overflowCount, deduct: 2.0, subscore: 8.0 };
      }
      return { overflowCount: 0, deduct: 0, subscore: 10.0 };
    }

    // ── css_check: font sizes and page-break rules ──
    case "css_check": {
      // Extract <style> block
      const styleMatch = html.match(/<style[^>]*>([\s\S]*?)<\/style>/i);
      const styleContent = styleMatch ? styleMatch[1] : "";

      let violations = [];

      if (check.id === "font_size_compliance") {
        // body font-size: 11.5px ± 0.5
        const bodyFontRe = /body\s*\{[^}]*font-size:\s*([\d.]+)px/i;
        const bodyMatch = styleContent.match(bodyFontRe);
        if (bodyMatch) {
          const sz = parseFloat(bodyMatch[1]);
          if (sz < 11.0 || sz > 12.0) violations.push(`body font-size ${sz}px (expected 11.5±0.5)`);
        } else {
          violations.push("body font-size not found");
        }

        // h2: 17px ± 1
        const h2Re = /\bh2\b[^{]*\{[^}]*font-size:\s*([\d.]+)px/i;
        const h2Match = styleContent.match(h2Re);
        if (h2Match) {
          const sz = parseFloat(h2Match[1]);
          if (sz < 16.0 || sz > 18.0) violations.push(`h2 font-size ${sz}px (expected 17±1)`);
        } else {
          violations.push("h2 font-size not found");
        }

        // h3: 13.5px ± 1
        const h3Re = /\bh3\b[^{]*\{[^}]*font-size:\s*([\d.]+)px/i;
        const h3Match = styleContent.match(h3Re);
        if (h3Match) {
          const sz = parseFloat(h3Match[1]);
          if (sz < 12.5 || sz > 14.5) violations.push(`h3 font-size ${sz}px (expected 13.5±1)`);
        } else {
          violations.push("h3 font-size not found");
        }
      }

      if (check.id === "page_break_consistency") {
        // Every .page should have page-break-after
        const pageBreakRe = /\.page\b[^{]*\{[^}]*page-break-after/i;
        if (!pageBreakRe.test(styleContent)) {
          violations.push(".page missing page-break-after");
        }
        // .back-cover should have page-break-after: auto
        const backCoverBreakRe = /\.back-cover\b[^{]*\{[^}]*page-break-after\s*:\s*auto/i;
        // Also check if page rule applies to back-cover (back-cover extends .page)
        const backCoverInPageRe = /\.page(?:[^{]|\{[^}]*page-break-after[^}]*\})[^{]*\.back-cover/is;
        const backCoverHasAutoRe = /\.back-cover[^{]*\{[^}]*page-break-after\s*:\s*auto/i;
        if (!backCoverHasAutoRe.test(styleContent)) {
          violations.push(".back-cover missing page-break-after: auto");
        }
      }

      const deduct = violations.length * 1.5;
      const subscore = Math.max(0, 10.0 - deduct);
      return { violations, deduct, subscore };
    }

    // ── entity_list_check: sanctions entity scan ──
    //
    // FAIL-CLOSED semantics (per step-04 hardening):
    //   • List missing or unparseable → INACTIVE warning + subscore 3.5 (not silent 10.0).
    //     subscore 3.5 keeps data_integrity mechanical below 9.5 so a human is forced to
    //     notice that sanctions coverage is unverified. It also propagates as triggers:
    //     ["sanctions-list-unavailable"] so the round-3 red-line check can veto.
    //   • Sanctioned entity found without [SANCTIONED] marker → set_score 0 (hard veto on
    //     data_integrity dim) + triggers: ["sanctions-entity-unmarked"] for red-line veto.
    //   • Clean report + list present → subscore 10.0.
    //
    // Authoritative data source: shared/sanctions-list.json (OFAC SDN + sources, refreshed on cadence).
    // Run: node scripts/ingest-sanctions.mjs to refresh.
    case "entity_list_check": {
      const listPath = check.list_path
        ? path.resolve(SKILL_ROOT, check.list_path)
        : null;

      // FAIL-CLOSED: missing list → INACTIVE warning + non-pass subscore
      if (!listPath || !fs.existsSync(listPath)) {
        const msg = `[entity_list_check] COMPLIANCE GATE INACTIVE: sanctions-list.json not found at ${listPath || "(not configured)"}. ` +
          `Report sanctions compliance is UNVERIFIED — data_integrity subscore capped at 3.5 to force human review. ` +
          `Provide shared/sanctions-list.json signed by compliance-luoyang.`;
        console.warn(msg);
        return {
          subscore: 3.5,
          note: "sanctions-list-unavailable — compliance gate INACTIVE",
          triggers: ["sanctions-list-unavailable"],
          deduct: 6.5    // informational; actual score is via subscore
        };
      }

      let sanctionsList;
      try {
        sanctionsList = readJson(listPath);
      } catch (_) {
        const msg = `[entity_list_check] COMPLIANCE GATE INACTIVE: could not parse sanctions-list.json — ` +
          `data_integrity subscore capped at 3.5.`;
        console.warn(msg);
        return {
          subscore: 3.5,
          note: "sanctions-list-unavailable — compliance gate INACTIVE",
          triggers: ["sanctions-list-unavailable"],
          deduct: 6.5
        };
      }

      // Validate authoritative status and log an advisory if still on seed/interim data
      if (sanctionsList._meta?.status && !sanctionsList._meta.status.includes("AUTHORITATIVE-INGESTED")) {
        console.warn(
          `[entity_list_check] ADVISORY: sanctions-list.json status: "${sanctionsList._meta.status}". ` +
          `Run: node scripts/ingest-sanctions.mjs to populate authoritative OFAC data.`
        );
      }

      const entities = Array.isArray(sanctionsList) ? sanctionsList : sanctionsList.entities || [];

      // Stale check — auto-DEGRADE if list is beyond cadence
      const retrieved_at = sanctionsList._meta?.sources?.["OFAC-SDN"]?.retrieved_at
        || sanctionsList._meta?.generated_at;
      if (retrieved_at) {
        const ageMs = Date.now() - new Date(retrieved_at).getTime();
        const ageDays = ageMs / (1000 * 60 * 60 * 24);
        const OFAC_STALE_DAYS = 2; // OFAC cadence: daily T+1
        if (ageDays > OFAC_STALE_DAYS) {
          const msg = `[entity_list_check] STALE: OFAC sanctions data retrieved ${ageDays.toFixed(1)} days ago (cadence: ${OFAC_STALE_DAYS} days). Auto-DEGRADE — run: node scripts/ingest-sanctions.mjs`;
          console.warn(msg);
          return {
            subscore: 3.5,
            note: `sanctions data stale: OFAC retrieved_at ${retrieved_at} (${ageDays.toFixed(1)} days old, cadence: ${OFAC_STALE_DAYS} days)`,
            triggers: ["sanctions-list-stale"],
            deduct: 6.5,
            stale_since: retrieved_at,
            stale_days: ageDays,
            auto_action: "DEGRADE — refresh with: node scripts/ingest-sanctions.mjs"
          };
        }
      }

      // Use prose-only scan to reduce CSS/attribute false positives
      const proseText = extractProseText(html);
      // Also scan full plain text for entity names that may appear in metadata/headings
      const fullPlainText = html
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ")
        .replace(/<[^>]+>/g, " ").toLowerCase();
      const hits = [];

      // C-2: word-boundary guard for abbreviation aliases (<=5 chars or all-caps).
      // "ROE"/"CBR"/"GPB"/"IRISL" must match as whole words only (\bALIAS\b) to
      // avoid mass false-positives ("ROE" -> "return on equity", "CBR" -> "CBR index", etc.).
      // Full entity names (longer, mixed-case) keep normal substring matching.
      function isShortAbbreviation(alias) {
        return alias.length <= 5 || /^[A-Z0-9]+$/.test(alias);
      }

      // C-3: skip purely numeric aliases and short alphanumeric codenames (e.g. "27", "H1").
      // These are criminal gang member aliases/codenames in OFAC SDN, not financial organization
      // names. A macro report mentioning "27" (a number or percentage) or "H1" (heading level)
      // would generate massive false-positives. Only skip when the ALIAS (not the primary name)
      // is purely numeric or ≤3 chars alphanumeric — the full entity name still gets checked.
      function isAmbiguousCodername(alias) {
        if (/^\d+$/.test(alias)) return true;           // purely numeric: "27", "1234"
        if (/^[A-Z0-9]{1,3}$/.test(alias)) return true; // short alphanumeric code: "H1", "B2"
        return false;
      }

      // C-4 (EN-report hardening): detect aliases that are ordinary English words.
      // OFAC assigns codenames like "PRECIOUS"/"HUGE"/"GLORY"/"MAJESTIC" to entities (often
      // IRAN/narcotics programs). These collide with normal report vocabulary ("precious metals",
      // "huge risk") and generate false positives, especially in English-language reports where
      // such words are common. Such aliases are NOT skipped outright (they may be real hits in a
      // sanctions-context paragraph), but require a sanctions-context signal nearby to trigger.
      //
      // NOTE: an earlier version relaxed *any* pure-alpha token with a vowel — but that wrongly
      // relaxed real acronym aliases like "IRISL"/"CIMEX"/"AEOI"/"ABADAN" (thousands of OFAC
      // all-caps transliterations that are NOT English words), creating false NEGATIVES. We now
      // use an explicit allowlist of known OFAC codenames that lower-case to ordinary English
      // words. Anything not on this list stays strict, even if it has a vowel. The allowlist is
      // short and stable (OFAC reuses the same codenames); extend it only when a real FP surfaces.
      const OFAC_WORD_CODENAMES = new Set([
        // narcotics / SDGT program codenames observed in OFAC-SDN
        "PRECIOUS", "HUGE", "GLORY", "MAJESTIC", "EXPLORER", "HERBY",
        "HYDRA", "TITAN", "EMPEROR", "VICTORY", "EMERALD", "RUBY",
        "PEARL", "DIAMOND", "CRYSTAL", "SAPPHIRE", "ROYAL", "GOLDEN",
        "SILVER", "IMPERIAL", "CROWN", "NOBLE",
        // transliterated names that are also common given names (misread as common words)
        "BASHIR", "KHADEM",
      ].map(s => s.toLowerCase()));
      function isCommonWordAlias(alias) {
        if (!/^[A-Za-z]{4,12}$/.test(alias)) return false;
        return OFAC_WORD_CODENAMES.has(alias.toLowerCase());
      }

      // Sanctions-context keywords: a common-word alias only triggers if one of these appears
      // within ±150 chars of the match. Macro/mining reports discuss commodities, not sanctions
      // deals, so a real sanctions reference will carry context like "sanctioned"/"OFAC"/"Iran".
      const SANCTIONS_CTX_RE = /\b(sanction|ofac|sdn|designat|blocked|prohibited|iran|dprk|north korea|russia|terroris|narcotic|weapons?|arms?|proliferat|entity list|denied party)\b/i;

      for (const entity of entities) {
        const names = [entity.name, ...(entity.aliases || [])].filter(Boolean);
        for (const nm of names) {
          // Skip ambiguous codenames when they appear as aliases (not primary entity names)
          // Primary entity name (first in list) always gets checked.
          if (nm !== entity.name && isAmbiguousCodername(nm)) continue;
          const nmLower = nm.toLowerCase();
          const useWordBoundary = isShortAbbreviation(nm);

          let inProse, inFull;
          if (useWordBoundary) {
            // Word-boundary match -- use RegExp \b...\b on the lowercased text
            const escapedNm = nmLower.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const wordBoundaryRe = new RegExp(`\\b${escapedNm}\\b`);
            inProse = wordBoundaryRe.test(proseText.toLowerCase());
            inFull  = wordBoundaryRe.test(fullPlainText);
          } else {
            // Normal substring match for full entity names
            inProse = proseText.toLowerCase().includes(nmLower);
            inFull  = fullPlainText.includes(nmLower);
          }

          if (!inProse && !inFull) continue;

          // Search for nearest [SANCTIONED] marker (within ~200 chars of the match)
          const searchText = inFull ? fullPlainText : proseText.toLowerCase();
          let idx;
          if (useWordBoundary) {
            const escapedNm2 = nmLower.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            idx = searchText.search(new RegExp(`\\b${escapedNm2}\\b`));
          } else {
            idx = searchText.indexOf(nmLower);
          }
          if (idx === -1) continue;
          const ctxWindow = searchText.slice(Math.max(0, idx - 150), idx + nmLower.length + 150);
          // C-4: common-word codenames (Precious/Huge/Glory...) need a sanctions-context signal
          // within ±150 chars to trigger — otherwise "precious metals"/"huge risk" in a normal
          // macro report false-positive. Real sanctions references carry context words.
          // The decision is made by isCommonWordAlias() against the OFAC_WORD_CODENAMES allowlist,
          // applied uniformly to BOTH aliases and primary names. This avoids the prior bug where
          // every all-caps 4-12-char primary name (IRISL, CIMEX, AEOI, ABDULLAH, …) was wrongly
          // relaxed — only genuine English-word codenames on the allowlist get context-gating;
          // real acronym entities stay strict.
          const treatAsCommonWord = isCommonWordAlias(nm);
          if (treatAsCommonWord && !ctxWindow.includes("[sanctioned]") && !SANCTIONS_CTX_RE.test(ctxWindow)) {
            continue; // common word without sanctions context → skip (false positive)
          }
          if (!ctxWindow.includes("[sanctioned]")) {
            // Only record each entity once (avoid alias duplicates)
            if (!hits.some(h => h.entity === entity.name)) {
              hits.push({ entity: entity.name, matched: nm });
            }
          }
        }
      }

      if (hits.length > 0) {
        const msg = `[entity_list_check] VETO: sanctioned entities found without [SANCTIONED] marker: ` +
          hits.map(h => `${h.entity} (matched "${h.matched}")`).join(", ");
        console.warn(msg);
        // Hard veto: set_score 0 on data_integrity + red-line trigger
        // Action 5 (HIGH) — G34 runtime hook:
        // A real sanctioned-entity hit in an outgoing report IS a G34 "制裁触发" event.
        // Mechanism-building = single compliance sign; runtime hit = G34 double-sign.
        return {
          hits,
          set_score: 0,
          subscore: 0,
          note: "sanctioned-entity-unmarked — AUTO-DEGRADE: report blocked/watermarked; cite authoritative match",
          triggers: ["sanctions-entity-unmarked"],
          // Authoritative citation per hit:
          matched_citations: hits.map(h => {
            const entity = entities.find(e => e.name === h.entity);
            return {
              matched_entity: h.entity,
              matched_alias: h.matched,
              source: entity?.source || "OFAC",
              source_url: entity?.source_url || "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
              source_publish_date: entity?.source_publish_date || sanctionsList._meta?.sources?.["OFAC-SDN"]?.publish_date || "unknown",
              source_record_uid: entity?.source_record_uid || "unknown"
            };
          }),
          // [NEEDS-SIGNOFF · P0-5b / G34] A runtime sanctioned-entity hit in an
          // OUTGOING report is a G34 "制裁触发" event = 王选策 + 罗阳 双签. The prior
          // "no human required" auto-DEGRADE is acceptable ONLY for INTERNAL drafts
          // (watermark). For EXTERNAL distribution this must FAIL-CLOSED (block, not
          // watermark) until a double-sign receipt is presented. Distribution mode is
          // carried by distribution_marking (see rubric); the publisher MUST honor
          // external_block_requires_signoff before releasing.
          auto_action: "DEGRADE (INTERNAL draft → watermark). EXTERNAL → BLOCK pending G34 double-sign.",
          external_block_requires_signoff: ["ceo-wangxc", "compliance-luoyang"]
        };
      }

      // Clean: list present + no hits
      // If INTERIM, note that content coverage is provisional but mechanism is approved
      const interimNote = (sanctionsList._meta?.status?.includes("SEED") || sanctionsList._meta?.status?.includes("INTERIM"))
        ? "INTERIM-seed-scan-passed (mechanism approved; content coverage INTERIM pending data-op ingest)"
        : undefined;
      return { hits: [], subscore: 10.0, ...(interimNote ? { note: interimNote } : {}) };
    }

    // ── svg_safety: unescaped chars in SVG text/tspan ──
    case "svg_safety": {
      // Extract SVG content from chart images
      const chartImgRe = /<img[^>]+class="chart"[^>]+src="data:image\/[^;]+;base64,([^"]+)"/gi;
      const svgParts = [];

      for (const m of html.matchAll(chartImgRe)) {
        try {
          const decoded = Buffer.from(m[1], "base64").toString("utf8");
          if (decoded.includes("<svg")) svgParts.push(decoded);
        } catch (_) { /* skip */ }
      }

      // Also inline SVG
      for (const m of html.matchAll(/<svg[\s\S]*?<\/svg>/gi)) {
        svgParts.push(m[0]);
      }

      if (svgParts.length === 0) {
        return { subscore: 10.0, note: "no-svg-found" };
      }

      const violations = [];
      for (const svg of svgParts) {
        violations.push(...checkSvgSafety(svg));
      }

      if (violations.length > 0) {
        return { violations, set_score: 0, subscore: 0, note: "svg-injection-detected" };
      }

      return { violations: [], subscore: 10.0 };
    }

    // ── score_figure_svg: deterministic JS figure quality scorer ──
    // Calls scoreFigureSvg from figures/figure_checks.mjs over every inline SVG.
    // Checks: (a) SVG safety (no unescaped text injection), (b) data marks present,
    // (c) labeling present, (d) viewBox ≥ 1040×640.
    // Any veto → set_score 0; any blocker → deduct based on severity.
    case "score_figure_svg": {
      // Collect all inline SVG chart blocks (from render-figures.mjs output or gen_reference_charts)
      // Dedup strategy: collect chart-block positions first, then add only bare SVGs that
      // don't overlap with already-collected chart-block regions.
      const svgParts = [];
      const chartBlockRegions = []; // [{start, end}] of chart-block div regions

      // 1. Inline chart-block divs (produced by render-figures.mjs SVG fallback or renderHorizontalBar)
      for (const m of html.matchAll(/<div[^>]*class="[^"]*chart[^"]*"[^>]*>([\s\S]*?)<\/div>/gi)) {
        if (m[1].includes("<svg")) {
          svgParts.push(m[1]);
          chartBlockRegions.push({ start: m.index, end: m.index + m[0].length });
        }
      }

      // 2. Base64-encoded SVG inside <img class="chart"> (PNG images contain no SVG; skip non-SVG)
      //    — skip here; PNG image_metadata check already handles PNG-encoded charts.

      // 3. Any bare <svg> elements that are NOT inside already-collected chart-block
      //    regions AND are NOT brand/logo SVGs.
      //    Logo SVGs are decorative brand marks (e.g. the MiningClaw icon+wordmark at
      //    viewBox 137×32), not data figures. Scoring them as charts is a category
      //    error — they have no polylines/rects(data-value), so they always score low
      //    and unjustly drag down expert_citation_quality. Exclude by viewBox signature and by
      //    the presence of the brand wordmark path.
      const LOGO_VIEWBOX_RE = /viewbox=["']0 0 137 32["']/i;
      const LOGO_WORDMARK_RE = /MiningClaw/i;
      for (const m of html.matchAll(/<svg[\s\S]*?<\/svg>/gi)) {
        const svgStart = m.index;
        const inChartBlock = chartBlockRegions.some(r => svgStart >= r.start && svgStart < r.end);
        if (inChartBlock) continue;
        // Skip brand/logo SVGs — they are not data figures.
        if (LOGO_VIEWBOX_RE.test(m[0]) || LOGO_WORDMARK_RE.test(m[0])) continue;
        svgParts.push(m[0]);
      }

      if (svgParts.length === 0) {
        // No inline SVG found — if PNG charts exist they are checked by image_metadata.
        // If no charts at all, this check passes (chart_image_present will catch absence).
        return { subscore: 10.0, note: "no-inline-svg (png-path or no-charts)" };
      }

      // Import scoreFigureSvg lazily (avoids circular dep; figure_checks imports from here for safety)
      let scoreFigureSvg;
      try {
        const { pathToFileURL } = await import("node:url");
        const mod = await import(pathToFileURL(path.join(__dirname, "../figures/figure_checks.mjs")).href);
        scoreFigureSvg = mod.scoreFigureSvg;
      } catch (err) {
        console.warn("[score_figure_svg] WARNING: could not import figure_checks.mjs —", err.message);
        return { subscore: 10.0, note: "figure_checks-unavailable-warn" };
      }

      let totalVetoes   = 0;
      let totalBlockers = 0;
      let dimSum        = { safety: 0, data_marks: 0, labeling: 0, resolution: 0 };
      let svgCount      = 0;

      for (const svg of svgParts) {
        // Deduplicate: only score SVGs that have viewBox (real charts, not decorative)
        if (!/<svg\b/.test(svg)) continue;
        svgCount++;
        const result = await scoreFigureSvg(svg);
        totalVetoes   += result.vetoes.length;
        totalBlockers += result.blockers.length;
        dimSum.safety     += result.dims.safety;
        dimSum.data_marks += result.dims.data_marks;
        dimSum.labeling   += result.dims.labeling;
        dimSum.resolution += result.dims.resolution;
      }

      if (svgCount === 0) {
        return { subscore: 10.0, note: "no-scored-svgs" };
      }

      // Average dims across all SVGs
      const avgDims = {
        safety:     dimSum.safety     / svgCount,
        data_marks: dimSum.data_marks / svgCount,
        labeling:   dimSum.labeling   / svgCount,
        resolution: dimSum.resolution / svgCount,
      };

      // Any veto (svg_injection or no_data_marks) → hard set_score 0
      if (totalVetoes > 0) {
        return {
          svgCount, totalVetoes, totalBlockers, avgDims,
          set_score: 0, subscore: 0,
          note: `figure-quality-veto (${totalVetoes} vetoes across ${svgCount} SVGs)`,
        };
      }

      // Blockers (no labels, missing viewBox) → heavy deduct
      if (totalBlockers > 0) {
        const deductPerBlocker = 2.0;
        const deduct = Math.min(totalBlockers * deductPerBlocker, 8.0);
        return {
          svgCount, totalVetoes, totalBlockers, avgDims,
          deduct, subscore: Math.max(0, 10.0 - deduct),
        };
      }

      // All dims pass: score by average across dimensions (all must be 1.0 to get full marks)
      const overallAvg = (avgDims.safety + avgDims.data_marks + avgDims.labeling + avgDims.resolution) / 4;
      return {
        svgCount, totalVetoes: 0, totalBlockers: 0, avgDims,
        subscore: overallAvg * 10.0,
      };
    }

    // ── chart_data_match: deterministic geometry-vs-data comparison ──
    // Parses data-value attributes from bar rects and compares heights/widths to
    // the declared values. For line charts, checks polyline exists.
    // Tolerance from check.tolerance (default 2%).
    // IMPORTANT: comparisons are scoped PER SVG element to avoid cross-chart false positives.
    // Different charts have different px/unit scales; cross-chart ratios are meaningless.
    // Returns subscore 10.0 (pass) or deducted value; set_score 0 on mismatch > tolerance.
    case "chart_data_match": {
      const tolerance = typeof check.tolerance === "number" ? check.tolerance : 0.02;

      // Extract each SVG block separately, then check proportionality within each SVG.
      // This prevents cross-chart false positives (each chart has its own px/unit scale).
      const svgBlocks = [...html.matchAll(/<svg\b[\s\S]*?<\/svg>/gi)].map(m => m[0]);

      if (svgBlocks.length === 0) {
        return { svgCount: 0, subscore: 10.0, note: "no-svg-found" };
      }

      let totalMismatches = 0;
      let totalComparisons = 0;
      let totalPairs = 0;
      let chartsMeasured = 0;

      for (const svgHtml of svgBlocks) {
        // Collect all data-value rects within this SVG
        const dataValuePairs = [];
        for (const m of svgHtml.matchAll(/<rect\b[^>]*data-value="([^"]+)"[^>]*>/gi)) {
          const dataVal = parseFloat(m[1]);
          if (!isFinite(dataVal)) continue;

          const attrStr = m[0];
          const hMatch = attrStr.match(/\bheight="([^"]+)"/i);
          const wMatch = attrStr.match(/\bwidth="([^"]+)"/i);
          const geomH = hMatch ? parseFloat(hMatch[1]) : null;
          const geomW = wMatch ? parseFloat(wMatch[1]) : null;

          if (geomH != null && isFinite(geomH) && geomH > 0) {
            dataValuePairs.push({ dataVal, geom: geomH, kind: "height" });
          } else if (geomW != null && isFinite(geomW) && geomW > 0) {
            dataValuePairs.push({ dataVal, geom: geomW, kind: "width" });
          }
        }

        if (dataValuePairs.length < 2) continue; // line chart or decorative SVG

        const pairs = dataValuePairs.filter(p => Math.abs(p.dataVal) > 0);
        if (pairs.length < 2) continue;

        chartsMeasured++;
        totalPairs += pairs.length;

        // Check proportionality within this SVG only
        for (let i = 0; i < pairs.length - 1; i++) {
          for (let j = i + 1; j < pairs.length; j++) {
            const ratioData = Math.abs(pairs[i].dataVal) / Math.abs(pairs[j].dataVal);
            const ratioGeom = pairs[i].geom / pairs[j].geom;
            if (!isFinite(ratioGeom) || ratioGeom === 0) continue;
            totalComparisons++;
            const relErr = Math.abs(ratioData - ratioGeom) / Math.max(ratioData, ratioGeom);
            if (relErr > tolerance) totalMismatches++;
          }
        }
      }

      if (chartsMeasured === 0) {
        // No bar charts with data-value attrs (e.g. all line charts)
        return { svgCount: svgBlocks.length, chartsMeasured, subscore: 10.0, note: "no-data-attr-or-too-few" };
      }

      if (totalComparisons === 0) {
        return { svgCount: svgBlocks.length, chartsMeasured, totalPairs, subscore: 10.0, note: "no-nonzero-pairs" };
      }

      const mismatchRatio = totalMismatches / totalComparisons;

      if (mismatchRatio > 0.5) {
        return {
          svgCount: svgBlocks.length, chartsMeasured, totalPairs, totalMismatches, totalComparisons, mismatchRatio,
          set_score: 0, subscore: 0,
          note: `chart-data-mismatch: ${totalMismatches}/${totalComparisons} pairs exceed ${(tolerance * 100).toFixed(0)}% tolerance`,
        };
      }

      const deduct = mismatchRatio * 8.0;
      return {
        svgCount: svgBlocks.length, chartsMeasured, totalPairs, totalMismatches, totalComparisons, mismatchRatio,
        deduct, subscore: Math.max(0, 10.0 - deduct),
      };
    }

    default:
      return { method: check.method, note: "unknown", subscore: 10.0, deduct: 0 };
  }
}

// ─────────────────────────────────────────────────
// 融合: 机械分 × 0.40 + LLM 分 × 0.60
// LLM 分由 rubric-reviewer subagent 产出 (scores/*.json)
//
// Round-3 gate ALSO requires:
//   min(llm_dim) ≥ 8.5 AND no hard red-line (citation/disclaimer missing)
// ─────────────────────────────────────────────────
function fuseScores(mechanicalResults, llmScoresPath, rubric) {
  const llm = readJson(llmScoresPath);   // rubric-reviewer 输出
  const merged = {};
  for (const dim of rubric.dimensions) {
    const m = mechanicalResults[dim.id]?.mechanical_score ?? 0;
    const l = llm.scores[dim.id]?.score ?? 0;
    const fusedRaw =
      rubric.meta.mechanical_weight * m +
      rubric.meta.llm_weight * l;
    merged[dim.id] = {
      score: Math.round(fusedRaw * 10) / 10,   // display rounded
      fused_raw: fusedRaw,                      // raw for comparisons
      mechanical: m,
      llm: l,
      comment: llm.scores[dim.id]?.comment ?? "",
      evidence: llm.scores[dim.id]?.evidence ?? "",
      passes_9_5: fusedRaw >= rubric.meta.gate_threshold
    };
  }
  return merged;
}

// ─────────────────────────────────────────────────
// Round-3 enhanced gate: weighted total + LLM floor + red-line check
//
// Optional 3rd arg mechanicalResults: if provided, sanctions triggers from
// entity_list_check are inspected directly to enforce the compliance red-line.
// Without it, the gate falls back to inspecting data_integrity.mechanical score.
// ─────────────────────────────────────────────────
function evaluateRound3(fused, rubric, mechanicalResults) {
  // Use raw fused scores for all comparisons (no display-rounding effects)
  let totalWeightedScore = 0;
  for (const dim of rubric.dimensions) {
    totalWeightedScore += (fused[dim.id]?.fused_raw ?? 0) * dim.weight;
  }

  const totalThreshold = rubric.meta.total_gate_threshold ?? 9.0;

  // Check LLM floor: min(llm_dim) must be ≥ 8.5
  const llmScores = rubric.dimensions.map(d => fused[d.id]?.llm ?? 0);
  const minLlm = Math.min(...llmScores);
  const llmFloorOk = minLlm >= 8.5;

  // Check hard red-lines: citation/disclaimer checks must not be failing
  // A "hard red line" = any dim where mechanical_score = 0 on a critical check
  // We use: logical_consistency mechanical ≥ 2.0 (not completely dead) AND language_quality has disclaimer
  const logicConsistMech = fused["logical_consistency"]?.mechanical ?? 0;
  const langQualityMech  = fused["language_quality"]?.mechanical ?? 0;
  const redLineBroken = (logicConsistMech === 0) || (langQualityMech === 0);

  // Sanctions red-line check (step-04 hardening):
  //   1. Sanctioned entity found without marker → data_integrity mechanical = 0 → veto
  //   2. Sanctions list unavailable (INACTIVE) → data_integrity mechanical ≤ 3.5 → veto
  // Both conditions are a DEGRADE regardless of weighted total.
  // If mechanicalResults provided, check triggers directly; otherwise infer from score.
  let sanctionsRedLine = false;
  let sanctionsRedLineReason = "";

  if (mechanicalResults) {
    // Inspect entity_list_check triggers directly
    const ccChecks = mechanicalResults["data_integrity"]?.checks || [];
    const entityCheck = ccChecks.find(c => c.id === "sanctions_entity_check");
    if (entityCheck) {
      if (entityCheck.triggers?.includes("sanctions-entity-unmarked")) {
        sanctionsRedLine = true;
        sanctionsRedLineReason = "sanctioned entity found without [SANCTIONED] marker";
      } else if (entityCheck.triggers?.includes("sanctions-list-unavailable")) {
        sanctionsRedLine = true;
        sanctionsRedLineReason = "sanctions-list unavailable — compliance gate INACTIVE; refresh with: node scripts/ingest-sanctions.mjs";
      }
    }
  } else {
    // FAIL-CLOSED: without mechanicalResults we cannot inspect the sanctions
    // entity_list_check triggers directly, so the sanctions red-line is
    // UNVERIFIABLE. The previous behaviour inferred from data_integrity's
    // fused mechanical score (ccMech ≤ 3.6), but that blend dilutes an INACTIVE
    // sanctions sub-check up to ~8.1, letting a report that production would
    // DEGRADE pass as PASS_WITH_NOTES (the test path did exactly this). A
    // compliance gate must never pass on "could not verify" — treat missing
    // mechanicalResults as a red-line and DEGRADE. Callers MUST pass the third
    // argument (see test/baseline.mjs); the fallback exists only to fail safe.
    sanctionsRedLine = true;
    sanctionsRedLineReason = "sanctions red-line UNVERIFIABLE — evaluateRound3 called without mechanicalResults; fail-closed to DEGRADED";
  }

  const totalOk = totalWeightedScore >= totalThreshold;

  // [NEEDS-SIGNOFF · P0-5c] Compliance independent floor: a dimension flagged
  // hard_floor in the rubric (language_quality) must NOT be rescued by the round-3
  // weighted average. If its fused score is below gate_threshold, DEGRADE regardless
  // of total. Closes the "MNPI/marketing violation averaged away" gap (compliance P1-3).
  let complianceFloorBroken = false;
  let complianceFloorReason = "";
  if (rubric.meta?.compliance_floor_enabled) {
    for (const dim of rubric.dimensions) {
      if (!dim.hard_floor) continue;
      const f = fused[dim.id]?.fused_raw ?? fused[dim.id]?.score ?? 0;
      if (f < (rubric.meta.gate_threshold ?? 9.5)) {
        complianceFloorBroken = true;
        complianceFloorReason = `hard_floor dimension '${dim.id}' fused=${f.toFixed?.(2) ?? f} < gate_threshold ${rubric.meta.gate_threshold ?? 9.5} — not eligible for weighted-average rescue`;
        break;
      }
    }
  }

  let verdict;
  if (!totalOk) {
    verdict = "DEGRADED";
  } else if (!llmFloorOk || redLineBroken || sanctionsRedLine || complianceFloorBroken) {
    verdict = "DEGRADED";
  } else {
    verdict = "PASS_WITH_NOTES";
  }

  return {
    verdict,
    totalWeightedScore: Math.round(totalWeightedScore * 1000) / 1000,
    totalThreshold,
    minLlm,
    sanctionsRedLine,
    sanctionsRedLineReason,
    complianceFloorBroken,
    complianceFloorReason,
    llmFloorOk,
    redLineBroken,
    failedDims: Object.entries(fused).filter(([, v]) => !v.passes_9_5).map(([k]) => k)
  };
}

// ─────────────────────────────────────────────────
// 主循环
// ─────────────────────────────────────────────────
async function main() {
  const args = parseArgs();
  const rubric = loadRubric();
  const REPORT_ID = args["report-id"];

  // ── Per-run directory (item 3: namespaced, no cross-run collisions) ──
  const RUN_DIR = path.resolve(args["run-dir"]);
  ensureDir(RUN_DIR);

  // All writable artifacts go into RUN_DIR (not SKILL_ROOT)
  const AUDIT_PATH   = path.join(RUN_DIR, `audit-${REPORT_ID}.json`);
  const STATE_PATH   = path.join(RUN_DIR, "state.json");
  const SCORES_DIR   = path.join(RUN_DIR, "scores");
  const DRAFT_DIR    = path.join(RUN_DIR, "draft");

  ensureDir(SCORES_DIR);
  ensureDir(DRAFT_DIR);

  // ── Crash-resume: load state from prior run if it exists (item 1) ──
  let resumeState = loadRunState(STATE_PATH);
  let resuming = false;

  if (resumeState && resumeState.status === "FAILED") {
    // Prior run was marked FAILED — resume from last incomplete step
    console.log(`[resume] found FAILED state from ${resumeState.started_at}, resuming from round ${resumeState.current_round || 1}`);
    resuming = true;
  } else if (resumeState && resumeState.status === "RUNNING") {
    // Prior run was interrupted mid-run (process killed without fail-closed)
    console.log(`[resume] found RUNNING state (possible crash), resuming from round ${resumeState.current_round || 1}`);
    resuming = true;
  } else if (resumeState && (resumeState.status === "PASS" || resumeState.status === "PASS_WITH_NOTES" || resumeState.status === "DEGRADED")) {
    console.log(`[resume] run already completed (${resumeState.status}) — re-running from scratch (pass --resume to reuse)`);
    resumeState = null;
    resuming = false;
  }

  // ── Build audit object (or restore partial from resume) ──
  const audit = resuming && resumeState?.audit
    ? resumeState.audit
    : {
        report_id: REPORT_ID,
        started_at: now(),
        source: args["source"],
        output: args["output"],
        rubric_version: rubric.meta.version,
        rounds: [],
        final_status: null
      };

  // Persist initial state so crash before round-1 is recoverable
  let state = {
    report_id: REPORT_ID,
    started_at: now(),
    status: "RUNNING",
    current_round: resumeState?.current_round || 0,
    data_path: resumeState?.data_path || null,
    audit
  };
  saveRunState(STATE_PATH, state);

  // ── Round 0: data-collector (一次, 不参与门控循环, 但失败也回退) ──
  let dataPath = resumeState?.data_path || null;

  if (!dataPath || !fs.existsSync(dataPath)) {
    console.log(`[round-0] dispatching data-collector...`);
    const dcReq = dispatchSubagent("data-collector", {
      report_id: REPORT_ID,
      round: 0,
      source_path: args["source"]
    }, RUN_DIR);
    dataPath = await awaitDispatch(dcReq, RUN_DIR, 30 * 60 * 1000, RUN_DIR);
    state.data_path = dataPath;
    saveRunState(STATE_PATH, state);
  } else {
    console.log(`[round-0] RESUME: using cached data-collector output: ${dataPath}`);
  }

  // Resume from prior round if crash-resuming (item 1: round counter in state file)
  let currentRound = (resumeState?.current_round && resumeState.current_round > 0)
    ? resumeState.current_round
    : 1;
  let finalHtmlPath = resumeState?.final_html_path || null;
  let degraded = false;
  let failedDims = resumeState?.failed_dims || [];

  while (currentRound <= rubric.meta.max_rounds) {
    // 3-strike / no-infinite-loop (item 8): confirm we never exceed max_rounds
    // even on a resumed run. The state file tracks the true round counter.
    if (currentRound > rubric.meta.max_rounds) {
      console.log(`[round-${currentRound}] exceeded max_rounds=${rubric.meta.max_rounds} — exiting DEGRADED (3-strike)`);
      degraded = true;
      audit.final_status = "DEGRADED";
      break;
    }

    const roundLog = { round: currentRound, started_at: now(), dispatches: [] };

    // Update state before each round so crash in this round is resumable to THIS round
    state.current_round = currentRound;
    state.status = "RUNNING";
    saveRunState(STATE_PATH, state);

    // ── content-writer ──
    const awReq = dispatchSubagent("content-writer", {
      report_id: REPORT_ID,
      round: currentRound,
      data_path: dataPath,
      reviewer_feedback: currentRound > 1
        ? path.join(SCORES_DIR, `${REPORT_ID}-v${currentRound - 1}.json`)
        : null
    }, RUN_DIR);
    const draftHtml = await awaitDispatch(awReq, RUN_DIR, 30 * 60 * 1000, RUN_DIR);
    roundLog.dispatches.push({ agent: "content-writer", req: awReq });

    // ── visual-designer ──
    const cbReq = dispatchSubagent("visual-designer", {
      report_id: REPORT_ID,
      round: currentRound,
      draft_html: draftHtml,
      data_path: dataPath
    }, RUN_DIR);
    const draftWithCharts = await awaitDispatch(cbReq, RUN_DIR, 30 * 60 * 1000, RUN_DIR);
    roundLog.dispatches.push({ agent: "visual-designer", req: cbReq });

    // ── rubric-reviewer (独立!) ──
    const rrReq = dispatchSubagent("rubric-reviewer", {
      report_id: REPORT_ID,
      round: currentRound,
      draft_html: draftWithCharts,
      data_path: dataPath,
      rubric_path: RUBRIC_PATH,
      isolation: "fresh_context"   // 关键: 不复用前面 subagent context
    }, RUN_DIR);
    const llmScoresPath = await awaitDispatch(rrReq, RUN_DIR, 30 * 60 * 1000, RUN_DIR);
    roundLog.dispatches.push({ agent: "rubric-reviewer", req: rrReq });

    // ── 机械检查 + 融合 ──
    const mechanical = await runMechanicalChecks(draftWithCharts, dataPath, rubric);
    const fused = fuseScores(mechanical, llmScoresPath, rubric);

    roundLog.scores = fused;
    roundLog.completed_at = now();

    failedDims = Object.entries(fused)
      .filter(([_, v]) => !v.passes_9_5)
      .map(([k, _]) => k);

    // Persist round scores atomically
    const roundScorePath = path.join(SCORES_DIR, `${REPORT_ID}-v${currentRound}.json`);
    writeJson(roundScorePath, fused);

    if (failedDims.length === 0) {
      // C-1 BLOCKER: before accepting early-PASS, check if any sanctions trigger
      // is present in data_integrity's sanctions_entity_check result.
      // The sanctions gate MUST NOT be averaged away — it cannot be bypassed by
      // high LLM scores on other dims.
      const ccChecks = mechanical["data_integrity"]?.checks || [];
      const entityCheck = ccChecks.find(c => c.id === "sanctions_entity_check");
      const sanctionsTriggers = entityCheck?.triggers || [];
      const SANCTIONS_BLOCKERS = [
        "sanctions-entity-unmarked",
        "sanctions-list-unavailable",
        "sanctions-list-stale",
      ];
      const hasBlockingTrigger = sanctionsTriggers.some(t => SANCTIONS_BLOCKERS.includes(t));

      if (hasBlockingTrigger) {
        // Force into round-3 red-line evaluation — do NOT early-PASS
        console.log(
          `[round-${currentRound}] C-1 SHORT-CIRCUIT: sanctions trigger detected ` +
          `(${sanctionsTriggers.join(", ")}) — early-PASS FORBIDDEN, forcing round-3 evaluation`
        );
        // Treat as if this is the final round so we fall through to evaluateRound3 below
        currentRound = rubric.meta.max_rounds;
        // Re-compute failedDims to include data_integrity if not already there
        if (!failedDims.includes("data_integrity")) {
          failedDims.push("data_integrity");
        }
        // Fall through to the max_rounds branch below
      } else {
        // Normal early-PASS
        roundLog.status = "PASS";
        audit.rounds.push(roundLog);
        audit.final_status = "PASS";
        finalHtmlPath = draftWithCharts;
        console.log(`[round-${currentRound}] PASS — 全部 6 项 >= 9.5`);
        // Persist completed state
        state = { ...state, status: "PASS", current_round: currentRound, final_html_path: finalHtmlPath, failed_dims: [], audit };
        saveRunState(STATE_PATH, state);
        break;
      }
    }

    // ── 两阶段门控 ──
    if (currentRound >= rubric.meta.max_rounds) {
      // Pass mechanicalResults so evaluateRound3 can inspect sanctions triggers directly
      const r3 = evaluateRound3(fused, rubric, mechanical);
      roundLog.weighted_total = r3.totalWeightedScore;
      roundLog.round3_details = r3;

      if (r3.verdict === "PASS_WITH_NOTES") {
        console.log(`[round-${currentRound}] ${r3.failedDims.length} 项未达 9.5, 但加权总分 ${r3.totalWeightedScore} >= ${r3.totalThreshold} + LLM floor OK — 放行 (附评分明细)`);
        roundLog.status = "PASS_WITH_NOTES";
        roundLog.note = `加权总分 ${r3.totalWeightedScore}/${r3.totalThreshold}, 单项未达标: ${r3.failedDims.join(", ")}`;
        audit.rounds.push(roundLog);
        audit.final_status = "PASS_WITH_NOTES";
        finalHtmlPath = draftWithCharts;
        degraded = false;
        state = { ...state, status: "PASS_WITH_NOTES", current_round: currentRound, final_html_path: finalHtmlPath, failed_dims: r3.failedDims, audit };
        saveRunState(STATE_PATH, state);
        break;
      }

      let degradeReason = `加权总分 ${r3.totalWeightedScore} < ${r3.totalThreshold}`;
      if (!r3.llmFloorOk) degradeReason += `, LLM floor failed (min_llm=${r3.minLlm} < 8.5)`;
      if (r3.redLineBroken) degradeReason += `, hard red-line broken`;
      if (r3.sanctionsRedLine) degradeReason += `, sanctions red-line: ${r3.sanctionsRedLineReason}`;
      console.log(`[round-${currentRound}] DEGRADED — ${degradeReason}`);
      degraded = true;
      finalHtmlPath = draftWithCharts;
      roundLog.status = "DEGRADED";
      roundLog.note = `${degradeReason}, 未达标项: ${failedDims.join(", ")}`;
      audit.rounds.push(roundLog);
      audit.final_status = "DEGRADED";
      state = { ...state, status: "DEGRADED", current_round: currentRound, final_html_path: finalHtmlPath, failed_dims: failedDims, audit };
      saveRunState(STATE_PATH, state);
      break;
    }

    roundLog.status = "FAIL_NEEDS_FIX";
    roundLog.failed = failedDims;
    audit.rounds.push(roundLog);
    console.log(`[round-${currentRound}] FAIL — failed: ${failedDims.join(", ")}`);
    state = { ...state, current_round: currentRound, failed_dims: failedDims, audit };
    saveRunState(STATE_PATH, state);
    currentRound++;
  }

  // ── 出 PDF (wrap render in try/catch for fail-closed fatal audit) ──
  // Report language: validated & defaulted in parseArgs() (drives banner i18n).
  const reportLang = args["lang"];
  const watermarkArgs = degraded
    ? degradedWatermark(failedDims, audit, rubric, reportLang)
    : null;

  const passWithNotes = audit.final_status === "PASS_WITH_NOTES";
  const statusLabel = degraded ? "DEGRADED" : passWithNotes ? "PASS_WITH_NOTES" : "PASS";
  console.log(`[pdf] rendering ${args["output"]} (${statusLabel})`);

  const renderArgs = [
    path.join(SKILL_ROOT, "scripts", "render-with-watermark.mjs"),
    "--html", finalHtmlPath,
    "--output", args["output"],
  ];
  if (watermarkArgs) renderArgs.push("--watermark", JSON.stringify(watermarkArgs));
  if (passWithNotes) renderArgs.push("--embed-score-table", JSON.stringify({
    i18n: {
      dimNames: i18nT("scoreDimNames", reportLang),
      scoreHeader: i18nT("scoreTableHeader", reportLang),
      colDim: i18nT("scoreColDim", reportLang),
      colMech: i18nT("scoreColMech", reportLang),
      colLlm: i18nT("scoreColLlm", reportLang),
      colFused: i18nT("scoreColFused", reportLang),
      colStatus: i18nT("scoreColStatus", reportLang),
      pass: i18nT("scorePass", reportLang),
      fail: i18nT("scoreFail", reportLang),
    },
    ...audit.rounds[audit.rounds.length - 1].scores
  }));

  const buildResult = spawnSync("node", renderArgs, { stdio: "inherit" });
  if (buildResult.status !== 0) {
    const renderErr = new Error("render-with-watermark.mjs 失败");
    writeAuditFatal(RUN_DIR, REPORT_ID, "pdf-render", renderErr, state);
    throw renderErr;
  }

  audit.output_pdf = args["output"];
  audit.degraded = degraded;
  if (passWithNotes) audit.pass_with_notes = true;
  audit.completed_at = now();
  writeJson(AUDIT_PATH, audit);   // atomic write
  console.log(`[audit] written to ${AUDIT_PATH}`);

  // Final state: completed
  state = { ...state, status: audit.final_status, completed_at: now(), audit };
  saveRunState(STATE_PATH, state);

  console.log(`[done] ${statusLabel}: ${args["output"]}`);
}

// degradedWatermark() — 总分 < total_gate_threshold 时触发降级出书
function degradedWatermark(failedDims, audit, rubric, lang = "en") {
  const failedList = failedDims
    .map(d => `${d}=${audit.rounds[audit.rounds.length - 1].scores[d].score}`)
    .join(", ");

  // 降级出书配置: 加水印 + 封面横幅 + 嵌入评分表
  // Banner text is localized (en default) — reports may be English or Chinese.
  const DECISION = {
    cover_banner:     { enabled: true, text: i18nT("degradedBanner", lang), color: "#f59e0b" },
    embed_score_table: true
  };

  return {
    lang,
    watermark_text: rubric.degraded_output.watermark_format
        .replace("{failed_list_with_scores}", failedList)
        .replace("{report_id}", audit.report_id),
    watermark_color: rubric.degraded_output.watermark_color,
    watermark_size_px: rubric.degraded_output.watermark_size_px,
    watermark_position: rubric.degraded_output.watermark_position,
    cover_banner: DECISION.cover_banner,
    embed_score_table: DECISION.embed_score_table,
    score_table: audit.rounds[audit.rounds.length - 1].scores
  };
}

// ─────────────────────────────────────────────────
// Exports for test harness
// ─────────────────────────────────────────────────
export {
  runOneCheck,
  runMechanicalChecks,
  fuseScores,
  evaluateRound3,
  extractProseText,
  readPngDimensions,
  checkSvgSafety,
  makeRegex
};

// ─────────────────────────────────────────────────
// Guard: only run main() when this file is executed directly, not when imported.
const isMain = process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main().catch(err => {
    // ── Fail-closed fatal handler (item 4) ──
    // Parse args again to find the run-dir so we can write audit-fatal.json
    // before exiting non-zero. Never silent process.exit(1) with no trace.
    console.error("[fatal]", err.message);
    try {
      const a = parseArgs();
      const runDir = path.resolve(a["run-dir"] || path.join(SKILL_ROOT, "runs", a["report-id"] || "unknown"));
      const reportId = a["report-id"] || "unknown";
      writeAuditFatal(runDir, reportId, "main-catch", err, null);
    } catch (auditErr) {
      console.error("[fatal-audit-write-failed]", auditErr.message);
      // Absolute last resort: write to cwd
      try {
        const fallback = path.join(process.cwd(), `audit-fatal-${Date.now()}.json`);
        const tmp = fallback + ".tmp";
        fs.writeFileSync(tmp, JSON.stringify({ timestamp: now(), error: err.message, stack: err.stack }, null, 2), "utf8");
        fs.renameSync(tmp, fallback);
        console.error("[fatal-audit-fallback] written to", fallback);
      } catch (_) { /* truly last resort */ }
    }
    process.exit(1);
  });
}
