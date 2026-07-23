#!/usr/bin/env node
/**
 * dispatch-runner.mjs
 *
 * 消费 dispatch-queue.json 中的 PENDING 请求, 调度对应的 subagent prompt
 * (agents/01-04.md), 把产物路径写回 result_path 并标 status=DONE.
 *
 * 提供 6 种 runner 后端 (--backend), 让 enforce-gate.mjs 不用关心
 * agent 怎么实际跑:
 *
 *   --backend=claude-cli      (推荐, 本地生产)
 *      调用 `claude --agent-prompt <path> --context <json>` (claude-code CLI).
 *      需要 CLAUDE_CLI_BIN 环境变量, 默认 `claude`.
 *
 *   --backend=anthropic-api   (推荐, 云端部署)
 *      使用 ANTHROPIC_API_KEY + @anthropic-ai/sdk 直接调用 Claude API.
 *      模型可通过 DISPATCH_MODEL 环境变量覆盖, 默认 claude-opus-4-8.
 *      DISPATCH_API_BASE 可设自定义 base URL (如 Azure / 代理).
 *
 *   --backend=openai-api      (OpenAI / 兼容端点)
 *      使用 OPENAI_API_KEY + openai npm 包.
 *      模型默认 gpt-4o. DISPATCH_API_BASE 可指向 Azure OpenAI 或本地代理.
 *
 *   --backend=gemini-api      (Google Gemini)
 *      使用 GEMINI_API_KEY (或 GOOGLE_API_KEY) + @google/generative-ai.
 *      模型默认 gemini-2.5-pro.
 *
 *   --backend=mock            (测试用)
 *      读 examples/mock-{agent}.json 直接当作产物落盘, 不调任何 LLM.
 *      用于 baseline test / CI 验证 enforce-gate 主循环逻辑.
 *
 *   --backend=manual          (调试用, 不可用于无人值守)
 *      把 prompt + context 打印到 stdout, 等人工把产物路径手写回 queue.
 *      用于第一次调试或 debug rubric reviewer 偏差.
 *      NOTE: manual backend is INTERACTIVE ONLY. Any attempt to use it in
 *      --watch/unattended mode will be refused at startup.
 *
 * 环境变量:
 *   ANTHROPIC_API_KEY   — anthropic-api backend 必需
 *   OPENAI_API_KEY      — openai-api backend 必需
 *   GEMINI_API_KEY      — gemini-api backend 必需 (也接受 GOOGLE_API_KEY)
 *   CLAUDE_CLI_BIN      — claude-cli backend bin 路径, 默认 `claude`
 *   DISPATCH_MODEL      — 覆盖 API backend 的模型 ID
 *   DISPATCH_API_BASE   — 自定义 base URL (仅 openai-api; 用于 Azure / 本地代理)
 *
 * 用法:
 *   # 一次性消费所有 PENDING (退出后 enforce-gate 接管下一轮)
 *   node scripts/dispatch-runner.mjs --backend=mock --once
 *
 *   # 云端 API 模式 (无本地 CLI 依赖)
 *   ANTHROPIC_API_KEY=sk-... node scripts/dispatch-runner.mjs --backend=anthropic-api --watch --run-dir=./runs/MCW-001
 *
 *   # 守护模式 (推荐配合 enforce-gate 同时跑, 由 run.mjs 自动 spawn)
 *   node scripts/dispatch-runner.mjs --backend=claude-cli --watch --run-dir=./runs/MCW-001
 *
 *   # Backend contract verification (mock backend: trivially passes; claude-cli: binary probe)
 *   node scripts/dispatch-runner.mjs --backend=mock --verify-backend
 *
 * ─────────────────────────────────────────────────────────────────────
 * CLAUDE-CLI BACKEND CONTRACT (pinned — do NOT change without ADR)
 * ─────────────────────────────────────────────────────────────────────
 * Invocation:
 *   $CLAUDE_CLI_BIN --agent-prompt-file <path-to-agent.md> \
 *                   --context-json <json-string> \
 *                   --output-dir <path>
 *
 * Expected stdout protocol:
 *   The CLI MUST print exactly one line of the form:
 *     RESULT_PATH:<absolute-path-to-result-file>
 *   to stdout. The runner parses this line to find the output artifact.
 *
 * Failure modes:
 *   - exit status != 0        → FAILED with stderr as error message
 *   - no RESULT_PATH: line    → FAILED with "claude-cli 未返回 RESULT_PATH 标记"
 *   - RESULT_PATH file missing → FAILED with "result file not found"
 *
 * NOTE: The real Claude Code CLI flags (--agent-prompt-file / --context-json /
 * --output-dir) may differ in production. Verify with `claude --help` in the
 * deploy environment and update this section + runClaudeCli() accordingly.
 * A --verify-backend run in the deploy env confirms the contract.
 * ─────────────────────────────────────────────────────────────────────
 *
 * ─────────────────────────────────────────────────────────────────────
 * API BACKEND CONTRACT (anthropic-api / openai-api / gemini-api)
 * ─────────────────────────────────────────────────────────────────────
 * Each API backend:
 *   1. Reads the prompt file at req.prompt_path
 *   2. Appends context JSON as a user message
 *   3. Calls the API with the configured model
 *   4. Writes the response text to RESULT_PATH as a .txt file
 *   5. Returns { status: "DONE", result_path }
 *
 * SDK packages are loaded via LAZY dynamic import() so this file passes
 * `node --check` even if the packages are not installed. Each SDK is only
 * imported when that backend is actually selected.
 *
 * Install SDKs (optional):
 *   npm i --include=optional        # install all three
 *   npm i @anthropic-ai/sdk         # Anthropic only
 *   npm i openai                    # OpenAI only
 *   npm i @google/generative-ai     # Gemini only
 * ─────────────────────────────────────────────────────────────────────
 */

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, "..");

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    backend: "mock",
    once: false,
    watch: false,
    pollMs: 3000,
    runDir: null,
    verifyBackend: false
  };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a.startsWith("--backend="))    { opts.backend = a.split("=").slice(1).join("="); }
    else if (a === "--once")           { opts.once = true; }
    else if (a === "--watch")          { opts.watch = true; }
    else if (a.startsWith("--poll-ms=")) { opts.pollMs = parseInt(a.split("=")[1], 10); }
    else if (a.startsWith("--run-dir=")) { opts.runDir = a.split("=").slice(1).join("="); }
    else if (a === "--run-dir" && args[i+1]) { opts.runDir = args[++i]; }
    else if (a === "--verify-backend") { opts.verifyBackend = true; }
  }
  // Default run-dir: skill root (backward compat for standalone use)
  if (!opts.runDir) opts.runDir = SKILL_ROOT;
  return opts;
}

