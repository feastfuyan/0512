---
name: geopolitics-report
description: '生成 MiningClaw 地缘政治风险分析报告（PDF格式，14页A4机构级版式）, 强制执行 4 subagent 团队协作 + 6 项 rubric 混合评分 (mechanical+LLM) + 9.5/10 单项门控 + 制裁检查 + CRI 五维框架 + 图表引擎 + i18n. 触发: 生成地缘政治报告, 出一份地缘风险分析, 做一期地缘政治报告; NOT for: 宏观经济周报, 专家团报告, 单页备忘.'
when_to_invoke: 当用户要生成机构级地缘政治风险分析报告（PDF格式，14页A4结构）, 且要求多 agent 分工 + CRI 五维 + 9.5 单项门控 + 审计日志时调用.
input:
  report_title: 报告标题 (必需)
  report_period: 报告期 (必需)
  source: 数据包路径 — DB 导出 zip 或 flat JSON 目录 (必需)
  lang: 报告语言, "en" (默认) | "zh"
  output: 目标 PDF 输出路径
governance:
  constitution: "§1 第一人称视域 ∥ §2 因果先验"
  doctrine: "教典第 1 条 · 编排器纪律 ∥ 教典第 2 条 · 严苛评估"
  enforced_gates: "6 项 rubric 单项 ≥ 9.5/10 硬门控 (enforce-gate.mjs); 4 subagent 角色分离; 混合评分 (mechanical 0.4 + LLM 0.6); 制裁检查 fail-closed; CRI 五维框架"
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
  changelog: "v3.0: 对齐 01/02 架构 — PDF 输出 + chart engine + 混合评分 + i18n + 制裁检查 + CRI 五维框架 + 4 subagent + 14 页结构"
---

# MiningClaw 地缘政治风险报告技能 v3.0

生成机构级地缘政治风险分析报告（14 页 A4 PDF），包含 CRI 五维框架、P×I 风险矩阵、传染路径分析、情景预测、制裁追踪。

## 第一步: 准备数据

```bash
# 用户提供的 DB 导出数据包
source="/path/to/mc_export_*.zip"

# 或现有 flat JSON 数据目录
source="data/"
```

支持的数据表（按 report_table_mapping.yaml mc-02）:
- `geopolitical_events` — 标题/类型/严重度/区域/国家/矿种/影响分/关联股票/日期
- `ingest_news_articles` — 新闻标题/发布日期/分类/摘要
- `ingest_commodity_prices` — 商品名称/收盘价/日期
- `ingest_fx_rates` — 汇率对/汇率/日期

---

## 第二步: 执行编排 (调用 scripts/enforce-gate.mjs)

```bash
node scripts/enforce-gate.mjs \
  --report-id "MCG-GEO-20260715-001" \
  --source "runs/MCG-GEO-20260715-001/source.txt" \
  --output "MCG-GEO-20260715-001.pdf" \
  --run-dir "runs/MCG-GEO-20260715-001" \
  --lang en
```

**enforce-gate.mjs 执行流程:**

1. **01-data-collector**: 从数据包提取地缘事件、新闻、商品价格 → 输出 data.json
2. **02-content-writer**: 撰写14页HTML（CRI 五维 + P×I + 传染矩阵）→ 输出 draft HTML
3. **03-visual-designer**: 生成 FigureSpec（事件时间线/风险矩阵/商品趋势）→ 注入 HTML
4. **04-rubric-reviewer**: 独立评分（6维度）→ 输出 scores.json
5. **enforce-gate**: 检查单项 ≥ 9.5 → render-with-watermark.mjs 出 PDF

---

## 第三步: 门控检查 (6 项 Rubric)

| # | 维度 | 权重 | 门控 | 评分标准 |
|---|------|------|------|----------|
| 1 | 事件覆盖度 (event_coverage) | 20% | ≥ 9.5 | 全区域覆盖, 每章 ≥3 条事件含 src_line |
| 2 | 分析深度 (analytical_depth) | 20% | ≥ 9.5 | CRI 五维 + P×I 矩阵 + 情景分析 + 传染路径 |
| 3 | 地缘政治严谨性 (geopolitical_rigor) | 15% | ≥ 9.5 | 因果链准确, 政策/制裁引用有出处 |
| 4 | 数据完整性 (data_integrity) | 15% | ≥ 9.5 | 所有事件有 src_line, 制裁检查通过 |
| 5 | 结构合规性 (structure_compliance) | 15% | ≥ 9.5 | 14 页结构完整, CSS 样式统一 |
| 6 | 语言质量 (language_quality) | 15% | ≥ 9.5 | 英文专业流畅, 风险对称, 免责完整 |

