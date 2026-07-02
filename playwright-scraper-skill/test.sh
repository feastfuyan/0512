#!/bin/bash
# 簡單測試腳本

set -e

# Use TMPDIR env var (falls back to /tmp on most systems)
TMPDIR="${TMPDIR:-/tmp}"
TEST_SIMPLE="$TMPDIR/test-simple-$$.json"
TEST_STEALTH="$TMPDIR/test-stealth-$$.json"
TEST_ENV="$TMPDIR/test-env-$$.json"

echo "🧪 Playwright Scraper Skill 測試"
echo ""

# 測試 1: Playwright Simple
echo "📝 測試 1: Playwright Simple (Example.com)"
node scripts/playwright-simple.js https://example.com > "$TEST_SIMPLE"
if grep -q "Example Domain" "$TEST_SIMPLE"; then
  echo "✅ Simple 模式正常"
else
  echo "❌ Simple 模式失敗"
  exit 1
fi
echo ""

# 測試 2: Playwright Stealth
echo "📝 測試 2: Playwright Stealth (Example.com)"
node scripts/playwright-stealth.js https://example.com > "$TEST_STEALTH"
if grep -q "Example Domain" "$TEST_STEALTH"; then
  echo "✅ Stealth 模式正常"
else
  echo "❌ Stealth 模式失敗"
  exit 1
fi
echo ""

# 測試 3: 環境變數
echo "📝 測試 3: 環境變數 (WAIT_TIME)"
WAIT_TIME=1000 node scripts/playwright-simple.js https://example.com > "$TEST_ENV"
if grep -q "Example Domain" "$TEST_ENV"; then
  echo "✅ 環境變數正常"
else
  echo "❌ 環境變數失敗"
  exit 1
fi
echo ""

# 清理
rm -f "$TEST_SIMPLE" "$TEST_STEALTH" "$TEST_ENV" screenshot-*.png

echo "✅ 所有測試通過！"