// ─────────────────────────────────────────────────────
// Atomic write helpers
// ─────────────────────────────────────────────────────
function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

/**
 * Atomic write: write to temp + rename (item 2).
 * A crash mid-write never leaves a torn queue file.
 */
function writeQueueAtomic(queuePath, queue) {
  ensureDir(path.dirname(queuePath));
  const tmp = queuePath + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(queue, null, 2), "utf8");
  fs.renameSync(tmp, queuePath);
}

function readQueue(queuePath) {
  if (!fs.existsSync(queuePath)) return [];
  try {
    return JSON.parse(fs.readFileSync(queuePath, "utf8"));
  } catch (_) {
    // Mid-write corruption: return empty, retry next tick
    return [];
  }
}

function now() {
  return new Date().toISOString();
}

// ─────────────────────────────────────────────────────
// Startup validation
// ─────────────────────────────────────────────────────
function validateStartup(opts) {
  // Refuse manual backend in unattended (watch) mode
  if (opts.backend === "manual" && opts.watch) {
    console.error("[runner-fatal] manual backend is INTERACTIVE ONLY and cannot be used with --watch.");
    console.error("               Use --backend=mock or --backend=claude-cli for unattended runs.");
    process.exit(1);
  }
}

// ─────────────────────────────────────────────────────────────────────
// Backend: claude-cli (生产)
//
// CONTRACT (Claude Code CLI v2.x, `claude -p` 非交互模式):
//   Invoke: $CLAUDE_CLI_BIN -p "<combined_prompt>" --dangerously-skip-permissions
//   Agent prompt (md) + context JSON 合并为单一 prompt 传入。
//   Agent 被要求将产物写入 result_path（由 context 提供），完成后输出 "RESULT_PATH:<path>"。
//   Timeout: 5 minutes per agent
//   On non-zero exit, timeout, or missing result file → FAILED
// ─────────────────────────────────────────────────────────────────────
function runClaudeCli(req, runDir) {
  const claudeBin = process.env.CLAUDE_CLI_BIN || "claude";

  if (!claudeBin.includes(path.sep) && !path.isAbsolute(claudeBin)) {
    console.warn(`[runner] WARN: CLAUDE_CLI_BIN='${claudeBin}' is a bare name (PATH-dependent). Set an absolute path for unattended use.`);
  }

  // Write context to file
  const ctxDir = path.join(runDir, "ctx");
  ensureDir(ctxDir);
  const ctxFile = path.join(ctxDir, `${req.request_id}-context.json`);
  const ctxTmp  = ctxFile + ".tmp." + process.pid;
  fs.writeFileSync(ctxTmp, JSON.stringify(req.context, null, 2), "utf8");
  fs.renameSync(ctxTmp, ctxFile);

  // 读取 agent prompt 内容
  const agentPrompt = fs.existsSync(req.prompt_path)
    ? fs.readFileSync(req.prompt_path, "utf8")
    : `You are the ${req.agent} agent.`;

  const contextStr = JSON.stringify(req.context, null, 2);
  const resultPath = req.context.result_path || path.join(runDir, `${req.request_id}-result.txt`);

  // 构建完整 prompt：agent 角色 + 上下文 + 明确写文件指令
  const fullPrompt = `${agentPrompt}

---
## TASK CONTEXT (JSON)
${contextStr}

---
## EXECUTION INSTRUCTION
Complete your role as defined above using the provided context.
When done, write your complete output to this file:
  ${resultPath}

After writing the file, output EXACTLY this line (nothing else after it):
RESULT_PATH:${resultPath}
`;

  const result = spawnSync(claudeBin, [
    "--print",
    "--dangerously-skip-permissions",
    fullPrompt
  ], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 8 * 60 * 1000   // 8 min for real LLM calls
  });

  if (result.error && result.error.code === "ETIMEDOUT") {
    return { status: "FAILED", error: `claude-cli timeout after 8m (${req.request_id})` };
  }
  if (result.status !== 0) {
    return { status: "FAILED", error: result.stderr || `exit ${result.status}` };
  }

  // 若 agent 已写文件，直接返回（不强依赖 RESULT_PATH 行）
  if (fs.existsSync(resultPath)) {
    return { status: "DONE", result_path: resultPath };
  }

  // 兜底：从 stdout 找 RESULT_PATH 行
  const stdoutLines = (result.stdout || "").split("\n").filter(l => l.startsWith("RESULT_PATH:"));
  if (stdoutLines.length > 0) {
    const rp = stdoutLines[0].replace("RESULT_PATH:", "").trim();
    if (fs.existsSync(rp)) return { status: "DONE", result_path: rp };
  }

  // 最后兜底：把 stdout 内容直接写为结果文件
  if (result.stdout && result.stdout.trim().length > 0) {
    fs.writeFileSync(resultPath, result.stdout, "utf8");
    console.warn(`[runner] WARN: agent did not write result file; saved stdout as result: ${resultPath}`);
    return { status: "DONE", result_path: resultPath };
  }

  return { status: "FAILED", error: "claude-cli 无有效输出 (empty stdout, no result file)" };
}

