# stock-study-v3.2

LynAI Mines · ASX 矿业股 AI 研究系统 · 生产级开发档案

```
范式: Tier-1 Deterministic Workflow + Tier-2 LLM-Augmented Step + Tier-3 True Agent
状态: LOCKED, 进入 4 周 Sprint
```

## 0. 一分钟启动 / 60-Second Start

```bash
# 1) 起依赖（PG + Redis + Jaeger + Grafana）
docker compose up -d

# 2) Python 环境
make setup              # 创建 venv + pip install -e ".[dev]"

# 3) 拷贝 .env 模板，填入 ANTHROPIC_API_KEY
cp .env.example .env && $EDITOR .env

# 4) 跑 50 PI 用例（应全绿）
make test-adversarial

# 5) 跑 unit + smoke
make test

# 6) 跑一次 daily run（mock data 模式，不调 LLM）
make smoke
```

只要前 5 步全绿，团队就可以并行开始 vibe coding。各人入口见 `docs/onboarding/D1_*.md`。

## 1. 仓库地图 / Repo Map

```
stock-study/
├── workflows/           # Prefect DAG (Tier 1+2 编排, 入口在这里)
├── tier1/               # 确定性 Python (data / factor / backtest / risk / excel)
├── tier2/               # LLM-augmented 单点 (Agent-XT-Reasoner / Compliance-Sentinel)
├── tier3/               # True Agent (Agent-ZT-Evolver, 月度+ad-hoc)
├── safety/              # 三层 PI 防护 (sanitizer / tool_guard / output_gate)
├── schemas/             # Pydantic v2 单一来源, 所有跨组件 contract
├── observability/       # OTel tracing / BudgetGuard / Prometheus
├── prompts/             # System prompts (Git + semver, registry.yaml pin)
├── compliance/          # Restricted issuers / banned phrases / disclaimer
├── knowledge/           # 陈夏童的 IP: 启发式 + golden dataset
├── tests/               # unit + e2e + adversarial (50 PI 用例 ✦)
├── docs/                # ARCHITECTURE.md + ADR + D1 onboarding
└── infra/               # SQL schema + Grafana dashboards
```

## 2. Owner 一览 / Component Owners

| 组件 | Owner | D1 文档 |
|---|---|---|
| C1 data-pipeline | 罗阳 (Luo Yang) | `docs/onboarding/D1_luo_yang.md` |
| C2 factor-engine, C3 backtest-scorer, C4 risk-alert, A1 Agent-XT-Reasoner | 陈夏童 (Chen Xiatong) | `docs/onboarding/D1_chen_xiatong.md` |
| C5 excel-renderer | 付岩 (Fu Yan) | `docs/onboarding/D1_fu_yan.md` |
| C6 safety-gate, A2 Compliance-Sentinel | 杜慧仪 (Du Huiyi) | `docs/onboarding/D1_du_huiyi.md` |
| A3 Agent-ZT-Evolver, Honey 仿真 | 张涛 (Zhang Tao, CTO) | `docs/onboarding/D1_zhang_tao.md` |

## 3. 不可妥协的 10 条 / The Constitution

| # | 纲领 |
|---|---|
| D1 | Workflow first, Agent second. 能用 Prefect DAG 就不用 LLM. |
| D2 | 每个 LLM call 必有 RFC. 见 `docs/ARCHITECTURE.md §6`. |
| D3 | Pydantic v2 单一 Schema 来源. 禁止 proto3 / 第二份 JSON Schema. |
| D4 | Token / Cost / Latency 三联追踪. 每次 LLM call 必经 BudgetGuard. |
| D5 | Evals First. 任一 PR 必先有 ≥5 个 golden test cases 通过才能 merge. |
| D6 | 三层 PI 防护缺一不可. `safety/sanitizer.py` + `tool_guard.py` + `output_gate.py`. |
| D7 | LLM 不做最终 pass/fail. 所有质量门、合规门必须有 numerical/rule 层先过. |
| D8 | Prompt 走 Git + semver. Production 必须 pin 到 `prompts/registry.yaml`. |
| D9 | 交易日 SLA 同步. 开盘前窗口内 escalate 必须 ≤15 min 同步响应. |
| D10 | Champion 切换必有人类签字. 模型/calibrator/prompt major 必须 CEO 签字. |

违反任一条, PR 一律 reject. 详见 `docs/ARCHITECTURE.md`.

## 4. 关键命令 / Cheatsheet

```bash
make setup              # 装依赖
make test               # 全部 unit + adversarial（CI 必跑）
make test-adversarial   # 仅 50 PI 用例
make test-golden        # 仅 golden dataset 测试
make smoke              # 端到端 mock LLM smoke test
make lint               # ruff + mypy
make fmt                # black + isort
make daily              # 真跑一次 daily_run（需 ANTHROPIC_API_KEY）
make grafana            # 打开 http://localhost:3000
make jaeger             # 打开 http://localhost:16686
make budget             # 打印当月花费
make rollback PROMPT=agent_xt_reasoner@v1.0.0   # 回滚 prompt
```

## 5. 编辑约定 / Editing Conventions

- 任何架构级改动 → 写 ADR (`docs/adr/NNNN-title.md`), 走 PR review.
- 新增组件 → 9 组件之外的, 必须新增 ADR + 评审.
- 改 prompt → 走 `prompts/<agent>/v<semver>.md` + 更新 `registry.yaml`.
- 改 schema → Pydantic v2 + alembic migration + 更新影响范围说明.
- 改 safety pattern → 同步更新 `safety/patterns/pi_patterns.yaml` + `tests/adversarial/`.

## 6. 调用约定

- Python 3.11+, 严格 type hints, `from __future__ import annotations`.
- 所有 LLM 调用必走 `tier2/base_agent.py::BaseAgent.invoke`.
- 所有外部输入文本进 LLM context 之前必经 `safety.sanitizer.InputSanitizer.scan()`.
- 所有发布产物进入 publish 之前必经 `safety.output_gate.OutputGate.gate()`.

## 7. License & Confidentiality

CONFIDENTIAL. LynAI Mines internal R&D asset. Do not redistribute.

---

Perth · Hangzhou · Harare