**门控逻辑:**
- 单项 < 9.5 → 触发回退到对应 subagent 修改
- 最多 3 轮；仍不过则加水印放行 (DEGRADED)
- 每轮修改 + 重评都记录到 `audit-{report-id}.json`

---

## 14 页结构 (Reference-Aligned v3.0)

| 页 | 内容 | 布局 |
|------|------|------|
| P01 | Cover (logo + title + cover-cri CRI score block + date) | 深色全页 `.cover` |
| P02 | Key Takeaways (6 core findings + AI badge) | 全宽 `.full-page` |
| P03 | TOC + Data Sources | 全宽 `.full-page` |
| P04 | I. Global Event Overview (stat-cards + event-type chart + risk-level table) | 内容页 `.content-page` |
| P05 | II. Risk Matrix (P×I quadrant donut + P×I scatter matrix) | 内容页 `.content-page` |
| P06 | II. Top 10 Risk Events table | 内容页 `.content-page` |
| P07-P11 | III-VII. Event Deep-Dive (3-5 pages: CRI radar + P×I + contagion Sankey + commodity table + AI assessment) | 内容页 `.content-page` |
| P12 | VIII. Commodities & Mining (price table + GPR index chart + trade data) | 内容页 `.content-page` |
| P13 | IX. Strategy (AI strategy + watch events + 2×2 asset allocation grid + disclaimer) | 内容页 `.content-page` |
| P14 | Appendix: Disclaimers & Data Sources (analyst cert + COI + AI notice + data table + compliance) | 内容页 `.content-page` |
| Back | Back Cover | 深色全页 `.back-cover` |

---

## CRI 五维框架 (V2 Spec)

MiningClaw Geopolitical Country Risk Index (CRI), 满分 10 (后映射 0-100 区间供报告展示).

| 维度 | 权重 | 量表 | 核心问题 |
|------|------|------|----------|
| D1 地缘紧张度 (Geopolitical Tension) | 25% | 1-10 | How much damage to inter-state relations? |
| D2 供应冲击 (Supply Shock) | 25% | 1-10 | How much physical disruption to mineral supply chain? |
| D3 价格影响 (Price Impact) | 20% | 1-10 | Commodity price impact over next 3 months? |
| D4 政策方向 (Policy Direction) | 15% | -5 to +5 (双极 BIPOLAR) | Policy toward protectionism (-) or openness (+)? |
| D5 持续性 (Persistence) | 15% | 1-10 | How long do event effects last? |

**CRI 公式:**

```
CRI = 0.25×D1 + 0.25×D2 + 0.20×D3 + 0.15×(|D4|×2) + 0.15×D5
```

- D4 是**唯一**的双极 (bipolar) 维度 (-5 至 +5).
- 在 CRI 计算时取 `|D4|×2` 归一化到 0-10 量表, 其符号仅用于报告叙事 (方向性解读).
- D1/D2/D3/D5 均为单向 (1-10), 数值越高风险越大.

**风险等级映射:**

| CRI | 等级 | 色值 | 处置 SLA |
|------|------|------|----------|
| ≥ 7.0 | EXTREME | `#dc2626` 红 | Flash Alert + P×I 红区处置 |
| 5.0 - 6.9 | HIGH | `#f59e0b` 琥珀 | Weekly Core + 对冲评估 |
| 3.0 - 4.9 | MEDIUM | `#eab308` 黄 | Weekly Core + 应急预案 |
| < 3.0 | LOW | `#10b981` 绿 | 归档 + 常规监测 |

---



## Logo 使用规范

Logo 已从内联 SVG 转为 PNG 图片，避免变形/颜色丢失问题:

| 文件 | 用途 | 背景色 |
|---|---|---|
| `assets/logos/logo-dark-bg.png` | 封面/封底（深色背景） | 白色文字 |
| `assets/logos/logo-light-bg.png` | page-bar/sidebar（浅色背景） | 深色文字 |
| `assets/logos/logo-light-bg-small.png` | sidebar 小尺寸 | 深色文字 |

### HTML 引用方式

