# D1 Onboarding · 罗阳 (Luo Yang)

**Role**: ML / Data Pipeline Engineer · Owner of C1 (data-pipeline)
**Reports to**: 王选策 (CEO)
**Buddy this week**: 陈夏童

> 你是上游数据的唯一负责人。C1 跑红了，下游所有组件直接饿死。SLO 是 99.5%。

---

## 第一天清单

### 09:00 – 10:00 环境就绪
- [ ] `git clone <repo>` 然后 `make setup`
- [ ] `cp .env.example .env`，填入 `ANTHROPIC_API_KEY` / `LBMA_API_KEY` / `LME_API_KEY`
- [ ] `docker compose up -d`
- [ ] `make test-adversarial` 必须 55/55 全绿（即使你不直接碰 safety，也要确认环境健康）
- [ ] `make smoke` 跑通

### 10:00 – 11:00 读架构
- [ ] 读 `docs/ARCHITECTURE.md` §1 + §8（SLO）
- [ ] 读 `schemas/data.py`（你产出的契约）
- [ ] 读 `tier1/data_pipeline/orchestrator.py` 的现有骨架（你接手填代码）
- [ ] 在 `docs/adr/0001-tier-architecture.md` 末尾签"已读已认同"

### 11:00 – 13:00 触摸代码
- [ ] 跑 `python -m tier1.data_pipeline.yahoo` 看 yfinance 现状
- [ ] 跑 `python -m tier1.data_pipeline.lbma`（如果有 API key）
- [ ] 写 `tests/unit/test_data_pipeline_smoke.py`，至少 8 个 assert：OHLCV schema 合规 / 缺失数据 / 退市检测 / ADV20 计算 / 时间窗口 / 货币单位 / 价格非负 / volume 非负

### 14:00 – 16:00 写第一个 PR
- [ ] 在 `tier1/data_pipeline/yahoo.py` 把 Yahoo Finance 适配器实现完整（参考已有 docstring 的接口）
- [ ] 重点：所有 OHLCV 输出必须经过 `schemas.data.OHLCV` Pydantic 校验
- [ ] 提 PR "C1: implement Yahoo adapter (罗阳 D1)"

### 16:00 – 17:30 与 王选策 1:1
- [ ] 议题 1：S1 周末前 C1 是否真能 99.5% 跑稳
- [ ] 议题 2：Yahoo 限流策略 / fallback 链
- [ ] 议题 3：是否启用 Alpha Vantage / Refinitiv 作为 2nd source

---

## 第一周目标 (Week 1 · S1)

| 工作日 | Output | DoD |
|---|---|---|
| Mon | yahoo.py + lbma.py 适配器 | `pytest tests/unit/test_data_pipeline.py` 全绿 |
| Tue | lme.py + asx_index.py + consensus.py | 10 个 unit test，覆盖 cache / retry / fallback |
| Wed | orchestrator.py 编排（Prefect tasks） | Smoke test 跑通 478 标的 < 90s |
| Thu | 退市检测 + ADV20 计算 + stale_warning 字段 | golden dataset 5 退市标的 100% 检出 |
| Fri | OpenTelemetry span 接入 + Prometheus metrics | Grafana 看到 `data_freshness_seconds` |

---

## 关键联系人

| 找谁 | 何时 |
|---|---|
| 陈夏童 | 因子需要的字段是否齐全、回测窗口长度 |
| 张涛 | Prefect 编排、性能、缓存策略 |
| 付岩 | Excel 渲染需要的字段 |
| 王选策 | 数据源选型、商业数据合同（LBMA/LME） |

## 文件入口

```
tier1/data_pipeline/yahoo.py         ← 你主战场
tier1/data_pipeline/lbma.py          ← 你主战场
tier1/data_pipeline/lme.py           ← 你主战场
tier1/data_pipeline/asx_index.py     ← 你主战场
tier1/data_pipeline/orchestrator.py  ← 你主战场
schemas/data.py                      ← 改前必跟陈夏童打招呼（D3）
```

## 不可妥协

- **D3 — Pydantic 单一来源**：所有 OHLCV / Consensus / DataResponse 输出必须走 `schemas.data.*`，不要私造 dataclass。
- **SLO 99.5%**：每月只有 3.6 小时 error budget。设计时优先想"失败了怎么 fallback"。
- **数据源不可信任**：Yahoo / LBMA / LME 返回的字符串字段如果会 forward 到 LLM context，必须先经 `safety.sanitizer`。

## D2-D5 计划

- **D2**: LBMA + LME 适配器
- **D3**: orchestrator.py + Prefect 集成
- **D4**: 退市检测 + ADV20
- **D5**: 可观测性接入（OTel + Prometheus）

## 你应该问王选策的问题

1. 哪些商业数据源已经签合同了（LBMA/LME 是否就绪）
2. 数据缓存的政策（保留多久？哪些字段会变更？）
3. 当 Yahoo 限流时的 fallback 策略
4. ASX 退市公司的特殊处理流程

---

*last updated: 2026-05-25 by Xuan-Ce*