// ─────────────────────────────────────────────
// Backend: mock (测试)
// ─────────────────────────────────────────────
function runMock(req, runDir) {
  const mockMap = {
    "data-collector":  "mock-data-collector-output.json",
    "content-writer":  "mock-content-writer-output.html",
    "visual-designer":   "mock-visual-designer-output.html",
    "rubric-reviewer": "mock-rubric-reviewer-output.json"
  };
  const mockFile = mockMap[req.agent];
  if (!mockFile) return { status: "FAILED", error: `mock 不支持 agent: ${req.agent}` };
  const mockPath = path.join(SKILL_ROOT, "examples", mockFile);
  if (!fs.existsSync(mockPath)) return { status: "FAILED", error: `mock 文件缺失: ${mockPath}` };

  // Atomic copy to per-run outputs dir (items 2+3)
  const outDir = path.join(runDir, "outputs", req.request_id);
  ensureDir(outDir);
  const ext = path.extname(mockFile);
  const resultPath = path.join(outDir, `result${ext}`);
  const tmpPath = resultPath + ".tmp." + process.pid;
  fs.copyFileSync(mockPath, tmpPath);
  fs.renameSync(tmpPath, resultPath);
  return { status: "DONE", result_path: resultPath };
}

// ─────────────────────────────────────────────
// Backend: manual (调试, 不可用于无人值守)
// ─────────────────────────────────────────────
function runManual(req) {
  console.log("\n" + "─".repeat(70));
  console.log(`[manual] request_id: ${req.request_id}`);
  console.log(`[manual] agent: ${req.agent}`);
  console.log(`[manual] prompt: ${req.prompt_path}`);
  console.log(`[manual] context: ${JSON.stringify(req.context, null, 2)}`);
  console.log("─".repeat(70));
  console.log(`请人工跑这个 agent, 把产物路径写到 dispatch-queue.json 中本条目的 result_path, status 设为 DONE`);
  console.log(`然后回车继续...`);
  return { status: "PENDING", note: "awaiting manual completion" };
}