```html
<!-- 封面/封底 (深色背景) -->
<img src="assets/logos/logo-dark-bg.png" style="height:36px;width:auto" alt="MiningClaw"/>

<!-- 内页 page-bar (浅色背景) -->
<img src="assets/logos/logo-light-bg.png" style="height:16px;width:auto" alt="MiningClaw"/>

<!-- 内页 sidebar (浅色背景, 小尺寸) -->
<img src="assets/logos/logo-light-bg-small.png" style="height:14px;width:auto" alt="MiningClaw"/>
```

### 禁止
- 禁止内联 SVG logo（容易丢失 defs/fill）
- 禁止使用 `MiningClawd`（多了一个 d）

## CRI 评分引擎 (cri-scorer.mjs)

事件 CRI 评分由 `scripts/cri-scorer.mjs` 自动计算，**禁止 mock 或硬编码 CRI 分数**。

### 调用方式

```js
import { scoreBatch } from './scripts/cri-scorer.mjs';
const scored = scoreBatch(events);  // 返回按 CRI 降序排列的事件数组
// 每个事件附加 cri_score = { d1, d2, d3, d4, d4_normalized, d5, cri, risk_level, risk_color, action, sla, confidence }
```

### 评分规则

| 维度 | 基础分 | 加分依据 |
|---|---|---|
| D1 Tension | 2.0 | event_type(war+4/conflict+2.5/sanction+2) + war关键词(+1.5) + 描述质量(0-1.5) + 来源质量(+0.5) |
| D2 Supply | 2.0 | 高影响矿种(Li/W/Cu/REE/Oil+2) + 文本矿种(+0.8/个) + event_type(war+3/conflict+2) + 供应中断信号(+1) |
| D3 Price | 2.0 | 商品波动性(Oil 3.0/Gas 2.8/Li 2.5/Cu 2.0) + 价格信号词(+0.8/个) + event_type(war+1) |
| D4 Policy | 0.0 | sanction/export_control(-3) / tariff(-2) / trade_agreement(+3) / 保护主义/自由化关键词调整 |
| D5 Duration | 3.0+ | event_type持续期(war 9/conflict 8/sanction 7/tariff 5) + 时间跨度关键词(±1) |
| Confidence | 0.5+ | 描述长度(0-0.2) + 标题长度(0-0.05) + 来源URL(+0.1) + 高质量来源(+0.1) + 国家信息(+0.05) + 矿种(+0.05) |

### 关键约束

- **P×I 散点图 (`pi-scatter`) 必须使用全部事件**（不是仅 Top 20/30），以显示真实分布
- **散点图的 CRI 分布必须是自然聚类**（大多数 MEDIUM，少数 EXTREME/LOW），由评分引擎产生，不可手动调分
- D1 基础分 2.0（非 3.0），避免所有 security 类事件 CRI 都偏高导致分布过窄
- 置信度与 CRI 弱相关但含随机波动，不可均匀递减

---

## 图表引擎 (10 种 chart_type)

`figures/render_product_svg.mjs` + `figures/figure_spec.mjs` 支持：

### 通用图表（从 02 移植）

| chart_type | 用途 |
|---|---|
| `horizontal-bar` | 水平柱状图 |
| `multi-series-line` | 多系列折线图 |
| `grouped-bar` | 分组柱状图 |
| `signed-bar` | 正负柱状图 |

### 地缘政治专用图表

| chart_type | 尺寸 | 用途 | 输入字段 |
|---|---|---|---|
| `cri-radar` | 270×270 | CRI 五维雷达（五边形+琥珀色数据多边形） | `label`, `value` |
| `pi-scatter` | 580×270 | P×I 散点矩阵（4色分区+事件点） | `cri`, `confidence`, `label`, `color`, `size` |
| `pi-quadrant` | 270×270 | P×I 小象限（4色方块+定位点） | `encoding.dot={x,y}` |
| `contagion-sankey` | 460×150 | 商品传导 Sankey（主矿种+箭头链） | `name`, `is_primary`, `d2`, `d3`, `channel` |
| `event-bar` | 560×260 | 事件类型柱状图（百分比标签） | `label`, `value`, `color` |
| `gpr-line` | 600×160 | GPR 走势图（折线+面积填充） | `date`, `value` |

### 图表使用规则

