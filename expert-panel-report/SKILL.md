---
name: expert-panel-report
description: '生成 MiningClaw 专家团分析报告（PDF格式，14页A4机构级版式）, 强制执行 4 subagent 团队协作 + 6 项 rubric 混合评分 (mechanical+LLM) + 9.5/10 单项门控 + 制裁检查 + 图表引擎 + i18n. 触发: 生成专家团报告, 出一份专家团分析, 做一期矿业专家团报告, 生成季度报告, 做一个Expert Panel Report; NOT for: 单页备忘, Markdown 周报, 内部 standup 摘要.'
when_to_invoke: 当用户要生成机构级专家团分析报告（PDF格式，14页A4结构）, 且要求多 agent 分工 + 9.5 单项门控 + 审计日志时调用.
input:
  report_title: 报告标题 (必需)
  report_period: 报告期, 如 "2026年Q2" (必需)
  report_date: 报告发布日期 YYYY.MM.DD (必需)
  experts: 专家团成员列表 (可选, 默认沿用6位专家)
  core_topic: 本期核心主题 (可选)
  lang: 报告语言, "en" (默认) | "zh"
  output: 目标 PDF 输出路径
governance:
  constitution: "§1 第一人称视域 ∥ §2 因果先验"
  doctrine: "教典第 1 条 · 编排器纪律 ∥ 教典第 2 条 · 严苛评估"
  enforced_gates: "6 项 rubric 单项 ≥ 9.5/10 硬门控 (enforce-gate.mjs); 4 subagent 角色分离; 混合评分 (mechanical 0.4 + LLM 0.6); 制裁检查 fail-closed; 图表分辨率/色板白名单"
runtime: nodejs
entry:
  type: node-file
  file: scripts/enforce-gate.mjs
  args_format: named
  required_args: ["--report-id", "--source", "--output"]
output:
  patterns: ["*.pdf", "audit-*.json"]
  exclude_patterns: ["input.html", "snapshot.html", "trace.html"]
metadata:
  version: "3.0.0"
  changelog: "v3.0: 对齐 02-macro-pdf-report-v3 架构 — PDF 输出 + chart engine + 混合评分 + i18n + 制裁检查 + 真实专家引用库"
---

# expert-panel-report — v3.0 机构级 PDF 报告生成

> **v3.0 升级**: 基于 02-macro-pdf-report-v3 架构, 移植了 PDF 输出 (Playwright)、图表引擎 (figures/)、混合评分 (mechanical+LLM)、i18n 系统、制裁检查、共享参数解析。保留 01 自己的 14 页专家报告结构 (MCI 指数 / 评分卡 / 专家引用 / 情景卡片)。
>
> **4 subagent**: `data-collector` → `content-writer` → `visual-designer` → `rubric-reviewer`, 6 维评分门控, 最多 3 轮, fail-closed 出带水印 PDF。

## 核心法则 (优先级最高, 不可绕过)

| # | 法则 | 违反后果 |
|---|---|---|
| L0 | **禁止臆造** — 所有数据、专家引用、市场观点必须基于真实来源. | 直接拒稿, 重做. |
| L1 | **角色与边界** — 每个 subagent 只能做自己角色定义内的事. data-collector 不写分析, content-writer 不改样式, visual-designer 不动文字, rubric-reviewer 不能直接改稿子. | 越界即作废本轮. |
| L2 | **三类要素齐备** — 每个矿种分析必须同时包含: 文字论点 + 量化数据 + 视觉元素（评分卡/价格预测）. | 缺类直接判 0 分. |
| L3 | **单项 ≥ 9.5/10 才放行** — 6 项 rubric 任一项 < 9.5 触发返工. | 最多 3 轮; 仍不过则水印放行. |
| L4 | **审计日志** — 每轮评分 + 修改 diff + reviewer comment 必须落盘到 `audit-{report-id}.json`. | 缺日志的 HTML 视为未交付. |

---

## 团队拓扑 (4 个 subagent + 1 个编排器)

```
                        ┌─────────────────────┐
                        │  SKILL.md 编排器     │  ← 你正在读
                        │  (主 Claude 担任)    │
                        └──────────┬──────────┘
                                   │ 串行调度
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
 ┌──────────────┐         ┌──────────────┐          ┌──────────────┐
 │ ①            │  data   │ ②            │  draft   │ ③            │
 │ data-        │ ─────►  │ content-     │ ────►    │ visual-      │
 │ collector    │         │ writer       │          │ designer     │
 └──────────────┘         └──────────────┘          └──────────────┘
                                   │
                                   ▼ (HTML draft + 视觉元素)
                        ┌──────────────────────┐
                        │ ④ rubric-reviewer    │
                        │ (独立, 不接触上文记忆)│
                        └──────────┬───────────┘
                                   │ scores.json
                                   ▼
                        ┌──────────────────────┐
                        │ enforce-gate.mjs     │
                        │ (单项 < 9.5 触发回退) │
                        └──────────┬───────────┘
                                   │
                  ┌────────────────┴────────────────┐
                  │ pass: build-report.mjs → 出 HTML │
                  │ fail: 回退到对应 subagent (≤3轮) │
                  └─────────────────────────────────┘
```

