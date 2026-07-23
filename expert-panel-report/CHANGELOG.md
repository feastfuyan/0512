# Expert Panel Report 变更日志

本文档记录 01 号技能（expert-panel-report）的版本变更历史。

---

## [2.0.0] - 2026-06-30

### Added（新增）

**核心架构：**
- ✅ 4-Agent 协作架构（data-collector / content-writer / visual-designer / rubric-reviewer）
- ✅ 6 项 rubric 评分门控（单项 ≥ 9.5/10）
- ✅ 审计日志系统（audit-{report-id}.json）
- ✅ 自动回退重试机制（最多 3 轮）
- ✅ JSON Schema 通信协议（跨 agent 数据验证）

**目录结构：**
- ✅ `agents/` — 4 个独立 subagent 定义
- ✅ `scripts/` — 编排脚本系统（run.mjs / enforce-gate.mjs / build-report.mjs）
- ✅ `rubric/` — 评分标准与细则
- ✅ `shared/` — 共享配置（schema.json / constants.json）
- ✅ `examples/` — Mock 数据与示例
- ✅ `test/` — 测试套件
- ✅ `references/` — 专家洞察库 + 写作风格指南
- ✅ `assets/` — CSS 模板

**文档：**
- ✅ SKILL.md（与 02 号技能结构对齐）
- ✅ README.md（快速开始指南）
- ✅ CHANGELOG.md（本文档）

### Changed（变更）

**架构升级：**
- 🔄 单脚本生成 → 模块化 subagent 分工
- 🔄 无评分 → 自动评分 + 门控检查（≥ 9.5/10）
- 🔄 无审计 → 完整审计日志记录（每轮评分 + 修改历史）
- 🔄 无版本管理 → package.json + 版本号系统

**技能规范：**
- 🔄 SKILL.md 结构与 02 号技能完全对齐（YAML frontmatter）
- 🔄 核心法则从单一"禁止臆造"扩展到 5 条法则
- 🔄 输出格式从单一 HTML → HTML + 审计日志

### Fixed（修复）

**数据完整性：**
- 🐛 修复 14 页结构不完整问题
- 🐛 修复专家引用缺失问题（每章节至少 1 条）
- 🐛 修复三类要素不齐备问题（论点 + 数据 + 专家引用）

**质量管控：**
- 🐛 修复无评分门控问题（6 维度评分 ≥ 9.5）
- 🐛 修复无回退机制问题（最多 3 轮重试）
- 🐛 修复无审计日志问题（完整追踪修改历史）

### Technical Details（技术细节）

**Agent 职责：**
1. **01-data-collector** — 数据采集（专家信息、市场数据、政策事件）
2. **02-content-writer** — 内容撰写（14 页 HTML，中英双语）
3. **03-visual-designer** — 视觉设计（评分卡、图表、价格预测）
4. **04-rubric-reviewer** — 评分审核（6 维度评分 + 修改建议）

**评分维度：**
1. 数据完整性（Data Integrity）— 权重 20%
2. 逻辑一致性（Logical Consistency）— 权重 20%
3. 语言质量（Language Quality）— 权重 15%
4. 结构合规性（Structure Compliance）— 权重 15%
5. 专家引用质量（Expert Citation Quality）— 权重 15%
6. 专业深度（Professional Depth）— 权重 15%

**工作流程：**
```
data-collector → content-writer → visual-designer → rubric-reviewer
                                                    ↓
                                            enforce-gate.mjs
                                                    ↓
                                    ≥ 9.5: 通过 → build-report.mjs
                                    < 9.5: 回退（≤3轮）
```

### Dependencies（依赖）

**Node.js 依赖：**
- openclaw ^1.0.0

**无外部依赖** — 所有脚本使用 Node.js 原生模块。

### Migration Notes（迁移指南）

**从 v1.x 迁移到 v2.0：**

1. **不兼容变更：**
   - 单脚本 API 已废弃，使用 `npm start` 调用完整管线
   - 输出文件新增 `audit-{report-id}.json`

2. **新增要求：**
   - Node.js >= 18.0.0
   - 6 个矿种数据必须齐全
   - 每章节至少 1 条专家引用

3. **保留兼容：**
   - `assets/base_styles.html` 样式完全保留
   - 14 页结构不变
   - 中英双语格式不变

---

## [1.0.0] - 2026-04-07

### Added（新增）

**初始版本：**
- ✅ 单脚本生成 HTML 报告
- ✅ 14 页 A4 结构（封面 + 12 内容页 + 封底）
- ✅ CSS 模板（base_styles.html）
- ✅ 中英双语支持
- ✅ 6 个矿种分析（铜、铁矿石、锂、黄金、镍、稀土）

### Limitations（限制）

**已知问题：**
- ❌ 无评分门控
- ❌ 无审计日志
- ❌ 无回退机制
- ❌ 无测试覆盖
- ❌ 无版本管理

---

## Roadmap（路线图）

### v2.1.0（计划中）

**计划新增：**
- 📋 真实数据源集成（LME、彭博、路透）
- 📋 专家引用自动匹配
- 📋 图表自动生成（Vega-Lite）
- 📋 PDF 导出支持

### v3.0.0（远期）

**计划重构：**
- 📋 真实多 agent 并行执行
- 📋 分布式编排（支持多机器）
- 📋 实时协作编辑
- 📋 AI 辅助写作

---

## References（参考）

- **02 号技能**：`../02-macro-pdf-report-v3/`（架构参考）
- **公司仓库**：`lynaimining/LynAI-skills`
- **分支**：`feat/mc-reports-folder`

---

## Credits（致谢）

**架构设计：** 参考零二号技能（macro-pdf-report-v3）的工程化设计

**实施日期：** 2026-06-30

**实施者：** OpenClaw AI Assistant