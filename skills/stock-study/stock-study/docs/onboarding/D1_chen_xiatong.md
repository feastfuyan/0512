# D1 Onboarding · 陈夏童 (Chen Xiatong)

**Role**: Senior Quant Engineer · Owner of C2/C3/C4/A1
**Reports to**: 王选策 (CEO)
**Buddy this week**: 张涛 (CTO)

> 你是 v3.2 的最关键路径。Tier 1 的三个组件（C2/C3/C4）+ Tier 2 的 Agent-XT-Reasoner（A1）+ Knowledge Encoding 全部由你 owner。这份 onboarding 是你第 1 天到第 1 周的具体 checklist。

---

## 第一天清单 (Day 1)

### 09:00 – 10:00 环境就绪
- [ ] `git clone <repo>` 然后 `make setup`
- [ ] `cp .env.example .env`，从 1Password 取 `ANTHROPIC_API_KEY` 填入
- [ ] `docker compose up -d` 起 PG/Redis/Jaeger/Grafana
- [ ] `make test-adversarial` 必须 55/55 全绿
- [ ] `make smoke` 跑通（mock LLM 模式）

### 10:00 – 11:00 读架构
- [ ] 读 `docs/ARCHITECTURE.md` 全篇（重点 §1 Tier 化 / §6 RFC-A1）
- [ ] 读 `prompts/agent_xt_reasoner/v1.0.0.md` 全篇
- [ ] 读 `schemas/scores.py` / `schemas/narratives.py` / `schemas/tasks.py`
- [ ] 在 `docs/adr/0001-tier-architecture.md` 末尾签字"已读已认同"

### 11:00 – 13:00 触摸代码
- [ ] 用 `tier1/factor_engine/technical.py` 跑一遍现有 v1 因子（你以前写过）
- [ ] 跑 `python -m tier1.factor_engine.demo` 看 6 个因子族的样例输出
- [ ] 写一个 `tests/unit/test_factor_engine_smoke.py`，至少 5 个 assert（pytest 用例）

### 14:00 – 16:00 写第一个 PR
- [ ] 在 `knowledge/heuristics/red_flags.yaml` 加 5 条你最常用的 red flag（参考 `RF-001` 的格式）
- [ ] 这是你的第一个"vibe code"任务：把脑子里的隐性规则显式化
- [ ] 提 PR，标题 "knowledge: initial 5 red flags by 陈夏童"
- [ ] 请 杜慧仪 review（合规视角）

### 16:00 – 17:30 与 王选策 1:1
- [ ] 议题 1：Sprint S1/S2 你的 task 排序
- [ ] 议题 2：Knowledge Encoding E1（录音）的时间窗
- [ ] 议题 3：哪 30 只标的进 Golden Dataset（`knowledge/golden/30_tickers.yaml` 由你定）

---

## 第一周目标 (Week 1 · S1)

| 工作日 | Output | DoD |
|---|---|---|
| Mon | C1 接 data-pipeline 接口 → C2 factor-engine 6 因子族迁移完毕 | `pytest tests/unit/test_factor_engine.py` 全绿，IC ≥ 0.06 |
| Tue | C3 backtest-scorer walk-forward + Isotonic | Brier ≤ 0.22 在 5 个 golden regime 上 |
| Wed | C4 risk-alert v1 sklearn 模型迁入 + sanity test | 空头准确率 ≥ 60% |
| Thu | Knowledge E1 录音 Round 1（2h with 王选策） | `knowledge/transcripts/round1.md` 提交 |
| Fri | A1 Agent-XT-Reasoner 骨架 + `prompts/agent_xt_reasoner/v1.0.0.md` 第一稿 | `make smoke` 跑通含 narrative 输出 |

---

## 关键联系人

| 找谁 | 何时 |
|---|---|
| 罗阳 | 数据格式问题、调 `tier1/data_pipeline/*` 接口 |
| 张涛 | sklearn / pandas 性能、numerical sanity |
| 杜慧仪 | banned phrase 是否覆盖到了你 narrative 里的某种表达 |
| 付岩 | Excel 输出哪些字段、jinja2 模板 |
| 王选策 | 大方向、KE 录音、Champion 切换签字 |

## 文件入口（你最常碰的）

```
tier1/factor_engine/         ← 你主战场
tier1/backtest_scorer/       ← 你主战场
tier1/risk_alert/            ← 你主战场
tier2/agent_xt_reasoner.py   ← 你主战场
tier2/tools/xt_tools.py      ← 你主战场
prompts/agent_xt_reasoner/   ← 你主战场（写 prompt）
knowledge/heuristics/        ← 你的 IP 沉淀位
knowledge/golden/            ← 你定 Golden Dataset
schemas/factors.py           ← 改前必跟我打招呼（D3）
schemas/scores.py            ← 改前必跟我打招呼（D3）
```

## 不可妥协（再读一遍 Constitution）

- **D5 — Evals First**：每写一个 factor 必先写至少 5 个 unit test。
- **D2 — LLM 必有 RFC**：你新增任何 LLM 调用必须先写一份 RFC（参考 `docs/ARCHITECTURE.md §6 RFC-A1`）。
- **D7 — LLM 不做最终判断**：你的 Agent-XT-Reasoner 不能"决定"label，label 必须从 calibrator 的 numerical 概率落到 4 档。

## D2-D5 计划

- **D2 (Tue)**: walk-forward 框架 + Isotonic Calibrator 实现
- **D3 (Wed)**: risk-alert v1 模型迁移 + 与 v1 输出对比验证
- **D4 (Thu)**: Knowledge Encoding 录音 Round 1
- **D5 (Fri)**: Agent-XT-Reasoner v0.1 demo（mock data 跑通）

## 你应该问王选策的问题

1. 30 只标的的最终敲定（你提名单，他签字）
2. Knowledge Encoding E1 4 轮录音的时间表
3. Sprint S1 哪个 task 最优先？如果时间不够先丢哪个？
4. v1 risk-alert 模型权重是否原封不动迁过来？

---

*last updated: 2026-05-25 by Xuan-Ce*
