#!/usr/bin/env node
/**
 * build_docx.js — thin orchestration wrapper around docx_producer.js (v1.2)
 *
 * v1.2 changes:
 *   - Renders .pdf via LibreOffice headless AS PART of the build (not validator-only)
 *   - Both <slug>.docx AND <slug>.pdf are placed in outputs_dir before this script exits
 *   - producer_log.json now carries `pdf_path` and `pdf_size_bytes` fields
 *
 * v1.1 changes (preserved):
 *   - Paths read from templates/runtime_paths.json (env-overridable)
 *   - MANDATORY pre-flight gate_token + redaction_report verification
 *   - Self-lint pass on the produced .docx
 *
 * Usage:
 *   node build_docx.js \
 *     --workdir /tmp/lynai_pls \
 *     --slug LYNAI_PILBARA_MINERALS_20260514_v3 \
 *     --token gate_token_v3.json \
 *     --redaction redaction_report.json
 *
 * Expects workdir to contain:
 *   draft_final.md         (the approved + possibly sanitized draft)
 *   charts/                (PNG files from Chart-Smith)
 *   tables.json
 *   report_meta.json
 *   gate_token_v{n}.json
 *   redaction_report.json
 *
 * Writes (v1.2):
 *   ${LYNAI_OUTPUTS_DIR}/<slug>.docx     ← authoritative source
 *   ${LYNAI_OUTPUTS_DIR}/<slug>.pdf      ← LibreOffice render of the same .docx
 *   <workdir>/producer_log.json          ← producer audit log
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execSync } = require("child_process");

// ----- runtime paths -----

const HERE = __dirname;
const RUNTIME_PATHS_FILE = path.resolve(HERE, "../templates/runtime_paths.json");
if (!fs.existsSync(RUNTIME_PATHS_FILE)) {
  console.error(`FATAL: ${RUNTIME_PATHS_FILE} missing`);
  process.exit(3);
}
const RUNTIME = JSON.parse(fs.readFileSync(RUNTIME_PATHS_FILE, "utf-8"));

function resolvePath(key) {
  const entry = RUNTIME.paths[key];
  if (!entry) throw new Error(`Unknown runtime path key: ${key}`);
  return process.env[entry.env] || entry.default;
}

const OUTPUTS_DIR = resolvePath("outputs_dir");
const DOCX_SKILL_ROOT = resolvePath("docx_skill_root");
const TEMPLATE = path.resolve(HERE, "../templates/docx_producer.js");

const GK_SECRET = process.env.GK_TOKEN_SECRET || "";
if (GK_SECRET.length < 32) {
  console.error("FATAL: GK_TOKEN_SECRET env var must be 32+ chars. See docs/06_GATE_CONTRACT.md.");
  process.exit(3);
}

// ----- arg parsing -----

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace(/^--/, "");
    opts[key] = args[i + 1];
  }
  return opts;
}

const opts = parseArgs();
for (const r of ["workdir", "slug", "token", "redaction"]) {
  if (!opts[r]) {
    console.error(`Missing required arg --${r}`);
    console.error("Usage: node build_docx.js --workdir <dir> --slug <slug> --token <path> --redaction <path>");
    process.exit(1);
  }
}

const workdir    = path.resolve(opts.workdir);
const slug       = opts.slug;
const draftPath  = path.join(workdir, "draft_final.md");
const chartsDir  = path.join(workdir, "charts");
const tablesPath = path.join(workdir, "tables.json");
const metaPath   = path.join(workdir, "report_meta.json");
const tokenPath  = path.resolve(opts.token);
const redactPath = path.resolve(opts.redaction);
const outPath    = path.join(OUTPUTS_DIR, `${slug}.docx`);
const pdfPath    = path.join(OUTPUTS_DIR, `${slug}.pdf`);
const logPath    = path.join(workdir, "producer_log.json");

const log = {
  version: "1.2",
  slug,
  timestamp: new Date().toISOString(),
  workdir,
  outputs: { docx: outPath, pdf: pdfPath },
  output: outPath,                    // legacy field kept for v1.1 readers
  preflight: {},
  self_lint: {},
  pdf_render: {},
  errors: [],
};

// ----- hash helpers -----

function sha256File(p) {
  const h = crypto.createHash("sha256");
  h.update(fs.readFileSync(p));
  return "sha256:" + h.digest("hex");
}

function hmacSign(token_id, draft_hash, decision, secret) {
  const msg = `${token_id}||${draft_hash}||${decision}`;
  return "GK1." + crypto.createHmac("sha256", secret).update(msg).digest("hex");
}

// ----- naming check -----

function checkSlug() {
  if (!/^LYNAI_[A-Z0-9_]+_[0-9]{8}_v[0-9]+$/.test(slug)) {
    throw new Error(`INVALID_SLUG: ${slug} does not match locked naming pattern (docs/00_DECISIONS.md §D-8)`);
  }
  log.preflight.slug = "ok";
}

// ----- gate token verification (P10 §0) -----

function verifyGateToken() {
  if (!fs.existsSync(tokenPath)) throw new Error("INVALID_TOKEN_SCHEMA: token file missing");
  const token = JSON.parse(fs.readFileSync(tokenPath, "utf-8"));

  // Rule echo
  const rule = token.rule_applied || {};
  if (rule.operator !== ">" || rule.threshold !== 9.5 || rule.scope !== "every_dimension") {
    throw new Error("RULE_MISMATCH: gate_token rule_applied does not match locked constants");
  }

  // Hash rebind
  const liveHash = sha256File(draftPath);
  if (liveHash !== token.draft_content_hash) {
    throw new Error(`HASH_MISMATCH: live draft hash ${liveHash} != token ${token.draft_content_hash}`);
  }

  // Signature
  const expected = hmacSign(token.token_id, token.draft_content_hash, token.decision, GK_SECRET);
  if (expected !== token.signature) {
    throw new Error("SIGNATURE_INVALID: gate_token signature does not recompute");
  }

  // Decision authorizes build?
  if (!["PASS", "DELIVER_WITH_SHORTFALL"].includes(token.decision)) {
    throw new Error(`DECISION_NOT_AUTHORIZING_BUILD: decision = ${token.decision}`);
  }
  if (token.decision === "DELIVER_WITH_SHORTFALL" && !token.shortfall_note) {
    throw new Error("SHORTFALL_NOTE_MISSING");
  }

  log.preflight.gate_token = {
    token_id: token.token_id,
    decision: token.decision,
    rule: rule,
    verified: true,
  };
  return token;
}

// ----- redaction report verification (P10 §0 check 6-7) -----

function verifyRedactionReport(tokenDraftHash) {
  if (!fs.existsSync(redactPath)) throw new Error("INVALID_REDACTION_SCHEMA: redaction_report file missing");
  const rep = JSON.parse(fs.readFileSync(redactPath, "utf-8"));

  if (!["CLEAR", "REDACTED"].includes(rep.overall_verdict)) {
    throw new Error(`REDACTION_BLOCKED: overall_verdict = ${rep.overall_verdict}`);
  }
  if (rep.overall_verdict === "REDACTED") {
    // The live draft we're building must be the sanitized version
    const liveHash = sha256File(draftPath);
    if (liveHash !== rep.sanitized_draft_hash) {
      throw new Error("SANITIZED_HASH_MISMATCH: live draft is not the sanitized version");
    }
    if (liveHash !== tokenDraftHash) {
      throw new Error("CHAIN_DESYNC: gate_token hash does not match live (sanitized) draft hash");
    }
  }

  log.preflight.redaction_report = {
    verdict: rep.overall_verdict,
    findings_count: (rep.findings || []).length,
    verified: true,
  };
}

// ----- physical pre-flight checks (v1.0 carry-over) -----

function preflightFiles() {
  if (!fs.existsSync(OUTPUTS_DIR)) fs.mkdirSync(OUTPUTS_DIR, { recursive: true });
  log.preflight.outputs_dir = OUTPUTS_DIR;

  for (const [name, p] of [
    ["draft_final.md", draftPath],
    ["report_meta.json", metaPath],
    ["charts/", chartsDir],
  ]) {
    if (!fs.existsSync(p)) throw new Error(`Missing required input: ${name} (${p})`);
  }
  log.preflight.required_inputs = "ok";

  log.preflight.tables_json = fs.existsSync(tablesPath) ? "present" : "absent (OK)";

  // Chart sanity
  const charts = fs.readdirSync(chartsDir).filter(f => f.endsWith(".png"));
  if (charts.length === 0) {
    log.preflight.charts = "warning: no PNGs found in charts/";
  } else {
    const bad = [];
    const seen = new Set();
    for (const f of charts) {
      const full = path.join(chartsDir, f);
      const stat = fs.statSync(full);
      if (stat.size < 1024) bad.push(`${f} too small (${stat.size}B)`);
      if (stat.size > 10 * 1024 * 1024) bad.push(`${f} too large (${stat.size}B)`);
      const lc = f.toLowerCase();
      if (seen.has(lc)) bad.push(`${f} duplicate (case-insensitive)`);
      seen.add(lc);
    }
    log.preflight.charts = bad.length === 0 ? `ok (${charts.length} files)` : `issues: ${bad.join("; ")}`;
    if (bad.length > 0) throw new Error(`Chart pre-flight failed: ${bad.join("; ")}`);
  }

  // npm module pins
  try { require.resolve("docx"); log.preflight.docx_module = "ok"; }
  catch (e) { throw new Error("docx-js not installed. Run: npm install -g docx@^8.5.0"); }

  try { require.resolve("image-size"); log.preflight.image_size_module = "ok"; }
  catch (e) { throw new Error("image-size@1.0.2 not installed. Run: npm install -g image-size@1.0.2"); }

  if (!fs.existsSync(TEMPLATE)) throw new Error(`docx_producer.js template missing at ${TEMPLATE}`);
  log.preflight.template = "ok";
}

// ----- self-lint pass on output (P10 step 3) -----

function selfLint(outFile) {
  const AdmZip = (() => {
    try { return require("adm-zip"); }
    catch (e) {
      // Fallback to no-op self-lint if adm-zip not available; warn but don't abort
      console.warn("[warn] adm-zip not installed — self-lint skipped (install with: npm install -g adm-zip)");
      return null;
    }
  })();

  if (!AdmZip) {
    log.self_lint = { skipped: true, reason: "adm-zip unavailable" };
    return;
  }

  const zip = new AdmZip(outFile);
  const docXml = zip.getEntry("word/document.xml");
  if (!docXml) throw new Error("SELF_LINT_FAILED: word/document.xml missing");

  const xml = docXml.getData().toString("utf-8");
  const findings = [];

  if (/<w:shd[^>]*w:val="solid"/i.test(xml)) findings.push("ShadingType.SOLID detected (must be CLEAR)");
  if (/<w:rFonts[^>]*w:ascii="Calibri"/i.test(xml)) findings.push("Calibri font detected (must be Georgia)");

  // PageBreak outside <w:r>
  const breakRe = /<w:br\s+w:type="page"\s*\/?>/g;
  let m;
  while ((m = breakRe.exec(xml)) !== null) {
    const before = xml.slice(Math.max(0, m.index - 200), m.index);
    if (!/<w:r[^>]*>[^<]*$/.test(before)) {
      findings.push(`PageBreak outside <w:r> at offset ${m.index}`);
      break;
    }
  }

  // Image extent range
  const extents = xml.matchAll(/<wp:extent\s+cx="(\d+)"\s+cy="(\d+)"/g);
  for (const e of extents) {
    const cx = parseInt(e[1], 10);
    if (cx < 1000000 || cx > 10000000) {
      findings.push(`image cx ${cx} EMU out of range [1e6, 1e7]`);
    }
  }

  if (findings.length > 0) {
    log.self_lint = { passed: false, findings };
    throw new Error(`SELF_LINT_FAILED: ${findings.join("; ")}`);
  }
  log.self_lint = { passed: true, checks: 4 };
}

// ----- PDF render via LibreOffice headless (D-11) -----

function renderPdf(docxFinalPath) {
  // Resolve soffice.py from the public docx skill
  const sofficePy = path.join(DOCX_SKILL_ROOT, "scripts", "office", "soffice.py");
  if (!fs.existsSync(sofficePy)) {
    throw new Error(
      `PDF_RENDER_PRECONDITION: soffice.py not found at ${sofficePy}. ` +
      `Ensure DOCX_SKILL_ROOT points to a valid public docx skill install.`
    );
  }

  // Single shot: docx → pdf, output directly to outputs_dir (no temp shuffle)
  const cmd = `python "${sofficePy}" --headless --convert-to pdf "${docxFinalPath}" --outdir "${OUTPUTS_DIR}"`;
  log.pdf_render.cmd = cmd;
  try {
    const out = execSync(cmd, { encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] });
    log.pdf_render.stdout = (out || "").trim().slice(0, 500);
  } catch (err) {
    log.pdf_render.error = err.message.slice(0, 500);
    throw new Error(`PDF_RENDER_FAILED: ${err.message.split("\n")[0]}`);
  }

  if (!fs.existsSync(pdfPath)) {
    throw new Error(`PDF_RENDER_FAILED: expected ${pdfPath} not created`);
  }
  const pdfStat = fs.statSync(pdfPath);
  if (pdfStat.size < 5 * 1024) {
    throw new Error(`PDF_RENDER_FAILED: ${pdfPath} is only ${pdfStat.size} bytes (need ≥ 5 KB)`);
  }
  log.pdf_render.size_bytes = pdfStat.size;
  log.pdf_render.path = pdfPath;
  log.pdf_render.success = true;
}

// ----- run the producer -----

async function build() {
  checkSlug();
  preflightFiles();
  const token = verifyGateToken();
  verifyRedactionReport(token.draft_content_hash);

  const { buildDocument } = require(TEMPLATE);
  const finalPath = await buildDocument({
    contentPath: draftPath,
    chartsDir,
    tablesPath,
    metaPath,
    outPath,
    shortfallNote: token.decision === "DELIVER_WITH_SHORTFALL" ? token.shortfall_note : null,
  });

  const stat = fs.statSync(finalPath);
  log.size_bytes = stat.size;

  selfLint(finalPath);

  // v1.2: render PDF as part of the build (D-11)
  renderPdf(finalPath);

  log.success = true;
  return finalPath;
}

build()
  .then(p => {
    fs.writeFileSync(logPath, JSON.stringify(log, null, 2));
    console.log(`[ok] docx produced ${p} (${log.size_bytes} bytes)`);
    console.log(`[ok] pdf  produced ${pdfPath} (${log.pdf_render.size_bytes} bytes)`);
    console.log(`[ok] log written to ${logPath}`);
  })
  .catch(err => {
    log.success = false;
    log.errors.push(err.message);
    try { fs.writeFileSync(logPath, JSON.stringify(log, null, 2)); } catch (_) {}
    console.error(`[fatal] ${err.message}`);
    process.exit(2);
  });