- **cri-radar + pi-quadrant 并排显示**（Deep-Dive 页面），两个图宽度统一 270px
- **pi-scatter 使用全部事件**（覆盖全 CRI 范围，自然分布）
- **contagion-sankey 在每个 Deep-Dive 页面**的商品传导分析节
- **event-bar 在 Global Overview 页面**显示事件类型分布
- **gpr-line 在 Commodities 页面**（数据源：Caldara & Iacoviello 月度系列）

---

## Deep-Dive 页面结构（硬性要求）

每个事件深度分析页必须包含以下结构（违反则 structure_compliance 降分）：

### 侧栏（sidebar-col）

1. **CRI 公式分解** — D1-D5 五行，每行显示 `权重×分值=贡献值`，末行 TOTAL（带 teal 横线分隔）
2. **事件信息** — Type / Countries / Date / Confidence / Action

### 主栏（main-col）

1. **page-bar** — 右侧带 CRI Badge pill（大号分数 + 等级 + 颜色边框）
2. **标题** — `#N Event Title`（border-bottom 颜色按风险等级）
3. **事件元数据** — `Countries: X | Date: Y | Type: Z`
4. **摘要框** — 灰底圆角 + 左边线（颜色按风险等级）
5. **来源链接行** — publisher 颜色 pill 链接（来源名 + 截断标题 + ↗）
6. **(1) 五维雷达 + P×I 定位** — 两个 SVG 并排（cri-radar + pi-quadrant）
7. **(2) 商品传导分析** — contagion-sankey SVG + 商品影响表（HIGH/MEDIUM 徽章）
8. **AI 评估** — highlight 框（CRI 分解 + 行动建议 + src 引用）

---

## P×I 风险矩阵 (Probability × Impact)

4×4 概率 × 影响矩阵, 映射到 5 个行动等级:

| 行动等级 | 概率 (P) | 影响 (I) | 处置 SLA |
|----------|----------|----------|----------|
| CRITICAL | > 75% | > $20B | 立即 (<4h), 执行对冲, Flash Alert |
| Active Hedge | 50-75% | > $5B | 72h 内, 建立对冲头寸 |
| Attention | 25-50% | > $5B | 1 周内, 加入监测池 |
| Monitor | < 25% | (任意) | 月度复审, 常规跟踪 |
| Accept | — | — | 无特定 SLA |

- P×I 散点图必须覆盖全部已覆盖矿种的事件.
- 红区 (CRITICAL + Active Hedge) 事件须在 P06 Top 10 表中置顶并标注.

---

## V2.1 Gap 规则 (事件间语义补丁)

| Gap | 规则 | 说明 |
|------|------|------|
| Gap 1 | 多矿种评分 | 主矿种 (primary mineral) 计算 CRI, 其他矿种作为 satellite 关联展示, 不重复计 CRI |
| Gap 3 | 关联事件聚类 | 同一事件簇内出现 ≥ 2 个 Active Hedge → 整簇升级为 CRITICAL |
| Gap 5 | 风险削减事件 | CRI 可为负值 (缓解型事件); 调整后概率 `P_new = P_old × (1 - P_relief)` |

- Gap 2 / Gap 4 暂保留位, 不在 v3.0 启用.

---

## V5 强化要求 (Enhancement Requirements)

| 编号 | 要求 | 内容 |
|------|------|------|
| V5-G2 | CRI 权重敏感性 | 必须输出 3 套情景: (a) V2 baseline `25/25/20/15/15`; (b) Equal `20×5`; (c) MSCI-analog `30/30/20/10/10`. 对比同一事件在三套权重下的等级漂移 |
| V5-G3 | 数据快照截止时间表 | 报告须列出每类数据源的 cutoff UTC 时间 (events / news / prices / fx / sanctions) |
| V5-G4 | warn 三段式 | 每个 warn 必须含四字段: `field` / `reason` / `impact` / `remediation` |
| V5-G6 | 方法论附录 | 必须含 reference-set 引用集 + backtest 状态 (最近一次回测日期 / 命中率) |
| V5-G7 | AI 免责 3 条款 | (1) non-AFSL 声明; (2) AI bias 提示; (3) 须结合持牌专业意见使用 |

---

## 跨矿种传染矩阵 (Cross-Commodity Contagion Matrix)

主商品 (primary) → 卫星商品 (satellite) 传导路径, 用于 P08 Sankey 与 P06 关联列:

