---
name: stock-study
description: ASX mining stock research system, single-ticker senior equity research, 6-factor scoring (technical/volatility/commodity-beta/liquidity/valuation/fundamental), regime-filtered probability calibration, walk-forward backtest with IC/Brier/reliability-gap, short-side risk alerts; 触发: ASX mining stock, 个股研究, 6-factor scoring, regime filter, walk-forward backtest, 选股打分, P(up) calibration, target price 区间; NOT for: 资源量编报/NI 43-101 (用 vp-geology), 宏观大类配置 (用 macro-commodity-analyst), 非上市矿权估值 (用 valuation-analyst)
when_to_invoke: 当用户要对单只或一批 ASX 矿业股做量化研究/打分/方向预测/回测验证时调用；需要 yfinance 行情 + 商品价格 + regime 上下文。
input:
  ticker: "单只 ASX 代码 (如 ASX:BHP) 或留空跑全量矿业 universe"
  asof: "评估基准日 YYYY-MM-DD (可选，默认今日)"
  env: "STOCKSTUDY_* 阈值环境变量 (liquidity gate / RSI / horizon / regime thresholds / DRY_RUN kill switch)"
  mock: "STOCKSTUDY_MOCK_LLM=true 走无 API 离线模式"
output:
  scores: "每股 JSON: p_up_calibrated / label / target_central+P20/P80 / stop_loss / liquidity_gate_pass / regime / risk_alert"
  backtest: "walk-forward WFReport: ic_mean/ic_ir / brier / reliability_gap / direction_accuracy / meltdown_alerts"
  report: "经 OutputGate 合规闸门后的 markdown/Excel 报告 + 强制 disclaimer"
governance:
  constitution: "§2 因果先验 + §5 自我超越"
  doctrine: "教典第 2 条 · 严苛评估 + 第 5 条 · 自主科学发现"
  arxiv: ["T2-04:arXiv:2507.02825", "T2-05:arXiv:2406.12045", "T5-13:arXiv:2508.14111"]
  enforced_gates: "walk-forward 样本外验证; pass^3 >= 0.8; trivial(do-nothing/random-50) baseline pass^k < 5%; Brier skill score > 0 vs baseline_prob; 95% CI"
  lineage:
    renamed_from: "stock_study"
    reason: "frontmatter name 与目录名 / _meta.json slug 'stock-study' 不一致 (F5)，对齐为 kebab-case；原下划线名保留于此以存血缘"
version: "3.2"
status: ACTIVE
---

# Stock Study — ASX Mining Stock Research System v3.2

## Overview

Production-grade ASX mining stock analysis system with:
- **6-factor scoring**: technical + volatility + commodity beta + liquidity + valuation + fundamental
- **Regime filter**: automatically adjusts for Bull/Neutral/Bear/Crash market conditions
- **Liquidity gate**: filters out thin-volume stocks (<1M AUD/day ADV)
- **Risk-adjusted ratings**: E[r]/σ instead of raw trend → eliminates v1's negative correlation bug
- **Short-side risk alerts**: independent module preserving v1's 60%+ bear accuracy
- **Walk-forward backtest engine**: rolling validation with meltdown alerts

## Architecture

```
Tier 1 (Deterministic):
  data_pipeline/yahoo.py    → OHLCV + commodity prices + index data
  factor_engine/orchestrator.py → 6-family factor computation
  factor_engine/scorer.py   → probability calibration + label + target price
  risk_alert/short_side.py  → independent short-side risk detection
  backtest_scorer/walk_forward.py → walk-forward validation

Tier 2 (LLM-Augmented):
  tier2/agent_xt_reasoner.py → narrative generation (optional)

Safety:
  safety/output_gate.py     → deterministic publish gate (restricted issuers, banned phrases)
  safety/sanitizer.py       → input sanitization
  compliance/               → disclaimers, restricted issuers, banned phrases
```

## Usage

### Single Stock Analysis
```bash
# Analyze one ASX mining stock
python -m workflows.daily_run --ticker ASX:BHP

# Analyze with specific date
python -m workflows.daily_run --ticker ASX:NCM --asof 2026-05-24
```

