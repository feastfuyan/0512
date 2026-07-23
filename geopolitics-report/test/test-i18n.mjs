#!/usr/bin/env node
/**
 * test/test-i18n.mjs
 *
 * Unit tests for the i18n module (scripts/lib/i18n.mjs) and FigureSpec lang field.
 *
 * Usage:
 *   node test/test-i18n.mjs
 *
 * Exit codes:
 *   0  — all tests passed
 *   1  — one or more tests failed
 */

import { t, validateLang, DEFAULT_LANG, SUPPORTED_LANGS } from "../scripts/lib/i18n.mjs";
import { FigureSpec, FigureRenderError } from "../figures/figure_spec.mjs";
import { renderFigure } from "../figures/render_product_svg.mjs";

let passed = 0, failed = 0;
const failures = [];

function assert(cond, name, detail = "") {
  if (cond) { passed++; console.log(`  PASS  ${name}`); }
  else {
    failed++;
    const msg = `  FAIL  ${name}${detail ? " — " + detail : ""}`;
    console.error(msg); failures.push(msg);
  }
}
function section(s) { console.log(`\n── ${s} ──`); }

// ── 1. t() basic lookup ──
section("1. t() basic lookup");
assert(t("chartSourceLabel", "en") === "Source: ", "en chartSourceLabel", t("chartSourceLabel", "en"));
assert(t("chartSourceLabel", "zh") === "数据来源：", "zh chartSourceLabel", t("chartSourceLabel", "zh"));
assert(t("chartSourceLabel") === "Source: ", "default lang (en) when omitted", t("chartSourceLabel"));

// ── 2. t() unknown key throws ──
section("2. t() error handling");
try { t("nonexistent"); assert(false, "unknown key throws"); }
catch (e) { assert(/unknown key/.test(e.message), "unknown key throws", e.message); }

// unsupported lang "fr" → t() throws (fail-closed, consistent with validateLang).
// An earlier version silently fell back to en via `??`, masking typos like "eng".
try { t("chartSourceLabel", "fr"); assert(false, "fr should throw"); }
catch (e) { assert(/unsupported lang/.test(e.message), "t() throws on unsupported lang (fr)", e.message); }

// ── 3. validateLang ──
section("3. validateLang");
assert(validateLang("en") === "en", "en valid");
assert(validateLang("zh") === "zh", "zh valid");
assert(validateLang(null) === DEFAULT_LANG, "null → default en");
assert(validateLang(undefined) === DEFAULT_LANG, "undefined → default en");
try { validateLang("fr"); assert(false, "fr throws"); }
catch (e) { assert(/unsupported lang/.test(e.message), "fr throws", e.message); }

// ── 4. SUPPORTED_LANGS / DEFAULT_LANG constants ──
section("4. constants");
assert(DEFAULT_LANG === "en", "DEFAULT_LANG is en");
assert(SUPPORTED_LANGS.includes("en") && SUPPORTED_LANGS.includes("zh"), "SUPPORTED_LANGS has en+zh");
assert(SUPPORTED_LANGS.length === 2, "exactly 2 supported langs");

// ── 5. FigureSpec lang field — default ──
section("5. FigureSpec lang field");
const specEn = FigureSpec({
  render_target: "paper", chart_type: "signed-bar",
  data: [{ x: "a", label: "a", value: 1, y: 1 }],
  encoding: { x_field: "x", y_field: "y", label_field: "label", value_field: "value", unit: "%" },
  title: "Test", source_note: "Test", claim: "Test",
  paper: { dimensions: "paper-183mm" },
});
assert(specEn.lang === "en", "FigureSpec default lang = en", specEn.lang);

// ── 6. FigureSpec lang field — explicit zh ──
const specZh = FigureSpec({
  render_target: "paper", chart_type: "signed-bar",
  data: [{ x: "a", label: "a", value: 1, y: 1 }],
  encoding: { x_field: "x", y_field: "y", label_field: "label", value_field: "value", unit: "%" },
  title: "测试", source_note: "测试", claim: "测试",
  paper: { dimensions: "paper-183mm" },
  lang: "zh",
});
assert(specZh.lang === "zh", "FigureSpec explicit zh", specZh.lang);

// ── 7. FigureSpec lang — invalid throws ──
try {
  FigureSpec({
    render_target: "paper", chart_type: "signed-bar",
    data: [{ x: "a", label: "a", value: 1, y: 1 }],
    encoding: { x_field: "x", y_field: "y", label_field: "label", value_field: "value", unit: "%" },
    title: "T", source_note: "T", claim: "T",
    paper: { dimensions: "paper-183mm" },
    lang: "fr",
  });
  assert(false, "invalid lang throws");
} catch (e) {
  assert(e instanceof FigureRenderError || /unsupported lang/.test(e.message), "invalid lang throws (fr)", e.message);
}

// ── 8. renderFigure produces localized source label ──
section("8. renderFigure localized source label");
const svgEn = renderFigure(specEn);
assert(/Source: /.test(svgEn) && !/数据来源/.test(svgEn), "en SVG has 'Source: '", svgEn.match(/Source: |数据来源：/)?.[0]);

const svgZh = renderFigure(specZh);
assert(/数据来源：/.test(svgZh) && !/Source: /.test(svgZh), "zh SVG has '数据来源：'", svgZh.match(/Source: |数据来源：/)?.[0]);

// ── 9. all dict keys have both en and zh ──
section("9. dict completeness (en+zh for every key)");
const criticalKeys = [
  "chartSourceLabel", "summaryTitle", "reportHeader", "riskHeader", "riskBoxTitle",
  "disclaimerBody", "scoreTableHeader", "degradedBanner", "endOfReport",
  "defaultKeyPoints", "defaultRisks",
];
for (const key of criticalKeys) {
  const enVal = t(key, "en");
  const zhVal = t(key, "zh");
  assert(enVal !== undefined && enVal !== null, `${key} has en`);
  assert(zhVal !== undefined && zhVal !== null, `${key} has zh`);
}

// ── Summary ──
console.log(`\n${"─".repeat(50)}`);
console.log(`Tests: ${passed + failed} total, ${passed} passed, ${failed} failed`);
if (failures.length) { console.log("\nFailed:"); failures.forEach(f => console.log(f)); }
console.log(`${"─".repeat(50)}`);
process.exit(failed > 0 ? 1 : 0);
