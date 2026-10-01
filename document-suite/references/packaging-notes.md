# 打包说明（Packaging Notes）

## 来源

本技能包由本地已安装的 Expert「理文文 / Paige（文档处理专家）」**提取打包**而成。

- **原专家插件路径**：`~/.workbuddy/plugins/marketplaces/experts/plugins/document-skills/`
- **插件标识**：`document-skills` v1.0.1，作者 CodeBuddy Teams
- **原插件构成**：1 份 agent 提示词（`agents/document-processing-expert.md`，即专家的"人格与工作方式"）+ 4 个技能（`skills/docx`、`skills/xlsx`、`skills/pptx`、`skills/pdf`）
- **打包时间**：2026-09-24

## 做了什么

1. **提取能力层**：把 4 个技能的全部内容（操作手册 + 脚本 + schema + 模板）复制成本技能包的 `modules/docx|pptx|xlsx|pdf`。
2. **新增总入口**：撰写 `SKILL.md` 做格式路由与通用铁律统一，这正是原专家 agent 提示词在做的事（原提示词里的"先问用途再动手""保留原始模板""中文排版规范"等原则已整合进 `SKILL.md` 的「通用铁律」）。
3. **模块手册规范化**：各模块原 `SKILL.md` 改名为 `GUIDE.md`，剥离 YAML frontmatter（避免与技能系统冲突），保留完整正文，并在顶部加注路径提示。
4. **清理无用文件**：移除 `__pycache__`、`.pyc`、空 `__init__.py`，以及面向内部仓库构建流程的 `build.sh`。

## 未包含

- **专家的头像与展示元数据**（`avatars/`、插件 `plugin.json` 中的 displayName / profession / quickPrompts 等）——那些是"专家商店"的上架信息，与文档处理能力无关。
- 原 agent 提示词中的**角色人格设定**（自称"理文文"等）。本技能包只保留其**工作方法与原则**，不绑定人格。

## 许可与免责

原作者声明为 **Proprietary（专有许可）**，其 frontmatter 注明 "LICENSE.txt has complete terms"，但插件包内并未随附 LICENSE.txt 文件。

因此请注意：

- 本技能包**仅供个人在本机使用**。
- 如需**对外分发、商业使用或二次发布**，请先向原作者（CodeBuddy Teams / 插件来源方）确认授权，不要直接转发。
- 本包未做任何代码改写，脚本逻辑与原始版本一致；仅调整了文档命名与目录组织方式。

## 维护

若上游专家插件升级（`~/.workbuddy/plugins/marketplaces/experts/plugins/document-skills/` 内文件更新），可用同样流程重新提取：复制 4 个 `skills/*` 目录 → 重命名 `SKILL.md` 为 `GUIDE.md` → 保留本包的总入口 `SKILL.md`。