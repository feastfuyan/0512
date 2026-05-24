#!/usr/bin/env node

const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { GitWeeklyReporter } = require('./git-weekly');
const { WorkReportGenerator } = require('./work-report');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✅ ${name}`);
    passed++;
  } catch (err) {
    console.log(`  ❌ ${name}: ${err.message}`);
    failed++;
  }
}

console.log('🧪 Testing GitWeeklyReporter...\n');

test('default output path uses homedir, not hardcoded', () => {
  const reporter = new GitWeeklyReporter({ repo: process.cwd() });
  assert.ok(reporter.outputPath.includes(os.homedir()), 'Should use os.homedir()');
  assert.ok(reporter.outputPath.includes('MC周报'), 'Should contain MC周报');
  // Verify it's dynamic, not a literal string
  assert.strictEqual(reporter.mcReportDir, path.join(os.homedir(), 'Desktop', 'MC周报'));
});

test('mcReportDir uses env var when set', () => {
  process.env.MC_REPORT_DIR = '/tmp/test-mc';
  const reporter = new GitWeeklyReporter({ repo: process.cwd() });
  assert.strictEqual(reporter.mcReportDir, '/tmp/test-mc');
  delete process.env.MC_REPORT_DIR;
});

test('custom output path overrides default', () => {
  const reporter = new GitWeeklyReporter({ repo: process.cwd(), output: '/tmp/custom.md' });
  assert.strictEqual(reporter.outputPath, '/tmp/custom.md');
});

test('calculateSince returns date string', () => {
  const reporter = new GitWeeklyReporter({ repo: process.cwd(), days: 7 });
  const since = reporter.since;
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(since), 'Should be YYYY-MM-DD format');
});

test('categorizeCommits works', () => {
  const reporter = new GitWeeklyReporter({ repo: process.cwd() });
  const commits = [
    { message: 'feat: add login' },
    { message: 'fix: crash on startup' },
    { message: 'docs: update readme' },
    { message: 'refactor: clean up utils' },
    { message: 'chore: update deps' },
  ];
  const cats = reporter.categorizeCommits(commits);
  assert.strictEqual(cats['功能开发'].length, 1);
  assert.strictEqual(cats['问题修复'].length, 1);
  assert.strictEqual(cats['文档更新'].length, 1);
  assert.strictEqual(cats['代码优化'].length, 1);
  assert.strictEqual(cats['其他'].length, 1);
});

console.log('\n🧪 Testing WorkReportGenerator...\n');

test('default output path uses homedir', () => {
  const gen = new WorkReportGenerator();
  assert.ok(gen.output.includes(os.homedir()), 'Should use os.homedir()');
  assert.strictEqual(gen.mcReportDir, path.join(os.homedir(), 'Desktop', 'MC周报'));
});

test('mcReportDir uses env var when set', () => {
  process.env.MC_REPORT_DIR = '/tmp/test-mc2';
  const gen = new WorkReportGenerator();
  assert.strictEqual(gen.mcReportDir, '/tmp/test-mc2');
  delete process.env.MC_REPORT_DIR;
});

test('generateFromTemplate produces valid markdown', () => {
  const gen = new WorkReportGenerator();
  const report = gen.generateFromTemplate();
  assert.ok(report.includes('# 工作周报'), 'Should have title');
  assert.ok(report.includes('本周工作总结'), 'Should have work summary');
  assert.ok(report.includes('下周工作计划'), 'Should have next week plan');
});

test('getWeekNumber returns positive integer', () => {
  const gen = new WorkReportGenerator();
  const week = gen.getWeekNumber();
  assert.ok(Number.isInteger(week) && week > 0 && week <= 53);
});

// --- Integration test: generate actual report ---
console.log('\n🧪 Integration test...\n');

test('generateReport with current repo', async () => {
  const reporter = new GitWeeklyReporter({ repo: process.cwd(), days: 7, output: '/tmp/test-weekly.md' });
  const report = await reporter.generateReport();
  assert.ok(report.length > 100, 'Report should have content');
  assert.ok(fs.existsSync('/tmp/test-weekly.md'), 'Output file should exist');
  fs.unlinkSync('/tmp/test-weekly.md');
});

// Wait for async test
setTimeout(() => {
  console.log(`\n📊 Results: ${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}, 5000);