// ─────────────────────────────────────────────────────────────────────
// Helper: build the prompt text for API backends
// Reads prompt file + serialises context into a single user message.
// ─────────────────────────────────────────────────────────────────────
function buildApiPrompt(req) {
  let promptText = "";
  if (req.prompt_path && fs.existsSync(req.prompt_path)) {
    promptText = fs.readFileSync(req.prompt_path, "utf8");
  }

  // Inject file contents for API backends (no filesystem access)
  const FILE_KEYS = ["source_path", "data_path", "draft_html", "rubric_path", "reviewer_feedback"];
  const ctx = req.context || {};
  let filesBlock = "";
  const ctxMeta = {};

  for (const [k, v] of Object.entries(ctx)) {
    if (FILE_KEYS.includes(k) && typeof v === "string" && v && v !== "null") {
      if (fs.existsSync(v)) {
        const content = fs.readFileSync(v, "utf8");
        const truncated = content.length > 50000 ? content.slice(0, 50000) + "\n... [truncated]" : content;
        filesBlock += `\n\n=== FILE: ${k} (${v}) ===\n${truncated}\n`;
        ctxMeta[k] = v; // keep path in metadata
      } else {
        ctxMeta[k] = v;
      }
    } else {
      ctxMeta[k] = v;
    }
  }

  const ctxBlock = JSON.stringify(ctxMeta, null, 2);
  let result = `${promptText}\n\n---\nCONTEXT:\n${ctxBlock}`;
  if (filesBlock) {
    result += `\n\n---\nFILE CONTENTS (injected for API backend):${filesBlock}\n\nIMPORTANT: Use the file contents above directly. Do NOT attempt to read files from disk. Output your result as direct content (HTML/JSON/SVG) without markdown code fences or explanatory preamble.`;
  }
  return result;
}

// ─────────────────────────────────────────────────────────────────────
// Helper: write API response to result file and return DONE record
// ─────────────────────────────────────────────────────────────────────
async function writeApiResult(text, req, runDir) {
  const outDir = path.join(runDir, "outputs", req.request_id);
  ensureDir(outDir);
  const resultPath = path.join(outDir, "result.txt");
  const tmp = resultPath + ".tmp." + process.pid;

  // Strip markdown code fences if present (API models often wrap output)
  let cleaned = text.trim();
  if (cleaned.startsWith("```")) {
    // Remove opening fence (with optional language tag like ```html, ```json)
    cleaned = cleaned.replace(/^```[a-zA-Z]*\n?/, "");
    // Remove closing fence
    cleaned = cleaned.replace(/\n?```$/s, "");
    cleaned = cleaned.trim();
  }

  // Post-process visual-designer output: merge FigureSpec JSON into analyst HTML
  if (req.agent === "visual-designer" && req.context?.draft_html && req.context?.data_path) {
    try {
      const parsed = JSON.parse(cleaned);
      if (parsed.figure_specs || parsed.report_id) {
        // This is FigureSpec JSON — need to render into HTML
        const specsPath = path.join(outDir, "specs.json");
        fs.writeFileSync(specsPath, JSON.stringify(parsed, null, 2), "utf8");

        // Read the analyst draft HTML
        let draftHtml = fs.readFileSync(req.context.draft_html, "utf8");

        // Try to render figures using render-figures logic (inline import)
        const htmlPath = path.join(outDir, "merged.html");
        fs.writeFileSync(htmlPath, draftHtml, "utf8");

        // spawn render-figures.mjs
        const renderResult = spawnSync("node", [
          path.join(__dirname, "render-figures.mjs"),
          "--specs", specsPath,
          "--html", htmlPath,
          "--no-raster"  // skip PNG for speed, use inline SVG
        ], { encoding: "utf8", timeout: 60000 });

        if (renderResult.status === 0) {
          // Read the merged HTML with charts injected
          const mergedHtml = fs.readFileSync(htmlPath, "utf8");
          fs.writeFileSync(tmp, mergedHtml, "utf8");
          fs.renameSync(tmp, resultPath);
          console.log(`[api-postprocess] visual-designer: merged ${parsed.figure_specs?.length || 0} figures into HTML (${mergedHtml.length} chars)`);
          return { status: "DONE", result_path: resultPath };
        } else {
          // render-figures failed — fall back to analyst HTML as-is
          console.error(`[api-postprocess] render-figures failed: ${renderResult.stderr?.slice(0, 200)}`);
          fs.writeFileSync(tmp, draftHtml, "utf8");
          fs.renameSync(tmp, resultPath);
          return { status: "DONE", result_path: resultPath };
        }
      }
    } catch (e) {
      // Not JSON or post-process failed — use raw text
      console.error(`[api-postprocess] visual-designer post-process skipped: ${e.message.slice(0, 100)}`);
    }
  }

  // Strip explanatory preamble for content-writer (should start with <!DOCTYPE or <html)
  if (req.agent === "content-writer") {
    const htmlStart = cleaned.indexOf("<!DOCTYPE");
    const htmlStart2 = cleaned.indexOf("<html");
    const earliest = htmlStart >= 0 ? htmlStart : htmlStart2;
    if (earliest > 0) {
      cleaned = cleaned.slice(earliest);
    }
    // Also strip trailing text after </html>
    const htmlEnd = cleaned.lastIndexOf("</html>");
    if (htmlEnd >= 0 && htmlEnd < cleaned.length - 10) {
      cleaned = cleaned.slice(0, htmlEnd + 7);
    }
  }

  // Fix Chinese quotes and other non-ASCII quote chars inside JSON (rubric-reviewer)
  if (req.agent === "rubric-reviewer") {
    cleaned = cleaned.replace(/\u201C/g, '\\u201C');  // “ → escaped
    cleaned = cleaned.replace(/\u201D/g, '\\u201D');  // ” → escaped
    cleaned = cleaned.replace(/\u2018/g, '\\u2018');  // ‘ → escaped
    cleaned = cleaned.replace(/\u2019/g, '\\u2019');  // ’ → escaped
  }

  fs.writeFileSync(tmp, cleaned, "utf8");
  fs.renameSync(tmp, resultPath);
  return { status: "DONE", result_path: resultPath };
}

