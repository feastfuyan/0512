---
name: report-scorecard
description: "对研究报告/矿业报告/法律文书进行多维度专业评分。支持4种模板（默认/矿业/法律/技术评估），输出评分卡+数据源质量评估+优化建议。触发词：'给报告打分'、'评估报告质量'、'score this report'、'报告评分'。"
version: "2.0.0"
---

# Report Scorecard v2.0 — 专业报告质量评分

## 概述
对任意报告进行多维度专业度评分，输出结构化评分卡 + 数据来源质量评估 + 优化方向建议。支持 PDF/Word/Markdown/HTML 输入，输出 JSON + Excel + HTML 三种格式。

## 四种评分模板

| 模板 | 维度数 | 适用场景 |
|------|--------|---------|
| default | 10 | 通用研究报告、分析文档 |
| mining | 12 | 矿业报告（含JORC/矿权合规/地质数据可靠性） |
| legal | 10 | 法律/合规报告（含法规引用准确性/法律逻辑） |
| tech-eval | 12 | 技术评估/可行性分析报告 |

## 使用方式

### 方式一：对话触发
> "用矿业模板给这份报告打分"

### 方式二：命令行
```bash
# 评分
python3 scripts/score.py <报告文件> --template mining --provider deepseek --model deepseek-v4-pro

# 导出 Excel
python3 scripts/excel_export.py <评分结果.json>

# 导出 HTML
python3 scripts/html_export.py <评分结果.json>
```

### 方式三：多模型审查
```bash
# DeepSeek 深度审查
python3 scripts/score.py <报告> --template mining --provider deepseek --model deepseek-v4-pro

# Claude Sonnet 审查
python3 scripts/score.py <报告> --template mining --provider api147 --model claude-sonnet-4-6

# 对比两个模型的评分差异
```

## 评分输出

### 维度评分
每维度 0-10 分，加权计算总分，A+ 到 F 等级。

### 数据来源质量评估
- 自动提取报告中的数据引用
- 分类：权威/可靠/可疑/不可验证
- 计算数据质量分

### 优化建议
三级优先级（critical/high/medium），每条含：
- 当前状态
- 具体改进方案
- 预期影响

## 输出格式
- **JSON**：`~/Documents/MiningClawd/scorecards/`（自动保存）
- **Excel**：3个 Sheet（评分总览+雷达图、数据源评估、优化建议）
- **HTML**：可视化评分卡，浏览器直接打开

## 文件结构
```
report-scorecard/
├── SKILL.md
├── config/
│   ├── default.yaml
│   ├── mining.yaml
│   ├── legal.yaml
│   └── tech-eval.yaml
├── scripts/
│   ├── score.py            # 核心评分引擎
│   ├── report_parser.py    # 报告解析器
│   ├── excel_export.py     # Excel导出
│   └── html_export.py      # HTML导出
├── tests/
│   └── test_scoring.py     # 单元测试
└── samples/                # 测试报告
```

## 支持的模型
| 模型 | Provider | 角色 |
|------|----------|------|
| DeepSeek V4 Pro | deepseek | 深度分析 |
| DeepSeek V4 Flash | deepseek | 快速扫描 |
| Claude Sonnet 4.6 | api147 | 对照审查 |
| GLM-5.1 | zai | 默认模型 |

## 配置
- 输出目录：`SCORECARD_OUTPUT_DIR` 环境变量（默认 `~/Documents/MiningClawd/scorecards/`）
- 缓存：同文件+同模板不重复调用模型