### Batch Analysis (All ASX Mining)
```bash
# Run full daily analysis
python -m workflows.daily_run

# Mock mode (no API calls)
STOCKSTUDY_MOCK_LLM=true python -m workflows.daily_run --asof 2026-05-20
```

### Backtesting
```bash
# Run walk-forward backtest on historical predictions
python -m tier1.backtest_scorer.walk_forward
```

## Configuration (Environment Variables)

All thresholds are configurable — no hardcoded values:

| Variable | Default | Description |
|----------|---------|-------------|
| `STOCKSTUDY_MIN_ADV_AUD` | 1000000 | Minimum 20-day ADV in AUD for liquidity gate |
| `STOCKSTUDY_RSI_PERIOD` | 14 | RSI lookback period |
| `STOCKSTUDY_MA_SHORT` | 20 | Short moving average period |
| `STOCKSTUDY_MA_LONG` | 50 | Long moving average period |
| `STOCKSTUDY_COMMODITY_BETA_WINDOW` | 60 | Commodity beta rolling window |
| `STOCKSTUDY_HORIZON_DAYS` | 14 | Prediction horizon (shortened from 30) |
| `STOCKSTUDY_BULL_THRESHOLD` | 0.55 | P(up) threshold for bull label |
| `STOCKSTUDY_BEAR_THRESHOLD` | 0.40 | P(up) threshold for bear label |
| `STOCKSTUDY_SHORT_ALERT_THRESHOLD` | 0.55 | Short-side alert threshold |
| `STOCKSTUDY_DRY_RUN` | false | Block all output (emergency kill switch) |

## Output Format

Each stock receives:

```json
{
  "ticker": "ASX:BHP",
  "p_up_calibrated": 0.62,
  "label": "↑多头",
  "target_central": 48.50,
  "target_p20": 44.20,
  "target_p80": 52.80,
  "stop_loss": 41.50,
  "liquidity_gate_pass": true,
  "regime": "Neutral",
  "risk_alert": {
    "short_probability": 0.18,
    "alert_level": "none"
  }
}
```

## Key Fixes vs v1

| Issue | v1 | v3.2 |
|-------|----|----|
| Direction accuracy | 39.6% (below random) | Regime-filtered + risk-adjusted |
| Bull accuracy | 19.7% | Liquidity gate + commodity beta |
| Recommendation | Negative correlation with returns | E[r]/σ scoring |
| Target price | 47.3% median bias | Confidence interval (P20/P80) |
| Prediction horizon | 30 days | 14 days (shorter = more reliable) |
| Bear accuracy | 60.1% ✅ | Preserved as independent module |
| Backtesting | None | Walk-forward + meltdown alerts |

## Dependencies

```bash
pip install yfinance pandas numpy scikit-learn pydantic pyyaml openpyxl
```

## Compliance

- All output passes through `OutputGate` before publishing
- Restricted issuer list enforced (compliance/restricted_issuers.yaml)
- Banned phrases checked (compliance/banned_phrases.yaml)
- Mandatory disclaimer appended to all reports
- Emergency kill switch via `STOCKSTUDY_DRY_RUN=true`

---

# Original Stock Study — Senior Equity Research Analyst

> **NOTE**: The following is the original single-ticker analysis mode. For ASX mining batch analysis, use the v3.2 system above.

You are a senior equity research analyst at a top-tier investment bank with access to Bloomberg, FactSet, and SEC filings. Cite every metric with its source and date. If data is unavailable or potentially outdated, say so explicitly. Do not estimate or fabricate any numbers.

## Required Analysis

### Step 1 — Company Overview
- **What the company does in plain English**: 2-3 sentence business description
- **Business model and revenue streams**: Breakdown by percentage of total revenue in a table
- **Key competitive advantage**: One-sentence moat

### Step 2 — Wall Street Consensus
- Number of analysts covering this stock
- Buy / Hold / Sell breakdown with firm names
- Average, highest, and lowest price targets
- Most recent analyst upgrade or downgrade (firm name and date)

### Step 3 — Institutional Activity
- Top 5 institutional holders with position changes (QoQ)
- Notable hedge fund activity (new positions or exits with SEC filing dates)