// Helper for lazy child_process import (no-op, kept for reference)
function await_import_child_process() {
  return { spawnSync };
}

// ─────────────────────────────────────────────────────────────────────
// Shared API-backend helpers (P1-4 / P1-5 / P1-7)
// ─────────────────────────────────────────────────────────────────────

// Agents whose output contract is a JSON object (not HTML). For these we ask
// the provider for native structured output instead of hoping the prompt holds.
function isJsonAgent(agent) {
  return agent === "data-collector" || agent === "rubric-reviewer" || agent === "visual-designer";
}

// Resolve the model id. DISPATCH_MODEL always wins. When falling back to the
// built-in default on an API backend, warn loudly: hardcoded model ids drift
// and a retired id is a silent 404 at call time (gemini-1.5-pro was exactly this).
function resolveModel(provider, fallback) {
  if (process.env.DISPATCH_MODEL) return process.env.DISPATCH_MODEL;
  console.warn(
    `[dispatch-runner] using built-in default model "${fallback}" for ${provider}. ` +
    `Model ids drift between provider releases — if calls 404, set DISPATCH_MODEL to a current GA id.`
  );
  return fallback;
}

// Allowlist guard for DISPATCH_API_BASE (openai-api only). Pointing the base URL
// at an arbitrary relay would exfiltrate the full source document (buildApiPrompt
// injects it) to a third party — a data-egress red line. Require an explicit
// opt-in env (DISPATCH_ALLOW_CUSTOM_BASE=1) for non-official hosts, and always
// record a custom base so compliance lint can see it.
const OFFICIAL_API_HOSTS = [/(^|\.)openai\.com$/i, /(^|\.)openai\.azure\.com$/i, /(^|\.)azure\.com$/i];
function checkApiBase(base) {
  let host;
  try {
    host = new URL(base).host.split(":")[0];
  } catch (_) {
    return { ok: false, error: `DISPATCH_API_BASE is not a valid URL: ${base}` };
  }
  const official = OFFICIAL_API_HOSTS.some(re => re.test(host));
  if (official) return { ok: true, host, custom: false };
  if (process.env.DISPATCH_ALLOW_CUSTOM_BASE === "1") {
    console.warn(
      `[dispatch-runner] DISPATCH_API_BASE points at non-official host "${host}". ` +
      `Source document content WILL be sent there — treat as data egress; compliance must approve.`
    );
    return { ok: true, host, custom: true };
  }
  return {
    ok: false,
    error: `DISPATCH_API_BASE host "${host}" is not an official endpoint. ` +
      `Sending the source document there is data egress. ` +
      `Set DISPATCH_ALLOW_CUSTOM_BASE=1 to opt in explicitly (and get compliance sign-off).`
  };
}

// ─────────────────────────────────────────────────────────────────────
// Backend: anthropic-api
//
// Uses ANTHROPIC_API_KEY + @anthropic-ai/sdk (lazy import).
// Model: DISPATCH_MODEL env var, default claude-opus-4-8.
// Fail-closed if ANTHROPIC_API_KEY is not set.
// ─────────────────────────────────────────────────────────────────────
async function runAnthropicApi(req, runDir) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return {
      status: "FAILED",
      error: "ANTHROPIC_API_KEY not set — set the env var to use anthropic-api backend"
    };
  }

  let Anthropic;
  try {
    ({ default: Anthropic } = await import("@anthropic-ai/sdk"));
  } catch (err) {
    return {
      status: "FAILED",
      error: `@anthropic-ai/sdk not installed — run: npm i @anthropic-ai/sdk (${err.message})`
    };
  }

  const model = resolveModel("anthropic", "claude-opus-4-8");
  const client = new Anthropic({ apiKey });

  const userContent = buildApiPrompt(req);

  const maxTokens = req.agent === "rubric-reviewer" ? 16384 : (req.agent === "content-writer" || req.agent === "visual-designer") ? 8192 : 6144;
  let response;
  try {
    response = await client.messages.create({
      model,
      max_tokens: maxTokens,
      messages: [{ role: "user", content: userContent }]
    });
  } catch (err) {
    return { status: "FAILED", error: `anthropic-api call failed: ${err.message}` };
  }

  const text = (response.content || [])
    .filter(b => b.type === "text")
    .map(b => b.text)
    .join("\n");

  if (!text) {
    return { status: "FAILED", error: "anthropic-api returned empty response" };
  }

  return await writeApiResult(text, req, runDir);
}

