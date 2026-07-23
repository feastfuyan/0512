# Expert Panel Report v2.0

> 本目录是 01 号技能完整版, 参考零二号技能（macro-pdf-report-v3）的架构重构.
>
> **范式跃迁**: v1 是单脚本生成 HTML 报告; v2 是 4 个独立 subagent + 6 项 rubric + 9.5/10 硬门控 + 工程闭环.

---

## 完整目录

```
01-expert-panel-report/
├── SKILL.md                              主编排器 (编排器文档)
├── README.md                             ← 你在这
├── package.json                          版本管理
├── assets/                               CSS 模板 + HTML 蓝本
│   └── base_styles.html                  MiningClaw 专家团报告样式
├── agents/                               4 个 subagent 角色定义
│   ├── 01-data-collector.md              数据采集（专家信息、市场数据、政策事件）
│   ├── 02-content-writer.md              内容撰写（14 页 HTML）
│   ├── 03-visual-designer.md             视觉设计（评分卡、图表、价格预测）
│   └── 04-rubric-reviewer.md             评分审核（6 维度评分）
├── rubric/
│   └── scoring-rubric.md                 6 项 rubric 评分细则
├── scripts/
│   ├── run.mjs                           主编排脚本
│   ├── enforce-gate.mjs                  门控强制器
│   └── build-report.mjs                  HTML 构建
├── shared/
│   ├── schema.json                       跨 agent 通信协议
│   └── constants.json                    常量定义（矿种、权重等）
├── references/                           专家洞察库 + 写作风格指南
├── examples/                             Mock 数据 + 示例
│   ├── mock-data.json
│   ├── mock-content.html
│   └── mock-scores.json
└── test/                                 测试套件
    ├── test-data-collector.mjs
    ├── test-content-writer.mjs
    └── test-rubric-reviewer.mjs
```

---

## 快速开始

### 运行完整流程

```powershell
# 装依赖
npm install

# 跑完整流程
npm start -- \
  --report-id "MCE-EXPERT-20260714-001" \
  --report-title "2026年Q2矿业市场专家团分析报告" \
  --report-period "2026年Q2" \
  --report-date "2026-07-01" \
  --output "output/MiningClaw_ExpertPanel_Report_2026Q2_V1.html"
```

### 跑测试

```powershell
npm test
```

---

## 4-Agent 工作流

```
data-collector → content-writer → visual-designer → rubric-reviewer
                                    │
                                    ▼ (门控检查)
                              enforce-gate.mjs
                                    │
                              ≥ 9.5: 通过 → build-report.mjs → 输出 HTML
                              < 9.5: 回退到对应 subagent（最多 3 轮）
```

---

## 评分门控

**6 项 Rubric（单项 ≥ 9.5/10 才放行）:**

| # | 维度 | 权重 | 评分标准 |
|---|------|------|----------|
| 1 | 数据完整性 | 20% | 所有矿种数据齐全，无"待填"占位 |
| 2 | 逻辑一致性 | 20% | 各章节观点不矛盾，执行摘要与详细分析一致 |
| 3 | 语言质量 | 15% | 中英双语流畅，专业术语准确 |
| 4 | 结构合规性 | 15% | 14 页结构完整，CSS 样式统一 |
| 5 | 专家引用质量 | 15% | 每章节至少 1 条专家引用，相关性高 |
| 6 | 专业深度 | 15% | 有量化分析、有情景预测、有风险评估 |

**门控逻辑:**
- 单项 < 9.5 → 自动回退到对应 subagent 修改
- 最多 3 轮；仍不过则加水印放行
- 每轮修改 + 重评都记录到 `audit-{report-id}.json`

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

## 输出文件

**成功通过门控:**
```
output/MiningClaw_ExpertPanel_Report_{period}_V1.html  # 最终报告
output/audit-{report-id}.json                           # 审计日志
```

**未通过门控（3轮后）:**
```
output/MiningClaw_ExpertPanel_Report_{period}_V1_DRAFT.html  # 草稿（带水印）
output/audit-{report-id}.json                              # 审计日志
```

---

## 审计日志格式

审计日志记录每轮评分 + 修改 diff + reviewer comment，示例见 `examples/audit-sample.json`。

---

## 版本历史

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

---

## 参考文档

- **02 号技能**: `../02-macro-pdf-report-v3/` （宏观经济报告，架构参考）
- **评分标准**: `rubric/scoring-rubric.md`
- **通信协议**: `shared/schema.json`
- **CSS 模板**: `assets/base_styles.html`