每个 subagent 的完整 prompt + 边界定义见:
- `agents/01-data-collector.md`
- `agents/02-content-writer.md`
- `agents/03-visual-designer.md`
- `agents/04-rubric-reviewer.md`

---

## 第一步: 收集输入信息 (编排器自己做, 不调 subagent)

确认以下信息. 缺则向用户索取, **不得自动补全**:

| 信息项 | 必需 | 示例 |
|---|---|---|
| 报告标题 | ✅ | "2026年Q2矿业市场专家团分析报告" |
| 报告期 | ✅ | "2026年Q2" |
| 报告发布日期 | ✅ | `2026.07.01` |
| 专家团成员 | ⚪ | 默认6位专家（王选策、陈毅等）或用户提供 |
| 核心主题 | ⚪ | 如"地缘政治震荡下的矿业供应链重塑" |
| 输出路径 | ⚪ | 默认 `runs/{report-id}/` 目录下 |

---

## 第二步: 执行编排 (调用 scripts/enforce-gate.mjs)

编排器不直接生成内容, 而是调用 `scripts/enforce-gate.mjs` 启动 4 个 subagent 的串行调度 + 评分门控:

```bash
node scripts/enforce-gate.mjs \
  --report-id "MCE-EXPERT-20260714-001" \
  --source "runs/MCE-EXPERT-20260714-001/source.txt" \
  --output "MCE-EXPERT-20260714-001.pdf" \
  --run-dir "runs/MCE-EXPERT-20260714-001" \
  --lang en
```

**enforce-gate.mjs 执行流程:**

1. **01-data-collector**: 收集专家信息、市场数据、政策事件 → 输出 data.json
2. **02-content-writer**: 撰写14页HTML内容（封面→执行摘要→矿种分析→展望）→ 输出 draft HTML
3. **03-visual-designer**: 生成评分卡、价格预测框、MCI指数图表等视觉元素 → 注入 HTML
4. **04-rubric-reviewer**: 独立评分（6维度）+ 提出修改建议 → 输出 scores.json
5. **enforce-gate**: 检查单项 ≥ 9.5 → 通过则 render-with-watermark.mjs 出 PDF → 不通过则回退

---

## 第三步: 门控检查 (enforce-gate.mjs)

**6 项 Rubric 评分细则（见 rubric/scoring-rubric.md）:**

| # | 维度 | 权重 | 门控 | 评分标准 |
|---|------|------|------|----------|
| 1 | 专业深度 (professional_depth) | 20% | ≥ 9.5 | 有量化分析、有情景预测、有风险评估 |
| 2 | 逻辑一致性 (logical_consistency) | 20% | ≥ 9.5 | 各章节观点不矛盾，执行摘要与详细分析一致 |
| 3 | 数据完整性 (data_integrity) | 15% | ≥ 9.5 | 所有数据齐全，无"待填"占位 |
| 4 | 结构合规性 (structure_compliance) | 15% | ≥ 9.5 | 14 页结构完整，CSS 样式统一 |
| 5 | 专家引用质量 (expert_citation_quality) | 15% | ≥ 9.5 | 每章节至少 1 条专家引用，相关性高 |
| 6 | 语言质量 (language_quality) | 10% | ≥ 9.5 | 英文流畅，专业术语准确 |

**门控逻辑:**
- 单项 < 9.5 → 触发回退到对应 subagent 修改
- 最多 3 轮；仍不过则加水印放行
- 每轮修改 + 重评都记录到 `audit-{report-id}.json`

---

## 第四步: 输出文件

**成功通过门控:**
```
{output}.pdf                                    # 最终报告 PDF
runs/{report-id}/audit-{report-id}.json        # 审计日志
```

**未通过门控（3轮后）:**
```
{output}.pdf                                    # 降级 PDF（带水印）
runs/{report-id}/audit-{report-id}.json        # 审计日志
```

---

## 审计日志格式 (audit-{report-id}.json)

```json
{
  "report_id": "MCE-EXPERT-20260714-001",
  "started_at": "2026-07-14T10:00:00Z",
  "rounds": [
    {
      "round": 1,
      "scores": {
        "data_integrity": 9.2,
        "logical_consistency": 9.8,
        "language_quality": 9.6,
        "structure_compliance": 10.0,
        "expert_citation_quality": 9.4,
        "professional_depth": 9.3
      },
      "weak_items": [
        {
          "dimension": "data_integrity",
          "score": 9.2,
          "target_agent": "01-data-collector",
          "reviewer_comment": "锂矿价格数据缺失，请补充 Q1-Q3 价格区间"
        }
      ],
      "retry": true
    },
    {
      "round": 2,
      "scores": {
        "data_integrity": 9.8,
        "logical_consistency": 9.9,
        "language_quality": 9.7,
        "structure_compliance": 10.0,
        "expert_citation_quality": 9.6,
        "professional_depth": 9.5
      },
      "weak_items": [],
      "retry": false
    }
  ],
  "final_status": "pass",
  "output_file": "MCE-EXPERT-20260714-001.pdf"
}
```