// ─────────────────────────────────────────────────────────────────────
// Backend: openai-api
//
// Uses OPENAI_API_KEY + openai npm package (lazy import).
// Model: DISPATCH_MODEL env var, default gpt-4o.
// DISPATCH_API_BASE sets custom base URL (Azure OpenAI / local proxy).
// Fail-closed if OPENAI_API_KEY is not set.
// ─────────────────────────────────────────────────────────────────────
async function runOpenAiApi(req, runDir) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return {
      status: "FAILED",
      error: "OPENAI_API_KEY not set — set the env var to use openai-api backend"
    };
  }

  let OpenAI;
  try {
    ({ default: OpenAI } = await import("openai"));
  } catch (err) {
    return {
      status: "FAILED",
      error: `openai package not installed — run: npm i openai (${err.message})`
    };
  }

  const model = resolveModel("openai", "gpt-4o");
  const clientOpts = { apiKey };
  if (process.env.DISPATCH_API_BASE) {
    const baseCheck = checkApiBase(process.env.DISPATCH_API_BASE);
    if (!baseCheck.ok) {
      return { status: "FAILED", error: baseCheck.error };
    }
    clientOpts.baseURL = process.env.DISPATCH_API_BASE;
  }
  const client = new OpenAI(clientOpts);

  const userContent = buildApiPrompt(req);

  const maxTokens = req.agent === "rubric-reviewer" ? 16384 : (req.agent === "content-writer" || req.agent === "visual-designer") ? 8192 : 6144;
  const createOpts = {
    model,
    max_tokens: maxTokens,
    messages: [{ role: "user", content: userContent }]
  };
  // P1-5 structured outputs: force JSON for agents whose contract is a JSON object.
  // json_object mode requires the literal word "json" in the prompt (buildApiPrompt asks for JSON).
  if (isJsonAgent(req.agent)) {
    createOpts.response_format = { type: "json_object" };
  }
  let response;
  try {
    response = await client.chat.completions.create(createOpts);
  } catch (err) {
    return { status: "FAILED", error: `openai-api call failed: ${err.message}` };
  }

  const text = response.choices?.[0]?.message?.content || "";
  if (!text) {
    return { status: "FAILED", error: "openai-api returned empty response" };
  }

  return await writeApiResult(text, req, runDir);
}

// ─────────────────────────────────────────────────────────────────────
// Backend: gemini-api
//
// Uses GEMINI_API_KEY (or GOOGLE_API_KEY) + @google/generative-ai (lazy import).
// Model: DISPATCH_MODEL env var, default gemini-2.5-pro.
// Fail-closed if neither GEMINI_API_KEY nor GOOGLE_API_KEY is set.
// ─────────────────────────────────────────────────────────────────────
async function runGeminiApi(req, runDir) {
  const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return {
      status: "FAILED",
      error: "GEMINI_API_KEY not set — set the env var to use gemini-api backend (also accepts GOOGLE_API_KEY)"
    };
  }

  let GoogleGenerativeAI;
  try {
    ({ GoogleGenerativeAI } = await import("@google/generative-ai"));
  } catch (err) {
    return {
      status: "FAILED",
      error: `@google/generative-ai not installed — run: npm i @google/generative-ai (${err.message})`
    };
  }

  // gemini-1.5-pro is retired; default to a current-generation id. Override with DISPATCH_MODEL.
  const modelName = resolveModel("gemini", "gemini-2.5-pro");
  const genAI = new GoogleGenerativeAI(apiKey);
  const modelOpts = { model: modelName };
  // P1-5 structured outputs: ask Gemini for JSON mime when the agent contract is JSON.
  if (isJsonAgent(req.agent)) {
    modelOpts.generationConfig = { responseMimeType: "application/json" };
  }
  const model = genAI.getGenerativeModel(modelOpts);

  const userContent = buildApiPrompt(req);

  let result;
  try {
    result = await model.generateContent(userContent);
  } catch (err) {
    return { status: "FAILED", error: `gemini-api call failed: ${err.message}` };
  }

  const text = result?.response?.text?.() || "";
  if (!text) {
    return { status: "FAILED", error: "gemini-api returned empty response" };
  }

  return await writeApiResult(text, req, runDir);
}

