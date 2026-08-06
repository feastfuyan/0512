# KICKOFF · StockStudy-Native v3.2

**Date**: 2026-05-25 · **Status**: LOCKED, ready to start S0
**From**: 王选策 (CEO) · **To**: 全员 (陈夏童, 罗阳, 付岩, 张涛, 杜慧仪)

---

## 一、定调 / Framing

v3.2 是工程项目，不是 spec 项目。我们已经过了画 PPT 的阶段，现在要写代码。

The v3.2 work begins as an engineering project — not a spec project. We are past the "draw architecture diagrams" phase. From today onward we ship code.

- **代码总量 ~6000 行**（Tier 1 ~3500 + Tier 2 ~1500 + Safety+Schema+Obs ~1000）
- **时间窗 4 周**（S0 准备 → S1 Tier 1 → S2 Tier 2 → S3 红队+Shadow → S4 切换）
- **质量门**：每周五 17:00 demo + `make test` 必须全绿，否则下周暂停新功能、修 bug 优先
- **沟通**：Slack #stockstudy-v32 · 日 standup 周一 9:30 · 周五 demo 16:30

## 二、明天 (D1) 每个人必做的三件事 / Three things each of you must do on Day 1

| 人 | Day 1 三件事 |
|---|---|
| **陈夏童** | (1) 跑 `make test-adversarial` 55/55 全绿 (2) 在 `knowledge/heuristics/red_flags.yaml` 加 5 条 red flag (3) 与我 1:1 敲定 30 只标的 |
| **罗阳** | (1) 跑 `make smoke` 通过 (2) 实现 `tier1/data_pipeline/yahoo.py` Yahoo 适配器 (3) 与我 1:1 敲定 LBMA / LME 合同状态 |
| **付岩** | (1) 跑 `make smoke` 通过 (2) 移植 v1 Excel 模板 5 个 sheet 到 `tier1/excel_renderer/templates/` (3) 与我 1:1 敲定推送渠道 |
| **张涛 (CTO)** | (1) Jaeger / Grafana 完全跑通 (2) 把现有 Honey 仿真器代码移植到 `tier3/tools/honey.py` (3) 给我一份 architectural review redline |
| **杜慧仪** | (1) 跑 `make test-adversarial` 55/55 全绿 (2) Restricted Issuer 列表 ≥5 只 + Banned Phrase ≥5 条 (3) 新增 3 个 PI 用例 PR |

每个人都有专属的 D1 文档：

```
docs/onboarding/D1_chen_xiatong.md
docs/onboarding/D1_luo_yang.md
docs/onboarding/D1_fu_yan.md
docs/onboarding/D1_zhang_tao.md
docs/onboarding/D1_du_huiyi.md
```

D1 文档里有每个人 D2-D5 的 task。读完它，不需要找我确认下一步。

## 三、四周 Sprint Plan / Sprint Plan

| Week | Sprint | 主题 | 周末验收 |
|---|---|---|---|
| W0 (this week, half-week) | S0 | Eval-First Foundation | docker-compose up; `make test-adversarial` 55/55; D1 onboarding 全员 acknowledge |
| W1 | S1 | Tier 1 Workflow (data + factor + backtest + risk + excel) | Tier 1 端到端 Prefect DAG 跑通；golden 30 标的 IC ≥ 0.06；Brier ≤ 0.22 |
| W2 | S2 | Tier 2 LLM 增强 (Agent-XT-Reasoner + Sentinel) | A1 narrative 人评 ≥ 4.0；A2 误报率 ≤ 5%；prompt registry 就位 |
| W3 | S3 | Adversarial + Knowledge Encoding + Shadow Run 启动 | 70 PI 用例 100% 拦截；E4 一致性 ≥ 80%；shadow run 第 1 周完成 |
| W4 | S4 | Tier 3 + 切换正式生产 | A3 monthly_evolve 演练；Shadow 全部门槛达标；CEO + 杜慧仪 联合签字 → v3.2 上线 |

## 四、不可妥协的 10 条 / The Constitution

`README.md` 第 3 章列出了 D1-D10 十条最高纲领。违反一条 PR 一律 reject。重点重复 3 条最常被违反的：

1. **D5 — Evals First**：每个 PR 必先有 ≥5 个 test cases 通过才能 merge.
2. **D6 — 三层 PI 防护缺一不可**：50 用例 100% 拦截不达标，不能上 production.
3. **D7 — LLM 不做最终判断**：所有质量门、合规门必须 numerical/rule 层先过，LLM 仅做 advisory.

## 五、第一周日常节奏 / Weekly Cadence

- **Mon 09:30** standup（15 min）：每人说 (a) 上周完成了什么 (b) 这周做什么 (c) blocker
- **Wed 14:00** mid-week sync（30 min，可选）：技术细节问题集中讨论
- **Fri 16:30** demo（45 min）：每人 5 分钟，show 你这周写的代码 / 测试
- **Slack** #stockstudy-v32：日常异步；@here 仅紧急；周末非紧急不打扰

## 六、对外口径 / External Comms

v3.2 在 S4 切换正式上线之前，对外（包括其他部门同事）一律说"在做技术升级，预计 Q3"。不要透露版本号、不要透露 Tier 化设计、不要给客户预览。

Until S4 cutover, external comms (including to other LynAI teams) should say only "engineering upgrade in progress, ETA Q3". Do not disclose version numbers, tier architecture, or give clients a preview.

## 七、紧急情况 / Emergency

- **PI critical 命中 production**：立即 Slack @杜慧仪 + @张涛 + @我（电话也行）
- **数据源大面积 fail**：立即 Slack @罗阳 + 我
- **预算预警 ≥ 80%**：自动进 degrade 模式，无需人介入；100% 触发时 PagerDuty 找张涛 + 我
- **CEO 不在 / 不可达**：杜慧仪 + 张涛 二人会签即可决定

5 个 incident playbook 在 `docs/playbooks/IP-1 ~ IP-5.md`。

---

## English Version

**Subject**: StockStudy-Native v3.2 Engineering Kickoff

Team,

v3.2 is an engineering project, not a spec project. We are done drawing architecture diagrams; from today onward we ship code.

- **Scope**: ~6,000 lines of code (Tier 1 ~3,500 + Tier 2 ~1,500 + Safety/Schema/Obs ~1,000)
- **Timeline**: 4 weeks (S0 prep → S1 Tier 1 → S2 Tier 2 → S3 red-team + shadow → S4 cutover)
- **Quality gate**: Friday 17:00 demo every week; `make test` must be green or new features pause
- **Comms**: Slack #stockstudy-v32 · Mon standup 09:30 · Fri demo 16:30

Day-1 actions for each of you are in `docs/onboarding/D1_<your_name>.md`. Read it; don't ask me what's next.

Three rules I will not negotiate:

1. **D5 — Evals First**: every PR needs ≥5 passing test cases before merge.
2. **D6 — Three-layer PI defence is non-negotiable**: 50 adversarial cases must pass 100% in CI.
3. **D7 — LLM is never the final arbiter**: every quality / compliance gate must have a numerical or rule layer ahead of the LLM. LLM is advisory.

Five sprints in four weeks. Public cutover when S4 ends.

For emergencies: incidents playbook in `docs/playbooks/IP-1 ~ IP-5.md`.

Let's ship.

— Xuan-Ce / 王选策
LynAI Mines · Founder & CEO
2026-05-25