---

## 报告结构（14 页 A4）

| 页码 | 内容 | 布局 |
|------|------|------|
| P01 | 封面（Cover） | 深色全页 `.cover` |
| P02 | 免责声明与方法论 | 全宽 `.full-page` |
| P03 | 目录 + 核心要点 | 全宽 `.full-page` |
| P04 | 执行摘要 + MCI指数 | 左侧边栏 `.content-page` |
| P05 | 宏观环境 | 左侧边栏 `.content-page` |
| P06 | 矿种分析：铜 + 铁矿石 | 左侧边栏 `.content-page` |
| P07 | 矿种分析：锂 + 黄金 | 左侧边栏 `.content-page` |
| P08 | 矿种分析：镍 + 稀土 | 左侧边栏 `.content-page` |
| P09 | 区域市场分析 | 左侧边栏 `.content-page` |
| P10 | 上市公司与资本市场 | 左侧边栏 `.content-page` |
| P11 | 政策、监管与ESG | 左侧边栏 `.content-page` |
| P12 | 技术与创新 + 投资机会 | 左侧边栏 `.content-page` |
| P13 | 下季展望 + 风险日历 | 左侧边栏 `.content-page` |
| P14 | 封底（Back Cover） | 深色全页 `.back-cover` |

详见完整的 HTML 结构规范（见 assets/base_styles.html）。

---

## 依赖与安装

```bash
cd 01-expert-panel-report
npm install
```

**package.json 依赖:**
```json
{
  "name": "expert-panel-report",
  "version": "3.0.0",
  "type": "module",
  "scripts": {
    "check": "node --check scripts/enforce-gate.mjs && ...",
    "install:browser": "npx playwright install chromium"
  },
  "dependencies": {
    "playwright": "1.58.2",
    "yaml": "2.5.1"
  }
}
```

---

## 测试

```bash
# 运行所有测试
npm test

# 手动测试完整流程
node scripts/enforce-gate.mjs \
  --report-id "MCE-EXPERT-TEST-001" \
  --source "runs/MCE-EXPERT-TEST-001/source.txt" \
  --output "test-output.pdf" \
  --run-dir "runs/MCE-EXPERT-TEST-001" \
  --lang en
```

---

## 版本历史

### v3.0.0 (2026-07-14)
**升级对齐 02-macro-pdf-report-v3 架构:**
- PDF 输出 (render-with-watermark.mjs + Playwright)
- Chart engine (figures/render_product_svg.mjs, 9 chart types)
- 混合评分 (mechanical 40% + LLM 60%, enforce-gate.mjs)
- i18n (en/zh, scripts/lib/i18n.mjs)
- 制裁检查 (OFAC SDN, entity_list_check)
- 14 页机构级版式 (scorecard/forecast-box/scenario-grid/conviction-list)
- 修复: 评分表维度标签 i18n 化, CSS 重复块清理, 遗留 run.mjs/build-report.mjs 删除

### v2.0.0 (2026-06-30)
**Added:**
- 4-Agent 协作架构（data-collector / content-writer / visual-designer / rubric-reviewer）
- 6 项 rubric 评分门控（单项 ≥ 9.5/10）
- 审计日志系统（audit-{report-id}.json）
- 自动回退重试机制（最多 3 轮）

**Changed:**
- 单脚本生成 → 模块化 subagent 分工
- 无评分 → 自动评分 + 门控检查
- 无审计 → 完整审计日志记录

**Fixed:**
- 修复 14 页结构不完整问题
- 修复专家引用缺失问题

---



## Logo 使用规范

Logo 已从内联 SVG 转为 PNG 图片:

| 文件 | 用途 | 背景色 |
|---|---|---|
| `assets/logos/logo-dark-bg.png` | 封面/封底 | 白色文字 |
| `assets/logos/logo-light-bg.png` | page-bar | 深色文字 |
| `assets/logos/logo-light-bg-small.png` | sidebar | 深色文字 |

```html
<img src="assets/logos/logo-dark-bg.png" style="height:36px;width:auto" alt="MiningClaw"/>
<img src="assets/logos/logo-light-bg.png" style="height:16px;width:auto" alt="MiningClaw"/>
<img src="assets/logos/logo-light-bg-small.png" style="height:14px;width:auto" alt="MiningClaw"/>
```

## 参考文档

- **02 号技能**: `../02-macro-pdf-report-v3/` （宏观经济报告，架构参考）
- **评分标准**: `rubric/scoring-rubric.md`
- **通信协议**: `shared/schema.json`
- **Mock 数据**: `examples/mock-data.json`