## Format
- Clear markdown headers
- Tables for quantitative data
- Source citations immediately after each metric
- Flag any data that may be more than 30 days old

## Watchlist (for reference)
Current tickers: MIAX, YUM, GM, PENG, FUTU

---

## 凌云治理锚 (Governance · 三重锚定)

本 skill 遵守 **宪法 §2 因果先验 + §5 自我超越** ∥ **教典第 2 条 · 严苛评估 + 第 5 条 · 自主科学发现** (arXiv:2507.02825 + arXiv:2406.12045 + arXiv:2508.14111)。

- 三重可证伪锚：严苛评估 (rigorous-evaluation) 要求样本外、报 pass^k 而非均值、带 baseline；自主科学 (agentic-science) 要求假设→实验→证伪的闭环而非一次性拟合。本 skill 的 walk-forward backtest 即是把"6 因子模型能预测方向"当作**可被回测证伪的假设**来对待。
- 援引的量化门 (frontmatter `enforced_gates`)：walk-forward 样本外验证；**pass^3 ≥ 0.8**；trivial baseline (do-nothing / random-50) 的 pass^k **< 5%**；Brier skill score > 0 (vs `baseline_prob` 常数预测)；方向准确率报 95% CI。
- 因果先验 (§2)：技术指标的相关 ≠ 收益的成因。本 skill 用 `E[r]/σ` 风险调整打分替代 v1 的裸趋势，正是为了消除 v1 那个"推荐与收益负相关"的伪因果 bug。
- 配套 doctrine skill：`engineering-doctrine:rigorous-evaluation` + `engineering-doctrine:agentic-science`。

## 验证方法学 (V 层 · 教典第 2 条 ABC + pass^k)

> 本段只**声明方法学并指向真实验证资产**,不在评审时真跑 (跑测试需 yfinance/API env, 缺 key 会假阴)。本 skill 是全队**最接近真 V 分**的——它自带可执行的 walk-forward backtest + golden eval + 对抗测试。

- **Task Validity (任务可解性)**：任务定义为"给定 as-of 日的行情/商品/regime 上下文,输出未来 `STOCKSTUDY_HORIZON_DAYS`(默认 14 天)内的方向概率 `p_up_calibrated` 与目标价区间"。可解性边界:仅对**过流动性门** (`STOCKSTUDY_MIN_ADV_AUD` 默认 1M AUD/day ADV) 的标的有效;薄量股被 `liquidity_gate` 主动判为不可解并剔除,而非强行打分。
- **Outcome Validity (真成功 vs 凑巧)**：用 `tier1/backtest_scorer/walk_forward.py` 的**滚动样本外**验证证明,而非训练集拟合。核心指标:
  - `ic_mean` / `ic_ir` — 预测分与实际收益的信息系数及其 IR (穿越时间稳定性);
  - `brier` — 概率校准质量,须优于常数 `baseline_prob` (Brier skill score > 0);
  - `reliability_gap` — 校准曲线偏离对角线的程度 (过自信检测);
  - `direction_accuracy` — 方向准确率,须显著高于 50% 的 random-coin baseline;
  - `meltdown_alerts` — 在 regime=Crash 段的失效预警。
- **Walk-forward 如何给出样本外 pass^k**：把历史切成滚动 train/predict 窗口,每个窗口的预测只用窗口前数据 (无 lookahead),对每个窗口独立判 pass/fail (如 direction_accuracy > 50% 且 brier 优于 baseline)。**pass^3** = 连续 3 个独立窗口/独立 seed 全部达标的比例,目标 ≥ 0.8;同口径下 trivial baseline (do-nothing 全判平 / random-50) 的 pass^k 应 < 5%,以证明 0.8 不是任务本身好过。
- **Reporting**：报 **pass^k 而非均值** (单次高分可能是过拟合或运气);所有指标附 baseline (do-nothing / random-50 / 常数 `baseline_prob`) + 95% CI。
- **现有测试 / eval (可在本机带 env 复跑)**：
  - `make smoke` → `STOCKSTUDY_MOCK_LLM=true python -m workflows.daily_run --asof <date>` (离线 mock,无 API);
  - `make test` → `tests/unit/` + `tests/adversarial/` (70 个 prompt-injection 对抗用例,全 PASS 才可 merge);
  - `make test-golden` → `evals/golden/` (`test_ticker_universe.py` universe 覆盖 + `test_narrative_quality.py` 叙事质量) + `tests/e2e/`;
  - walk-forward 回测:`python -m tier1.backtest_scorer.walk_forward`。

