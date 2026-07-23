#!/usr/bin/env node
/**
 * test/test-args.mjs
 *
 * Unit tests for the three behaviours introduced by PR#43 that shipped with
 * zero coverage:
 *   (a) parseFlags()      — scripts/lib/args.mjs   (the consolidated CLI parser)
 *   (b) seededShuffle()   — scripts/inject-references.mjs (deterministic shuffle)
 *   (c) manual backend    — scripts/dispatch-runner.mjs refuses --backend=manual
 *                           under --watch (unattended) mode.
 *
 * Usage:
 *   node test/test-args.mjs
 *
 * Exit codes:
 *   0 — all assertions pass
 *   1 — at least one assertion failed
 *
 * Functions are imported directly from the shipped modules (single source of
 * truth); no inlined copies.
 */

import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(__dirname, '..');

const { parseFlags } = await import(
  pathToFileURL(path.join(SKILL_ROOT, 'scripts/lib/args.mjs')).href
);
// seededShuffle from inject-references.mjs removed — 01 doesn't have that script

// ── Minimal test framework (matches test-checks.mjs / test-escape.mjs) ──
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

// ── (a) parseFlags ────────────────────────────────────────────────────────────
console.log('\n=== (a) parseFlags() ===');

test('bare --flag → true', () => {
  assert.deepEqual(parseFlags(['--watch']), { watch: true });
});

test('--key value (space form)', () => {
  assert.deepEqual(parseFlags(['--backend', 'mock']), { backend: 'mock' });
});

test('--key=value (equals form)', () => {
  assert.deepEqual(parseFlags(['--backend=mock']), { backend: 'mock' });
});

test('--key= → empty string value', () => {
  assert.deepEqual(parseFlags(['--key=']), { key: '' });
});

test('--a=b=c → value keeps everything after first "=" ', () => {
  assert.deepEqual(parseFlags(['--a=b=c']), { a: 'b=c' });
});

test('--flag followed by another --flag: both boolean (no value theft)', () => {
  assert.deepEqual(parseFlags(['--flag', '--next']), { flag: true, next: true });
});

test('leading positional token is ignored (flag-only parser)', () => {
  assert.deepEqual(parseFlags(['pos', '--x', '1']), { x: '1' });
});

test('multiple flags parse independently', () => {
  assert.deepEqual(
    parseFlags(['--backend=anthropic-api', '--watch', '--poll-ms', '500']),
    { backend: 'anthropic-api', watch: true, 'poll-ms': '500' }
  );
});

// Documented sharp edge (F4): a lone "--" has key "" and swallows the next
// non-flag token. Locked in so any future change to this behaviour is deliberate.
test('lone "--" is a degenerate empty key (documented sharp edge)', () => {
  assert.deepEqual(parseFlags(['--x', '--', 'y']), { x: true, '': 'y' });
});

// ── (b) seededShuffle — SKIPPED (inject-references.mjs removed from 01) ──────
console.log('\n=== (b) seededShuffle — SKIPPED (inject-references.mjs not in 01) ===');

// ── (c) manual backend refused under --watch (dispatch-runner.mjs) ─────────────
console.log('\n=== (c) dispatch-runner manual-backend guard ===');

test('manual + --watch exits non-zero (fail-closed for unattended)', () => {
  const runner = path.join(SKILL_ROOT, 'scripts/dispatch-runner.mjs');
  const r = spawnSync(process.execPath,
    [runner, '--backend=manual', '--watch', '--run-dir', path.join(SKILL_ROOT, 'runs', '__test_reject')],
    { encoding: 'utf8' });
  assert.notStrictEqual(r.status, 0, 'expected non-zero exit for manual+watch');
  assert.match(r.stderr, /manual backend is INTERACTIVE ONLY/i);
});

test('mock + --watch is NOT rejected by the startup guard', () => {
  // mock+watch must pass validateStartup; we kill it fast so it never polls.
  const runner = path.join(SKILL_ROOT, 'scripts/dispatch-runner.mjs');
  const r = spawnSync(process.execPath,
    [runner, '--backend=mock', '--watch', '--run-dir', path.join(SKILL_ROOT, 'runs', '__test_ok')],
    { encoding: 'utf8', timeout: 800 });
  // Either killed by timeout (still running = passed the guard) or clean exit,
  // but never the manual-only fatal message.
  assert.doesNotMatch(r.stderr || '', /manual backend is INTERACTIVE ONLY/i);
});

// ── Summary ───────────────────────────────────────────────────────────────────
console.log(`\n=== RESULT: ${passed} passed, ${failed} failed ===`);
process.exit(failed > 0 ? 1 : 0);
