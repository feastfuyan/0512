# D1 Onboarding · 付岩 (Fu Yan)

**Role**: Excel / Document Engineer · Owner of C5 (excel-renderer)
**Reports to**: 王选策 (CEO)
**Buddy this week**: 陈夏童 (字段需求) + 杜慧仪 (合规与免责声明)

> 你负责把 Tier 1+2 的输出渲染成 Goldman Sachs 风格的 Excel。这是用户最后看到的东西，是脸面。

---

## 第一天清单

### 09:00 – 10:00 环境就绪
- [ ] `git clone <repo>` 然后 `make setup`
- [ ] `make test-adversarial` 必须 55/55 全绿
- [ ] `make smoke` 跑通，看 `output/sample.xlsx` 输出长什么样

### 10:00 – 11:00 读架构
- [ ] 读 `docs/ARCHITECTURE.md` §1（C5 部分）
- [ ] 读 `schemas/publish.py` 与 `schemas/scores.py`
- [ ] 拉一份 v1 的 Excel sample 看（陈夏童给）
- [ ] 在 `docs/adr/0001-tier-architecture.md` 末尾签"已读已认同"

### 11:00 – 13:00 触摸代码
- [ ] 跑 `python -m tier1.excel_renderer.demo`
- [ ] 写 `tests/unit/test_excel_renderer_smoke.py`：开 .xlsx 文件断言 sheet 数 / cell 内容 / 合规 disclaimer 文本存在
- [ ] 用 openpyxl 打开 v1 sample，把模板里的字号 / 颜色 / 列宽抄到 `tier1/excel_renderer/templates/stockstudy.xlsx.j2`

### 14:00 – 16:00 写第一个 PR
- [ ] 把 v1 Excel 模板的 5 个核心 sheet 移植：Cover, Top10, Bottom10, AllScores, Disclaimer
- [ ] 强约束：`compliance/disclaimer.txt` 的全文必须出现在最后一个 sheet
- [ ] 提 PR "C5: port v1 template (付岩 D1)"

### 16:00 – 17:30 与 王选策 1:1
- [ ] 议题 1：还有哪些 sheet 是 v3.2 新增（regime / narrative / 因子归因等）
- [ ] 议题 2：用户 push 渠道（邮件 / Slack / NAS 直接落盘？）
- [ ] 议题 3：Excel 文件命名规范 / 归档路径

---

## 第一周目标 (Week 1 · S1)

| 工作日 | Output | DoD |
|---|---|---|
| Mon | 5 个核心 sheet 模板移植 + jinja2 化 | `make smoke` 输出 .xlsx 可正常打开 |
| Tue | Narrative sheet（中英双语） + 因子归因 visualization | Narrative 文本不超过列宽 |
| Wed | Excel 输出经 `OutputGate.gate()` 验证 | restricted issuer 测试用例 100% 被截断 |
| Thu | 文件命名 / 归档 / Slack 推送 | 一键点推送 link 即可下载 |
| Fri | 单元测试 ≥ 5 + 一致性测试（v1 vs v3.2 表头） | CI 全绿 |

---

## 关键联系人

| 找谁 | 何时 |
|---|---|
| 陈夏童 | 需要哪些字段、字段顺序、字段格式 |
| 杜慧仪 | Disclaimer 文本、Restricted issuer 列表 |
| 罗阳 | 数据上游字段是否齐全 |
| 王选策 | 推送渠道决策、向客户的最终 sample 审核 |

## 文件入口

```
tier1/excel_renderer/renderer.py        ← 你主战场
tier1/excel_renderer/templates/*.j2     ← 你主战场
compliance/disclaimer.txt               ← 改前必跟杜慧仪打招呼
schemas/publish.py                      ← 改前必跟陈夏童打招呼
```

## 不可妥协

- **D3**：`PublishArtifactModel` 是你输出的唯一契约。
- **Disclaimer 必须 100% 完整出现**：`OutputGate` Layer 3 会自动 block 不含 disclaimer 的 artifact。
- **不写敏感词**：banned_phrases.yaml 列出的词一旦出现在 cell 文本里，OutputGate 立刻 block。

## D2-D5 计划

- **D2**: Narrative sheet 中英双语
- **D3**: 接 OutputGate + 完整合规链路
- **D4**: 推送通道（Slack / 邮件）
- **D5**: 测试 + sample 给客户预览

## 你应该问王选策的问题

1. 客户最终拿到 Excel 的形式（邮件附件 / SharePoint / NAS）
2. Excel 模板的品牌字体（是否要 Georgia）
3. 命名规范：`StockStudy_YYYYMMDD_v3.2.xlsx` 还是别的

---

*last updated: 2026-05-25 by Xuan-Ce*
