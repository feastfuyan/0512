# Expert Panel Report 写作风格指南

本文档定义 01 号技能（expert-panel-report）的写作风格规范。

---

## 核心原则

### 1. 中英双语 (Bilingual)

**格式:**
```
中文在前，英文在后 / Chinese first, English second
```

**示例:**
```
铜价上涨 2% / Copper prices rose 2%
```

**原则:**
- 所有标题、段落、要点都必须有英文翻译
- 英文翻译必须准确，不能直译
- 专有名词使用英文名（如 LME 铜）

---

### 2. 论点先行 (Thesis-First)

**格式:**
```
**核心论点 / Key Thesis**: [论点]
```

**示例:**
```
**核心论点 / Key Thesis**: 铜价在 9,800 USD/t 获得支撑, 受益于全球制造业 PMI 回升 + 中国基建投资加速.
```

**原则:**
- 每个章节开头必须有核心论点
- 论点必须有数据支撑
- 论点必须清晰、简洁

---

### 3. 数据带来源 (Data with Citation)

**格式:**
```
[数据] [data:来源]
```

**示例:**
```
LME 铜 +2.3% w/w 至 9,180 USD/ton [data:cu]
```

**原则:**
- 所有数据必须有来源标注
- 来源格式：`[data:{矿种代码}]` 或 `[data:mci]`
- 不能编造数据

---

### 4. 专家引用 (Expert Citation)

**格式:**
```html
<div class="expert-quote">
  <div class="eq-text">"[引用内容]"</div>
  <div class="eq-author">
    <div class="eq-avatar">{姓名缩写}</div>
    <div>
      <div class="eq-name">{专家全名}</div>
      <div class="eq-role">{职称} | {机构}</div>
    </div>
  </div>
</div>
```

**示例:**
```html
<div class="expert-quote">
  <div class="eq-text">"全球制造业 PMI 回升是铜价核心驱动, 预计 Q3 铜价将突破 10,000 USD/t." / "Global manufacturing PMI recovery is the core driver for copper prices, expected to break through 10,000 USD/t in Q3."</div>
  <div class="eq-author">
    <div class="eq-avatar">王选策</div>
    <div>
      <div class="eq-name">王选策 / Wang Xuanze</div>
      <div class="eq-role">首席分析师 / Chief Analyst | 凌云智矿 / LynAI Mines</div>
    </div>
  </div>
</div>
```

**原则:**
- 每个章节至少 1 条专家引用
- 引用内容必须与章节主题相关
- 引用专家必须来自 `experts` 列表

---

### 5. 风险对称 (Risk Symmetry)

**格式:**
```
上行风险 / Upside Risk: [风险]
下行风险 / Downside Risk: [风险]
```

**示例:**
```
上行风险 / Upside Risk: 海外铜矿罢工导致供应收紧
下行风险 / Downside Risk: 中国房地产低迷超预期
```

**原则:**
- 必须同时列出上行风险和下行风险
- 风险必须有具体触发条件
- 风险必须有概率估算

---

### 6. 三类要素齐备 (Three Elements)

每个章节必须包含:

1. **文字论点** (`.thesis` 或 `<p class="key">`)
2. **量化数据** (`.data-table` 或 `.key-points`)
3. **专家引用** (`.expert-quote`)

**示例:**
```html
<div class="thesis">
  <strong>核心论点 / Key Thesis</strong>: 铜价在 9,800 USD/t 获得支撑.
</div>

<div class="key-points">
  <div><strong>当前价格 / Current Price</strong>: 9,800 USD/ton [data:cu]</div>
  <div><strong>评级 / Rating</strong>: 看多 / Bull [data:cu]</div>
</div>

<div class="expert-quote">
  <div class="eq-text">"..."</div>
</div>
```

**原则:**
- 三类要素缺一不可
- 每类要素至少 1 项
- 要素之间必须有逻辑关联

---

## 专业术语表

| 中文 | 英文 | 缩写 |
|------|------|------|
| 伦敦金属交易所 | London Metal Exchange | LME |
| 制造业采购经理人指数 | Manufacturing Purchasing Managers' Index | PMI |
| 环境社会和治理 | Environmental, Social, and Governance | ESG |
| 稀土元素 | Rare Earth Elements | REE |
| 公吨 | Metric Ton | t |
| 金衡盎司 | Troy Ounce | oz |
| 千克 | Kilogram | kg |
| 季度 | Quarter | Q |
| 周同比 | Week-over-Week | WoW |
| 月环比 | Month-over-Month | MoM |
| 年同比 | Year-over-Year | YoY |

---

## 数字格式规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 价格 | 整数，无小数 | 9,800 USD/ton |
| 百分比 | 保留 1 位小数 | +2.3% |
| 日期 | YYYY.MM.DD | 2026.07.01 |
| 时间 | HH:MM | 16:30 |
| 纯数字 | 保留 2 位小数（必要时） | 9.55 |

---

## 句式规范

### 禁止的句式

- ❌ "本周市场..."（无核心论点）
- ❌ "铜价上涨"（无数据来源）
- ❌ "我们预计"（无专家引用）
- ❌ "可能是"（无量化分析）

### 推荐的句式

- ✅ "**核心论点 / Key Thesis**: 铜价在 9,800 USD/t 获得支撑."
- ✅ "LME 铜 +2.3% w/w 至 9,180 USD/ton [data:cu]."
- ✅ "王选策: '全球制造业 PMI 回升是铜价核心驱动.'"
- ✅ "上行风险 / Upside Risk: 海外铜矿罢工导致供应收紧."

---

## 参考文档

- **assets/base_styles.html** — CSS 样式模板
- **shared/constants.json** — 常量定义
- **rubric/scoring-rubric.md** — 评分标准