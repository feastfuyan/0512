---
name: report-scorecard
description: "Use when the user asks to evaluate, score, grade, or rate the quality of any research report, investment memo, analysis document, or PDF/Word report. Produces a structured scorecard with numerical scores (0-10) across 10 institutional-grade dimensions, overall grade (A+ to F), and actionable improvement suggestions. Triggers: '给报告打分', '评估报告质量', 'score this report', 'grade this report', 'evaluate report quality', '报告专业度打分', '报告评分'."
version: "1.0.0"
---

# Report Scorecard — 专业报告质量评分

## 概述
对任意研究报告/投资备忘录进行10维度专业度评分，输出结构化评分卡 + 改进建议。

## 评分维度（10 个维度，每项 0-10 分）

### A. 内容质量（Content）
1. **论点清晰度 (Thesis Clarity)** — 核心论点是否明确、可证伪？读者能否一句话概括报告立场？
2. **数据支撑度 (Data Anchoring)** — 关键论断是否有数据/图表/引用支撑？数据来源是否可信？
3. **逻辑严密性 (Logical Rigor)** — 推理链条是否完整？是否存在逻辑跳跃或自相矛盾？
4. **深度与洞察 (Depth & Insight)** — 是否超越常识性描述？是否提供了非显而易见的洞察？
5. **反证与情景 (Contrarian & Scenario)** — 是否考虑了相反论据？是否有多情景分析（bull/base/bear）？

### B. 结构与表达（Structure & Expression）
6. **结构完整性 (Structural Integrity)** — 是否有清晰的引言-论证-结论结构？章节衔接是否流畅？
7. **表达精炼度 (Concision)** — 是否有冗余/重复/填充内容？信息密度是否足够？

### C. 专业规范（Professional Standards）
8. **图表质量 (Chart Quality)** — 图表是否清晰、专业、无 chartjunk？标题是否传达单一信息？
9. **引用与合规 (Citation & Compliance)** — 是否标注数据来源？是否有免责声明？PII/MNPI 是否清除？
10. **排版与格式 (Layout & Formatting)** — 字体、配色、间距是否符合专业标准？页眉页脚是否完整？

## 评分等级

| 分数 | 等级 | 含义 |
|------|------|------|
| 9.6-10.0 | A+ | 投行级，可直接发布 |
| 9.0-9.5 | A | 专业水准，微调后发布 |
| 8.0-8.9 | B+ | 良好，需要适度修改 |
| 7.0-7.9 | B | 及格，有明显不足 |
| 6.0-6.9 | C | 需大幅修改 |
| < 6.0 | F | 不合格，建议重写 |

## 工作流程

### Step 1: 读取报告
- 用户提供的 PDF / Word / Markdown / HTML 文件
- 提取文本内容、图表、表格、引用

### Step 2: 逐维度评分
对每个维度：
1. 给出 **分数** (0-10，精确到0.1)
2. 给出 **一句话评价**（好的方面）
3. 给出 **一句话改进建议**（如有不足）
4. 引用报告中的 **具体段落/图表** 作为评分依据

### Step 3: 汇总
- 计算加权总分（默认等权，用户可指定权重）
- 给出总体等级
- 列出 Top 3 优势 + Top 3 待改进项

### Step 4: 输出评分卡
生成结构化评分卡（Markdown 格式），包含：

```markdown
# 📊 报告评分卡

**报告名称：** [标题]
**报告日期：** [日期]
**评分日期：** [今天]
**总体评分：** [X.X/10] — [等级]

---

## 维度评分

| # | 维度 | 分数 | 评价 |
|---|------|------|------|
| 1 | 论点清晰度 | X.X | [一句话] |
| 2 | 数据支撑度 | X.X | [一句话] |
| ... | ... | ... | ... |
| 10 | 排版与格式 | X.X | [一句话] |

## 评分分布图
[用文字画出分数分布]

## 🏆 三大优势
1. [优势1 + 具体证据]
2. [优势2 + 具体证据]
3. [优势3 + 具体证据]

## ⚠️ 三大待改进
1. [问题1 + 改进建议]
2. [问题2 + 改进建议]
3. [问题3 + 改进建议]

## 改进优先级
- **立即修改（影响等级）：** [列出]
- **建议修改（提升专业度）：** [列出]
- **锦上添花：** [列出]

---
*评分标准基于 Goldman Sachs Global Investment Research / McKinsey 报告质量框架*
```

## 注意事项
- 评分必须基于报告实际内容，不得凭空臆断
- 引用报告原文时标注页码或章节
- 如果报告内容不足以评估某维度，标注 "N/A" 并说明原因
- 评分要公正，不因报告主题偏好而调整分数
- 对于中文报告和英文报告使用同一标准

## 与 lynai-report 配合
此评分技能可作为 lynai-report 的独立质检工具使用：
1. lynai-report 生成报告 → report-scorecard 评分 → 根据反馈修订
2. 也可用于评估外部研报质量