// ─────────────────────────────────────────────
// Backend contract verification (--verify-backend, item 6)
// ─────────────────────────────────────────────
async function verifyBackend(backend) {
  if (backend === "mock") {
    const mockFiles = [
      "mock-data-collector-output.json",
      "mock-content-writer-output.html",
      "mock-visual-designer-output.html",
      "mock-rubric-reviewer-output.json",
    ];
    const missing = mockFiles.filter(f => !fs.existsSync(path.join(SKILL_ROOT, "examples", f)));
    if (missing.length > 0) {
      console.error(`[verify-backend] FAIL: missing mock fixtures: ${missing.join(", ")}`);
      process.exit(1);
    }
    console.log("[verify-backend] mock backend OK — all 4 fixture files present");
    return;
  }
  if (backend === "claude-cli") {
    const claudeBin = process.env.CLAUDE_CLI_BIN || "claude";
    console.log(`[verify-backend] claude-cli: bin='${claudeBin}'`);
    const versionResult = spawnSync(claudeBin, ["--version"], {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["ignore", "pipe", "pipe"]
    });
    if (versionResult.status === 0 && versionResult.stdout) {
      console.log(`[verify-backend] claude-cli version: ${versionResult.stdout.trim()}`);
    } else {
      console.log(`[verify-backend] claude-cli --version returned exit=${versionResult.status} (binary may still be valid)`);
    }
    console.log("[verify-backend] CONTRACT: claude <bin> --agent-prompt-file <md> --context-json <ctx-file> --output-dir <dir>");
    console.log("[verify-backend] CONTRACT: stdout must contain 'RESULT_PATH:<path>' line");
    console.log("[verify-backend] NOTE: Real round-trip contract must be verified in deploy env.");
    if (path.isAbsolute(claudeBin) && !fs.existsSync(claudeBin)) {
      console.error(`[verify-backend] FAIL: CLAUDE_CLI_BIN='${claudeBin}' not on disk`);
      process.exit(1);
    }
    console.log("[verify-backend] claude-cli binary check passed.");
    return;
  }
  if (backend === "anthropic-api") {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      console.error("[verify-backend] FAIL: ANTHROPIC_API_KEY not set — set the env var to use anthropic-api backend");
      process.exit(1);
    }
    let Anthropic;
    try {
      ({ default: Anthropic } = await import("@anthropic-ai/sdk"));
    } catch (err) {
      console.error(`[verify-backend] FAIL: @anthropic-ai/sdk not installed — run: npm i @anthropic-ai/sdk`);
      process.exit(1);
    }
    const model = process.env.DISPATCH_MODEL || "claude-opus-4-8";
    console.log(`[verify-backend] anthropic-api: model='${model}', key set (length=${apiKey.length})`);
    const client = new Anthropic({ apiKey });
    try {
      const resp = await client.messages.create({
        model,
        max_tokens: 10,
        messages: [{ role: "user", content: "reply with the word PONG" }]
      });
      const text = (resp.content || []).filter(b => b.type === "text").map(b => b.text).join("");
      if (!text) {
        console.error("[verify-backend] FAIL: anthropic-api probe returned empty response");
        process.exit(1);
      }
      console.log(`[verify-backend] anthropic-api probe OK — response: '${text.slice(0, 50)}'`);
    } catch (err) {
      console.error(`[verify-backend] FAIL: anthropic-api probe failed: ${err.message}`);
      process.exit(1);
    }
    return;
  }
  if (backend === "openai-api") {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      console.error("[verify-backend] FAIL: OPENAI_API_KEY not set — set the env var to use openai-api backend");
      process.exit(1);
    }
    let OpenAI;
    try {
      ({ default: OpenAI } = await import("openai"));
    } catch (err) {
      console.error(`[verify-backend] FAIL: openai package not installed — run: npm i openai`);
      process.exit(1);
    }
    const model = process.env.DISPATCH_MODEL || "gpt-4o";
    const clientOpts = { apiKey };
    if (process.env.DISPATCH_API_BASE) {
      clientOpts.baseURL = process.env.DISPATCH_API_BASE;
      console.log(`[verify-backend] openai-api: using custom base URL '${process.env.DISPATCH_API_BASE}'`);
    }
    console.log(`[verify-backend] openai-api: model='${model}', key set (length=${apiKey.length})`);
    const client = new OpenAI(clientOpts);
    try {
      const resp = await client.chat.completions.create({
        model,
        max_tokens: 10,
        messages: [{ role: "user", content: "reply with the word PONG" }]
      });
      const text = resp.choices?.[0]?.message?.content || "";
      if (!text) {
        console.error("[verify-backend] FAIL: openai-api probe returned empty response");
        process.exit(1);
      }
      console.log(`[verify-backend] openai-api probe OK — response: '${text.slice(0, 50)}'`);
    } catch (err) {
      console.error(`[verify-backend] FAIL: openai-api probe failed: ${err.message}`);
      process.exit(1);
    }
    return;
  }
  if (backend === "gemini-api") {
    const apiKey = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
    if (!apiKey) {
      console.error("[verify-backend] FAIL: GEMINI_API_KEY not set — set the env var to use gemini-api backend (also accepts GOOGLE_API_KEY)");
      process.exit(1);
    }
    let GoogleGenerativeAI;
    try {
      ({ GoogleGenerativeAI } = await import("@google/generative-ai"));
    } catch (err) {
      console.error(`[verify-backend] FAIL: @google/generative-ai not installed — run: npm i @google/generative-ai`);
      process.exit(1);
    }
    const modelName = process.env.DISPATCH_MODEL || "gemini-2.5-pro";
    console.log(`[verify-backend] gemini-api: model='${modelName}', key set (length=${apiKey.length})`);
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: modelName });
    try {
      const result = await model.generateContent("reply with the word PONG");
      const text = result?.response?.text?.() || "";
      if (!text) {
        console.error("[verify-backend] FAIL: gemini-api probe returned empty response");
        process.exit(1);
      }
      console.log(`[verify-backend] gemini-api probe OK — response: '${text.slice(0, 50)}'`);
    } catch (err) {
      console.error(`[verify-backend] FAIL: gemini-api probe failed: ${err.message}`);
      process.exit(1);
    }
    return;
  }
  if (backend === "manual") {
    console.error("[verify-backend] manual backend cannot be verified — it is interactive-only.");
    process.exit(1);
  }
  console.error(`[verify-backend] unknown backend: '${backend}'`);
  process.exit(1);
}