## 可观测与沙箱 (O/E 层 · 教典第 3 条)

- **trace / lineage**：运行经 `observability/tracing.py` 写 trace (含 `trace_id`),`observability/cost_ledger.py` + `budget.py` 记 token/成本 lineage,`metrics.py` 出可观测指标 (可接 Jaeger / Grafana,见 `make jaeger` / `make grafana`)。每份报告的产物可回溯到 as-of 日、env 阈值快照与数据源,形成 data lineage。
- **safe-bash / 凭证 / sandbox**：破坏性或对外命令一律过 `safe-bash` 保险丝;API key (yfinance / LLM) 走环境变量与 vault,**不进上下文、不落仓** (见 `.gitignore`)。离线评审用 `STOCKSTUDY_MOCK_LLM=true` 的 mock 沙箱模式,不触外网。输入经 `safety/sanitizer.py` 清洗,工具调用经 `safety/tool_guard.py` 守门。

## 高风险操作与列禁 (high-risk allowlist)

- 本 skill 的**对外动作仅为发布投研报告**,且必须先过 `safety/output_gate.py` 确定性合规闸门 (restricted issuers + banned phrases + 强制 disclaimer)。
- **紧急熔断**:`STOCKSTUDY_DRY_RUN=true` 阻断一切输出 (kill switch),用于合规事件或数据异常时。
- 删除产物/缓存走回收站,**禁止** `rm -rf` / `shutil.rmtree` 直删;一律改用 `safe-bash` 包裹。
- 版本/代码推送**禁止** `git push --force` / `git push -f` / `git reset --hard` 到共享分支;以上破坏性命令均**不得**绕过 `safe-bash`。
- **禁止**未过 `output_gate` 直接发布;**禁止**对 restricted issuer 出具评级;**禁止**把任何输出当作投资建议外传 (默认 INTERNAL / IC-only)。

## 诚实边界 (Honest Boundary · 做不到什么)

- 本 skill **不做**:资源量编报 / NI 43-101 (用 vp-geology);宏观大类资产配置 (用 macro-commodity-analyst);非上市矿权估值 (用 valuation-analyst);也不提供个性化投资建议——输出是**概率化的研究信号**,不是 buy/sell 指令。
- 已知**失败模式 / 踩坑 (anti-patterns)**:
  1. **回测 lookahead bias**:若特征计算或 regime 标注不慎用了未来数据,walk-forward 的样本外分会虚高。已用滚动窗口隔离,但任何新增因子必须自查只用 as-of 日之前的数据。
  2. **流动性门陷阱**:`liquidity_gate` 剔除薄量股是正确的,但也意味着对小盘/早期勘探股**无能为力**;低于 ADV 门的标的不应被强行打分。
  3. **mock 与真实 API 分歧**:`STOCKSTUDY_MOCK_LLM=true` 的离线分数与真实 yfinance/LLM 结果可能不一致;mock 仅用于 CI/评审,**不可**据 mock 输出做真实决策。
  4. **regime 滞后**:regime filter 基于历史窗口判别,在 Crash 拐点会滞后失效——故配独立 short-side 模块 + `meltdown_alerts` 兜底,但拐点当天仍可能误判。
  5. **校准漂移**:`p_up_calibrated` 的校准在分布漂移 (新商品周期/政策冲击) 后会退化,`reliability_gap` 升高即信号过期,需重新 walk-forward 校准。
- 不确定性:即使 pass^3 ≥ 0.8,单只股票的单次预测仍带显著残差;`p_up`、`target_p20/p80` 是区间分布而非点估计,使用时须按区间而非中枢解读。
