---
name: stock_study
description: ASX/美股量化分析。触发词："分析 PLS"、"NVDA 怎么样"、"帮我看看 BHP"、"持仓分析"
---

# Stock Study v3.2 — 轻量量化投研技能

## 触发条件

用户消息包含以下模式之一时自动触发：
- `分析 <股票代码/名称>` → `分析 PLS`、`分析 BHP`
- `<股票代码> 怎么样` → `PLS 怎么样`、`NVDA 怎么样`
- `帮我看看 <股票代码>` → `帮我看看 BHP`
- `持仓分析` → 分析持仓中的标的

## 执行步骤

### 1. 确定股票代码

- **ASX 股票**：使用 `ASX:` 前缀（如 `PLS` → `ASX:PLS`）
- **美股**：直接使用 ticker（如 `NVDA` → `NVDA`，`AAPL` → `AAPL`）
- **格式转换**：ASX 代码调用 yfinance 时会自动加 `.AX` 后缀

### 2. 获取数据

通过 `stock_skill.py` 的 `analyze_ticker()` 自动完成：
1. 调用 `tier1/data_pipeline/yahoo.py` 拉取 **1 年日线** OHLCV 数据
2. 获取商品价格（金/银/铜）与 ASX 200 指数
3. 计算 20 日均成交额（ADV）
4. 识别市场 regime（Bull/Neutral/Bear/Crash）
5. 检测退市/停牌状态

### 3. 6 因子打分

通过 `tier1/factor_engine/` 计算：

| 因子 | 权重 | 说明 |
|------|------|------|
| 技术面 (technical) | 20% | 动量、RSI、均线交叉 |
| 波动率 (volatility) | 15% | 实现波动率、最大回撤、ATR |
| 商品Beta (commodity_beta) | 30% | 对金/铜的滚动 Beta |
| 流动性 (liquidity) | 10% | ADV、换手率 |
| 估值 (valuation) | 15% | 估值指标（如有基本面数据） |
| 基本面 (fundamental) | 10% | 财务指标（如有数据） |

输出：原始分 → sigmoid 归一化 → regime 调整 → 标签

### 4. LLM 解读

使用 `prompts/agent_xt_reasoner/v1.1.0.md` 的 system prompt：
- 资深 ASX 矿业分析师 persona
- 中文解读（80-150 字）
- 三段式结构：因子归因 + 市态影响 + 风险提示

### 5. 输出格式

```
📊 PLS 分析报告
━━━━━━━━━━━━━━━━━━
评分: 68/100 | 等级: A- | 信号: ↗偏多
多头概率: 58.3%
目标价(中): $3.42 | 区间: $2.98 - $4.12
止损: $2.76 | 流动性: ✓ 通过

因子归因:
  · 商品Beta(30%) — 主导正面
  · 技术面(25%) — 中性偏正
  · 波动率(15%) — 中性

市场环境: 震荡市(Neutral)
主要风险: 锂价持续承压、流动性变化

💡 PLS 评分 0.58，主要由商品Beta（30%）推动。
当前震荡市，方向不明朗，因子信号分化。
建议观察，关注商品价格与流动性变化。
```

### 6. 可选输出

如果用户说"Excel"或"报告"，调用 `tier1/excel_renderer/` 导出 5-sheet Excel 报告：
- 评分总览
- 因子明细
- 风险预警
- 回测统计
- 持仓建议

## CLI 用法

```bash
# 分析单只股票
python stock_skill.py PLS

# 分析后生成 Excel 报告
python stock_skill.py PLS --excel

# 多只批量分析
python stock_skill.py PLS BHP NCM --excel

# 通过 Makefile
make analyze TICKER=PLS
make analyze TICKER=PLS EXCEL=1
```

## Python API

```python
from stock_skill import analyze_ticker, analyze_tickers

# 单只
result = analyze_ticker("PLS")
# → dict: {ticker, score, grade, label, factors, narrative, ...}

# 多只
results = analyze_tickers(["PLS", "BHP", "NCM"])
# → list[dict]
```

## 配置 (环境变量)

参见原系统的 `SCHEDULE_*` / `STOCKSTUDY_*` 环境变量，全部可配置无硬编码。

## 数据源

- 价格数据: yfinance (Yahoo Finance)
- 商品价格: GC=F (黄金), SI=F (白银), HG=F (铜)
- 指数: ^AXJO (ASX 200)
- 缓存: 文件缓存，默认 24 小时 TTL

## 合规

- 所有输出需附加免责声明
- 不包含投资建议
- 不对未来价格做确定性预测