// ─────────────────────────────────────────────
// 主循环
// ─────────────────────────────────────────────
async function processOne(req, backend, runDir) {
  console.log(`[runner] processing ${req.request_id} (${req.agent}) via ${backend}`);
  let result;
  try {
    switch (backend) {
      case "claude-cli":    result = runClaudeCli(req, runDir); break;
      case "mock":          result = runMock(req, runDir); break;
      case "manual":        result = runManual(req); break;
      case "anthropic-api": result = await runAnthropicApi(req, runDir); break;
      case "openai-api":    result = await runOpenAiApi(req, runDir); break;
      case "gemini-api":    result = await runGeminiApi(req, runDir); break;
      default:              result = { status: "FAILED", error: `unknown backend: ${backend}` };
    }
  } catch (err) {
    // Wrap so a bad queue item logs+continues rather than killing the runner (item 2)
    result = { status: "FAILED", error: `processOne threw: ${err.message}` };
  }
  return {
    ...req,
    status: result.status,
    result_path: result.result_path,
    error: result.error,
    completed_at: result.status === "DONE" ? now() : undefined
  };
}

async function tick(backend, runDir) {
  // Per-run namespaced queue (item 3)
  const queuePath = path.join(runDir, "dispatch-queue.json");
  const queue = readQueue(queuePath);
  const pending = queue.filter(r => r.status === "PENDING");
  if (pending.length === 0) return 0;

  for (const req of pending) {
    const idx = queue.findIndex(r => r.request_id === req.request_id);
    queue[idx] = await processOne(req, backend, runDir);
    writeQueueAtomic(queuePath, queue);   // atomic write per item (item 2)
  }
  return pending.length;
}

async function main() {
  const opts = parseArgs();

  // --verify-backend mode (item 6)
  if (opts.verifyBackend) {
    await verifyBackend(opts.backend);
    process.exit(0);
  }

  validateStartup(opts);   // refuse manual+watch
  console.log(`[runner] backend=${opts.backend}, mode=${opts.watch ? "watch" : "once"}, run-dir=${opts.runDir}`);

  if (opts.once) {
    try {
      const n = await tick(opts.backend, opts.runDir);
      console.log(`[runner] processed ${n} pending request(s), exit`);
    } catch (err) {
      console.error("[runner-fatal] tick threw:", err.message);
      process.exit(1);
    }
    return;
  }

  if (opts.watch) {
    const queuePath = path.join(opts.runDir, "dispatch-queue.json");
    console.log(`[runner] polling ${queuePath} every ${opts.pollMs}ms (Ctrl-C to stop)`);
    while (true) {
      let n = 0;
      try {
        n = await tick(opts.backend, opts.runDir);
      } catch (err) {
        // Wrap tick error: log+continue, don't kill runner (item 2 supervisor resilience)
        console.error("[runner] tick error (continuing):", err.message);
      }
      if (n > 0) console.log(`[runner] tick processed ${n}`);
      await new Promise(r => setTimeout(r, opts.pollMs));
    }
  }

  console.error("必须指定 --once 或 --watch");
  process.exit(1);
}

main().catch(err => {
  console.error("[runner-fatal]", err);
  process.exit(1);
});
