# D1 Onboarding · 杜慧仪 (Du Huiyi)

**Role**: Compliance / Safety Lead · Owner of C6 (safety-gate) + A2 (Compliance-Sentinel)
**Reports to**: 王选策 (CEO)
**Buddy this week**: 张涛 (架构 + 平台支撑)

> 你是 v3.2 最关键的守门人。Safety 跑红了，公司出监管事故。50 个 PI 用例 + Restricted Issuer + Banned Phrase 全部由你负责。LLM 不替你做决定。

---

## 第一天清单

### 09:00 – 10:00 环境就绪
- [ ] `git clone <repo>` 然后 `make setup`
- [ ] `docker compose up -d`
- [ ] **`make test-adversarial` 必须 55/55 全绿（这是你最关心的）**
- [ ] `make smoke` 跑通

### 10:00 – 11:30 读架构 + safety code
- [ ] 读 `docs/ARCHITECTURE.md` §3 全篇
- [ ] 读 `safety/sanitizer.py` / `tool_guard.py` / `output_gate.py`（你 owner 的代码）
- [ ] 读 `safety/patterns/pi_patterns.yaml`（50 PI 用例对应的 patterns）
- [ ] 读 `tests/adversarial/pi_*.py` 全部 6 个文件
- [ ] 读 `compliance/restricted_issuers.yaml` + `banned_phrases.yaml` + `disclaimer.txt`
- [ ] 在 `docs/adr/0003-three-layer-safety.md` 末尾签"已读已认同"

### 11:30 – 13:00 触摸代码
- [ ] 给 `compliance/restricted_issuers.yaml` 加入真实的 restricted 标的（≥5 只）
  - 来源：ASIC, ASX 公告, 内部 watchlist
- [ ] 给 `compliance/banned_phrases.yaml` 加入你认为缺漏的 phrase（≥5 条）
- [ ] 提 PR "compliance: initial restricted list (杜慧仪 D1)"

### 14:00 – 16:00 写第一个 vibe code 任务
- [ ] 设计 3 个新的 PI 用例 ——
  - 1 个针对中文媒体语义（如 "据可靠内部消息..."）
  - 1 个针对 PDF 公告隐写（你想到的方式）
  - 1 个针对最新攻击（参考 Anthropic Red Teaming 公开论文）
- [ ] 把 3 个用例加到对应的 `tests/adversarial/pi_*.py`
- [ ] 加 patterns 到 `safety/patterns/pi_patterns.yaml`
- [ ] 跑 `make test-adversarial` 必须 58/58 全绿
- [ ] 提 PR "safety: 3 new PI cases (杜慧仪 D1)"

### 16:00 – 17:30 与 王选策 1:1
- [ ] 议题 1：Restricted Issuer 列表来源（ASIC？内部？审批流？）
- [ ] 议题 2：Disclaimer 文本是否需要法律团队签字
- [ ] 议题 3：当 Sentinel LLM 故障时的降级策略（D7）

---

## 第一周目标 (Week 1 · S0/S1)

| 工作日 | Output | DoD |
|---|---|---|
| Mon | Restricted Issuer 列表 ≥10 只 + Banned Phrase ≥20 条 | OutputGate test 全绿 |
| Tue | 新增 5 个 PI 用例 + 对应 patterns | 60/60 PI 全绿 |
| Wed | Compliance-Sentinel v1.0 prompt 写完 | `prompts/compliance_sentinel/v1.0.0.md` |
| Thu | A2 误报率测试集 100 例 clean narrative | 误报率 ≤ 5% |
| Fri | Red-team 演练第一次：拿 3 个真实新闻 + 3 个 PDF | 100% 拦截 |

---

## 关键联系人

| 找谁 | 何时 |
|---|---|
| 张涛 | safety code 架构改动 / Prometheus metrics |
| 陈夏童 | narrative 风格 / 哪些 phrase 容易误判 |
| 罗阳 | 数据源是否会带恶意文本 |
| 付岩 | Excel 输出是否含 disclaimer |
| 王选策 | 监管口径、法律团队对接、重大事件通报 |

## 文件入口

```
safety/sanitizer.py              ← 你主战场
safety/tool_guard.py             ← 你主战场
safety/output_gate.py            ← 你主战场
safety/patterns/pi_patterns.yaml ← 你主战场
compliance/restricted_issuers.yaml ← 你主战场
compliance/banned_phrases.yaml     ← 你主战场
compliance/disclaimer.txt          ← 你主战场（改前需法律 review）
tests/adversarial/pi_*.py          ← 你主战场（红队用例）
tier2/compliance_sentinel.py       ← 你主战场
prompts/compliance_sentinel/       ← 你主战场
docs/playbooks/IP-3.md             ← 你主战场（incident playbook）
```

## 不可妥协

- **D6 — 三层 PI 防护**：sanitizer + tool_guard + output_gate 永远三层，不允许只一层。
- **D7 — LLM 不做最终判断**：Compliance-Sentinel 输出 `ComplianceWarningList`，是 advisory，最终 pass/fail 在 OutputGate 的规则层。
- **50 用例 100% 拦截**：CI 跑红的 PR 一律 reject，无例外。
- **Restricted/Banned 加入 = PR + 双人签字**：你 + 王选策（或法律顾问）。

## D2-D5 计划

- **D2**: 红队用例扩展 + Sentinel prompt
- **D3**: Compliance-Sentinel 实现完整 + 100 例误报测试
- **D4**: Red-team 第一次正式演练
- **D5**: Incident playbook IP-3 文档化

## 你应该问王选策的问题

1. 谁是 v3.2 的"first responder"（PI critical 命中时的电话）？
2. ASIC 是否有要求我们提交安全自评报告
3. Anthropic 是否提供 enterprise 红队工具

---

*last updated: 2026-05-25 by Xuan-Ce*
