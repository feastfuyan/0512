---
name: code-review-agent
description: 代码审查 Agent 编排器。克隆仓库 → 多模型并行审查 → 汇总评分报告。比传统 skill 更高效：独立会话、多模型交叉验证、不污染主上下文。
version: 1.0.0
triggers:
  - 代码审查
  - code review
  - 审查代码
  - 代码评分
  - review commits
---

# 代码审查 Agent 编排器

## 为什么用 Agent 而不是 Skill

| 对比维度 | Skill（传统方式） | Agent（本方案） |
|----------|-------------------|-----------------|
| 上下文 | 审查内容塞进主会话，token 爆炸 | 独立子会话，互不干扰 |
| 模型选择 | 主会话模型一手包办 | 每个子 agent 可指定不同模型 |
| 并行能力 | 串行执行 | 3+ 子 agent 并行审查 |
| 持久化 | 结果只存在聊天记录里 | 自动输出 Excel + Markdown 归档 |
| 一致性 | 每次靠人工描述审查标准 | Agent system prompt 固化标准 |

## 触发方式

用户说「代码审查」「审查代码」「review commits」等即触发。

可选参数：
- `周期`：默认本周一至今天
- `开发者`：默认全部（夏童、薛娴、林素雅、慧怡），可指定某人
- `仓库`：默认 monorepo + data-pipeline，可指定

## 执行流程

### Step 1：确认参数

如果用户未指定，使用默认值：
- 周期：本周一至今天
- 开发者：全部 4 人
- 仓库：monorepo + data-pipeline

### Step 2：克隆仓库

```bash
rm -rf /tmp/code-review-*
git clone https://github.com/lynaimining/lynai-miningclawd-monorepo /tmp/code-review-mono
git clone https://github.com/lynaimining/lynai-miningclawd-data-pipeline /tmp/code-review-data
```

### Step 3：提取本周 commits

按开发者提取本周 commits，生成审查数据摘要。

### Step 4：多模型并行审查（核心差异化）

同时 spawn 3 个子 agent，每个用不同模型和关注点：

**Agent A — 安全与合规审查（模型：Claude Sonnet）**
- 硬编码 IP/端口/URL/路径
- 明文密码/API key/token
- SQL 注入/XSS/CSRF 漏洞
- .gitignore 完整性
- 敏感信息泄露

**Agent B — 架构与工程质量审查（模型：GLM）**
- 代码结构与模块化
- 设计模式合理性与配置外部化
- CI/CD 接入完整性
- 测试覆盖（单元/集成/smoke test）
- 研发文档与 Context 记录

**Agent C — 逻辑与规范审查（模型：DeepSeek）**
- 业务逻辑正确性
- 错误处理与边界情况
- Commit 颗粒度与 Conventional Commits
- AG 任务编号接入
- 研发日志质量
- PR 规范（squash merge、description）

```python
# spawn 3 个子 agent
sessions_spawn(
    task="审查 {developer} 本周在 monorepo 的代码提交...",
    agentId="code-review-security",  # Agent A
    model="newapi2/claude-sonnet-4-5",
    attachments=[...]  # commits 摘要
)
```

### Step 5：汇总评分

收集 3 个子 agent 的审查结果，按 11 维×10 分=110 分体系汇总：

| 分组 | 维度 | 权重 | 来源 Agent |
|------|------|------|-----------|
| 个人表现(50) | 沟通响应 | 10 | C |
| | 时间投入 | 10 | C |
| | 代码质量 | 10 | B |
| | 效率 | 10 | C |
| | 团队协作 | 10 | C |
| 安全质量(20) | 测试覆盖 | 10 | B |
| | 安全合规 | 10 | A |
| 工程规范(40) | AG任务编号 | 10 | C |
| | CI接入 | 10 | B |
| | Commit颗粒度 | 10 | C |
| | 开发日志 | 10 | C |

### Step 6：生成报告

输出 Excel 评分表（对齐模板 `代码审查模板.xlsx`）+ Markdown 摘要。
保存到 `/Users/feast/Desktop/MC周报/weekly/YYYYMMDD_代码审查报告.xlsx`。

### Step 7：收尾

```bash
afplay /System/Library/Sounds/Glass.aiff
say -v Tingting "代码审查完成，报告已生成"
open /Users/feast/Desktop/MC周报/weekly/
```

## 配置

审查标准配置文件：`config.yaml`

```yaml
repos:
  - name: monorepo
    url: https://github.com/lynaimining/lynai-miningclawd-monorepo
  - name: data-pipeline
    url: https://github.com/lynaimining/lynai-miningclawd-data-pipeline

developers:
  - name: 夏童
    github: xiatong
    alias: [acxt, cxt, 陈夏彤]
  - name: 薛娴
    github: xuexiansc-bit
    alias: [xian]
  - name: 林素雅
    github: Linsuya
    alias: [KIP, 素雅]
  - name: 慧怡
    github: huiyi
    alias: [冬末, 杜慧仪]

models:
  security: newapi2/claude-sonnet-4-5  # 安全审查
  architecture: zai/glm-5              # 架构审查
  logic: deepseek/deepseek-v4-pro      # 逻辑审查

red_lines:
  - 硬编码 IP/端口/URL/路径/阈值
  - 明文密码/API key/token
  - 研发日志残留（console.log/print/debugger/注释代码）
  - 零测试文件
  - 敏感文件未纳入 .gitignore

output_dir: /Users/feast/Desktop/MC周报/weekly
template: /Users/feast/Desktop/MC周报/weekly/代码审查模板.xlsx
```