- **Cu** → Al, W (电力/合金链路)
- **Fe** → W, Al (钢铁合金链路)
- **Au** → (避险独立, 主要传导至汇率/REER)
- **REE** → Li, W (高端制造/磁材链路)
- **Li** → Al, Cu (电池/导电链路)
- **W** → Fe, REE (硬质合金链路)
- **Al** → Cu (电解/电力链路)

- 传导强度按事件 CRI × 关联系数 (0-1) 计算, 仅显示 ≥ 0.4 的边.
- Sankey 图边宽 ∝ 传导强度.

---

## 覆盖矿种词表 (Covered Minerals Vocabulary)

报告统一使用以下缩写, 中英文混排时首次出现须给出全称:

| 缩写 | 中文 | English |
|------|------|---------|
| Cu | 铜 | Copper |
| Fe | 铁矿石 | Iron Ore |
| Au | 黄金 | Gold |
| Al | 铝 | Aluminum |
| W | 钨 | Tungsten |
| Li | 锂 | Lithium |
| REE | 稀土 | Rare Earth Elements |

- 默认覆盖集合: `{Cu, Fe, Au, Al, W, Li, REE}`.
- 不在词表内的矿种须在附录注明 "out-of-scope" 并说明排除原因.

---

## Pre-Output Self-Check (出稿前自检清单)

输出 PDF 前必过 (condensed):

- [ ] 每个事件含 `src_line` (DB 行号或 URL)
- [ ] CRI 五维齐全, D4 双极性正确, 公式复算无误
- [ ] **CRI 分数由 cri-scorer.mjs 计算, 禁止 mock/硬编码**
- [ ] **P×I 散点图 (pi-scatter) 使用全部事件, 非仅 Top 20**
- [ ] P×I 矩阵 ≥ CRITICAL 事件已在 P06 置顶
- [ ] **Deep-Dive 页面含: CRI公式分解侧栏 + 来源链接行 + 雷达+象限并排 + 商品传导Sankey + AI评估框**
- [ ] **cri-radar 与 pi-quadrant 宽度统一 (270px)**
- [ ] Gap 1/3/5 规则已应用 (多矿种 / 聚类 / 缓解)
- [ ] V5-G2 三套权重情景均已输出
- [ ] V5-G3 cutoff 时间表完整
- [ ] V5-G4 warn 四字段齐全
- [ ] V5-G6 方法论附录含 reference-set + backtest
- [ ] V5-G7 AI 免责 3 条款在 P13 + P14 均出现
- [ ] 传染 Sankey 仅含传导强度 ≥ 0.4 的边
- [ ] 制裁检查 (OFAC SDN) 通过, fail-closed
- [ ] 6 项 rubric 单项均 ≥ 9.5
- [ ] 14 页结构 / CSS 样式 / i18n 一致
- [ ] **模板使用 min-height:297mm (非 height), 品牌名 MiningClaw (非 MiningClawd)**

---

## 输出文件

```
{output}.pdf                                    # 最终报告 PDF
runs/{report-id}/audit-{report-id}.json        # 审计日志
```

---

## 依赖

```bash
cd 03-geopolitics-report
npm install
npx playwright install chromium
```

---

## 测试

```bash
npm run check          # 语法检查
npm run test:args      # 参数解析
npm run test:i18n      # 国际化
npm run test:figures   # 图表引擎
npm run test:escape    # XSS 防护
```

---

## 版本历史

### v3.0.0 (2026-07-15)
**升级对齐 01/02 v3.0 架构:**
- PDF 输出 (render-with-watermark.mjs + Playwright)
- Chart engine (figures/render_product_svg.mjs)
- 混合评分 (mechanical 40% + LLM 60%)
- i18n (en/zh)
- 制裁检查 (OFAC SDN)
- 4 subagent 架构 (data-collector/content-writer/visual-designer/rubric-reviewer)
- CRI 五维框架保留
- 14 页机构级版式

### v1.2.0 (2026-07-08)
- V2.1 补充: 传染矩阵 + Gap 规则
- 单 agent HTML+PDF 生成

---

## 参考文档

- **01 号技能**: `../01-expert-panel-report/` （专家团报告，架构参考）
- **02 号技能**: `../02-macro-pdf-report-v3/` （宏观经济报告，架构参考）
- **评分标准**: `rubric/institutional-rubric.yaml`
- **通信协议**: `shared/schema.json`
