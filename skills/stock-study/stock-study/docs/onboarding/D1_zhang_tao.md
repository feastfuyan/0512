# D1 Onboarding · 张涛 (Zhang Tao, CTO)

**Role**: CTO · Owner of Honey 仿真器 + A3 (Agent-ZT-Evolver) + 横切平台
**Reports to**: 王选策 (CEO)
**Buddy this week**: 全员（你是 platform owner）

> 你是 CTO，但 D1 你拿到的 owner 角色只是 A3 + Honey + 横切平台（observability / budget / prompt registry / 仿真器）。Tier 1/2 的具体业务代码由陈夏童主导，你做横向支援与最终架构守门人。

---

## 第一天清单

### 09:00 – 10:00 环境就绪
- [ ] `git clone <repo>` 然后 `make setup`
- [ ] `docker compose up -d` 起完整可观测栈
- [ ] `make test-adversarial` 必须 55/55 全绿
- [ ] `make smoke` 跑通
- [ ] 打开 `http://localhost:16686`（Jaeger）和 `http://localhost:3000`（Grafana）确认能看到 trace

### 10:00 – 12:00 读架构（你最深）
- [ ] 读 `docs/ARCHITECTURE.md` 全篇（你是平台负责人，要全懂）
- [ ] 读 5 份 ADR（`docs/adr/0001-0005.md`）
- [ ] 读 `observability/` 全部代码
- [ ] 读 `safety/` 全部代码
- [ ] 读 `prompts/agent_zt_evolver/v1.0.0.md`
- [ ] 在 `docs/adr/0001-tier-architecture.md` 末尾签"已读已认同"

### 13:00 – 15:00 横向 review
- [ ] 跑一遍 `make daily`（用真 API key），观察 Jaeger trace，记下"哪些 span 缺失/不规范"
- [ ] 写一份 review notes `docs/reviews/W0_tao_review.md`，提 3 个最重要的改进点
- [ ] 给 王选策 一张 redline list（最影响 SLO 的 3 件事）

### 15:00 – 17:00 写第一个 PR
- [ ] 把 Honey 仿真器骨架放进 `tier3/tools/honey.py`（如果有现有代码就移植）
- [ ] 实现 sim-to-real gap 检查：`tier3/tools/honey.py::health_check()` 返回 Wasserstein distance
- [ ] 提 PR "T3: Honey health_check skeleton (张涛 D1)"

### 17:00 – 18:00 与 王选策 1:1
- [ ] 议题 1：S4 周末前 Agent-ZT-Evolver 能否真上线
- [ ] 议题 2：Champion 切换 / Prompt rollback 流程，哪里需要你额外搭建
- [ ] 议题 3：你 D1-D5 的 task 排序

---

## 第一周目标 (Week 1 · S0/S1 横向支援)

| 工作日 | Output | DoD |
|---|---|---|
| Mon | 全套 OTel + Jaeger + Grafana + Prometheus 跑通 | 任意 LLM call 在 Jaeger UI 30 秒内可见 |
| Tue | Prompt registry CLI (`make rollback`) 实现 | `make rollback PROMPT=agent_xt_reasoner@v1.0.0` 工作 |
| Wed | BudgetGuard 集成测试 + 4 级告警链路 | 模拟 100% 月度 → degrade mode 触发 |
| Thu | Honey 仿真器接口骨架 + 100 历史窗口的 sim/real 对照测试 | `pytest tests/unit/test_honey.py` 全绿 |
| Fri | 张涛 architectural review report → 全员 | 你给团队的"架构守门"周报 |

---

## 关键联系人

| 找谁 | 何时 |
|---|---|
| 陈夏童 | 任何 LLM call 设计 / sklearn 性能 / sim-to-real |
| 罗阳 | 数据延迟、Yahoo SLA |
| 杜慧仪 | safety 模式更新、PI patterns 加入 |
| 付岩 | Excel 输出性能 |
| 王选策 | Champion 切换签字、模型选型 |

## 文件入口

```
tier3/agent_zt_evolver.py        ← 你主战场
tier3/tools/honey.py             ← 你主战场（Honey 仿真）
observability/*                  ← 你横向 owner
safety/sanitizer.py              ← 你横向 review（杜慧仪 owner）
prompts/registry.yaml            ← 你横向 owner
infra/grafana/dashboards/*       ← 你横向 owner
workflows/monthly_evolve.py      ← 你主战场
```

## 不可妥协

- **D2 — RFC 必须**：你新增 A3 的 tool，必须先在 `docs/adr/` 写 ADR。
- **D4 — Budget 是 hard gate**：BudgetGuard.precheck() 抛 `BudgetExceeded` 时不可吞掉。
- **D10 — Champion 签字**：你执行 champion 切换的 SQL/CLI 时必有 CEO 签字邮件。
- **A3 仿真闭环**：Honey sim-to-real Wasserstein ≤ 0.1 才允许用 challenger 提名上线（参见 incident playbook IP-5）。

## D2-D5 计划

- **D2**: prompt registry + rollback CLI
- **D3**: BudgetGuard 集成测试
- **D4**: Honey 健康检查与 sim/real gap 验证框架
- **D5**: 全团队 architectural review report

## 你应该问王选策的问题

1. 你想我（张涛）多大程度上 own platform？例如 docker-compose + infra 全归我？
2. 月度 Champion 切换的 SOP 你画完了吗？
3. Honey 仿真器现有代码版本（是 v0.3 还是有新分支？）
4. Anthropic 是否给我们 enterprise SLA / 私有 endpoint？

---

*last updated: 2026-05-25 by Xuan-Ce*
