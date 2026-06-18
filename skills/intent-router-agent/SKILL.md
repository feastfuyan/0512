---
name: intent-router-agent
description: |
  AI 意图路由 Agent。接收用户自然语言指令，用 LLM 分析意图后匹配到最合适的 skill。
  
  核心能力：
  1. LLM 语义理解 — 不依赖关键词，理解用户真实意图
  2. 智能路由 — 匹配到 workspace/skills 中最合适的 skill
  3. 自进化 — 记录每次路由结果，从纠错中学习，自动优化匹配
  4. 自动注册 — 自动扫描 skills 目录，发现新 skill 即更新路由表
  
  Use when: 用户发来指令需要先理解意图再决定调哪个 skill
  Voice triggers: "帮我看看该用哪个技能", "意图识别", "路由"
preamble-tier: 0
triggers:
  - intent router
  - 意图识别
  - 路由
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Python
  - Glob
  - Grep
benefits-from:
  - openclaw-intent-router
  - self-improvement
